"""The desktop app: one window, a big Listen button, and everything spoken back.

Built to be usable by voice alone, by keyboard alone, with a screen reader
(VoiceOver, NVDA, Narrator, JAWS), or with low vision: every control has an
accessible name, results are announced, text can be enlarged and there's a
high-contrast theme. With the Limitless Sound hub running, the suite's shared
text size, high contrast and reduced motion settings apply too (look.py).
"""

import os
import sys
import threading
from pathlib import Path

from PySide6.QtCore import QObject, Qt, QTimer, Signal, QUrl
from PySide6.QtGui import QAction, QDesktopServices, QIcon, QKeySequence
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QDialog, QDialogButtonBox, QDoubleSpinBox,
    QFormLayout, QFrame, QHBoxLayout, QLineEdit, QListWidget, QListWidgetItem, QMainWindow,
    QMessageBox, QProgressBar, QProgressDialog, QPushButton, QSlider, QSystemTrayIcon,
    QMenu, QVBoxLayout, QWidget,
)

from . import __version__, applog, mac_keys, words
from .audio import Listener, list_input_devices
from .engine import Engine
from .grammar import DEFAULT_PACK_DIR, load_packs
from .look import LiveText, add_item, grow, in_use, label, resize_text, sized
from .model import DEFAULT_MODEL, MODELS, download_model, find_model
from .language import ENGLISH, available, load as load_language, model_for, model_language, wanted
from .platforms import current_os, get_platform
from .settings import APP_NAME, Settings, user_packs_dir
from .hud import Hud, state_icon
from .suite import Suite
from .voice_out import Speaker
from .words import phrase, ui

OWN_NAMES = (APP_NAME, "LimitlessVoice", "Limitless Voice.exe", "python", "python3", "Python")

HIGH_CONTRAST = """
QWidget { background: #000; color: #ffeb3b; }
QPushButton { background: #111; color: #fff; border: 3px solid #ffeb3b; padding: 4px 10px; }
QPushButton:checked { background: #003a40; }
QPushButton:focus { border-color: #00e5ff; }
QPushButton:disabled { color: #9e9e9e; border: 3px dashed #9e9e9e; }
QComboBox, QLineEdit, QListWidget, QDoubleSpinBox { background: #111; color: #fff; border: 2px solid #ffeb3b; }
QComboBox, QLineEdit, QListWidget, QDoubleSpinBox, QComboBox QAbstractItemView, QMenu {
    selection-background-color: #ffeb3b; selection-color: #000; }
QComboBox:focus, QLineEdit:focus, QListWidget:focus, QDoubleSpinBox:focus, QSlider:focus {
    border: 3px solid #00e5ff; }
QMenu, QToolTip { background: #000; color: #fff; border: 2px solid #ffeb3b; }
QMenu::item:selected { background: #ffeb3b; color: #000; }
QMenu::item:disabled, QCheckBox:disabled { color: #9e9e9e; }
QCheckBox::indicator { width: 18px; height: 18px; border: 2px solid #ffeb3b; background: #111; }
QCheckBox::indicator:checked { background: #00e5ff; }
QCheckBox:focus { color: #00e5ff; }
QSlider::groove:horizontal { height: 6px; background: #444; }
QSlider::handle:horizontal { width: 18px; margin: -7px 0; background: #00e5ff; border: 2px solid #ffeb3b; }
QProgressBar { border: 2px solid #ffeb3b; color: #fff; }
QProgressBar::chunk { background: #00e5ff; }
"""


def command_phrases(packs, language=ENGLISH):
    """Everything the command recognizer should listen for."""
    return language.recognizer_phrases(packs)


def announce(widget, text):
    """Ask the screen reader to read text aloud, if one is running."""
    try:
        from PySide6.QtGui import QAccessible, QAccessibleAnnouncementEvent
        QAccessible.updateAccessibility(QAccessibleAnnouncementEvent(widget, text))
    except Exception:
        pass


def add_row(form, text, field):
    """A row of a form with its label, the label's words following Voice's language."""
    form.addRow(text, field)
    words.keep(form.labelForField(field).setText, text)


class Bridge(QObject):
    """Carries events from the mic thread to the window thread."""
    heard = Signal(str, str)
    level = Signal(float)
    error = Signal(object)  # words.Text, so a problem shown is shown again in another language
    call = Signal(object)   # calls from the Limitless Sound link


class CommandsDialog(QDialog):
    """Every command, in the language Voice listens in; its own words in Voice's language."""

    def __init__(self, parent, engine):
        super().__init__(parent)
        lang = engine.lang
        words.show(self.setWindowTitle, ui.text("What you can say"))
        self.engine = engine
        layout = QVBoxLayout(self)
        app = engine.current_app_name()
        title = label(ui.text("Commands for {app}. Words in [brackets] are optional; {number} means say a number.",
                              app=app or ui.text("any app"), number="{number}"))
        title.setWordWrap(True)
        layout.addWidget(title)
        self.search = QLineEdit()
        words.show(self.search.setPlaceholderText, ui.text("Search commands"))
        words.show(self.search.setAccessibleName, ui.text("Search commands"))
        layout.addWidget(self.search)
        self.list = QListWidget()
        words.show(self.list.setAccessibleName, ui.text("Commands"))
        layout.addWidget(self.list, 1)
        self.rows = []
        for c in engine.commands_for(app):
            phrases = " / ".join(c.phrases).replace(":number}", "}").replace(":text}", "}").replace(":keys}", "}")
            self.rows.append(f"{phrases}   ({c.pack})" + (f": {c.help}" if c.help else ""))
        always = ui.text("always")
        self.rows += [
            ui.text("{phrases}   ({note})", phrases=f"{lang.first('sleep')} / {lang.first('wake')}", note=always),
            ui.text("{phrases}   ({note})", phrases=f"{lang.first('dictation_on')} / {lang.first('dictation_off')}",
                    note=always),
            ui.text("{phrases}   ({note})", phrases=lang.first("again"), note=ui.text("repeats the last command")),
            lang.text("... N times   (e.g. nudge right 4 times)"),   # what to say: in the language listened in
        ]
        self._filter("")
        self.search.textChanged.connect(self._filter)
        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        words.show(buttons.button(QDialogButtonBox.Close).setText, ui.text("Close"))
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.resize(640, 560)

    def _filter(self, text):
        self.list.clear()
        for row in map(words.again, self.rows):
            if text.lower() in row.lower():
                words.show(QListWidgetItem(self.list).setText, row)


class SettingsDialog(QDialog):
    def __init__(self, parent, settings, suite_language=None):
        """suite_language: Limitless Sound's language, for "Same as Limitless Sound"."""
        super().__init__(parent)
        words.show(self.setWindowTitle, ui.text("Settings"))
        self.settings = settings
        self.suite_language = suite_language or wanted("", None, settings.extra.get("suite_language", ""))
        form = QFormLayout(self)

        self.speak = QCheckBox()
        words.show(self.speak.setText, ui.text("Say what happened out loud"))
        self.speak.setChecked(settings.speak_feedback)
        form.addRow(self.speak)

        self.rate = QSlider(Qt.Horizontal)
        self.rate.setRange(120, 300)
        self.rate.setValue(settings.voice_rate)
        words.show(self.rate.setAccessibleName, ui.text("Speaking speed"))
        add_row(form, ui.text("Speaking speed"), self.rate)

        self.start_listening = QCheckBox()
        words.show(self.start_listening.setText, ui.text("Start listening when the app opens"))
        self.start_listening.setChecked(settings.start_listening)
        form.addRow(self.start_listening)

        self.vocab = QCheckBox()
        words.show(self.vocab.setText,
                   ui.text("Listen for command words only (more accurate; turn off if commands are missed)"))
        self.vocab.setChecked(settings.command_vocabulary)
        form.addRow(self.vocab)

        self.on_top = QCheckBox()
        words.show(self.on_top.setText, ui.text("Keep this window on top of other apps"))
        self.on_top.setChecked(settings.keep_on_top)
        form.addRow(self.on_top)

        self.scale = QDoubleSpinBox()
        self.scale.setRange(0.8, 3.0)
        self.scale.setSingleStep(0.1)
        self.scale.setValue(settings.text_scale)
        words.show(self.scale.setAccessibleName, ui.text("Text size"))
        add_row(form, ui.text("Text size"), self.scale)

        self.contrast = QCheckBox()
        words.show(self.contrast.setText, ui.text("High contrast colours"))
        self.contrast.setChecked(settings.high_contrast)
        form.addRow(self.contrast)

        # Shortcuts are written the way the keyboard library reads them, <ctrl> and all, in any language
        self.hotkey = QLineEdit(settings.hotkey)
        words.show(self.hotkey.setPlaceholderText,
                   ui.text("e.g. {example}, or {other}", example="<ctrl>+<alt>+l", other="<f13>"))
        words.show(self.hotkey.setAccessibleName, ui.text("Keyboard shortcut to turn listening on and off"))
        add_row(form, ui.text("Listen on/off shortcut"), self.hotkey)

        # Each language's name in itself, so someone who reads only that language finds it. Any
        # but English is downloaded once, the first time it's chosen.
        self.language = QComboBox()
        words.show(self.language.setAccessibleName, ui.text("Language"))
        words.show(self.language.setAccessibleDescription, ui.text("Language to listen and answer in"))
        same = load_language(self.suite_language).name
        add_item(self.language, ui.text("Same as Limitless Sound ({language})", language=same), "")
        for code, _ in available():
            lang = load_language(code)
            here = any(find_model(m) for m in lang.models)
            add_item(self.language, lang.label if here else
                     ui.text("{language} ({size} download)", language=lang.label, size=lang.models[lang.model]["size"]),
                     code)
        self.language.setCurrentIndex(max(0, self.language.findData(settings.language)))
        add_row(form, ui.text("Language"), self.language)
        self.language_note = LiveText(ui.text("About the language"))
        self.language_note.setWordWrap(True)
        form.addRow(self.language_note)

        self.model = QComboBox()
        words.show(self.model.setAccessibleName, ui.text("Speech model"))
        # what VoiceOver reads as its label
        words.show(self.model.setAccessibleDescription, ui.text("Speech model for listening"))
        add_row(form, ui.text("Speech model"), self.model)
        self._language_chosen()
        self.language.currentIndexChanged.connect(self._language_chosen)

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        words.show(buttons.button(QDialogButtonBox.Save).setText, ui.text("Save"))
        words.show(buttons.button(QDialogButtonBox.Cancel).setText, ui.text("Cancel"))
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)

    def chosen_language(self):
        return load_language(self.language.currentData() or self.suite_language)

    def _language_chosen(self):
        """The speech models for the language chosen, and whether it's a download."""
        lang = self.chosen_language()
        self.model.clear()
        for name, m in lang.models.items():
            # the models' labels are in English in the language files, and in the table like any words
            add_item(self.model, ui.text("{model} (installed)", model=ui.text(m["label"])) if find_model(name) else
                     ui.text("{model} ({size} download)", model=ui.text(m["label"]), size=m["size"]), name)
        self.model.setCurrentIndex(max(0, self.model.findData(model_for(lang, self.settings.model))))
        missing = not find_model(model_for(lang, self.settings.model))
        note = lang.text("{language} is downloaded once ({size}), then works without internet.",
                         language=lang.name, size=lang.models[lang.model]["size"]) if missing else ""
        note = " ".join(t for t in (lang.preview, note) if t)   # a preview says so first
        self.language_note.setText(note)
        self.language_note.setVisible(bool(note))

    def apply(self):
        s = self.settings
        s.speak_feedback = self.speak.isChecked()
        s.voice_rate = self.rate.value()
        s.start_listening = self.start_listening.isChecked()
        s.command_vocabulary = self.vocab.isChecked()
        s.keep_on_top = self.on_top.isChecked()
        s.text_scale = round(self.scale.value(), 1)
        s.high_contrast = self.contrast.isChecked()
        s.hotkey = self.hotkey.text().strip()
        s.model = self.model.currentData()
        s.language = self.language.currentData()
        s.save()


class MainWindow(QMainWindow):
    def __init__(self, settings, platform, model_path):
        super().__init__()
        self.settings = settings
        self.platform = platform
        self.listener = None
        self.bridge = Bridge()
        # The windows are in the language wanted from the start; it's listened in once its speech
        # model is here. self.lang is the language listened in (and replies are spoken in): the
        # speech model's it starts with, until apply_language() moves to the one wanted.
        words.use(wanted(settings.language, None, settings.extra.get("suite_language", "")))
        self.lang = load_language(model_language(Path(str(model_path)).name) or "en")
        words.listen_in(self.lang)
        self.speaker = Speaker(settings.speak_feedback, settings.voice_rate, on_busy=self._speaking,
                               on_no_voice=lambda lang: self.bridge.call.emit(lambda: self._no_voice(lang)))
        self.speaker.set_language(self.lang)
        self.hotkey_listener = None

        ensure_user_packs_dir()
        self.packs = load_packs([DEFAULT_PACK_DIR, user_packs_dir()], platform.os_name)   # in English
        self.engine = Engine(platform, self.lang.translate(self.packs), feedback=self._feedback,
                             start_awake=settings.start_listening, own_names=OWN_NAMES, language=self.lang)
        self._own_busy = self._suite_busy = False
        self.bridge.call.connect(lambda fn: fn())
        self.suite = Suite(self.engine, on_change=self._update_state, on_phrases=self._suite_phrases,
                           on_speaking=self._suite_speaking, on_look=self._suite_prefs,
                           dispatch=self.bridge.call.emit)
        self.suite.language = self.lang.code

        self._quitting = False
        self.hud = Hud()
        self._build_ui()
        self.apply_settings()

        self.listener = Listener(
            model_path, self._phrases(),
            on_text=self.bridge.heard.emit, on_level=self.bridge.level.emit,
            on_error=self.bridge.error.emit,
            device=self._device_index(settings.mic_name),
            use_command_vocabulary=settings.command_vocabulary, instant=self.engine.instant,
        )
        self.bridge.heard.connect(self.on_heard)
        self.bridge.level.connect(self._on_level)
        self.bridge.error.connect(self.on_mic_error)
        self.wizard = None
        self._listening_started = False
        self._last_problem = None
        # On a Mac, opening the mic before permission is granted gives silence,
        # so the listener starts once the microphone is allowed.
        if platform.mic_permission() == "granted":
            self.start_listener()
        self.suite.start()

        self.focus_timer = QTimer(self)
        self.focus_timer.timeout.connect(self._track_focus)
        self.focus_timer.start(500)
        self.permission_timer = QTimer(self)
        self.permission_timer.timeout.connect(self._check_permissions)
        self.permission_timer.start(2000)

        self._update_state()
        self._check_permissions()
        self.apply_language()

    def start_listener(self):
        if not self._listening_started and self.listener:
            self._listening_started = True
            self.listener.start()

    def choose_mic(self, name):
        self.settings.mic_name = name
        self.settings.save()
        idx = self.mic_combo.findData(name)
        self.mic_combo.blockSignals(True)
        self.mic_combo.setCurrentIndex(max(0, idx))
        self.mic_combo.blockSignals(False)
        self.listener.set_device(self._device_index(name))

    def _on_level(self, level):
        self.level.setValue(int(level * 100))
        if self.wizard is not None:
            self.wizard.on_level(level)

    def show_setup(self):
        from .onboarding import SetupWizard
        if self.wizard is not None:
            self.wizard.raise_()
            return
        self.wizard = SetupWizard(self)
        self.wizard.finished.connect(self._setup_done)
        self.wizard.show()

    def _setup_done(self, _result):
        self.wizard = None
        self.start_listener() if self.platform.mic_permission() == "granted" else None
        self._check_permissions()
        self._update_state()

    def set_login_item(self, enabled):
        try:
            self.platform.set_login_item(enabled)
        except Exception as e:
            self._show_did(ui.text("Couldn't change the login setting: {error}", error=e))

    # -- layout --------------------------------------------------------

    def _build_ui(self):
        self.setWindowTitle(APP_NAME)
        root = QWidget()
        layout = QVBoxLayout(root)
        layout.setSpacing(12)

        self.listen_btn = sized(QPushButton(), 1.6, bold=True)
        self.listen_btn.setCheckable(True)
        self.listen_btn.setMinimumHeight(90)
        self.listen_btn.clicked.connect(self.toggle_listening)
        self.listen_btn.setShortcut(QKeySequence("Ctrl+L"))
        layout.addWidget(self.listen_btn)

        self.permission_box = QFrame()
        self.permission_box.setFrameShape(QFrame.StyledPanel)
        pbox = QVBoxLayout(self.permission_box)
        self.permission_text = LiveText(ui.text("Permission needed"))
        self.permission_text.setWordWrap(True)
        pbox.addWidget(self.permission_text)
        prow = QHBoxLayout()
        self.permission_open = QPushButton()
        words.show(self.permission_open.setText, ui.text("Open settings"))
        self.permission_check = QPushButton()
        words.show(self.permission_check.setText, ui.text("I've done it, check again"))
        self.permission_check.clicked.connect(self._check_permissions)
        prow.addWidget(self.permission_open)
        prow.addWidget(self.permission_check)
        pbox.addLayout(prow)
        self.permission_box.hide()
        layout.addWidget(self.permission_box)

        # A language whose speech model isn't here yet, or that has no voice on this computer
        self.language_box = QFrame()
        self.language_box.setFrameShape(QFrame.StyledPanel)
        lbox = QVBoxLayout(self.language_box)
        self.language_text = LiveText(ui.text("Language"))
        self.language_text.setWordWrap(True)
        lbox.addWidget(self.language_text)
        self.language_download = QPushButton()   # its words are the language's, in _language_note
        self.language_download.clicked.connect(lambda: self.apply_language(download=True))
        lbox.addWidget(self.language_download)
        self.language_box.hide()
        layout.addWidget(self.language_box)

        # A screen reader reads their words, and what each one is (see LiveText)
        self.heard_label = sized(LiveText(ui.text("Last thing heard"), self._say_something()), 1.25)
        self.heard_label.setWordWrap(True)
        self.did_label = LiveText(ui.text("What happened"))
        self.did_label.setWordWrap(True)
        self.target_label = LiveText(ui.text("App receiving commands"))
        for lbl in (self.heard_label, self.did_label, self.target_label):
            lbl.setTextInteractionFlags(Qt.TextSelectableByKeyboard | Qt.TextSelectableByMouse)
            layout.addWidget(lbl)

        mic_row = QHBoxLayout()
        mic_label = label(ui.text("&Microphone"))
        self.mic_combo = QComboBox()
        words.show(self.mic_combo.setAccessibleName, ui.text("Microphone"))
        # what VoiceOver reads as its label
        words.show(self.mic_combo.setAccessibleDescription, ui.text("Microphone to listen with"))
        mic_label.setBuddy(self.mic_combo)
        mic_row.addWidget(mic_label)
        mic_row.addWidget(self.mic_combo, 1)
        refresh = QPushButton()
        words.show(refresh.setText, ui.text("Refresh"))
        words.show(refresh.setAccessibleName, ui.text("Refresh microphone list"))
        refresh.clicked.connect(self._fill_mics)
        mic_row.addWidget(refresh)
        layout.addLayout(mic_row)

        self.level = QProgressBar()
        self.level.setRange(0, 100)
        self.level.setTextVisible(False)
        self.level.setFixedHeight(22)
        words.show(self.level.setAccessibleName, ui.text("Microphone level"))
        layout.addWidget(self.level)

        self.mic_error = LiveText(ui.text("Microphone problem"))
        self.mic_error.setWordWrap(True)
        self.mic_error.hide()
        layout.addWidget(self.mic_error)

        history_label = label(ui.text("&History"))
        self.history = QListWidget()
        words.show(self.history.setAccessibleName, ui.text("History of commands"))
        history_label.setBuddy(self.history)
        layout.addWidget(history_label)
        layout.addWidget(self.history, 1)

        buttons = QHBoxLayout()
        for text, slot in ((ui.text("What can I say?"), self.show_commands),
                           (ui.text("Settings"), self.show_settings),
                           (ui.text("My commands folder"), self.open_user_packs)):
            b = QPushButton()
            words.show(b.setText, text)
            b.clicked.connect(slot)
            buttons.addWidget(b)
        layout.addLayout(buttons)

        self.setCentralWidget(root)
        self.resize(560, 620)
        self._fill_mics()
        self.mic_combo.currentIndexChanged.connect(self._mic_changed)
        self._build_tray()

    def _build_tray(self):
        self.tray = None
        if not QSystemTrayIcon.isSystemTrayAvailable():
            return
        self.tray = QSystemTrayIcon(state_icon("awake"), self)
        self.tray_menu = menu = QMenu()
        self.tray_status = QAction(self)   # its words say how it's listening, in _update_state
        self.tray_status.setEnabled(False)
        menu.addAction(self.tray_status)
        self.tray_toggle = QAction(self)   # and this one's what it does now
        self.tray_toggle.triggered.connect(self.toggle_listening)
        menu.addAction(self.tray_toggle)
        menu.addSeparator()
        for text, slot in ((ui.text("Show {app}", app=APP_NAME), self.bring_forward),
                           (ui.text("What can I say?"), self.show_commands),
                           (ui.text("Run setup again…"), self.show_setup),
                           (None, None),
                           (ui.text("Quit {app}", app=APP_NAME), self.quit_app)):
            if text is None:
                menu.addSeparator()
                continue
            action = QAction(self)
            words.show(action.setText, text)
            action.triggered.connect(slot)
            menu.addAction(action)
        self.tray.setContextMenu(menu)
        self.tray.setToolTip(APP_NAME)
        self.tray.activated.connect(
            lambda reason: self.bring_forward() if reason == QSystemTrayIcon.DoubleClick else None)
        self.tray.show()

    def quit_app(self):
        self._quitting = True
        self.shutdown()
        QApplication.quit()

    def bring_forward(self):
        self.showNormal()
        self.raise_()
        self.activateWindow()

    # -- settings ------------------------------------------------------

    def apply_settings(self):
        s = self.settings
        self.apply_look()
        self.setWindowFlag(Qt.WindowStaysOnTopHint, s.keep_on_top)
        self.show()
        self.speaker.enabled = s.speak_feedback
        self.speaker.rate = s.voice_rate
        self._setup_hotkey()

    def apply_look(self):
        """Text size, high contrast and reduced motion, for every window: the more accessible
        of this app's settings and the suite's. Runs again whenever either changes."""
        look = in_use(self.settings, self.suite.prefs)
        app = QApplication.instance()
        if not hasattr(self, "_base_point_size"):
            self._base_point_size = app.font().pointSizeF()
            self._effects = QApplication.isEffectEnabled(Qt.UI_General)
        # colours first: changing the style sheet puts back each widget's earlier font
        app.setStyleSheet(HIGH_CONTRAST if look["highContrast"] else "")
        size = self._base_point_size * look["textScale"]
        resize_text(size)
        # reduced motion: menus, lists and tooltips appear without sliding or fading in
        QApplication.setEffectEnabled(Qt.UI_General, self._effects and not look["reduceMotion"])
        for b in self.findChildren(QPushButton):
            if b is not self.listen_btn:
                b.setMinimumHeight(int(size * 2.6))
        if hasattr(self, "look"):
            # larger text than before: the open windows grow with it, so nothing gets squeezed
            for win in (self, getattr(self, "wizard", None)):
                if win is not None:
                    grow(win, look["textScale"] / self.look["textScale"])
        self.look = look
        self.hud.set_look(look["textScale"], look["highContrast"], look["reduceMotion"])
        self.suite.report_look(look)

    def _setup_hotkey(self):
        if self.hotkey_listener:
            self.hotkey_listener.stop()
            self.hotkey_listener = None
        if not self.settings.hotkey:
            return
        try:
            from pynput import keyboard
            self.hotkey_listener = keyboard.GlobalHotKeys(
                {self.settings.hotkey: lambda: QTimer.singleShot(0, self.toggle_listening)})
            self.hotkey_listener.start()
        except Exception as e:
            self._show_did(ui.text("Couldn't use that shortcut: {error}", error=e))

    def show_settings(self):
        old_model = self.settings.model
        old_vocab = self.settings.command_vocabulary
        dlg = SettingsDialog(self, self.settings, self.suite_language())
        if dlg.exec() != QDialog.Accepted:
            return
        dlg.apply()
        self.apply_settings()
        if self.settings.command_vocabulary != old_vocab:
            self.listener.use_command_vocabulary = self.settings.command_vocabulary
            self.listener.set_phrases(self._phrases())
        if dlg.chosen_language().code != self.lang.code:
            self.apply_language(download=True)   # chosen just now, so downloaded now if need be
        elif self.settings.model != old_model:
            path = ensure_model(self, self.settings.model)
            if path:
                self.listener.stop()
                self.listener._model = None
                self.listener.model_path = path
                self.listener.start()

    # -- language --------------------------------------------------------

    def suite_language(self):
        """Limitless Sound's language: what the hub sent, or the last it sent while it's not running."""
        return wanted("", self.suite.prefs.get("language"), self.settings.extra.get("suite_language", ""))

    def _suite_prefs(self):
        self.apply_look()
        self.apply_language()

    def apply_language(self, download=False):
        """Show, listen and answer in the language wanted: the one chosen in Settings, else
        Limitless Sound's. The windows change to it at once. Any but English is downloaded once:
        until it's here Voice keeps listening in the language it has, says so, and offers the
        download; download=True asks for it now."""
        code = self.suite.prefs.get("language")
        if code and code != self.settings.extra.get("suite_language"):
            # remembered, so Voice starts in it next time, before the hub is running
            self.settings.extra["suite_language"] = code
            self.settings.save()
        want = load_language(wanted(self.settings.language, self.suite_language()))
        if words.use(want.code):
            self.retranslate()
        if want.code == self.lang.code:
            if self._language_problem == "model":
                self._language_note("")
            return
        name = model_for(want, self.settings.model)
        path = find_model(name)
        if path is None and download:
            path = ensure_model(self, name, want, ask=False)   # asked for just now, in Settings or here
        if path is None:
            size = MODELS[name][1]
            self._language_note(want.text("To listen in {language}, Limitless Voice needs to download its speech "
                                          "model ({size}). Until then, it keeps listening as before.",
                                          language=want.name, size=size),
                                want.text("Download {language} ({size})", language=want.name, size=size))
            return
        self._use_language(want, path)

    def _use_language(self, lang, path):
        """Listen with this language's speech model, and answer in it."""
        self.lang = lang
        words.listen_in(lang)
        self.retranslate()   # the commands the windows suggest, now in this language
        self.engine.set_language(lang, lang.translate(self.packs))
        self.speaker.set_language(lang)
        self.suite.language = lang.code
        self.suite.report_look()   # so the hub reads Voice's replies with a voice for it
        self._language_note("")
        # a new model for the microphone; it's loaded on the listening thread
        self.listener.stop()
        self.listener._model = None
        self.listener.model_path = path
        self.listener.set_phrases(self._phrases())
        if self._listening_started:
            self.listener.start()
        self._update_state()
        self._track_focus()
        self._feedback(lang.text("Listening in {language}", language=lang.name))
        self._show_did(lang.text("Listening in {language}", language=lang.name))

    def _no_voice(self, lang):
        """The computer has no voice for the language: say where to add one (and never add it)."""
        if lang.code != self.lang.code or self._language_problem == "model":
            return
        if sys.platform == "darwin":
            where = lang.text("There's no {language} voice on this Mac, so replies are read in its own voice. "
                              "To add one: System Settings › Accessibility › Spoken Content › System voice › "
                              "Manage Voices.",
                              language=lang.english_name)
        elif sys.platform.startswith("win"):
            where = lang.text("There's no {language} voice on this computer, so replies are read in its own voice. "
                              "To add one: Settings › Time & language › Speech › Add voices.",
                              language=lang.english_name)
        else:
            where = lang.text("There's no {language} voice on this computer, so replies are read in its own voice.",
                              language=lang.english_name)
        self._language_note(where, problem="voice")

    _language_problem = None   # what the language box is saying: "model", "voice" or nothing

    def _language_note(self, text, download=None, problem=None):
        """Show or hide the language box. With download, it offers to download the language."""
        self._language_problem = (problem or ("model" if download else None)) if text else None
        self.language_box.setVisible(bool(text))
        self.language_download.setVisible(bool(download))
        if download:
            self.language_download.setText(download)
        if text and text != self.language_text.text():
            self.language_text.setText(text)
            announce(self.language_text, text)
        elif not text:
            self.language_text.setText("")

    # -- microphones -----------------------------------------------------

    def _fill_mics(self):
        self.mic_combo.blockSignals(True)
        self.mic_combo.clear()
        add_item(self.mic_combo, ui.text("System default microphone"), "")
        try:
            for d in list_input_devices():
                # a microphone's name is its own, in any language
                add_item(self.mic_combo, ui.text("{name} (default)", name=d.name) if d.is_default else d.name, d.name)
        except Exception as e:
            self.on_mic_error(ui.text("Couldn't list microphones: {error}", error=e))
        idx = self.mic_combo.findData(self.settings.mic_name)
        self.mic_combo.setCurrentIndex(max(0, idx))
        self.mic_combo.blockSignals(False)

    def _device_index(self, name):
        if not name:
            return None
        try:
            for d in list_input_devices():
                if d.name == name:
                    return d.index
        except Exception:
            pass
        return None

    def _mic_changed(self):
        name = self.mic_combo.currentData() or ""
        self.settings.mic_name = name
        self.settings.save()
        self.listener.set_device(self._device_index(name))
        self._show_did(ui.text("Using {microphone}", microphone=name or ui.text("System default microphone")))

    def on_mic_error(self, msg):
        self.mic_error.setText(msg)
        self.mic_error.setVisible(bool(msg))
        if msg:
            announce(self.mic_error, msg)

    # -- listening -------------------------------------------------------

    def _phrases(self):
        # Other apps name their actions in English, so they're only listened for in English.
        return command_phrases(self.engine.packs, self.lang) | (self.suite.phrases() if self.lang.is_english else set())

    def _suite_phrases(self):
        if self.listener:
            self.listener.set_phrases(self._phrases())

    def toggle_listening(self):
        self.engine.awake = not self.engine.awake
        if not self.engine.awake:
            self.engine.dictating = False
        self._feedback(self.lang.text("Listening" if self.engine.awake else "Asleep"))
        self._update_state()

    def _update_state(self):
        lang = self.lang   # the words to say are the ones listened for
        if self.engine.dictating:
            text = ui.text('Dictating: say "{stop}" to go back to commands', stop=lang.first("dictation_off"))
        elif self.engine.awake:
            text = ui.text('Listening: say "{sleep}" to pause', sleep=lang.first("sleep"))
        else:
            text = ui.text('Asleep: say "{wake}" or press here to start', wake=lang.first("wake"))
        if self.engine.take and self.engine.awake:
            text = ui.text('Take mode: only "{stop}" works until the take ends', stop=lang.first("take_stop"))
        self.suite.report_state()
        words.show(self.listen_btn.setText, text)
        words.show(self.listen_btn.setAccessibleName, text)
        self.listen_btn.setChecked(self.engine.awake)
        state = self.suite.listening()
        if state != getattr(self, "_shown_state", None):
            self._shown_state = state
            self.hud.set_state(state)
            self.setWindowIcon(state_icon(state))
            if self.tray:
                self.tray.setIcon(state_icon(state))
        if self.tray:
            # the words each time: what to say changes with the language listened in, too
            words.show(self.tray.setToolTip, ui.text("{app}: {state}", app=APP_NAME, state=text))
            words.show(self.tray_status.setText, text)
            words.show(self.tray_toggle.setText, ui.text("Go to sleep") if self.engine.awake else ui.text("Wake up"))

    def on_heard(self, heard, alternative):
        if self.wizard is not None:
            # during setup, speech is only a microphone test
            self.wizard.on_heard(heard, alternative)
            return
        try:
            result = self.engine.handle(heard, alternative)
        except Exception as e:
            result = None
            self._show_did(ui.text("That didn't work: {error}", error=e))
            self.speaker.say(self.lang.text("That didn't work"))
        self._update_state()
        if result is None or result.message in ("asleep", "take"):
            return
        self.suite.report(result)
        if self.engine.dictating or not result.handled:
            shown = alternative or heard   # the plain-English transcript reads better
        else:
            shown = result.heard or heard
        self.heard_label.setText(ui.text("Heard: “{text}”", text=shown.replace("[unk]", "").strip()))
        if result.message:
            first_line = result.message.splitlines()[0]
            self._show_did(("✓ " if result.handled else "? ") + first_line)
            if self.settings.show_hud and not self.isActiveWindow():
                # The transcript is shown above it, so a miss needs only these words; any other
                # refusal (a DAW command with no DAW in front, say) shows its reason.
                did = self.lang.text("Didn't catch a command") if result.kind == "missed" else first_line
                self.hud.show_message(shown.replace("[unk]", "").strip(), did, result.handled,
                                      self.settings.hud_seconds)
            self.history.insertItem(0, f"{shown}  →  {first_line}")
            while self.history.count() > 200:
                self.history.takeItem(self.history.count() - 1)
            if result.kind == "help":
                self.show_commands()

    def _feedback(self, msg):
        # with the suite's one voice on, the hub speaks so apps never talk over each other
        if not self.settings.speak_feedback or not self.suite.say(msg):
            self.speaker.say(msg)

    def _speaking(self, busy):
        # don't let the mic hear our own voice, or the suite's
        self._own_busy = busy
        if self.listener:
            self.listener.paused = self._own_busy or self._suite_busy

    def _suite_speaking(self, busy):
        self._suite_busy = busy
        self._speaking(self._own_busy)

    def _show_did(self, text):
        self.did_label.setText(text)
        # with spoken feedback on, the screen reader would say it twice
        if not self.settings.speak_feedback:
            announce(self.did_label, text)

    def _track_focus(self):
        try:
            self.engine.note_frontmost()
        except Exception:
            return
        name = self.engine.target.name if self.engine.target else None
        self.target_label.setText(ui.text("Sending commands to: {app}", app=name) if name else
                                  ui.text("Click into the app you want to control (Logic, Pro Tools…)"))

    def _say_something(self):
        return ui.text('Say something, like "{phrase}".', phrase=phrase("what can I say"))

    def retranslate(self):
        """The language Voice shows or listens in changed: every word in its windows, the menu bar
        menu and the floating display changes in place, so the keyboard focus and what a screen
        reader is on stay put."""
        words.show_again()

    # -- dialogs -------------------------------------------------------

    def show_commands(self):
        CommandsDialog(self, self.engine).exec()

    def open_user_packs(self):
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(user_packs_dir())))

    def _check_permissions(self):
        if self.platform.mic_permission() == "granted":
            self.start_listener()
        problems = self.platform.permission_problems()
        if not problems:
            if self._last_problem is not None:
                self._last_problem = None
                self.permission_box.hide()
                self._show_did(ui.text("\u2713 All set"))
            self.permission_box.hide()
            return
        title, how, link = problems[0]
        if getattr(title, "english", title) == self._last_problem:   # in whichever language it's shown
            return
        self._last_problem = getattr(title, "english", title)
        self.permission_text.setText(ui.text("<b>{title}</b><br>{how}", title=title, how=how))
        try:
            self.permission_open.clicked.disconnect()
        except (RuntimeError, TypeError):
            pass
        self.permission_open.clicked.connect(lambda: self.platform.open_settings(link))
        self.permission_box.show()
        self.speaker.say(title)
        announce(self.permission_text, f"{title}. {how}")

    def closeEvent(self, event):
        if self.tray is not None and self.settings.keep_in_menu_bar and not self._quitting:
            # keep listening from the menu bar, like other Mac menu bar apps
            event.ignore()
            self.hide()
            if not self.settings.extra.get("told_menu_bar"):
                self.settings.extra["told_menu_bar"] = True
                self.settings.save()
                self.tray.showMessage(APP_NAME, ui.text("Still listening. Open it again from the menu bar icon."))
                self.speaker.say(self.lang.text("Still listening from the menu bar"))
            return
        self.shutdown()
        super().closeEvent(event)
        QApplication.quit()

    def shutdown(self):
        self.hud.hide()
        self.suite.stop()
        self.listener.stop()
        if self.hotkey_listener:
            self.hotkey_listener.stop()


USER_PACKS_HELP = """Your own voice commands go in this folder.

Make a text file ending in .yaml (for example my-commands.yaml) like this:

name: My Commands
apps: ["Pro Tools"]        # leave out this line for commands that work everywhere
commands:
  - say: ["drum bus", "show [the] drum bus"]
    do: {keys: cmd+shift+d}
  - say: ["comp lead vocal"]
    do:
      steps:
        - {keys: "cmd+e"}
        - {wait: 0.2}
        - {keys: "opt+cmd+3"}

Write shortcuts with Mac key names (cmd, opt, ctrl, shift). On Windows, cmd
means Ctrl and opt means Alt. Restart Limitless Voice to load changes.
The built-in commands are a good place to copy from: say "what can I say".
"""


def ensure_user_packs_dir():
    folder = user_packs_dir()
    folder.mkdir(parents=True, exist_ok=True)
    help_file = folder / "How to add commands.txt"
    if not help_file.exists():
        help_file.write_text(USER_PACKS_HELP, encoding="utf-8")
    return folder


def ensure_model(parent, name="", lang=ENGLISH, ask=True):
    """Return the model folder, downloading it (with a progress window) if needed. lang is the
    language it talks in: the model's. ask=False when the person has just asked for it.
    Its buttons are named in that language too: Qt's own Yes, No and OK are English."""
    name = name or DEFAULT_MODEL
    path = find_model(name)
    if path:
        return path
    model_label, size = MODELS.get(name, (name, "?"))
    if ask:
        box = QMessageBox(QMessageBox.Question, lang.text("Download speech model"),
                          lang.text("Limitless Voice needs the {label} speech model ({size}). It's downloaded once "
                                    "and then works without internet. Download it now?",
                                    label=model_label, size=size), parent=parent)
        yes = box.addButton(lang.text("Download {language} ({size})", language=lang.name, size=size),
                            QMessageBox.AcceptRole)
        box.addButton(lang.text("Cancel"), QMessageBox.RejectRole)
        box.setDefaultButton(yes)
        box.exec()
        if box.clickedButton() is not yes:
            return None
    dlg = QProgressDialog(lang.text("Downloading speech model…"), lang.text("Cancel"), 0, 100, parent)
    dlg.setWindowModality(Qt.WindowModal)
    dlg.setMinimumDuration(0)
    state = {"done": False, "path": None, "error": None, "pct": 0}

    def work():
        try:
            state["path"] = download_model(name, lambda f: state.__setitem__("pct", int(f * 100)))
        except Exception as e:
            state["error"] = e
        state["done"] = True

    threading.Thread(target=work, daemon=True).start()
    while not state["done"]:
        dlg.setValue(state["pct"])
        QApplication.processEvents()
        if dlg.wasCanceled():
            return None
        threading.Event().wait(0.05)
    dlg.close()
    if state["error"]:
        box = QMessageBox(QMessageBox.Warning, lang.text("Download failed"),
                          lang.text("Couldn't download the model: {error}\n"
                                    "Check the internet connection and try again.", error=state["error"]),
                          parent=parent)
        box.addButton(lang.text("OK"), QMessageBox.AcceptRole)
        box.exec()
        return None
    return state["path"]


def run(argv=None):
    applog.start("Limitless Voice", __version__)
    mac_keys.prepare()   # before anything presses or listens for keys, on this, the main thread
    # Qt on macOS activates the whole app whenever any window is raised, which
    # would pull focus away from Logic or Pro Tools. Turn that off.
    os.environ.setdefault("QT_MAC_SET_RAISE_PROCESS", "0")
    QApplication.setApplicationName(APP_NAME)
    QApplication.setApplicationDisplayName(APP_NAME)
    app = QApplication(argv if argv is not None else sys.argv)
    app.setQuitOnLastWindowClosed(False)   # the menu bar icon keeps it running
    icon_path = DEFAULT_PACK_DIR.parent / "assets" / "icon.png"
    if icon_path.exists():
        app.setWindowIcon(QIcon(str(icon_path)))

    settings = Settings.load()
    # The language wanted, if its model is here; else English until the window downloads it.
    want = load_language(wanted(settings.language, None, settings.extra.get("suite_language", "")))
    model_path = find_model(model_for(want, settings.model)) or ensure_model(None, model_for(ENGLISH, settings.model))
    if not model_path:
        return 1
    platform = get_platform()
    win = MainWindow(settings, platform, model_path)
    win.setWindowTitle(f"{APP_NAME} {__version__}")
    win.show()
    if not settings.first_run_done or platform.permission_problems() or platform.mic_permission() == "ask":
        QTimer.singleShot(400, win.show_setup)
    app.aboutToQuit.connect(win.shutdown)
    return app.exec()


__all__ = ["run", "current_os"]
