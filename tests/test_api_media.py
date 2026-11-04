import json
import shutil
import subprocess
from pathlib import Path
import httpx
import pytest
from api import media, providers


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg absent")
def test_real_audio_and_spoofed_upload(tmp_path):
    original = tmp_path / "input.wav"
    subprocess.run(
        [
            "ffmpeg",
            "-nostdin",
            "-y",
            "-v",
            "error",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:duration=1",
            str(original),
        ],
        check=True,
    )
    audio, duration = media.prepare_audio(original, tmp_path)
    assert 0.9 < duration < 1.1 and audio.stat().st_size > 0
    clip = media.clip_audio(audio, 0, 0.5, tmp_path / "clip.mp3")
    assert clip.stat().st_size > 0
    fake = tmp_path / "fake.mp4"
    fake.write_text("#EXTM3U\n/etc/passwd\n")
    with pytest.raises(ValueError):
        media.prepare_audio(fake, tmp_path)


@pytest.mark.parametrize(
    "segments",
    [
        [{"start": -1, "end": 1, "arabic": "هلا"}],
        [{"start": 0, "end": float("inf"), "arabic": "هلا"}],
        [{"start": 0, "end": 1, "arabic": ""}],
        [
            {"start": 1, "end": 3, "arabic": "هلا"},
            {"start": 2, "end": 4, "arabic": "هلا"},
        ],
    ],
)
def test_provider_rejects_invalid(segments):
    with pytest.raises(ValueError):
        providers.validate_segments(segments)


def test_mock_gemini(tmp_path, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "fake")
    monkeypatch.setenv("GEMINI_TRANSCRIPTION_MODEL", "test-model")
    audio = tmp_path / "audio.mp3"
    audio.write_bytes(b"audio")
    expected = {
        "start": 0,
        "end": 1,
        "arabic": "هلا",
        "english": "Hello",
        "transliteration": "hala",
        "explanation": "Greeting",
    }

    def respond(request):
        assert request.url.host == "generativelanguage.googleapis.com"
        config = json.loads(request.content)["generationConfig"]
        assert config["maxOutputTokens"] == 6000
        assert not {"temperature", "top_p", "top_k", "topP", "topK"}.intersection(
            config
        )
        return httpx.Response(
            200,
            json={
                "candidates": [
                    {
                        "content": {
                            "parts": [{"text": json.dumps({"segments": [expected]})}]
                        }
                    }
                ]
            },
        )

    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        assert providers._gemini(audio, client) == [expected]


def test_mock_openai_preserves_transcript(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "fake")
    monkeypatch.setenv("OPENAI_TRANSCRIPTION_MODEL", "whisper-1")
    audio = tmp_path / "audio.mp3"
    audio.write_bytes(b"audio")
    expected = {
        "start": 0,
        "end": 1,
        "arabic": "هلا",
        "english": "Hello",
        "transliteration": "hala",
        "explanation": "Greeting",
    }

    def respond(request):
        if request.url.path.endswith("/transcriptions"):
            return httpx.Response(
                200, json={"segments": [{"start": 0, "end": 1, "text": "هلا"}]}
            )
        return httpx.Response(
            200,
            json={
                "choices": [
                    {"message": {"content": json.dumps({"segments": [expected]})}}
                ]
            },
        )

    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        assert providers._openai(audio, client) == [expected]


def test_ai_disabled_without_explicit_enable(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "fake")
    monkeypatch.setenv("GEMINI_TRANSCRIPTION_MODEL", "test-model")
    monkeypatch.setenv("NAWAB_ENABLE_AI", "false")
    assert providers.provider_name() is None
    with pytest.raises(providers.ConfigurationError):
        providers.transcribe("missing.mp3")


def test_tiktok_redirect_restriction(monkeypatch):
    class Response:
        status = 302

        def getheaders(self):
            return [("Location", "https://evil.example/a")]

        def getheader(self, k):
            return "https://evil.example/a" if k == "Location" else None

    class Connection:
        def __init__(self, *args):
            pass

        def request(self, *a, **kw):
            pass

        def getresponse(self):
            return Response()

        def close(self):
            pass

    monkeypatch.setattr(media, "public_addresses", lambda host: ["8.8.8.8"])
    monkeypatch.setattr(media, "_PinnedHTTPS", Connection)
    with pytest.raises(ValueError, match="approved TikTok"):
        media.safe_fetch("https://www.tiktok.com/a", tiktok_only=True)


def test_process_timeout(monkeypatch):
    def timeout(*a, **kw):
        raise subprocess.TimeoutExpired("ffmpeg", 45)

    monkeypatch.setattr(media.subprocess, "run", timeout)
    with pytest.raises(ValueError):
        media._run(["ffmpeg"])


def test_tiktok_challenge_solver_disabled(tmp_path, monkeypatch):
    from yt_dlp.extractor.tiktok import TikTokIE

    url = "https://www.tiktok.com/@user/video/1234567890123456789"
    monkeypatch.setattr(media, "safe_fetch", lambda *a, **kw: (b"page", url, {}, 200))
    monkeypatch.setattr(
        TikTokIE,
        "extract",
        lambda self, url: self._solve_challenge_and_set_cookies("challenge"),
    )
    with pytest.raises(ValueError, match="requires a challenge"):
        media._extract(url, tmp_path / "video.mp4")
