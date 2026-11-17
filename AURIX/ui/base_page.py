"""Shared building blocks used by every screen."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QLabel, QScrollArea, QVBoxLayout, QWidget


class BasePage(QWidget):
    """Title + subtitle + body. scroll=True for dashboards, False for split editors."""

    def __init__(self, title: str, subtitle: str, parent=None, scroll: bool = True):
        super().__init__(parent)
        self.setObjectName("Page")
        self.setAttribute(Qt.WA_StyledBackground, True)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        content = QWidget()
        content.setObjectName("PageContent")
        content.setAttribute(Qt.WA_StyledBackground, True)
        root = QVBoxLayout(content)
        root.setContentsMargins(36, 30, 36, 24)
        root.setSpacing(4)
        self.title_label = QLabel(title)
        self.title_label.setObjectName("PageTitle")
        self.subtitle_label = QLabel(subtitle)
        self.subtitle_label.setObjectName("PageSubtitle")
        root.addWidget(self.title_label)
        root.addWidget(self.subtitle_label)
        root.addSpacing(16)

        self.body = QVBoxLayout()
        self.body.setSpacing(16)
        if scroll:
            root.addLayout(self.body)
            root.addStretch(1)
            area = QScrollArea()
            area.setWidgetResizable(True)
            area.setFrameShape(QFrame.NoFrame)
            area.setWidget(content)
            outer.addWidget(area)
        else:
            root.addLayout(self.body, 1)
            outer.addWidget(content)

    def refresh(self) -> None:
        """Called each time the page is shown. Override to reload data."""


def make_card(title: str | None = None):
    """Returns (card, content_layout). Put your widgets in content_layout."""
    card = QFrame()
    card.setObjectName("Card")
    outer = QVBoxLayout(card)
    outer.setContentsMargins(20, 16, 20, 16)
    outer.setSpacing(8)
    if title:
        label = QLabel(title)
        label.setObjectName("CardTitle")
        outer.addWidget(label)
    content = QVBoxLayout()
    content.setSpacing(6)
    outer.addLayout(content)
    return card, content
