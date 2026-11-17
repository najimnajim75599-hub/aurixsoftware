"""Indexing of user-chosen folders (names, sizes, dates only; contents are never read)
and management of indexed folders / file details."""
import os
import sqlite3
from datetime import datetime
from pathlib import Path

from core.errors import ValidationError
from core.memory_manager import parse_tags
from models.file_record import FileRecord

SKIP_DIRS = {"$recycle.bin", "system volume information", "node_modules", "__pycache__",
             "appdata", "windows", "program files", "program files (x86)"}
BATCH = 200


def scan(folder_path, should_stop=lambda: False):
    """Yield one dict per file. Skips hidden/system folders. Never opens files."""
    for root, dirs, names in os.walk(folder_path, onerror=lambda e: None):
        dirs[:] = [d for d in dirs if not d.startswith(".") and d.lower() not in SKIP_DIRS]
        for name in names:
            if should_stop():
                return
            if name.startswith((".", "~$")):
                continue
            full = os.path.join(root, name)
            try:
                st = os.stat(full)
            except OSError:
                continue
            yield {
                "path": full, "name": name,
                "extension": os.path.splitext(name)[1].lower().lstrip("."),
                "size": st.st_size,
                "modified": datetime.fromtimestamp(st.st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
            }


def index_folder(db, folder_id, folder_path, should_stop=lambda: False, progress=None):
    """Scan one folder into the files table. Keeps descriptions and tags you wrote.
    Returns (files_seen, stopped_early)."""
    db.conn.execute("CREATE TEMP TABLE IF NOT EXISTS seen(path TEXT PRIMARY KEY)")
    db.conn.execute("DELETE FROM seen")
    count = 0
    sql = ("INSERT INTO files(path, name, extension, size_bytes, modified_at, folder_id) "
           "VALUES(?, ?, ?, ?, ?, ?) ON CONFLICT(path) DO UPDATE SET name=excluded.name, "
           "extension=excluded.extension, size_bytes=excluded.size_bytes, "
           "modified_at=excluded.modified_at, folder_id=excluded.folder_id, "
           "indexed_at=datetime('now','localtime')")
    batch = []

    def flush():
        with db.transaction() as c:
            c.executemany(sql, [(f["path"], f["name"], f["extension"], f["size"], f["modified"], folder_id) for f in batch])
            c.executemany("INSERT OR IGNORE INTO seen(path) VALUES(?)", [(f["path"],) for f in batch])
        batch.clear()

    for info in scan(folder_path, should_stop):
        batch.append(info)
        count += 1
        if len(batch) >= BATCH:
            flush()
            if progress:
                progress(count)
    if batch:
        flush()
    stopped = should_stop()
    if not stopped:
        with db.transaction() as c:  # forget files that no longer exist
            c.execute("DELETE FROM files WHERE folder_id = ? AND path NOT IN (SELECT path FROM seen)", (folder_id,))
        db.log("indexed", "folder", folder_id, f"Indexed {count} files in {Path(folder_path).name or folder_path}")
    if progress:
        progress(count)
    return count, stopped


class FileManager:
    """Indexed folders and per-file details (description, tags)."""

    def __init__(self, db):
        self.db = db

    # folders
    def add_folder(self, path) -> int:
        p = Path(path).expanduser()
        if not p.is_dir():
            raise ValidationError("That folder does not exist.")
        p = p.resolve()
        if p.parent == p:
            raise ValidationError("Please choose a specific folder, not a whole drive.")
        try:
            fid = self.db.execute("INSERT INTO indexed_folders(path) VALUES(?)", (str(p),))
        except sqlite3.IntegrityError:
            raise ValidationError("That folder is already indexed.")
        self.db.log("added", "folder", fid, f"Folder added for indexing: {p.name}")
        return fid

    def list_folders(self) -> list:
        return self.db.query_all(
            "SELECT d.*, (SELECT COUNT(*) FROM files f WHERE f.folder_id = d.id) AS file_count "
            "FROM indexed_folders d ORDER BY d.added_at, d.id")

    def set_paused(self, folder_id: int, paused: bool) -> None:
        self.db.execute("UPDATE indexed_folders SET paused = ? WHERE id = ?", (int(paused), folder_id))

    def remove_folder(self, folder_id: int) -> None:
        row = self.db.query_one("SELECT path FROM indexed_folders WHERE id = ?", (folder_id,))
        if row:
            self.db.execute("DELETE FROM indexed_folders WHERE id = ?", (folder_id,))  # files cascade
            self.db.log("removed", "folder", folder_id, f"Folder removed: {Path(row['path']).name}")

    # files
    def get_file(self, file_id: int):
        row = self.db.query_one("SELECT * FROM files WHERE id = ?", (file_id,))
        return FileRecord.from_row(row) if row else None

    def recent_files(self, limit=5) -> list:
        rows = self.db.query_all(
            "SELECT * FROM files ORDER BY last_opened_at IS NULL, last_opened_at DESC, modified_at DESC LIMIT ?",
            (limit,))
        return [FileRecord.from_row(r) for r in rows]

    def touch_opened(self, file_id: int) -> None:
        self.db.execute("UPDATE files SET last_opened_at = datetime('now','localtime') WHERE id = ?", (file_id,))

    def update_details(self, file_id: int, description: str, tags: str) -> None:
        description = (description or "").strip()
        if len(description) > 2000:
            raise ValidationError("The description is too long (max 2000 characters).")
        f = self.get_file(file_id)
        if f is None:
            raise ValidationError("That file is no longer in the index.")
        self.db.execute("UPDATE files SET description = ?, tags = ? WHERE id = ?",
                        (description, ", ".join(parse_tags(tags)), file_id))
        self.db.log("updated", "file", file_id, f"File details updated: {f.name}")

    def undescribed_count(self) -> int:
        return self.db.query_one("SELECT COUNT(*) FROM files WHERE description = ''")[0]
