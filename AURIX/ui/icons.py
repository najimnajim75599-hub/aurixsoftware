"""One consistent line-icon set (24x24 grid, 1.8px stroke), drawn as SVG
and rendered to QIcon in any colour. No external icon files needed."""
from PySide6.QtCore import QByteArray, Qt
from PySide6.QtGui import QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

_PATHS = {
    "home": '<path d="M3 11l9-8 9 8"/><path d="M5 10v10h14V10"/>',
    "memory": '<rect x="5" y="3" width="14" height="18" rx="2"/><path d="M9 8h6M9 12h6M9 16h4"/>',
    "find": '<circle cx="11" cy="11" r="7"/><path d="M21 21l-5-5"/>',
    "flow": '<rect x="3" y="4" width="5" height="16" rx="1"/><rect x="10" y="4" width="5" height="10" rx="1"/><rect x="17" y="4" width="4" height="6" rx="1"/>',
    "connect": '<circle cx="6" cy="6" r="2.5"/><circle cx="18" cy="8" r="2.5"/><circle cx="12" cy="18" r="2.5"/><path d="M8 7l8 1M7.5 8l3 8M16.5 10l-3 6"/>',
    "activity": '<path d="M3 12h4l3-8 4 16 3-8h4"/>',
    "settings": '<circle cx="12" cy="12" r="3"/><path d="M12 2v3M12 19v3M2 12h3M19 12h3M4.9 4.9l2.1 2.1M17 17l2.1 2.1M4.9 19.1L7 17M17 7l2.1-2.1"/>',
}


def _pixmap(name: str, color: str, size: int = 40) -> QPixmap:
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" '
           f'stroke="{color}" stroke-width="1.8" stroke-linecap="round" '
           f'stroke-linejoin="round">{_PATHS[name]}</svg>')
    pix = QPixmap(size, size)
    pix.fill(Qt.transparent)
    painter = QPainter(pix)
    QSvgRenderer(QByteArray(svg.encode())).render(painter)
    painter.end()
    return pix


def make_icon(name: str, color: str, active_color: str | None = None) -> QIcon:
    """Icon with a normal colour and (optionally) a different colour when checked."""
    icon = QIcon()
    icon.addPixmap(_pixmap(name, color), QIcon.Normal, QIcon.Off)
    icon.addPixmap(_pixmap(name, active_color or color), QIcon.Normal, QIcon.On)
    return icon
