"""AURIX Connect: an interactive knowledge graph of files, projects, notes, ideas and tasks.
Drag nodes, scroll or use the buttons to zoom, click a node to see and edit its connections."""
import os

from PySide6.QtCore import QRectF, Qt, QUrl, Signal
from PySide6.QtGui import QBrush, QColor, QDesktopServices, QFont, QPainter, QPen
from PySide6.QtWidgets import (QComboBox, QGraphicsEllipseItem, QGraphicsItem, QGraphicsLineItem, QGraphicsScene,
                               QGraphicsSimpleTextItem, QGraphicsView, QHBoxLayout, QInputDialog,
                               QLabel, QListWidget, QListWidgetItem, QPushButton, QVBoxLayout, QWidget)

from core.errors import ValidationError
from ui.base_page import BasePage, make_card
from ui.components import PickerDialog

# type -> (fill, border, radius, human label)
STYLE = {
    "project": ("#C51F32", "#780D18", 17, "Project"),
    "note":    ("#080808", "#080808", 12, "Note"),
    "idea":    ("#780D18", "#780D18", 12, "Idea"),
    "file":    ("#C5C5C5", "#8A8A8A", 11, "File"),
    "task":    ("#FFFFFF", "#C51F32", 9, "Task"),
}
LABEL_ORDER = ["project", "note", "idea", "file", "task"]


class EdgeItem(QGraphicsLineItem):
    def __init__(self, a, b, label=""):
        super().__init__()
        self.a, self.b, self.label_text = a, b, label
        self.setPen(QPen(QColor("#C5C5C5"), 1.6))
        self.setZValue(0)
        self.text = None
        if label and label != "has task":
            self.text = QGraphicsSimpleTextItem(label, self)
            self.text.setBrush(QBrush(QColor("#8A8A8A")))
            f = QFont("Segoe UI", 7)
            self.text.setFont(f)
        self.update_position()

    def update_position(self):
        p1, p2 = self.a.pos(), self.b.pos()
        self.setLine(p1.x(), p1.y(), p2.x(), p2.y())
        if self.text:
            mid = (p1 + p2) / 2
            self.text.setPos(mid.x() + 4, mid.y() - 12)

    def set_highlight(self, on):
        self.setPen(QPen(QColor("#C51F32") if on else QColor("#C5C5C5"), 2.2 if on else 1.6))
        self.setZValue(1 if on else 0)


class NodeItem(QGraphicsEllipseItem):
    def __init__(self, key, title, x, y):
        fill, border, r, _ = STYLE[key[0]]
        super().__init__(-r, -r, 2 * r, 2 * r)
        self.key, self.radius = key, r
        self.edges = []
        self.setPos(x, y)
        self.setBrush(QBrush(QColor(fill)))
        self.setPen(QPen(QColor(border), 2))
        self.setZValue(2)
        flag = QGraphicsItem.GraphicsItemFlag
        self.setFlags(flag.ItemIsMovable | flag.ItemIsSelectable | flag.ItemSendsGeometryChanges)
        self.setAcceptHoverEvents(True)
        self.setCursor(Qt.PointingHandCursor)
        short = title if len(title) <= 24 else title[:23] + "…"
        self.label = QGraphicsSimpleTextItem(short, self)
        self.label.setFont(QFont("Segoe UI", 8))
        self.label.setBrush(QBrush(QColor("#080808")))
        w = self.label.boundingRect().width()
        self.label.setPos(-w / 2, r + 3)
        self.setToolTip(title)

    def itemChange(self, change, value):
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged:
            for e in self.edges:
                e.update_position()
        return super().itemChange(change, value)

    def paint(self, painter, option, widget=None):
        # Drawn by hand so Qt's default rectangular selection box does not appear.
        painter.setBrush(self.brush())
        painter.setPen(self.pen())
        painter.drawEllipse(self.rect())
        if self.isSelected():
            painter.setPen(QPen(QColor("#C51F32"), 2, Qt.DashLine))
            painter.setBrush(Qt.NoBrush)
            r = self.radius + 6
            painter.drawEllipse(QRectF(-r, -r, 2 * r, 2 * r))

    def hoverEnterEvent(self, e):
        self.setScale(1.12)
        super().hoverEnterEvent(e)

    def hoverLeaveEvent(self, e):
        self.setScale(1.0)
        super().hoverLeaveEvent(e)


class GraphView(QGraphicsView):
    def __init__(self, scene):
        super().__init__(scene)
        self.setRenderHint(QPainter.Antialiasing)
        self.setDragMode(QGraphicsView.ScrollHandDrag)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.setBackgroundBrush(QBrush(QColor("#FAFAFA")))
        self.setObjectName("Graph")
        self._zoom = 1.0

    def zoom_by(self, factor):
        new = self._zoom * factor
        if 0.15 <= new <= 4.0:
            self._zoom = new
            self.scale(factor, factor)

    def wheelEvent(self, event):
        self.zoom_by(1.15 if event.angleDelta().y() > 0 else 1 / 1.15)

    def fit(self):
        rect = self.scene().itemsBoundingRect()
        if rect.isEmpty():
            return
        self.resetTransform()
        self.fitInView(rect.adjusted(-50, -50, 50, 50), Qt.KeepAspectRatio)
        self._zoom = self.transform().m11()
        if self._zoom > 1.5:  # a tiny graph should not be blown up
            self.resetTransform()
            self.scale(1.5, 1.5)
            self._zoom = 1.5
            self.centerOn(rect.center())


class ConnectPage(BasePage):
    open_note = Signal(int)
    open_project = Signal(int)

    def __init__(self, ctx, parent=None):
        super().__init__("Connect", "See how your files, projects, notes, ideas and tasks relate", parent, scroll=False)
        self.ctx, self.rel = ctx, ctx.relations
        self.nodes = {}
        self.edge_items = []
        self.selected = None
        self.scene = QGraphicsScene(self)
        self.scene.selectionChanged.connect(self._on_selection)

        row = QHBoxLayout()
        row.setSpacing(18)
        self.body.addLayout(row, 1)

        # ---- graph side ----
        gcol = QVBoxLayout()
        gcol.setSpacing(8)
        tools = QHBoxLayout()
        for text, handler in (("＋", lambda: self.view.zoom_by(1.25)), ("－", lambda: self.view.zoom_by(0.8)),
                              ("Fit", lambda: self.view.fit()), ("Re-arrange", self._rearrange)):
            b = QPushButton(text)
            b.clicked.connect(handler)
            if len(text) == 1:
                b.setFixedWidth(40)
            tools.addWidget(b)
        tools.addStretch(1)
        self.legend = QLabel("  ".join(f'<span style="color:{STYLE[t][0] if t != "task" else "#C51F32"}">●</span> {STYLE[t][3]}'
                                      for t in LABEL_ORDER))
        self.legend.setObjectName("CardText")
        tools.addWidget(self.legend)
        gcol.addLayout(tools)
        self.view = GraphView(self.scene)
        gcol.addWidget(self.view, 1)
        self.stats = QLabel("")
        self.stats.setObjectName("CardText")
        gcol.addWidget(self.stats)
        row.addLayout(gcol, 1)

        # ---- details side ----
        side = QWidget()
        side.setFixedWidth(340)
        scol = QVBoxLayout(side)
        scol.setContentsMargins(0, 0, 0, 0)
        card, d = make_card("Selected item")
        self.d_type = QLabel("")
        self.d_type.setObjectName("Badge")
        self.d_title = QLabel("Click a node in the graph")
        self.d_title.setObjectName("RowTitle")
        self.d_title.setWordWrap(True)
        self.d_sub = QLabel("")
        self.d_sub.setObjectName("CardText")
        self.d_sub.setWordWrap(True)
        self.d_detail = QLabel("")
        self.d_detail.setWordWrap(True)
        self.d_detail.setTextInteractionFlags(Qt.TextSelectableByMouse)
        for w in (self.d_type, self.d_title, self.d_sub, self.d_detail):
            d.addWidget(w)
        self.d_type.setVisible(False)
        self.open_btn = QPushButton("Open")
        self.open_btn.clicked.connect(self._open_selected)
        d.addWidget(self.open_btn)
        scol.addWidget(card)

        lcard, l = make_card("Connections")
        self.links = QListWidget()
        self.links.setObjectName("ItemList")
        self.links.setMinimumHeight(120)
        self.links.currentItemChanged.connect(lambda *_: self._update_buttons())
        l.addWidget(self.links, 1)
        self.type_combo = QComboBox()
        for t in LABEL_ORDER:
            self.type_combo.addItem(f"Connect to a {STYLE[t][3].lower()}…", t)
        self.connect_btn = QPushButton("Connect")
        self.connect_btn.setObjectName("Primary")
        self.connect_btn.clicked.connect(self._connect)
        self.disconnect_btn = QPushButton("Remove connection")
        self.disconnect_btn.setObjectName("Danger")
        self.disconnect_btn.clicked.connect(self._disconnect)
        l.addWidget(self.type_combo)
        r = QHBoxLayout()
        r.addWidget(self.connect_btn)
        r.addWidget(self.disconnect_btn)
        l.addLayout(r)
        scol.addWidget(lcard, 1)

        acard, a = make_card("Add")
        r2 = QHBoxLayout()
        self.new_idea_btn = QPushButton("New idea")
        self.new_proj_btn = QPushButton("New project")
        self.new_idea_btn.clicked.connect(self._new_idea)
        self.new_proj_btn.clicked.connect(self._new_project)
        r2.addWidget(self.new_idea_btn)
        r2.addWidget(self.new_proj_btn)
        a.addLayout(r2)
        tip = QLabel("Files appear in the graph once you connect them. Notes and projects always show.")
        tip.setObjectName("CardText")
        tip.setWordWrap(True)
        a.addWidget(tip)
        scol.addWidget(acard)
        row.addWidget(side)
        self._show_selection(None)

    # ---------- public ----------
    def refresh(self) -> None:
        keep = self.selected
        self._build()
        if keep in self.nodes:
            self.nodes[keep].setSelected(True)
        else:
            self._show_selection(None)

    def reset(self) -> None:
        self.selected = None

    def focus_node(self, ntype, nid):
        self.refresh()
        item = self.nodes.get((ntype, nid))
        if item:
            item.setSelected(True)
            self.view.centerOn(item)

    # ---------- graph ----------
    def _build(self, rearrange=False):
        self.scene.blockSignals(True)
        self.scene.clear()
        self.scene.blockSignals(False)
        self.nodes, self.edge_items = {}, []
        data_nodes, data_edges = self.rel.graph()
        for key, n in data_nodes.items():
            item = NodeItem(key, n["title"], n["x"], n["y"])
            self.scene.addItem(item)
            self.nodes[key] = item
        for a, b, label in data_edges:
            edge = EdgeItem(self.nodes[a], self.nodes[b], label)
            self.nodes[a].edges.append(edge)
            self.nodes[b].edges.append(edge)
            self.scene.addItem(edge)
            self.edge_items.append(edge)
        self.scene.setSceneRect(self.scene.itemsBoundingRect().adjusted(-400, -400, 400, 400))
        self.stats.setText(f"{len(self.nodes)} item(s), {len(self.edge_items)} connection(s)"
                           if self.nodes else "Nothing to show yet. Create notes or projects, then connect them here.")
        self.view.fit()

    def _rearrange(self):
        self.selected = None
        self._build()

    def _on_selection(self):
        items = [i for i in self.scene.selectedItems() if isinstance(i, NodeItem)]
        self._show_selection(items[0].key if items else None)

    def _show_selection(self, key):
        self.selected = key
        for e in self.edge_items:
            e.set_highlight(key is not None and key in ((e.a.key), (e.b.key)))
        info = self.rel.node_info(*key) if key else None
        has = info is not None
        self.d_type.setVisible(has)
        for w in (self.type_combo, self.connect_btn, self.open_btn):
            w.setEnabled(has)
        self.links.clear()
        if not has:
            self.selected = None
            self.d_title.setText("Click a node in the graph")
            self.d_sub.setText("")
            self.d_detail.setText("")
            self._update_buttons()
            return
        self.d_type.setText(STYLE[key[0]][3])
        self.d_title.setText(info["title"])
        self.d_sub.setText(info["subtitle"])
        self.d_detail.setText(info["detail"])
        self.open_btn.setVisible(key[0] != "task")
        for link in self.rel.links_for(*key):
            o = link["other"]
            label = f" ({link['label']})" if link["label"] and link["label"] != "attached" else ""
            item = QListWidgetItem(f"{STYLE[o['type']][3]}: {o['title']}{label}")
            item.setData(Qt.UserRole, link["relation_id"])
            self.links.addItem(item)
        self._update_buttons()

    def _update_buttons(self):
        self.disconnect_btn.setEnabled(self.links.currentItem() is not None)

    # ---------- actions ----------
    def _connect(self):
        if not self.selected:
            return
        kind = self.type_combo.currentData()
        dlg = PickerDialog(f"Connect to a {STYLE[kind][3].lower()}",
                           lambda q: self.rel.candidates(kind, q), self, ask_label=True)
        if dlg.exec() != PickerDialog.Accepted or dlg.chosen_id is None:
            return
        try:
            self.rel.connect(*self.selected, kind, dlg.chosen_id, dlg.label.text())
        except ValidationError as exc:
            self.ctx.notifier.error(str(exc))
            return
        keep = self.selected
        self._build()
        if keep in self.nodes:
            self.nodes[keep].setSelected(True)
        self.ctx.notifier.success("Connected")

    def _disconnect(self):
        item = self.links.currentItem()
        if item is None:
            return
        self.rel.disconnect(item.data(Qt.UserRole))
        keep = self.selected
        self._build()
        if keep in self.nodes:
            self.nodes[keep].setSelected(True)

    def _open_selected(self):
        if not self.selected:
            return
        kind, oid = self.selected
        if kind in ("note", "idea"):
            self.open_note.emit(oid)
        elif kind == "project":
            self.open_project.emit(oid)
        elif kind == "file":
            f = self.ctx.files.get_file(oid)
            if f and os.path.exists(f.path):
                QDesktopServices.openUrl(QUrl.fromLocalFile(f.path))
                self.ctx.files.touch_opened(f.id)
            else:
                self.ctx.notifier.error("File not found. It may have been moved or deleted.")

    def _new_idea(self):
        title, ok = QInputDialog.getText(self, "New idea", "Title of the idea:")
        if not ok:
            return
        try:
            nid = self.ctx.memory.save_note(title, "", "idea")
        except ValidationError as exc:
            self.ctx.notifier.error(str(exc))
            return
        self._build()
        self.focus_node("idea", nid)

    def _new_project(self):
        name, ok = QInputDialog.getText(self, "New project", "Project name:")
        if not ok:
            return
        try:
            pid = self.ctx.projects.save_project(name)
        except ValidationError as exc:
            self.ctx.notifier.error(str(exc))
            return
        self._build()
        self.focus_node("project", pid)
