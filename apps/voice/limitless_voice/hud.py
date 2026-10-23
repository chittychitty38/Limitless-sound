"""The on-screen display: a small floating card near the bottom of the screen
showing what was heard and what happened, like macOS Voice Control's.

It never takes focus, so Logic or Pro Tools keeps receiving the commands,
and it lets clicks pass through to whatever is underneath. It follows the
window's text size and high contrast, and with reduced motion it disappears
at once instead of fading.
"""

from PySide6.QtCore import QAbstractAnimation, QEasingCurve, QPropertyAnimation, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QGuiApplication, QPainter, QPen, QPixmap, QIcon
from PySide6.QtWidgets import QGraphicsOpacityEffect, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from .look import LiveText, sized

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
        self.setWindowTitle("Limitless Voice")   # a window it draws itself: named for screen readers
        self.setAccessibleName("What Limitless Voice heard")

        self.dot = QLabel()
        # sized even at the normal size: labels with a style sheet of their own keep their
        # first font unless it's set again when the text size changes
        self.state_label = sized(LiveText("Listening state"), 1.0)
        self.heard = sized(LiveText("Heard"), 1.5, bold=True)
        self.did = sized(LiveText("What happened"), 1.0)
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
        self.state = "awake"
        self.ok = True
        self.set_look(1.0)

    def set_look(self, scale, high_contrast=False, reduce_motion=False):
        """The text itself is sized for every window at once (look.resize_text); this
        sizes the card and its dot to match, and sets the colours and motion."""
        self.scale, self.high_contrast, self.reduce_motion = scale, high_contrast, reduce_motion
        self.setFixedWidth(int(460 * max(1.0, scale)))
        self.dot.setFixedSize(int(14 * max(1.0, scale)), int(14 * max(1.0, scale)))
        self.set_state(self.state)
        self._colour_did()
        if reduce_motion and self.fade.state() == QAbstractAnimation.Running:
            self.fade_out()   # a fade already under way ends at once
        if self.isVisible():
            self.adjustSize()
            self._place()
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        if self.high_contrast:
            # solid black with a thick yellow edge, like the window's high-contrast theme
            p.setPen(QPen(QColor("#ffeb3b"), 3))
            p.setBrush(QColor("#000"))
            p.drawRoundedRect(QRectF(self.rect()).adjusted(1.5, 1.5, -1.5, -1.5), 18, 18)
            return
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(20, 20, 24, 225))
        p.drawRoundedRect(self.rect(), 18, 18)

    def set_state(self, state):
        self.state = state
        colour, label = STATES.get(state, STATES["asleep"])
        size = self.dot.width()
        edge = "border: 2px solid white;" if self.high_contrast else ""
        self.dot.setStyleSheet(f"background: {colour}; border-radius: {size // 2}px; {edge}")
        self.state_label.setText(label)

    def _colour_did(self):
        if self.high_contrast:
            colour = "#ffffff" if self.ok else "#ffeb3b"
        else:
            colour = "#9ef0a8" if self.ok else "#ffd479"
        self.did.setStyleSheet(f"color: {colour}; background: transparent;")

    def show_message(self, heard, did, ok=True, seconds=3.0):
        self.heard.setText(f"“{heard}”" if heard else "")
        self.heard.setVisible(bool(heard))
        mark = "✓ " if ok else ""
        self.did.setText(mark + did if did else "")
        self.ok = ok
        self._colour_did()
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
        if self.reduce_motion:
            self.hide()
            return
        self.fade.setStartValue(self.opacity.opacity())
        self.fade.setEndValue(0.0)
        self.fade.start()

    def _fade_done(self):
        if self.opacity.opacity() < 0.05:
            self.hide()
