"""AURIX Activity: a timeline of what changed and when. Only actions done inside AURIX are recorded."""
from datetime import date, timedelta

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import QButtonGroup, QComboBox, QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QPushButton

from core.activity_manager import FILTERS, RANGES
from ui.base_page import BasePage

ICONS = {"created": "＋", "updated": "✎", "deleted": "✕", "completed": "✔", "task_done": "✔", "task_added": "＋",
         "task_updated": "↻", "task_deleted": "✕", "indexed": "⟳", "added": "＋", "removed": "✕", "connected": "⇄"}


def day_label(day: str) -> str:
    try:
        d = date.fromisoformat(day)
    except ValueError:
        return day
    if d == date.today():
        return "Today"
    if d == date.today() - timedelta(days=1):
        return "Yesterday"
    return d.strftime("%A, %d %B %Y")


class ActivityPage(BasePage):
    def __init__(self, ctx, parent=None):
        super().__init__("Activity", "What changed, and when", parent, scroll=False)
        self.ctx = ctx
        self.group = "All"

        bar = QHBoxLayout()
        bar.setSpacing(6)
        self.chips = QButtonGroup(self)
        for name in FILTERS:
            b = QPushButton(name)
            b.setObjectName("Chip")
            b.setCheckable(True)
            b.setChecked(name == "All")
            b.clicked.connect(lambda _=False, n=name: self._set_group(n))
            self.chips.addButton(b)
            bar.addWidget(b)
        bar.addStretch(1)
        self.range = QComboBox()
        self.range.addItems(list(RANGES))
        self.range.currentIndexChanged.connect(lambda _: self.refresh())
        bar.addWidget(self.range)
        self.body.addLayout(bar)

        self.recording = QLabel("")
        self.recording.setObjectName("CardText")
        self.body.addWidget(self.recording)
        self.list = QListWidget()
        self.list.setObjectName("ItemList")
        self.list.setSelectionMode(QListWidget.NoSelection)
        self.body.addWidget(self.list, 1)
        self.empty = QLabel("")
        self.empty.setObjectName("CardText")
        self.empty.setAlignment(Qt.AlignCenter)
        self.empty.setWordWrap(True)
        self.body.addWidget(self.empty)

    def _set_group(self, name):
        self.group = name
        self.refresh()

    def refresh(self) -> None:
        on = self.ctx.db.activity_enabled()
        self.recording.setText("Recording is on. Only actions you take inside AURIX are saved on this computer."
                               if on else "Recording is paused (Settings → Privacy). New actions are not being saved.")
        rows = self.ctx.activity.list(self.group, self.range.currentText())
        self.list.clear()
        last_day = None
        bold = QFont()
        bold.setBold(True)
        for r in rows:
            day = r["created_at"][:10]
            if day != last_day:
                head = QListWidgetItem(day_label(day))
                head.setFlags(Qt.NoItemFlags)
                head.setFont(bold)
                head.setForeground(QColor("#780D18"))
                self.list.addItem(head)
                last_day = day
            icon = ICONS.get(r["event_type"], "•")
            item = QListWidgetItem(f"   {r['created_at'][11:16]}    {icon}   {r['summary']}")
            item.setFlags(Qt.ItemIsEnabled)
            self.list.addItem(item)
        self.list.setVisible(bool(rows))
        self.empty.setVisible(not rows)
        self.empty.setText("Nothing here yet. As you create notes, projects and tasks, they will appear on this timeline."
                           if self.group == "All" and self.range.currentIndex() == 0 else
                           "No activity matches this filter.")
