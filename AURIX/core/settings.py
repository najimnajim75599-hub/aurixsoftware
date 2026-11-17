"""App-wide constants, file locations and persistent user settings."""
import json
import os
import sys
from pathlib import Path

APP_NAME = "AURIX"
APP_VERSION = "1.0.0"
TAGLINE = "Your World, Connected."

# Brand colours
OBSIDIAN = "#080808"
CRIMSON = "#780D18"
SIGNAL_RED = "#C51F32"
TITANIUM = "#C5C5C5"
WHITE = "#FFFFFF"


def project_root() -> Path:
    """Folder that contains assets/. Works from source and from a PyInstaller build."""
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    return Path(__file__).resolve().parent.parent


def asset_path(*parts: str) -> Path:
    return project_root().joinpath("assets", *parts)


def app_data_dir() -> Path:
    """Where AURIX keeps its database. Windows: %APPDATA%\\AURIX"""
    base = os.environ.get("APPDATA")
    folder = Path(base) / APP_NAME if base else Path.home() / ".aurix"
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def config_path() -> Path:
    return app_data_dir() / "config.json"


def default_db_path() -> Path:
    """The database location. Normally %APPDATA%\\AURIX\\aurix.db; the user can move it in Settings."""
    try:
        custom = json.loads(config_path().read_text(encoding="utf-8")).get("db_path")
        if custom and Path(custom).parent.is_dir():
            return Path(custom)
    except (OSError, ValueError):
        pass
    return app_data_dir() / "aurix.db"


def set_custom_db_path(path) -> None:
    config_path().write_text(json.dumps({"db_path": str(path)}), encoding="utf-8")


def reset_custom_db_path() -> None:
    try:
        config_path().unlink()
    except OSError:
        pass


class AppSettings:
    """Small key/value store backed by the `settings` table."""

    def __init__(self, db):
        self.db = db

    def get(self, key: str, default: str = "") -> str:
        row = self.db.query_one("SELECT value FROM settings WHERE key = ?", (key,))
        return row["value"] if row else default

    def set(self, key: str, value: str) -> None:
        self.db.execute(
            "INSERT INTO settings(key, value) VALUES(?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, str(value)),
        )
