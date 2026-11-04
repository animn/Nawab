"""Single-owner API. All learning content and media require a Bearer session."""

import base64
import csv
import hashlib
import hmac
import io
import json
import os
import re
import secrets
import time
import threading
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from difflib import SequenceMatcher
from pathlib import Path
from urllib.parse import urlparse
from uuid import uuid4

import requests
from fastapi import (
    BackgroundTasks,
    Depends,
    FastAPI,
    File,
    Form,
    HTTPException,
    UploadFile,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response, JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field, model_validator
from . import db, media, providers

DB_PATH = os.getenv("NAWAB_DB_PATH", os.getenv("NAWAB_DB", "learning_progress_v8.db"))
MEDIA_ROOT = Path(os.getenv("NAWAB_MEDIA_DIR", "nawab_media")).resolve()
_lock = threading.Lock()
_login_attempts = []
_processing_slots = threading.Semaphore(2)
_clip_slots = threading.Semaphore(2)


def now():
    return datetime.now(timezone.utc).isoformat()


@asynccontextmanager
async def lifespan(app):
    Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    MEDIA_ROOT.mkdir(parents=True, exist_ok=True)
    db.init(DB_PATH)
    with db.connect(DB_PATH) as c:
        c.execute(
            "UPDATE nawab_jobs SET status='failed',error='Processing interrupted by server restart. Retry is available.' WHERE status IN ('queued','processing')"
        )
        c.execute(
            "UPDATE nawab_sheet_outbox SET status='uncertain',error='Server restarted during dispatch; check the Sheet before any manual retry.' WHERE status='sending'"
        )
    yield


app = FastAPI(title="Nawab 2 API", version="2.0.0", lifespan=lifespan)


@app.middleware("http")
async def https_only(request, call_next):
    if (
        os.getenv("NAWAB_REQUIRE_HTTPS", "true").lower() == "true"
        and request.url.scheme != "https"
        and request.url.hostname not in {"localhost", "127.0.0.1", "::1", "testserver"}
    ):
        return JSONResponse(
            status_code=400,
            content={
                "detail": "HTTPS is required. Use TLS at your trusted reverse proxy."
            },
        )
    return await call_next(request)


class BodyLimitMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        limit = 32 * 1024 * 1024
        headers = dict(scope.get("headers", []))
        try:
            length = int(headers.get(b"content-length", b"0"))
        except ValueError:
            length = limit + 1
        if length > limit:
            return await JSONResponse(
                status_code=413, content={"detail": "Request body exceeds 32 MB."}
            )(scope, receive, send)
        count = 0

        async def limited_receive():
            nonlocal count
            message = await receive()
            count += len(message.get("body", b""))
            if count > limit:
                raise HTTPException(413, "Request body exceeds 32 MB.")
            return message

        return await self.app(scope, limited_receive, send)


app.add_middleware(BodyLimitMiddleware)

origins = [
    x.strip() for x in os.getenv("NAWAB_CORS_ORIGINS", "").split(",") if x.strip()
]
if origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_methods=["GET", "POST", "PUT"],
        allow_headers=["Authorization", "Content-Type"],
    )
security = HTTPBearer(auto_error=False)


def auth_configured():
    return (
        len(os.getenv("NAWAB_PASSWORD", "")) >= 12
        and len(os.getenv("NAWAB_TOKEN_SECRET", "")) >= 32
    )


def require_auth(credentials: HTTPAuthorizationCredentials = Depends(security)):
    if not auth_configured():
        raise HTTPException(
            503,
            "Authentication needs configuration: set a password of at least 12 characters and token secret of at least 32 characters.",
        )
    try:
        if credentials is None or credentials.scheme.lower() != "bearer":
            raise ValueError()
        payload, signature = credentials.credentials.split(".")
        expected = hmac.new(
            os.environ["NAWAB_TOKEN_SECRET"].encode(), payload.encode(), hashlib.sha256
        ).hexdigest()
        value = json.loads(
            base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4))
        )
        if (
            not hmac.compare_digest(signature, expected)
            or value["exp"] <= time.time()
            or value["sub"] != "owner"
        ):
            raise ValueError()
    except Exception:
        raise HTTPException(
            401,
            "Session expired or invalid. Please sign in.",
            headers={"WWW-Authenticate": "Bearer"},
        )


class Login(BaseModel):
    password: str = Field(max_length=1024)


@app.get("/health")
def health():
    return {
        "status": "ok",
        "auth_configured": auth_configured(),
        "provider_configured": bool(providers.provider_name()),
        "provider": providers.provider_name(),
    }


@app.post("/auth/login")
def login(data: Login):
    if not auth_configured():
        raise HTTPException(503, "Owner authentication is not configured.")
    with _lock:
        _login_attempts[:] = [t for t in _login_attempts if t > time.time() - 60]
        if len(_login_attempts) >= 10:
            raise HTTPException(429, "Too many login attempts. Wait one minute.")
        _login_attempts.append(time.time())
    if not hmac.compare_digest(
        data.password.encode(), os.environ["NAWAB_PASSWORD"].encode()
    ):
        raise HTTPException(401, "Invalid password.")
    payload = (
        base64.urlsafe_b64encode(
            json.dumps(
                {
                    "sub": "owner",
                    "exp": int(time.time()) + 43200,
                    "nonce": secrets.token_hex(12),
                }
            ).encode()
        )
        .decode()
        .rstrip("=")
    )
    signature = hmac.new(
        os.environ["NAWAB_TOKEN_SECRET"].encode(), payload.encode(), hashlib.sha256
    ).hexdigest()
    return {
        "access_token": payload + "." + signature,
        "token_type": "bearer",
        "expires_in": 43200,
    }


@app.get("/v1/vocab", dependencies=[Depends(require_auth)])
def vocab():
    with db.connect(DB_PATH) as c:
        rows = c.execute(
            "SELECT id,"
            + ",".join(n for n in db.COLUMNS if n != "audio_mp3")
            + ",audio_mp3 IS NOT NULL AS has_audio FROM vocab ORDER BY chapter,arabic"
        ).fetchall()
    return [dict(r) for r in rows]


def get_word(c, word_id):
    row = c.execute("SELECT * FROM vocab WHERE id=?", (word_id,)).fetchone()
    if not row:
        raise HTTPException(404, "Word not found.")
    return dict(row)


class Review(BaseModel):
    correct: bool


class Note(BaseModel):
    notes: str = Field(max_length=20000)


@app.post("/v1/vocab/{word_id}/review", dependencies=[Depends(require_auth)])
def review(word_id: str, data: Review):
    with db.connect(DB_PATH) as c:
        get_word(c, word_id)
        c.execute(
            "UPDATE vocab SET score=CASE WHEN ? THEN COALESCE(score,0)+1 ELSE 0 END WHERE id=?",
            (data.correct, word_id),
        )
        return {"score": get_word(c, word_id)["score"]}


@app.put("/v1/vocab/{word_id}/notes", dependencies=[Depends(require_auth)])
def notes(word_id: str, data: Note):
    with db.connect(DB_PATH) as c:
        get_word(c, word_id)
        c.execute("UPDATE vocab SET notes=? WHERE id=?", (data.notes, word_id))
    return {"notes": data.notes}


@app.get("/v1/vocab/{word_id}/audio", dependencies=[Depends(require_auth)])
def word_audio(word_id: str):
    with db.connect(DB_PATH) as c:
        row = get_word(c, word_id)
    if not row["audio_mp3"]:
        raise HTTPException(404, "No saved audio for this word.")
    return Response(row["audio_mp3"], media_type="audio/mpeg")


class JobInput(BaseModel):
    url: str = Field(max_length=2048)
    rights_confirmed: bool


class Segment(BaseModel):
    start: float = Field(ge=0, le=180, allow_inf_nan=False)
    end: float = Field(gt=0, le=180, allow_inf_nan=False)
    arabic: str = Field(min_length=1, max_length=4000)
    english: str = Field(default="", max_length=4000)
    transliteration: str = Field(default="", max_length=4000)
    explanation: str = Field(default="", max_length=8000)

    @model_validator(mode="after")
    def ordered(self):
        if self.end <= self.start or not self.arabic.strip():
            raise ValueError("Provide Arabic text and end > start.")
        return self


class Segments(BaseModel):
    segments: list[Segment] = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def chronological(self):
        if any(b.start < a.end for a, b in zip(self.segments, self.segments[1:])):
            raise ValueError("Segments must be chronological and must not overlap.")
        return self


class Approval(BaseModel):
    approved: bool
    write_to_sheet: bool = False


def job(c, job_id):
    row = c.execute("SELECT * FROM nawab_jobs WHERE id=?", (job_id,)).fetchone()
    if not row:
        raise HTTPException(404, "Job not found.")
    result = dict(row)
    result["segments"] = json.loads(result["segments"])
    return result


def public_job(row):
    return {k: v for k, v in row.items() if k not in ("media_path", "audio_path")}


def new_job(source_url, rights):
    if not rights:
        raise HTTPException(
            422,
            "Confirm that you own or have permission to download, process and store this media.",
        )
    job_id = uuid4().hex
    with db.connect(DB_PATH) as c:
        c.execute("BEGIN IMMEDIATE")
        if (
            c.execute(
                "SELECT COUNT(*) FROM nawab_jobs WHERE status IN ('queued','processing')"
            ).fetchone()[0]
            >= 25
        ):
            raise HTTPException(
                429, "Too many queued media jobs. Wait for processing to finish."
            )
        c.execute(
            "INSERT INTO nawab_jobs(id,status,source_url,rights_confirmed,created_at,updated_at) VALUES (?,'queued',?,1,?,?)",
            (job_id, source_url, now(), now()),
        )
    (MEDIA_ROOT / job_id).mkdir(parents=True, exist_ok=True)
    return job_id


def update_job(job_id, **values):
    values["updated_at"] = now()
    with db.connect(DB_PATH) as c:
        c.execute(
            "UPDATE nawab_jobs SET "
            + ",".join(k + "=?" for k in values)
            + " WHERE id=?",
            list(values.values()) + [job_id],
        )


def process_job(job_id):
    with _processing_slots:
        _process_job(job_id)


def _process_job(job_id):
    try:
        with db.connect(DB_PATH) as c:
            result = c.execute(
                "UPDATE nawab_jobs SET status='processing',error='' WHERE id=? AND status='queued'",
                (job_id,),
            )
            if not result.rowcount:
                return
            item = job(c, job_id)
        directory = MEDIA_ROOT / job_id
        original = (
            Path(item["media_path"])
            if item["media_path"]
            else media.download_tiktok(item["source_url"], directory)
        )
        update_job(job_id, media_path=str(original))
        audio, duration = media.prepare_audio(original, directory)
        update_job(job_id, audio_path=str(audio), duration=duration)
        segments = providers.transcribe(audio)
        validated = Segments(segments=segments)
        if any(s.end > duration + 0.1 for s in validated.segments):
            raise ValueError("Transcript timestamps exceed media duration.")
        update_job(
            job_id,
            status="needs_review",
            segments=json.dumps(
                [s.model_dump() for s in validated.segments], ensure_ascii=False
            ),
        )
    except providers.ConfigurationError:
        with db.connect(DB_PATH) as c:
            extracted = bool(job(c, job_id)["audio_path"])
        update_job(
            job_id,
            status="needs_configuration",
            error=(
                "AI transcription is not enabled/configured. Enter a timestamped transcript manually or ask the owner to configure a provider."
                if extracted
                else "Media extraction needs server configuration (ffmpeg/ffprobe or yt-dlp). Ask the operator to install the required tools."
            ),
        )
    except Exception as exc:
        # Do not expose provider bodies, credentials, server paths or internal URLs.
        update_job(
            job_id,
            status="failed",
            error="Media processing failed. Retry or upload an authorized MP4/M4A/MP3/WAV file. "
            + (
                "Invalid or unsupported media."
                if isinstance(exc, ValueError)
                else "Check server setup and provider availability."
            ),
        )


@app.post("/v1/jobs", dependencies=[Depends(require_auth)], status_code=202)
def create_job(data: JobInput, background: BackgroundTasks):
    try:
        media.validate_tiktok_url(data.url)
    except ValueError as exc:
        raise HTTPException(422, str(exc))
    job_id = new_job(data.url, data.rights_confirmed)
    background.add_task(process_job, job_id)
    with db.connect(DB_PATH) as c:
        return public_job(job(c, job_id))


async def save_upload(file, destination):
    total = 0
    try:
        with destination.open("wb") as out:
            while chunk := await file.read(1024 * 1024):
                total += len(chunk)
                if total > media.MAX_BYTES:
                    raise HTTPException(413, "Media limit is 30 MB.")
                out.write(chunk)
        if total == 0:
            raise HTTPException(422, "Empty media file.")
    except BaseException:
        destination.unlink(missing_ok=True)
        raise
    finally:
        await file.close()


@app.post("/v1/jobs/upload", dependencies=[Depends(require_auth)], status_code=202)
async def upload_job(
    background: BackgroundTasks,
    file: UploadFile = File(...),
    rights_confirmed: bool = Form(...),
    source_url: str = Form(""),
):
    if source_url:
        try:
            media.validate_tiktok_url(source_url)
        except ValueError as exc:
            raise HTTPException(422, str(exc))
    extension = Path(file.filename or "").suffix.lower()
    if extension not in {".mp4", ".mov", ".m4a", ".mp3", ".wav", ".webm"}:
        raise HTTPException(422, "Upload MP4, MOV, M4A, MP3, WAV or WebM media.")
    job_id = new_job(source_url, rights_confirmed)
    destination = MEDIA_ROOT / job_id / ("original" + extension)
    try:
        await save_upload(file, destination)
    except BaseException:
        update_job(
            job_id, status="failed", error="Upload failed or exceeded the 30 MB limit."
        )
        raise
    update_job(job_id, media_path=str(destination))
    background.add_task(process_job, job_id)
    with db.connect(DB_PATH) as c:
        return public_job(job(c, job_id))


@app.get("/v1/jobs", dependencies=[Depends(require_auth)])
def jobs():
    with db.connect(DB_PATH) as c:
        ids = [
            r[0]
            for r in c.execute(
                "SELECT id FROM nawab_jobs ORDER BY created_at DESC LIMIT 200"
            )
        ]
        return [public_job(job(c, i)) for i in ids]


@app.get("/v1/jobs/{job_id}", dependencies=[Depends(require_auth)])
def read_job(job_id: str):
    with db.connect(DB_PATH) as c:
        return public_job(job(c, job_id))


@app.post(
    "/v1/jobs/{job_id}/retry", dependencies=[Depends(require_auth)], status_code=202
)
def retry(job_id: str, background: BackgroundTasks):
    with db.connect(DB_PATH) as c:
        c.execute("BEGIN IMMEDIATE")
        item = job(c, job_id)
        if item["status"] not in ("failed", "needs_configuration"):
            raise HTTPException(409, "Only failed or unconfigured jobs can be retried.")
        if not item["media_path"] and not item["source_url"]:
            raise HTTPException(409, "Upload a new authorized file to continue.")
        c.execute(
            "UPDATE nawab_jobs SET status='queued',error='',updated_at=? WHERE id=?",
            (now(), job_id),
        )
    background.add_task(process_job, job_id)
    return {"id": job_id, "status": "queued"}


@app.put("/v1/jobs/{job_id}/segments", dependencies=[Depends(require_auth)])
def edit_segments(job_id: str, data: Segments):
    with db.connect(DB_PATH) as c:
        c.execute("BEGIN IMMEDIATE")
        item = job(c, job_id)
        if (
            item["status"] not in ("needs_review", "needs_configuration", "failed")
            or not item["duration"]
        ):
            raise HTTPException(
                409,
                "Wait for media extraction before editing. Approved lessons cannot be edited.",
            )
        if any(s.end > item["duration"] + 0.1 for s in data.segments):
            raise HTTPException(422, "Segment timestamps exceed media duration.")
        c.execute(
            "UPDATE nawab_jobs SET status='needs_review',segments=?,error='',updated_at=? WHERE id=?",
            (
                json.dumps([s.model_dump() for s in data.segments], ensure_ascii=False),
                now(),
                job_id,
            ),
        )
        return public_job(job(c, job_id))


def atomic_clip(source, start, end, output):
    with _clip_slots:
        if output.exists():
            return output
        temporary = output.with_name(output.stem + "-" + uuid4().hex + ".tmp.mp3")
        try:
            media.clip_audio(source, start, end, temporary)
            temporary.replace(output)
        finally:
            temporary.unlink(missing_ok=True)
    return output


@app.get(
    "/v1/jobs/{job_id}/segments/{index}/audio", dependencies=[Depends(require_auth)]
)
def segment_audio(job_id: str, index: int):
    with db.connect(DB_PATH) as c:
        item = job(c, job_id)
    if index < 0 or index >= len(item["segments"]) or not item["audio_path"]:
        raise HTTPException(404, "Segment audio not available.")
    seg = item["segments"][index]
    output = (
        MEDIA_ROOT
        / job_id
        / f"segment-{index}-{hashlib.sha256(json.dumps(seg).encode()).hexdigest()[:12]}.mp3"
    )
    try:
        if not output.exists():
            atomic_clip(Path(item["audio_path"]), seg["start"], seg["end"], output)
    except Exception:
        raise HTTPException(422, "Could not extract segment audio.")
    return FileResponse(output, media_type="audio/mpeg")


SHEET_MAP = {
    "chapter": "chapter",
    "arabicscript": "arabic",
    "pronunciation": "pronunciation",
    "englishmeaning": "english",
    "explanation": "explanation",
    "letterwisepronounciation": "letter_pronunc",
    "letterwiseenglish": "letter_eng",
    "ttstext": "ttstext",
}
DEFAULT_SHEET = "https://docs.google.com/spreadsheets/d/1DQ_74TZtMpbinusdnMOU2441hEFa7RRnaqeMx8qrBg0/export?format=csv"


def sheet_url_ok(url):
    parsed = urlparse(url)
    if (
        parsed.scheme != "https"
        or parsed.username
        or parsed.password
        or parsed.port not in (None, 443)
        or not parsed.hostname
        or not (
            parsed.hostname
            in {"docs.google.com", "script.google.com", "script.googleusercontent.com"}
            or parsed.hostname.endswith(".googleusercontent.com")
        )
    ):
        raise ValueError("Only configured HTTPS Google Sheets endpoints are allowed.")
    return url


def fetch_sheet_csv(url):
    for _ in range(5):
        sheet_url_ok(url)
        with requests.get(
            url, timeout=(10, 30), allow_redirects=False, stream=True
        ) as response:
            if response.status_code in (301, 302, 303, 307, 308):
                from urllib.parse import urljoin

                url = urljoin(url, response.headers.get("Location", ""))
                continue
            response.raise_for_status()
            content = bytearray()
            for chunk in response.iter_content(65536):
                content.extend(chunk)
                if len(content) > 5 * 1024 * 1024:
                    raise ValueError("Sheet exceeds 5 MB import limit.")
            return content.decode("utf-8-sig")
    raise ValueError("Too many Sheet redirects.")


@app.post("/v1/sheets/import", dependencies=[Depends(require_auth)])
def import_sheet():
    try:
        text = fetch_sheet_csv(os.getenv("SHEET_URL", DEFAULT_SHEET))
        reader = csv.DictReader(io.StringIO(text))
        if not reader.fieldnames or "arabicscript" not in [
            re.sub("[^a-z0-9]", "", k.lower()) for k in reader.fieldnames
        ]:
            raise ValueError("Sheet needs an Arabic Script column.")
        count = 0
        with db.connect(DB_PATH) as c:
            for row in reader:
                clean = {
                    re.sub("[^a-z0-9]", "", k.lower()): (v or "").strip()
                    for k, v in row.items()
                    if k
                }
                if not clean.get("arabicscript"):
                    continue
                if any(len(v) > 20000 for v in clean.values()) or count >= 20000:
                    raise ValueError("Sheet import limits exceeded.")
                fields = {dest: clean.get(src, "") for src, dest in SHEET_MAP.items()}
                fields["letter_pronunc"] = clean.get(
                    "letterwisepronounciation", clean.get("letterwisepronunciation", "")
                )
                word_id = db.upsert(c, fields)
                c.execute(
                    "INSERT OR IGNORE INTO nawab_sheet_known(vocab_id) VALUES (?)",
                    (word_id,),
                )
                count += 1
        return {"imported": count, "progress_preserved": True}
    except Exception:
        raise HTTPException(
            422,
            "Could not import the configured public Google Sheet. Check sharing, column names and server configuration.",
        )


def formula_safe(value):
    value = str(value or "")
    return (
        "'" + value
        if value.lstrip().startswith(("=", "+", "-", "@", "\t", "\r"))
        else value
    )


def dispatch_sheet(word_id):
    # Reserve once before external I/O. A timeout is uncertain, NEVER blindly retried.
    with db.connect(DB_PATH) as c:
        c.execute("BEGIN IMMEDIATE")
        row = c.execute(
            "SELECT * FROM nawab_sheet_outbox WHERE vocab_id=?", (word_id,)
        ).fetchone()
        if not row or row["status"] != "pending":
            return
        c.execute(
            "UPDATE nawab_sheet_outbox SET status='sending' WHERE vocab_id=?",
            (word_id,),
        )
        payload = json.loads(row["payload"])
        operation_id = row["operation_id"]
    status, error = (
        "uncertain",
        "The request may have reached the Sheet. Check the Sheet before any manual retry.",
    )
    try:
        url = sheet_url_ok(os.environ["SHEET_APPEND_WEBHOOK_URL"])
        # Apps Script redirects POST results to a GET page; never replay a POST on redirects.
        response = requests.post(
            url,
            json={
                "secret": os.environ["SHEET_APPEND_SECRET"],
                "entry": payload,
                "operation_id": operation_id,
            },
            timeout=(10, 30),
            allow_redirects=False,
            headers={"Idempotency-Key": operation_id},
        )
        if response.status_code in (301, 302, 303):
            redirect = response.headers.get("Location", "")
            body = json.loads(fetch_sheet_csv(redirect))
        else:
            response.raise_for_status()
            body = response.json()
        if body.get("success") is True or body.get("ok") is True:
            status, error = "sent", ""
        elif body.get("success") is False or body.get("ok") is False:
            status, error = (
                "failed",
                "Sheet webhook rejected the entry; inspect its configuration.",
            )
    except Exception:
        pass
    with db.connect(DB_PATH) as c:
        c.execute(
            "UPDATE nawab_sheet_outbox SET status=?,error=? WHERE vocab_id=?",
            (status, error, word_id),
        )


@app.post("/v1/jobs/{job_id}/approve", dependencies=[Depends(require_auth)])
def approve_job(job_id: str, data: Approval):
    if not data.approved:
        raise HTTPException(
            422, "Explicit approval is required before saving lesson entries."
        )
    if data.write_to_sheet and not (
        os.getenv("SHEET_APPEND_WEBHOOK_URL") and os.getenv("SHEET_APPEND_SECRET")
    ):
        raise HTTPException(
            503, "Sheet write-back is not configured. You can approve locally instead."
        )
    word_ids = []
    # Prepare immutable audio clips outside SQLite's write transaction.
    with db.connect(DB_PATH) as c:
        snapshot = job(c, job_id)
        if (
            snapshot["status"] not in ("needs_review", "approved")
            or not snapshot["segments"]
        ):
            raise HTTPException(
                409, "Review a timestamped transcript before approving."
            )
        audio_needed = {}
        for index, seg in enumerate(snapshot["segments"]):
            word_id = hashlib.md5(seg["arabic"].strip().encode()).hexdigest()
            existing = c.execute(
                "SELECT audio_mp3 FROM vocab WHERE id=?", (word_id,)
            ).fetchone()
            if snapshot["audio_path"] and (not existing or not existing[0]):
                audio_needed[word_id] = (index, seg)
    prepared = {}
    for word_id, (index, seg) in audio_needed.items():
        digest = hashlib.sha256(json.dumps(seg).encode()).hexdigest()[:12]
        target = MEDIA_ROOT / job_id / f"approved-{index}-{digest}.mp3"
        try:
            atomic_clip(Path(snapshot["audio_path"]), seg["start"], seg["end"], target)
            prepared[word_id] = target.read_bytes()
        except Exception:
            raise HTTPException(
                422,
                "Could not preserve original segment audio. Nothing has been approved; check ffmpeg and retry.",
            )
    with db.connect(DB_PATH) as c:
        c.execute("BEGIN IMMEDIATE")
        item = job(c, job_id)
        if (
            item["status"] not in ("needs_review", "approved")
            or item["segments"] != snapshot["segments"]
        ):
            raise HTTPException(409, "Lesson changed during approval. Review it again.")
        for index, seg in enumerate(item["segments"]):
            fields = {
                "arabic": seg["arabic"],
                "pronunciation": seg["transliteration"],
                "english": seg["english"],
                "explanation": seg["explanation"],
                "chapter": "TikTok lesson",
                "ttstext": seg["arabic"],
            }
            word_id = hashlib.md5(seg["arabic"].strip().encode()).hexdigest()
            # Approval is not permission to overwrite pre-existing vocabulary metadata.
            if not c.execute("SELECT 1 FROM vocab WHERE id=?", (word_id,)).fetchone():
                db.upsert(c, fields)
            word_ids.append(word_id)
            if word_id in prepared:
                c.execute(
                    "UPDATE vocab SET audio_mp3=?,audio_provider='original_source_audio' WHERE id=? AND audio_mp3 IS NULL",
                    (prepared[word_id], word_id),
                )
            c.execute(
                "INSERT OR IGNORE INTO nawab_sources(job_id,segment_index,vocab_id,start,end) VALUES (?,?,?,?,?)",
                (job_id, index, word_id, seg["start"], seg["end"]),
            )
            if data.write_to_sheet:
                payload = {
                    src: formula_safe(fields.get(dest, ""))
                    for src, dest in SHEET_MAP.items()
                }
                status = (
                    "already_present"
                    if c.execute(
                        "SELECT 1 FROM nawab_sheet_known WHERE vocab_id=?", (word_id,)
                    ).fetchone()
                    else "pending"
                )
                c.execute(
                    "INSERT OR IGNORE INTO nawab_sheet_outbox(vocab_id,operation_id,status,payload) VALUES (?,?,?,?)",
                    (
                        word_id,
                        "nawab-" + word_id,
                        status,
                        json.dumps(payload, ensure_ascii=False),
                    ),
                )
        c.execute(
            "UPDATE nawab_jobs SET status='approved',updated_at=? WHERE id=?",
            (now(), job_id),
        )
    if data.write_to_sheet:
        for word_id in set(word_ids):
            dispatch_sheet(word_id)
    with db.connect(DB_PATH) as c:
        statuses = [
            dict(r)
            for r in c.execute(
                "SELECT vocab_id,status,error FROM nawab_sheet_outbox WHERE vocab_id IN ("
                + ",".join("?" for _ in word_ids)
                + ")",
                word_ids,
            )
        ]
    return {
        "id": job_id,
        "status": "approved",
        "vocab_ids": word_ids,
        "sheet_results": statuses,
    }


@app.get("/v1/sheets/status", dependencies=[Depends(require_auth)])
def sheet_status():
    with db.connect(DB_PATH) as c:
        return {
            "configured": bool(
                os.getenv("SHEET_APPEND_WEBHOOK_URL")
                and os.getenv("SHEET_APPEND_SECRET")
            ),
            "entries": [
                dict(r)
                for r in c.execute(
                    "SELECT vocab_id,operation_id,status,error FROM nawab_sheet_outbox"
                )
            ],
        }


class Practice(BaseModel):
    transcript: str = Field(min_length=1, max_length=4000)


def measure(word_id, transcript, recording_path=None):
    with db.connect(DB_PATH) as c:
        word = get_word(c, word_id)
        normalize = lambda s: re.sub(r"[\u064b-\u065f\u0670\W_]+", "", s.lower())
        similarity = round(
            100
            * SequenceMatcher(
                None, normalize(word["arabic"]), normalize(transcript)
            ).ratio(),
            1,
        )
        practice_id = uuid4().hex
        label = "text_similarity_not_pronunciation_or_fluency"
        c.execute(
            "INSERT INTO nawab_practice VALUES (?,?,?,?,?,?,?,?)",
            (
                practice_id,
                word_id,
                str(recording_path) if recording_path else None,
                transcript,
                word["arabic"],
                similarity,
                label,
                now(),
            ),
        )
    return {
        "id": practice_id,
        "transcript": transcript,
        "reference_text": word["arabic"],
        "similarity": similarity,
        "measurement": label,
        "notice": "Transcript text similarity only. This does not measure pronunciation, accent, fluency or acoustic accuracy.",
    }


@app.post("/v1/vocab/{word_id}/practice", dependencies=[Depends(require_auth)])
def practice(word_id: str, data: Practice):
    return measure(word_id, data.transcript)


@app.post(
    "/v1/vocab/{word_id}/practice/recording", dependencies=[Depends(require_auth)]
)
async def practice_recording(
    word_id: str,
    file: UploadFile = File(...),
    transcript: str = Form(...),
    rights_confirmed: bool = Form(...),
):
    if not rights_confirmed:
        raise HTTPException(422, "Confirm permission to store this recording.")
    if not 0 < len(transcript.strip()) <= 4000:
        raise HTTPException(
            422, "Enter the actual spoken transcript (1–4000 characters)."
        )
    with db.connect(DB_PATH) as c:
        get_word(c, word_id)
    directory = MEDIA_ROOT / "practice" / uuid4().hex
    directory.mkdir(parents=True)
    extension = Path(file.filename or "").suffix.lower()
    if extension not in {".m4a", ".mp3", ".wav", ".webm", ".mp4"}:
        raise HTTPException(422, "Unsupported recording format.")
    original = directory / ("recording" + extension)
    await save_upload(file, original)
    try:
        media.prepare_audio(original, directory)
    except Exception:
        original.unlink(missing_ok=True)
        raise HTTPException(422, "Invalid recording or duration over 180 seconds.")
    return measure(word_id, transcript, original)


@app.get("/v1/practice/{practice_id}/audio", dependencies=[Depends(require_auth)])
def practice_audio(practice_id: str):
    with db.connect(DB_PATH) as c:
        row = c.execute(
            "SELECT recording_path FROM nawab_practice WHERE id=?", (practice_id,)
        ).fetchone()
    if not row or not row[0] or not Path(row[0]).is_file():
        raise HTTPException(404, "Recording not found.")
    return FileResponse(row[0])


@app.get("/v1/jobs/{job_id}/audio", dependencies=[Depends(require_auth)])
def source_audio(job_id: str):
    """Authenticated original track for reviewing or manually transcribing a lesson."""
    with db.connect(DB_PATH) as c:
        item = job(c, job_id)
    if not item["audio_path"] or not Path(item["audio_path"]).is_file():
        raise HTTPException(404, "Original audio is not available yet.")
    return FileResponse(item["audio_path"], media_type="audio/mpeg")
