"""Limitless Control: runs the controller in the background and serves the settings page.

The settings page is a local web page (only reachable from this computer) so it
works with VoiceOver, Narrator, NVDA, zoom and high-contrast modes out of the box.
"""

from __future__ import annotations

import argparse
import collections
import copy
import json
import os
import secrets
import socket
import subprocess
import sys
import threading
import time
import webbrowser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from . import __version__, applog, frontmost, keys, login, profiles
from .engine import Engine

PORT = 47820
WEB_DIR = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent)) / "limitless_control" / "web"
if not WEB_DIR.exists():
    WEB_DIR = Path(__file__).resolve().parent / "web"


def accessibility_ok() -> bool:
    """On Mac, sending keys to other apps needs Accessibility permission."""
    if sys.platform != "darwin":
        return True
    try:
        import ctypes
        lib = ctypes.cdll.LoadLibrary("/System/Library/Frameworks/ApplicationServices.framework/ApplicationServices")
        lib.AXIsProcessTrusted.restype = ctypes.c_bool
        return bool(lib.AXIsProcessTrusted())
    except Exception:
        return True


def request_accessibility() -> None:
    """Ask macOS to list Limitless Control under Accessibility, then open that settings pane."""
    if sys.platform != "darwin":
        return
    try:
        from HIServices import AXIsProcessTrustedWithOptions, kAXTrustedCheckOptionPrompt
        AXIsProcessTrustedWithOptions({kAXTrustedCheckOptionPrompt: True})
    except Exception:
        pass
    subprocess.Popen(["open", "x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility"])


def validate(config: dict) -> list[str]:
    """Problems that would stop the setup working, in plain words."""
    problems = []
    if not isinstance(config.get("profiles"), list) or not config["profiles"]:
        return ["There are no profiles."]
    sections = [("Everywhere", [config.get("global", {})])]
    sections += [(p.get("name", "?"), p.get("layers", [])) for p in config["profiles"]]
    for name, layers in sections:
        for i, layer in enumerate(layers):
            for inp, b in layer.items():
                for kind in ("tap", "hold"):
                    a = (b or {}).get(kind)
                    if not a or "keys" not in a:
                        continue
                    k = a["keys"]
                    for variant in (k.values() if isinstance(k, dict) else [k]):
                        try:
                            keys.parse(variant)
                        except (ValueError, AttributeError) as exc:
                            problems.append(f"{name}, layer {i + 1}, {inp} {kind}: {exc}")
    return problems


class Log:
    def __init__(self):
        self.lines = collections.deque(maxlen=50)

    def __call__(self, text: str) -> None:
        stamp = time.strftime("%H:%M:%S")
        self.lines.append(f"{stamp}  {text}")
        print(text, flush=True)


class Output:
    """Engine output: real key presses and speech, plus a log of what fired."""

    def __init__(self, log: Log, dry_run: bool = False):
        from .output import KeySender, Speaker
        self.log = log
        self.dry_run = dry_run
        self.sender = None if dry_run else KeySender(log)
        self.speaker = Speaker(log)
        self.last_action = ""
        self.suite_say = None

    def send(self, k) -> None:
        text = keys.resolve(k)
        self.last_action = text or ""
        if self.dry_run:
            self.log(f"(test mode) would press {text}")
        elif self.sender:
            self.sender.send(k)

    def speak(self, text: str) -> None:
        # With Limitless Sound's one voice on, the hub speaks so apps never talk over each other.
        if self.suite_say and self.suite_say(text):
            return
        self.speaker.speak(text)


class App:
    def __init__(self, dry_run: bool = False):
        self.lock = threading.RLock()
        self.log = Log()
        self.output = Output(self.log, dry_run)
        self.config = profiles.load()
        self.engine = Engine(self.config, self.output)
        self.reader = None
        self.front_app: str | None = None
        self.last_input = {"name": None, "at": 0.0}
        self.last_action = {"input": None, "label": None, "at": 0.0}
        self.token = secrets.token_urlsafe(16)
        self.url = ""
        self.running = True
        self.restart = False
        self.menu = None
        self.engine.on_fire = self._fired
        from .suite import OWN_LOOK, Suite
        # Text size, high contrast and reduced motion for the settings page; the suite can change them.
        self.look = dict(OWN_LOOK)
        self.suite = Suite(self)
        self.output.suite_say = self.suite.say

    # Controller callbacks (main thread)

    def _press(self, name: str) -> None:
        with self.lock:
            self.last_input = {"name": name, "at": time.time()}
            self.engine.press(name, time.monotonic())

    def _release(self, name: str) -> None:
        with self.lock:
            self.engine.release(name, time.monotonic())

    def _fired(self, name: str, action: dict) -> None:
        self.last_action = {"input": name, "label": self.action_label(action), "at": time.time()}

    def action_label(self, action: dict) -> str:
        """The name a person would use for an action: "Record", "Layer 2 for the next switch"."""
        ident = action.get("id") or action.get("command")
        if ident in profiles.COMMANDS:
            return profiles.COMMANDS[ident]["label"]
        if action.get("command") == "suite":
            for a in self.suite.suite_actions():
                if a.get("id") == action.get("suite"):
                    return a.get("label", action["suite"])
            return action.get("suite", "")
        profile = (self.engine.profile or {}).get("name", "")
        for name in (profile, *profiles.CATALOG):
            entry = profiles.CATALOG.get(name, {}).get(ident or "")
            if entry and entry.get("keys") == action.get("keys"):
                return entry["label"]
        k = keys.resolve(action.get("keys"))
        try:
            return keys.describe(k) if k else ""
        except ValueError:
            return k or ""

    def open_settings(self) -> None:
        if self.url:
            webbrowser.open(self.url)

    def toggle_enabled(self) -> None:
        with self.lock:
            self.engine.set_enabled(not self.engine.enabled)

    def next_layer(self) -> None:
        with self.lock:
            self.engine._run("layer", {})
            self.engine.on_change()

    def quit(self) -> None:
        self.running = False

    # Settings API (server threads)

    def state(self) -> dict:
        with self.lock:
            p = self.engine.profile or {}
            return {
                "version": __version__,
                "platform": keys.platform_name(),
                "enabled": self.engine.enabled,
                "layer": self.engine.layer + 1,
                "profile": p.get("name"),
                "app": self.front_app,
                "controllers": self.reader.connected if self.reader else [],
                "lastInput": self.last_input,
                "lastAction": self.last_action,
                "held": self.reader.held if self.reader else [],
                "now": time.time(),
                "accessibility": accessibility_ok(),
                "setupDone": bool(self.config.get("setupDone")),
                "startAtLogin": login.is_enabled(),
                "menuBar": self.menu is not None,
                "look": dict(self.look),
                "log": list(self.output.log.lines)[-12:],
            }

    def settings(self) -> dict:
        with self.lock:
            from .controller import ALL_INPUTS
            return {
                "config": copy.deepcopy(self.config),
                "catalog": profiles.CATALOG,
                "commands": profiles.COMMANDS,
                "timingPresets": profiles.TIMING_PRESETS,
                "suite": self.suite.suite_actions(),
                "inputs": ALL_INPUTS,
                "platform": keys.platform_name(),
                "path": str(profiles.config_path()),
            }

    def apply(self, config: dict) -> list[str]:
        problems = validate(config)
        if problems:
            return problems
        with self.lock:
            # The settings page and a reset never undo the finished welcome steps.
            if self.config.get("setupDone") and "setupDone" not in config:
                config["setupDone"] = True
            self.config = config
            profiles.save(config)
            self.engine.reload(config, self.front_app)
            if self.reader:
                self.reader.threshold = float(config.get("analogThreshold", 0.6))
        return []

    # Main loop

    def run(self, open_browser: bool) -> None:
        from .controller import ControllerReader
        server = self._serve()
        self.url = f"http://127.0.0.1:{server.server_address[1]}/?t={self.token}"
        self._write_session(server.server_address[1])
        self.log(f"Limitless Control {__version__} running. Settings: {self.url}")
        if not accessibility_ok():
            self.log("Mac: allow Accessibility access so key commands reach your apps.")
        # The first time, always show the guided setup.
        if open_browser or not self.config.get("setupDone"):
            self.open_settings()

        self.suite.start()
        self.reader = ControllerReader(self._press, self._release, self.log)
        self.reader.threshold = float(self.config.get("analogThreshold", 0.6))
        self.reader.start()
        if sys.platform == "darwin" and self.reader.video_driver == "cocoa":
            try:
                from .macmenu import MenuBar
                self.menu = MenuBar(self.open_settings, self.toggle_enabled, self.next_layer, self.quit)
            except Exception as exc:
                self.log(f"Menu bar icon unavailable: {exc}")
        next_app_check = 0.0
        try:
            while self.running:
                self.reader.poll()
                now = time.monotonic()
                with self.lock:
                    self.engine.tick(now)
                if now >= next_app_check:
                    next_app_check = now + 0.4
                    app = frontmost.frontmost_app()
                    if app != self.front_app:
                        with self.lock:
                            self.front_app = app
                            self.engine.app_changed(app)
                            self.suite.report_state()
                    if self.menu:
                        with self.lock:
                            p = self.engine.profile or {}
                            state = (self.engine.enabled, self.engine.layer + 1, p.get("name"))
                        self.menu.update(*state, self.reader.connected)
                # Every 10 ms while a controller is plugged in or a switch is held. With
                # nothing connected, 20 times a second still notices one being plugged in.
                time.sleep(0.01 if self.reader.connected or self.engine.busy else 0.05)
        except KeyboardInterrupt:
            pass
        finally:
            server.shutdown()
            server.server_close()
            self.suite.stop()
            self.reader.stop()
            self._clear_session()
            if self.restart:
                relaunch()

    def _serve(self) -> ThreadingHTTPServer:
        app = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def _ok_origin(self) -> bool:
                host = self.headers.get("Host", "")
                return host in (f"127.0.0.1:{self.server.server_address[1]}", f"localhost:{self.server.server_address[1]}")

            def _authorized(self) -> bool:
                return self._ok_origin() and secrets.compare_digest(self.headers.get("X-Token", ""), app.token)

            def _send(self, code: int, body: bytes, ctype: str) -> None:
                self.send_response(code)
                self.send_header("Content-Type", ctype)
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-store")
                self.send_header("X-Content-Type-Options", "nosniff")
                self.send_header("Referrer-Policy", "no-referrer")
                self.end_headers()
                self.wfile.write(body)

            def _json(self, data, code: int = 200) -> None:
                self._send(code, json.dumps(data).encode(), "application/json")

            def do_GET(self):
                if not self._ok_origin():
                    return self._send(HTTPStatus.FORBIDDEN, b"Forbidden", "text/plain")
                path = urlparse(self.path).path
                if path in ("/", "/index.html"):
                    body = (WEB_DIR / "index.html").read_bytes()
                    return self._send(200, body, "text/html; charset=utf-8")
                if path == "/favicon.ico":
                    return self._send(204, b"", "image/x-icon")
                if not self._authorized():
                    return self._json({"error": "Open settings from the Limitless Control app."}, 403)
                if path == "/api/state":
                    return self._json(app.state())
                if path == "/api/settings":
                    return self._json(app.settings())
                self._send(404, b"Not found", "text/plain")

            def do_POST(self):
                if not self._authorized():
                    return self._json({"error": "forbidden"}, 403)
                length = int(self.headers.get("Content-Length", 0) or 0)
                try:
                    data = json.loads(self.rfile.read(length) or b"{}")
                except ValueError:
                    return self._json({"error": "bad json"}, 400)
                path = urlparse(self.path).path
                if path == "/api/settings":
                    problems = app.apply(data.get("config", {}))
                    return self._json({"ok": not problems, "problems": problems}, 200 if not problems else 400)
                if path == "/api/reset":
                    app.apply(profiles.default_config())
                    return self._json({"ok": True})
                if path == "/api/enabled":
                    with app.lock:
                        app.engine.set_enabled(bool(data.get("enabled")))
                    return self._json({"ok": True})
                if path == "/api/open-accessibility" and sys.platform == "darwin":
                    request_accessibility()
                    return self._json({"ok": True})
                if path == "/api/login":
                    try:
                        login.set_enabled(bool(data.get("enabled")))
                    except OSError as exc:
                        return self._json({"ok": False, "problems": [str(exc)]}, 500)
                    return self._json({"ok": True, "enabled": login.is_enabled()})
                if path == "/api/setup-done":
                    with app.lock:
                        config = copy.deepcopy(app.config)
                    config["setupDone"] = True
                    app.apply(config)
                    return self._json({"ok": True})
                if path == "/api/restart":
                    app.restart = True
                    app.running = False
                    return self._json({"ok": True})
                if path == "/api/quit":
                    app.running = False
                    return self._json({"ok": True})
                if path == "/api/simulate" and app.output.dry_run and app.reader:
                    # Test mode only: act as if a switch was pressed or released.
                    name, down = str(data.get("input", "")), bool(data.get("down"))
                    held = app.reader._down.setdefault(-1, set())
                    (held.add if down else held.discard)(name)
                    (app._press if down else app._release)(name)
                    return self._json({"ok": True})
                self._json({"error": "not found"}, 404)

        server = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
        server.daemon_threads = True
        threading.Thread(target=server.serve_forever, daemon=True, name="settings").start()
        return server

    def _session_file(self) -> Path:
        return profiles.config_dir() / "session.json"

    def _write_session(self, port: int) -> None:
        f = self._session_file()
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(json.dumps({"port": port, "token": self.token, "pid": os.getpid()}))
        try:
            os.chmod(f, 0o600)
        except OSError:
            pass

    def _clear_session(self) -> None:
        try:
            self._session_file().unlink()
        except OSError:
            pass


def relaunch() -> None:
    """Start a fresh copy (macOS reads a new Accessibility grant reliably only at launch)."""
    if getattr(sys, "frozen", False):
        exe = Path(sys.executable)
        bundle = exe.parents[2]
        if sys.platform == "darwin" and bundle.suffix == ".app":
            subprocess.Popen(["/usr/bin/open", "-n", str(bundle)])
        else:
            subprocess.Popen([str(exe)])
    else:
        subprocess.Popen([sys.executable, "-m", "limitless_control"])


def already_running() -> dict | None:
    """If another copy is running, return its session so we can just open its settings."""
    with socket.socket() as s:
        if s.connect_ex(("127.0.0.1", PORT)) != 0:
            return None
    try:
        return json.loads((profiles.config_dir() / "session.json").read_text())
    except (OSError, ValueError):
        return {}


def self_test() -> int:
    """Check that a packaged build starts: controller layer, key output, speech and settings page."""
    import urllib.request
    from .controller import ControllerReader
    from .output import KeySender

    app = App(dry_run=True)
    KeySender(app.log)
    reader = ControllerReader(lambda n: None, lambda n: None, app.log)
    reader.start()
    reader.poll()
    app.reader = reader
    login.is_enabled()
    if sys.platform == "darwin":
        # Make sure the Mac pieces made it into the package.
        import AppKit  # noqa: F401
        import HIServices  # noqa: F401
        from . import macmenu  # noqa: F401
        frontmost.frontmost_app()
    state = app.state()
    assert "setupDone" in state and "held" in state, "state incomplete"
    server = app._serve()
    port = server.server_address[1]
    try:
        page = urllib.request.urlopen(f"http://127.0.0.1:{port}/", timeout=5).read()
        req = urllib.request.Request(f"http://127.0.0.1:{port}/api/settings", headers={"X-Token": app.token})
        settings = json.loads(urllib.request.urlopen(req, timeout=5).read())
        assert b"Limitless Control" in page, "settings page missing"
        assert len(settings["config"]["profiles"]) >= 4, "profiles missing"
    finally:
        server.shutdown()
        reader.stop()
    print(f"Self-test passed on {keys.platform_name()}")
    return 0


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(prog="limitless-control", description="Use switches and adaptive controllers as key commands.")
    parser.add_argument("--background", action="store_true", help="start without opening the settings page")
    parser.add_argument("--test-mode", action="store_true", help="log key commands instead of pressing them")
    parser.add_argument("--self-test", action="store_true", help="check the app starts, then quit")
    args = parser.parse_args(argv)
    applog.start("Limitless Control", __version__)
    if args.self_test:
        sys.exit(self_test())

    other = already_running()
    if other is not None:
        if other.get("token"):
            webbrowser.open(f"http://127.0.0.1:{other.get('port', PORT)}/?t={other['token']}")
        else:
            print(f"Something else is using port {PORT}.")
        return
    App(dry_run=args.test_mode).run(open_browser=not args.background)


if __name__ == "__main__":
    main()
