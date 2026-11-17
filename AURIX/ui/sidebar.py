"""Dark left navigation bar."""
from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtSvgWidgets import QSvgWidget
from PySide6.QtWidgets import (QButtonGroup, QFrame, QHBoxLayout, QLabel,
                               QPushButton, QVBoxLayout)

from core.settings import APP_VERSION, SIGNAL_RED, TITANIUM, WHITE, asset_path
from ui.icons import make_icon

NAV_ITEMS = [  # (key, label)
    ("home", "Home"), ("memory", "Memory"), ("find", "Find"),
    ("flow", "Flow"), ("connect", "Connect"), ("activity", "Activity"),
]


class Sidebar(QFrame):
    page_selected = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("Sidebar")
        self.setFixedWidth(224)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 22, 14, 16)
        lay.setSpacing(4)

        # Brand block: A-mark + wordmark + tagline
        brand = QHBoxLayout()
        mark_path = asset_path("logo", "aurix_mark_light.svg")
        if mark_path.exists():
            mark = QSvgWidget(str(mark_path))
            mark.setFixedSize(48, 32)
            brand.addWidget(mark)
        word = QLabel("AURIX")
        word.setObjectName("BrandWord")
        brand.addWidget(word)
        brand.addStretch(1)
        lay.addLayout(brand)
        tag = QLabel("Your World, Connected.")
        tag.setObjectName("BrandTag")
        lay.addWidget(tag)
        lay.addSpacing(22)

        self.group = QButtonGroup(self)
        self.group.setExclusive(True)
        self.buttons = {}
        for key, label in NAV_ITEMS:
            self._add_button(lay, key, label)

        lay.addStretch(1)
        divider = QFrame()
        divider.setObjectName("SidebarDivider")
        lay.addWidget(divider)
        lay.addSpacing(6)
        self._add_button(lay, "settings", "Settings")
        footer = QLabel(f"v{APP_VERSION}  ·  Local-first")
        footer.setObjectName("SidebarFooter")
        lay.addWidget(footer, alignment=Qt.AlignHCenter)

    def _add_button(self, layout, key, label):
        btn = QPushButton("  " + label)
        btn.setObjectName("NavButton")
        btn.setCheckable(True)
        btn.setCursor(Qt.PointingHandCursor)
        btn.setIcon(make_icon(key, TITANIUM, WHITE))
        btn.setIconSize(QSize(20, 20))
        btn.clicked.connect(lambda _=False, k=key: self.page_selected.emit(k))
        self.group.addButton(btn)
        self.buttons[key] = btn
        layout.addWidget(btn)

    def select(self, key: str) -> None:
        self.buttons[key].setChecked(True)
