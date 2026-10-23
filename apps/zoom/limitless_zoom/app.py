"""Limitless Zoom: wires keys, voice, panel, tray icon and feedback together."""

import argparse
import getpass
import logging
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from PySide6.QtCore import QCoreApplication, QLockFile, QObject, Qt, QTimer, Signal
from PySide6.QtGui import QAction, QColor, QIcon, QPainter, QPen, QPixmap
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

from . import __version__, applog, mac_keys, voice, words
from .actions import APP_ACTIONS, LABELS
from .hotkeys import GlobalKeys, KeyLogic
from .keys import format_key
from .router import Router
from .settings import Settings, config_dir, voice_app_models
from .suite import Suite
from .ui import KeyCaptureDialog, Look, Panel, Setup, Toast
from .words import t

SERVER_NAME = f"limitless-zoom-{getpass.getuser()}"
SHOW = "show"   # what opening Zoom again sends the copy already running: show the panel
log = logging.getLogger("Limitless Zoom")


class Bus(QObject):
    """Carries events from the key and voice threads onto the UI thread. Words go as objects,
    so words made with t() reach the window still able to change language (words.again)."""

    action = Signal(str)
    layer = Signal(bool)
    switch = Signal()
    status = Signal(object)
    captured = Signal(str)
    voice_ready = Signal(str, str)      # a speech model downloaded: its folder, its language
    voice_failed = Signal(str, object)  # one that couldn't be: its language, the problem
    heard = Signal(object)
    voice_status = Signal(object)
    level = Signal(float)
    call = Signal(object)   # calls from the Limitless Sound link


def app_icon():
    png = Path(__file__).resolve().parent / "resources" / "icon.png"
    return QIcon(str(png)) if png.exists() else tray_icon(color="#ffcc00")


def tray_icon(color=None):
    """A plain magnifier. On a Mac it's a template icon, so the menu bar
    draws it black or white to match light and dark mode."""
    pm = QPixmap(64, 64)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.setPen(QPen(QColor(color or "#000000"), 7, Qt.SolidLine, Qt.RoundCap))
    p.drawEllipse(9, 9, 32, 32)
    p.setPen(QPen(QColor(color or "#000000"), 10, Qt.SolidLine, Qt.RoundCap))
    p.drawLine(41, 41, 54, 54)
    p.end()
    icon = QIcon(pm)
    if color is None and sys.platform == "darwin":
        icon.setIsMask(True)
    elif color is None:
        return app_icon()
    return icon


def bundled_dirs():
    """Folders that may hold the voice model: inside the installed app, or app data."""
    dirs = []
    if getattr(sys, "frozen", False):
        dirs.append(Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent)) / "models")
    dirs.append(Path(__file__).resolve().parent.parent / "models")
    dirs.append(config_dir() / "models")
    return dirs


def model_dirs():
    """Folders that may hold a speech model: Zoom's own, then Limitless Voice's, which has the
    Spanish model once Voice has listened in Spanish."""
    return bundled_dirs() + [voice_app_models()]


class ZoomApp(QObject):
    def __init__(self, settings, backend, use_keys=True, use_voice=True, use_tray=True):
        super().__init__()
        self.settings, self.backend = settings, backend
        self.bus = Bus()
        self.router = Router(backend.os_name, settings["big_steps"], settings["key_overrides"])
        self.worker = ThreadPoolExecutor(max_workers=1)
        self.last_app = (None, None)
        self.last_action = None
        self.voice = None
        self.voice_wanted = None        # the language voice was last started for
        self._voice_note = None         # what to add to the listener's status, as words
        self._listener_said = None      # the listener's last status
        self._downloading = set()       # languages whose speech model is downloading
        self.setup_window = None
        self.capture_dialog = None
        self._perms_ok = None
        self._perms_shown = None   # what Setup shows now, so it's only redrawn when that changes
        self._status_text = None
        self.look = Look()   # the suite's shared text size, contrast and motion (set_look)
        self.ui_effects = QApplication.isEffectEnabled(Qt.UI_General)

        self.toast = Toast()
        self.badge = Toast(persistent=True, about=t("Zoom keys"))
        self.tts = None
        try:
            from PySide6.QtTextToSpeech import QTextToSpeech

            self.tts = QTextToSpeech()
        except Exception:
            pass

        self.panel = Panel(settings["dwell_ms"], settings["scan_ms"], settings["button_scale"])
        self.panel.action.connect(self.run)

        self.bus.action.connect(self.run)
        self.bus.layer.connect(self._layer_changed)
        self.bus.switch.connect(self.panel.switch_pressed)
        self.bus.status.connect(self._status)
        self.bus.voice_ready.connect(self._voice_ready)
        self.bus.voice_failed.connect(self._voice_failed)
        self.bus.heard.connect(self._heard)
        self.bus.voice_status.connect(self._voice_status)
        self.bus.level.connect(self._level)

        self.logic = KeyLogic(settings.get_layer_key(), settings["switch_key"], settings["layer_map"],
                              self.bus.action.emit, self.bus.layer.emit, self.bus.switch.emit)
        self.use_keys = use_keys
        self.keys = None
        self.panel.set_keys_state(False, self.key_text())

        # Watch permissions so keys start working the moment they're allowed.
        self.perm_timer = QTimer(self, interval=1000, timeout=self._check_permissions)

        self.poll = QTimer(self, interval=400, timeout=self._poll_front)
        self.poll.start()

        self.server = QLocalServer(self)
        QLocalServer.removeServer(SERVER_NAME)
        self.server.listen(SERVER_NAME)
        self.server.newConnection.connect(self._remote_command)

        self.tray = self._make_tray() if use_tray and QSystemTrayIcon.isSystemTrayAvailable() else None
        self.use_voice = use_voice

        self.bus.call.connect(lambda fn: fn())
        self.suite = Suite(self, dispatch=self.bus.call.emit)

    # Start-up ---------------------------------------------------------------

    def start(self):
        self.backend.keep_responsive()
        self.suite.start()
        self.start_keys()
        if self.settings["show_panel_on_start"]:
            self.show_panel()
        self._check_permissions()
        self.perm_timer.start()
        if self.settings["first_run"] or self._perms_ok is False:
            QTimer.singleShot(300, self.show_setup)
        if self.use_voice and self.settings["voice_enabled"]:
            self.start_voice()
        else:
            self._voice_status(t("off"))

    def key_text(self):
        return format_key(self.logic.layer_key, self.backend.os_name)

    def start_keys(self):
        if not self.use_keys:
            return
        if self.keys:
            self.keys.stop()
        self.keys = GlobalKeys(self.logic, self.backend.os_name)
        try:
            self.keys.start()
        except Exception as e:
            self.keys = None
            self._status(t("Zoom keys couldn't start: {problem}", problem=e))

    def _check_permissions(self):
        try:
            perms = self.backend.permissions()
        except Exception:
            return
        ok = all(p["state"] != "missing" for p in perms if p["required"])
        if ok and self._perms_ok is False:
            # Just allowed: the keyboard listener has to be made again to work.
            self.start_keys()
            self.feedback(t("Zoom keys are ready"))
        if not ok:
            missing = ", ".join(t(p["title"]) for p in perms if p["required"] and p["state"] == "missing")
            self._status(t("Needs {names}. Open Setup from the menu bar.", names=missing))
        elif self._perms_ok is False:
            self._status("")
        self._perms_ok = ok
        setup_open = self.setup_window is not None and self.setup_window.isVisible()
        if self.setup_window is not None and perms != self._perms_shown:
            # Only when something changed: restyling Setup every second redrew the whole
            # window every second for as long as a permission was missing.
            self._perms_shown = perms
            self.setup_window.set_permissions(perms)
        # Check every second while someone is setting up, otherwise now and then.
        self.perm_timer.setInterval(1000 if setup_open or not ok else 10000)

    def show_panel(self):
        self.panel.show()
        self.backend.prepare_panel(self.panel)
        screen = self.panel.screen().availableGeometry()
        self.panel.move(screen.right() - self.panel.width() - 20, screen.top() + 80)

    # Running actions ---------------------------------------------------------

    def _poll_front(self):
        try:
            app_id, handle = self.backend.frontmost()
        except Exception:
            return
        if handle is not None and not self.backend.is_self(handle):
            self.last_app = (app_id, handle)

    def run(self, action):
        if action == "again":
            if not self.last_action:
                return
            action = self.last_action
        if action in APP_ACTIONS:
            self._app_action(action)
            self.suite.did(action)
            return

        self._poll_front()
        app_id, handle = self.last_app
        plan = self.router.plan(action, app_id)
        self.feedback(plan.message)
        if not plan.ok:
            return
        self.last_action = action
        self.suite.did(action)
        # If the panel or a dialog of ours is in front, put the DAW back first.
        _, front = self.backend.frontmost()
        reactivate = handle if (front is not None and self.backend.is_self(front)) else None
        self.worker.submit(self._press, plan.combos, reactivate)

    def _press(self, combos, reactivate):
        try:
            if reactivate is not None:
                self.backend.activate(reactivate)
                time.sleep(0.15)
            for c in combos:
                self.backend.send(c)
        except Exception as e:
            self.bus.status.emit(t("Couldn't press the zoom keys: {problem}", problem=e))

    def _app_action(self, action):
        if action == "panel":
            if self.panel.isVisible():
                self.panel.hide()
            else:
                self.show_panel()
        elif action == "keys":
            self.logic.set_layer(not self.logic.layer_on)
        elif action in ("sleep", "wake"):
            if self.voice:
                self.voice.asleep = action == "sleep"
            self.feedback(t(LABELS[action]))

    def feedback(self, text):
        self.toast.show_text(text)
        if self.settings["speak"] and self.suite.say(text):
            return  # the suite's one voice said it
        if self.settings["speak"] and self.tts is not None:
            self.tts.stop()
            self.tts.say(text)

    def _layer_changed(self, on):
        if on:
            self.badge.show_text(t("ZOOM KEYS ON"), where="corner")
        else:
            self.badge.hide()
        self.panel.set_keys_state(on, self.key_text())
        if self.setup_window is not None:
            self.setup_window.set_layer_state(on)
        self.feedback(t("Zoom keys on") if on else t("Zoom keys off"))
        self.suite.keys_changed(on)
        if self.tray:
            self.keys_action.setChecked(on)

    def _status(self, text):
        if text == self._status_text:
            return
        self._status_text = text
        self.panel.status.setText(text)
        self._tray_tip()

    def _tray_tip(self):
        if self.tray:
            self.tray.setToolTip(f"Limitless Zoom\n{self._status_text}" if self._status_text else "Limitless Zoom")

    def _voice_status(self, text):
        log.info("Voice: %s", text)   # only when it changes: which microphone, or why there's none
        self.panel.voice_label.setText(t("Voice: {status}", status=text))
        if self.setup_window is not None:
            self.setup_window.set_voice_status(text)

    def _heard(self, text):
        self.panel.voice_label.setText(t("Voice: heard \u201c{text}\u201d", text=text))
        if self.setup_window is not None:
            self.setup_window.set_heard(text)

    def _level(self, value):
        if self.setup_window is not None and self.setup_window.isVisible():
            self.setup_window.set_level(value)

    def set_look(self, look):
        """The suite's text size, high contrast and reduced motion, live in every window.
        The panel's own button_scale wins when it makes the panel's text bigger."""
        self.look = look
        self.toast.set_look(look)
        self.badge.set_look(look)
        self.panel.set_look(look.combined(Look(self.settings["button_scale"])))
        for w in (self.setup_window, self.capture_dialog):
            if w is not None:
                w.set_look(look)
        # Menus, pop-up lists and tooltips appear at once instead of sliding or fading in.
        QApplication.setEffectEnabled(Qt.UI_General, self.ui_effects and not look.reduce_motion)

    def retranslate(self):
        """The suite's language changed: every word in every window and the menu changes in
        place, so the keyboard focus and what a screen reader is on stay put."""
        words.show_again()
        if self._status_text:
            self._status_text = words.again(self._status_text)
            self._tray_tip()
        self._perms_shown = None   # the permissions, named in the new language
        self._check_permissions()
        self.follow_language()     # voice commands in it too, unless another was chosen for them
        self.set_look(self.look)   # room for the new words, each window where it was

    # Voice -----------------------------------------------------------------

    def listening_language(self):
        """The language voice commands are said in: the one chosen for them (voice_language in
        the settings, or the menu), else the language Zoom's windows are in, which is the
        suite's (or the computer's until the hub says)."""
        code = words.tag(self.settings["voice_language"]) or words.language()
        return voice.LANGUAGES.get(code, voice.ENGLISH)

    def heard_language(self):
        """The language voice commands work in right now: the one being listened in, which is
        English while another language's speech model is still downloading."""
        return self.voice.language if self.voice else self.listening_language()

    def start_voice(self):
        """Listen in the language wanted. Its speech model is downloaded once, the first time;
        until it's here, Zoom listens in English and says so."""
        want = self.voice_wanted = self.listening_language()
        self._voice_note = None
        model = voice.find_model(self.settings["voice_model"], model_dirs(), want)
        if model:
            self._start_voice_with(str(model), want.code)
            return
        english = None if want is voice.ENGLISH else voice.find_model(self.settings["voice_model"], model_dirs())
        if english:
            self._voice_note = t("until the {language} voice model is downloaded ({size}, one time only), "
                                 "say the commands in English", language=t(want.english_name), size=want.size)
            self._start_voice_with(str(english), voice.ENGLISH.code)
        else:
            self.stop_voice()
            self._voice_status(t("downloading the voice model (about 40 MB), one time only…") if want is voice.ENGLISH
                               else t("downloading the {language} voice model (about {size}), one time only…",
                                      language=t(want.english_name), size=want.size))
        self._download(want)

    def _download(self, lang):
        if lang.code in self._downloading:
            return
        self._downloading.add(lang.code)

        def fetch():
            try:
                path = voice.download_model(config_dir() / "models", language=lang)
            except Exception as e:
                done = (self.bus.voice_failed, (lang.code, e))
            else:
                done = (self.bus.voice_ready, (str(path), lang.code))
            try:
                done[0].emit(*done[1])
            except RuntimeError:   # Zoom quit while it downloaded
                pass

        threading.Thread(target=fetch, daemon=True).start()

    def _voice_ready(self, path, code):
        """A speech model finished downloading: listen with it if it's still the one wanted."""
        self._downloading.discard(code)
        if not (self.use_voice and self.settings["voice_enabled"]) or self.listening_language().code != code:
            return   # kept for when it's wanted
        waited = self.voice is not None   # it listened in English meanwhile
        self._voice_note = None
        self._start_voice_with(path, code)
        if waited:
            self.feedback(t("Voice commands in {language}", language=t(voice.LANGUAGES[code].english_name)))

    def _voice_failed(self, code, problem):
        self._downloading.discard(code)
        lang = voice.LANGUAGES[code]
        if not (self.use_voice and self.settings["voice_enabled"]) or self.listening_language() is not lang:
            return
        if self.voice is not None:   # still listening in English: say why, and that it is
            self._voice_note = t("the {language} voice model couldn't be downloaded ({problem}), so say the "
                                 "commands in English", language=t(lang.english_name), problem=problem)
            if self._listener_said is not None:
                self._voice_status(self._noted(self._listener_said))
        elif lang is voice.ENGLISH:
            self._voice_status(t("couldn't download the voice model: {problem}", problem=problem))
        else:
            self._voice_status(t("couldn't download the {language} voice model: {problem}",
                                 language=t(lang.english_name), problem=problem))

    def _noted(self, status):
        """The listener's status, with what Zoom has to add to it (still downloading a language)."""
        return t("{status}; {note}", status=status, note=self._voice_note) if self._voice_note else status

    def _listener_status(self, text):
        """The listener's status (said on its own thread), with the note added."""
        self._listener_said = text
        self.bus.voice_status.emit(self._noted(text))

    def _start_voice_with(self, model_path, code=voice.ENGLISH.code):
        self.stop_voice()
        self.voice = voice.VoiceListener(model_path, self.bus.action.emit, self._listener_status,
                                         self.settings["voice_device"],
                                         self.settings["voice_confidence"],
                                         on_heard=self.bus.heard.emit, on_level=self.bus.level.emit,
                                         language=voice.LANGUAGES[code])
        self.voice.start()
        self._show_phrases()

    def stop_voice(self):
        if self.voice:
            self.voice.stop()
            self.voice = None
        self._listener_said = None

    def follow_language(self):
        """The suite's language changed, or the one chosen for voice: listen in it, and show
        what can be said in it."""
        if self.use_voice and self.settings["voice_enabled"] and self.listening_language() is not self.voice_wanted:
            self.start_voice()
        self._show_phrases()

    def set_voice_language(self, code):
        """Voice commands in this language ("en", "es"), or None for the windows' language."""
        self.settings["voice_language"] = code
        self.settings.save()
        self.follow_language()

    def _show_phrases(self):
        """What can be said, in the language voice works in now, in Setup."""
        if self.setup_window is not None:
            self.setup_window.set_phrases(self.heard_language())

    def set_voice(self, on):
        self.settings["voice_enabled"] = on
        self.settings.save()
        if on:
            self.start_voice()
        else:
            self.stop_voice()
            self._voice_status(t("off"))

    def set_mic(self, name):
        self.settings["voice_device"] = name
        self.settings.save()
        if self.settings["voice_enabled"]:
            self.start_voice()

    # Choosing keys --------------------------------------------------------------

    def capture_key(self, title, prompt):
        dlg = self.capture_dialog = KeyCaptureDialog(title, prompt, lambda cb: None, look=self.look)
        self.bus.captured.connect(dlg.got_key)
        self.logic.capture_next(self.bus.captured.emit)
        dlg.exec()
        self.capture_dialog = None
        self.logic.capture = None
        self.bus.captured.disconnect(dlg.got_key)
        return dlg.key

    def choose_layer_key(self):
        key = self.capture_key(t("Zoom keys on/off"), t("Press the key you want to turn the zoom keys on and off."))
        if key:
            self.settings["layer_key"] = self.logic.layer_key = key
            self.settings.save()
            self.panel.set_keys_state(self.logic.layer_on, self.key_text())
            if self.setup_window is not None:
                self.setup_window.set_key_text(self.key_text())
                self.setup_window.set_layer_state(self.logic.layer_on)
            self.feedback(t("Zoom key is {key}", key=self.key_text()))
        return key

    def choose_switch_key(self):
        key = self.capture_key(t("Switch"), t("Press your switch now."))
        if key:
            self.settings["switch_key"] = self.logic.switch_key = key
            self.settings.save()
            text = format_key(key, self.backend.os_name)
            if self.setup_window is not None:
                self.setup_window.set_switch_text(text)
            self.feedback(t("Switch is {key}", key=text))
        return key

    def show_setup(self):
        if self.setup_window is not None:
            self.setup_window.show()
            self.setup_window.raise_()
            self.backend.bring_to_front()
            return
        try:
            mics = voice.list_microphones()
        except Exception:
            mics = []
        login = self.backend.open_at_login() if self.backend.can_open_at_login() else None
        w = Setup(self.key_text(), format_key(self.settings["switch_key"], self.backend.os_name),
                  mics, self.settings["voice_device"], login, look=self.look)
        w.request_permission.connect(self.backend.request_permission)
        w.choose_layer.connect(self.choose_layer_key)
        w.choose_switch.connect(self.choose_switch_key)
        w.mic_changed.connect(self.set_mic)
        w.login_changed.connect(self.set_open_at_login)
        w.finished.connect(self._setup_done)
        w.set_layer_state(self.logic.layer_on)
        if self.voice is None:
            w.set_voice_status(t("off") if not self.settings["voice_enabled"] else t("starting…"))
        self.setup_window = w
        self._show_phrases()
        self._perms_shown = None
        self._check_permissions()
        screen = w.screen().availableGeometry()
        w.resize(min(w.width(), screen.width() - 40), min(w.height(), screen.height() - 40))
        w.move(screen.center() - w.rect().center())
        w.show()
        w.raise_()
        self.backend.bring_to_front()

    def _setup_done(self):
        self.settings["first_run"] = False
        self.settings.save()
        self.feedback(t("Ready. Say {phrase}, or tap {key}", phrase=self.heard_language().first("in"),
                        key=self.key_text()))

    def set_open_at_login(self, on):
        try:
            self.backend.set_open_at_login(on)
        except Exception as e:
            self._status(t("Couldn't change Open at login: {problem}", problem=e))
        if self.tray and hasattr(self, "login_action"):
            self.login_action.setChecked(self.backend.open_at_login())

    # Tray menu and remote commands ---------------------------------------------

    def _make_tray(self):
        tray = QSystemTrayIcon(tray_icon(), self)
        menu = QMenu()

        def item(text, *run, checkable=False):
            # A menu item whose words follow the suite's language.
            a = menu.addAction("", *run) if run else QAction(menu, checkable=checkable)
            words.show(a.setText, text)
            return a

        item(t("Show or hide zoom panel"), lambda: self.run("panel"))
        self.keys_action = item(t("Zoom keys on"), checkable=True)
        self.keys_action.triggered.connect(lambda on: self.logic.set_layer(on))
        menu.addAction(self.keys_action)
        voice_action = item(t("Listen for voice commands"), checkable=True)
        voice_action.setChecked(self.settings["voice_enabled"])
        voice_action.triggered.connect(self.set_voice)
        menu.addAction(voice_action)
        lang_menu = self.language_menu = menu.addMenu("")
        words.show(lang_menu.setTitle, t("Voice command language"))
        lang_menu.aboutToShow.connect(lambda: self._fill_languages(lang_menu))
        speak_action = item(t("Speak each action"), checkable=True)
        speak_action.setChecked(self.settings["speak"])
        speak_action.triggered.connect(lambda on: (self.settings.__setitem__("speak", on), self.settings.save()))
        menu.addAction(speak_action)
        menu.addSeparator()
        item(t("Choose zoom keys on/off key…"), self.choose_layer_key)
        item(t("Choose switch key…"), self.choose_switch_key)
        mic_menu = menu.addMenu("")
        words.show(mic_menu.setTitle, t("Microphone"))
        mic_menu.aboutToShow.connect(lambda: self._fill_mics(mic_menu))
        if self.backend.can_open_at_login():
            self.login_action = item(t("Open at login"), checkable=True)
            self.login_action.setChecked(self.backend.open_at_login())
            self.login_action.triggered.connect(self.set_open_at_login)
            menu.addAction(self.login_action)
        item(t("Setup and help…"), self.show_setup)
        menu.addSeparator()
        item(t("Quit Limitless Zoom"), QApplication.quit)
        tray.setContextMenu(menu)
        tray.setToolTip("Limitless Zoom")
        tray.show()
        self._menu = menu
        return tray

    def _fill_mics(self, menu):
        menu.clear()
        try:
            mics = voice.list_microphones()
        except Exception:
            mics = []
        for name in [None] + mics:
            a = QAction(name or t("System default"), menu, checkable=True)
            a.setChecked(name == self.settings["voice_device"])
            a.triggered.connect(lambda _=False, n=name: self.set_mic(n))
            menu.addAction(a)

    def _fill_languages(self, menu):
        """Voice commands in the windows' language, or in one chosen for them. Each language by
        its name in itself, so someone who reads only that language finds it."""
        menu.clear()
        same = t("Same as Limitless Sound ({language})",
                 language=t(voice.LANGUAGES.get(words.language(), voice.ENGLISH).english_name))
        for code, name in [(None, same)] + [(c, lang.name) for c, lang in voice.LANGUAGES.items()]:
            a = QAction(name, menu, checkable=True)
            a.setChecked(code == (words.tag(self.settings["voice_language"]) or None))
            a.triggered.connect(lambda _=False, c=code: self.set_voice_language(c))
            menu.addAction(a)

    def _remote_command(self):
        sock = self.server.nextPendingConnection()

        def read():
            # Read whatever is already waiting as well as anything that arrives
            # later, then answer so the sender knows it can hang up. (On Windows,
            # unread data is lost if the sender closes the pipe first.)
            words = bytes(sock.readAll()).decode("utf-8", "ignore").split()
            for word in words:
                if word == SHOW:
                    self.show_panel()
                elif word in LABELS:
                    self.run(word)
            if words:
                sock.write(b"ok\n")
                sock.flush()

        sock.readyRead.connect(read)
        sock.disconnected.connect(sock.deleteLater)
        read()


def send_remote(action, timeout_ms=1000):
    """Send an action to a running copy. Returns True if one was running."""
    sock = QLocalSocket()
    sock.connectToServer(SERVER_NAME)
    if not sock.waitForConnected(timeout_ms):
        return False
    sock.write((action + "\n").encode())
    sock.flush()
    sock.waitForBytesWritten(timeout_ms)
    sock.waitForReadyRead(timeout_ms)  # the app's "ok"
    sock.disconnectFromServer()
    if sock.state() != QLocalSocket.UnconnectedState:
        sock.waitForDisconnected(timeout_ms)
    return True


def single_instance(folder=None, take_over=False):
    """A lock that only one running Limitless Zoom holds, or None while another copy has it.
    Two copies opened at the same moment (at login, say) could otherwise both find nobody
    listening yet, and both run: twice the CPU, and every zoom key pressed twice.
    take_over: the copy holding it never answered, so it's gone; take the lock anyway."""
    folder = Path(folder or config_dir())
    try:
        folder.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass
    lock = QLockFile(str(folder / "running.lock"))
    lock.setStaleLockTime(0)   # a copy that crashed leaves a lock; it's stale once that process is gone
    if take_over:
        lock.removeStaleLockFile()
    if lock.tryLock(0) or lock.error() != QLockFile.LockError.LockFailedError:
        return lock   # ours, or no lock can be made there at all: run as before
    return None


def _try(fn):
    try:
        return bool(fn())
    except Exception as e:
        print("selftest error:", e)
        return False


def _key_sender(os_name):
    from .platforms import KeySender

    return KeySender(os_name) is not None


def _load_model(settings):
    import vosk

    path = voice.find_model(settings["voice_model"], bundled_dirs())
    if path is None:
        raise RuntimeError("voice model not bundled")
    vosk.SetLogLevel(-1)
    return vosk.Model(str(path)) is not None


def main(argv=None):
    applog.start("Limitless Zoom", __version__)
    parser = argparse.ArgumentParser(prog="limitless-zoom", description="Accessible zoom control")
    parser.add_argument("--do", metavar="ACTION", help="send an action to the running app, e.g. in, out, fit")
    parser.add_argument("--no-voice", action="store_true", help="don't listen for voice commands")
    parser.add_argument("--no-keys", action="store_true", help="don't use system-wide keys")
    parser.add_argument("--selftest", action="store_true", help="start everything, then quit (for builds)")
    args = parser.parse_args(argv)

    if args.do:
        # The Limitless Sound hub runs this when Zoom is closed, e.g. for its link "one-hand
        # mode on: zoom keys off". It only passes the action on, so it needs no windows.
        core = QCoreApplication(sys.argv[:1])   # the socket needs one, alive while it's used
        core.setApplicationName("Limitless Zoom")
        sent = send_remote(args.do)
        log.info("--do %s: %s", args.do, "passed to the Limitless Zoom that's running" if sent
                 else "Limitless Zoom isn't running, so nothing was done")
        return 0 if sent else 1

    mac_keys.prepare()   # before anything presses or listens for keys, on this, the main thread
    QApplication.setAttribute(Qt.AA_ShareOpenGLContexts)
    qapp = QApplication(sys.argv[:1])
    qapp.setApplicationName("Limitless Zoom")
    qapp.setQuitOnLastWindowClosed(False)
    qapp.setWindowIcon(app_icon())

    lock = None
    if not args.selftest:
        if send_remote(SHOW):
            log.info("Already running: showed its panel")
            return 0
        lock = single_instance()
        if lock is None:
            # Another copy is opening right now: show its panel once it's ready, and leave it be.
            for _ in range(60):
                if send_remote(SHOW, 250):
                    log.info("Another copy was opening at the same moment; left it running")
                    return 0
                time.sleep(0.25)
            # Nobody answered for half a minute, so the copy that left the lock is gone. Qt can't
            # tell when it was left under another computer name (a Mac's name can change with its
            # network): take the lock over rather than never open again.
            log.info("The last copy left its lock behind; taking it over")
            lock = single_instance(take_over=True)

    from .platforms import get_backend

    settings = Settings()
    if args.selftest:
        settings["first_run"] = False
    app = ZoomApp(settings, get_backend(), use_keys=not (args.no_keys or args.selftest),
                  use_voice=not (args.no_voice or args.selftest))
    app.start()
    if args.selftest:
        def check():
            results = {"routing": app.router.plan("in", "com.apple.logic10").ok,
                       "panel": app.panel.isVisible(),
                       "icon": not app_icon().isNull(),
                       "key sender": _try(lambda: _key_sender(app.backend.os_name))}
            if not args.no_voice:
                # Load the bundled speech model without opening a microphone.
                results["voice model"] = _try(lambda: _load_model(app.settings))
            for name, ok in results.items():
                print(f"selftest {name}: {'ok' if ok else 'FAILED'}")
            ok = all(results.values())
            print("selftest", "ok" if ok else "FAILED")
            qapp.exit(0 if ok else 1)
        QTimer.singleShot(1500, check)
    return qapp.exec()


if __name__ == "__main__":
    sys.exit(main())
