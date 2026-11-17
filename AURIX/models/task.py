from dataclasses import dataclass
from datetime import date


@dataclass
class Task:
    id: int
    project_id: int
    title: str
    status: str
    deadline: str
    created_at: str
    completed_at: str

    @classmethod
    def from_row(cls, r) -> "Task":
        return cls(r["id"], r["project_id"], r["title"], r["status"], r["deadline"] or "",
                   r["created_at"], r["completed_at"] or "")

    @property
    def overdue(self) -> bool:
        return bool(self.deadline) and self.status != "done" and self.deadline < date.today().isoformat()
