"""Notes and ideas: create, edit, delete, tag, search. No UI code here."""
import re

from core.database import like
from core.errors import ValidationError
from models.note import Note

MAX_TITLE = 200
MAX_BODY = 100_000

_SELECT = """
SELECT n.*, COALESCE((SELECT group_concat(t.name, ',') FROM note_tags nt
        JOIN tags t ON t.id = nt.tag_id WHERE nt.note_id = n.id), '') AS tag_list
FROM notes n
"""


def parse_tags(text) -> list:
    """'#ideas, Study  ,ideas' -> ['ideas', 'Study']  (no duplicates, max 20)."""
    seen, out = set(), []
    for raw in re.split(r"[,;\n]", text or ""):
        tag = raw.strip().lstrip("#").strip()
        if tag and len(tag) <= 40 and tag.lower() not in seen:
            seen.add(tag.lower())
            out.append(tag)
    return out[:20]


class MemoryManager:
    def __init__(self, db):
        self.db = db

    def save_note(self, title, body="", kind="note", important=False, tags=None, note_id=None) -> int:
        title = (title or "").strip()
        if not title:
            raise ValidationError("Please give it a title.")
        if len(title) > MAX_TITLE:
            raise ValidationError(f"The title is too long (max {MAX_TITLE} characters).")
        if kind not in ("note", "idea"):
            raise ValidationError("Type must be Note or Idea.")
        if len(body or "") > MAX_BODY:
            raise ValidationError("The text is too long.")
        tag_list = parse_tags(tags) if isinstance(tags, str) or tags is None else list(tags)

        with self.db.transaction() as c:
            if note_id is None:
                cur = c.execute(
                    "INSERT INTO notes(title, body, kind, is_important) VALUES(?, ?, ?, ?)",
                    (title, body or "", kind, int(important)))
                note_id, event = cur.lastrowid, "created"
            else:
                cur = c.execute(
                    "UPDATE notes SET title=?, body=?, kind=?, is_important=?, "
                    "updated_at=datetime('now','localtime') WHERE id=?",
                    (title, body or "", kind, int(important), note_id))
                if cur.rowcount == 0:
                    raise ValidationError("That note no longer exists.")
                event = "updated"
            c.execute("DELETE FROM note_tags WHERE note_id = ?", (note_id,))
            for tag in tag_list:
                c.execute("INSERT OR IGNORE INTO tags(name) VALUES(?)", (tag,))
                tag_id = c.execute("SELECT id FROM tags WHERE name = ?", (tag,)).fetchone()[0]
                c.execute("INSERT OR IGNORE INTO note_tags(note_id, tag_id) VALUES(?, ?)", (note_id, tag_id))
            c.execute("DELETE FROM tags WHERE id NOT IN (SELECT tag_id FROM note_tags)")
            self.db.log_conn(c, event, kind, note_id, f"{kind.capitalize()} {event}: {title}")
        return note_id

    def get_note(self, note_id: int):
        row = self.db.query_one(_SELECT + " WHERE n.id = ?", (note_id,))
        return Note.from_row(row) if row else None

    def delete_note(self, note_id: int) -> None:
        note = self.get_note(note_id)
        if note is None:
            return
        with self.db.transaction() as c:
            c.execute("DELETE FROM relations WHERE (source_type IN ('note','idea') AND source_id = ?) "
                      "OR (target_type IN ('note','idea') AND target_id = ?)", (note_id, note_id))
            c.execute("DELETE FROM notes WHERE id = ?", (note_id,))
            c.execute("DELETE FROM tags WHERE id NOT IN (SELECT tag_id FROM note_tags)")
            self.db.log_conn(c, "deleted", note.kind, note_id, f"{note.kind.capitalize()} deleted: {note.title}")

    def list_notes(self, query="", kind=None, important=False, tag=None, limit=300) -> list:
        where, params = [], []
        for term in (query or "").split()[:8]:
            p = like(term)
            where.append("(n.title LIKE ? ESCAPE '\\' OR n.body LIKE ? ESCAPE '\\' OR EXISTS ("
                         "SELECT 1 FROM note_tags nt JOIN tags t ON t.id = nt.tag_id "
                         "WHERE nt.note_id = n.id AND t.name LIKE ? ESCAPE '\\'))")
            params += [p, p, p]
        if kind in ("note", "idea"):
            where.append("n.kind = ?")
            params.append(kind)
        if important:
            where.append("n.is_important = 1")
        if tag:
            where.append("EXISTS (SELECT 1 FROM note_tags nt JOIN tags t ON t.id = nt.tag_id "
                         "WHERE nt.note_id = n.id AND t.name = ?)")
            params.append(tag)
        sql = _SELECT + (" WHERE " + " AND ".join(where) if where else "")
        sql += " ORDER BY n.updated_at DESC, n.id DESC LIMIT ?"
        return [Note.from_row(r) for r in self.db.query_all(sql, (*params, limit))]

    def all_tags(self) -> list:
        return [r["name"] for r in self.db.query_all("SELECT name FROM tags ORDER BY name COLLATE NOCASE")]
