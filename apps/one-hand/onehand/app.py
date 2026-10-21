"""The control window: one big on/off button, hand choice, the key map, options."""
import sys

from PySide6.QtCore import QObject, Qt, QTimer, Signal
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (QApplication, QButtonGroup, QCheckBox, QComboBox, QFrame, QGridLayout,
                               QHBoxLayout, QLabel, QPushButton, QScrollArea, QVBoxLayout, QWidget)

from .engine import Engine, Settings
from .keys import MIRROR, ROWS, cap, shortcut_text
from .platform_sim import get_backend
from .settings import APP_NAME, Prefs, load_layouts
from .suite import Suite

STYLE = """
QWidget { background: #111; color: #fff; font-size: 18px; }
QLabel#title { font-size: 26px; font-weight: 800; }
QLabel#status { font-size: 20px; }
QLabel#hint { color: #ccc; }
QPushButton { background: #2a2a2a; color: #fff; border: 3px solid #888; border-radius: 12px; padding: 12px; }
QPushButton:focus { border-color: #4fc3ff; }
QPushButton:checked { background: #ffe600; color: #000; border-color: #ffe600; font-weight: 800; }
QPushButton#power { font-size: 30px; font-weight: 800; min-height: 110px; }
QPushButton#power:checked { background: #ffe600; color: #000; }
QFrame#key { border: 2px solid #666; border-radius: 10px; background: #1b1b1b; }
QFrame#key[active="true"] { border-color: #ffe600; }
QLabel#cap { background: #ffe600; color: #000; font-weight: 800; font-size: 22px; padding: 0 8px; border-radius: 6px; }
QLabel#cmd { font-weight: 700; background: transparent; }
QLabel#sends { color: #bbb; font-size: 15px; background: transparent; }
QFrame#banner { background: #5a1a00; border: 2px solid #ff8a50; border-radius: 10px; }
QFrame#banner QLabel { background: transparent; }
QCheckBox { spacing: 12px; padding: 4px; }
QCheckBox::indicator { width: 26px; height: 26px; border: 2px solid #ccc; border-radius: 5px; background: #111; }
QCheckBox::indicator:checked { background: #ffe600; border-color: #ffe600; }
QScrollArea { border: none; }
QComboBox { padding: 6px; border: 2px solid #888; border-radius: 8px; }
"""


class KeyCard(QFrame):
    def __init__(self):
        super().__init__()
        self.setObjectName("key")
        self.setMinimumSize(130, 118)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 6, 8, 6)
        lay.setSpacing(2)
        self.cap = QLabel(objectName="cap")
        self.cap.setSizePolicy(self.cap.sizePolicy().Policy.Maximum, self.cap.sizePolicy().Policy.Fixed)
        self.cmd = QLabel(objectName="cmd", wordWrap=True)
        self.sends = QLabel(objectName="sends")
        for w in (self.cap, self.cmd, self.sends):
            lay.addWidget(w)
        lay.addStretch()

    def show_command(self, key, label, sends):
        self.cap.setText(cap(key))
        self.cmd.setText(label)
        self.sends.setText(sends)
        self.setAccessibleName(f"{cap(key)} key: {label or 'nothing'}")


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
        self._seen_changes = 0
        self._front = None

        self.setWindowTitle(APP_NAME)
        self.setStyleSheet(STYLE)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea(widgetResizable=True)
        outer.addWidget(scroll)
        content = QWidget()
        scroll.setWidget(content)
        root = QVBoxLayout(content)
        root.setContentsMargins(20, 16, 20, 16)
        root.setSpacing(12)

        root.addWidget(QLabel(APP_NAME, objectName="title"))

        self.banner = QFrame(objectName="banner")
        bl = QVBoxLayout(self.banner)
        self.banner_text = QLabel(wordWrap=True)
        bl.addWidget(self.banner_text)
        row = QHBoxLayout()
        self.open_settings = QPushButton("Open System Settings")
        self.open_settings.clicked.connect(lambda: self.backend.open_permission_settings())
        retry = QPushButton("Try again")
        retry.clicked.connect(self.start_backend)
        row.addWidget(self.open_settings)
        row.addWidget(retry)
        row.addStretch()
        bl.addLayout(row)
        root.addWidget(self.banner)

        self.power = QPushButton(objectName="power", checkable=True)
        self.power.clicked.connect(lambda checked: self.engine.set_enabled(checked))
        root.addWidget(self.power)
        hint = QLabel("Click the button, double-tap Shift, or press a foot pedal set to F18.",
                      objectName="hint", wordWrap=True)
        root.addWidget(hint)

        self.status = QLabel(objectName="status", wordWrap=True)
        root.addWidget(self.status)

        hands = QHBoxLayout()
        hands.addWidget(QLabel("I'm using my"))
        self.hand_group = QButtonGroup(self)
        for hand in ("left", "right"):
            b = QPushButton(f"{hand.title()} hand", checkable=True)
            b.setAccessibleName(f"Use {hand} hand layout")
            b.setChecked(prefs.hand == hand)
            b.clicked.connect(lambda _=False, h=hand: self.set_hand(h))
            self.hand_group.addButton(b)
            hands.addWidget(b)
        hands.addStretch()
        root.addLayout(hands)

        pick = QHBoxLayout()
        pick.addWidget(QLabel("Keys for"))
        self.app_pick = QComboBox()
        self.app_pick.setAccessibleName("Show keys for app")
        for app in layouts["apps"]:
            if app.get(backend.platform):
                self.app_pick.addItem(app["name"], app["id"])
        self.app_pick.currentIndexChanged.connect(self.refresh_keys)
        pick.addWidget(self.app_pick)
        pick.addStretch()
        root.addLayout(pick)

        grid = QGridLayout()
        grid.setSpacing(8)
        self.cards = []
        for r, row_keys in enumerate(ROWS):
            for c in range(len(row_keys)):
                card = KeyCard()
                grid.addWidget(card, r, c)
                self.cards.append((r, c, card))
        root.addLayout(grid)
        self.note = QLabel(objectName="hint", wordWrap=True)
        root.addWidget(self.note)

        self.add_option(root, "Hold Space to type letters from the other side", "mirror_typing")
        self.add_option(root, "Double-tap Shift switches one-hand mode", "double_shift")
        if backend.platform == "windows":
            self.add_option(root, "Caps Lock switches one-hand mode", "caps_lock_toggle")
        self.add_option(root, "Play a sound when switching", "play_sounds")
        self.add_option(root, "Say “on” and “off” out loud", "speak")
        self.add_option(root, "Keep this window on top", "keep_on_top", self.apply_on_top)

        QShortcut(QKeySequence("Ctrl+Q"), self, activated=QApplication.quit)

        self._main_thread = MainThread()
        self.suite = Suite(self.engine, backend, self.set_hand, dispatch=self._main_thread.call.emit).start()

        self.timer = QTimer(self, interval=150, timeout=self.tick)
        self.timer.start()
        self.apply_on_top()
        self.start_backend()
        self.refresh_power()
        self.refresh_keys()

    # ---- setup helpers -----------------------------------------------

    def _engine_settings(self):
        p = self.prefs
        return Settings(hand=p.hand, mirror_typing=p.mirror_typing, double_shift=p.double_shift,
                        toggle_keys=p.toggle_keys())

    def add_option(self, layout, text, attr, extra=None):
        box = QCheckBox(text)
        box.setChecked(getattr(self.prefs, attr))

        def changed(state):
            setattr(self.prefs, attr, box.isChecked())
            self.prefs.save()
            with self.engine.lock:
                self.engine.settings = self._engine_settings()
            if extra:
                extra()
        box.stateChanged.connect(changed)
        layout.addWidget(box)

    def start_backend(self):
        try:
            self.backend.stop()
            self.backend.error = None
            self.backend.start(self.engine)
            self.banner.hide()
        except Exception as exc:
            self.banner_text.setText(f"{exc}\n\n{self.backend.permission_help() or ''}".strip())
            self.open_settings.setVisible(self.backend.platform == "mac")
            self.banner.show()

    def apply_on_top(self):
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, self.prefs.keep_on_top)
        if self.isVisible():
            self.show()

    def set_hand(self, hand):
        self.prefs.hand = hand
        self.prefs.save()
        for b in self.hand_group.buttons():
            b.setChecked(b.text().lower().startswith(hand))
        with self.engine.lock:
            self.engine.settings = self._engine_settings()
        self.refresh_keys()
        self.suite.hand_changed(hand)

    # ---- live updates ------------------------------------------------

    def tick(self):
        if self.engine.changes != self._seen_changes:
            self._seen_changes = self.engine.changes
            self.refresh_power()
            on = self.engine.enabled
            if self.prefs.play_sounds:
                self.backend.play_sound(on)
            self.suite.mode_changed(on)
            if self.prefs.speak:
                text = "One hand on" if on else "One hand off"
                if not self.suite.say(text):
                    self.backend.speak(text)
        front = self.backend.front_app()
        if front != self._front:
            self._front = front
            app = self.engine.profile_for(front)
            if app:
                i = self.app_pick.findData(app["id"])
                if i >= 0:
                    self.app_pick.setCurrentIndex(i)
            self.refresh_power()

    def refresh_power(self):
        on = self.engine.enabled
        self.power.setChecked(on)
        self.power.setText("One-hand mode is ON" if on else "One-hand mode is OFF")
        self.power.setAccessibleName(self.power.text())
        app = self.engine.profile_for(self._front)
        if not on:
            text = "Your keyboard works normally."
        elif app:
            text = f"{app['name']} is in front. Your {self.prefs.hand}-hand keys are now {app['name']} commands."
        else:
            text = "Waiting for a supported app. Other apps type normally."
        self.status.setText(text)
        for _, _, card in self.cards:
            card.setProperty("active", bool(on and app))
            card.style().unpolish(card)
            card.style().polish(card)

    def refresh_keys(self):
        app_id = self.app_pick.currentData()
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

    def closeEvent(self, event):
        self.suite.stop()
        self.backend.stop()
        super().closeEvent(event)


def main(backend=None):
    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    font = app.font()
    font.setPointSize(16)
    app.setFont(font)
    win = MainWindow(backend or get_backend(), Prefs.load(), load_layouts())
    win.show()
    return app.exec()
