"""Actual source video and backward-compatible API integration tests; no paid calls."""

import json
import shutil
import sqlite3
import subprocess
from pathlib import Path

import pytest
from api import main, media, providers, db
from test_api import client, segment


@pytest.fixture
def video(tmp_path):
    if not shutil.which("ffmpeg"):
        pytest.skip("ffmpeg required")
    output = tmp_path / "original.mp4"
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
            "testsrc2=size=320x240:rate=30:duration=2",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:duration=2",
            "-c:v",
            "libx264",
            "-threads",
            "1",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-shortest",
            str(output),
        ],
        check=True,
    )
    return output


def upload(client, video):
    result = client.post(
        "/v1/jobs/upload",
        data={"rights_confirmed": "true"},
        files={"file": ("original.mp4", video.read_bytes(), "video/mp4")},
    )
    assert result.status_code == 202, result.text
    return result.json()["id"]


def test_real_video_segments_approval_and_range(client, video, monkeypatch, tmp_path):
    monkeypatch.setattr(providers, "transcribe", lambda path: [segment()])
    job_id = upload(client, video)
    job = client.get("/v1/jobs/" + job_id).json()
    assert job["has_video"] and job["video_metadata"]["has_audio"]
    assert job["video_metadata"]["width"] == 320
    assert "media_path" not in job
    route = f"/v1/jobs/{job_id}/segments/0/video"
    assert client.get(route, headers={"Authorization": ""}).status_code == 401
    assert (
        client.get(
            route, headers={"Authorization": "Bearer bad", "Range": "bytes=0-99"}
        ).status_code
        == 401
    )
    full = client.get(route)
    assert full.status_code == 200
    assert full.headers["content-type"] == "video/mp4"
    assert full.headers["accept-ranges"] == "bytes"
    clip = tmp_path / "returned.mp4"
    clip.write_bytes(full.content)
    metadata = media.probe_video(clip)
    assert metadata["has_audio"] and 0.75 < metadata["duration"] < 1.25
    original = Path(main.MEDIA_ROOT / job_id / "original.mp4")
    assert original.read_bytes() == video.read_bytes()
    partial = client.get(route, headers={"Range": "bytes=0-99"})
    assert partial.status_code == 206 and partial.content == full.content[:100]
    assert partial.headers["content-range"].startswith("bytes 0-99/")
    assert (
        client.get(
            route, headers={"Range": f"bytes={len(full.content)+1}-"}
        ).status_code
        == 416
    )
    source = client.get(f"/v1/jobs/{job_id}/video")
    assert source.status_code == 200
    assert client.get("/v1/vocab").json() == []
    result = client.post(f"/v1/jobs/{job_id}/approve", json={"approved": True})
    assert result.status_code == 200, result.text
    word_id = result.json()["vocab_ids"][0]
    assert client.get("/v1/vocab").json()[0]["has_video"] is True
    sources = client.get(f"/v1/vocab/{word_id}/videos").json()
    assert len(sources) == 1 and sources[0]["video_url"] == route
    assert (
        sources[0]["arabic"] == segment()["arabic"]
        and sources[0]["english"] == segment()["english"]
    )
    with db.connect(main.DB_PATH) as c:
        assert (
            c.execute(
                "SELECT COUNT(*) FROM nawab_video_assets WHERE job_id=?", (job_id,)
            ).fetchone()[0]
            == 2
        )
    assert (
        client.put(
            f"/v1/jobs/{job_id}/segments", json={"segments": [segment()]}
        ).status_code
        == 409
    )


def test_video_boundaries_regenerate(client, video, monkeypatch, tmp_path):
    monkeypatch.setattr(providers, "transcribe", lambda p: [segment()])
    job_id = upload(client, video)
    route = f"/v1/jobs/{job_id}/segments/0/video"
    first = client.get(route)
    assert first.status_code == 200
    updated = dict(segment(), start=0.5, end=1.8)
    assert (
        client.put(
            f"/v1/jobs/{job_id}/segments", json={"segments": [updated]}
        ).status_code
        == 200
    )
    second = client.get(route)
    assert second.status_code == 200 and second.content != first.content
    clip = tmp_path / "new.mp4"
    clip.write_bytes(second.content)
    assert 1.05 < media.probe_video(clip)["duration"] < 1.55
    with db.connect(main.DB_PATH) as c:
        assert c.execute("SELECT COUNT(*) FROM nawab_video_assets").fetchone()[0] == 2


def test_audio_only_stays_audio(client, video, monkeypatch, tmp_path):
    audio, _ = media.prepare_audio(video, tmp_path)
    monkeypatch.setattr(providers, "transcribe", lambda p: [segment()])
    response = client.post(
        "/v1/jobs/upload",
        data={"rights_confirmed": "true"},
        files={"file": ("audio.mp3", audio.read_bytes(), "audio/mpeg")},
    )
    job_id = response.json()["id"]
    item = client.get("/v1/jobs/" + job_id).json()
    assert item["has_video"] is False and item["video_metadata"] is None
    assert client.get(f"/v1/jobs/{job_id}/video").status_code == 404
    assert client.get(f"/v1/jobs/{job_id}/segments/0/video").status_code == 404
    result = client.post(f"/v1/jobs/{job_id}/approve", json={"approved": True})
    assert result.status_code == 200
    word_id = result.json()["vocab_ids"][0]
    assert client.get(f"/v1/vocab/{word_id}/videos").json() == []
    assert (
        client.get("/v1/vocab").json()[0]["has_audio"]
        and not client.get("/v1/vocab").json()[0]["has_video"]
    )


def test_silent_video_manual_captions(client, video, monkeypatch, tmp_path):
    silent = tmp_path / "silent.mp4"
    subprocess.run(
        [
            "ffmpeg",
            "-nostdin",
            "-y",
            "-v",
            "error",
            "-i",
            str(video),
            "-c:v",
            "copy",
            "-an",
            str(silent),
        ],
        check=True,
    )
    monkeypatch.setattr(
        providers,
        "transcribe",
        lambda p: pytest.fail("Silent video must not invoke speech AI"),
    )
    job_id = upload(client, silent)
    item = client.get("/v1/jobs/" + job_id).json()
    assert item["has_video"] and not item["video_metadata"]["has_audio"]
    assert item["status"] == "needs_configuration" and "no audio track" in item["error"]
    assert (
        client.put(
            f"/v1/jobs/{job_id}/segments", json={"segments": [segment()]}
        ).status_code
        == 200
    )
    assert (
        client.post(f"/v1/jobs/{job_id}/approve", json={"approved": True}).status_code
        == 200
    )
    assert client.get(f"/v1/jobs/{job_id}/segments/0/video").status_code == 200


def test_video_migration_preserves_legacy_job_and_progress(tmp_path):
    path = tmp_path / "old.db"
    with sqlite3.connect(path) as c:
        c.execute(
            "CREATE TABLE vocab(id TEXT PRIMARY KEY,arabic TEXT,score INTEGER,notes TEXT,audio_mp3 BLOB)"
        )
        c.execute(
            "INSERT INTO vocab VALUES (?,?,?,?,?)", ("word", "هلا", 9, "note", b"audio")
        )
        c.execute(
            "CREATE TABLE nawab_jobs(id TEXT PRIMARY KEY,status TEXT,source_url TEXT,rights_confirmed INTEGER,media_path TEXT,audio_path TEXT,duration REAL,segments TEXT,error TEXT,created_at TEXT,updated_at TEXT)"
        )
        c.execute(
            "INSERT INTO nawab_jobs VALUES ('job','approved','https://www.tiktok.com/a',1,'original.mp4','audio.mp3',2,'[]','','now','now')"
        )
    db.init(path)
    db.init(path)
    with db.connect(path) as c:
        assert tuple(
            c.execute("SELECT score,notes,audio_mp3 FROM vocab").fetchone()
        ) == (9, "note", b"audio")
        item = c.execute("SELECT * FROM nawab_jobs").fetchone()
        assert (
            item["status"] == "approved"
            and item["media_path"] == "original.mp4"
            and item["has_video"] is None
        )
    assert len(list(tmp_path.glob("*.bak"))) == 1


def test_low_disk_rejects_without_deleting(client, monkeypatch):
    class Usage:
        free = 512 * 1024 * 1024

    monkeypatch.setattr(main.shutil, "disk_usage", lambda p: Usage())
    result = client.post(
        "/v1/jobs",
        json={"url": "https://www.tiktok.com/@u/video/123", "rights_confirmed": True},
    )
    assert (
        result.status_code == 507
        and "no originals were deleted" in result.json()["detail"]
    )
    assert client.get("/v1/jobs").json() == []


def test_gemini_model_required(client, monkeypatch):
    monkeypatch.setenv("NAWAB_ENABLE_AI", "true")
    monkeypatch.setenv("NAWAB_AI_PROVIDER", "gemini")
    monkeypatch.setenv("GEMINI_API_KEY", "fake")
    monkeypatch.delenv("GEMINI_TRANSCRIPTION_MODEL", raising=False)
    assert providers.provider_name() is None
    assert client.get("/health").json()["provider_configured"] is False
    with pytest.raises(providers.ConfigurationError):
        providers.transcribe("unused.mp3")


def test_http_health_only(client):
    assert client.get("http://remote.example/health").status_code == 200
    assert (
        client.post(
            "http://remote.example/auth/login", json={"password": "test-owner-password"}
        ).status_code
        == 400
    )


def test_video_disk_guard_keeps_original(client, video, monkeypatch):
    monkeypatch.setattr(providers, "transcribe", lambda p: [segment()])
    job_id = upload(client, video)

    class Usage:
        free = 512 * 1024 * 1024

    monkeypatch.setattr(main.shutil, "disk_usage", lambda p: Usage())
    response = client.get(f"/v1/jobs/{job_id}/segments/0/video")
    assert response.status_code == 507
    assert (
        main.MEDIA_ROOT / job_id / "original.mp4"
    ).read_bytes() == video.read_bytes()
    assert client.get("/v1/vocab").json() == []


def test_failed_video_render_cannot_approve(client, video, monkeypatch):
    monkeypatch.setattr(providers, "transcribe", lambda p: [segment()])
    job_id = upload(client, video)

    def fail(*args):
        raise ValueError("mock encode failure")

    monkeypatch.setattr(media, "clip_video", fail)
    response = client.post(f"/v1/jobs/{job_id}/approve", json={"approved": True})
    assert response.status_code == 422
    assert client.get("/v1/vocab").json() == []
    assert client.get("/v1/jobs/" + job_id).json()["status"] == "needs_review"
    assert not list((main.MEDIA_ROOT / job_id).glob("*.tmp.mp4"))


def test_legacy_approved_video_discovered_from_vocab(client, video, monkeypatch):
    monkeypatch.setattr(providers, "transcribe", lambda p: [segment()])
    job_id = upload(client, video)
    approved = client.post(f"/v1/jobs/{job_id}/approve", json={"approved": True})
    word_id = approved.json()["vocab_ids"][0]
    with db.connect(main.DB_PATH) as c:
        c.execute(
            "UPDATE nawab_jobs SET has_video=NULL,video_metadata=NULL WHERE id=?",
            (job_id,),
        )
        c.execute("UPDATE vocab SET score=7,notes=? WHERE id=?", ("unchanged", word_id))
    item = client.get("/v1/vocab").json()[0]
    assert (
        item["has_video"] is True
        and item["score"] == 7
        and item["notes"] == "unchanged"
    )
    assert (
        client.get(f"/v1/vocab/{word_id}/videos").json()[0]["english"]
        == segment()["english"]
    )
