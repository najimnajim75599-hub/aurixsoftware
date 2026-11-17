"""Main window: sidebar on the left, stacked pages on the right."""
from PySide6.QtCore import QPropertyAnimation, Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QGraphicsOpacityEffect, QHBoxLayout, QMainWindow, QStackedWidget, QWidget

from core.settings import APP_NAME, TAGLINE, asset_path
from ui.activity import ActivityPage
from ui.connect import ConnectPage
from ui.dashboard import DashboardPage
from ui.find import FindPage
from ui.flow import FlowPage
from ui.memory import MemoryPage
from ui.settings import SettingsPage
from ui.sidebar import Sidebar


class MainWindow(QMainWindow):
    def __init__(self, ctx):
        super().__init__()
        self.ctx = ctx
        self.setWindowTitle(f"{APP_NAME} — {TAGLINE}")
        self.resize(1280, 800)
        self.setMinimumSize(1050, 660)
        logo = asset_path("logo", "aurix_logo.png")
        if logo.exists():
            self.setWindowIcon(QIcon(str(logo)))

        central = QWidget()
        central.setObjectName("Content")
        central.setAttribute(Qt.WA_StyledBackground, True)
        row = QHBoxLayout(central)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(0)
        self.setCentralWidget(central)
        self.sidebar = Sidebar()
        self.stack = QStackedWidget()
        row.addWidget(self.sidebar)
        row.addWidget(self.stack, 1)

        self.pages = {
            "home": DashboardPage(ctx),
            "memory": MemoryPage(ctx),
            "find": FindPage(ctx),
            "flow": FlowPage(ctx),
            "connect": ConnectPage(ctx),
            "activity": ActivityPage(ctx),
            "settings": SettingsPage(ctx),
        }
        for page in self.pages.values():
            self.stack.addWidget(page)

        home = self.pages["home"]
        home.open_page.connect(self.show_page)
        home.search_requested.connect(self._go_search)
        home.new_note.connect(self._go_new_note)
        home.add_folder.connect(self._go_add_folder)
        home.open_note.connect(self._go_note)
        home.new_project.connect(self._go_new_project)
        home.open_project.connect(self._go_project)
        self.pages["find"].open_note.connect(self._go_note)
        self.pages["flow"].open_note.connect(self._go_note)
        self.pages["connect"].open_note.connect(self._go_note)
        self.pages["connect"].open_project.connect(self._go_project)
        self.pages["settings"].data_replaced.connect(self._data_replaced)

        ctx.notifier.message.connect(self._toast)
        self.sidebar.page_selected.connect(self.show_page)
        self.show_page("home")

    def show_page(self, key: str) -> None:
        page = self.pages[key]
        self.sidebar.select(key)
        self.stack.setCurrentWidget(page)
        page.refresh()
        self._fade_in(page)

    def _fade_in(self, page) -> None:
        """A short fade when changing pages. The effect is removed again afterwards."""
        effect = QGraphicsOpacityEffect(page)
        page.setGraphicsEffect(effect)
        anim = QPropertyAnimation(effect, b"opacity", page)
        anim.setDuration(160)
        anim.setStartValue(0.0)
        anim.setEndValue(1.0)
        anim.finished.connect(lambda: page.setGraphicsEffect(None))
        anim.start(QPropertyAnimation.DeleteWhenStopped)
        self._anim = anim

    def _go_new_project(self):
        self.show_page("flow")
        self.pages["flow"].new_project()

    def _go_project(self, project_id):
        self.show_page("flow")
        self.pages["flow"].open_project(project_id)

    def _data_replaced(self):
        """Backup restored or data erased: make every page forget what it was showing."""
        for page in self.pages.values():
            if hasattr(page, "reset"):
                page.reset()

    def _go_search(self, text):
        self.show_page("find")
        self.pages["find"].set_query(text)

    def _go_new_note(self):
        self.show_page("memory")
        self.pages["memory"].new_note()

    def _go_add_folder(self):
        self.show_page("find")
        self.pages["find"].add_folder()

    def _go_note(self, note_id):
        self.show_page("memory")
        self.pages["memory"].open_note(note_id)

    def _toast(self, text, kind):
        prefix = {"success": "✓  ", "error": "⚠  "}.get(kind, "")
        self.statusBar().showMessage(prefix + text, 6000)

    def closeEvent(self, event):
        self.ctx.indexing.stop(wait=True)
        super().closeEvent(event)
