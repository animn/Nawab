"""Bounded media ingestion. All remote connections pin a validated public IP.

TikTok can block automated access. Never bypass its login, CAPTCHA or private
content restrictions: callers should offer the authorized local-upload path.
"""

from __future__ import annotations
import http.client
import importlib.util
import io
import ipaddress
import json
import math
from pathlib import Path
import shutil
import socket
import ssl
import subprocess
import sys
import time
from urllib.parse import urljoin, urlsplit

MAX_BYTES = 30 * 1024 * 1024
MAX_DURATION = 180
# Never permit HLS/concat/playlist demuxers that can read secondary local files.
MEDIA_FORMATS = "mov,mp4,m4a,3gp,3g2,mj2,mp3,wav,ogg,flac,aac,matroska,webm"
TIKTOK_HOSTS = {"tiktok.com", "www.tiktok.com", "vm.tiktok.com", "vt.tiktok.com"}


class ConfigurationError(ValueError):
    """A server component is not configured; no content has been invented."""


def validate_tiktok_url(url: str) -> str:
    try:
        p = urlsplit(url)
        if (
            p.scheme != "https"
            or p.hostname not in TIKTOK_HOSTS
            or p.port not in (None, 443)
        ):
            raise ValueError()
        if p.username or p.password or p.fragment or not p.path or len(url) > 2048:
            raise ValueError()
        if any(ord(c) < 33 for c in url) or "\\" in url:
            raise ValueError()
    except (ValueError, TypeError):
        raise ValueError(
            "Use an HTTPS TikTok video link, without credentials or fragments."
        ) from None
    return url


def public_addresses(host: str) -> list[str]:
    try:
        addresses = sorted(
            {
                row[4][0]
                for row in socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
            }
        )
    except OSError:
        raise ValueError("The remote host could not be resolved.") from None
    if not addresses or any(not ipaddress.ip_address(ip).is_global for ip in addresses):
        raise ValueError("Non-public network destinations are not allowed.")
    return addresses


class _PinnedHTTPS(http.client.HTTPSConnection):
    def __init__(self, host: str, address: str, timeout: float):
        super().__init__(
            host, port=443, timeout=timeout, context=ssl.create_default_context()
        )
        self.address = address

    def connect(self):
        # No second DNS lookup: prevents DNS-rebinding between validation and use.
        sock = socket.create_connection((self.address, 443), self.timeout)
        try:
            self.sock = self._context.wrap_socket(sock, server_hostname=self.host)
        except BaseException:
            sock.close()
            raise


def safe_fetch(
    url: str,
    *,
    limit: int = MAX_BYTES,
    headers: dict | None = None,
    timeout: float = 45,
    tiktok_only: bool = False,
) -> tuple[bytes, str, dict, int]:
    """HTTPS GET, no proxies/cookies, public pinned DNS, bounded size/time/redirects."""
    deadline = time.monotonic() + timeout
    for _ in range(6):
        p = urlsplit(url)
        if (
            p.scheme != "https"
            or not p.hostname
            or p.port not in (None, 443)
            or p.username
            or p.password
            or "\\" in url
            or any(ord(c) < 33 for c in url)
        ):
            raise ValueError("Unsafe remote URL.")
        if tiktok_only and p.hostname not in TIKTOK_HOSTS:
            raise ValueError("TikTok redirects must remain on an approved TikTok host.")
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise ValueError("Remote transfer timed out.")
        addresses = public_addresses(p.hostname)
        conn = _PinnedHTTPS(p.hostname, addresses[0], min(10, remaining))
        allowed = {"user-agent", "accept", "accept-language", "referer", "range"}
        request_headers = {
            k: v for k, v in (headers or {}).items() if k.lower() in allowed
        }
        request_headers["Accept-Encoding"] = "identity"
        try:
            conn.request(
                "GET",
                p.path + ("?" + p.query if p.query else ""),
                headers=request_headers,
            )
            response = conn.getresponse()
            result_headers = dict(response.getheaders())
            if response.status in (301, 302, 303, 307, 308):
                location = response.getheader("Location")
                if not location:
                    raise ValueError("Remote redirect has no destination.")
                url = urljoin(url, location)
                continue
            if not 200 <= response.status < 300:
                raise ValueError(
                    "Remote media is unavailable; upload a file you have permission to use."
                )
            length = response.getheader("Content-Length")
            if length and int(length) > limit:
                raise ValueError("Remote media exceeds the size limit.")
            output = bytearray()
            while True:
                if time.monotonic() >= deadline:
                    raise ValueError("Remote transfer timed out.")
                chunk = response.read(min(65536, limit - len(output) + 1))
                if not chunk:
                    break
                output.extend(chunk)
                if len(output) > limit:
                    raise ValueError("Remote media exceeds the size limit.")
            return bytes(output), url, result_headers, response.status
        finally:
            conn.close()
    raise ValueError("Too many remote redirects.")


def _extract(url: str, output: Path):
    import yt_dlp
    from yt_dlp.networking.common import Response
    from yt_dlp.extractor.tiktok import TikTokIE

    class RestrictedYDL(yt_dlp.YoutubeDL):
        def urlopen(self, request):
            target = (
                request
                if isinstance(request, str)
                else getattr(request, "url", None) or request.full_url
            )
            if getattr(request, "data", None):
                raise ValueError(
                    "Remote POST requests are not permitted for extraction."
                )
            body, final_url, headers, status = safe_fetch(
                target,
                limit=4 * 1024 * 1024,
                headers=getattr(request, "headers", {}),
                timeout=20,
            )
            return Response(io.BytesIO(body), final_url, headers, status=status)

    # Restrict both initial and short-link redirects before invoking any extractor.
    _, resolved, _, _ = safe_fetch(
        validate_tiktok_url(url), limit=4 * 1024 * 1024, tiktok_only=True, timeout=20
    )
    options = {
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "cachedir": False,
        "skip_download": True,
        "socket_timeout": 10,
        "retries": 0,
        "extractor_retries": 0,
        "enable_file_urls": False,
        "proxy": "",
        "allowed_extractors": ["TikTok", "TikTokVM"],
        "external_downloader": None,
    }

    # Call only the known TikTok extractor, never plugin or generic extractors.
    # Recent yt-dlp versions solve TikTok challenge cookies automatically; disallow
    # that behavior and require the authorized-upload fallback instead.
    class PublicTikTokIE(TikTokIE):
        def _solve_challenge_and_set_cookies(self, *args, **kwargs):
            raise ValueError("TikTok requires a challenge. Use an authorized upload.")

    with RestrictedYDL(options, auto_init=False) as ydl:
        if not PublicTikTokIE.suitable(resolved):
            raise ValueError("The link did not resolve to a supported TikTok video.")
        info = PublicTikTokIE(ydl).extract(resolved)
    if (
        not info
        or info.get("_type") in ("playlist", "url", "url_transparent")
        or info.get("is_live")
    ):
        raise ValueError("Only a single public recorded video is supported.")
    duration = float(info.get("duration") or 0)
    if not math.isfinite(duration) or duration <= 0 or duration > MAX_DURATION:
        raise ValueError("Video must be between 0 and 180 seconds.")
    candidates = [
        f
        for f in info.get("formats", [])
        if f.get("url", "").startswith("https://")
        and f.get("ext") == "mp4"
        and f.get("protocol", "https") in ("https", "http")
        and f.get("acodec") != "none"
        and not f.get("fragments")
        and (f.get("filesize") or 0) <= MAX_BYTES
    ]
    if not candidates:
        raise ValueError(
            "No safely downloadable video found. Use an authorized upload."
        )
    chosen = sorted(
        candidates, key=lambda f: (f.get("height") or 9999, f.get("tbr") or 9999)
    )[0]
    data, _, _, _ = safe_fetch(
        chosen["url"],
        headers=chosen.get("http_headers") or info.get("http_headers", {}),
        timeout=35,
    )
    output.write_bytes(data)


def download_tiktok(url: str, directory: str | Path) -> Path:
    validate_tiktok_url(url)
    if importlib.util.find_spec("yt_dlp") is None:
        raise ConfigurationError(
            "TikTok extraction needs yt-dlp on the server. Upload your authorized file instead."
        )
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    output = directory / "original.mp4"
    try:
        result = subprocess.run(
            [sys.executable, "-m", "api.media", "_extract", url, str(output)],
            timeout=90,
            capture_output=True,
            check=False,
        )
        if (
            result.returncode
            or not output.is_file()
            or output.stat().st_size > MAX_BYTES
        ):
            raise ValueError(
                "TikTok extraction failed or access is restricted. Upload a file you have permission to use."
            )
    except subprocess.TimeoutExpired:
        output.unlink(missing_ok=True)
        raise ValueError(
            "TikTok extraction timed out. Try an authorized upload."
        ) from None
    except BaseException:
        output.unlink(missing_ok=True)
        raise
    return output


def _binary(name):
    result = shutil.which(name)
    if not result:
        raise ConfigurationError(f"The server needs {name} for audio processing.")
    return result


def _run(command, timeout=45):
    try:
        return subprocess.run(
            command, timeout=timeout, check=True, capture_output=True
        ).stdout
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
        raise ValueError(
            "Media could not be processed safely. Check its format and duration."
        ) from None


def prepare_audio(path: str | Path, directory: str | Path) -> tuple[Path, float]:
    path = Path(path).resolve()
    if (
        not path.is_file()
        or path.stat().st_size > MAX_BYTES
        or path.stat().st_size == 0
    ):
        raise ValueError("Media must be nonempty and no larger than 30 MB.")
    raw = _run(
        [
            _binary("ffprobe"),
            "-v",
            "error",
            "-protocol_whitelist",
            "file,pipe",
            "-format_whitelist",
            MEDIA_FORMATS,
            "-show_entries",
            "format=duration",
            "-of",
            "json",
            str(path),
        ],
        timeout=15,
    )
    try:
        duration = float(json.loads(raw)["format"]["duration"])
    except (ValueError, KeyError, TypeError):
        raise ValueError("The media duration could not be verified.") from None
    if not math.isfinite(duration) or not 0 < duration <= MAX_DURATION:
        raise ValueError("Media must be no longer than 180 seconds.")
    output = Path(directory).resolve() / "audio.mp3"
    output.parent.mkdir(parents=True, exist_ok=True)
    _run(
        [
            _binary("ffmpeg"),
            "-nostdin",
            "-y",
            "-v",
            "error",
            "-protocol_whitelist",
            "file,pipe",
            "-format_whitelist",
            MEDIA_FORMATS,
            "-i",
            str(path),
            "-map",
            "0:a:0",
            "-vn",
            "-t",
            str(MAX_DURATION),
            "-ac",
            "1",
            "-ar",
            "16000",
            "-b:a",
            "64k",
            "-fs",
            str(MAX_BYTES),
            str(output),
        ]
    )
    return output, duration


def clip_audio(path: str | Path, start: float, end: float, output: str | Path) -> Path:
    if (
        not all(math.isfinite(x) for x in (start, end))
        or not 0 <= start < end <= MAX_DURATION
    ):
        raise ValueError("Invalid audio segment times.")
    output = Path(output)
    _run(
        [
            _binary("ffmpeg"),
            "-nostdin",
            "-y",
            "-v",
            "error",
            "-protocol_whitelist",
            "file,pipe",
            "-format_whitelist",
            MEDIA_FORMATS,
            "-ss",
            str(start),
            "-i",
            str(Path(path).resolve()),
            "-t",
            str(end - start),
            "-map",
            "0:a:0",
            "-vn",
            "-ac",
            "1",
            "-ar",
            "16000",
            "-b:a",
            "64k",
            str(output),
        ]
    )
    return output


if __name__ == "__main__":
    try:
        if len(sys.argv) != 4 or sys.argv[1] != "_extract":
            raise ValueError("Invalid invocation.")
        _extract(sys.argv[2], Path(sys.argv[3]))
    except Exception:
        sys.exit(1)
