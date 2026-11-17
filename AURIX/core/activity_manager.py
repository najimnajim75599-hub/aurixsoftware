"""Reads the activity timeline. Only actions done inside AURIX are ever recorded,
and recording can be switched off in Settings."""
from datetime import date, timedelta

# Filter name -> event types
FILTERS = {
    "All": None,
    "Files": ("indexed", "added", "removed", "updated:file"),
    "Projects": ("created:project", "completed:project", "updated:project", "deleted:project"),
    "Notes": ("created:note", "created:idea", "updated:note", "updated:idea", "deleted:note", "deleted:idea"),
    "Tasks": ("task_added", "task_done", "task_updated", "task_deleted"),
    "Connections": ("connected",),
}
RANGES = {"All time": None, "Today": 0, "Last 7 days": 7, "Last 30 days": 30}


def _matches(row, rules) -> bool:
    for rule in rules:
        ev, _, item = rule.partition(":")
        if row["event_type"] == ev and (not item or row["item_type"] == item):
            return True
    return False


class ActivityManager:
    def __init__(self, db):
        self.db = db

    def list(self, group="All", days_key="All time", limit=500) -> list:
        sql, params = "SELECT * FROM activity", []
        days = RANGES.get(days_key)
        if days is not None:
            since = (date.today() - timedelta(days=days)).isoformat()
            sql += " WHERE created_at >= ?"
            params.append(since)
        sql += " ORDER BY id DESC LIMIT ?"
        rows = self.db.query_all(sql, (*params, limit * 4 if FILTERS.get(group) else limit))
        rules = FILTERS.get(group)
        if rules:
            rows = [r for r in rows if _matches(r, rules)]
        return rows[:limit]

    def clear(self) -> None:
        self.db.execute("DELETE FROM activity")

    def set_recording(self, enabled: bool) -> None:
        self.db.execute("INSERT INTO settings(key, value) VALUES('record_activity', ?) "
                        "ON CONFLICT(key) DO UPDATE SET value = excluded.value", ("1" if enabled else "0",))
