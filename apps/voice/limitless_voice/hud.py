"""The on-screen display: a small floating card near the bottom of the screen
showing what was heard and what happened, like macOS Voice Control's.

It never takes focus, so Logic or Pro Tools keeps receiving the commands,
and it lets clicks pass through to whatever is underneath.
"""

from PySide6.QtCore import QEasingCurve, QPropertyAnimation, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QGuiApplication, QPainter, QPixmap, QIcon
from PySide6.QtWidgets import QGraphicsOpacityEffect, QHBoxLayout, QLabel, QVBoxLayout, QWidget

# state -> (dot colour, label)
STATES = {
    "awake": ("#34c759", "Listening"),
    "asleep": ("#8e8e93", "Asleep"),
    "take": ("#ff3b30", "Take mode"),
    "dictating": ("#0a84ff", "Dictating"),
}


def state_icon(state, size=64):
    """A round coloured dot with a mic, for the menu bar and the window."""
    colour = QColor(STATES.get(state, STATES["asleep"])[0])
    pix = QPixmap(size, size)
    pix.fill(Qt.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.Antialiasing)
    p.setPen(Qt.NoPen)
    p.setBrush(colour)
    p.drawEllipse(4, 4, size - 8, size - 8)
    p.setBrush(QColor("white"))
    w, h = size * 0.22, size * 0.36
    p.drawRoundedRect(int(size / 2 - w / 2), int(size * 0.2), int(w), int(h), w / 2, w / 2)
    pen = p.pen()
    pen.setColor(QColor("white"))
    pen.setWidthF(size * 0.06)
    p.setPen(pen)
    p.setBrush(Qt.NoBrush)
    p.drawArc(int(size * 0.3), int(size * 0.32), int(size * 0.4), int(size * 0.34), 180 * 16, 180 * 16)
    p.drawLine(int(size / 2), int(size * 0.66), int(size / 2), int(size * 0.78))
    p.end()
    return QIcon(pix)


class Hud(QWidget):
    def __init__(self):
        super().__init__(None, Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint
                         | Qt.WindowDoesNotAcceptFocus | Qt.WindowTransparentForInput)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_MacAlwaysShowToolWindow)
        self.setFocusPolicy(Qt.NoFocus)

        self.dot = QLabel()
        self.dot.setFixedSize(14, 14)
        self.state_label = QLabel()
        self.heard = QLabel()
        self.did = QLabel()
        for lbl in (self.state_label, self.heard, self.did):
            lbl.setStyleSheet("color: white; background: transparent;")
        self.heard.setWordWrap(True)
        self.did.setWordWrap(True)

        top = QHBoxLayout()
        top.addWidget(self.dot)
        top.addWidget(self.state_label)
        top.addStretch(1)
        box = QVBoxLayout(self)
        box.setContentsMargins(20, 14, 20, 14)
        box.addLayout(top)
        box.addWidget(self.heard)
        box.addWidget(self.did)

        self.opacity = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self.opacity)
        self.fade = QPropertyAnimation(self.opacity, b"opacity", self)
        self.fade.setDuration(400)
        self.fade.setEasingCurve(QEasingCurve.InOutQuad)
        self.fade.finished.connect(self._fade_done)
        self.hide_timer = QTimer(self, singleShot=True)
        self.hide_timer.timeout.connect(self.fade_out)
        self.scale = 1.0
        self.state = "awake"
        self.set_scale(1.0)

    def set_scale(self, scale):
        self.scale = scale
        base = QFont()
        big = QFont(base)
        big.setPointSizeF(base.pointSizeF() * 1.5 * scale)
        big.setBold(True)
        small = QFont(base)
        small.setPointSizeF(base.pointSizeF() * 1.0 * scale)
        self.heard.setFont(big)
        self.did.setFont(small)
        self.state_label.setFont(small)
        self.setFixedWidth(int(460 * max(1.0, scale)))

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(20, 20, 24, 225))
        p.drawRoundedRect(self.rect(), 18, 18)

    def set_state(self, state):
        self.state = state
        colour, label = STATES.get(state, STATES["asleep"])
        self.dot.setStyleSheet(f"background: {colour}; border-radius: 7px;")
        self.state_label.setText(label)

    def show_message(self, heard, did, ok=True, seconds=3.0):
        self.heard.setText(f"“{heard}”" if heard else "")
        self.heard.setVisible(bool(heard))
        mark = "✓ " if ok else ""
        self.did.setText(mark + did if did else "")
        self.did.setStyleSheet("color: %s; background: transparent;" % ("#9ef0a8" if ok else "#ffd479"))
        self.adjustSize()
        self._place()
        self.fade.stop()
        self.opacity.setOpacity(1.0)
        self.show()   # no raise_(): on a Mac that would pull focus away from the DAW
        self.hide_timer.start(int(seconds * 1000))

    def _place(self):
        screen = QGuiApplication.primaryScreen()
        if screen is None:
            return
        area = screen.availableGeometry()
        self.move(area.center().x() - self.width() // 2, area.bottom() - self.height() - 60)

    def fade_out(self):
        self.fade.stop()
        self.fade.setStartValue(self.opacity.opacity())
        self.fade.setEndValue(0.0)
        self.fade.start()

    def _fade_done(self):
        if self.opacity.opacity() < 0.05:
            self.hide()
