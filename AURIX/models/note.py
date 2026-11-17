from dataclasses import dataclass, field


@dataclass
class Note:
    id: int
    title: str
    body: str
    kind: str
    is_important: bool
    created_at: str
    updated_at: str
    tags: list = field(default_factory=list)

    @classmethod
    def from_row(cls, row) -> "Note":
        tag_list = row["tag_list"] if "tag_list" in row.keys() else ""
        return cls(row["id"], row["title"], row["body"], row["kind"],
                   bool(row["is_important"]), row["created_at"], row["updated_at"],
                   [t for t in tag_list.split(",") if t])
