"""On-screen parts: the big-text toast, the "zoom keys on" badge, the
big-button panel (dwell and switch scanning), and the first-run welcome."""

from PySide6.QtCore import QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QPainter
from PySide6.QtWidgets import (QComboBox, QDialog, QGridLayout, QHBoxLayout, QLabel,
                               QPushButton, QVBoxLayout, QWidget)

from .actions import PANEL_BUTTONS

HIGHLIGHT = "#ffcc00"
DWELL = "#4fc3f7"

OVERLAY_FLAGS = (Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint
                 | Qt.WindowTransparentForInput | Qt.WindowDoesNotAcceptFocus)


class Toast(QWidget):
    """Large, high-contrast text that never takes focus or blocks clicks."""

    def __init__(self, persistent=False, color="#000000", background="#ffcc00"):
        super().__init__(None, OVERLAY_FLAGS)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WA_MacAlwaysShowToolWindow)
        self.persistent = persistent
        self.label = QLabel(self)
        self.label.setStyleSheet(
            f"color:{color}; background:{background}; border-radius:18px; padding:14px 28px;")
        f = QFont()
        f.setPointSize(30)
        f.setBold(True)
        self.label.setFont(f)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self.label)
        self.timer = QTimer(self, singleShot=True, timeout=self.hide)

    def show_text(self, text, ms=1200, where="center"):
        self.label.setText(text)
        self.adjustSize()
        screen = self.screen().availableGeometry()
        if where == "corner":
            self.move(screen.right() - self.width() - 24, screen.top() + 24)
        else:
            self.move(screen.center().x() - self.width() // 2,
                      screen.bottom() - self.height() - 120)
        self.show()
        self.raise_()
        if not self.persistent:
            self.timer.start(ms)


class DwellButton(QPushButton):
    """A button that presses itself when the pointer rests on it.
    Eye trackers and head pointers move the pointer, so this needs no click."""

    dwelled = Signal()

    def __init__(self, text, dwell_ms, parent=None):
        super().__init__(text, parent)
        self.dwell_ms = dwell_ms
        self.dwell_enabled = True
        self.scanned = False
        self.progress = 0.0
        self._elapsed = 0
        self._tick = QTimer(self, interval=30, timeout=self._step)
        self.setFocusPolicy(Qt.NoFocus)
        self.setMouseTracking(True)

    def enterEvent(self, e):
        if self.dwell_enabled and self.isEnabled():
            self._elapsed = 0
            self._tick.start()
        super().enterEvent(e)

    def leaveEvent(self, e):
        self._tick.stop()
        self.progress = 0.0
        self.update()
        super().leaveEvent(e)

    def _step(self):
        self._elapsed += self._tick.interval()
        self.progress = min(1.0, self._elapsed / max(1, self.dwell_ms))
        if self.progress >= 1.0:
            # Fire, then start over so resting on a button keeps zooming.
            self._elapsed = 0
            self.progress = 0.0
            self.dwelled.emit()
        self.update()

    def paintEvent(self, e):
        super().paintEvent(e)
        p = QPainter(self)
        if self.scanned:
            pen = p.pen()
            pen.setColor(QColor(HIGHLIGHT))
            pen.setWidth(8)
            p.setPen(pen)
            p.drawRoundedRect(QRectF(self.rect()).adjusted(4, 4, -4, -4), 14, 14)
        if self.progress > 0:
            p.fillRect(QRectF(0, self.height() - 10, self.width() * self.progress, 10),
                       QColor(DWELL))
        p.end()


class Panel(QWidget):
    """Floating big buttons. Click, dwell, or scan with one switch."""

    action = Signal(str)

    def __init__(self, dwell_ms=900, scan_ms=1500, scale=1.0):
        super().__init__(None, Qt.Tool | Qt.WindowStaysOnTopHint | Qt.WindowDoesNotAcceptFocus)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WA_MacAlwaysShowToolWindow)
        self.setWindowTitle("Limitless Zoom")
        self.setAccessibleName("Limitless Zoom panel")
        px = int(22 * scale)
        h = int(96 * scale)
        self.setStyleSheet(f"""
            QWidget {{ background:#111; color:#fff; font-size:{px}px; font-weight:600; }}
            QPushButton {{ background:#2a2a2a; border:4px solid #555; border-radius:16px;
                          min-height:{h}px; padding:6px; }}
            QPushButton:hover {{ border-color:{DWELL}; }}
            QPushButton:pressed {{ background:#444; }}
            QPushButton#small {{ min-height:{int(h * 0.6)}px; font-size:{int(px * 0.8)}px; }}
        """)

        self.buttons = []
        grid = QGridLayout()
        grid.setSpacing(12)
        for i, (name, label) in enumerate(PANEL_BUTTONS):
            b = DwellButton(label, dwell_ms)
            b.setAccessibleName(label)
            b.clicked.connect(lambda _=False, n=name: self.action.emit(n))
            b.dwelled.connect(lambda n=name: self.action.emit(n))
            grid.addWidget(b, i // 2, i % 2)
            self.buttons.append(b)

        self.scan_button = DwellButton("Scanning: off", dwell_ms)
        self.dwell_button = DwellButton("Dwell: on", dwell_ms)
        for b in (self.scan_button, self.dwell_button):
            b.setObjectName("small")
        self.scan_button.clicked.connect(self.toggle_scan)
        self.scan_button.dwelled.connect(self.toggle_scan)
        self.dwell_button.clicked.connect(self.toggle_dwell)
        self.dwell_button.dwelled.connect(self.toggle_dwell)
        self.buttons += [self.scan_button, self.dwell_button]

        bar = QHBoxLayout()
        bar.addWidget(self.scan_button)
        bar.addWidget(self.dwell_button)
        self.status = QLabel("")
        self.status.setWordWrap(True)
        self.status.setStyleSheet(f"font-size:{int(px * 0.7)}px; color:#bbb;")

        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 12, 12, 12)
        lay.addLayout(grid)
        lay.addLayout(bar)
        lay.addWidget(self.status)

        self.scan_index = -1
        self.scan_timer = QTimer(self, interval=scan_ms, timeout=self._advance)
        self.resize(int(440 * scale), int(620 * scale))

    # Scanning: one switch steps through the buttons.
    def scanning(self):
        return self.scan_timer.isActive()

    def toggle_scan(self):
        if self.scanning():
            self.scan_timer.stop()
            self._highlight(-1)
            self.scan_button.setText("Scanning: off")
        else:
            self._highlight(0)
            self.scan_timer.start()
            self.scan_button.setText("Scanning: on")

    def _advance(self):
        self._highlight((self.scan_index + 1) % len(self.buttons))

    def _highlight(self, i):
        for j, b in enumerate(self.buttons):
            b.scanned = j == i
            b.update()
        self.scan_index = i

    def switch_pressed(self):
        """The accessibility switch was pressed."""
        if not self.isVisible():
            self.show()
        if not self.scanning():
            self.toggle_scan()
            return
        b = self.buttons[self.scan_index]
        b.click()
        self.scan_timer.start()  # restart the step so the next highlight isn't rushed

    def toggle_dwell(self):
        on = not self.buttons[0].dwell_enabled
        for b in self.buttons:
            b.dwell_enabled = on
        # The dwell button itself always dwells, so it can be turned back on.
        self.dwell_button.dwell_enabled = True
        self.dwell_button.setText("Dwell: on" if on else "Dwell: off")


class KeyCaptureDialog(QDialog):
    """Big, simple screen: press any key (or your switch) and it's saved."""

    def __init__(self, title, prompt, start_capture, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setStyleSheet("QWidget{background:#111;color:#fff;font-size:26px;font-weight:600;}")
        self.key = None
        self.label = QLabel(prompt)
        self.label.setWordWrap(True)
        self.label.setAlignment(Qt.AlignCenter)
        cancel = QPushButton("Cancel")
        cancel.setMinimumHeight(70)
        cancel.clicked.connect(self.reject)
        lay = QVBoxLayout(self)
        lay.addWidget(self.label)
        lay.addWidget(cancel)
        self.resize(560, 280)
        start_capture(self.got_key)

    def got_key(self, name):
        self.key = name
        self.accept()

    def keyPressEvent(self, e):
        # Fallback when system-wide keys aren't permitted yet: keys typed here.
        k = e.key()
        if Qt.Key_F1 <= k <= Qt.Key_F35:
            self.got_key(f"f{k - Qt.Key_F1 + 1}")
        elif k == Qt.Key_Escape:
            self.reject()
        elif e.text().strip():
            self.got_key(e.text().strip().lower())


class Welcome(QDialog):
    """First run: pick the zoom key, the switch key and the microphone."""

    choose_layer = Signal()
    choose_switch = Signal()

    def __init__(self, layer_text, switch_text, mics, current_mic, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Welcome to Limitless Zoom")
        self.setStyleSheet("""
            QWidget{background:#111;color:#fff;font-size:22px;}
            QPushButton{background:#2a2a2a;border:4px solid #555;border-radius:14px;
                        min-height:70px;font-weight:600;}
            QPushButton:hover{border-color:#4fc3f7;}
            QComboBox{min-height:50px;}
        """)
        intro = QLabel(
            "Zoom your DAW or your whole screen without a mouse.\n\n"
            "• Say \"zoom in\", \"zoom out\", \"taller\", \"fit\".\n"
            "• Or tap your zoom key, then use E, Q, S, W, A with one hand.\n"
            "• Or rest your eyes or pointer on the big buttons.\n"
            "• Or press your switch to scan through them.")
        intro.setWordWrap(True)
        self.layer_btn = QPushButton(f"Zoom keys on/off: {layer_text}  (change)")
        self.switch_btn = QPushButton(f"Switch key: {switch_text}  (change)")
        self.layer_btn.clicked.connect(self.choose_layer)
        self.switch_btn.clicked.connect(self.choose_switch)
        self.mic = QComboBox()
        self.mic.addItem("System default microphone", None)
        for m in mics:
            self.mic.addItem(m, m)
        if current_mic in mics:
            self.mic.setCurrentIndex(mics.index(current_mic) + 1)
        done = QPushButton("Start")
        done.clicked.connect(self.accept)
        lay = QVBoxLayout(self)
        lay.addWidget(intro)
        lay.addWidget(self.layer_btn)
        lay.addWidget(self.switch_btn)
        lay.addWidget(QLabel("Microphone:"))
        lay.addWidget(self.mic)
        lay.addWidget(done)
        self.resize(680, 600)
