"""Limitless Keys: wires the shortcut engine, plugin undo, windows and menu bar icon together."""

import argparse
import getpass
import sys
import threading
from pathlib import Path

from PySide6.QtCore import QObject, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QAction, QColor, QFont, QIcon, QPainter, QPen, QPixmap
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

from . import __version__
from .daws import DAWS, find_daw, scope_name
from .engine import KeyEngine
from .keys import format_combo, parse_combo, speak_combo
from .limitless_link import config_dir as suite_dir
from .logic_windows import LogicWindows
from .plugin_undo import PluginUndo
from .profiles import Profiles
from .runner import Context, Runner
from .settings import Settings, config_dir
from .suite import Suite
from .ui import AddAppDialog, CheatSheet, HistoryWindow, Setup, ShortcutsWindow, Toast
from .undo_link import LinkServer

SERVER_NAME = f"limitless-keys-{getpass.getuser()}"
REMOTE = {"pluginUndo", "pluginRedo", "pluginBefore", "pluginAfter", "undoFront", "pluginHistory",
          "cheatSheet", "pause", "resume", "settings", "setup", "history"}


class Bus(QObject):
    """Carries calls from the keyboard, link and worker threads onto the UI thread."""

    call = Signal(object)
    captured = Signal(object)


def tray_icon():
    """A key cap with an undo arrow. On a Mac it's a template icon, so the menu bar
    draws it black or white to match light and dark mode."""
    pm = QPixmap(64, 64)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.setPen(QPen(QColor("#000"), 6))
    p.drawRoundedRect(QRectF(6, 6, 52, 52), 12, 12)
    f = QFont()
    f.setPixelSize(34)
    f.setBold(True)
    p.setFont(f)
    p.drawText(QRectF(6, 4, 52, 52), Qt.AlignCenter, "↶")
    p.end()
    icon = QIcon(pm)
    if sys.platform == "darwin":
        icon.setIsMask(True)
    return icon


def app_icon():
    png = Path(__file__).resolve().parent / "resources" / "icon.png"
    return QIcon(str(png)) if png.exists() else tray_icon()


class KeysApp(QObject):
    def __init__(self, settings, profiles, backend, use_keys=True, use_tray=True, link_path=None):
        super().__init__()
        self.settings, self.profiles, self.backend = settings, profiles, backend
        self.bus = Bus()
        self.bus.call.connect(lambda fn: fn())
        self.toast = Toast()
        self.cheat = CheatSheet()
        self.tts = None
        try:
            from PySide6.QtTextToSpeech import QTextToSpeech

            self.tts = QTextToSpeech()
        except Exception:
            pass

        self.front = (None, None)
        self.plugins = PluginUndo()
        self.link = LinkServer(link_path or suite_dir() / "undo-link.json", self.plugins.link_message,
                               self.plugins.link_closed, __version__)
        self.engine = KeyEngine(profiles, self._shortcut)
        self.engine.enabled = settings["enabled"]
        self.suite = Suite(self, dispatch=self.bus.call.emit)
        self.runner = Runner(backend, self.plugins, self.bus.call.emit, self.feedback, self.app_action,
                             self.suite.run, did=self.suite.did)
        self.windows = None
        if backend.ax is not None and settings["watch_logic_windows"]:
            self.windows = LogicWindows(self.plugins, backend.ax,
                                        is_logic=lambda pid: find_daw(backend.app_id_for_pid(pid)) == "logic",
                                        markers=settings["logic_plugin_markers"])
            self.plugins.windows = self.windows

        self.use_keys = use_keys
        self.key_listener = self.mouse_listener = None
        self.shortcuts_window = self.history_window = self.setup_window = None
        self._perms_ok = None
        self.perm_timer = QTimer(self, interval=1000, timeout=self._check_permissions)
        self.poll = QTimer(self, interval=300, timeout=self._poll_front)

        self.server = QLocalServer(self)
        QLocalServer.removeServer(SERVER_NAME)
        self.server.listen(SERVER_NAME)
        self.server.newConnection.connect(self._remote_command)
        self.tray = self._make_tray() if use_tray and QSystemTrayIcon.isSystemTrayAvailable() else None

    # Start-up ---------------------------------------------------------------------

    def start(self):
        self.backend.keep_responsive()
        try:
            self.link.start()
            self.plugins.link = self.link
        except OSError as e:
            self._status(f"Plugin link couldn't start: {e}")
        self.runner.start()
        if self.windows is not None:
            self.windows.start()
        self.suite.start()
        self.poll.start()
        self.start_listening()
        self._check_permissions()
        self.perm_timer.start()
        if self.settings["first_run"] or self._perms_ok is False:
            QTimer.singleShot(300, self.show_setup)
        if self.profiles.problems:
            self._status("Some shortcuts in your file couldn't be used. See My shortcuts.")

    def start_listening(self):
        if not self.use_keys:
            return
        for listener in (self.key_listener, self.mouse_listener):
            if listener is not None:
                try:
                    listener.stop()
                except Exception:
                    pass
        self.engine.release_all()
        try:
            self.key_listener = self.backend.start_keys(self.engine)
        except Exception as e:
            self.key_listener = None
            self._status(f"Shortcuts couldn't start: {e}")
        if self.windows is not None:
            try:
                self.mouse_listener = self.backend.start_mouse(self._mouse)
            except Exception:
                self.mouse_listener = None

    def _check_permissions(self):
        try:
            perms = self.backend.permissions()
        except Exception:
            return
        ok = all(p["state"] != "missing" for p in perms if p["required"])
        if ok and self._perms_ok is False:
            self.start_listening()   # just allowed: the listeners must be made again to work
            self.feedback("Limitless Keys is ready")
        if not ok:
            missing = ", ".join(p["title"] for p in perms if p["required"] and p["state"] == "missing")
            self._status(f"Needs {missing}. Open Setup from the menu bar.")
        self._perms_ok = ok
        if self.setup_window is not None:
            self.setup_window.set_permissions(perms)
        setup_open = self.setup_window is not None and self.setup_window.isVisible()
        self.perm_timer.setInterval(1000 if setup_open or not ok else 10000)

    # Which app ----------------------------------------------------------------------

    def _poll_front(self):
        try:
            app_id, pid = self.backend.frontmost()
        except Exception:
            return
        self.front = (app_id, pid)
        if find_daw(app_id):
            self.plugins.last_daw = (app_id, pid)

    def last_daw_context(self):
        app_id, pid = self.plugins.last_daw
        if app_id is None:
            app_id, pid = self.front
        return Context(app_id, pid)

    def _mouse(self, x, y, kind):
        # From the mouse thread: only clicks while Logic is in front are worth a look.
        if find_daw(self.front[0]) == "logic" and self.windows is not None:
            self.windows.mouse(x, y, kind)

    # Shortcuts --------------------------------------------------------------------------

    def _shortcut(self, binding, phase, app_id, pid):
        """From the keyboard thread, for every shortcut of yours that was pressed."""
        if phase == "down":
            self.bus.call.emit(lambda: self._heard(binding, app_id))
        self.runner.submit(binding, phase, app_id, pid)

    def _heard(self, binding, app_id):
        if self.setup_window is not None and self.setup_window.isVisible():
            where = scope_name(find_daw(app_id)) if find_daw(app_id) else (app_id or "this app")
            self.setup_window.set_heard(f"✓ {format_combo(binding.combo)} in {where}: {binding.label}")

    def app_action(self, name, ctx=None):
        if name == "cheatSheet":
            if self.cheat.isVisible():
                self.cheat.hide()
                return
            ctx = ctx if ctx is not None and ctx.app_id else self.last_daw_context()
            daw = find_daw(ctx.app_id)
            name_ = DAWS[daw]["name"] if daw else (ctx.app_id or "this app")
            self.cheat.show_for(name_, self.profiles.active(ctx.app_id))
        elif name == "pause":
            self.set_enabled(not self.engine.enabled)
        elif name == "settings":
            self.show_shortcuts()
        elif name == "history":
            self.show_history()

    def set_enabled(self, on):
        self.engine.enabled = on
        self.settings["enabled"] = on
        self.settings.save()
        self.feedback("Limitless Keys on" if on else "Limitless Keys paused")
        self.suite.paused(not on)
        if self.tray:
            self.pause_action.setChecked(not on)

    def suite_action(self, action, args):
        """Something asked for one of our actions: the hub, or the command line."""
        ctx = self.last_daw_context()
        plugin = {"pluginUndo": ("undo", "down"), "pluginRedo": ("redo", "down"),
                  "pluginBefore": ("compare", "down"), "pluginAfter": ("compare", "up"),
                  "undoFront": ("undoFront", "down")}
        if action in plugin:
            what, phase = plugin[action]
            self.runner.submit_action({"plugin": what}, phase, ctx)
            return True, ""
        if action == "press":
            try:
                combo = parse_combo(args.get("shortcut", ""))
            except ValueError as e:
                return False, str(e)
            b = self.profiles.find(ctx.app_id, combo)
            if b is None or b.passes:
                return False, f"{speak_combo(combo)} isn't one of your shortcuts here."
            self.runner.submit_action(b.action, "down", ctx)
            if b.hold:
                self.runner.submit_action(b.action, "up", ctx)
            return True, b.label
        if action in ("pause", "resume"):
            self.set_enabled(action == "resume")
            return True, ""
        if action in ("cheatSheet", "pluginHistory", "history", "settings", "setup"):
            {"cheatSheet": lambda: self.app_action("cheatSheet", ctx),
             "pluginHistory": self.show_history, "history": self.show_history,
             "settings": self.show_shortcuts, "setup": self.show_setup}[action]()
            return True, ""
        return False, f"Limitless Keys has no action {action!r}."

    # Feedback ----------------------------------------------------------------------------

    def feedback(self, text, ok=True, speak=True):
        if self.settings["toasts"]:
            self.toast.show_text(text, ok)
        if not (self.settings["speak"] and speak):
            return
        if self.suite.say(text):
            return      # the suite's one voice said it
        if self.tts is not None:
            self.tts.stop()
            self.tts.say(text)

    def _status(self, text):
        if self.tray:
            self.tray.setToolTip(f"Limitless Keys\n{text}" if text else "Limitless Keys")

    def plugin_status(self):
        links = sum(1 for s in self.plugins.timeline.sources.values() if s.kind == "link")
        parts = [f"Limitless Undo plugins connected: {links}"]
        if self.windows is not None:
            parts.append("Logic plugin windows: watching")
        if not self.engine.enabled:
            parts.append("Paused")
        return " · ".join(parts)

    # Windows ------------------------------------------------------------------------------

    def _front_window(self, w):
        w.show()
        w.raise_()
        w.activateWindow()
        self.backend.bring_to_front()

    def show_shortcuts(self):
        if self.shortcuts_window is None:
            w = ShortcutsWindow(self.profiles, self.suite.suite_actions)
            w.capture.connect(self._capture_for)
            w.add_app_requested.connect(self._add_app)
            self.shortcuts_window = w
        self.shortcuts_window.refresh()
        self._front_window(self.shortcuts_window)

    def _capture_for(self, dialog):
        """Catch the next shortcut pressed anywhere, for the shortcut editor."""
        def got(combo):
            self.bus.call.emit(lambda: dialog.got_combo(combo))
        self.engine.capture_next(got)

    def _add_app(self):
        try:
            apps = self.backend.running_apps()
        except Exception:
            apps = []
        dlg = AddAppDialog(apps, self.shortcuts_window)
        if dlg.exec() and dlg.choice:
            app_id, name = dlg.choice
            self.shortcuts_window.add_scope(app_id, name)

    def show_history(self):
        if self.history_window is None:
            w = HistoryWindow(self.plugins, self.plugin_status)
            w.undo.connect(lambda: self.suite_action("pluginUndo", {}))
            w.redo.connect(lambda: self.suite_action("pluginRedo", {}))
            self.history_window = w
        self._front_window(self.history_window)

    def show_setup(self):
        if self.setup_window is None:
            login = self.backend.open_at_login() if self.backend.can_open_at_login() else None
            w = Setup(login)
            w.request_permission.connect(self.backend.request_permission)
            w.open_logic_undo.connect(self.open_logic_undo)
            w.install_plugin.connect(self.install_plugin)
            w.login_changed.connect(self.set_open_at_login)
            w.finished.connect(self._setup_done)
            self.setup_window = w
        self.setup_window.set_plugin_status(self._plugin_install_text())
        self._check_permissions()
        self._front_window(self.setup_window)

    def _plugin_install_text(self):
        bundled = self.backend.bundled_plugins()
        have = ", ".join(p.name for p in bundled) if bundled else "none in this copy (see the README to build it)"
        return f"Plugins inside Limitless Keys: {have}. {self.plugin_status()}."

    def _setup_done(self):
        self.settings["first_run"] = False
        self.settings.save()
        self.feedback("Ready. Option Command Z undoes plugin changes.")

    def open_logic_undo(self):
        pid = getattr(self.backend, "pid_for", lambda _: None)("logic")
        if not pid:
            self.feedback("Open Logic Pro first.", ok=False)
            return
        self.backend.activate(pid)

        def then():
            self.runner.submit_action({"menu": "Edit > Undo History…"}, "down", Context("com.apple.logic10", pid))
            self.feedback("In Undo History, turn Plug-in off next to Include Parameter Changes From.")
        QTimer.singleShot(500, then)

    def install_plugin(self):
        self.feedback("Installing Limitless Undo…")

        def work():
            try:
                ok, message = self.backend.install_plugins()
            except Exception as e:
                ok, message = False, f"Couldn't install it: {e}"
            self.bus.call.emit(lambda: self._installed(ok, message))
        threading.Thread(target=work, daemon=True).start()

    def _installed(self, ok, message):
        self.feedback(message, ok)
        if self.setup_window is not None:
            self.setup_window.set_plugin_status(message)

    def set_open_at_login(self, on):
        try:
            self.backend.set_open_at_login(on)
        except Exception as e:
            self._status(f"Couldn't change Open at login: {e}")
        if self.tray and hasattr(self, "login_action"):
            self.login_action.setChecked(self.backend.open_at_login())

    def save_report(self):
        """A text outline of the window in front, to help with an app that doesn't work yet."""
        ctx = self.last_daw_context()

        def work():
            try:
                text = self.backend.window_report(ctx.pid)
                path = Path.home() / "Desktop" / "Limitless Keys window report.txt"
                path.write_text(f"App: {ctx.app_id}\n\n{text}\n", encoding="utf-8")
                self.bus.call.emit(lambda: (self.feedback("Saved a report on your Desktop."),
                                            self.backend.reveal(path)))
            except Exception as e:
                self.bus.call.emit(lambda: self.feedback(f"Couldn't save the report: {e}", ok=False))
        threading.Thread(target=work, daemon=True).start()

    # Menu bar -------------------------------------------------------------------------------

    def _make_tray(self):
        tray = QSystemTrayIcon(tray_icon(), self)
        menu = QMenu()
        menu.addAction("Undo the last plugin change", lambda: self.suite_action("pluginUndo", {}))
        menu.addAction("Redo the last plugin change", lambda: self.suite_action("pluginRedo", {}))
        menu.addAction("Plugin changes…", self.show_history)
        menu.addSeparator()
        menu.addAction("My shortcuts…", self.show_shortcuts)
        menu.addAction("Show my shortcuts for this app", lambda: self.app_action("cheatSheet"))
        self.pause_action = QAction("Pause Limitless Keys", menu, checkable=True)
        self.pause_action.setChecked(not self.engine.enabled)
        self.pause_action.triggered.connect(lambda paused: self.set_enabled(not paused))
        menu.addAction(self.pause_action)
        speak = QAction("Say what each shortcut did", menu, checkable=True)
        speak.setChecked(self.settings["speak"])
        speak.triggered.connect(lambda on: (self.settings.__setitem__("speak", on), self.settings.save()))
        menu.addAction(speak)
        menu.addSeparator()
        if self.backend.can_open_at_login():
            self.login_action = QAction("Open at login", menu, checkable=True)
            self.login_action.setChecked(self.backend.open_at_login())
            self.login_action.triggered.connect(self.set_open_at_login)
            menu.addAction(self.login_action)
        menu.addAction("Setup and help…", self.show_setup)
        menu.addAction("Save a report of the window in front", self.save_report)
        menu.addSeparator()
        menu.addAction("Quit Limitless Keys", QApplication.quit)
        tray.setContextMenu(menu)
        tray.setToolTip("Limitless Keys")
        tray.show()
        self._menu = menu
        return tray

    def _remote_command(self):
        sock = self.server.nextPendingConnection()

        def read():
            words = bytes(sock.readAll()).decode("utf-8", "ignore").split()
            for word in words:
                if word in REMOTE:
                    self.suite_action(word, {})
            if words:
                sock.write(b"ok\n")
                sock.flush()

        sock.readyRead.connect(read)
        sock.disconnected.connect(sock.deleteLater)
        read()

    def stop(self):
        self.link.stop()
        self.suite.stop()


def send_remote(action, timeout_ms=1000):
    """Send an action to a running copy. Returns True if one was running."""
    sock = QLocalSocket()
    sock.connectToServer(SERVER_NAME)
    if not sock.waitForConnected(timeout_ms):
        return False
    sock.write((action + "\n").encode())
    sock.flush()
    sock.waitForBytesWritten(timeout_ms)
    sock.waitForReadyRead(timeout_ms)
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


def _mac_parts():
    if sys.platform != "darwin":
        return True
    import Quartz  # noqa: F401

    from . import macax  # noqa: F401

    return True


def main(argv=None):
    parser = argparse.ArgumentParser(prog="limitless-keys",
                                     description="Your own shortcuts for every DAW, and plugin undo")
    parser.add_argument("--do", metavar="ACTION",
                        help="tell the running app to do something: " + ", ".join(sorted(REMOTE)))
    parser.add_argument("--no-keys", action="store_true", help="don't catch shortcuts system-wide")
    parser.add_argument("--selftest", action="store_true", help="start everything, then quit (for builds)")
    args = parser.parse_args(argv)

    qapp = QApplication(sys.argv[:1])
    qapp.setApplicationName("Limitless Keys")
    qapp.setQuitOnLastWindowClosed(False)
    qapp.setWindowIcon(app_icon())

    if args.do:
        return 0 if send_remote(args.do) else 1
    if not args.selftest and send_remote("settings"):
        return 0   # already running: show its shortcuts

    from .platforms import get_backend

    settings = Settings()
    profiles = Profiles.load(config_dir() / "shortcuts.json")
    if args.selftest:
        settings["first_run"] = False
    app = KeysApp(settings, profiles, get_backend(), use_keys=not (args.no_keys or args.selftest))
    app.start()
    qapp.aboutToQuit.connect(app.stop)
    if args.selftest:
        def check():
            undo = profiles.find("com.apple.logic10", parse_combo("alt+cmd+z"))
            results = {"shortcuts": undo is not None and undo.action == {"plugin": "undo"},
                       "plugin link": app.link.port is not None,
                       "icon": not app_icon().isNull(),
                       "mac parts": _try(_mac_parts)}
            for name, ok in results.items():
                print(f"selftest {name}: {'ok' if ok else 'FAILED'}")
            ok = all(results.values())
            print("selftest", "ok" if ok else "FAILED")
            qapp.exit(0 if ok else 1)
        QTimer.singleShot(1500, check)
    return qapp.exec()


if __name__ == "__main__":
    sys.exit(main())
