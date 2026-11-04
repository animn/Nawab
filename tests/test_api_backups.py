import shutil
import sqlite3
from pathlib import Path
import json

import pytest

from api import db
from scripts.backup_runtime import create_backup, verify_backup


@pytest.fixture
def legacy_runtime(tmp_path):
    database = tmp_path / "learning_progress_v8.db"
    with sqlite3.connect(database) as connection:
        connection.execute(
            "CREATE TABLE vocab (id TEXT PRIMARY KEY, arabic TEXT, score INTEGER, notes TEXT, audio_mp3 BLOB, future_column TEXT)"
        )
        connection.execute(
            "INSERT INTO vocab VALUES (?,?,?,?,?,?)",
            (
                "original-id",
                "شلونك",
                7,
                "Keep my note",
                b"original-audio",
                "keep-extra",
            ),
        )
    media = tmp_path / "media"
    (media / "job-one").mkdir(parents=True)
    (media / "job-one" / "original.mp4").write_bytes(b"synthetic-video-fixture")
    return database, media


def test_backup_restore_preserves_legacy_fields_audio_and_media(
    tmp_path, legacy_runtime
):
    database, media = legacy_runtime
    backup = tmp_path / "snapshot"
    manifest = create_backup(database, media, backup, quiesced=True)
    assert manifest["counts"] == {
        "vocabulary": 1,
        "nonzero_scores": 1,
        "saved_notes": 1,
        "saved_audio": 1,
    }
    assert verify_backup(backup) == manifest
    restored = tmp_path / "restore-test"
    restored.mkdir()
    restored_db = restored / "learning_progress_v8.db"
    shutil.copyfile(backup / "database.sqlite3", restored_db)
    shutil.copytree(backup / "media", restored / "media")
    db.init(restored_db)
    with sqlite3.connect(restored_db) as connection:
        assert connection.execute(
            "SELECT id,score,notes,audio_mp3,future_column FROM vocab"
        ).fetchone() == (
            "original-id",
            7,
            "Keep my note",
            b"original-audio",
            "keep-extra",
        )
    assert (
        restored / "media/job-one/original.mp4"
    ).read_bytes() == b"synthetic-video-fixture"
    with sqlite3.connect(database) as connection:
        assert len(connection.execute("PRAGMA table_info(vocab)").fetchall()) == 6


def test_backup_requires_quiesced_service(tmp_path, legacy_runtime):
    with pytest.raises(ValueError, match="Pause requests"):
        create_backup(*legacy_runtime, tmp_path / "snapshot", quiesced=False)


def test_backup_never_overwrites_existing_destination(tmp_path, legacy_runtime):
    destination = tmp_path / "snapshot"
    destination.mkdir()
    (destination / "keep").write_text("keep")
    with pytest.raises(FileExistsError):
        create_backup(*legacy_runtime, destination, quiesced=True)
    assert (destination / "keep").read_text() == "keep"


def test_backup_verification_detects_media_corruption(tmp_path, legacy_runtime):
    destination = tmp_path / "snapshot"
    create_backup(*legacy_runtime, destination, quiesced=True)
    (destination / "media/job-one/original.mp4").write_bytes(b"corrupted")
    with pytest.raises(ValueError, match="checksum"):
        verify_backup(destination)


def test_backup_refuses_active_jobs(tmp_path, legacy_runtime):
    database, media = legacy_runtime
    db.init(database)
    with sqlite3.connect(database) as connection:
        connection.execute(
            "INSERT INTO nawab_jobs (id,status,rights_confirmed,created_at,updated_at) VALUES ('busy','processing',1,'now','now')"
        )
    with pytest.raises(ValueError, match="processing"):
        create_backup(database, media, tmp_path / "snapshot", quiesced=True)


def test_backup_rejects_symlink_media(tmp_path, legacy_runtime):
    database, media = legacy_runtime
    (media / "alias").symlink_to(database)
    with pytest.raises(ValueError, match="symbolic link"):
        create_backup(database, media, tmp_path / "snapshot", quiesced=True)


def test_backup_rejects_missing_referenced_media(tmp_path, legacy_runtime):
    database, media = legacy_runtime
    db.init(database)
    with sqlite3.connect(database) as connection:
        connection.execute(
            "INSERT INTO nawab_jobs (id,status,rights_confirmed,media_path,audio_path,created_at,updated_at) VALUES ('lost','approved',1,?,?,'now','now')",
            (str(media / "missing.mp4"), str(media / "missing.mp3")),
        )
    with pytest.raises(ValueError, match="referenced"):
        create_backup(database, media, tmp_path / "snapshot", quiesced=True)


def test_verify_rejects_reference_omitted_from_manifest(tmp_path, legacy_runtime):
    database, media = legacy_runtime
    db.init(database)
    with sqlite3.connect(database) as connection:
        connection.execute(
            "INSERT INTO nawab_jobs (id,status,rights_confirmed,media_path,created_at,updated_at) VALUES ('job-one','approved',1,?,'now','now')",
            (str(media / "job-one/original.mp4"),),
        )
    snapshot = tmp_path / "snapshot"
    manifest = create_backup(database, media, snapshot, quiesced=True)
    del manifest["sha256"]["media/job-one/original.mp4"]
    (snapshot / "manifest.json").write_text(json.dumps(manifest))
    (snapshot / "media/job-one/original.mp4").unlink()
    with pytest.raises(ValueError, match="media reference"):
        verify_backup(snapshot)


def test_modern_runtime_restore_uses_restored_files_not_originals(
    tmp_path, legacy_runtime
):
    database, media = legacy_runtime
    db.init(database)
    job_dir = media / "job-one"
    for name in ("audio.mp3", "sentence.mp4", "practice.m4a"):
        (job_dir / name).write_bytes(("fixture-" + name).encode())
    with sqlite3.connect(database) as connection:
        connection.execute(
            "INSERT INTO nawab_jobs (id,status,rights_confirmed,media_path,audio_path,created_at,updated_at) VALUES ('job-one','approved',1,?,?,'now','now')",
            (str(job_dir / "original.mp4"), str(job_dir / "audio.mp3")),
        )
        connection.execute(
            "INSERT INTO nawab_video_assets (job_id,segment_index,start,end,path,metadata,created_at) VALUES ('job-one',0,0,1,?,'{}','now')",
            (str(job_dir / "sentence.mp4"),),
        )
        connection.execute(
            "INSERT INTO nawab_practice (id,vocab_id,recording_path,transcript,reference_text,similarity,measurement,created_at) VALUES ('practice','original-id',?,'x','x',1,'test','now')",
            (str(job_dir / "practice.m4a"),),
        )
    snapshot = tmp_path / "snapshot"
    create_backup(database, media, snapshot, quiesced=True)
    # Simulate an isolated replacement host preserving the original mount paths.
    # Move old files completely away before restoration so no reads can fall back.
    old_media = tmp_path / "offline-originals"
    media.rename(old_media)
    database.rename(tmp_path / "offline-original.db")
    verify_backup(snapshot)  # Verification reads backup files, not the original mount.
    shutil.copyfile(snapshot / "database.sqlite3", database)
    shutil.copytree(snapshot / "media", media)
    db.init(database)
    with sqlite3.connect(database) as connection:
        paths = [
            value
            for row in connection.execute(
                "SELECT media_path,audio_path FROM nawab_jobs"
            )
            for value in row
        ]
        paths.extend(
            row[0] for row in connection.execute("SELECT path FROM nawab_video_assets")
        )
        paths.extend(
            row[0]
            for row in connection.execute("SELECT recording_path FROM nawab_practice")
        )
    assert len(paths) == 4
    for value in paths:
        restored = Path(value)
        original = old_media / restored.relative_to(media)
        assert restored.is_file()
        assert not restored.samefile(original)
        assert restored.read_bytes() == original.read_bytes()
