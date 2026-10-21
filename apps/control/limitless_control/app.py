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

from . import __version__, frontmost, keys, profiles
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

    def send(self, k) -> None:
        text = keys.resolve(k)
        self.last_action = text or ""
        if self.dry_run:
            self.log(f"(test mode) would press {text}")
        elif self.sender:
            self.sender.send(k)

    def speak(self, text: str) -> None:
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
        self.token = secrets.token_urlsafe(16)
        self.running = True

    # Controller callbacks (main thread)

    def _press(self, name: str) -> None:
        with self.lock:
            self.last_input = {"name": name, "at": time.time()}
            self.engine.press(name, time.monotonic())

    def _release(self, name: str) -> None:
        with self.lock:
            self.engine.release(name, time.monotonic())

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
                "now": time.time(),
                "accessibility": accessibility_ok(),
                "log": list(self.output.log.lines)[-12:],
            }

    def settings(self) -> dict:
        with self.lock:
            from .controller import ALL_INPUTS
            return {
                "config": copy.deepcopy(self.config),
                "catalog": profiles.CATALOG,
                "commands": profiles.COMMANDS,
                "inputs": ALL_INPUTS,
                "platform": keys.platform_name(),
                "path": str(profiles.config_path()),
            }

    def apply(self, config: dict) -> list[str]:
        problems = validate(config)
        if problems:
            return problems
        with self.lock:
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
        url = f"http://127.0.0.1:{server.server_address[1]}/?t={self.token}"
        self._write_session(server.server_address[1])
        self.log(f"Limitless Control {__version__} running. Settings: {url}")
        if not accessibility_ok():
            self.log("Mac: allow Accessibility access so key commands reach your apps.")
        if open_browser:
            webbrowser.open(url)

        self.reader = ControllerReader(self._press, self._release, self.log)
        self.reader.threshold = float(self.config.get("analogThreshold", 0.6))
        self.reader.start()
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
                time.sleep(0.01)
        except KeyboardInterrupt:
            pass
        finally:
            server.shutdown()
            self.reader.stop()
            self._clear_session()

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
                    subprocess.Popen(["open", "x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility"])
                    return self._json({"ok": True})
                if path == "/api/quit":
                    app.running = False
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
