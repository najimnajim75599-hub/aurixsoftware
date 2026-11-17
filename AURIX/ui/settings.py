"""Settings: appearance, data location, indexed folders, privacy, backup/restore, about."""
import platform
import sqlite3
from pathlib import Path

from PySide6 import __version__ as PYSIDE_VERSION
from PySide6.QtCore import Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (QCheckBox, QFileDialog, QHBoxLayout, QInputDialog, QLabel,
                               QListWidget, QListWidgetItem, QMessageBox, QPushButton)

from core.errors import ValidationError
from core.settings import (APP_NAME, APP_VERSION, TAGLINE, app_data_dir,
                           reset_custom_db_path, set_custom_db_path)
from services import backup_service
from ui.base_page import BasePage, make_card


def _label(text, name="CardText"):
    lab = QLabel(text)
    lab.setObjectName(name)
    lab.setWordWrap(True)
    lab.setTextInteractionFlags(Qt.TextSelectableByMouse)
    return lab


class SettingsPage(BasePage):
    data_replaced = Signal()   # emitted after restore / erase so every page reloads

    def __init__(self, ctx, parent=None):
        super().__init__("Settings", "Appearance, privacy and your data", parent)
        self.ctx = ctx

        # ---- appearance ----
        card, c = make_card("Appearance")
        c.addWidget(_label("AURIX Light: the official white, black and dark-red branding. "
                           "More themes may come in a later version."))
        self.body.addWidget(card)

        # ---- data location ----
        card, c = make_card("Data storage")
        c.addWidget(_label("Everything you save lives in one database file on this computer. Nothing is uploaded."))
        self.path_label = _label("")
        c.addWidget(self.path_label)
        row = QHBoxLayout()
        self.open_folder_btn = QPushButton("Open folder")
        self.move_btn = QPushButton("Move database…")
        self.default_btn = QPushButton("Use default location")
        self.open_folder_btn.clicked.connect(self._open_data_folder)
        self.move_btn.clicked.connect(self._move_db)
        self.default_btn.clicked.connect(self._use_default)
        for b in (self.open_folder_btn, self.move_btn, self.default_btn):
            row.addWidget(b)
        row.addStretch(1)
        c.addLayout(row)
        self.body.addWidget(card)

        # ---- indexed folders ----
        card, c = make_card("Indexed folders")
        c.addWidget(_label("AURIX only reads file names, sizes and dates in folders you added. "
                           "Add folders in Find. You can skip or remove them here."))
        self.folders = QListWidget()
        self.folders.setObjectName("ItemList")
        self.folders.setFixedHeight(110)
        self.folders.currentItemChanged.connect(lambda *_: self._update_folder_buttons())
        c.addWidget(self.folders)
        row = QHBoxLayout()
        self.skip_btn = QPushButton("Skip / include")
        self.remove_btn = QPushButton("Remove folder")
        self.remove_btn.setObjectName("Danger")
        self.skip_btn.clicked.connect(self._toggle_folder)
        self.remove_btn.clicked.connect(self._remove_folder)
        row.addWidget(self.skip_btn)
        row.addWidget(self.remove_btn)
        row.addStretch(1)
        c.addLayout(row)
        self.body.addWidget(card)

        # ---- privacy ----
        card, c = make_card("Privacy")
        c.addWidget(_label("AURIX never scans your computer on its own, never opens your files, and never sends "
                           "anything over the internet. You decide what is recorded and you can delete it at any time."))
        self.record_check = QCheckBox("Record my actions in the Activity timeline")
        self.record_check.toggled.connect(self._toggle_recording)
        c.addWidget(self.record_check)
        row = QHBoxLayout()
        self.clear_btn = QPushButton("Clear activity log")
        self.erase_btn = QPushButton("Delete all my data…")
        self.erase_btn.setObjectName("Danger")
        self.clear_btn.clicked.connect(self._clear_activity)
        self.erase_btn.clicked.connect(self._erase_all)
        row.addWidget(self.clear_btn)
        row.addWidget(self.erase_btn)
        row.addStretch(1)
        c.addLayout(row)
        self.body.addWidget(card)

        # ---- backup ----
        card, c = make_card("Backup and restore")
        c.addWidget(_label("Save a copy of everything (notes, projects, connections, file index, activity) "
                           "to a file you choose, for example on a USB drive. Restoring replaces your current data, "
                           "but AURIX first saves your current data next to the database so you can undo it."))
        row = QHBoxLayout()
        self.backup_btn = QPushButton("Create backup…")
        self.backup_btn.setObjectName("Primary")
        self.restore_btn = QPushButton("Restore from backup…")
        self.backup_btn.clicked.connect(self._backup)
        self.restore_btn.clicked.connect(self._restore)
        row.addWidget(self.backup_btn)
        row.addWidget(self.restore_btn)
        row.addStretch(1)
        c.addLayout(row)
        self.body.addWidget(card)

        # ---- about ----
        card, c = make_card("About")
        self.about = _label("")
        c.addWidget(self.about)
        self.body.addWidget(card)

    # ---------- refresh ----------
    def refresh(self) -> None:
        db = self.ctx.db
        self.path_label.setText(f"Database: {db.path}")
        self.default_btn.setEnabled(Path(db.path) != app_data_dir() / "aurix.db")
        self.record_check.blockSignals(True)
        self.record_check.setChecked(db.activity_enabled())
        self.record_check.blockSignals(False)
        self.folders.clear()
        for f in self.ctx.files.list_folders():
            state = "skipped" if f["paused"] else f"{f['file_count']} files"
            item = QListWidgetItem(f"{f['path']}\n{state}")
            item.setData(Qt.UserRole, f["id"])
            self.folders.addItem(item)
        self._update_folder_buttons()
        counts = db.table_counts()
        try:
            size = Path(db.path).stat().st_size / 1024
        except OSError:
            size = 0
        self.about.setText(
            f"{APP_NAME} {APP_VERSION}  ·  {TAGLINE}\n"
            f"Notes & ideas: {counts['notes']}   Projects: {counts['projects']}   Tasks: {counts['tasks']}   "
            f"Files indexed: {counts['files']}   Connections: {counts['relations']}\n"
            f"Database size: {size:.0f} KB   ·   Schema v{db.schema_version}\n"
            f"Python {platform.python_version()}  ·  PySide6 {PYSIDE_VERSION}  ·  SQLite {sqlite3.sqlite_version}\n"
            "AURIX is free software for personal use and works fully offline.")

    # ---------- data location ----------
    def _open_data_folder(self):
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(Path(self.ctx.db.path).parent)))

    def _move_db(self):
        if self._indexing_busy():
            return
        folder = QFileDialog.getExistingDirectory(self, "Choose the new folder for your AURIX database")
        if not folder:
            return
        target = Path(folder) / "aurix.db"
        if target.exists():
            QMessageBox.warning(self, APP_NAME, f"{target} already exists. Choose an empty folder.")
            return
        try:
            backup_service.backup_to(self.ctx.db, target)
            set_custom_db_path(target)
        except (OSError, ValidationError, sqlite3.Error) as exc:
            self.ctx.notifier.error(f"Could not move the database: {exc}")
            return
        QMessageBox.information(self, APP_NAME, "Your data was copied to the new location.\n\n"
                                "Please close and reopen AURIX to start using it. The old file was left in place; "
                                "delete it yourself once you have checked everything works.")

    def _use_default(self):
        if self._indexing_busy():
            return
        default = app_data_dir() / "aurix.db"
        if default.exists():
            QMessageBox.warning(self, APP_NAME, f"A database already exists at {default}.\n"
                                "Restore from a backup instead, or move that file away first.")
            return
        try:
            backup_service.backup_to(self.ctx.db, default)
            reset_custom_db_path()
        except (OSError, ValidationError, sqlite3.Error) as exc:
            self.ctx.notifier.error(f"Could not move the database: {exc}")
            return
        QMessageBox.information(self, APP_NAME, "Your data was copied to the default location.\n"
                                "Please close and reopen AURIX.")

    # ---------- folders ----------
    def _selected_folder(self):
        item = self.folders.currentItem()
        return item.data(Qt.UserRole) if item else None

    def _update_folder_buttons(self):
        has = self._selected_folder() is not None
        self.skip_btn.setEnabled(has)
        self.remove_btn.setEnabled(has)

    def _toggle_folder(self):
        fid = self._selected_folder()
        if fid is None or self._indexing_busy():
            return
        row = next((f for f in self.ctx.files.list_folders() if f["id"] == fid), None)
        if row:
            self.ctx.files.set_paused(fid, not row["paused"])
            self.refresh()

    def _remove_folder(self):
        fid = self._selected_folder()
        if fid is None or self._indexing_busy():
            return
        if QMessageBox.question(self, "Remove folder?", "Remove this folder from AURIX? Your files on disk are not touched, "
                                "but their index entries, descriptions and tags are deleted.") == QMessageBox.Yes:
            self.ctx.files.remove_folder(fid)
            self.refresh()
            self.data_replaced.emit()

    # ---------- privacy ----------
    def _toggle_recording(self, checked):
        self.ctx.activity.set_recording(checked)
        self.ctx.notifier.info("Activity recording is on" if checked else "Activity recording is paused")

    def _clear_activity(self):
        if QMessageBox.question(self, "Clear activity", "Delete the whole activity timeline? Your notes and projects stay.") == QMessageBox.Yes:
            self.ctx.activity.clear()
            self.ctx.notifier.success("Activity cleared")

    def _erase_all(self):
        if self._indexing_busy():
            return
        text, ok = QInputDialog.getText(self, "Delete all my data",
                                        "This permanently deletes every note, idea, project, task, connection, "
                                        "indexed file entry and activity record.\nYour real files on disk are not touched.\n\n"
                                        "Tip: create a backup first.\n\nType DELETE to confirm:")
        if not ok or text.strip() != "DELETE":
            if ok:
                self.ctx.notifier.info("Nothing was deleted.")
            return
        backup_service.erase_all_data(self.ctx.db)
        self.data_replaced.emit()
        self.refresh()
        self.ctx.notifier.success("All data deleted")

    # ---------- backup ----------
    def _indexing_busy(self) -> bool:
        if self.ctx.indexing.running:
            QMessageBox.information(self, APP_NAME, "AURIX is indexing files right now. Wait for it to finish "
                                    "or pause it in Find, then try again.")
            return True
        return False

    def _backup(self):
        path, _ = QFileDialog.getSaveFileName(self, "Save backup", str(Path.home() / backup_service.default_backup_name()),
                                              "AURIX backup (*.db)")
        if not path:
            return
        if not path.lower().endswith(".db"):
            path += ".db"
        try:
            backup_service.backup_to(self.ctx.db, path)
        except (OSError, ValidationError, sqlite3.Error) as exc:
            self.ctx.notifier.error(f"Backup failed: {exc}")
            return
        self.ctx.notifier.success(f"Backup saved: {path}")

    def _restore(self):
        if self._indexing_busy():
            return
        path, _ = QFileDialog.getOpenFileName(self, "Choose a backup to restore", str(Path.home()), "AURIX backup (*.db)")
        if not path:
            return
        try:
            backup_service.validate_backup(path)
        except ValidationError as exc:
            self.ctx.notifier.error(str(exc))
            return
        if QMessageBox.question(self, "Restore backup", "This replaces ALL current AURIX data with the backup.\n"
                                "Your current data is saved first so you can undo this.\n\nContinue?") != QMessageBox.Yes:
            return
        try:
            safety = backup_service.restore_from(self.ctx.db, path, Path(self.ctx.db.path).parent / "safety-backups")
        except (OSError, ValidationError, sqlite3.Error) as exc:
            self.ctx.notifier.error(f"Restore failed: {exc}")
            return
        self.data_replaced.emit()
        self.refresh()
        QMessageBox.information(self, APP_NAME, f"Backup restored.\n\nYour previous data was saved to:\n{safety}")
