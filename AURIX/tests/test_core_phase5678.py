import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from core.activity_manager import ActivityManager
from core.database import Database
from core.errors import ValidationError
from core.file_indexer import FileManager, index_folder
from core.memory_manager import MemoryManager
from core.project_manager import ProjectManager
from core.relationship_engine import RelationshipEngine
from services import backup_service


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.db = Database(self.root / "t.db")
        self.mem, self.proj = MemoryManager(self.db), ProjectManager(self.db)
        self.rel, self.act, self.files = RelationshipEngine(self.db), ActivityManager(self.db), FileManager(self.db)

    def tearDown(self):
        self.db.close()
        self.tmp.cleanup()


class FlowTests(Base):
    def test_project_progress_and_status(self):
        pid = self.proj.save_project("Website", "Build it")
        self.assertEqual(self.proj.get_project(pid).progress, 0)
        t1 = self.proj.add_task(pid, "Design", "2026-12-01")
        t2 = self.proj.add_task(pid, "Code")
        self.proj.set_task_status(t1, "done")
        p = self.proj.get_project(pid)
        self.assertEqual((p.total_tasks, p.done_tasks, p.progress), (2, 1, 50))
        self.assertTrue(self.proj.get_task(t1).completed_at)
        self.proj.set_task_status(t1, "todo")
        self.assertEqual(self.proj.get_task(t1).completed_at, "")
        self.proj.save_project("Website", "Build it", "done", pid)
        self.assertEqual(self.proj.get_project(pid).status, "done")

    def test_validation(self):
        pid = self.proj.save_project("P")
        for bad in (lambda: self.proj.save_project("  "), lambda: self.proj.add_task(pid, ""),
                    lambda: self.proj.add_task(pid, "x", "31/12/2026"), lambda: self.proj.add_task(999, "x"),
                    lambda: self.proj.set_task_status(1, "bogus")):
            with self.assertRaises(ValidationError):
                bad()

    def test_history_and_delete(self):
        pid = self.proj.save_project("P")
        tid = self.proj.add_task(pid, "T")
        self.proj.set_task_status(tid, "done")
        events = [h["event_type"] for h in self.proj.history(pid)]
        self.assertEqual(events, ["task_done", "task_added", "created"])
        nid = self.mem.save_note("n")
        self.rel.connect("project", pid, "note", nid)
        self.rel.connect("task", tid, "note", nid)
        self.proj.delete_project(pid)
        self.assertEqual(self.db.table_counts()["tasks"], 0)
        self.assertEqual(self.db.table_counts()["relations"], 0)

    def test_sql_injection_text_is_just_text(self):
        pid = self.proj.save_project("x'); DROP TABLE projects;--")
        self.assertEqual(self.proj.list_projects("DROP")[0].id, pid)


class ConnectTests(Base):
    def test_connect_and_graph(self):
        pid = self.proj.save_project("P")
        nid = self.mem.save_note("Idea one", kind="idea")
        tid = self.proj.add_task(pid, "T")
        self.rel.connect("project", pid, "idea", nid, "inspired by")
        self.rel.connect("task", tid, "idea", nid)
        links = self.rel.links_for("idea", nid)
        self.assertEqual({l["other"]["type"] for l in links}, {"project", "task"})
        nodes, edges = self.rel.graph()
        self.assertEqual(len(nodes), 3)
        self.assertTrue(all("x" in n and "y" in n for n in nodes.values()))
        self.assertGreaterEqual(len(edges), 3)  # 2 stored + implicit project-task

    def test_rules(self):
        pid = self.proj.save_project("P")
        nid = self.mem.save_note("n")
        self.rel.connect("project", pid, "note", nid)
        for bad in (lambda: self.rel.connect("note", nid, "project", pid),   # duplicate (reverse)
                    lambda: self.rel.connect("project", pid, "project", pid),
                    lambda: self.rel.connect("project", pid, "note", 999),
                    lambda: self.rel.connect("planet", 1, "note", nid)):
            with self.assertRaises(ValidationError):
                bad()

    def test_deleted_note_and_orphans(self):
        pid = self.proj.save_project("P")
        nid = self.mem.save_note("n")
        self.rel.connect("project", pid, "note", nid)
        self.mem.delete_note(nid)
        self.assertEqual(self.rel.links_for("project", pid), [])

    def test_file_removed_from_index_is_pruned(self):
        d = self.root / "docs"
        d.mkdir()
        (d / "a.txt").write_text("hi")
        fid = self.files.add_folder(d)
        index_folder(self.db, fid, str(d))
        file_id = self.db.query_one("SELECT id FROM files")["id"]
        pid = self.proj.save_project("P")
        self.rel.connect("project", pid, "file", file_id)
        self.files.remove_folder(fid)
        nodes, edges = self.rel.graph()
        self.assertEqual(edges, [])
        self.assertEqual(self.db.table_counts()["relations"], 0)


class ActivityTests(Base):
    def test_filters_and_recording_switch(self):
        pid = self.proj.save_project("P")
        tid = self.proj.add_task(pid, "T")
        self.proj.set_task_status(tid, "done")
        self.mem.save_note("N")
        self.assertEqual(len(self.act.list("Tasks")), 2)
        self.assertEqual(len(self.act.list("Notes")), 1)
        self.assertEqual(len(self.act.list("Projects")), 1)
        self.assertEqual(len(self.act.list("All", "Today")), 4)
        self.act.set_recording(False)
        before = len(self.act.list())
        self.mem.save_note("Silent")
        self.proj.save_project("Silent")
        self.assertEqual(len(self.act.list()), before)
        self.act.set_recording(True)
        self.mem.save_note("Loud")
        self.assertEqual(len(self.act.list()), before + 1)
        self.act.clear()
        self.assertEqual(self.act.list(), [])


class BackupTests(Base):
    def test_backup_restore_roundtrip(self):
        self.mem.save_note("Keep me", "important text")
        self.proj.save_project("Keep project")
        bk = backup_service.backup_to(self.db, self.root / "b" / "x.db")
        self.assertEqual(backup_service.validate_backup(bk), 2)
        self.mem.save_note("Added later")
        self.mem.delete_note(self.mem.list_notes("Keep")[0].id)
        safety = backup_service.restore_from(self.db, bk, self.root / "safe")
        self.assertTrue(safety.exists())
        self.assertEqual([n.title for n in self.mem.list_notes()], ["Keep me"])
        self.assertEqual(self.db.query_one("PRAGMA foreign_keys")[0], 1)
        self.mem.save_note("Works after restore")
        self.assertEqual(len(self.mem.list_notes()), 2)
        # the safety copy holds the state before restore
        self.assertEqual(backup_service.validate_backup(safety), 2)

    def test_rejects_non_aurix_files(self):
        junk = self.root / "junk.db"
        junk.write_text("not a database")
        with self.assertRaises(ValidationError):
            backup_service.validate_backup(junk)
        import sqlite3
        other = self.root / "other.db"
        c = sqlite3.connect(other); c.execute("CREATE TABLE x(a)"); c.commit(); c.close()
        with self.assertRaises(ValidationError):
            backup_service.validate_backup(other)
        with self.assertRaises(ValidationError):
            backup_service.validate_backup(self.root / "missing.db")

    def test_erase_all(self):
        self.mem.save_note("a", tags="t")
        self.proj.add_task(self.proj.save_project("p"), "t")
        backup_service.erase_all_data(self.db)
        counts = self.db.table_counts()
        self.assertEqual(sum(counts.values()), 0)


if __name__ == "__main__":
    unittest.main()
