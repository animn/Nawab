"""Offline/quiesced SQLite + media backup, with checksums and restore verification.

Pause new requests and wait for processing to finish before using `create`.
This command never deletes originals and refuses to overwrite an existing backup.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3


def digest(path: Path) -> str:
    result = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            result.update(block)
    return result.hexdigest()


def inspect_database(path: Path) -> dict:
    with sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True) as db:
        if db.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise ValueError("Database integrity check failed.")
        tables = {
            r[0]
            for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        if "nawab_jobs" in tables:
            active = db.execute(
                "SELECT count(*) FROM nawab_jobs WHERE status IN ('queued','processing')"
            ).fetchone()[0]
            if active:
                raise ValueError(
                    "Wait for queued/processing jobs to finish before backup."
                )
        if "nawab_sheet_outbox" in tables:
            sending = db.execute(
                "SELECT count(*) FROM nawab_sheet_outbox WHERE status='sending'"
            ).fetchone()[0]
            if sending:
                raise ValueError("Wait for Sheet dispatch to finish before backup.")
        counts = {}
        if "vocab" in tables:
            columns = {r[1] for r in db.execute("PRAGMA table_info(vocab)")}
            counts["vocabulary"] = db.execute("SELECT count(*) FROM vocab").fetchone()[
                0
            ]
            for column, label in (
                ("score", "nonzero_scores"),
                ("notes", "saved_notes"),
                ("audio_mp3", "saved_audio"),
            ):
                if column in columns:
                    condition = (
                        "score != 0" if column == "score" else f"length({column}) > 0"
                    )
                    counts[label] = db.execute(
                        f"SELECT count(*) FROM vocab WHERE {condition}"
                    ).fetchone()[0]
        return counts


def referenced_media(database: Path, media_root: Path) -> set[str]:
    """Map every current API file reference into the snapshot, without reading live files."""
    references = set()
    with sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True) as db:
        for table, columns in {
            "nawab_jobs": ("media_path", "audio_path"),
            "nawab_practice": ("recording_path",),
            "nawab_video_assets": ("path",),
        }.items():
            present = {r[1] for r in db.execute(f"PRAGMA table_info({table})")}
            for column in columns:
                if column not in present:
                    continue
                for (value,) in db.execute(
                    f"SELECT {column} FROM {table} WHERE {column} IS NOT NULL AND {column} != ''"
                ):
                    path = Path(value)
                    if not path.is_absolute() or ".." in path.parts:
                        raise ValueError(
                            "Runtime media reference is not an absolute safe path."
                        )
                    try:
                        relative = path.relative_to(media_root)
                    except ValueError:
                        raise ValueError(
                            "Runtime media reference is outside the configured media directory."
                        ) from None
                    references.add((Path("media") / relative).as_posix())
    return references


def create_backup(
    database: Path, media: Path, destination: Path, quiesced: bool
) -> dict:
    if not quiesced:
        raise ValueError("Pause requests, finish active jobs, then pass --quiesced.")
    if database.is_symlink() or media.is_symlink():
        raise ValueError("Source paths must not be symbolic links.")
    database, media, destination = (
        database.resolve(),
        media.resolve(),
        destination.resolve(),
    )
    if not database.is_file() or not media.is_dir():
        raise ValueError("Both the existing database and media directory are required.")
    if destination == media or media in destination.parents:
        raise ValueError("Backup destination must be outside the media directory.")
    counts = inspect_database(database)
    references = referenced_media(database, media)
    originals = []
    for path in sorted(media.rglob("*")):
        if path.is_symlink():
            raise ValueError(
                "Media directory contains a symbolic link; inspect before backup."
            )
        if path.is_file():
            originals.append(path)
    available = {(Path("media") / p.relative_to(media)).as_posix() for p in originals}
    if not references.issubset(available):
        raise ValueError(
            "A referenced original, audio, recording or video clip is missing. Backup cannot be verified."
        )
    destination.parent.mkdir(parents=True, exist_ok=True)
    required = (
        database.stat().st_size
        + sum(p.stat().st_size for p in originals)
        + 512 * 1024**2
    )
    if shutil.disk_usage(destination.parent).free < required:
        raise ValueError("Insufficient backup space; keep at least 512 MiB free.")
    destination.mkdir(mode=0o700, exist_ok=False)
    copied_db = destination / "database.sqlite3"
    with sqlite3.connect(database.as_uri() + "?mode=ro", uri=True) as source:
        with sqlite3.connect(copied_db) as target:
            source.backup(target)
    if inspect_database(copied_db) != counts:
        raise ValueError(
            "Database changed during backup. Keep this incomplete copy for inspection."
        )
    files = {"database.sqlite3": digest(copied_db)}
    (destination / "media").mkdir(mode=0o700)
    for source in originals:
        relative = Path("media") / source.relative_to(media)
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        files[relative.as_posix()] = digest(target)
        if files[relative.as_posix()] != digest(source):
            raise ValueError(
                "Media changed during backup. Pause requests before retrying to a new destination."
            )
    manifest = {
        "version": 1,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "original_database_path": str(database),
        "original_media_root": str(media),
        "counts": counts,
        "sha256": files,
    }
    (destination / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    verify_backup(destination)
    return manifest


def verify_backup(directory: Path) -> dict:
    directory = directory.resolve()
    manifest = json.loads((directory / "manifest.json").read_text())
    if manifest.get("version") != 1 or "database.sqlite3" not in manifest.get(
        "sha256", {}
    ):
        raise ValueError("Backup manifest is missing or unsupported.")
    for name, expected in manifest["sha256"].items():
        path = directory / name
        if (
            path.is_symlink()
            or directory not in path.resolve().parents
            or not path.is_file()
        ):
            raise ValueError("Unsafe or missing backup file.")
        if digest(path) != expected:
            raise ValueError("Backup checksum verification failed.")
    if inspect_database(directory / "database.sqlite3") != manifest["counts"]:
        raise ValueError("Backup record-count verification failed.")
    media_root = Path(manifest.get("original_media_root", ""))
    if not media_root.is_absolute() or ".." in media_root.parts:
        raise ValueError("Original media mount path is missing or unsafe.")
    references = referenced_media(directory / "database.sqlite3", media_root)
    if not references.issubset(manifest["sha256"]):
        raise ValueError(
            "A database media reference is missing from the verified snapshot."
        )
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    create = commands.add_parser("create")
    create.add_argument("--database", type=Path, required=True)
    create.add_argument("--media", type=Path, required=True)
    create.add_argument("--destination", type=Path, required=True)
    create.add_argument("--quiesced", action="store_true")
    verify = commands.add_parser("verify")
    verify.add_argument("directory", type=Path)
    args = parser.parse_args()
    os.umask(0o077)
    try:
        result = (
            create_backup(args.database, args.media, args.destination, args.quiesced)
            if args.command == "create"
            else verify_backup(args.directory)
        )
    except (ValueError, OSError, sqlite3.Error) as exc:
        parser.exit(1, f"Backup not verified: {exc}\n")
    print(
        json.dumps(
            {
                "verified": True,
                "files": len(result["sha256"]),
                "counts": result["counts"],
            }
        )
    )


if __name__ == "__main__":
    main()
