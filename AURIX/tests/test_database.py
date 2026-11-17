import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from core.database import Database
from core.settings import AppSettings


class DatabaseTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "test.db"
        self.db = Database(self.path)

    def tearDown(self):
        self.db.close()
        self.tmp.cleanup()

    def test_schema_created(self):
        self.assertEqual(self.db.schema_version, 2)
        self.assertEqual(set(self.db.table_counts().values()), {0})

    def test_reopen_keeps_data(self):
        self.db.execute("INSERT INTO notes(title) VALUES(?)", ("hello",))
        self.db.close()
        self.db = Database(self.path)
        self.assertEqual(self.db.table_counts()["notes"], 1)

    def test_parameterized_query_is_safe(self):
        evil = "x'); DROP TABLE notes;--"
        self.db.execute("INSERT INTO notes(title) VALUES(?)", (evil,))
        row = self.db.query_one("SELECT title FROM notes")
        self.assertEqual(row["title"], evil)

    def test_cascade_delete_tasks(self):
        pid = self.db.execute("INSERT INTO projects(name) VALUES(?)", ("P",))
        self.db.execute("INSERT INTO tasks(project_id, title) VALUES(?, ?)", (pid, "T"))
        self.db.execute("DELETE FROM projects WHERE id = ?", (pid,))
        self.assertEqual(self.db.table_counts()["tasks"], 0)

    def test_invalid_status_rejected(self):
        with self.assertRaises(sqlite3.IntegrityError):
            self.db.execute("INSERT INTO projects(name, status) VALUES(?, ?)", ("P", "bogus"))

    def test_settings_roundtrip(self):
        s = AppSettings(self.db)
        self.assertEqual(s.get("theme", "light"), "light")
        s.set("theme", "dark")
        s.set("theme", "dark2")
        self.assertEqual(s.get("theme"), "dark2")


if __name__ == "__main__":
    unittest.main()
