"""Limitless Zoom: wires keys, voice, panel, tray icon and feedback together."""

import argparse
import getpass
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from PySide6.QtCore import QObject, Qt, QTimer, Signal
from PySide6.QtGui import QAction, QColor, QIcon, QPainter, QPen, QPixmap
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

from . import __version__, applog, mac_keys, voice
from .actions import APP_ACTIONS, LABELS
from .hotkeys import GlobalKeys, KeyLogic
from .keys import format_key
from .router import Router
from .settings import Settings, config_dir
from .suite import Suite
from .ui import KeyCaptureDialog, Panel, Setup, Toast

SERVER_NAME = f"limitless-zoom-{getpass.getuser()}"


class Bus(QObject):
    """Carries events from the key and voice threads onto the UI thread."""

    action = Signal(str)
    layer = Signal(bool)
    switch = Signal()
    status = Signal(str)
    captured = Signal(str)
    voice_ready = Signal(str)
    heard = Signal(str)
    voice_status = Signal(str)
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
        self.setup_window = None
        self._perms_ok = None

        self.toast = Toast()
        self.badge = Toast(persistent=True)
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
        self.bus.voice_ready.connect(self._start_voice_with)
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
            self.panel.voice_label.setText("Voice: off")

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
            self._status(f"Zoom keys couldn't start: {e}")

    def _check_permissions(self):
        try:
            perms = self.backend.permissions()
        except Exception:
            return
        ok = all(p["state"] != "missing" for p in perms if p["required"])
        if ok and self._perms_ok is False:
            # Just allowed: the keyboard listener has to be made again to work.
            self.start_keys()
            self.feedback("Zoom keys are ready")
        if not ok:
            missing = ", ".join(p["title"] for p in perms if p["required"] and p["state"] == "missing")
            self._status(f"Needs {missing}. Open Setup from the menu bar.")
        elif self._perms_ok is False:
            self._status("")
        self._perms_ok = ok
        setup_open = self.setup_window is not None and self.setup_window.isVisible()
        if self.setup_window is not None:
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
            self.bus.status.emit(f"Couldn't press the zoom keys: {e}")

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
            self.feedback(LABELS[action])

    def feedback(self, text):
        self.toast.show_text(text)
        if self.settings["speak"] and self.suite.say(text):
            return  # the suite's one voice said it
        if self.settings["speak"] and self.tts is not None:
            self.tts.stop()
            self.tts.say(text)

    def _layer_changed(self, on):
        if on:
            self.badge.show_text("ZOOM KEYS ON", where="corner")
        else:
            self.badge.hide()
        self.panel.set_keys_state(on, self.key_text())
        if self.setup_window is not None:
            self.setup_window.set_layer_state(on)
        self.feedback("Zoom keys on" if on else "Zoom keys off")
        self.suite.keys_changed(on)
        if self.tray:
            self.keys_action.setChecked(on)

    def _status(self, text):
        self.panel.status.setText(text)
        if self.tray:
            self.tray.setToolTip(f"Limitless Zoom\n{text}" if text else "Limitless Zoom")

    def _voice_status(self, text):
        self.panel.voice_label.setText(f"Voice: {text}")
        if self.setup_window is not None:
            self.setup_window.set_voice_status(text)

    def _heard(self, text):
        self.panel.voice_label.setText(f"Voice: heard \u201c{text}\u201d")
        if self.setup_window is not None:
            self.setup_window.set_heard(text)

    def _level(self, value):
        if self.setup_window is not None and self.setup_window.isVisible():
            self.setup_window.set_level(value)

    # Voice -----------------------------------------------------------------

    def start_voice(self):
        model = voice.find_model(self.settings["voice_model"], bundled_dirs())
        if model:
            self._start_voice_with(str(model))
            return
        self._voice_status("downloading the voice model (about 40 MB), one time only…")

        def fetch():
            try:
                path = voice.download_model(config_dir() / "models")
                self.bus.voice_ready.emit(str(path))
            except Exception as e:
                self.bus.voice_status.emit(f"couldn't download the voice model: {e}")

        threading.Thread(target=fetch, daemon=True).start()

    def _start_voice_with(self, model_path):
        self.stop_voice()
        self.voice = voice.VoiceListener(model_path, self.bus.action.emit, self.bus.voice_status.emit,
                                         self.settings["voice_device"],
                                         self.settings["voice_confidence"],
                                         on_heard=self.bus.heard.emit, on_level=self.bus.level.emit)
        self.voice.start()

    def stop_voice(self):
        if self.voice:
            self.voice.stop()
            self.voice = None

    def set_voice(self, on):
        self.settings["voice_enabled"] = on
        self.settings.save()
        if on:
            self.start_voice()
        else:
            self.stop_voice()
            self._voice_status("off")

    def set_mic(self, name):
        self.settings["voice_device"] = name
        self.settings.save()
        if self.settings["voice_enabled"]:
            self.start_voice()

    # Choosing keys --------------------------------------------------------------

    def capture_key(self, title, prompt):
        dlg = KeyCaptureDialog(title, prompt, lambda cb: None)
        self.bus.captured.connect(dlg.got_key)
        self.logic.capture_next(self.bus.captured.emit)
        dlg.exec()
        self.logic.capture = None
        self.bus.captured.disconnect(dlg.got_key)
        return dlg.key

    def choose_layer_key(self):
        key = self.capture_key("Zoom keys on/off", "Press the key you want to turn the zoom keys on and off.")
        if key:
            self.settings["layer_key"] = self.logic.layer_key = key
            self.settings.save()
            self.panel.set_keys_state(self.logic.layer_on, self.key_text())
            if self.setup_window is not None:
                self.setup_window.set_key_text(self.key_text())
                self.setup_window.set_layer_state(self.logic.layer_on)
            self.feedback(f"Zoom key is {self.key_text()}")
        return key

    def choose_switch_key(self):
        key = self.capture_key("Switch", "Press your switch now.")
        if key:
            self.settings["switch_key"] = self.logic.switch_key = key
            self.settings.save()
            text = format_key(key, self.backend.os_name)
            if self.setup_window is not None:
                self.setup_window.set_switch_text(text)
            self.feedback(f"Switch is {text}")
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
                  mics, self.settings["voice_device"], login)
        w.request_permission.connect(self.backend.request_permission)
        w.choose_layer.connect(self.choose_layer_key)
        w.choose_switch.connect(self.choose_switch_key)
        w.mic_changed.connect(self.set_mic)
        w.login_changed.connect(self.set_open_at_login)
        w.finished.connect(self._setup_done)
        w.set_layer_state(self.logic.layer_on)
        if self.voice is None:
            w.set_voice_status("off" if not self.settings["voice_enabled"] else "starting…")
        self.setup_window = w
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
        self.feedback(f"Ready. Say zoom in, or tap {self.key_text()}")

    def set_open_at_login(self, on):
        try:
            self.backend.set_open_at_login(on)
        except Exception as e:
            self._status(f"Couldn't change Open at login: {e}")
        if self.tray and hasattr(self, "login_action"):
            self.login_action.setChecked(self.backend.open_at_login())

    # Tray menu and remote commands ---------------------------------------------

    def _make_tray(self):
        tray = QSystemTrayIcon(tray_icon(), self)
        menu = QMenu()
        menu.addAction("Show or hide zoom panel", lambda: self.run("panel"))
        self.keys_action = QAction("Zoom keys on", menu, checkable=True)
        self.keys_action.triggered.connect(lambda on: self.logic.set_layer(on))
        menu.addAction(self.keys_action)
        voice_action = QAction("Listen for voice commands", menu, checkable=True)
        voice_action.setChecked(self.settings["voice_enabled"])
        voice_action.triggered.connect(self.set_voice)
        menu.addAction(voice_action)
        speak_action = QAction("Speak each action", menu, checkable=True)
        speak_action.setChecked(self.settings["speak"])
        speak_action.triggered.connect(lambda on: (self.settings.__setitem__("speak", on), self.settings.save()))
        menu.addAction(speak_action)
        menu.addSeparator()
        menu.addAction("Choose zoom keys on/off key…", self.choose_layer_key)
        menu.addAction("Choose switch key…", self.choose_switch_key)
        mic_menu = menu.addMenu("Microphone")
        mic_menu.aboutToShow.connect(lambda: self._fill_mics(mic_menu))
        if self.backend.can_open_at_login():
            self.login_action = QAction("Open at login", menu, checkable=True)
            self.login_action.setChecked(self.backend.open_at_login())
            self.login_action.triggered.connect(self.set_open_at_login)
            menu.addAction(self.login_action)
        menu.addAction("Setup and help…", self.show_setup)
        menu.addSeparator()
        menu.addAction("Quit Limitless Zoom", QApplication.quit)
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
            a = QAction(name or "System default", menu, checkable=True)
            a.setChecked(name == self.settings["voice_device"])
            a.triggered.connect(lambda _=False, n=name: self.set_mic(n))
            menu.addAction(a)

    def _remote_command(self):
        sock = self.server.nextPendingConnection()

        def read():
            # Read whatever is already waiting as well as anything that arrives
            # later, then answer so the sender knows it can hang up. (On Windows,
            # unread data is lost if the sender closes the pipe first.)
            words = bytes(sock.readAll()).decode("utf-8", "ignore").split()
            for word in words:
                if word in LABELS:
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
    mac_keys.prepare()   # before anything presses or listens for keys, on this, the main thread
    parser = argparse.ArgumentParser(prog="limitless-zoom", description="Accessible zoom control")
    parser.add_argument("--do", metavar="ACTION", help="send an action to the running app, e.g. in, out, fit")
    parser.add_argument("--no-voice", action="store_true", help="don't listen for voice commands")
    parser.add_argument("--no-keys", action="store_true", help="don't use system-wide keys")
    parser.add_argument("--selftest", action="store_true", help="start everything, then quit (for builds)")
    args = parser.parse_args(argv)

    QApplication.setAttribute(Qt.AA_ShareOpenGLContexts)
    qapp = QApplication(sys.argv[:1])
    qapp.setApplicationName("Limitless Zoom")
    qapp.setQuitOnLastWindowClosed(False)
    qapp.setWindowIcon(app_icon())

    if args.do:
        return 0 if send_remote(args.do) else 1
    if not args.selftest and send_remote("panel"):
        return 0  # already running: just show its panel

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
