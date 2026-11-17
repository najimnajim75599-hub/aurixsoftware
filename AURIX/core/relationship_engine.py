"""Connections between files, projects, notes, ideas and tasks (AURIX Connect).
Stored in the `relations` table. Also builds the data for the knowledge graph."""
import math

from core.errors import ValidationError

NODE_TYPES = ("file", "project", "note", "idea", "task")
MAX_GRAPH_NODES = 150


def _norm(t):
    return t if t in NODE_TYPES else None


class RelationshipEngine:
    def __init__(self, db):
        self.db = db

    # ---- looking up what a node is ----
    def node_info(self, ntype, nid):
        """dict(type, id, title, subtitle, detail) or None if it no longer exists."""
        q = self.db.query_one
        if ntype == "file":
            r = q("SELECT name, path, description, tags FROM files WHERE id=?", (nid,))
            if r:
                return dict(type=ntype, id=nid, title=r["name"], subtitle=r["path"],
                            detail=(r["description"] or "No description yet.") + (f"\nTags: {r['tags']}" if r["tags"] else ""))
        elif ntype == "project":
            r = q("SELECT p.name, p.description, p.status, (SELECT COUNT(*) FROM tasks t WHERE t.project_id=p.id) n, "
                  "(SELECT COUNT(*) FROM tasks t WHERE t.project_id=p.id AND t.status='done') d FROM projects p WHERE p.id=?", (nid,))
            if r:
                return dict(type=ntype, id=nid, title=r["name"], subtitle=f"{r['status'].replace('_', ' ').title()} · {r['d']}/{r['n']} tasks done",
                            detail=r["description"] or "No description yet.")
        elif ntype in ("note", "idea"):
            r = q("SELECT title, body, kind FROM notes WHERE id=?", (nid,))
            if r and r["kind"] == ntype:
                body = r["body"].strip()
                return dict(type=ntype, id=nid, title=r["title"], subtitle=r["kind"].capitalize(),
                            detail=(body[:400] + ("…" if len(body) > 400 else "")) or "(empty)")
        elif ntype == "task":
            r = q("SELECT t.title, t.status, t.deadline, p.name FROM tasks t JOIN projects p ON p.id=t.project_id WHERE t.id=?", (nid,))
            if r:
                due = f" · due {r['deadline']}" if r["deadline"] else ""
                return dict(type=ntype, id=nid, title=r["title"], subtitle=f"Task in {r['name']} · {r['status']}{due}", detail="")
        return None

    def candidates(self, ntype, query="", limit=200) -> list:
        """(id, title) pairs of one type, for pickers."""
        from core.database import like
        p = like(query or "")
        if ntype == "file":
            rows = self.db.query_all("SELECT id, name AS t FROM files WHERE name LIKE ? ESCAPE '\\' OR description LIKE ? ESCAPE '\\' "
                                     "ORDER BY name LIMIT ?", (p, p, limit))
        elif ntype == "project":
            rows = self.db.query_all("SELECT id, name AS t FROM projects WHERE name LIKE ? ESCAPE '\\' ORDER BY name LIMIT ?", (p, limit))
        elif ntype in ("note", "idea"):
            rows = self.db.query_all("SELECT id, title AS t FROM notes WHERE kind=? AND title LIKE ? ESCAPE '\\' "
                                     "ORDER BY updated_at DESC LIMIT ?", (ntype, p, limit))
        elif ntype == "task":
            rows = self.db.query_all("SELECT t.id, p.name || ' › ' || t.title AS t FROM tasks t JOIN projects p ON p.id=t.project_id "
                                     "WHERE t.title LIKE ? ESCAPE '\\' ORDER BY t.id DESC LIMIT ?", (p, limit))
        else:
            return []
        return [(r["id"], r["t"]) for r in rows]

    # ---- connections ----
    def connect(self, a_type, a_id, b_type, b_id, label="") -> int:
        if not _norm(a_type) or not _norm(b_type):
            raise ValidationError("Unknown item type.")
        if (a_type, a_id) == (b_type, b_id):
            raise ValidationError("An item cannot be connected to itself.")
        a, b = self.node_info(a_type, a_id), self.node_info(b_type, b_id)
        if not a or not b:
            raise ValidationError("One of the items no longer exists.")
        if self._existing(a_type, a_id, b_type, b_id):
            raise ValidationError("These two items are already connected.")
        label = (label or "").strip()[:60]
        with self.db.transaction() as c:
            rid = c.execute("INSERT INTO relations(source_type, source_id, target_type, target_id, label) VALUES(?,?,?,?,?)",
                            (a_type, a_id, b_type, b_id, label)).lastrowid
            self.db.log_conn(c, "connected", a_type, a_id, f"Connected “{a['title']}” with “{b['title']}”")
        return rid

    def _existing(self, a_type, a_id, b_type, b_id):
        return self.db.query_one(
            "SELECT id FROM relations WHERE (source_type=? AND source_id=? AND target_type=? AND target_id=?) "
            "OR (source_type=? AND source_id=? AND target_type=? AND target_id=?)",
            (a_type, a_id, b_type, b_id, b_type, b_id, a_type, a_id))

    def disconnect(self, relation_id: int) -> None:
        self.db.execute("DELETE FROM relations WHERE id = ?", (relation_id,))

    def links_for(self, ntype, nid) -> list:
        """Everything connected to one node: list of dict(relation_id, label, other=node_info)."""
        out = []
        rows = self.db.query_all(
            "SELECT * FROM relations WHERE (source_type=? AND source_id=?) OR (target_type=? AND target_id=?) ORDER BY id DESC",
            (ntype, nid, ntype, nid))
        for r in rows:
            if (r["source_type"], r["source_id"]) == (ntype, nid):
                other = self.node_info(r["target_type"], r["target_id"])
            else:
                other = self.node_info(r["source_type"], r["source_id"])
            if other:
                out.append(dict(relation_id=r["id"], label=r["label"], other=other))
        return out

    def prune(self) -> int:
        """Delete connections whose items no longer exist (e.g. a file removed from the index)."""
        removed = 0
        for r in self.db.query_all("SELECT * FROM relations"):
            if not (self.node_info(r["source_type"], r["source_id"]) and self.node_info(r["target_type"], r["target_id"])):
                self.disconnect(r["id"])
                removed += 1
        return removed

    # ---- graph data ----
    def graph(self, include_unlinked=True):
        """Returns (nodes, edges). nodes: {(type,id): dict(title,type,x,y)}; edges: [(a_key, b_key, label)].
        Projects and notes/ideas always show; files and tasks show once connected to something.
        A task is also drawn linked to its own project."""
        self.prune()
        keys = []
        edges = []

        def add(k):
            if k not in keys and len(keys) < MAX_GRAPH_NODES:
                keys.append(k)
            return k in keys

        for r in self.db.query_all("SELECT * FROM relations ORDER BY id"):
            a, b = (r["source_type"], r["source_id"]), (r["target_type"], r["target_id"])
            if add(a) and add(b):
                edges.append((a, b, r["label"]))
        if include_unlinked:
            for r in self.db.query_all("SELECT id FROM projects ORDER BY updated_at DESC"):
                add(("project", r["id"]))
            for r in self.db.query_all("SELECT id, kind FROM notes ORDER BY updated_at DESC LIMIT 60"):
                add((r["kind"], r["id"]))
        for t in [k for k in keys if k[0] == "task"]:
            row = self.db.query_one("SELECT project_id FROM tasks WHERE id=?", (t[1],))
            if row and add(("project", row["project_id"])):
                edges.append((("project", row["project_id"]), t, "has task"))
        nodes = {}
        for k in keys:
            info = self.node_info(*k)
            if info:
                nodes[k] = dict(type=k[0], id=k[1], title=info["title"])
        edges = [e for e in edges if e[0] in nodes and e[1] in nodes]
        layout(nodes, edges)
        return nodes, edges


def layout(nodes, edges, iterations=120):
    """Small force-directed layout (pure Python, fine for ~150 nodes). Fills node['x'], node['y']."""
    keys = list(nodes)
    n = len(keys)
    if n == 0:
        return
    pos = {}
    for i, k in enumerate(keys):  # start on a circle so results are stable
        ang = 2 * math.pi * i / n
        pos[k] = [math.cos(ang) * 250, math.sin(ang) * 250]
    idx = {k: i for i, k in enumerate(keys)}
    for step in range(iterations):
        force = {k: [0.0, 0.0] for k in keys}
        for i in range(n):
            for j in range(i + 1, n):
                a, b = keys[i], keys[j]
                dx, dy = pos[a][0] - pos[b][0], pos[a][1] - pos[b][1]
                d2 = max(dx * dx + dy * dy, 25.0)
                f = 14000.0 / d2
                d = math.sqrt(d2)
                force[a][0] += dx / d * f; force[a][1] += dy / d * f
                force[b][0] -= dx / d * f; force[b][1] -= dy / d * f
        for a, b, _ in edges:
            dx, dy = pos[b][0] - pos[a][0], pos[b][1] - pos[a][1]
            d = max(math.hypot(dx, dy), 1.0)
            f = (d - 140.0) * 0.04
            force[a][0] += dx / d * f; force[a][1] += dy / d * f
            force[b][0] -= dx / d * f; force[b][1] -= dy / d * f
        cool = 1.0 - step / iterations
        for k in keys:
            pos[k][0] += max(-20, min(20, force[k][0])) * cool
            pos[k][1] += max(-20, min(20, force[k][1])) * cool
            pos[k][0] *= 0.995; pos[k][1] *= 0.995
    for k in keys:
        nodes[k]["x"], nodes[k]["y"] = pos[k]
