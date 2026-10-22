"""On-screen parts: the big-text toast, the "zoom keys on" badge, the
big-button panel (dwell and switch scanning), key capture, and the setup assistant."""

import math
from typing import NamedTuple

from PySide6.QtCore import QElapsedTimer, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QPainter
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QFrame, QGridLayout, QHBoxLayout,
                               QLabel, QProgressBar, QPushButton, QScrollArea, QVBoxLayout,
                               QWidget)

from .actions import PANEL_BUTTONS

HIGHLIGHT = "#ffcc00"
DWELL = "#4fc3f7"
# High contrast is black, white and pure yellow, with strong borders.
HC_HIGHLIGHT = "#ffff00"
HC_DWELL = "#00ffff"

OVERLAY_FLAGS = (Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint
                 | Qt.WindowTransparentForInput | Qt.WindowDoesNotAcceptFocus)


class Look(NamedTuple):
    """Text size, contrast and motion for everything on screen. The suite's shared
    settings change it (see suite.py); on its own, Zoom looks as it always has."""

    text_scale: float = 1.0
    high_contrast: bool = False
    reduce_motion: bool = False

    def combined(self, other):
        """The more accessible of two looks: the bigger text, and high contrast or
        reduced motion on if either one has it on."""
        return Look(max(self.text_scale, other.text_scale), self.high_contrast or other.high_contrast,
                    self.reduce_motion or other.reduce_motion)


class Toast(QWidget):
    """Large, high-contrast text that never takes focus or blocks clicks."""

    def __init__(self, persistent=False, color="#000000", background="#ffcc00"):
        super().__init__(None, OVERLAY_FLAGS)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WA_MacAlwaysShowToolWindow)
        self.persistent = persistent
        self.colors = (color, background)
        self.where = "center"
        self.label = QLabel(self)
        f = QFont()
        f.setPointSize(30)
        f.setBold(True)
        self.label.setFont(f)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self.label)
        self.timer = QTimer(self, singleShot=True, timeout=self.hide)
        self.set_look(Look())

    def set_look(self, look):
        """Text size and contrast. A toast that's showing changes straight away."""
        color, background = self.colors
        border = ""
        if look.high_contrast:
            color, background, border = HC_HIGHLIGHT, "#000000", "border:4px solid #ffffff; "
        self.label.setStyleSheet(
            f"color:{color}; background:{background}; {border}border-radius:18px; padding:14px 28px;")
        f = self.label.font()
        f.setPointSizeF(30 * look.text_scale)
        self.label.setFont(f)
        if self.isVisible():
            self._place()

    def show_text(self, text, ms=1200, where="center"):
        self.label.setText(text)
        self.where = where
        self._place()
        self.show()
        self.raise_()
        if not self.persistent:
            self.timer.start(ms)

    def _place(self):
        screen = self.screen().availableGeometry()
        # Very large text wraps rather than running off the screen.
        room = screen.width() - 48
        self.label.setWordWrap(False)
        self.label.setWordWrap(self.label.sizeHint().width() > room)
        self.label.setMaximumWidth(room)
        self.adjustSize()
        if self.where == "corner":
            self.move(screen.right() - self.width() - 24, screen.top() + 24)
        else:
            self.move(screen.center().x() - self.width() // 2,
                      screen.bottom() - self.height() - 120)


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
        self.look = Look()
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
        self._stop_dwell()
        super().leaveEvent(e)

    def hideEvent(self, e):
        # Hidden under the pointer ("hide panel" said while resting on a button) there may be
        # no leave event: the 30 ms tick would run on, pressing the hidden button again and again.
        self._stop_dwell()
        super().hideEvent(e)

    def _stop_dwell(self):
        self._tick.stop()
        self.progress = 0.0
        self.update()

    def _step(self):
        self.progress = min(1.0, self._clock.elapsed() / max(1, self.dwell_ms))
        if self.progress >= 1.0:
            # Fire, then start over so resting on a button keeps zooming.
            self._clock.restart()
            self.progress = 0.0
            self.dwelled.emit()
        self.update()

    def shown_progress(self):
        """How much of the dwell bar to fill. With reduced motion it fills in four
        steps instead of sliding."""
        if self.look.reduce_motion:
            return math.ceil(self.progress * 4) / 4
        return self.progress

    def paintEvent(self, e):
        super().paintEvent(e)
        p = QPainter(self)
        hc = self.look.high_contrast
        if self.scanned:
            pen = p.pen()
            pen.setColor(QColor(HC_HIGHLIGHT if hc else HIGHLIGHT))
            pen.setWidth(8)
            p.setPen(pen)
            p.drawRoundedRect(QRectF(self.rect()).adjusted(4, 4, -4, -4), 14, 14)
        shown = self.shown_progress()
        if shown > 0:
            p.fillRect(QRectF(0, self.height() - 10, self.width() * shown, 10),
                       QColor(HC_DWELL if hc else DWELL))
        p.end()


PANEL_HIGH_CONTRAST = f"""
    QWidget {{ background:#000; }}
    QPushButton {{ background:#000; border-color:#fff; }}
    QPushButton:hover {{ border-color:{HC_DWELL}; }}
    QPushButton:pressed {{ background:#fff; color:#000; }}
"""


class Panel(QWidget):
    """Floating big buttons. Click, dwell, or scan with one switch."""

    action = Signal(str)

    def __init__(self, dwell_ms=900, scan_ms=1500, scale=1.0):
        super().__init__(None, Qt.Tool | Qt.WindowStaysOnTopHint | Qt.WindowDoesNotAcceptFocus)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WA_MacAlwaysShowToolWindow)
        self.setWindowTitle("Limitless Zoom")
        self.setAccessibleName("Limitless Zoom panel")
        self.scale = scale   # button size; the text can grow bigger still (set_look)

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

        self.keys_label = QLabel("Zoom keys: off")
        self.voice_label = QLabel("Voice: starting…")
        self.keys_on = False
        for chip in (self.keys_label, self.voice_label):
            chip.setWordWrap(True)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 12, 12, 12)
        lay.addWidget(self.keys_label)
        lay.addWidget(self.voice_label)
        lay.addLayout(grid)
        lay.addLayout(bar)
        lay.addWidget(self.status)

        self.scan_index = -1
        self.scan_timer = QTimer(self, interval=scan_ms, timeout=self._advance)
        self.scan_timer.setTimerType(Qt.PreciseTimer)
        self._home_right, self._placed = None, None
        self.look = Look(scale)
        self.set_look(self.look)
        self.resize(int(440 * scale), int(700 * scale))

    def set_look(self, look):
        """Text size and contrast, live. The buttons and the panel grow to fit the text,
        and with reduced motion the dwell bar fills in steps instead of sliding."""
        new_size = look.text_scale != self.look.text_scale
        # Where the panel belongs: its right edge, unless it had to slide left to fit very large
        # text on screen; then where it was before that. If the musician moved it, there.
        here = (self.x(), self.width())
        right = self._home_right if here == self._placed else self.x() + self.width()
        self.look = look
        hc = look.high_contrast
        px = int(22 * look.text_scale)
        h = int(96 * self.scale)
        self.setStyleSheet(f"""
            QWidget {{ background:#111; color:#fff; font-size:{px}px; font-weight:600; }}
            QPushButton {{ background:#2a2a2a; border:4px solid #555; border-radius:16px;
                          min-height:{h}px; padding:6px; }}
            QPushButton:hover {{ border-color:{DWELL}; }}
            QPushButton:pressed {{ background:#444; }}
            QPushButton#small {{ min-height:{int(h * 0.6)}px; font-size:{int(px * 0.8)}px; }}
        """ + (PANEL_HIGH_CONTRAST if hc else ""))
        self.status.setStyleSheet(f"font-size:{int(px * 0.7)}px; color:{'#fff' if hc else '#bbb'};")
        self.chip_px = int(px * 0.75)
        self.voice_label.setStyleSheet(self._chip_style(False))
        self.keys_label.setStyleSheet(self._chip_style(self.keys_on))
        for b in self.buttons:
            b.look = look
            b.update()
        # Fit the text now (Qt grows the panel past its usual size if the text needs it).
        # invalidate() first: the layout keeps each button's size from the old text until
        # told, and on Windows that kept the panel at its big-text width after shrinking.
        self.layout().invalidate()
        self.layout().activate()
        if new_size:
            self.resize(int(440 * self.scale), int(700 * self.scale))
        if self.isVisible():
            # Keep the right edge where it was (it starts at the right of the screen), on screen.
            area = self.screen().availableGeometry()
            self.move(max(area.left(), min(right, area.right()) - self.width()),
                      max(area.top(), min(self.y(), area.bottom() - self.height())))
            self._home_right, self._placed = right, (self.x(), self.width())

    def _chip_style(self, on):
        base = f"font-size:{self.chip_px}px; border-radius:10px; padding:6px 10px;"
        if on:
            lit = HC_HIGHLIGHT if self.look.high_contrast else HIGHLIGHT
            return base + f"background:{lit}; color:#000; font-weight:800;"
        if self.look.high_contrast:
            return base + "background:#000; color:#fff; border:2px solid #fff;"
        return base + "background:#1d1d1d; color:#ddd;"

    def set_keys_state(self, on, key_text):
        self.keys_on = on
        if on:
            self.keys_label.setText("Zoom keys ON: E in, Q out, S taller, W shorter, A fit. "
                                    f"Tap {key_text} to turn off.")
        else:
            self.keys_label.setText(f"Zoom keys off. Tap {key_text} to turn on.")
        self.keys_label.setStyleSheet(self._chip_style(on))

    def hideEvent(self, e):
        # Scanning stops with the panel: a hidden panel kept stepping through its buttons, and
        # the next switch press picked one nobody could see. Now that press shows the panel and
        # starts scanning from the first button.
        if self.scanning() and not e.spontaneous():
            self.toggle_scan()
        super().hideEvent(e)

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

    def __init__(self, title, prompt, start_capture, parent=None, look=Look()):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.set_look(look)
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

    def set_look(self, look):
        px = int(26 * look.text_scale)
        style = f"QWidget{{background:#111;color:#fff;font-size:{px}px;font-weight:600;}}"
        if look.high_contrast:
            style += ("QWidget{background:#000;} QPushButton{border:3px solid #fff;border-radius:12px;}"
                      f"QPushButton:focus{{border-color:{HC_HIGHLIGHT};}}")
        self.setStyleSheet(style)

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

SETUP_HIGH_CONTRAST = f"""
    QWidget {{ background:#000; }}
    QLabel#muted {{ color:#fff; }}
    QFrame#card {{ background:#000; border:3px solid #fff; }}
    QPushButton, QComboBox {{ background:#000; border-color:#fff; }}
    QPushButton:hover, QPushButton:focus, QComboBox:focus {{ border-color:{HC_HIGHLIGHT}; }}
    QPushButton#primary {{ background:{HC_HIGHLIGHT}; border-color:{HC_HIGHLIGHT}; }}
    QPushButton#primary:focus {{ background:#000; color:{HC_HIGHLIGHT}; }}
    QProgressBar {{ background:#000; border:2px solid #fff; }}
"""


def setup_style(look):
    s = look.text_scale
    return f"""
    QWidget {{ background:#111; color:#fff; font-size:{int(19 * s)}px; }}
    QLabel#h1 {{ font-size:{int(32 * s)}px; font-weight:800; }}
    QLabel#h2 {{ font-size:{int(23 * s)}px; font-weight:700; margin-top:10px; }}
    QLabel#muted {{ color:#bbb; }}
    QFrame#card {{ background:#1c1c1c; border-radius:16px; }}
    QFrame#card QLabel {{ background:transparent; }}
    QPushButton {{ background:#2a2a2a; border:3px solid #555; border-radius:12px;
                  min-height:52px; padding:4px 18px; font-weight:600; }}
    QPushButton:hover, QPushButton:focus {{ border-color:#4fc3f7; }}
    QPushButton#primary {{ background:#ffcc00; color:#000; border-color:#ffcc00;
                          min-height:68px; font-size:{int(23 * s)}px; }}
    QComboBox {{ min-height:46px; background:#2a2a2a; border:2px solid #555; border-radius:10px;
                padding:0 10px; }}
    QProgressBar {{ background:#2a2a2a; border:none; border-radius:8px; height:16px; }}
    QProgressBar::chunk {{ background:#3ddc84; border-radius:8px; }}
    QCheckBox {{ spacing:12px; }} QCheckBox::indicator {{ width:28px; height:28px; }}
""" + (SETUP_HIGH_CONTRAST if look.high_contrast else "")


class Setup(QWidget):
    """The setup assistant: shown on first launch and from the menu.
    Everything updates live, so people can see each step work."""

    request_permission = Signal(str)
    choose_layer = Signal()
    choose_switch = Signal()
    mic_changed = Signal(object)
    login_changed = Signal(bool)
    finished = Signal()

    def __init__(self, key_text, switch_text, mics, current_mic, login=None, parent=None, look=Look()):
        super().__init__(parent, Qt.Window)
        self.setWindowTitle("Set up Limitless Zoom")
        self.setAccessibleName("Limitless Zoom setup")
        self.look = look
        self.setStyleSheet(setup_style(look))

        body = QWidget()
        lay = QVBoxLayout(body)
        lay.setContentsMargins(28, 24, 28, 24)
        lay.setSpacing(12)

        h1 = QLabel("Welcome to Limitless Zoom")
        h1.setObjectName("h1")
        h1.setWordWrap(True)
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
        self.perms = []

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
        self.resize(int(760 * look.text_scale), int(860 * look.text_scale))

    def set_look(self, look):
        """Text size and contrast, live."""
        self.look = look
        self.setStyleSheet(setup_style(look))
        if self.perms:
            self.set_permissions(self.perms)
        self.set_layer_state(self.layer_on)

    def _h2(self, text, lay):
        h = QLabel(text)
        h.setObjectName("h2")
        h.setWordWrap(True)
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
        self.perms = perms
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
            mark.setStyleSheet(f"font-size:{int(30 * self.look.text_scale)}px; font-weight:800;"
                               f"color:{color};")
            need = "" if p["required"] else " (optional)"
            muted = "#fff" if self.look.high_contrast else "#bbb"
            text.setText(f"<b>{p['title']}{need}</b><br><span style='color:{muted}'>{p['why']}</span>")
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
        self.layer_on = on
        s, hc = self.look.text_scale, self.look.high_contrast
        if on:
            self.key_state.setText("ZOOM KEYS ON")
            self.key_state.setStyleSheet(f"background:{HC_HIGHLIGHT if hc else '#ffcc00'}; color:#000;"
                                         f"font-size:{int(24 * s)}px; font-weight:800; border-radius:12px;")
        else:
            self.key_state.setText(f"Zoom keys off. Tap {self.key_text}.")
            colors = ("background:#000; color:#fff; border:3px solid #fff;" if hc
                      else "background:#2a2a2a; color:#ddd;")
            self.key_state.setStyleSheet(colors + f"font-size:{int(20 * s)}px; border-radius:12px;")

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
