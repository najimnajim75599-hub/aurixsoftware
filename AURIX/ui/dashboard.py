"""Home dashboard: greeting, search, quick actions, summary, recent items, suggestions."""
import os
from datetime import date, datetime, timedelta

from PySide6.QtCore import QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QGridLayout, QHBoxLayout, QLabel

from ui.base_page import BasePage, make_card
from ui.components import ActionTile, EmptyState, ListRow, SearchBar, StatCard, clear_layout


class DashboardPage(BasePage):
    open_page = Signal(str)
    search_requested = Signal(str)
    new_note = Signal()
    add_folder = Signal()
    open_note = Signal(int)
    new_project = Signal()
    open_project = Signal(int)

    def __init__(self, ctx, parent=None):
        super().__init__("Welcome", "Your ideas, projects and files, all in one place.", parent)
        self.ctx = ctx

        self.search = SearchBar("Search by description, not just filename…")
        self.search.submitted.connect(self.search_requested)
        self.body.addWidget(self.search)

        tiles = QHBoxLayout()
        tiles.setSpacing(14)
        for icon, title, sub, handler in [
            ("memory", "New Note", "Save an idea", self.new_note.emit),
            ("find", "Search", "Find anything", lambda: self.search_requested.emit("")),
            ("connect", "Add Folder", "Make files searchable", self.add_folder.emit),
            ("flow", "New Project", "Plan your next step", self.new_project.emit),
        ]:
            tile = ActionTile(icon, title, sub)
            tile.clicked.connect(handler)
            tiles.addWidget(tile)
        self.body.addLayout(tiles)

        stats = QHBoxLayout()
        stats.setSpacing(14)
        self.stats = {}
        for key, label in [("notes", "Notes & ideas"), ("files", "Indexed files"),
                           ("projects", "Projects"), ("tasks", "Open tasks")]:
            self.stats[key] = StatCard(label)
            stats.addWidget(self.stats[key])
        self.body.addLayout(stats)

        grid = QGridLayout()
        grid.setSpacing(14)
        self.cards = {}
        for i, (key, title) in enumerate([("projects", "Recent projects"), ("files", "Recent files"),
                                          ("notes", "Important notes"), ("activity", "Recent activity")]):
            card, content = make_card(title)
            self.cards[key] = content
            grid.addWidget(card, i // 2, i % 2)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        self.body.addLayout(grid)

        card, self.tips = make_card("Suggestions")
        self.body.addWidget(card)

    def refresh(self) -> None:
        db = self.ctx.db
        hour = datetime.now().hour
        self.title_label.setText("Good morning" if hour < 12 else "Good afternoon" if hour < 18 else "Good evening")

        counts = db.table_counts()
        self.stats["notes"].set_value(counts["notes"])
        self.stats["files"].set_value(counts["files"])
        self.stats["projects"].set_value(counts["projects"])
        self.stats["tasks"].set_value(db.query_one("SELECT COUNT(*) FROM tasks WHERE status != 'done'")[0])

        # projects
        rows = []
        for p in self.ctx.projects.list_projects(limit=5):
            row = ListRow(p.name, f"{p.status.replace('_', ' ').title()} · {p.done_tasks}/{p.total_tasks} tasks", f"{p.progress}%", clickable=True)
            row.clicked.connect(lambda i=p.id: self.open_project.emit(i))
            rows.append(row)
        self._fill("projects", rows, "No projects yet", "Create one in Flow to track tasks and progress.")
        # files
        rows = []
        for f in self.ctx.files.recent_files(5):
            row = ListRow(f.name, f"{f.group} · {f.size_text}", f.modified_at[:10], clickable=True)
            row.clicked.connect(lambda f=f: self._open_file(f))
            rows.append(row)
        self._fill("files", rows, "No files yet", "Add a folder to index your files.")
        # important notes
        rows = []
        for n in self.ctx.memory.list_notes(important=True, limit=5):
            row = ListRow(n.title, ", ".join("#" + t for t in n.tags), n.updated_at[:10], clickable=True)
            row.clicked.connect(lambda i=n.id: self.open_note.emit(i))
            rows.append(row)
        self._fill("notes", rows, "No important notes", "Mark a note as important in Memory.")
        # activity
        week = db.query_one("SELECT COUNT(*) FROM activity WHERE created_at >= datetime('now','-7 days','localtime')")[0]
        rows = [ListRow(r["summary"], right=r["created_at"][5:16])
                for r in db.query_all("SELECT summary, created_at FROM activity ORDER BY id DESC LIMIT 5")]
        self._fill("activity", rows, "No activity yet", "Your actions will appear here.")
        if rows:
            note = QLabel(f"{week} action(s) in the last 7 days")
            note.setObjectName("CardText")
            self.cards["activity"].addWidget(note)
        self._suggestions(counts)

    def _fill(self, key, widgets, empty_title, empty_text):
        layout = self.cards[key]
        clear_layout(layout)
        if widgets:
            for w in widgets:
                layout.addWidget(w)
        else:
            layout.addWidget(EmptyState(empty_title, empty_text))

    def _suggestions(self, counts):
        clear_layout(self.tips)
        tips = []
        if not self.ctx.files.list_folders():
            tips.append("Add a folder in Find so AURIX can make your files searchable. You choose which folders.")
        elif (n := self.ctx.files.undescribed_count()):
            tips.append(f"{n} indexed file(s) have no description. A short description makes them easier to find.")
        if counts["notes"] == 0:
            tips.append("Write your first note in Memory. Tags help you find it later.")
        today = date.today().isoformat()
        late = self.ctx.db.query_one("SELECT COUNT(*) FROM tasks WHERE status != 'done' AND deadline < ?", (today,))[0]
        soon = self.ctx.db.query_one("SELECT COUNT(*) FROM tasks WHERE status != 'done' AND deadline BETWEEN ? AND ?",
                                     (today, (date.today() + timedelta(days=7)).isoformat()))[0]
        if late:
            tips.append(f"{late} task(s) are past their deadline. Open Flow to update them.")
        if soon:
            tips.append(f"{soon} task(s) are due in the next 7 days.")
        if counts["projects"] == 0 and counts["notes"] > 0:
            tips.append("Turn an idea into a project in Flow, then attach your notes to it.")
        if not tips:
            tips.append("You are all set. Keep adding notes and descriptions to make search more useful.")
        for t in tips:
            label = QLabel("•  " + t)
            label.setObjectName("CardText")
            label.setWordWrap(True)
            self.tips.addWidget(label)

    def _open_file(self, f):
        if os.path.exists(f.path):
            QDesktopServices.openUrl(QUrl.fromLocalFile(f.path))
            self.ctx.files.touch_opened(f.id)
        else:
            self.ctx.notifier.error("That file was not found. It may have been moved or deleted.")
