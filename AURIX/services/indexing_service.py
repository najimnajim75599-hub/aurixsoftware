"""Runs folder indexing in a background thread so the window never freezes."""
from PySide6.QtCore import QObject, QThread, Signal

from core.database import Database
from core.file_indexer import index_folder


class IndexWorker(QThread):
    progress = Signal(int, str)       # files seen so far, folder path
    completed = Signal(int, bool)     # total files, stopped early?
    failed = Signal(str)

    def __init__(self, db_path, folders):
        super().__init__()
        self.db_path, self.folders = db_path, folders

    def run(self):
        db = None
        try:
            db = Database(self.db_path)  # each thread uses its own connection
            total, stopped = 0, False
            for folder_id, path in self.folders:
                if self.isInterruptionRequested():
                    stopped = True
                    break
                n, stopped = index_folder(db, folder_id, path, self.isInterruptionRequested,
                                          lambda c, p=path: self.progress.emit(total + c, p))
                total += n
                if stopped:
                    break
            self.completed.emit(total, stopped)
        except Exception as exc:
            self.failed.emit(str(exc))
        finally:
            if db:
                db.close()


class IndexingService(QObject):
    progress = Signal(int, str)
    completed = Signal(int, bool)
    failed = Signal(str)
    state_changed = Signal(bool)

    def __init__(self, db_path):
        super().__init__()
        self.db_path, self.worker = db_path, None

    @property
    def running(self) -> bool:
        return self.worker is not None and self.worker.isRunning()

    def start(self, folders) -> bool:
        if self.running or not folders:
            return False
        self.worker = IndexWorker(self.db_path, folders)
        self.worker.progress.connect(self.progress)
        self.worker.completed.connect(self._done)
        self.worker.failed.connect(self._failed)
        self.worker.start()
        self.state_changed.emit(True)
        return True

    def stop(self, wait=False):
        if self.running:
            self.worker.requestInterruption()
            if wait:
                self.worker.wait(5000)

    def _done(self, total, stopped):
        self.state_changed.emit(False)
        self.completed.emit(total, stopped)

    def _failed(self, msg):
        self.state_changed.emit(False)
        self.failed.emit(msg)
