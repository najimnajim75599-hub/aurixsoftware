from dataclasses import dataclass


@dataclass
class Project:
    id: int
    name: str
    description: str
    status: str
    created_at: str
    updated_at: str
    total_tasks: int = 0
    done_tasks: int = 0

    @classmethod
    def from_row(cls, r) -> "Project":
        keys = r.keys()
        return cls(r["id"], r["name"], r["description"], r["status"], r["created_at"], r["updated_at"],
                   r["total_tasks"] if "total_tasks" in keys else 0,
                   r["done_tasks"] if "done_tasks" in keys else 0)

    @property
    def progress(self) -> int:
        """Percent of tasks that are done (0 when there are no tasks)."""
        return round(100 * self.done_tasks / self.total_tasks) if self.total_tasks else 0
