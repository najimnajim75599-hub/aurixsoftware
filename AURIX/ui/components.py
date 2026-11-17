"""Reusable widgets: search bar, action tile, stat card, list row, badge, empty state."""
from PySide6.QtCore import QByteArray, Qt, Signal
from PySide6.QtSvgWidgets import QSvgWidget
from PySide6.QtWidgets import (QDialog, QDialogButtonBox, QFrame, QHBoxLayout, QLabel, QLineEdit,
                               QListWidget, QListWidgetItem, QSizePolicy, QVBoxLayout, QWidget)

from core.settings import SIGNAL_RED
from ui.icons import make_icon


def clear_layout(layout) -> None:
    while layout.count():
        item = layout.takeAt(0)
        if item.widget():
            item.widget().deleteLater()
        elif item.layout():
            clear_layout(item.layout())


class SearchBar(QLineEdit):
    submitted = Signal(str)

    def __init__(self, placeholder="Search…", parent=None):
        super().__init__(parent)
        self.setObjectName("SearchBar")
        self.setPlaceholderText(placeholder)
        self.setClearButtonEnabled(True)
        self.addAction(make_icon("find", "#6B6B6B"), QLineEdit.LeadingPosition)
        self.returnPressed.connect(lambda: self.submitted.emit(self.text().strip()))


class Badge(QLabel):
    def __init__(self, text, parent=None):
        super().__init__(text, parent)
        self.setObjectName("Badge")


class ActionTile(QFrame):
    clicked = Signal()

    def __init__(self, icon, title, subtitle, parent=None):
        super().__init__(parent)
        self.setObjectName("Tile")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setCursor(Qt.PointingHandCursor)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 14, 16, 14)
        lay.setSpacing(2)
        pic = QLabel()
        pic.setPixmap(make_icon(icon, SIGNAL_RED).pixmap(24, 24))
        head = QLabel(title)
        head.setObjectName("TileTitle")
        sub = QLabel(subtitle)
        sub.setObjectName("CardText")
        for w in (pic, head, sub):
            lay.addWidget(w)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit()


class StatCard(QFrame):
    def __init__(self, label, parent=None):
        super().__init__(parent)
        self.setObjectName("Card")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(18, 14, 18, 14)
        lay.setSpacing(0)
        self.value = QLabel("0")
        self.value.setObjectName("StatValue")
        name = QLabel(label)
        name.setObjectName("StatLabel")
        lay.addWidget(self.value)
        lay.addWidget(name)

    def set_value(self, n) -> None:
        self.value.setText(str(n))


class ListRow(QFrame):
    clicked = Signal()

    def __init__(self, title, subtitle="", right="", clickable=False, parent=None):
        super().__init__(parent)
        self.setObjectName("Row")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self._clickable = clickable
        if clickable:
            self.setCursor(Qt.PointingHandCursor)
        row = QHBoxLayout(self)
        row.setContentsMargins(4, 6, 4, 6)
        col = QVBoxLayout()
        col.setSpacing(0)
        head = QLabel(title)
        head.setObjectName("RowTitle")
        head.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        col.addWidget(head)
        if subtitle:
            sub = QLabel(subtitle)
            sub.setObjectName("RowSub")
            sub.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
            col.addWidget(sub)
        row.addLayout(col, 1)
        if right:
            tail = QLabel(right)
            tail.setObjectName("RowSub")
            row.addWidget(tail)

    def mousePressEvent(self, event):
        if self._clickable and event.button() == Qt.LeftButton:
            self.clicked.emit()


_EMPTY_SVG = (b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 120 80">'
              b'<polygon points="42,66 60,10 78,66 69,66 60,38 51,66" fill="none" stroke="#C5C5C5" '
              b'stroke-width="3" stroke-linejoin="round"/><circle cx="94" cy="28" r="6" fill="#C51F32"/></svg>')


class EmptyState(QWidget):
    def __init__(self, title, text, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setAlignment(Qt.AlignCenter)
        lay.setSpacing(4)
        art = QSvgWidget()
        art.load(QByteArray(_EMPTY_SVG))
        art.setFixedSize(90, 60)
        head = QLabel(title)
        head.setObjectName("CardTitle")
        head.setAlignment(Qt.AlignCenter)
        body = QLabel(text)
        body.setObjectName("CardText")
        body.setAlignment(Qt.AlignCenter)
        body.setWordWrap(True)
        lay.addWidget(art, alignment=Qt.AlignCenter)
        lay.addWidget(head)
        lay.addWidget(body)


class PickerDialog(QDialog):
    """Search-and-pick dialog. fetch(query) must return a list of (id, title) pairs.
    After exec(), .chosen_id holds the picked id (or None)."""

    def __init__(self, title, fetch, parent=None, ask_label=False):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumSize(460, 440)
        self.fetch, self.chosen_id = fetch, None
        lay = QVBoxLayout(self)
        self.search = SearchBar("Type to filter…")
        self.list = QListWidget()
        self.list.setObjectName("ItemList")
        self.list.itemDoubleClicked.connect(lambda _: self._accept())
        self.label = QLineEdit()
        self.label.setPlaceholderText("Optional label for the connection (e.g. “inspired by”)")
        self.label.setMaxLength(60)
        self.label.setVisible(ask_label)
        self.empty = QLabel("")
        self.empty.setObjectName("CardText")
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        for w in (self.search, self.list, self.empty, self.label, buttons):
            lay.addWidget(w)
        self.search.textChanged.connect(self._reload)
        self._reload()

    def _reload(self, *_):
        self.list.clear()
        items = self.fetch(self.search.text())
        for item_id, text in items:
            row = QListWidgetItem(text)
            row.setData(Qt.UserRole, item_id)
            self.list.addItem(row)
        self.empty.setText("" if items else "Nothing to show here yet.")
        if items:
            self.list.setCurrentRow(0)

    def _accept(self):
        item = self.list.currentItem()
        if item is not None:
            self.chosen_id = item.data(Qt.UserRole)
            self.accept()
