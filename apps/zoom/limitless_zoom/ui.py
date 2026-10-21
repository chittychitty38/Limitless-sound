"""On-screen parts: the big-text toast, the "zoom keys on" badge, the
big-button panel (dwell and switch scanning), key capture, and the setup assistant."""

from PySide6.QtCore import QElapsedTimer, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QPainter
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QFrame, QGridLayout, QHBoxLayout,
                               QLabel, QProgressBar, QPushButton, QScrollArea, QVBoxLayout,
                               QWidget)

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
        # Measure real time, not timer ticks: macOS slows timers down for
        # apps in the background, which would stretch the dwell time.
        self._clock = QElapsedTimer()
        self._tick = QTimer(self, interval=30, timeout=self._step)
        self._tick.setTimerType(Qt.PreciseTimer)
        self.setFocusPolicy(Qt.NoFocus)
        self.setMouseTracking(True)

    def enterEvent(self, e):
        if self.dwell_enabled and self.isEnabled():
            self._clock.start()
            self._tick.start()
        super().enterEvent(e)

    def leaveEvent(self, e):
        self._tick.stop()
        self.progress = 0.0
        self.update()
        super().leaveEvent(e)

    def _step(self):
        self.progress = min(1.0, self._clock.elapsed() / max(1, self.dwell_ms))
        if self.progress >= 1.0:
            # Fire, then start over so resting on a button keeps zooming.
            self._clock.restart()
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

        self.keys_label = QLabel("Zoom keys: off")
        self.voice_label = QLabel("Voice: starting…")
        self.chip_px = int(px * 0.75)
        for chip in (self.keys_label, self.voice_label):
            chip.setWordWrap(True)
            chip.setStyleSheet(f"font-size:{self.chip_px}px; color:#ddd; background:#1d1d1d;"
                               "border-radius:10px; padding:6px 10px;")

        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 12, 12, 12)
        lay.addWidget(self.keys_label)
        lay.addWidget(self.voice_label)
        lay.addLayout(grid)
        lay.addLayout(bar)
        lay.addWidget(self.status)

        self.scan_index = -1
        self.scan_timer = QTimer(self, interval=scan_ms, timeout=self._advance)
        self.resize(int(440 * scale), int(700 * scale))

    def set_keys_state(self, on, key_text):
        base = f"font-size:{self.chip_px}px; border-radius:10px; padding:6px 10px;"
        if on:
            self.keys_label.setText("Zoom keys ON: E in, Q out, S taller, W shorter, A fit. "
                                    f"Tap {key_text} to turn off.")
            self.keys_label.setStyleSheet(base + f"background:{HIGHLIGHT}; color:#000; font-weight:800;")
        else:
            self.keys_label.setText(f"Zoom keys off. Tap {key_text} to turn on.")
            self.keys_label.setStyleSheet(base + "background:#1d1d1d; color:#ddd;")

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
        self.label = QLabel(prompt + "\n\nYou can also tap Right Option, Right Command, "
                                     "Right Control or Right Shift on its own.")
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


STATE_MARK = {"ok": ("✓", "#3ddc84"), "missing": ("!", "#ff9f43"), "unknown": ("?", "#9e9e9e")}

SETUP_STYLE = """
    QWidget { background:#111; color:#fff; font-size:19px; }
    QLabel#h1 { font-size:32px; font-weight:800; }
    QLabel#h2 { font-size:23px; font-weight:700; margin-top:10px; }
    QLabel#muted { color:#bbb; }
    QFrame#card { background:#1c1c1c; border-radius:16px; }
    QFrame#card QLabel { background:transparent; }
    QPushButton { background:#2a2a2a; border:3px solid #555; border-radius:12px;
                  min-height:52px; padding:4px 18px; font-weight:600; }
    QPushButton:hover, QPushButton:focus { border-color:#4fc3f7; }
    QPushButton#primary { background:#ffcc00; color:#000; border-color:#ffcc00;
                          min-height:68px; font-size:23px; }
    QComboBox { min-height:46px; background:#2a2a2a; border:2px solid #555; border-radius:10px;
                padding:0 10px; }
    QProgressBar { background:#2a2a2a; border:none; border-radius:8px; height:16px; }
    QProgressBar::chunk { background:#3ddc84; border-radius:8px; }
    QCheckBox { spacing:12px; } QCheckBox::indicator { width:28px; height:28px; }
"""


class Setup(QWidget):
    """The setup assistant: shown on first launch and from the menu.
    Everything updates live, so people can see each step work."""

    request_permission = Signal(str)
    choose_layer = Signal()
    choose_switch = Signal()
    mic_changed = Signal(object)
    login_changed = Signal(bool)
    finished = Signal()

    def __init__(self, key_text, switch_text, mics, current_mic, login=None, parent=None):
        super().__init__(parent, Qt.Window)
        self.setWindowTitle("Set up Limitless Zoom")
        self.setAccessibleName("Limitless Zoom setup")
        self.setStyleSheet(SETUP_STYLE)

        body = QWidget()
        lay = QVBoxLayout(body)
        lay.setContentsMargins(28, 24, 28, 24)
        lay.setSpacing(12)

        h1 = QLabel("Welcome to Limitless Zoom")
        h1.setObjectName("h1")
        intro = QLabel("Zoom Logic, Pro Tools, Ableton or your whole screen with your voice, "
                       "one key, your eyes or a switch. This takes about a minute.")
        intro.setObjectName("muted")
        intro.setWordWrap(True)
        lay.addWidget(h1)
        lay.addWidget(intro)

        # 1. Permissions (macOS)
        self.perm_header = self._h2("1. Allow access", lay)
        self.perm_box = QVBoxLayout()
        lay.addLayout(self.perm_box)
        self.perm_rows = {}

        # 2. Zoom key
        self._h2("2. Your zoom key", lay)
        card, c = self._card(lay)
        self.key_label = QLabel()
        self.key_label.setWordWrap(True)
        self.key_state = QLabel()
        self.key_state.setAlignment(Qt.AlignCenter)
        self.key_state.setMinimumHeight(56)
        change = QPushButton("Use a different key…")
        change.clicked.connect(self.choose_layer)
        c.addWidget(self.key_label)
        c.addWidget(self.key_state)
        c.addWidget(change, alignment=Qt.AlignLeft)
        self.set_key_text(key_text)
        self.set_layer_state(False)

        # 3. Voice
        self._h2("3. Voice", lay)
        card, c = self._card(lay)
        c.addWidget(QLabel("Microphone:"))
        self.mic = QComboBox()
        self.mic.setAccessibleName("Microphone")
        self.mic.addItem("System default microphone", None)
        for m in mics:
            self.mic.addItem(m, m)
        if current_mic in mics:
            self.mic.setCurrentIndex(mics.index(current_mic) + 1)
        self.mic.currentIndexChanged.connect(lambda _: self.mic_changed.emit(self.mic.currentData()))
        c.addWidget(self.mic)
        self.meter = QProgressBar()
        self.meter.setRange(0, 100)
        self.meter.setTextVisible(False)
        self.meter.setAccessibleName("Microphone level")
        c.addWidget(self.meter)
        self.heard = QLabel("Say \u201czoom in\u201d to try it.")
        self.heard.setWordWrap(True)
        c.addWidget(self.heard)
        self.voice_status = QLabel("")
        self.voice_status.setObjectName("muted")
        self.voice_status.setWordWrap(True)
        c.addWidget(self.voice_status)

        # 4. Switch
        self._h2("4. Switch (optional)", lay)
        card, c = self._card(lay)
        self.switch_label = QLabel()
        self.switch_label.setWordWrap(True)
        sw = QPushButton("Set up my switch…")
        sw.clicked.connect(self.choose_switch)
        c.addWidget(self.switch_label)
        c.addWidget(sw, alignment=Qt.AlignLeft)
        self.set_switch_text(switch_text)

        # Finish
        self.login = None
        if login is not None:
            self.login = QCheckBox("Open Limitless Zoom when I log in")
            self.login.setChecked(login)
            self.login.toggled.connect(self.login_changed)
            lay.addWidget(self.login)
        self.start_btn = QPushButton("Start zooming")
        self.start_btn.setObjectName("primary")
        self.start_btn.clicked.connect(self._finish)
        lay.addWidget(self.start_btn)
        tip = QLabel("You can open this again any time from the magnifier icon in the menu bar.")
        tip.setObjectName("muted")
        tip.setWordWrap(True)
        lay.addWidget(tip)

        scroll = QScrollArea()
        scroll.setWidget(body)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)
        self.resize(760, 860)

    def _h2(self, text, lay):
        h = QLabel(text)
        h.setObjectName("h2")
        lay.addWidget(h)
        return h

    def _card(self, lay):
        card = QFrame()
        card.setObjectName("card")
        c = QVBoxLayout(card)
        c.setContentsMargins(18, 16, 18, 16)
        c.setSpacing(10)
        lay.addWidget(card)
        return card, c

    def set_permissions(self, perms):
        self.perm_header.setVisible(bool(perms))
        for p in perms:
            row = self.perm_rows.get(p["key"])
            if row is None:
                card = QFrame()
                card.setObjectName("card")
                h = QHBoxLayout(card)
                h.setContentsMargins(16, 12, 16, 12)
                mark = QLabel()
                mark.setFixedWidth(44)
                mark.setAlignment(Qt.AlignCenter)
                text = QLabel()
                text.setWordWrap(True)
                btn = QPushButton("Allow…")
                btn.clicked.connect(lambda _=False, k=p["key"]: self.request_permission.emit(k))
                h.addWidget(mark)
                h.addWidget(text, 1)
                h.addWidget(btn)
                self.perm_box.addWidget(card)
                row = self.perm_rows[p["key"]] = (mark, text, btn)
            mark, text, btn = row
            symbol, color = STATE_MARK.get(p["state"], STATE_MARK["unknown"])
            mark.setText(symbol)
            mark.setStyleSheet(f"font-size:30px; font-weight:800; color:{color};")
            need = "" if p["required"] else " (optional)"
            text.setText(f"<b>{p['title']}{need}</b><br><span style='color:#bbb'>{p['why']}</span>")
            btn.setVisible(p["state"] != "ok")
            btn.setText("Open Settings…" if p["state"] == "unknown" else "Allow…")
            btn.setAccessibleName(f"Allow {p['title']}")
        missing = [p["title"] for p in perms if p["required"] and p["state"] == "missing"]
        self.start_btn.setText("Start zooming" if not missing
                               else f"Start (still needs {', '.join(missing)})")

    def set_key_text(self, key_text):
        self.key_text = key_text
        self.key_label.setText(f"Tap <b>{key_text}</b> to turn the zoom keys on. Then, with one hand: "
                               "<b>E</b> zoom in, <b>Q</b> out, <b>S</b> taller, <b>W</b> shorter, "
                               "<b>A</b> fit. Tap it again to turn them off. Try it now:")

    def set_layer_state(self, on):
        if on:
            self.key_state.setText("ZOOM KEYS ON")
            self.key_state.setStyleSheet("background:#ffcc00; color:#000; font-size:24px;"
                                         "font-weight:800; border-radius:12px;")
        else:
            self.key_state.setText(f"Zoom keys off. Tap {self.key_text}.")
            self.key_state.setStyleSheet("background:#2a2a2a; color:#ddd; font-size:20px;"
                                         "border-radius:12px;")

    def set_switch_text(self, switch_text):
        self.switch_label.setText(f"If you use a switch, it starts the big-button panel scanning, "
                                  f"then picks the lit button. Your switch key: <b>{switch_text}</b>.")

    def set_level(self, value):
        self.meter.setValue(int(value * 100))

    def set_heard(self, text):
        self.heard.setText(f"Heard: \u201c{text}\u201d")

    def set_voice_status(self, text):
        self.voice_status.setText(text)

    def _finish(self):
        self.finished.emit()
        self.close()
