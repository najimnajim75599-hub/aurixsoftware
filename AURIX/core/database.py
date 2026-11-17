"""SQLite storage for AURIX. All SQL in the app goes through this class
and always uses parameterized queries (the ? placeholders)."""
import sqlite3
from contextlib import contextmanager
from pathlib import Path

SCHEMA_VERSION = 2

SCHEMA_V1 = """
CREATE TABLE notes (
    id INTEGER PRIMARY KEY,
    title TEXT NOT NULL,
    body TEXT NOT NULL DEFAULT '',
    kind TEXT NOT NULL DEFAULT 'note' CHECK (kind IN ('note', 'idea')),
    is_important INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);
CREATE TABLE tags (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL UNIQUE COLLATE NOCASE
);
CREATE TABLE note_tags (
    note_id INTEGER NOT NULL REFERENCES notes(id) ON DELETE CASCADE,
    tag_id INTEGER NOT NULL REFERENCES tags(id) ON DELETE CASCADE,
    PRIMARY KEY (note_id, tag_id)
);
CREATE TABLE projects (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'not_started'
        CHECK (status IN ('not_started', 'in_progress', 'done')),
    created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);
CREATE TABLE tasks (
    id INTEGER PRIMARY KEY,
    project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'todo' CHECK (status IN ('todo', 'doing', 'done')),
    deadline TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    completed_at TEXT
);
CREATE TABLE indexed_folders (
    id INTEGER PRIMARY KEY,
    path TEXT NOT NULL UNIQUE,
    paused INTEGER NOT NULL DEFAULT 0,
    added_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);
CREATE TABLE files (
    id INTEGER PRIMARY KEY,
    path TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    extension TEXT NOT NULL DEFAULT '',
    size_bytes INTEGER NOT NULL DEFAULT 0,
    modified_at TEXT,
    folder_id INTEGER REFERENCES indexed_folders(id) ON DELETE CASCADE,
    description TEXT NOT NULL DEFAULT '',
    indexed_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);
CREATE TABLE relations (
    id INTEGER PRIMARY KEY,
    source_type TEXT NOT NULL CHECK (source_type IN ('file','project','note','idea','task')),
    source_id INTEGER NOT NULL,
    target_type TEXT NOT NULL CHECK (target_type IN ('file','project','note','idea','task')),
    target_id INTEGER NOT NULL,
    label TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    UNIQUE (source_type, source_id, target_type, target_id)
);
CREATE TABLE activity (
    id INTEGER PRIMARY KEY,
    event_type TEXT NOT NULL,
    item_type TEXT NOT NULL,
    item_id INTEGER,
    summary TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);
CREATE TABLE settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
CREATE INDEX idx_tasks_project ON tasks(project_id);
CREATE INDEX idx_files_name ON files(name);
CREATE INDEX idx_files_ext ON files(extension);
CREATE INDEX idx_activity_created ON activity(created_at DESC);
"""

MIGRATION_V2 = """
ALTER TABLE files ADD COLUMN tags TEXT NOT NULL DEFAULT '';
ALTER TABLE files ADD COLUMN last_opened_at TEXT;
"""


def like(term: str) -> str:
    """Safe LIKE pattern. Use with: ... LIKE ? ESCAPE '\\'"""
    return "%" + term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"


# Tables shown on the Home status card (and used by tests).
COUNTED_TABLES = ("notes", "projects", "tasks", "files", "relations", "activity")


class Database:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(self.path), timeout=15)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.conn.execute("PRAGMA journal_mode = WAL")
        self._migrate()

    @property
    def schema_version(self) -> int:
        return self.conn.execute("PRAGMA user_version").fetchone()[0]

    def _migrate(self) -> None:
        if self.schema_version < 1:
            self.conn.executescript("BEGIN;" + SCHEMA_V1 + "PRAGMA user_version = 1; COMMIT;")
        if self.schema_version < 2:
            self.conn.executescript("BEGIN;" + MIGRATION_V2 + "PRAGMA user_version = 2; COMMIT;")

    @contextmanager
    def transaction(self):
        """Several statements, one commit. Rolls back automatically on error."""
        with self.conn:
            yield self.conn

    def activity_enabled(self) -> bool:
        """Activity recording can be switched off in Settings (default: on)."""
        row = self.conn.execute("SELECT value FROM settings WHERE key = 'record_activity'").fetchone()
        return row is None or row[0] != "0"

    def log_conn(self, conn, event_type: str, item_type: str, item_id, summary: str) -> None:
        """Record an activity entry inside a transaction you already opened."""
        if self.activity_enabled():
            conn.execute(
                "INSERT INTO activity(event_type, item_type, item_id, summary) VALUES(?, ?, ?, ?)",
                (event_type, item_type, item_id, summary))

    def log(self, event_type: str, item_type: str, item_id, summary: str) -> None:
        with self.conn:
            self.log_conn(self.conn, event_type, item_type, item_id, summary)

    def execute(self, sql: str, params=()) -> int:
        """Run INSERT/UPDATE/DELETE. Returns the new row id (for inserts)."""
        with self.conn:
            cur = self.conn.execute(sql, params)
        return cur.lastrowid

    def query_all(self, sql: str, params=()) -> list:
        return self.conn.execute(sql, params).fetchall()

    def query_one(self, sql: str, params=()):
        return self.conn.execute(sql, params).fetchone()

    def table_counts(self) -> dict:
        # Table names come from a fixed constant, never from user input.
        return {t: self.conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
                for t in COUNTED_TABLES}

    def close(self) -> None:
        self.conn.close()
