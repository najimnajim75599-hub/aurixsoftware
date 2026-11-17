"""AURIX entry point. Run with:  python main.py"""
import sys

from PySide6.QtWidgets import QApplication, QMessageBox

from core.activity_manager import ActivityManager
from core.database import Database
from core.file_indexer import FileManager
from core.memory_manager import MemoryManager
from core.project_manager import ProjectManager
from core.relationship_engine import RelationshipEngine
from core.search_engine import SearchEngine
from core.settings import APP_NAME, asset_path, default_db_path
from services.indexing_service import IndexingService
from services.notification_service import NotificationService
from ui.context import AppContext
from ui.main_window import MainWindow


def load_stylesheet(app: QApplication) -> None:
    qss = asset_path("styles", "aurix.qss")
    try:
        app.setStyleSheet(qss.read_text(encoding="utf-8"))
    except OSError as exc:
        print(f"Warning: could not load stylesheet {qss}: {exc}")


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    load_stylesheet(app)
    db_path = default_db_path()
    try:
        db = Database(db_path)
    except Exception as exc:
        QMessageBox.critical(None, APP_NAME, f"AURIX could not open its database:\n{exc}")
        return 1
    ctx = AppContext(db=db, memory=MemoryManager(db), files=FileManager(db), search=SearchEngine(db),
                     notifier=NotificationService(), indexing=IndexingService(db_path),
                     projects=ProjectManager(db), relations=RelationshipEngine(db), activity=ActivityManager(db))
    window = MainWindow(ctx)
    window.show()
    code = app.exec()
    db.close()
    return code


if __name__ == "__main__":
    sys.exit(main())
