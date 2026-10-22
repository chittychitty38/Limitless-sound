"""Icons drawn in code, so they stay sharp at any size and need no image files."""
from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QFont, QIcon, QLinearGradient, QPainter, QPainterPath, QPixmap

YELLOW = QColor("#ffe600")


def _rounded(painter, rect, radius, brush, pen=Qt.PenStyle.NoPen):
    path = QPainterPath()
    path.addRoundedRect(rect, radius, radius)
    painter.setPen(pen)
    painter.setBrush(brush)
    painter.drawPath(path)


def _label(painter, rect, text, color, weight=QFont.Weight.Black, scale=0.42):
    font = QFont()
    font.setPixelSize(max(6, int(rect.height() * scale)))
    font.setWeight(weight)
    painter.setFont(font)
    painter.setPen(color)
    painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, text)


def app_pixmap(size=1024):
    """The app icon: a yellow key cap marked 1H on a dark tile."""
    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    s = size
    tile = QRectF(s * 0.09, s * 0.09, s * 0.82, s * 0.82)      # macOS icon grid
    bg = QLinearGradient(tile.topLeft(), tile.bottomLeft())
    bg.setColorAt(0, QColor("#2b2b2b"))
    bg.setColorAt(1, QColor("#050505"))
    _rounded(p, tile, s * 0.18, bg)
    cap = QRectF(s * 0.24, s * 0.22, s * 0.52, s * 0.52)
    _rounded(p, cap.translated(0, s * 0.035), s * 0.09, QColor("#8a7d00"))   # key side
    face = QLinearGradient(cap.topLeft(), cap.bottomLeft())
    face.setColorAt(0, QColor("#fff27a"))
    face.setColorAt(1, YELLOW)
    _rounded(p, cap, s * 0.09, face)
    _label(p, cap, "1H", QColor("#111"), scale=0.46)
    bar = QRectF(s * 0.30, s * 0.80, s * 0.40, s * 0.035)     # space bar hint
    _rounded(p, bar, s * 0.017, QColor("#ffe600"))
    p.end()
    return pm


def app_icon():
    icon = QIcon()
    for size in (16, 32, 64, 128, 256, 512):
        icon.addPixmap(app_pixmap(size))
    return icon


def tray_icon(on):
    """Menu bar icon: an outlined key when off, a filled yellow key when on."""
    size = 44
    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    rect = QRectF(3, 5, size - 6, size - 10)
    if on:
        _rounded(p, rect, 8, YELLOW)
        _label(p, rect, "1H", QColor("#000"), scale=0.62)
    else:
        pen = p.pen()
        pen.setColor(QColor("#000"))
        pen.setWidthF(3.5)
        _rounded(p, rect.adjusted(2, 2, -2, -2), 7, Qt.BrushStyle.NoBrush, pen)
        _label(p, rect, "1H", QColor("#000"), scale=0.56)
    p.end()
    icon = QIcon(pm)
    icon.setIsMask(not on)   # lets macOS tint the "off" icon for light and dark menu bars
    return icon
