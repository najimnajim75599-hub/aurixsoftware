import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from core.database import Database
from core.errors import ValidationError
from core.file_indexer import FileManager, index_folder
from core.memory_manager import MemoryManager, parse_tags
from core.search_engine import SearchEngine, extract_terms


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.db = Database(self.root / "t.db")
        self.mem, self.files, self.search = MemoryManager(self.db), FileManager(self.db), SearchEngine(self.db)

    def tearDown(self):
        self.db.close()
        self.tmp.cleanup()


class MemoryTests(Base):
    def test_parse_tags(self):
        self.assertEqual(parse_tags("#ideas, Study ,ideas,,"), ["ideas", "Study"])

    def test_create_edit_delete(self):
        nid = self.mem.save_note("Plan", "body text", "idea", True, "work, #x")
        n = self.mem.get_note(nid)
        self.assertEqual((n.title, n.kind, n.is_important, n.tags), ("Plan", "idea", True, ["work", "x"]))
        self.mem.save_note("Plan 2", "new", "note", False, "work", note_id=nid)
        n = self.mem.get_note(nid)
        self.assertEqual((n.title, n.tags), ("Plan 2", ["work"]))
        self.assertEqual(self.mem.all_tags(), ["work"])  # orphan tag 'x' removed
        self.mem.delete_note(nid)
        self.assertIsNone(self.mem.get_note(nid))
        self.assertEqual(self.mem.all_tags(), [])
        self.assertEqual(self.db.table_counts()["activity"], 3)

    def test_validation(self):
        with self.assertRaises(ValidationError):
            self.mem.save_note("   ")
        with self.assertRaises(ValidationError):
            self.mem.save_note("x", kind="bogus")
        with self.assertRaises(ValidationError):
            self.mem.save_note("x", note_id=999)

    def test_filters_and_search(self):
        self.mem.save_note("Business Plan", "grow brand", "note", True, "business")
        self.mem.save_note("AI idea", "assistant", "idea", False, "ideas")
        self.assertEqual(len(self.mem.list_notes()), 2)
        self.assertEqual(len(self.mem.list_notes(kind="idea")), 1)
        self.assertEqual(len(self.mem.list_notes(important=True)), 1)
        self.assertEqual(len(self.mem.list_notes(tag="ideas")), 1)
        self.assertEqual(len(self.mem.list_notes(query="brand")), 1)
        self.assertEqual(len(self.mem.list_notes(query="100%")), 0)  # % is literal


class FindTests(Base):
    def make_files(self):
        d = self.root / "docs"
        (d / "sub").mkdir(parents=True)
        (d / ".hidden").mkdir()
        for rel, size in [("logo_final.png", 10), ("sub/AI talk.pptx", 20), ("sub/plan.docx", 5),
                          ("notes.txt", 1), (".hidden/secret.txt", 1), ("~$tmp.docx", 1)]:
            (d / rel).write_bytes(b"x" * size)
        return d

    def test_index_search_and_privacy(self):
        d = self.make_files()
        fid = self.files.add_folder(d)
        count, stopped = index_folder(self.db, fid, str(d))
        self.assertEqual((count, stopped), (4, False))  # hidden folder + temp file skipped
        self.assertEqual(self.files.list_folders()[0]["file_count"], 4)
        names = lambda q, **k: [r.title for r in self.search.search(q, **k)]
        self.assertEqual(names("Find the logo I created for my business"), ["logo_final.png"])
        self.assertEqual(names("presentation about artificial intelligence"), ["AI talk.pptx"])
        self.assertEqual(sorted(names("", group="Documents")), ["notes.txt", "plan.docx"])
        self.assertEqual(len(names("")), 4)

    def test_description_tags_and_rescan_keep_them(self):
        d = self.make_files()
        fid = self.files.add_folder(d)
        index_folder(self.db, fid, str(d))
        f = self.search.search("plan")[0]
        self.files.update_details(f.id, "quarterly roadmap for the startup", "#work, roadmap")
        self.assertEqual([r.title for r in self.search.search("startup")], ["plan.docx"])
        self.assertEqual([r.title for r in self.search.search("roadmap")], ["plan.docx"])
        (d / "sub" / "plan.docx").unlink()
        index_folder(self.db, fid, str(d))  # rescan forgets removed file
        self.assertEqual(self.search.search("startup"), [])
        self.assertEqual(self.files.list_folders()[0]["file_count"], 3)

    def test_linked_note_makes_file_findable(self):
        d = self.make_files()
        fid = self.files.add_folder(d)
        index_folder(self.db, fid, str(d))
        file_id = self.search.search("notes")[0].id
        nid = self.mem.save_note("Meeting", "discuss zebra budget")
        self.db.execute("INSERT INTO relations(source_type,source_id,target_type,target_id) VALUES('note',?, 'file',?)", (nid, file_id))
        kinds = {(r.kind, r.title) for r in self.search.search("zebra")}
        self.assertIn(("file", "notes.txt"), kinds)
        self.assertIn(("note", "Meeting"), kinds)

    def test_stop_and_folder_rules(self):
        d = self.make_files()
        fid = self.files.add_folder(d)
        count, stopped = index_folder(self.db, fid, str(d), should_stop=lambda: True)
        self.assertTrue(stopped)
        with self.assertRaises(ValidationError):
            self.files.add_folder(d)  # duplicate
        with self.assertRaises(ValidationError):
            self.files.add_folder(self.root / "nope")
        with self.assertRaises(ValidationError):
            self.files.add_folder(Path(self.root.anchor))  # whole drive
        index_folder(self.db, fid, str(d))
        self.files.remove_folder(fid)
        self.assertEqual(self.db.table_counts()["files"], 0)  # cascade

    def test_terms(self):
        self.assertEqual(extract_terms("Show my unfinished projects"), ["unfinished", "projects"])


if __name__ == "__main__":
    unittest.main()
