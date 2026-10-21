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
from PySide6.QtWidgets import QApplication, QMenu, QMessageBox, QSystemTrayIcon

from . import voice
from .actions import APP_ACTIONS, LABELS
from .hotkeys import GlobalKeys, KeyLogic
from .keys import format_key
from .router import Router
from .settings import Settings, config_dir
from .ui import KeyCaptureDialog, Panel, Toast, Welcome

SERVER_NAME = f"limitless-zoom-{getpass.getuser()}"


class Bus(QObject):
    """Carries events from the key and voice threads onto the UI thread."""

    action = Signal(str)
    layer = Signal(bool)
    switch = Signal()
    status = Signal(str)
    captured = Signal(str)
    voice_ready = Signal(str)


def app_icon():
    pm = QPixmap(64, 64)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.setPen(QPen(QColor("#ffcc00"), 8))
    p.drawEllipse(8, 8, 34, 34)
    p.drawLine(38, 38, 56, 56)
    p.end()
    return QIcon(pm)


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

        self.logic = KeyLogic(settings["layer_key"], settings["switch_key"], settings["layer_map"],
                              self.bus.action.emit, self.bus.layer.emit, self.bus.switch.emit)
        self.keys = GlobalKeys(self.logic, backend.os_name) if use_keys else None

        self.poll = QTimer(self, interval=400, timeout=self._poll_front)
        self.poll.start()

        self.server = QLocalServer(self)
        QLocalServer.removeServer(SERVER_NAME)
        self.server.listen(SERVER_NAME)
        self.server.newConnection.connect(self._remote_command)

        self.tray = self._make_tray() if use_tray and QSystemTrayIcon.isSystemTrayAvailable() else None
        self.use_voice = use_voice

    # Start-up ---------------------------------------------------------------

    def start(self):
        for problem in self.backend.permission_problems():
            self._status(problem)
        if self.keys:
            try:
                self.keys.start()
            except Exception as e:
                self._status(f"Zoom keys couldn't start: {e}")
        if self.settings["show_panel_on_start"]:
            self.show_panel()
        if self.settings["first_run"]:
            QTimer.singleShot(300, self.welcome)
        if self.use_voice and self.settings["voice_enabled"]:
            self.start_voice()

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
            return

        self._poll_front()
        app_id, handle = self.last_app
        plan = self.router.plan(action, app_id)
        self.feedback(plan.message)
        if not plan.ok:
            return
        self.last_action = action
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
        if self.settings["speak"] and self.tts is not None:
            self.tts.stop()
            self.tts.say(text)

    def _layer_changed(self, on):
        if on:
            self.badge.show_text("ZOOM KEYS ON", where="corner")
        else:
            self.badge.hide()
        self.feedback("Zoom keys on" if on else "Zoom keys off")
        if self.tray:
            self.keys_action.setChecked(on)

    def _status(self, text):
        self.panel.status.setText(text)
        if self.tray:
            self.tray.setToolTip(f"Limitless Zoom\n{text}")

    # Voice -----------------------------------------------------------------

    def start_voice(self):
        model = voice.find_model(self.settings["voice_model"], bundled_dirs())
        if model:
            self._start_voice_with(str(model))
            return
        self._status("Downloading the voice model (about 40 MB), one time only…")

        def fetch():
            try:
                path = voice.download_model(config_dir() / "models")
                self.bus.voice_ready.emit(str(path))
            except Exception as e:
                self.bus.status.emit(f"Couldn't download the voice model: {e}")

        threading.Thread(target=fetch, daemon=True).start()

    def _start_voice_with(self, model_path):
        self.stop_voice()
        self.voice = voice.VoiceListener(model_path, self.bus.action.emit, self.bus.status.emit,
                                         self.settings["voice_device"],
                                         self.settings["voice_confidence"])
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
            self._status("Voice is off")

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
            self.feedback(f"Zoom key is {format_key(key)}")
        return key

    def choose_switch_key(self):
        key = self.capture_key("Switch", "Press your switch now.")
        if key:
            self.settings["switch_key"] = self.logic.switch_key = key
            self.settings.save()
            self.feedback(f"Switch is {format_key(key)}")
        return key

    def welcome(self):
        try:
            mics = voice.list_microphones()
        except Exception:
            mics = []
        w = Welcome(format_key(self.settings["layer_key"]), format_key(self.settings["switch_key"]),
                    mics, self.settings["voice_device"])

        def layer():
            k = self.choose_layer_key()
            if k:
                w.layer_btn.setText(f"Zoom keys on/off: {format_key(k)}  (change)")

        def switch():
            k = self.choose_switch_key()
            if k:
                w.switch_btn.setText(f"Switch key: {format_key(k)}  (change)")

        w.choose_layer.connect(layer)
        w.choose_switch.connect(switch)
        w.exec()
        mic = w.mic.currentData()
        self.settings["first_run"] = False
        self.settings.save()
        if mic != self.settings["voice_device"]:
            self.set_mic(mic)

    # Tray menu and remote commands ---------------------------------------------

    def _make_tray(self):
        tray = QSystemTrayIcon(app_icon(), self)
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
        menu.addAction("Welcome and help…", self.welcome)
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
            # The sender may have written and gone before we get here, so read
            # whatever is already waiting as well as anything that arrives later.
            for line in bytes(sock.readAll()).decode("utf-8", "ignore").split():
                if line in LABELS:
                    self.run(line)

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
    sock.disconnectFromServer()
    if sock.state() != QLocalSocket.UnconnectedState:
        sock.waitForDisconnected(timeout_ms)
    return True


def main(argv=None):
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
                  use_voice=not args.no_voice)
    app.start()
    if args.selftest:
        def check():
            ok = app.router.plan("in", None).ok and app.panel.isVisible()
            print("selftest", "ok" if ok else "FAILED")
            qapp.exit(0 if ok else 1)
        QTimer.singleShot(1500, check)
    return qapp.exec()


if __name__ == "__main__":
    sys.exit(main())
