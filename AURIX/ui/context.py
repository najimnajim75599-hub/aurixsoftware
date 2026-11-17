from dataclasses import dataclass
from typing import Any


@dataclass
class AppContext:
    """Everything the screens need, passed in one object."""
    db: Any
    memory: Any
    files: Any
    search: Any
    notifier: Any
    indexing: Any
    projects: Any
    relations: Any
    activity: Any
