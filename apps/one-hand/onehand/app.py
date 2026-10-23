"""The One-Hand window, menu bar icon, on-screen badge and first-launch setup."""
import sys

from PySide6.QtCore import QObject, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QAccessible, QAccessibleValueChangeEvent, QAction, QActionGroup, QKeySequence, QShortcut
from PySide6.QtWidgets import (QApplication, QBoxLayout, QCheckBox, QComboBox, QFrame, QGridLayout,
                               QHBoxLayout, QLabel, QMenu, QPushButton, QScrollArea, QStackedWidget, QStyle,
                               QSystemTrayIcon, QVBoxLayout, QWidget)

from . import __version__, applog
from .engine import Engine, Settings
from .icons import app_icon, tray_icon
from .keys import MIRROR, ROWS, cap, shortcut_text
from .platform_sim import get_backend
from .settings import APP_NAME, Prefs, load_layouts
from .suite import Suite

# High contrast (a Limitless Sound shared setting) goes on top of the usual look: pure black,
# white text and edges with no grey, and a blue focus ring that shows on every button, even a yellow one.
HIGH_CONTRAST = """
QWidget { background: #000; }
QLabel { background: transparent; }
QLabel#hint, QLabel#sends, QLabel#tick { color: #fff; }
QPushButton { background: #000; border-color: #fff; }
QPushButton:hover { border-color: #ffe600; }
QPushButton:focus { border-color: #4fc3ff; }
QFrame#key { background: #000; border-width: 3px; border-color: #fff; }
QFrame#card, QFrame#step { background: #000; border-color: #fff; }
QFrame#banner { background: #000; border-width: 3px; }
QCheckBox::indicator { background: #000; border-color: #fff; }
QCheckBox:focus { text-decoration: underline; }
QComboBox { border-color: #fff; }
QComboBox QAbstractItemView { border: 2px solid #fff; selection-background-color: #ffe600; selection-color: #000; }
"""


def style(scale=1.0, contrast=False):
    px = lambda n: f"{round(n * scale)}px"  # noqa: E731
    return f"""
QWidget {{ background: #111; color: #fff; font-size: {px(17)}; }}
QLabel {{ background: transparent; }}
QLabel#title {{ font-size: {px(28)}; font-weight: 800; }}
QLabel#h2 {{ font-size: {px(21)}; font-weight: 800; }}
QLabel#status {{ font-size: {px(19)}; }}
QLabel#hint, QLabel#sends {{ color: #c8c8c8; }}
QLabel#practice {{ font-size: {px(19)}; color: #ffe600; font-weight: 700; }}
QPushButton {{ background: #262626; color: #fff; border: 3px solid #8a8a8a; border-radius: 12px; padding: {px(10)} {px(16)}; }}
QPushButton:hover {{ border-color: #bbb; }}
QPushButton:focus {{ border-color: #4fc3ff; }}
QPushButton:checked {{ background: #ffe600; color: #000; border-color: #ffe600; font-weight: 800; }}
QPushButton#power {{ font-size: {px(30)}; font-weight: 800; min-height: {px(120)}; }}
QPushButton#primary {{ background: #ffe600; color: #000; border-color: #ffe600; font-weight: 800; }}
QPushButton#primary:focus {{ border-color: #4fc3ff; }}
QFrame#key {{ border: 2px solid #5c5c5c; border-radius: 12px; background: #1b1b1b; }}
QFrame#key[active="true"] {{ border-color: #ffe600; }}
QFrame#key[flash="true"] {{ background: #ffe600; border-color: #fff; }}
QFrame#key[flash="true"] QLabel {{ color: #000; }}
QLabel#cap {{ background: #ffe600; color: #000; font-weight: 800; font-size: {px(22)}; padding: 0 {px(8)}; border-radius: 6px; }}
QFrame#key[flash="true"] QLabel#cap {{ background: #000; color: #ffe600; }}
QLabel#cmd {{ font-weight: 700; }}
QLabel#sends {{ font-size: {px(15)}; }}
QFrame#card {{ background: #191919; border: 2px solid #333; border-radius: 14px; }}
QFrame#card QCheckBox, QFrame#card QLabel {{ background: transparent; }}
QFrame#banner {{ background: #4a1700; border: 2px solid #ff8a50; border-radius: 12px; }}
QFrame#step {{ background: #191919; border: 2px solid #444; border-radius: 12px; }}
QFrame#step[done="true"] {{ border-color: #3ddc84; }}
QLabel#tick {{ font-size: {px(30)}; font-weight: 800; color: #888; min-width: {px(40)}; max-width: {px(40)}; }}
QFrame#step[done="true"] QLabel#tick {{ color: #3ddc84; }}
QCheckBox {{ spacing: 12px; padding: 2px; }}
QCheckBox::indicator {{ width: {px(26)}; height: {px(26)}; border: 2px solid #ccc; border-radius: 6px; background: #111; }}
QCheckBox::indicator:checked {{ background: #ffe600; border-color: #ffe600; }}
QCheckBox:focus {{ color: #4fc3ff; }}
QScrollArea {{ border: none; }}
QComboBox {{ padding: {px(6)} {px(10)}; border: 2px solid #8a8a8a; border-radius: 8px; }}
QComboBox:focus {{ border-color: #4fc3ff; }}
""" + (HIGH_CONTRAST if contrast else "")


def repolish(widget):
    widget.style().unpolish(widget)
    widget.style().polish(widget)
    for child in widget.findChildren(QWidget):
        child.style().unpolish(child)
        child.style().polish(child)


class LiveText(QLabel):
    """Words that change on screen: the mode, the key just tried, what setup is waiting for.
    A screen reader reads the words themselves (on a Mac VoiceOver reads a label's name as its
    words, so these never get a fixed name), `about` says what they are, and each change is
    posted so a screen reader on the label reads the new words."""

    def __init__(self, about, text="", **props):
        super().__init__(text, **props)
        self.setAccessibleDescription(about)

    def setText(self, text):
        super().setText(text)
        # Qt posts the name change itself; VoiceOver follows a label's words as its value.
        iface = QAccessible.queryAccessibleInterface(self)
        QAccessible.updateAccessibility(
            QAccessibleValueChangeEvent(self, iface.text(QAccessible.Text.Name) if iface else text))


class KeyCard(QFrame):
    def __init__(self):
        super().__init__()
        self.setObjectName("key")
        self.setMinimumHeight(108)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 8, 10, 8)
        lay.setSpacing(3)
        self.cap = QLabel(objectName="cap")
        self.cap.setSizePolicy(self.cap.sizePolicy().Policy.Maximum, self.cap.sizePolicy().Policy.Fixed)
        self.cmd = QLabel(objectName="cmd", wordWrap=True)
        self.sends = QLabel(objectName="sends")
        for w in (self.cap, self.cmd, self.sends):
            lay.addWidget(w)
        lay.addStretch()
        self._unflash = QTimer(self, singleShot=True, interval=450, timeout=lambda: self.set_flash(False))
        self.steady = False   # reduced motion: a pressed key stays lit instead of flashing
        self.key = None

    def minimumSizeHint(self):
        # At least 112 wide, and never narrower than its text, however large the text is.
        hint = super().minimumSizeHint()
        return QSize(max(112, hint.width()), hint.height())

    def set_steady(self, on):
        self.steady = on
        if not on and self.property("flash"):
            self._unflash.start()

    def show_command(self, key, label, sends):
        self.key = key
        self.cap.setText(cap(key))
        self.cmd.setText(label)
        self.sends.setText(sends)
        self.setAccessibleName(f"{cap(key)} key: {label or 'nothing'}" + (f", presses {sends}" if sends else ""))

    def set_flash(self, on):
        self.setProperty("flash", on)
        repolish(self)
        if on and not self.steady:
            self._unflash.start()


class OnBadge(QWidget):
    """A small yellow badge at the top of the screen while one-hand mode is on."""

    def __init__(self, backend):
        super().__init__(None, Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint
                         | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.WindowDoesNotAcceptFocus
                         | Qt.WindowType.WindowTransparentForInput)
        self.backend = backend
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_MacAlwaysShowToolWindow)
        self.setWindowTitle(APP_NAME)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self.label = LiveText("One-hand mode")
        lay.addWidget(self.label)
        self._floated = False
        self.set_look(1.0, False)

    def set_look(self, scale, contrast):
        # High contrast keeps black on yellow, with a thicker edge so it stands out on light screens too.
        px = lambda n: f"{round(n * scale)}px"  # noqa: E731
        self.label.setStyleSheet(f"background: #ffe600; color: #000; font-size: {px(17)}; "
                                 f"font-weight: {900 if contrast else 800}; border-radius: {px(16)}; "
                                 f"padding: {px(7)} {px(18)}; border: {4 if contrast else 2}px solid #000;")
        if self.isVisible():
            self.show_text(self.label.text())   # resize and center it again

    def show_text(self, text):
        self.label.setText(text)
        self.adjustSize()
        screen = QApplication.primaryScreen().availableGeometry()
        self.move(screen.center().x() - self.width() // 2, screen.top() + 10)
        if not self.isVisible():
            self.show()
            if not self._floated:
                self.backend.float_window(self)
                self._floated = True


class PermissionPage(QWidget):
    """macOS only: walks through the two privacy switches and notices when they are on."""

    def __init__(self, main):
        super().__init__()
        self._shown = None
        outer = QVBoxLayout(self)
        outer.setContentsMargins(48, 36, 48, 36)
        outer.setSpacing(16)
        outer.addWidget(QLabel("Welcome to Limitless One-Hand", objectName="title"))
        intro = QLabel("To turn your keys into Logic Pro and Pro Tools commands, macOS needs you to allow "
                       "One-Hand to use the keyboard. This takes about a minute and you only do it once.",
                       wordWrap=True)
        outer.addWidget(intro)
        self.steps = {}
        for n, (name, why) in enumerate([
            ("Accessibility", "lets One-Hand press DAW shortcuts for you"),
            ("Input Monitoring", "lets One-Hand notice which keys you press"),
        ], start=1):
            box = QFrame(objectName="step")
            row = QHBoxLayout(box)
            row.setContentsMargins(16, 12, 16, 12)
            tick = LiveText(f"Step {n}", "○", objectName="tick")   # its width grows with the text, in style()
            tick.setAccessibleName(f"{name} not allowed yet")   # the circle, in words
            row.addWidget(tick)
            text = QLabel(f"<b>Step {n}: {name}</b><br>Switch on <b>Limitless One-Hand</b>. It {why}.",
                          wordWrap=True)
            row.addWidget(text, 1)
            btn = QPushButton(f"Open {name} settings", objectName="primary")
            btn.setAccessibleName(f"Open {name} settings in System Settings")
            btn.clicked.connect(lambda _=False, w=name: main.backend.open_permission_settings(w))
            row.addWidget(btn)
            outer.addWidget(box)
            self.steps[name] = (box, tick, btn)
        tips = QLabel("If One-Hand isn't in the list, press <b>+</b> under the list and choose "
                      "<b>Limitless One-Hand</b> from Applications. If macOS asks to quit and reopen the app, "
                      "choose <b>Quit &amp; Reopen</b>.", objectName="hint", wordWrap=True)
        outer.addWidget(tips)
        self.status = LiveText("Setup status", objectName="status", wordWrap=True)
        outer.addWidget(self.status)
        row = QHBoxLayout()
        self.reopen = QPushButton("Reopen One-Hand", objectName="primary")
        self.reopen.clicked.connect(main.relaunch)
        self.reopen.hide()
        later = QPushButton("Look around first")
        later.setAccessibleDescription("Skip for now and look at the key map")
        later.clicked.connect(lambda: main.show_main())
        row.addWidget(self.reopen)
        row.addWidget(later)
        row.addStretch()
        outer.addLayout(row)
        outer.addStretch()

    def refresh(self, status, tried):
        # Called every second while this page waits; restyling it each time kept the CPU busy.
        if (dict(status), tried) == self._shown:
            return
        self._shown = (dict(status), tried)
        for name, (box, tick, btn) in self.steps.items():
            done = status.get(name, False)
            box.setProperty("done", done)
            tick.setAccessibleName(f"{name} {'allowed' if done else 'not allowed yet'}")
            tick.setText("✓" if done else "○")
            btn.setVisible(not done)
            repolish(box)
        if all(status.values()) and tried:
            self.status.setText("Both are on. macOS needs One-Hand to restart before it can use them.")
            self.reopen.show()
        else:
            self.status.setText("Waiting for you to switch these on. This page updates by itself.")
            self.reopen.hide()


class MainThread(QObject):
    """Runs calls from the Limitless Sound link on the window's thread."""
    call = Signal(object)

    def __init__(self):
        super().__init__()
        self.call.connect(lambda fn: fn())


class MainWindow(QWidget):
    def __init__(self, backend, prefs, layouts):
        super().__init__()
        self.backend = backend
        self.prefs = prefs
        self.layouts = layouts
        self.engine = Engine(layouts, backend.platform, self._engine_settings())
        self.engine.self_app_ids = {(backend.own_app_id() or "").lower()} - {""}
        self._seen_changes = 0
        self._seen_previews = 0
        self._front = None
        self._quitting = False

        self.setWindowTitle(APP_NAME)
        self.setWindowIcon(app_icon())
        screen = QApplication.primaryScreen().availableGeometry()
        self.resize(min(1220, screen.width() - 40), min(860, screen.height() - 40))
        self.setMinimumSize(760, 520)
        self._effects = QApplication.isEffectEnabled(Qt.UIEffect.UI_General)   # menus and lists that fade or slide

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        self.pages = QStackedWidget()
        outer.addWidget(self.pages)
        self.permission_page = PermissionPage(self)
        self.pages.addWidget(self._scrolling(self.permission_page, "Set up keyboard access"))
        self.pages.addWidget(self._scrolling(self._build_main(), "One-Hand settings and key map"))

        self._main_thread = MainThread()
        self.suite = Suite(self.engine, backend, self.set_hand, dispatch=self._main_thread.call.emit,
                           prefs_changed=self.apply_style).start()

        self.badge = OnBadge(backend)
        self._build_tray()
        self.apply_style()

        QShortcut(QKeySequence.StandardKey.Quit, self, activated=self.quit)
        QShortcut(QKeySequence("Ctrl+W"), self, activated=self.close)

        self.timer = QTimer(self, interval=120, timeout=self.tick)
        self.timer.start()
        self.perm_timer = QTimer(self, interval=1000, timeout=self.check_permission)
        self._tried_with_permission = False

        self.apply_on_top()
        self.start_backend()
        if prefs.start_on and backend.running:
            self.engine.set_enabled(True)
        self.refresh_power()
        self.refresh_keys()
        self.power.setFocus()

    # ---- building the main page --------------------------------------

    @staticmethod
    def _scrolling(widget, name):
        area = QScrollArea(widgetResizable=True)
        area.setAccessibleName(name)   # Tab stops on it, to scroll by keyboard
        area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        area.setWidget(widget)
        return area

    def _build_main(self):
        page = QWidget()
        cols = self.cols = QBoxLayout(QBoxLayout.Direction.LeftToRight, page)
        cols.setContentsMargins(24, 20, 24, 20)
        cols.setSpacing(24)

        left = QVBoxLayout()
        left.setSpacing(12)
        cols.addLayout(left, 4)
        left.addWidget(QLabel(APP_NAME, objectName="title"))

        self.banner = QFrame(objectName="banner")
        bl = QVBoxLayout(self.banner)
        self.banner_text = LiveText("Keyboard access", wordWrap=True)
        bl.addWidget(self.banner_text)
        self.banner_button = QPushButton("Set up keyboard access", objectName="primary")
        self.banner_button.clicked.connect(self.show_permission)
        bl.addWidget(self.banner_button)
        self.banner.hide()
        left.addWidget(self.banner)

        self.power = QPushButton(objectName="power", checkable=True)
        self.power.setAccessibleDescription("Turns one-hand mode on or off. You can also double-tap Shift.")
        self.power.clicked.connect(lambda checked: self.engine.set_enabled(checked))
        left.addWidget(self.power)
        left.addWidget(QLabel("Click it, double-tap Shift, or press a foot pedal or switch set to F18.",
                              objectName="hint", wordWrap=True))
        self.status = LiveText("One-hand mode status", objectName="status", wordWrap=True)
        self.status.setMinimumHeight(56)
        left.addWidget(self.status)

        hands = QHBoxLayout()
        hands.addWidget(QLabel("I'm using my"))
        # Not a button group: in one, Tab skips the hand that isn't chosen, as with radio buttons.
        # set_hand keeps just one of them checked.
        self.hand_buttons = {}
        for hand in ("left", "right"):
            b = QPushButton(f"{hand.title()} hand", checkable=True)
            b.setAccessibleName(f"Use the {hand}-hand layout")
            b.setChecked(self.prefs.hand == hand)
            b.clicked.connect(lambda _=False, h=hand: self.set_hand(h))
            self.hand_buttons[hand] = b
            hands.addWidget(b)
        hands.addStretch()
        left.addLayout(hands)

        opts = QFrame(objectName="card")
        ol = QVBoxLayout(opts)
        ol.setContentsMargins(16, 10, 16, 10)
        ol.setSpacing(4)
        ol.addWidget(QLabel("Options", objectName="h2"))
        self.add_option(ol, "Hold Space to type letters from the other side", "mirror_typing")
        self.add_option(ol, "Double-tap Shift switches one-hand mode", "double_shift")
        if self.backend.platform == "windows":
            self.add_option(ol, "Caps Lock switches one-hand mode", "caps_lock_toggle")
        self.add_option(ol, "Show an ON badge at the top of the screen", "show_badge", self.refresh_power)
        self.add_option(ol, "Play a sound when switching", "play_sounds")
        self.add_option(ol, "Say “on” and “off” out loud", "speak")
        self.add_option(ol, "Larger text", "larger_text", self.apply_style)
        self.add_option(ol, "Keep this window on top", "keep_on_top", self.apply_on_top)
        self.add_option(ol, "Start with one-hand mode on", "start_on")
        if self.backend.login_item_supported():
            self.add_option(ol, "Open One-Hand when I log in", "open_at_login",
                            lambda: self.backend.set_login_item(self.prefs.open_at_login))
        left.addWidget(opts)
        left.addStretch()

        right = QVBoxLayout()
        right.setSpacing(10)
        cols.addLayout(right, 6)
        pick = QHBoxLayout()
        pick.addWidget(QLabel("Your keys in", objectName="h2"))
        self.app_pick = QComboBox()
        self.app_pick.setAccessibleName("Show the key map for")
        self.app_pick.setAccessibleDescription("App whose keys are shown")   # what VoiceOver reads as its label
        for app in self.layouts["apps"]:
            if app.get(self.backend.platform):
                self.app_pick.addItem(app["name"], app["id"])
        self.app_pick.currentIndexChanged.connect(self.refresh_keys)
        pick.addWidget(self.app_pick)
        pick.addStretch()
        right.addLayout(pick)

        grid = QGridLayout()
        grid.setSpacing(10)
        self.cards = []
        for r, row_keys in enumerate(ROWS):
            for c in range(len(row_keys)):
                card = KeyCard()
                grid.addWidget(card, r, c)
                self.cards.append((r, c, card))
        right.addLayout(grid)
        self.practice = LiveText("Key you just tried", objectName="practice", wordWrap=True)
        self.practice.setMinimumHeight(30)
        right.addWidget(self.practice)
        self.note = QLabel(objectName="hint", wordWrap=True)
        right.addWidget(self.note)
        tips = QLabel("Space still plays and stops. Holding ⌘, ⌥, ⌃ or ⇧ lets your normal shortcuts through. "
                      "Other apps type normally.", objectName="hint", wordWrap=True)
        right.addWidget(tips)
        right.addStretch()
        return page

    def _build_tray(self):
        self.tray = None
        if not QSystemTrayIcon.isSystemTrayAvailable():
            return
        self.tray = QSystemTrayIcon(tray_icon(False), self)
        menu = QMenu()
        self.tray_toggle = QAction("Turn one-hand mode on", menu)
        self.tray_toggle.triggered.connect(self.engine.toggle)
        menu.addAction(self.tray_toggle)
        menu.addSeparator()
        group = QActionGroup(menu)
        self.tray_hands = {}
        for hand in ("left", "right"):
            act = QAction(f"{hand.title()} hand", menu, checkable=True)
            act.setChecked(self.prefs.hand == hand)
            act.triggered.connect(lambda _=False, h=hand: self.set_hand(h))
            group.addAction(act)
            menu.addAction(act)
            self.tray_hands[hand] = act
        menu.addSeparator()
        show = QAction("Show One-Hand window", menu)
        show.triggered.connect(self.bring_back)
        menu.addAction(show)
        quit_ = QAction("Quit One-Hand", menu)
        quit_.triggered.connect(self.quit)
        menu.addAction(quit_)
        self.tray.setContextMenu(menu)
        self.tray.setToolTip(APP_NAME)
        self._tray_menu = menu
        self.tray.show()

    # ---- helpers -----------------------------------------------------

    def _engine_settings(self):
        p = self.prefs
        return Settings(hand=p.hand, mirror_typing=p.mirror_typing, double_shift=p.double_shift,
                        toggle_keys=p.toggle_keys())

    def add_option(self, layout, text, attr, extra=None):
        box = QCheckBox(text)
        box.setChecked(getattr(self.prefs, attr))

        def changed(_state):
            setattr(self.prefs, attr, box.isChecked())
            self.prefs.save()
            with self.engine.lock:
                self.engine.settings = self._engine_settings()
            if extra:
                extra()
        box.stateChanged.connect(changed)
        layout.addWidget(box)

    def apply_style(self):
        # Larger text here, or the musician's Limitless Sound settings when they help more.
        look = self.suite.look(self.prefs.larger_text)
        scale, contrast, calm = look["textScale"], look["highContrast"], look["reduceMotion"]
        self.setStyleSheet(style(scale, contrast))
        self.badge.set_look(scale, contrast)
        for _, _, card in self.cards:
            card.set_steady(calm)
        QApplication.setEffectEnabled(Qt.UIEffect.UI_General, self._effects and not calm)
        self.fit_to_text()
        self.suite.prefs_applied(look)

    def fit_to_text(self):
        # Larger text needs a wider window before the two columns fit side by side, and a wider window at all.
        bar = self.style().pixelMetric(QStyle.PixelMetric.PM_ScrollBarExtent)
        m = self.cols.contentsMargins()
        edges = m.left() + m.right() + bar
        self.cols.invalidate()
        self.cols.activate()   # measure afresh, even while this page is hidden behind the setup page
        left, right = (self.cols.itemAt(i).minimumSize().width() for i in (0, 1))
        self.wide_width = max(1120, left + self.cols.spacing() + right + edges)
        widest = max(max(left, right) + edges, self.permission_page.minimumSizeHint().width() + bar)
        self.setMinimumWidth(min(max(760, widest), QApplication.primaryScreen().availableGeometry().width()))
        self.fit_columns(self.width())

    def fit_columns(self, width):
        # Side by side on a wide window, stacked when narrow, so nothing is ever cut off.
        wide = width >= self.wide_width
        self.cols.setDirection(QBoxLayout.Direction.LeftToRight if wide else QBoxLayout.Direction.TopToBottom)

    def apply_on_top(self):
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, self.prefs.keep_on_top)
        if self.isVisible():
            self.show()

    def set_hand(self, hand):
        self.prefs.hand = hand
        self.prefs.save()
        for h, b in self.hand_buttons.items():
            b.setChecked(h == hand)
        if self.tray:
            self.tray_hands[hand].setChecked(True)
        with self.engine.lock:
            self.engine.settings = self._engine_settings()
        self.refresh_keys()
        self.refresh_power()
        self.suite.hand_changed(hand)

    # ---- keyboard access ---------------------------------------------

    def start_backend(self, show_setup=True):
        try:
            self.backend.stop()
            self.backend.error = None
            self.backend.start(self.engine)
        except Exception as exc:
            if self.backend.platform == "mac":
                if show_setup:
                    self.show_permission()
                self.perm_timer.start()
                return
            self.banner_text.setText(f"{exc}\n\n{self.backend.permission_help() or ''}".strip())
            self.banner_button.hide()
            self.banner.show()
            return
        self.perm_timer.stop()
        self.banner.hide()
        self.show_main()

    def check_permission(self):
        status = self.backend.permission_status()
        if status.get("Accessibility") and not self.backend.running:
            self.start_backend(show_setup=False)   # some macOS versions allow the tap before Input Monitoring shows as on
            self._tried_with_permission = all(status.values()) and not self.backend.running
        self.permission_page.refresh(status, self._tried_with_permission)

    def show_permission(self):
        self.pages.setCurrentIndex(0)
        self.permission_page.refresh(self.backend.permission_status(), self._tried_with_permission)

    def show_main(self):
        self.pages.setCurrentIndex(1)
        if self.backend.platform == "mac" and not self.backend.running:
            self.banner_text.setText("One-Hand can't use the keyboard yet, so your keys won't change.")
            self.banner_button.show()
            self.banner.show()
        self.power.setFocus()

    def relaunch(self):
        self.backend.relaunch()
        self.quit()

    # ---- live updates ------------------------------------------------

    def tick(self):
        if self.engine.changes != self._seen_changes:
            self._seen_changes = self.engine.changes
            self.refresh_power()
            on = self.engine.enabled
            text = "One hand on" if on else "One hand off"
            if self.prefs.play_sounds:
                self.backend.play_sound(on)
            self.suite.mode_changed(on)
            self.backend.announce(text)
            if self.prefs.speak and not self.suite.say(text):
                self.backend.speak(text)
        if self.engine.previews != self._seen_previews:
            self._seen_previews = self.engine.previews
            self.show_practice(*self.engine.last_preview)
        front = self.backend.front_app()
        if front != self._front:
            self._front = front
            app = self.engine.profile_for(front)
            if app:
                i = self.app_pick.findData(app["id"])
                if i >= 0:
                    self.app_pick.setCurrentIndex(i)
            self.refresh_power()

    def show_practice(self, key, label):
        sends = ""
        for _, _, card in self.cards:
            if card.key == key:
                card.set_flash(True)
                sends = card.sends.text()
            elif card.steady and card.property("flash"):
                card.set_flash(False)   # with reduced motion only the last key pressed stays lit
        name = self.app_pick.currentText()
        self.practice.setText(f"{cap(key)} → {label}. In {name} that presses {sends}.")
        self.backend.announce(label)

    def refresh_power(self):
        on = self.engine.enabled
        self.power.setChecked(on)
        self.power.setText("One-hand mode is ON" if on else "One-hand mode is OFF")
        self.power.setAccessibleName(self.power.text())
        app = self.engine.profile_for(self._front)
        in_self = bool(self._front) and self._front.lower() in self.engine.self_app_ids
        hand = self.prefs.hand
        if not on:
            text = "Your keyboard works normally."
            self.practice.setText("")
        elif app:
            text = f"{app['name']} is in front: your {hand}-hand keys are {app['name']} commands."
        elif in_self:
            text = f"Try it here: press the {hand}-hand keys below to see what they do."
        else:
            text = "Waiting for Logic Pro or Pro Tools. Other apps type normally."
        self.status.setText(text)
        for _, _, card in self.cards:
            card.setProperty("active", bool(on and (app or in_self)))
            if not on:
                card.setProperty("flash", False)   # a key left lit by reduced motion goes out with the mode
            repolish(card)
        if self.tray:
            self.tray.setIcon(tray_icon(on))
            self.tray_toggle.setText("Turn one-hand mode off" if on else "Turn one-hand mode on")
            self.tray.setToolTip(f"{APP_NAME}: {'ON' if on else 'off'}")
        if on and self.prefs.show_badge:
            where = app["name"] if app else "waiting for your DAW"
            self.badge.show_text(f"ONE-HAND ON  ·  {hand.title()} hand  ·  {where}")
        else:
            self.badge.hide()

    def refresh_keys(self):
        app_id = self.app_pick.currentData()
        self.engine.preview_app = app_id
        app = next((a for a in self.layouts["apps"] if a["id"] == app_id), None)
        cmds = {c["key"]: c for c in app["commands"]} if app else {}
        right = self.prefs.hand == "right"
        for r, c, card in self.cards:
            left_key = ROWS[r][len(ROWS[r]) - 1 - c] if right else ROWS[r][c]
            key = MIRROR[left_key] if right else left_key
            cmd = cmds.get(left_key)
            card.show_command(key, cmd["label"] if cmd else "",
                              shortcut_text(cmd["send"], cmd.get("mods", []), self.backend.platform) if cmd else "")
        notes = [f"{c['label']}: {c['note']}" for c in cmds.values() if c.get("note")]
        self.note.setText("\n".join(notes))
        self.note.setVisible(bool(notes))
        self.fit_to_text()   # another DAW's shortcuts can need more room

    # ---- window life -------------------------------------------------

    def resizeEvent(self, event):
        self.fit_columns(event.size().width())
        super().resizeEvent(event)

    def bring_back(self):
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def closeEvent(self, event):
        if self.tray and not self._quitting:
            event.ignore()
            self.hide()
            if not self.prefs.seen_menu_tip:
                self.prefs.seen_menu_tip = True
                self.prefs.save()
                self.tray.showMessage(APP_NAME, "One-Hand is still running in the menu bar. "
                                      "Double-tap Shift any time to switch one-hand mode.",
                                      tray_icon(False), 6000)
            return
        self.shutdown()
        super().closeEvent(event)

    def shutdown(self):
        if getattr(self, "_shut", False):
            return
        self._shut = True
        self.timer.stop()
        self.perm_timer.stop()
        self.badge.hide()
        if self.tray:
            self.tray.hide()
        self.suite.stop()
        self.backend.stop()

    def quit(self):
        self._quitting = True
        self.shutdown()
        QApplication.quit()


def main(backend=None):
    applog.start("Limitless One-Hand", __version__)
    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationDisplayName(APP_NAME)
    app.setWindowIcon(app_icon())
    app.setQuitOnLastWindowClosed(False)
    win = MainWindow(backend or get_backend(), Prefs.load(), load_layouts())
    if "--hidden" not in sys.argv or not win.tray:
        win.show()

    def reopened(state):  # clicking the Dock icon brings the window back
        if state == Qt.ApplicationState.ApplicationActive and not win.isVisible() and not win._quitting:
            win.bring_back()
    app.applicationStateChanged.connect(reopened)
    app.aboutToQuit.connect(win.shutdown)
    return app.exec()
