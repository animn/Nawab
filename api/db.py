import hashlib
import sqlite3
from pathlib import Path
from datetime import datetime, timezone
from contextlib import contextmanager

COLUMNS = {
    "chapter": "TEXT",
    "arabic": "TEXT",
    "pronunciation": "TEXT",
    "english": "TEXT",
    "explanation": "TEXT",
    "letter_pronunc": "TEXT",
    "letter_eng": "TEXT",
    "score": "INTEGER DEFAULT 0",
    "notes": "TEXT DEFAULT ''",
    "ttstext": "TEXT DEFAULT ''",
    "audio_mp3": "BLOB",
    "audio_provider": "TEXT DEFAULT ''",
}


@contextmanager
def connect(path):
    conn = sqlite3.connect(path, timeout=20)
    conn.row_factory = sqlite3.Row
    try:
        with conn:
            yield conn
    finally:
        conn.close()


def init(path):
    # SQLite backup produces a consistent snapshot even when the legacy app is open.
    if Path(path).exists():
        with connect(path) as source:
            present = {r[1] for r in source.execute("PRAGMA table_info(vocab)")}
            existing_api = source.execute(
                "SELECT 1 FROM sqlite_master WHERE name='nawab_jobs'"
            ).fetchone()
            if present and (not existing_api or not set(COLUMNS).issubset(present)):
                backup_path = (
                    str(path)
                    + ".pre-api-"
                    + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%f")
                    + ".bak"
                )
                with sqlite3.connect(backup_path) as target:
                    source.backup(target)
    with connect(path) as c:
        c.execute("CREATE TABLE IF NOT EXISTS vocab (id TEXT PRIMARY KEY)")
        present = {r[1] for r in c.execute("PRAGMA table_info(vocab)")}
        for name, definition in COLUMNS.items():
            if name not in present:
                c.execute(f"ALTER TABLE vocab ADD COLUMN {name} {definition}")
        c.executescript("""
        CREATE TABLE IF NOT EXISTS nawab_jobs (
          id TEXT PRIMARY KEY, status TEXT NOT NULL, source_url TEXT NOT NULL DEFAULT '',
          rights_confirmed INTEGER NOT NULL, media_path TEXT, audio_path TEXT,
          duration REAL, segments TEXT NOT NULL DEFAULT '[]', error TEXT NOT NULL DEFAULT '',
          created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS nawab_sources (
          job_id TEXT NOT NULL, segment_index INTEGER NOT NULL, vocab_id TEXT NOT NULL,
          start REAL NOT NULL, end REAL NOT NULL, PRIMARY KEY(job_id, segment_index));
        CREATE TABLE IF NOT EXISTS nawab_sheet_known (vocab_id TEXT PRIMARY KEY);
        CREATE TABLE IF NOT EXISTS nawab_sheet_outbox (
          vocab_id TEXT PRIMARY KEY, operation_id TEXT UNIQUE NOT NULL, status TEXT NOT NULL,
          payload TEXT NOT NULL, error TEXT NOT NULL DEFAULT '');
        CREATE TABLE IF NOT EXISTS nawab_practice (
          id TEXT PRIMARY KEY, vocab_id TEXT NOT NULL, recording_path TEXT,
          transcript TEXT NOT NULL, reference_text TEXT NOT NULL, similarity REAL NOT NULL,
          measurement TEXT NOT NULL, created_at TEXT NOT NULL);
        """)


def upsert(c, fields):
    arabic = fields["arabic"].strip()
    word_id = hashlib.md5(arabic.encode()).hexdigest()
    names = [
        "chapter",
        "arabic",
        "pronunciation",
        "english",
        "explanation",
        "letter_pronunc",
        "letter_eng",
        "ttstext",
    ]
    values = [fields.get(n, "") for n in names]
    values[1] = arabic
    c.execute(
        "INSERT INTO vocab (id,"
        + ",".join(names)
        + ") VALUES ("
        + ",".join("?" for _ in range(9))
        + ") ON CONFLICT(id) DO UPDATE SET "
        + ",".join(n + "=excluded." + n for n in names if n != "ttstext")
        + ",ttstext=CASE WHEN excluded.ttstext != '' THEN excluded.ttstext ELSE vocab.ttstext END",
        [word_id] + values,
    )
    return word_id
