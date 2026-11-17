"""Backup and restore of the AURIX database using SQLite's own safe backup API."""
import sqlite3
from datetime import datetime
from pathlib import Path

from core.database import SCHEMA_VERSION
from core.errors import ValidationError

REQUIRED_TABLES = {"notes", "tags", "note_tags", "projects", "tasks", "indexed_folders", "files",
                   "relations", "activity", "settings"}


def default_backup_name() -> str:
    return f"aurix-backup-{datetime.now():%Y-%m-%d_%H%M}.db"


def backup_to(db, dest_path) -> Path:
    """Write a consistent copy of the live database to dest_path."""
    dest = Path(dest_path)
    if dest.exists() and dest.samefile(db.path):
        raise ValidationError("Choose a different file than the live database.")
    dest.parent.mkdir(parents=True, exist_ok=True)
    out = sqlite3.connect(str(dest))
    try:
        db.conn.backup(out)
    finally:
        out.close()
    return dest


def validate_backup(path) -> int:
    """Check the file is an AURIX database. Returns its schema version."""
    p = Path(path)
    if not p.is_file():
        raise ValidationError("That file does not exist.")
    try:
        conn = sqlite3.connect(f"file:{p.as_posix()}?mode=ro", uri=True)
        try:
            if conn.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise ValidationError("That backup file is damaged.")
            tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            version = conn.execute("PRAGMA user_version").fetchone()[0]
        finally:
            conn.close()
    except sqlite3.DatabaseError:
        raise ValidationError("That is not an AURIX backup file.")
    if not REQUIRED_TABLES <= tables:
        raise ValidationError("That is not an AURIX backup file.")
    if version > SCHEMA_VERSION:
        raise ValidationError("That backup was made by a newer version of AURIX. Please update AURIX first.")
    return version


def restore_from(db, src_path, safety_dir) -> Path:
    """Replace the live data with the backup. First saves the current data into safety_dir
    so a mistaken restore can be undone. Returns the safety backup path."""
    validate_backup(src_path)
    safety = backup_to(db, Path(safety_dir) / f"before-restore-{datetime.now():%Y-%m-%d_%H%M%S}.db")
    src = sqlite3.connect(str(src_path))
    try:
        src.backup(db.conn)
    finally:
        src.close()
    db.conn.execute("PRAGMA foreign_keys = ON")
    db._migrate()  # an older backup is upgraded to the current layout
    return safety


def erase_all_data(db) -> None:
    """Delete every user record (notes, projects, files index, connections, activity). Settings stay."""
    with db.transaction() as c:
        for table in ("relations", "note_tags", "tags", "notes", "tasks", "projects", "files", "indexed_folders", "activity"):
            c.execute(f"DELETE FROM {table}")  # fixed names, never user input
    db.conn.execute("VACUUM")
