import hashlib
import sqlite3
import pytest
from fastapi.testclient import TestClient
from api import db, main, media, providers


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "DB_PATH", str(tmp_path / "legacy.db"))
    monkeypatch.setattr(main, "MEDIA_ROOT", tmp_path / "media")
    monkeypatch.setenv("NAWAB_PASSWORD", "test-owner-password")
    monkeypatch.setenv("NAWAB_TOKEN_SECRET", "x" * 40)
    monkeypatch.delenv("NAWAB_ENABLE_AI", raising=False)
    main._login_attempts.clear()
    with TestClient(main.app) as c:
        c.headers["Authorization"] = (
            "Bearer "
            + c.post("/auth/login", json={"password": "test-owner-password"}).json()[
                "access_token"
            ]
        )
        yield c


def segment():
    return dict(
        start=0,
        end=1,
        arabic="شلونك",
        english="How are you?",
        transliteration="shlonak",
        explanation="Greeting",
    )


def fake_media(monkeypatch):
    def download(url, d):
        p = d / "original.mp4"
        p.write_bytes(b"media")
        return p

    def prepare(p, d):
        p = d / "audio.mp3"
        p.write_bytes(b"audio")
        return p, 5

    monkeypatch.setattr(media, "download_tiktok", download)
    monkeypatch.setattr(media, "prepare_audio", prepare)
    monkeypatch.setattr(media, "probe_video", lambda p: None)
    monkeypatch.setattr(
        media, "clip_audio", lambda p, start, end, out: out.write_bytes(b"clip")
    )


def create(client):
    return client.post(
        "/v1/jobs",
        json={
            "url": "https://www.tiktok.com/@user/video/123",
            "rights_confirmed": True,
        },
    ).json()["id"]


def test_auth(client, monkeypatch):
    assert client.get("/v1/vocab", headers={"Authorization": ""}).status_code == 401
    assert (
        client.get("/v1/vocab", headers={"Authorization": "Bearer bogus"}).status_code
        == 401
    )
    monkeypatch.delenv("NAWAB_PASSWORD")
    assert client.get("/v1/vocab").status_code == 503
    assert client.post("/auth/login", json={"password": "x"}).status_code == 503


def test_https(client):
    assert client.get("http://remote.example/v1/vocab").status_code == 400


def test_migration(tmp_path):
    p = tmp_path / "legacy.db"
    c = sqlite3.connect(p)
    c.execute(
        "CREATE TABLE vocab(id TEXT PRIMARY KEY,arabic TEXT,score INTEGER,notes TEXT,audio_mp3 BLOB,custom_column TEXT)"
    )
    c.execute(
        "INSERT INTO vocab VALUES (?,?,?,?,?,?)",
        ("abc", "هلا", 7, "notes", b"audio", "extra"),
    )
    c.commit()
    c.close()
    db.init(str(p))
    db.init(str(p))
    with db.connect(p) as c:
        r = c.execute("SELECT * FROM vocab").fetchone()
        assert (r["score"], r["notes"], r["audio_mp3"], r["custom_column"]) == (
            7,
            "notes",
            b"audio",
            "extra",
        )
    assert len(list(tmp_path.glob("*.bak"))) == 1


@pytest.mark.parametrize(
    "url",
    [
        "http://www.tiktok.com/a",
        "https://tiktok.com.evil.org/a",
        "https://user:pass@tiktok.com/a",
        "https://127.0.0.1/a",
        "file:///tmp/test",
        "https://www.tiktok.com:8443/a",
    ],
)
def test_url(client, url):
    assert (
        client.post("/v1/jobs", json={"url": url, "rights_confirmed": True}).status_code
        == 422
    )


def test_rights(client):
    assert (
        client.post(
            "/v1/jobs",
            json={
                "url": "https://www.tiktok.com/@u/video/123",
                "rights_confirmed": False,
            },
        ).status_code
        == 422
    )


def test_manual_approval(client, monkeypatch):
    fake_media(monkeypatch)
    jid = create(client)
    base = "/v1/jobs/" + jid
    assert client.get(base).json()["status"] == "needs_configuration"
    assert client.get("/v1/vocab").json() == []
    assert client.post(base + "/approve", json={"approved": True}).status_code == 409
    assert (
        client.put(
            base + "/segments", json={"segments": [dict(segment(), end=8)]}
        ).status_code
        == 422
    )
    assert (
        client.put(base + "/segments", json={"segments": [segment()]}).status_code
        == 200
    )
    assert client.post(base + "/approve", json={"approved": False}).status_code == 422
    r = client.post(base + "/approve", json={"approved": True})
    assert r.status_code == 200
    wid = r.json()["vocab_ids"][0]
    assert wid == hashlib.md5("شلونك".encode()).hexdigest()
    client.post("/v1/vocab/" + wid + "/review", json={"correct": True})
    client.put("/v1/vocab/" + wid + "/notes", json={"notes": "keep"})
    assert client.post(base + "/approve", json={"approved": True}).status_code == 200
    r = client.get("/v1/vocab").json()[0]
    assert r["score"] == 1 and r["notes"] == "keep"
    assert (
        client.put(base + "/segments", json={"segments": [segment()]}).status_code
        == 409
    )


def test_retry(client, monkeypatch):
    def fail(*args):
        raise ValueError("secret")

    monkeypatch.setattr(media, "download_tiktok", fail)
    jid = create(client)
    base = "/v1/jobs/" + jid
    r = client.get(base).json()
    assert r["status"] == "failed" and "secret" not in r["error"]
    fake_media(monkeypatch)
    monkeypatch.setattr(providers, "transcribe", lambda p: [segment()])
    assert client.post(base + "/retry").status_code == 202
    assert client.get(base).json()["status"] == "needs_review"
    assert client.post(base + "/retry").status_code == 409


def test_sheet_import(client, monkeypatch):
    monkeypatch.setattr(
        main,
        "fetch_sheet_csv",
        lambda url: "Chapter,Arabic Script,English Meaning\nGreetings,هلا,Hello\nGreetings,هلا,Hello again\n",
    )
    assert client.post("/v1/sheets/import").json()["imported"] == 2
    wid = hashlib.md5("هلا".encode()).hexdigest()
    with db.connect(main.DB_PATH) as c:
        c.execute(
            "UPDATE vocab SET score=5,notes=?,audio_mp3=? WHERE id=?",
            ("keep", b"audio", wid),
        )
    client.post("/v1/sheets/import")
    r = client.get("/v1/vocab").json()
    assert len(r) == 1 and r[0]["score"] == 5 and r[0]["notes"] == "keep"
    assert client.get("/v1/vocab/" + wid + "/audio").content == b"audio"


@pytest.mark.parametrize("fail", [False, True])
def test_sheet_idempotency(client, monkeypatch, fail):
    fake_media(monkeypatch)
    monkeypatch.setattr(
        providers,
        "transcribe",
        lambda p: [dict(segment(), english='=IMPORTXML("evil")')],
    )
    monkeypatch.setenv(
        "SHEET_APPEND_WEBHOOK_URL", "https://script.google.com/macros/s/test/exec"
    )
    monkeypatch.setenv("SHEET_APPEND_SECRET", "fake")
    calls = []

    class Response:
        status_code = 200

        def raise_for_status(self):
            pass

        def json(self):
            return {"success": True}

    def post(url, **kwargs):
        calls.append(kwargs)
        if fail:
            raise TimeoutError()
        return Response()

    monkeypatch.setattr(main.requests, "post", post)
    jid = create(client)
    for _ in range(2):
        r = client.post(
            "/v1/jobs/" + jid + "/approve",
            json={"approved": True, "write_to_sheet": True},
        )
        assert r.status_code == 200
    assert len(calls) == 1 and calls[0]["json"]["entry"]["englishmeaning"].startswith(
        "'="
    )
    assert r.json()["sheet_results"][0]["status"] == ("uncertain" if fail else "sent")


def test_practice(client):
    with db.connect(main.DB_PATH) as c:
        wid = db.upsert(c, {"arabic": "هلا"})
    r = client.post("/v1/vocab/" + wid + "/practice", json={"transcript": "هلا"}).json()
    assert r["similarity"] == 100 and "not_pronunciation" in r["measurement"]


def test_upload(client):
    assert (
        client.post(
            "/v1/jobs/upload",
            data={"rights_confirmed": "true"},
            files={"file": ("bad.exe", b"bad")},
        ).status_code
        == 422
    )
    assert (
        client.post(
            "/v1/jobs/upload",
            data={"rights_confirmed": "true"},
            files={"file": ("empty.mp4", b"")},
        ).status_code
        == 422
    )


def test_private_dns(monkeypatch):
    monkeypatch.setattr(
        media.socket,
        "getaddrinfo",
        lambda *a, **kw: [(2, 1, 6, "", ("127.0.0.1", 443))],
    )
    with pytest.raises(ValueError):
        media.public_addresses("www.tiktok.com")


def test_login_throttle(client):
    main._login_attempts.clear()
    for _ in range(10):
        assert client.post("/auth/login", json={"password": "wrong"}).status_code == 401
    assert client.post("/auth/login", json={"password": "wrong"}).status_code == 429


def test_body_limit(client):
    assert (
        client.post(
            "/v1/jobs/upload", headers={"Content-Length": str(33 * 1024 * 1024)}
        ).status_code
        == 413
    )


def test_overlap_rejected(client, monkeypatch):
    fake_media(monkeypatch)
    jid = create(client)
    assert (
        client.put(
            "/v1/jobs/" + jid + "/segments",
            json={"segments": [segment(), dict(segment(), start=0.5, end=2)]},
        ).status_code
        == 422
    )


def test_existing_metadata_preserved(client, monkeypatch):
    fake_media(monkeypatch)
    monkeypatch.setattr(providers, "transcribe", lambda p: [segment()])
    with db.connect(main.DB_PATH) as c:
        wid = db.upsert(
            c,
            {
                "arabic": "شلونك",
                "chapter": "Original",
                "explanation": "Original explanation",
                "letter_eng": "letter words",
            },
        )
    jid = create(client)
    assert (
        client.post("/v1/jobs/" + jid + "/approve", json={"approved": True}).status_code
        == 200
    )
    r = client.get("/v1/vocab").json()[0]
    assert (
        r["chapter"] == "Original"
        and r["explanation"] == "Original explanation"
        and r["letter_eng"] == "letter words"
    )


def test_known_sheet_entry_not_duplicated(client, monkeypatch):
    fake_media(monkeypatch)
    monkeypatch.setattr(providers, "transcribe", lambda p: [segment()])
    monkeypatch.setattr(
        main,
        "fetch_sheet_csv",
        lambda url: "Arabic Script,English Meaning\nشلونك,How are you?\n",
    )
    assert client.post("/v1/sheets/import").status_code == 200
    monkeypatch.setenv(
        "SHEET_APPEND_WEBHOOK_URL", "https://script.google.com/macros/s/test/exec"
    )
    monkeypatch.setenv("SHEET_APPEND_SECRET", "fake")

    def forbidden(*a, **kw):
        pytest.fail("Known sheet word was dispatched again")

    monkeypatch.setattr(main.requests, "post", forbidden)
    jid = create(client)
    r = client.post(
        "/v1/jobs/" + jid + "/approve", json={"approved": True, "write_to_sheet": True}
    )
    assert r.json()["sheet_results"][0]["status"] == "already_present"


def test_expired_tampered_and_audio_auth(client):
    import base64, hmac, json, time

    token = client.headers["Authorization"].split()[1]
    assert (
        client.get(
            "/v1/vocab",
            headers={
                "Authorization": "Bearer "
                + token[:-1]
                + ("0" if token[-1] != "0" else "1")
            },
        ).status_code
        == 401
    )
    payload = (
        base64.urlsafe_b64encode(
            json.dumps({"sub": "owner", "exp": int(time.time()) - 1}).encode()
        )
        .decode()
        .rstrip("=")
    )
    signature = hmac.new(b"x" * 40, payload.encode(), hashlib.sha256).hexdigest()
    assert (
        client.get(
            "/v1/vocab",
            headers={"Authorization": "Bearer " + payload + "." + signature},
        ).status_code
        == 401
    )
    assert (
        client.get(
            "/v1/vocab/anything/audio", headers={"Authorization": ""}
        ).status_code
        == 401
    )
    assert (
        client.get(
            "/v1/jobs/anything/segments/0/audio", headers={"Authorization": ""}
        ).status_code
        == 401
    )


def test_restart_marks_interrupted(client):
    jid = main.new_job("https://www.tiktok.com/@u/video/123", True)
    assert client.get("/v1/jobs/" + jid).json()["status"] == "queued"
    with TestClient(main.app) as restarted:
        restarted.headers.update(client.headers)
        assert restarted.get("/v1/jobs/" + jid).json()["status"] == "failed"


def test_concurrent_approval_idempotent(client, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor

    fake_media(monkeypatch)
    monkeypatch.setattr(providers, "transcribe", lambda p: [segment()])
    jid = create(client)

    def approve():
        return client.post("/v1/jobs/" + jid + "/approve", json={"approved": True})

    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(lambda _: approve(), range(2)))
    assert all(r.status_code == 200 for r in responses)
    assert len(client.get("/v1/vocab").json()) == 1
    with db.connect(main.DB_PATH) as c:
        assert c.execute("SELECT COUNT(*) FROM nawab_sources").fetchone()[0] == 1


def test_chunked_body_limit():
    import asyncio
    from fastapi import HTTPException

    messages = iter(
        [{"type": "http.request", "body": b"x" * (17 * 1024 * 1024), "more_body": True}]
        * 2
    )

    async def receive():
        return next(messages)

    async def send(message):
        pass

    async def downstream(scope, receive, send):
        await receive()
        await receive()

    middleware = main.BodyLimitMiddleware(downstream)
    with pytest.raises(HTTPException) as exc:
        asyncio.run(middleware({"type": "http", "headers": []}, receive, send))
    assert exc.value.status_code == 413
