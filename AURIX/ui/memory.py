"""AURIX Memory: notes and ideas with tags. Everything is stored in local SQLite."""
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (QButtonGroup, QCheckBox, QComboBox, QHBoxLayout, QLabel,
                               QLineEdit, QListWidget, QListWidgetItem, QMessageBox,
                               QPlainTextEdit, QPushButton, QVBoxLayout, QWidget)

from core.errors import ValidationError
from ui.base_page import BasePage, make_card
from ui.components import SearchBar

FILTERS = [("All", None), ("Notes", "note"), ("Ideas", "idea"), ("Important", "important")]


class MemoryPage(BasePage):
    def __init__(self, ctx, parent=None):
        super().__init__("Memory", "Save, organize and connect your ideas", parent, scroll=False)
        self.ctx = ctx
        self.current_id = None
        self._loading = False
        self._dirty = False
        self.filter_key = None

        row = QHBoxLayout()
        row.setSpacing(18)
        self.body.addLayout(row, 1)

        # ---- left: list ----
        left = QWidget()
        left.setFixedWidth(350)
        lcol = QVBoxLayout(left)
        lcol.setContentsMargins(0, 0, 0, 0)
        lcol.setSpacing(10)
        top = QHBoxLayout()
        self.search = SearchBar("Search notes, ideas, tags…")
        new_btn = QPushButton("New")
        new_btn.setObjectName("Primary")
        new_btn.clicked.connect(self.new_note)
        top.addWidget(self.search, 1)
        top.addWidget(new_btn)
        lcol.addLayout(top)

        chips = QHBoxLayout()
        chips.setSpacing(6)
        self.chip_group = QButtonGroup(self)
        for label, key in FILTERS:
            b = QPushButton(label)
            b.setObjectName("Chip")
            b.setCheckable(True)
            b.setChecked(key is None)
            b.clicked.connect(lambda _=False, k=key: self._set_filter(k))
            self.chip_group.addButton(b)
            chips.addWidget(b)
        chips.addStretch(1)
        lcol.addLayout(chips)

        self.tag_combo = QComboBox()
        self.tag_combo.currentIndexChanged.connect(lambda _: self._reload())
        lcol.addWidget(self.tag_combo)
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

        # ---- right: editor ----
        card, form = make_card("Editor")
        self.title_edit = QLineEdit()
        self.title_edit.setPlaceholderText("Title")
        self.title_edit.setMaxLength(200)
        meta = QHBoxLayout()
        self.kind_combo = QComboBox()
        self.kind_combo.addItems(["Note", "Idea"])
        self.important = QCheckBox("Important")
        meta.addWidget(self.kind_combo)
        meta.addWidget(self.important)
        meta.addStretch(1)
        self.tags_edit = QLineEdit()
        self.tags_edit.setPlaceholderText("Tags, separated by commas (e.g. study, goals)")
        self.body_edit = QPlainTextEdit()
        self.body_edit.setPlaceholderText("Write your note or idea here…")
        self.info = QLabel("")
        self.info.setObjectName("CardText")
        buttons = QHBoxLayout()
        self.save_btn = QPushButton("Save")
        self.save_btn.setObjectName("Primary")
        self.delete_btn = QPushButton("Delete")
        self.delete_btn.setObjectName("Danger")
        self.save_btn.clicked.connect(self._save)
        self.delete_btn.clicked.connect(self._delete)
        buttons.addWidget(self.save_btn)
        buttons.addWidget(self.delete_btn)
        buttons.addStretch(1)
        buttons.addWidget(self.info)
        for w in (self.title_edit, ):
            form.addWidget(w)
        form.addLayout(meta)
        form.addWidget(self.tags_edit)
        form.addWidget(self.body_edit, 1)
        form.addLayout(buttons)
        row.addWidget(card, 1)

        for w in (self.title_edit, self.tags_edit):
            w.textChanged.connect(self._mark_dirty)
        self.body_edit.textChanged.connect(self._mark_dirty)
        self.kind_combo.currentIndexChanged.connect(self._mark_dirty)
        self.important.toggled.connect(self._mark_dirty)
        shortcut = QShortcut(QKeySequence("Ctrl+S"), self)
        shortcut.setContext(Qt.WidgetWithChildrenShortcut)
        shortcut.activated.connect(self._save)
        self._clear_editor()

    # ---- public ----
    def refresh(self) -> None:
        self._reload_tags()
        self._reload(self.current_id)

    def new_note(self) -> None:
        if not self._confirm_discard():
            return
        self._loading = True
        self.list.clearSelection()
        self.list.setCurrentRow(-1)
        self._loading = False
        self._clear_editor()
        self.title_edit.setFocus()

    def open_note(self, note_id: int) -> None:
        if not self._confirm_discard():
            return
        self.search.clear()
        self._set_filter(None)
        self._reload(note_id)
        note = self.ctx.memory.get_note(note_id)
        if note:
            self._load(note)

    # ---- list ----
    def _set_filter(self, key):
        self.filter_key = key
        for b, (_, k) in zip(self.chip_group.buttons(), FILTERS):
            b.setChecked(k == key)
        self._reload()

    def _reload_tags(self):
        current = self.tag_combo.currentText()
        self.tag_combo.blockSignals(True)
        self.tag_combo.clear()
        self.tag_combo.addItem("All tags")
        self.tag_combo.addItems(self.ctx.memory.all_tags())
        i = self.tag_combo.findText(current)
        self.tag_combo.setCurrentIndex(max(i, 0))
        self.tag_combo.blockSignals(False)

    def _reload(self, select_id=None):
        if select_id is None:
            select_id = self.current_id
        tag = self.tag_combo.currentText() if self.tag_combo.currentIndex() > 0 else None
        k = self.filter_key
        notes = self.ctx.memory.list_notes(self.search.text(), kind=k if k in ("note", "idea") else None,
                                           important=(k == "important"), tag=tag)
        self._loading = True
        self.list.clear()
        for n in notes:
            tags = ("  ".join("#" + t for t in n.tags) + "  ·  ") if n.tags else ""
            item = QListWidgetItem(f"{'★ ' if n.is_important else ''}{n.title}\n{tags}{n.kind.capitalize()} · {n.updated_at[:16]}")
            item.setData(Qt.UserRole, n.id)
            self.list.addItem(item)
            if n.id == select_id:
                self.list.setCurrentItem(item)
        self._loading = False
        if notes:
            self.hint.setText(f"{len(notes)} item(s)")
        else:
            total = self.ctx.db.table_counts()["notes"]
            self.hint.setText("Nothing saved yet. Write your first note on the right and press Save."
                              if total == 0 else "No matches. Try other words or filters.")

    def _on_select(self, current, previous):
        if self._loading or current is None:
            return
        note_id = current.data(Qt.UserRole)
        if note_id == self.current_id:
            return
        if not self._confirm_discard():
            self._loading = True
            if previous is not None:
                self.list.setCurrentItem(previous)
            else:
                self.list.setCurrentRow(-1)
            self._loading = False
            return
        note = self.ctx.memory.get_note(note_id)
        if note:
            self._load(note)

    # ---- editor ----
    def _mark_dirty(self, *_):
        if not self._loading:
            self._dirty = True

    def _confirm_discard(self) -> bool:
        if not self._dirty:
            return True
        answer = QMessageBox.question(self, "Unsaved changes", "Discard your unsaved changes?")
        if answer == QMessageBox.Yes:
            self._dirty = False
            return True
        return False

    def _clear_editor(self):
        self._loading = True
        self.current_id = None
        self.title_edit.clear()
        self.tags_edit.clear()
        self.body_edit.clear()
        self.kind_combo.setCurrentIndex(0)
        self.important.setChecked(False)
        self.info.setText("New note")
        self.delete_btn.setEnabled(False)
        self._loading = False
        self._dirty = False

    def _load(self, note):
        self._loading = True
        self.current_id = note.id
        self.title_edit.setText(note.title)
        self.tags_edit.setText(", ".join(note.tags))
        self.body_edit.setPlainText(note.body)
        self.kind_combo.setCurrentIndex(0 if note.kind == "note" else 1)
        self.important.setChecked(note.is_important)
        self.info.setText(f"Created {note.created_at[:16]} · Updated {note.updated_at[:16]}")
        self.delete_btn.setEnabled(True)
        self._loading = False
        self._dirty = False

    def _save(self):
        try:
            note_id = self.ctx.memory.save_note(
                self.title_edit.text(), self.body_edit.toPlainText(),
                "note" if self.kind_combo.currentIndex() == 0 else "idea",
                self.important.isChecked(), self.tags_edit.text(), self.current_id)
        except ValidationError as exc:
            self.ctx.notifier.error(str(exc))
            return
        self._dirty = False
        self.current_id = note_id
        self._reload_tags()
        self._reload(note_id)
        self._load(self.ctx.memory.get_note(note_id))
        self.ctx.notifier.success("Saved")

    def _delete(self):
        if self.current_id is None:
            return
        if QMessageBox.question(self, "Delete", "Delete this item permanently?") != QMessageBox.Yes:
            return
        self.ctx.memory.delete_note(self.current_id)
        self._clear_editor()
        self._reload_tags()
        self._reload()
        self.ctx.notifier.success("Deleted")
