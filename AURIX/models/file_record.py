from dataclasses import dataclass

from core.filetypes import group_of


@dataclass
class FileRecord:
    id: int
    path: str
    name: str
    extension: str
    size_bytes: int
    modified_at: str
    folder_id: int
    description: str
    tags: str
    last_opened_at: str

    @classmethod
    def from_row(cls, r) -> "FileRecord":
        return cls(r["id"], r["path"], r["name"], r["extension"], r["size_bytes"],
                   r["modified_at"] or "", r["folder_id"], r["description"],
                   r["tags"], r["last_opened_at"] or "")

    @property
    def group(self) -> str:
        return group_of(self.extension)

    @property
    def size_text(self) -> str:
        size = float(self.size_bytes)
        for unit in ("B", "KB", "MB", "GB"):
            if size < 1024 or unit == "GB":
                return f"{int(size)} B" if unit == "B" else f"{size:.1f} {unit}"
            size /= 1024
