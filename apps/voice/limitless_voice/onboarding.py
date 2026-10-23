"""First-launch setup: a short, friendly walk through everything Limitless
Voice needs, so it works the first time.

  1. Welcome
  2. Microphone permission
  3. Permission to press keys in other apps (Mac Accessibility)
  4. Microphone check: pick a mic, watch the level, say something
  5. Preferences: spoken feedback, on-screen display
  6. Ready: the first commands to try

Permissions are checked every second, so a page moves on by itself the
moment the person flips the switch in System Settings. Everything works by
keyboard and with a screen reader, and every page is read out.

Its words are in Voice's language (words.py) and change in place when that
changes. The commands it suggests are in the language Voice listens in.
"""

import unicodedata

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QHBoxLayout, QProgressBar, QPushButton,
    QStackedWidget, QVBoxLayout, QWidget,
)

from . import words
from .audio import list_input_devices
from .look import LiveText, add_item, grow, label, sized
from .settings import APP_NAME
from .words import phrase, ui

# What to say (in the language Voice listens in), and what it does (in Voice's language)
STARTER_COMMANDS = [
    ("what can I say", "every command for the app you're in"),
    ("play  /  stop  /  record", "transport"),
    ("go to bar thirty two", "jump anywhere"),
    ("solo track  /  mute track", "the selected track"),
    ("show the mixer", "windows and views"),
    ("nudge right four times", "repeat anything"),
    ("press command S", "any shortcut"),
    ("go to sleep  /  wake up", "pause listening"),
]


def _title(text):
    lbl = sized(label(text), 1.8, bold=True)
    lbl.setWordWrap(True)
    return lbl


def _body(text):
    lbl = label(text)
    lbl.setWordWrap(True)
    lbl.setTextFormat(Qt.RichText)
    lbl.setTextInteractionFlags(Qt.TextSelectableByKeyboard | Qt.TextSelectableByMouse)
    return sized(lbl, 1.15)


def _status(about, text=""):
    lbl = sized(LiveText(about, text), 1.15, bold=True)
    lbl.setWordWrap(True)
    return lbl


def _button(text):
    b = QPushButton()
    words.show(b.setText, text)
    return b


def _plain(text):
    """Lower case without accents, to compare what was heard: "Qué" and "que" alike."""
    return "".join(c for c in unicodedata.normalize("NFD", text.lower()) if not unicodedata.combining(c))


class Page(QWidget):
    """One step. spoken() is read aloud when the page appears."""

    def __init__(self, wizard):
        super().__init__()
        self.wizard = wizard
        self.box = QVBoxLayout(self)
        self.box.setSpacing(16)
        self.box.setContentsMargins(8, 8, 8, 8)

    def spoken(self):
        return ""

    def entered(self):
        pass

    def left(self):
        pass

    def ready(self):
        return True


class SetupWizard(QDialog):
    mic_answer = Signal(bool)

    def __init__(self, window):
        super().__init__(window)
        self.window = window
        self.platform = window.platform
        self.settings = window.settings
        words.show(self.setWindowTitle, ui.text("Set up {app}", app=APP_NAME))
        self.setModal(True)
        self.setMinimumSize(620, 520)
        grow(self, window.look["textScale"])   # room for larger text

        self.stack = QStackedWidget()
        self.back_btn = _button(ui.text("Back"))
        self.next_btn = _button(ui.text("Continue"))
        self.next_btn.setDefault(True)
        self.back_btn.clicked.connect(self.back)
        self.next_btn.clicked.connect(self.forward)
        self.step_label = LiveText(ui.text("Setup step"))

        nav = QHBoxLayout()
        nav.addWidget(self.step_label)
        nav.addStretch(1)
        nav.addWidget(self.back_btn)
        nav.addWidget(self.next_btn)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 20)
        layout.addWidget(self.stack, 1)
        layout.addLayout(nav)

        self.pages = [WelcomePage(self), MicPermissionPage(self), ControlPermissionPage(self),
                      MicCheckPage(self), PreferencesPage(self), ReadyPage(self)]
        for p in self.pages:
            self.stack.addWidget(p)

        self.poll = QTimer(self)
        self.poll.timeout.connect(self._refresh)
        self.poll.start(1000)
        self.mic_answer.connect(lambda granted: self._refresh())
        self._show(0)

    # -- navigation ------------------------------------------------------

    @property
    def page(self):
        return self.pages[self.stack.currentIndex()]

    def _show(self, i):
        if self.stack.currentIndex() != i:
            self.page.left()
        self.stack.setCurrentIndex(i)
        self.page.entered()
        last = i == len(self.pages) - 1
        words.show(self.next_btn.setText, ui.text("Start using {app}", app=APP_NAME) if last else ui.text("Continue"))
        self.back_btn.setEnabled(i > 0)
        self.step_label.setText(ui.text("Step {n} of {total}", n=i + 1, total=len(self.pages)))
        self._refresh()
        self.next_btn.setFocus()
        spoken = self.page.spoken()
        if spoken:
            self.window.speaker.say(spoken)

    def _refresh(self):
        self.next_btn.setEnabled(self.page.ready())
        if hasattr(self.page, "refresh"):
            self.page.refresh()
            self.next_btn.setEnabled(self.page.ready())

    def forward(self):
        i = self.stack.currentIndex()
        if i == len(self.pages) - 1:
            self.accept()
            return
        nxt = i + 1
        # skip permission pages that are already done
        while nxt < len(self.pages) - 1 and getattr(self.pages[nxt], "already_done", lambda: False)():
            nxt += 1
        self._show(nxt)

    def back(self):
        i = self.stack.currentIndex()
        prev = i - 1
        while prev > 0 and getattr(self.pages[prev], "already_done", lambda: False)():
            prev -= 1
        self._show(max(0, prev))

    def advance_if_on(self, page):
        """Move on by itself once a permission is granted (after a beat to read the tick)."""
        if self.page is page:
            # bound to the guide, so a guide closed before then doesn't move on
            QTimer.singleShot(900, self, lambda: self.page is page and self.forward())

    # -- events from the main window ---------------------------------------

    def on_heard(self, heard, alternative):
        if isinstance(self.page, MicCheckPage):
            self.page.heard(heard, alternative)

    def on_level(self, level):
        if isinstance(self.page, MicCheckPage):
            self.page.level.setValue(int(level * 100))

    def done(self, result):
        self.poll.stop()
        self.page.left()
        self.settings.first_run_done = True
        self.settings.save()
        super().done(result)


class WelcomePage(Page):
    def spoken(self):
        return ui.text("Welcome to Limitless Voice. Setup takes about a minute. Press Continue.")

    def __init__(self, wizard):
        super().__init__(wizard)
        self.box.addWidget(_title(ui.text("Welcome to Limitless Voice")))
        self.box.addWidget(_body(ui.text(
            "Run Logic Pro, Pro Tools and your whole computer with your voice.<br><br>"
            "Say <b>“{bar}”</b>, <b>“{solo}”</b> or <b>“{mixer}”</b>, and it happens in the app "
            "you're working in.<br><br>"
            "Everything runs on this computer. Your voice is never recorded or sent anywhere, "
            "and it works without internet.<br><br>"
            "Setup takes about a minute.",
            bar=phrase("go to bar thirty two"), solo=phrase("solo track"),
            mixer=phrase("show the mixer"))))
        self.box.addStretch(1)


class MicPermissionPage(Page):
    def spoken(self):
        return ui.text("First, Limitless Voice needs to hear you. Press Allow microphone.")

    def __init__(self, wizard):
        super().__init__(wizard)
        self.box.addWidget(_title(ui.text("Let Limitless Voice hear you")))
        self.box.addWidget(_body(ui.text(
            "Your computer will ask whether Limitless Voice may use the microphone. "
            "Choose <b>Allow</b>.<br><br>Audio is turned into words on this computer and then thrown away.")))
        self.button = _button(ui.text("Allow microphone"))
        self.button.setMinimumHeight(48)
        self.button.clicked.connect(self.ask)
        self.box.addWidget(self.button)
        self.status = _status(ui.text("Microphone permission"))
        self.box.addWidget(self.status)
        self.box.addStretch(1)
        self._announced = None

    def already_done(self):
        return self.wizard.platform.mic_permission() == "granted"

    def ask(self):
        p = self.wizard.platform
        state = p.mic_permission()
        if state == "ask":
            p.request_mic_permission(self.wizard.mic_answer.emit)
        elif state == "denied":
            p.open_settings(p.mic_settings_link())

    def refresh(self):
        state = self.wizard.platform.mic_permission()
        if state == "granted":
            text = ui.text("✓ Microphone allowed")
            self.button.hide()
            self.wizard.window.start_listener()
            if self._announced != state:
                self.wizard.advance_if_on(self)
        elif state == "denied":
            text = ui.text("The microphone is turned off for Limitless Voice. Press the button to open "
                           "Microphone settings, turn on Limitless Voice, and come back.")
            words.show(self.button.setText, ui.text("Open Microphone settings"))
            self.button.show()
        else:
            text = ""
        if state != self._announced:
            self._announced = state
            self.status.setText(text)
            if text:
                self.wizard.window.speaker.say(text.replace("✓ ", ""))

    def ready(self):
        return self.wizard.platform.mic_permission() == "granted"


class ControlPermissionPage(Page):
    def spoken(self):
        return ui.text("Next, allow Limitless Voice to control the computer. Press the button, "
                       "turn on Limitless Voice in the list, then come back.")

    def __init__(self, wizard):
        super().__init__(wizard)
        self.box.addWidget(_title(ui.text("Let your voice press the keys")))
        self.box.addWidget(_body(ui.text(
            "To play, record and edit for you, Limitless Voice presses keys in Logic and "
            "Pro Tools, the same way you would.<br><br>"
            "macOS needs your OK for that:<br>"
            "1. Press <b>Open Accessibility settings</b>.<br>"
            "2. Turn on the switch next to <b>Limitless Voice</b> (you may need your password).<br>"
            "3. Come back here. This page notices by itself.")))
        self.button = _button(ui.text("Open Accessibility settings"))
        self.button.setMinimumHeight(48)
        self.button.clicked.connect(self.ask)
        self.box.addWidget(self.button)
        self.status = _status(ui.text("Permission to press keys"))
        self.box.addWidget(self.status)
        self.skip = _button(ui.text("Skip for now (commands won't work until this is on)"))
        self.skip.setFlat(True)
        self.skip.clicked.connect(self.wizard.forward)
        self.box.addWidget(self.skip)
        self.box.addStretch(1)
        self._was = None

    def already_done(self):
        return self.wizard.platform.control_permission()

    def ask(self):
        p = self.wizard.platform
        p.request_control_permission()
        p.open_settings(p.control_settings_link())

    def refresh(self):
        ok = self.wizard.platform.control_permission()
        if ok != self._was:
            self._was = ok
            if ok:
                self.status.setText(ui.text("✓ Allowed. Limitless Voice can press keys for you."))
                self.button.hide()
                self.skip.hide()
                self.wizard.window.speaker.say(ui.text("Allowed"))
                self.wizard.advance_if_on(self)
            else:
                self.status.setText(ui.text("Waiting for the switch to be turned on…"))

    def ready(self):
        return self.wizard.platform.control_permission()


class MicCheckPage(Page):
    def spoken(self):
        return ui.text("Let's check the microphone. Say: {phrase}.", phrase=phrase("what can I say"))

    def __init__(self, wizard):
        super().__init__(wizard)
        self.box.addWidget(_title(ui.text("Check your microphone")))
        self.box.addWidget(_body(ui.text(
            "Pick the microphone you'll use, then say <b>“{phrase}”</b>.<br>"
            "The bar should move when you talk. A headset or a mic close to your mouth works "
            "best when speakers are playing.", phrase=phrase("what can I say"))))
        row = QHBoxLayout()
        lbl = label(ui.text("&Microphone"))
        self.mics = QComboBox()
        words.show(self.mics.setAccessibleName, ui.text("Microphone"))
        # what VoiceOver reads as its label
        words.show(self.mics.setAccessibleDescription, ui.text("Microphone to listen with"))
        lbl.setBuddy(self.mics)
        row.addWidget(lbl)
        row.addWidget(self.mics, 1)
        self.box.addLayout(row)
        self.level = QProgressBar()
        self.level.setRange(0, 100)
        self.level.setTextVisible(False)
        self.level.setFixedHeight(26)
        words.show(self.level.setAccessibleName, ui.text("Microphone level"))
        self.box.addWidget(self.level)
        self.result = _status(ui.text("What was heard"), ui.text("Listening…"))
        self.box.addWidget(self.result)
        self.box.addStretch(1)
        self.got_it = False
        self.mics.currentIndexChanged.connect(self._mic_changed)

    def entered(self):
        w = self.wizard.window
        w.start_listener()
        self.mics.blockSignals(True)
        self.mics.clear()
        add_item(self.mics, ui.text("System default microphone"), "")
        try:
            for d in list_input_devices():
                # a microphone's name is its own, in any language
                add_item(self.mics, ui.text("{name} (default)", name=d.name) if d.is_default else d.name, d.name)
        except Exception:
            pass
        self.mics.setCurrentIndex(max(0, self.mics.findData(self.wizard.settings.mic_name)))
        self.mics.blockSignals(False)

    def _mic_changed(self):
        self.wizard.window.choose_mic(self.mics.currentData() or "")
        self.result.setText(ui.text("Listening…"))

    def heard(self, heard, alternative):
        said = (alternative or heard or "").replace("[unk]", "").strip()
        if not said:
            return
        asked = phrase("what can I say")
        if _plain(asked) in _plain(heard + " " + alternative):
            self.result.setText(ui.text("✓ Heard “{text}”. Your microphone works.", text=said))
            self.wizard.window.speaker.say(ui.text("Got it. Your microphone works."))
        else:
            self.result.setText(ui.text("Heard “{text}”. Try once more: “{phrase}”.", text=said, phrase=asked))
        self.got_it = True


class PreferencesPage(Page):
    def spoken(self):
        return ui.text("Choose how Limitless Voice tells you what it did.")

    def __init__(self, wizard):
        super().__init__(wizard)
        s = wizard.settings
        self.box.addWidget(_title(ui.text("How should it answer you?")))
        self.speak = QCheckBox()
        words.show(self.speak.setText, ui.text("Say what happened out loud (“Recording”, “Bar 32”)"))
        self.speak.setChecked(s.speak_feedback)
        self.hud = QCheckBox()
        words.show(self.hud.setText, ui.text("Show what I said at the bottom of the screen"))
        self.hud.setChecked(s.show_hud)
        self.big = QCheckBox()
        words.show(self.big.setText, ui.text("Larger text"))
        self.big.setChecked(s.text_scale > 1.0)
        self.contrast = QCheckBox()
        words.show(self.contrast.setText, ui.text("High contrast colours"))
        self.contrast.setChecked(s.high_contrast)
        self.start = QCheckBox()
        words.show(self.start.setText, ui.text("Start Limitless Voice when I log in"))
        self.start.setChecked(s.extra.get("login_item", False))
        for cb in (self.speak, self.hud, self.big, self.contrast, self.start):
            cb.setMinimumHeight(36)
            self.box.addWidget(cb)
        self.box.addStretch(1)

    def left(self):
        s = self.wizard.settings
        s.speak_feedback = self.speak.isChecked()
        s.show_hud = self.hud.isChecked()
        s.text_scale = 1.3 if self.big.isChecked() else 1.0
        s.high_contrast = self.contrast.isChecked()
        s.extra["login_item"] = self.start.isChecked()
        s.save()
        self.wizard.window.apply_settings()
        self.wizard.window.set_login_item(self.start.isChecked())


class ReadyPage(Page):
    def spoken(self):
        return ui.text("You're all set. Click into Logic or Pro Tools and try: {play}, {bar}, or {mixer}. "
                       "Say {help} any time for the full list.",
                       play=phrase("play"), bar=phrase("go to bar thirty two"),
                       mixer=phrase("show the mixer"), help=phrase("what can I say"))

    def __init__(self, wizard):
        super().__init__(wizard)
        self.box.addWidget(_title(ui.text("You're all set")))
        self.box.addWidget(_body(ui.text(
            "Click into Logic Pro or Pro Tools and try one of these. Limitless Voice keeps "
            "working from the menu bar when this window is closed.")))
        grid = QVBoxLayout()
        for say, what in STARTER_COMMANDS:
            row = label(ui.text("<b>“{say}”</b> &nbsp; <span style='color:gray'>{what}</span>",
                                say=phrase(say), what=ui.text(what)))
            row.setTextFormat(Qt.RichText)
            row.setWordWrap(True)
            grid.addWidget(sized(row, 1.15))
        self.box.addLayout(grid)
        self.box.addStretch(1)
