"""Keyword search over indexed files and notes.

This is honest keyword search: it splits your sentence into words, ignores filler
words, understands a few type words ("slides" -> .pptx) and ranks results by how many
words matched file names, your descriptions, tags and notes linked to the file.
It is not AI. The SearchEngine class is the one place a local semantic engine can be
plugged in later."""
import re
from dataclasses import dataclass

from core.database import like
from core.filetypes import ALL_KNOWN, GROUPS, extensions_for_word, group_of
from models.file_record import FileRecord

STOPWORDS = {
    "find", "show", "me", "my", "the", "a", "an", "i", "created", "made", "for", "about", "of",
    "on", "in", "to", "and", "with", "that", "is", "are", "file", "files", "all", "from", "was",
    "have", "has", "did", "which", "where", "what", "some", "any", "please", "give", "get", "it",
}

LINKED_NOTE = ("EXISTS (SELECT 1 FROM relations r JOIN notes n ON n.id = "
               "CASE WHEN r.source_type = 'file' THEN r.target_id ELSE r.source_id END "
               "WHERE ((r.source_type = 'file' AND r.source_id = f.id AND r.target_type IN ('note','idea')) "
               "OR (r.target_type = 'file' AND r.target_id = f.id AND r.source_type IN ('note','idea'))) "
               "AND (n.title LIKE ? ESCAPE '\\' OR n.body LIKE ? ESCAPE '\\'))")


@dataclass
class SearchResult:
    kind: str       # 'file' | 'note' | 'idea'
    id: int
    title: str
    subtitle: str
    score: int = 0


def extract_terms(query: str) -> list:
    out = []
    for w in re.findall(r"[\w.\-]+", (query or "").lower()):
        w = w.strip(".-")
        if len(w) >= 2 and w not in STOPWORDS and w not in out:
            out.append(w)
    return out[:8]


class SearchEngine:
    def __init__(self, db):
        self.db = db

    def search(self, query="", scope="all", group=None, folder_id=None, limit=200) -> list:
        terms = extract_terms(query)
        results = []
        if scope in ("all", "files"):
            results += self._files(terms, group, folder_id, limit)
        if scope in ("all", "notes") and terms and not group and not folder_id:
            results += self._notes(terms, limit)
        results.sort(key=lambda r: -r.score)
        return results[:limit]

    def _files(self, terms, group, folder_id, limit):
        parts, sel_params = [], []
        for t in terms:
            p = like(t)
            clause = ("f.name LIKE ? ESCAPE '\\' OR f.description LIKE ? ESCAPE '\\' OR "
                      "f.tags LIKE ? ESCAPE '\\' OR f.path LIKE ? ESCAPE '\\' OR " + LINKED_NOTE)
            sel_params += [p, p, p, p, p, p]
            exts = sorted(extensions_for_word(t))
            if exts:
                clause += f" OR f.extension IN ({','.join('?' * len(exts))})"
                sel_params += exts
            parts.append(f"(CASE WHEN ({clause}) THEN 1 ELSE 0 END)")
        where, params = ["1 = 1"], []
        if group == "Other":
            where.append(f"f.extension NOT IN ({','.join('?' * len(ALL_KNOWN))})")
            params += sorted(ALL_KNOWN)
        elif group in GROUPS:
            where.append(f"f.extension IN ({','.join('?' * len(GROUPS[group]))})")
            params += sorted(GROUPS[group])
        if folder_id:
            where.append("f.folder_id = ?")
            params.append(folder_id)
        score = " + ".join(parts) if parts else "0"
        sql = (f"SELECT * FROM (SELECT f.*, ({score}) AS score FROM files f WHERE {' AND '.join(where)}) "
               + ("WHERE score > 0 " if terms else "")
               + "ORDER BY score DESC, modified_at DESC LIMIT ?")
        out = []
        for row in self.db.query_all(sql, (*sel_params, *params, limit)):
            f = FileRecord.from_row(row)
            parent = f.path.replace("\\", "/").rsplit("/", 2)
            where_txt = parent[-2] if len(parent) >= 2 else ""
            out.append(SearchResult("file", f.id, f.name, f"{f.group} · {f.size_text} · {where_txt}", row["score"]))
        return out

    def _notes(self, terms, limit):
        parts, params = [], []
        for t in terms:
            p = like(t)
            parts.append("(CASE WHEN (n.title LIKE ? ESCAPE '\\' OR n.body LIKE ? ESCAPE '\\' OR EXISTS ("
                         "SELECT 1 FROM note_tags nt JOIN tags g ON g.id = nt.tag_id "
                         "WHERE nt.note_id = n.id AND g.name LIKE ? ESCAPE '\\')) THEN 1 ELSE 0 END)")
            params += [p, p, p]
        sql = (f"SELECT * FROM (SELECT n.id, n.title, n.kind, n.updated_at, ({' + '.join(parts)}) AS score "
               "FROM notes n) WHERE score > 0 ORDER BY score DESC, updated_at DESC LIMIT ?")
        return [SearchResult(r["kind"], r["id"], r["title"], f"{r['kind'].capitalize()} · {r['updated_at'][:10]}", r["score"])
                for r in self.db.query_all(sql, (*params, limit))]
