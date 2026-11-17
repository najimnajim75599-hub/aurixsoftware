"""Projects and tasks (AURIX Flow). No UI code here."""
from datetime import date

from core.database import like
from core.errors import ValidationError
from models.project import Project
from models.task import Task

PROJECT_STATUSES = ("not_started", "in_progress", "done")
TASK_STATUSES = ("todo", "doing", "done")
STATUS_LABELS = {"not_started": "Not started", "in_progress": "In progress", "done": "Done",
                 "todo": "To do", "doing": "Doing"}

_SELECT = """
SELECT p.*, (SELECT COUNT(*) FROM tasks t WHERE t.project_id = p.id) AS total_tasks,
       (SELECT COUNT(*) FROM tasks t WHERE t.project_id = p.id AND t.status = 'done') AS done_tasks
FROM projects p
"""


def check_deadline(text) -> str | None:
    """'' -> None. 'YYYY-MM-DD' -> same text. Anything else -> ValidationError."""
    text = (text or "").strip()
    if not text:
        return None
    try:
        return date.fromisoformat(text).isoformat()
    except ValueError:
        raise ValidationError("The deadline must look like 2026-12-31.")


class ProjectManager:
    def __init__(self, db):
        self.db = db

    # ---- projects ----
    def save_project(self, name, description="", status="not_started", project_id=None) -> int:
        name = (name or "").strip()
        if not name:
            raise ValidationError("Please give the project a name.")
        if len(name) > 200:
            raise ValidationError("The project name is too long (max 200 characters).")
        if len(description or "") > 20_000:
            raise ValidationError("The description is too long.")
        if status not in PROJECT_STATUSES:
            raise ValidationError("Unknown project status.")
        with self.db.transaction() as c:
            if project_id is None:
                project_id = c.execute("INSERT INTO projects(name, description, status) VALUES(?, ?, ?)",
                                       (name, description or "", status)).lastrowid
                self.db.log_conn(c, "created", "project", project_id, f"Project created: {name}")
            else:
                old = c.execute("SELECT status FROM projects WHERE id = ?", (project_id,)).fetchone()
                if old is None:
                    raise ValidationError("That project no longer exists.")
                c.execute("UPDATE projects SET name=?, description=?, status=?, "
                          "updated_at=datetime('now','localtime') WHERE id=?",
                          (name, description or "", status, project_id))
                event = "completed" if status == "done" and old["status"] != "done" else "updated"
                self.db.log_conn(c, event, "project", project_id, f"Project {event}: {name}")
        return project_id

    def get_project(self, project_id):
        row = self.db.query_one(_SELECT + " WHERE p.id = ?", (project_id,))
        return Project.from_row(row) if row else None

    def list_projects(self, query="", status=None, limit=300) -> list:
        where, params = [], []
        for term in (query or "").split()[:6]:
            where.append("(p.name LIKE ? ESCAPE '\\' OR p.description LIKE ? ESCAPE '\\')")
            params += [like(term)] * 2
        if status in PROJECT_STATUSES:
            where.append("p.status = ?")
            params.append(status)
        sql = _SELECT + (" WHERE " + " AND ".join(where) if where else "") + " ORDER BY p.updated_at DESC, p.id DESC LIMIT ?"
        return [Project.from_row(r) for r in self.db.query_all(sql, (*params, limit))]

    def delete_project(self, project_id: int) -> None:
        p = self.get_project(project_id)
        if p is None:
            return
        task_ids = [r["id"] for r in self.db.query_all("SELECT id FROM tasks WHERE project_id = ?", (project_id,))]
        with self.db.transaction() as c:
            for tid in task_ids:
                c.execute("DELETE FROM relations WHERE (source_type='task' AND source_id=?) "
                          "OR (target_type='task' AND target_id=?)", (tid, tid))
            c.execute("DELETE FROM relations WHERE (source_type='project' AND source_id=?) "
                      "OR (target_type='project' AND target_id=?)", (project_id, project_id))
            c.execute("DELETE FROM projects WHERE id = ?", (project_id,))  # tasks cascade
            self.db.log_conn(c, "deleted", "project", None, f"Project deleted: {p.name}")

    # ---- tasks ----
    def add_task(self, project_id, title, deadline="") -> int:
        title = (title or "").strip()
        if not title:
            raise ValidationError("Please type a task title.")
        if len(title) > 300:
            raise ValidationError("The task title is too long (max 300 characters).")
        dl = check_deadline(deadline)
        p = self.get_project(project_id)
        if p is None:
            raise ValidationError("That project no longer exists.")
        with self.db.transaction() as c:
            tid = c.execute("INSERT INTO tasks(project_id, title, deadline) VALUES(?, ?, ?)",
                            (project_id, title, dl)).lastrowid
            c.execute("UPDATE projects SET updated_at=datetime('now','localtime') WHERE id=?", (project_id,))
            self.db.log_conn(c, "task_added", "project", project_id, f"Task added to {p.name}: {title}")
        return tid

    def get_task(self, task_id):
        row = self.db.query_one("SELECT * FROM tasks WHERE id = ?", (task_id,))
        return Task.from_row(row) if row else None

    def list_tasks(self, project_id) -> list:
        rows = self.db.query_all(
            "SELECT * FROM tasks WHERE project_id = ? ORDER BY (status = 'done'), "
            "deadline IS NULL, deadline, id", (project_id,))
        return [Task.from_row(r) for r in rows]

    def set_task_status(self, task_id, status) -> None:
        if status not in TASK_STATUSES:
            raise ValidationError("Unknown task status.")
        t = self.get_task(task_id)
        if t is None:
            raise ValidationError("That task no longer exists.")
        p = self.get_project(t.project_id)
        with self.db.transaction() as c:
            c.execute("UPDATE tasks SET status=?, completed_at=CASE WHEN ?='done' THEN datetime('now','localtime') "
                      "ELSE NULL END WHERE id=?", (status, status, task_id))
            c.execute("UPDATE projects SET updated_at=datetime('now','localtime') WHERE id=?", (t.project_id,))
            if status == "done" and t.status != "done":
                self.db.log_conn(c, "task_done", "project", t.project_id, f"Task completed in {p.name}: {t.title}")
            elif status != t.status:
                self.db.log_conn(c, "task_updated", "project", t.project_id,
                                 f"Task moved to {STATUS_LABELS[status]} in {p.name}: {t.title}")

    def set_task_deadline(self, task_id, deadline) -> None:
        dl = check_deadline(deadline)
        self.db.execute("UPDATE tasks SET deadline = ? WHERE id = ?", (dl, task_id))

    def delete_task(self, task_id: int) -> None:
        t = self.get_task(task_id)
        if t is None:
            return
        with self.db.transaction() as c:
            c.execute("DELETE FROM relations WHERE (source_type='task' AND source_id=?) "
                      "OR (target_type='task' AND target_id=?)", (task_id, task_id))
            c.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
            self.db.log_conn(c, "task_deleted", "project", t.project_id, f"Task deleted: {t.title}")

    # ---- history ----
    def history(self, project_id, limit=100) -> list:
        return self.db.query_all(
            "SELECT * FROM activity WHERE item_type = 'project' AND item_id = ? ORDER BY id DESC LIMIT ?",
            (project_id, limit))
