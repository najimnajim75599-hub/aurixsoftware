"""AURIX Find: keyword search over indexed files and notes, plus folder management.
Only folders you choose are indexed, and only names, sizes and dates are read."""
import os
import subprocess
import sys

from PySide6.QtCore import Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (QComboBox, QFileDialog, QHBoxLayout, QLabel, QLineEdit,
                               QListWidget, QListWidgetItem, QMessageBox, QPlainTextEdit,
                               QPushButton, QVBoxLayout, QWidget)

from core.errors import ValidationError
from core.filetypes import GROUP_NAMES
from ui.base_page import BasePage, make_card
from ui.components import SearchBar


class FindPage(BasePage):
    open_note = Signal(int)

    def __init__(self, ctx, parent=None):
        super().__init__("Find", "Search file names, tags, descriptions and notes. This is keyword search, not AI.",
                         parent, scroll=False)
        self.ctx = ctx
        self.detail = None  # ("file", id) or ("note", id)
        row = QHBoxLayout()
        row.setSpacing(18)
        self.body.addLayout(row, 1)

        # ---- left: search + results ----
        left = QVBoxLayout()
        left.setSpacing(10)
        self.search = SearchBar("Try: the presentation about artificial intelligence")
        left.addWidget(self.search)
        filters = QHBoxLayout()
        self.scope = QComboBox()
        self.scope.addItems(["Files and notes", "Files only", "Notes only"])
        self.group = QComboBox()
        self.group.addItem("All types")
        self.group.addItems(GROUP_NAMES)
        self.folder = QComboBox()
        for c in (self.scope, self.group, self.folder):
            filters.addWidget(c, 1)
            c.currentIndexChanged.connect(lambda _: self._search())
        left.addLayout(filters)
        self.status = QLabel("")
        self.status.setObjectName("CardText")
        self.status.setWordWrap(True)
        left.addWidget(self.status)
        self.results = QListWidget()
        self.results.setObjectName("ItemList")
        self.results.currentItemChanged.connect(self._on_result)
        left.addWidget(self.results, 1)
        row.addLayout(left, 3)

        self._timer = QTimer(self, singleShot=True, interval=250)
        self._timer.timeout.connect(self._search)
        self.search.textChanged.connect(lambda _: self._timer.start())

        # ---- right: details + folders ----
        right = QVBoxLayout()
        right.setSpacing(14)
        card, d = make_card("Details")
        self.d_title = QLabel("Select a result")
        self.d_title.setObjectName("RowTitle")
        self.d_title.setWordWrap(True)
        self.d_meta = QLabel("")
        self.d_meta.setObjectName("CardText")
        self.d_meta.setWordWrap(True)
        self.d_meta.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.d_desc = QPlainTextEdit()
        self.d_desc.setPlaceholderText("Add your own description, e.g. “logo I made for my business”")
        self.d_desc.setFixedHeight(78)
        self.d_tags = QLineEdit()
        self.d_tags.setPlaceholderText("Tags, separated by commas")
        self.btn_save = QPushButton("Save details")
        self.btn_save.setObjectName("Primary")
        self.btn_open = QPushButton("Open")
        self.btn_show = QPushButton("Show in folder")
        self.btn_note = QPushButton("Open in Memory")
        self.btn_save.clicked.connect(self._save_details)
        self.btn_open.clicked.connect(self._open_file)
        self.btn_show.clicked.connect(self._show_in_folder)
        self.btn_note.clicked.connect(lambda: self.open_note.emit(self.detail[1]))
        btns = QHBoxLayout()
        for b in (self.btn_save, self.btn_open, self.btn_show, self.btn_note):
            btns.addWidget(b)
        for w in (self.d_title, self.d_meta, self.d_desc, self.d_tags):
            d.addWidget(w)
        d.addLayout(btns)
        right.addWidget(card)

        fcard, f = make_card("Indexed folders")
        privacy = QLabel("AURIX only reads file names, sizes and dates in folders you add. It never opens "
                         "file contents and never uploads anything. Pause or remove a folder at any time.")
        privacy.setObjectName("CardText")
        privacy.setWordWrap(True)
        self.folder_list = QListWidget()
        self.folder_list.setObjectName("ItemList")
        self.folder_list.setFixedHeight(110)
        self.folder_list.currentItemChanged.connect(lambda *_: self._update_buttons())
        self.progress = QLabel("")
        self.progress.setObjectName("CardText")
        self.btn_add = QPushButton("Add folder…")
        self.btn_add.setObjectName("Primary")
        self.btn_scan = QPushButton("Re-scan")
        self.btn_stop = QPushButton("Pause indexing")
        self.btn_toggle = QPushButton("Skip / include")
        self.btn_remove = QPushButton("Remove")
        self.btn_remove.setObjectName("Danger")
        self.btn_add.clicked.connect(self.add_folder)
        self.btn_scan.clicked.connect(lambda: self._start_indexing())
        self.btn_stop.clicked.connect(lambda: self.ctx.indexing.stop())
        self.btn_toggle.clicked.connect(self._toggle_folder)
        self.btn_remove.clicked.connect(self._remove_folder)
        r1, r2 = QHBoxLayout(), QHBoxLayout()
        for b in (self.btn_add, self.btn_scan, self.btn_stop):
            r1.addWidget(b)
        for b in (self.btn_toggle, self.btn_remove):
            r2.addWidget(b)
        r2.addStretch(1)
        for w in (privacy, self.folder_list, self.progress):
            f.addWidget(w)
        f.addLayout(r1)
        f.addLayout(r2)
        right.addWidget(fcard)
        right.addStretch(1)
        holder = QWidget()
        holder.setFixedWidth(400)
        holder.setLayout(right)
        right.setContentsMargins(0, 0, 0, 0)
        row.addWidget(holder)

        idx = ctx.indexing
        idx.progress.connect(lambda n, p: self.progress.setText(f"Indexing… {n} files scanned"))
        idx.completed.connect(self._index_done)
        idx.failed.connect(lambda m: ctx.notifier.error(f"Indexing problem: {m}"))
        idx.state_changed.connect(lambda _: self._update_buttons())
        self._set_detail(None)

    # ---- public ----
    def refresh(self) -> None:
        self._reload_folders()
        self._search()

    def set_query(self, text: str) -> None:
        self.search.setText(text)
        self._search()

    # ---- search ----
    def _search(self):
        scope = ["all", "files", "notes"][self.scope.currentIndex()]
        group = self.group.currentText() if self.group.currentIndex() > 0 else None
        folder_id = self.folder.currentData()
        query = self.search.text().strip()
        found = self.ctx.search.search(query, scope, group, folder_id)
        self.results.blockSignals(True)
        self.results.clear()
        for r in found:
            item = QListWidgetItem(f"{r.title}\n{r.subtitle}")
            item.setData(Qt.UserRole, (r.kind, r.id))
            self.results.addItem(item)
        self.results.blockSignals(False)
        self._set_detail(None)
        if found:
            self.status.setText(f"{len(found)} result(s)" if query else "Recently modified files")
        elif not self.ctx.files.list_folders() and not query:
            self.status.setText("Add a folder on the right to start searching your files.")
        else:
            self.status.setText("No matches. Try different words, or fewer of them.")

    def _on_result(self, current, _prev):
        if current is None:
            return
        kind, rid = current.data(Qt.UserRole)
        if kind == "file":
            f = self.ctx.files.get_file(rid)
            if f:
                self._set_detail(("file", rid), f)
        else:
            n = self.ctx.memory.get_note(rid)
            if n:
                self._set_detail(("note", rid), n)

    def _set_detail(self, detail, obj=None):
        self.detail = detail
        is_file = detail is not None and detail[0] == "file"
        is_note = detail is not None and detail[0] == "note"
        for w in (self.d_desc, self.d_tags, self.btn_save, self.btn_open, self.btn_show):
            w.setVisible(is_file)
        self.btn_note.setVisible(is_note)
        if is_file:
            self.d_title.setText(obj.name)
            self.d_meta.setText(f"{obj.group} · {obj.size_text} · modified {obj.modified_at[:16]}\n{obj.path}")
            self.d_desc.setPlainText(obj.description)
            self.d_tags.setText(obj.tags)
        elif is_note:
            self.d_title.setText(obj.title)
            body = obj.body.strip()
            self.d_meta.setText((body[:300] + ("…" if len(body) > 300 else "")) or "(empty)")
        else:
            self.d_title.setText("Select a result")
            self.d_meta.setText("Pick a file or note to see its details.")

    def _save_details(self):
        try:
            self.ctx.files.update_details(self.detail[1], self.d_desc.toPlainText(), self.d_tags.text())
        except ValidationError as exc:
            self.ctx.notifier.error(str(exc))
            return
        self.ctx.notifier.success("Details saved")

    def _open_file(self):
        f = self.ctx.files.get_file(self.detail[1])
        if f and os.path.exists(f.path):
            QDesktopServices.openUrl(QUrl.fromLocalFile(f.path))
            self.ctx.files.touch_opened(f.id)
        else:
            self.ctx.notifier.error("File not found. It may have moved. Try Re-scan.")

    def _show_in_folder(self):
        f = self.ctx.files.get_file(self.detail[1])
        if not f or not os.path.exists(f.path):
            self.ctx.notifier.error("File not found. It may have moved. Try Re-scan.")
        elif sys.platform == "win32":
            subprocess.Popen(["explorer", "/select,", os.path.normpath(f.path)])
        else:
            QDesktopServices.openUrl(QUrl.fromLocalFile(os.path.dirname(f.path)))

    # ---- folders & indexing ----
    def _reload_folders(self):
        folders = self.ctx.files.list_folders()
        selected = self.folder.currentData()
        self.folder.blockSignals(True)
        self.folder.clear()
        self.folder.addItem("All folders", None)
        for fo in folders:
            self.folder.addItem(os.path.basename(fo["path"]) or fo["path"], fo["id"])
        i = self.folder.findData(selected)
        self.folder.setCurrentIndex(max(i, 0))
        self.folder.blockSignals(False)
        self.folder_list.clear()
        for fo in folders:
            state = "skipped" if fo["paused"] else f"{fo['file_count']} files"
            item = QListWidgetItem(f"{fo['path']}\n{state}")
            item.setData(Qt.UserRole, fo["id"])
            self.folder_list.addItem(item)
        self._update_buttons()

    def _selected_folder(self):
        item = self.folder_list.currentItem()
        return item.data(Qt.UserRole) if item else None

    def _update_buttons(self):
        running = self.ctx.indexing.running
        has_sel = self._selected_folder() is not None
        self.btn_add.setEnabled(not running)
        self.btn_scan.setEnabled(not running and self.folder_list.count() > 0)
        self.btn_stop.setEnabled(running)
        self.btn_toggle.setEnabled(not running and has_sel)
        self.btn_remove.setEnabled(not running and has_sel)

    def add_folder(self):
        path = QFileDialog.getExistingDirectory(self, "Choose a folder to index")
        if not path:
            return
        ok = QMessageBox.question(
            self, "Index this folder?",
            f"AURIX will read the names, sizes and dates of files in:\n\n{path}\n\n"
            "It will not open, read or upload file contents. Continue?")
        if ok != QMessageBox.Yes:
            return
        try:
            fid = self.ctx.files.add_folder(path)
        except ValidationError as exc:
            self.ctx.notifier.error(str(exc))
            return
        self._reload_folders()
        self._start_indexing([fid])

    def _start_indexing(self, only_ids=None):
        todo = [(f["id"], f["path"]) for f in self.ctx.files.list_folders()
                if not f["paused"] and (only_ids is None or f["id"] in only_ids)]
        if not todo:
            self.ctx.notifier.info("No folders to scan.")
            return
        self.progress.setText("Indexing… 0 files scanned")
        self.ctx.indexing.start(todo)

    def _index_done(self, total, stopped):
        self.progress.setText("Indexing paused." if stopped else f"Done. {total} files indexed.")
        self._reload_folders()
        self._search()
        self.ctx.notifier.info("Indexing paused" if stopped else f"Indexed {total} files")

    def _toggle_folder(self):
        fid = self._selected_folder()
        if fid is None:
            return
        row = next(f for f in self.ctx.files.list_folders() if f["id"] == fid)
        self.ctx.files.set_paused(fid, not row["paused"])
        self._reload_folders()

    def _remove_folder(self):
        fid = self._selected_folder()
        if fid is None:
            return
        ok = QMessageBox.question(
            self, "Remove folder?",
            "Remove this folder from AURIX? Your files on disk are not touched, but the index "
            "entries and any descriptions or tags you added to them will be deleted.")
        if ok == QMessageBox.Yes:
            self.ctx.files.remove_folder(fid)
            self._reload_folders()
            self._search()
