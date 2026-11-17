"""AURIX Flow: projects, tasks, deadlines, progress, attached notes/files and history."""
import os

from PySide6.QtCore import Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QColor, QDesktopServices
from PySide6.QtWidgets import (QComboBox, QHBoxLayout, QLabel, QLineEdit, QListWidget,
                               QListWidgetItem, QMessageBox, QPlainTextEdit, QProgressBar,
                               QPushButton, QTabWidget, QVBoxLayout, QWidget)

from core.errors import ValidationError
from core.project_manager import PROJECT_STATUSES, STATUS_LABELS
from ui.base_page import BasePage, make_card
from ui.components import PickerDialog, SearchBar

TASK_MARK = {"todo": "○", "doing": "◐", "done": "●"}


class FlowPage(BasePage):
    open_note = Signal(int)

    def __init__(self, ctx, parent=None):
        super().__init__("Flow", "Turn ideas into projects, tasks and progress", parent, scroll=False)
        self.ctx = ctx
        self.pm, self.rel = ctx.projects, ctx.relations
        self.current_id = None
        self._loading = False
        self._dirty = False

        row = QHBoxLayout()
        row.setSpacing(18)
        self.body.addLayout(row, 1)

        # ---- left: project list ----
        left = QWidget()
        left.setFixedWidth(330)
        lcol = QVBoxLayout(left)
        lcol.setContentsMargins(0, 0, 0, 0)
        lcol.setSpacing(10)
        top = QHBoxLayout()
        self.search = SearchBar("Search projects…")
        new_btn = QPushButton("New")
        new_btn.setObjectName("Primary")
        new_btn.clicked.connect(self.new_project)
        top.addWidget(self.search, 1)
        top.addWidget(new_btn)
        lcol.addLayout(top)
        self.status_filter = QComboBox()
        self.status_filter.addItem("All projects", None)
        for s in PROJECT_STATUSES:
            self.status_filter.addItem(STATUS_LABELS[s], s)
        self.status_filter.currentIndexChanged.connect(lambda _: self._reload())
        lcol.addWidget(self.status_filter)
        self.list = QListWidget()
        self.list.setObjectName("ItemList")
        self.list.currentItemChanged.connect(self._on_select)
        lcol.addWidget(self.list, 1)
        self.hint = QLabel("")
        self.hint.setObjectName("CardText")
        self.hint.setWordWrap(True)
        lcol.addWidget(self.hint)
        row.addWidget(left)
        self._timer = QTimer(self, singleShot=True, interval=200)
        self._timer.timeout.connect(self._reload)
        self.search.textChanged.connect(lambda _: self._timer.start())

        # ---- right: editor + tabs ----
        card, form = make_card("Project")
        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("Project name")
        self.name_edit.setMaxLength(200)
        meta = QHBoxLayout()
        self.status_combo = QComboBox()
        for s in PROJECT_STATUSES:
            self.status_combo.addItem(STATUS_LABELS[s], s)
        self.progress = QProgressBar()
        self.progress.setTextVisible(True)
        self.progress.setFormat("%p% of tasks done")
        meta.addWidget(self.status_combo)
        meta.addWidget(self.progress, 1)
        self.desc_edit = QPlainTextEdit()
        self.desc_edit.setPlaceholderText("What is this project about?")
        self.desc_edit.setFixedHeight(70)
        btns = QHBoxLayout()
        self.save_btn = QPushButton("Save project")
        self.save_btn.setObjectName("Primary")
        self.delete_btn = QPushButton("Delete project")
        self.delete_btn.setObjectName("Danger")
        self.info = QLabel("")
        self.info.setObjectName("CardText")
        self.save_btn.clicked.connect(self._save)
        self.delete_btn.clicked.connect(self._delete)
        for w in (self.save_btn, self.delete_btn):
            btns.addWidget(w)
        btns.addStretch(1)
        btns.addWidget(self.info)
        form.addWidget(self.name_edit)
        form.addLayout(meta)
        form.addWidget(self.desc_edit)
        form.addLayout(btns)

        self.tabs = QTabWidget()
        self.tabs.addTab(self._build_tasks_tab(), "Tasks")
        self.tabs.addTab(self._build_attach_tab(), "Notes & files")
        self.tabs.addTab(self._build_history_tab(), "History")
        form.addWidget(self.tabs, 1)
        row.addWidget(card, 1)

        for w in (self.name_edit,):
            w.textChanged.connect(self._mark_dirty)
        self.desc_edit.textChanged.connect(self._mark_dirty)
        self.status_combo.currentIndexChanged.connect(self._mark_dirty)
        self._clear_editor()

    # ---------- tabs ----------
    def _build_tasks_tab(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 10, 0, 0)
        add = QHBoxLayout()
        self.task_title = QLineEdit()
        self.task_title.setPlaceholderText("New task…")
        self.task_title.setMaxLength(300)
        self.task_due = QLineEdit()
        self.task_due.setPlaceholderText("Deadline YYYY-MM-DD (optional)")
        self.task_due.setMaxLength(10)
        self.task_due.setFixedWidth(210)
        self.add_task_btn = QPushButton("Add task")
        self.add_task_btn.setObjectName("Primary")
        self.add_task_btn.clicked.connect(self._add_task)
        self.task_title.returnPressed.connect(self._add_task)
        add.addWidget(self.task_title, 1)
        add.addWidget(self.task_due)
        add.addWidget(self.add_task_btn)
        lay.addLayout(add)
        self.tasks = QListWidget()
        self.tasks.setObjectName("ItemList")
        self.tasks.currentItemChanged.connect(lambda *_: self._update_task_buttons())
        lay.addWidget(self.tasks, 1)
        bar = QHBoxLayout()
        self.task_buttons = {}
        for label, status in (("To do", "todo"), ("Doing", "doing"), ("Done", "done")):
            b = QPushButton(label)
            b.clicked.connect(lambda _=False, s=status: self._set_task(s))
            bar.addWidget(b)
            self.task_buttons[status] = b
        self.due_btn = QPushButton("Set deadline…")
        self.due_btn.clicked.connect(self._edit_deadline)
        self.del_task_btn = QPushButton("Delete task")
        self.del_task_btn.setObjectName("Danger")
        self.del_task_btn.clicked.connect(self._delete_task)
        bar.addWidget(self.due_btn)
        bar.addStretch(1)
        bar.addWidget(self.del_task_btn)
        lay.addLayout(bar)
        return w

    def _build_attach_tab(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 10, 0, 0)
        hint = QLabel("Attach notes, ideas and indexed files to this project. Attachments also appear in Connect.")
        hint.setObjectName("CardText")
        hint.setWordWrap(True)
        lay.addWidget(hint)
        self.links = QListWidget()
        self.links.setObjectName("ItemList")
        self.links.itemDoubleClicked.connect(self._open_link)
        self.links.currentItemChanged.connect(lambda *_: self._update_task_buttons())
        lay.addWidget(self.links, 1)
        bar = QHBoxLayout()
        self.attach_note_btn = QPushButton("Attach note…")
        self.attach_idea_btn = QPushButton("Attach idea…")
        self.attach_file_btn = QPushButton("Attach file…")
        self.open_link_btn = QPushButton("Open")
        self.detach_btn = QPushButton("Detach")
        self.detach_btn.setObjectName("Danger")
        self.attach_note_btn.clicked.connect(lambda: self._attach("note"))
        self.attach_idea_btn.clicked.connect(lambda: self._attach("idea"))
        self.attach_file_btn.clicked.connect(lambda: self._attach("file"))
        self.open_link_btn.clicked.connect(lambda: self._open_link(self.links.currentItem()))
        self.detach_btn.clicked.connect(self._detach)
        for b in (self.attach_note_btn, self.attach_idea_btn, self.attach_file_btn, self.open_link_btn):
            bar.addWidget(b)
        bar.addStretch(1)
        bar.addWidget(self.detach_btn)
        lay.addLayout(bar)
        return w

    def _build_history_tab(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 10, 0, 0)
        self.history = QListWidget()
        self.history.setObjectName("ItemList")
        self.history.setSelectionMode(QListWidget.NoSelection)
        lay.addWidget(self.history)
        return w

    # ---------- public ----------
    def refresh(self) -> None:
        self._reload(self.current_id)
        self._load_children()

    def reset(self) -> None:
        self._clear_editor()

    def new_project(self) -> None:
        if not self._confirm_discard():
            return
        self._loading = True
        self.list.setCurrentRow(-1)
        self._loading = False
        self._clear_editor()
        self.name_edit.setFocus()

    def open_project(self, project_id: int) -> None:
        if not self._confirm_discard():
            return
        self.search.clear()
        self.status_filter.setCurrentIndex(0)
        self._reload(project_id)
        p = self.pm.get_project(project_id)
        if p:
            self._load(p)

    # ---------- list ----------
    def _reload(self, select_id=None):
        if select_id is None:
            select_id = self.current_id
        projects = self.pm.list_projects(self.search.text(), self.status_filter.currentData())
        self._loading = True
        self.list.clear()
        for p in projects:
            item = QListWidgetItem(f"{p.name}\n{STATUS_LABELS[p.status]} · {p.done_tasks}/{p.total_tasks} tasks · {p.progress}%")
            item.setData(Qt.UserRole, p.id)
            self.list.addItem(item)
            if p.id == select_id:
                self.list.setCurrentItem(item)
        self._loading = False
        if projects:
            self.hint.setText(f"{len(projects)} project(s)")
        else:
            total = self.ctx.db.table_counts()["projects"]
            self.hint.setText("No projects yet. Type a name on the right and press Save project."
                              if total == 0 else "No matches. Try other words or filters.")

    def _on_select(self, current, previous):
        if self._loading or current is None:
            return
        pid = current.data(Qt.UserRole)
        if pid == self.current_id:
            return
        if not self._confirm_discard():
            self._loading = True
            self.list.setCurrentItem(previous) if previous is not None else self.list.setCurrentRow(-1)
            self._loading = False
            return
        p = self.pm.get_project(pid)
        if p:
            self._load(p)

    # ---------- editor ----------
    def _mark_dirty(self, *_):
        if not self._loading:
            self._dirty = True

    def _confirm_discard(self) -> bool:
        if not self._dirty:
            return True
        if QMessageBox.question(self, "Unsaved changes", "Discard your unsaved changes?") == QMessageBox.Yes:
            self._dirty = False
            return True
        return False

    def _clear_editor(self):
        self._loading = True
        self.current_id = None
        self.name_edit.clear()
        self.desc_edit.clear()
        self.status_combo.setCurrentIndex(0)
        self.progress.setValue(0)
        self.info.setText("New project")
        self._loading = False
        self._dirty = False
        self._load_children()

    def _load(self, p):
        self._loading = True
        self.current_id = p.id
        self.name_edit.setText(p.name)
        self.desc_edit.setPlainText(p.description)
        self.status_combo.setCurrentIndex(PROJECT_STATUSES.index(p.status))
        self.progress.setValue(p.progress)
        self.info.setText(f"Created {p.created_at[:16]} · Updated {p.updated_at[:16]}")
        self._loading = False
        self._dirty = False
        self._load_children()

    def _load_children(self):
        has = self.current_id is not None
        self.delete_btn.setEnabled(has)
        for w in (self.task_title, self.task_due, self.add_task_btn, self.attach_note_btn,
                  self.attach_idea_btn, self.attach_file_btn):
            w.setEnabled(has)
        self.tasks.clear()
        self.links.clear()
        self.history.clear()
        if has:
            for t in self.pm.list_tasks(self.current_id):
                due = f" · due {t.deadline}" if t.deadline else ""
                late = "  (overdue)" if t.overdue else ""
                item = QListWidgetItem(f"{TASK_MARK[t.status]}  {t.title}{due}{late}")
                item.setData(Qt.UserRole, t.id)
                if t.status == "done":
                    item.setForeground(QColor("#8A8A8A"))
                elif t.overdue:
                    item.setForeground(QColor("#C51F32"))
                self.tasks.addItem(item)
            for link in self.rel.links_for("project", self.current_id):
                other = link["other"]
                if other["type"] == "task":
                    continue
                kind = {"note": "Note", "idea": "Idea", "file": "File"}.get(other["type"], other["type"].title())
                item = QListWidgetItem(f"{kind}: {other['title']}")
                item.setData(Qt.UserRole, (link["relation_id"], other["type"], other["id"]))
                self.links.addItem(item)
            for h in self.pm.history(self.current_id):
                item = QListWidgetItem(f"{h['created_at'][:16]}   {h['summary']}")
                self.history.addItem(item)
            p = self.pm.get_project(self.current_id)
            if p:
                self.progress.setValue(p.progress)
        self._update_task_buttons()

    def _save(self):
        try:
            pid = self.pm.save_project(self.name_edit.text(), self.desc_edit.toPlainText(),
                                       self.status_combo.currentData(), self.current_id)
        except ValidationError as exc:
            self.ctx.notifier.error(str(exc))
            return
        self._dirty = False
        self.current_id = pid
        self._reload(pid)
        self._load(self.pm.get_project(pid))
        self.ctx.notifier.success("Project saved")

    def _delete(self):
        if self.current_id is None:
            return
        if QMessageBox.question(self, "Delete project",
                                "Delete this project and all its tasks permanently?\n"
                                "Attached notes and files are not deleted.") != QMessageBox.Yes:
            return
        self.pm.delete_project(self.current_id)
        self._clear_editor()
        self._reload()
        self.ctx.notifier.success("Project deleted")

    # ---------- tasks ----------
    def _selected_task(self):
        item = self.tasks.currentItem()
        return item.data(Qt.UserRole) if item else None

    def _update_task_buttons(self):
        has = self._selected_task() is not None
        for b in (*self.task_buttons.values(), self.due_btn, self.del_task_btn):
            b.setEnabled(has)
        has_link = self.links.currentItem() is not None
        self.open_link_btn.setEnabled(has_link)
        self.detach_btn.setEnabled(has_link)

    def _add_task(self):
        if self.current_id is None:
            return
        try:
            self.pm.add_task(self.current_id, self.task_title.text(), self.task_due.text())
        except ValidationError as exc:
            self.ctx.notifier.error(str(exc))
            return
        self.task_title.clear()
        self.task_due.clear()
        self._after_task_change()
        self.task_title.setFocus()

    def _set_task(self, status):
        tid = self._selected_task()
        if tid is None:
            return
        try:
            self.pm.set_task_status(tid, status)
        except ValidationError as exc:
            self.ctx.notifier.error(str(exc))
            return
        self._after_task_change()

    def _edit_deadline(self):
        from PySide6.QtWidgets import QInputDialog
        tid = self._selected_task()
        if tid is None:
            return
        task = self.pm.get_task(tid)
        text, ok = QInputDialog.getText(self, "Deadline", "Deadline (YYYY-MM-DD, empty to clear):", text=task.deadline)
        if not ok:
            return
        try:
            self.pm.set_task_deadline(tid, text)
        except ValidationError as exc:
            self.ctx.notifier.error(str(exc))
            return
        self._after_task_change()

    def _delete_task(self):
        tid = self._selected_task()
        if tid is None:
            return
        if QMessageBox.question(self, "Delete task", "Delete this task?") != QMessageBox.Yes:
            return
        self.pm.delete_task(tid)
        self._after_task_change()

    def _after_task_change(self):
        keep = self.current_id
        self._reload(keep)
        self._load_children()

    # ---------- attachments ----------
    def _attach(self, kind):
        if self.current_id is None:
            return
        titles = {"note": "Attach a note", "idea": "Attach an idea", "file": "Attach an indexed file"}
        dlg = PickerDialog(titles[kind], lambda q: self.rel.candidates(kind, q), self, ask_label=False)
        if dlg.exec() != PickerDialog.Accepted or dlg.chosen_id is None:
            return
        try:
            self.rel.connect("project", self.current_id, kind, dlg.chosen_id, "attached")
        except ValidationError as exc:
            self.ctx.notifier.error(str(exc))
            return
        self.pm.db.execute("UPDATE projects SET updated_at=datetime('now','localtime') WHERE id=?", (self.current_id,))
        self._load_children()
        self.ctx.notifier.success("Attached")

    def _detach(self):
        item = self.links.currentItem()
        if item is None:
            return
        self.rel.disconnect(item.data(Qt.UserRole)[0])
        self._load_children()

    def _open_link(self, item):
        if item is None:
            return
        _, kind, oid = item.data(Qt.UserRole)
        if kind in ("note", "idea"):
            self.open_note.emit(oid)
        elif kind == "file":
            f = self.ctx.files.get_file(oid)
            if f and os.path.exists(f.path):
                QDesktopServices.openUrl(QUrl.fromLocalFile(f.path))
                self.ctx.files.touch_opened(f.id)
            else:
                self.ctx.notifier.error("File not found. It may have been moved or deleted.")
