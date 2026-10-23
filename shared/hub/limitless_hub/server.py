"""The hub's two local doors, both on 127.0.0.1 only.

  TCP  (default 47900)  tools stay connected here, one JSON message per line.
  HTTP (default 47901)  the settings page, plus one-shot triggers for Stream Deck,
                        Shortcuts, AutoHotkey or a browser bookmark:
                        GET /do/zoom.in?t=<token>
Both need the token from link.json, which only this user can read.
"""

from __future__ import annotations

import json
import os
from collections import deque
import secrets
import socket
import socketserver
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib import resources
from urllib.parse import parse_qs, unquote, urlparse

from . import __version__, applog, catalog, launcher as launcher_mod, paths
from . import setup as setup_mod
from .bus import PROTOCOL, Bus
from .speech import Speaker

MAX_LINE = 64 * 1024
HELLO_TIMEOUT = 5.0


def _bind(server_cls, handler, start_port: int):
    last = None
    for port in range(start_port, start_port + 10):
        try:
            return server_cls(("127.0.0.1", port), handler)
        except OSError as e:
            last = e
    raise OSError(f"No free port near {start_port}: {last}")


class _TCPServer(socketserver.ThreadingTCPServer):
    daemon_threads = True
    allow_reuse_address = not os.name == "nt"


class _HTTPServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = not os.name == "nt"

    def server_bind(self):
        # HTTPServer's own server_bind also looks up the computer's full name
        # (socket.getfqdn), which nothing here uses. On a Mac that lookup can wait on
        # multicast DNS for half a minute: Limitless Control took 35 s to start that way.
        socketserver.TCPServer.server_bind(self)
        self.server_name, self.server_port = self.server_address[:2]


class Outbox:
    """What the hub has to send one app. Sending never blocks the suite: when an app
    falls behind, its oldest events are dropped, but never an answer, a request or settings."""

    MAX_EVENTS = 1000
    MAX_OTHER = 5000  # past this the app has stopped reading altogether

    def __init__(self):
        self._items: deque = deque()
        self._events = 0
        self._cond = threading.Condition()
        self._closed = False

    def put(self, line: str, is_event: bool) -> None:
        with self._cond:
            if self._closed:
                return
            if is_event and self._events >= self.MAX_EVENTS:
                for i, (_, ev) in enumerate(self._items):
                    if ev:
                        del self._items[i]
                        self._events -= 1
                        break
            elif not is_event and len(self._items) - self._events >= self.MAX_OTHER:
                return
            self._items.append((line, is_event))
            self._events += is_event
            self._cond.notify()

    def get(self):
        with self._cond:
            while not self._items and not self._closed:
                self._cond.wait()
            if not self._items:
                return None
            line, ev = self._items.popleft()
            self._events -= ev
            return line

    def close(self) -> None:
        with self._cond:
            self._closed = True  # what's already queued (a last error) still goes out
            self._cond.notify_all()


class Hub:
    def __init__(self, settings: dict | None = None, *, token: str | None = None, port: int = paths.DEFAULT_PORT,
                 http_port: int = paths.DEFAULT_HTTP_PORT, speaker=None, launcher=None, write_link: bool = True,
                 persist: bool = True):
        self.settings = settings if settings is not None else (paths.read_json(paths.settings_file()) or {})
        self.token = token or secrets.token_urlsafe(24)
        self.persist = persist
        self.write_link = write_link
        self.launcher = launcher or launcher_mod.Launcher(self.settings, settings_url=self.page_url)
        self.bus = Bus(self.settings, self.token, launcher=self.launcher, save=self._save)
        self.bus.speaker = speaker if speaker is not None else Speaker(
            on_speaking=lambda on: self.bus.set_state("hub.speaking", on))
        self._socks: set[socket.socket] = set()
        self.tcp = _bind(_TCPServer, self._tcp_handler(), port)
        self.http = _bind(_HTTPServer, self._http_handler(), http_port)
        self.port = self.tcp.server_address[1]
        self.http_port = self.http.server_address[1]
        self._stop = threading.Event()
        self.quit = threading.Event()  # set by the page's Quit button

    # ------------------------------------------------------------------ lifecycle

    def page_url(self) -> str:
        return f"http://127.0.0.1:{self.http_port}/?t={self.token}"

    def _save(self, settings: dict) -> None:
        if self.persist:
            paths.write_private(paths.settings_file(), settings)

    def start(self) -> "Hub":
        for target, name in ((self.tcp.serve_forever, "link"), (self.http.serve_forever, "page"), (self._ticker, "tick")):
            threading.Thread(target=target, daemon=True, name=name).start()
        if self.write_link:
            paths.write_private(paths.link_file(), {
                "protocol": PROTOCOL, "port": self.port, "http": self.http_port,
                "token": self.token, "pid": os.getpid(), "version": __version__})
        self.bus._note(f"Limitless Sound hub {__version__} started", "info")
        return self

    def _ticker(self) -> None:
        while not self._stop.wait(0.5):
            self.bus.tick()

    def stop(self) -> None:
        self._stop.set()
        for sock in list(self._socks):  # tools notice at once and start reconnecting
            try:
                sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
        self.tcp.shutdown()
        self.http.shutdown()
        self.tcp.server_close()
        self.http.server_close()
        if self.write_link:
            current = paths.read_json(paths.link_file()) or {}
            if current.get("token") == self.token:
                try:
                    paths.link_file().unlink()
                except OSError:
                    pass

    def invoke_wait(self, action: str, args: dict | None, source: str, timeout: float = 3.5) -> dict:
        box: dict = {}
        done = threading.Event()

        def got(result):
            box.update(result)
            done.set()

        self.bus.invoke(action, args or {}, source=source, on_result=got)
        if not done.wait(timeout):
            return {"ok": False, "message": "No answer."}
        return box

    # ------------------------------------------------------------------ TCP: tools

    def _tcp_handler(self):
        bus = self.bus
        socks = self._socks

        class Handler(socketserver.StreamRequestHandler):
            def handle(self):
                out = Outbox()
                sock = self.request
                socks.add(sock)

                def send(msg: dict) -> None:
                    out.put(json.dumps(msg, separators=(",", ":")) + "\n", msg.get("op") == "event")

                def writer():
                    while True:
                        line = out.get()
                        if line is None:
                            return
                        try:
                            sock.sendall(line.encode())
                        except OSError:
                            return

                threading.Thread(target=writer, daemon=True).start()
                conn = bus.attach(send)
                sock.settimeout(HELLO_TIMEOUT)
                try:
                    while not conn.closed:
                        line = self.rfile.readline(MAX_LINE + 1)
                        if not line:
                            break
                        if len(line) > MAX_LINE:
                            send({"op": "error", "message": "Message too long."})
                            break
                        try:
                            msg = json.loads(line)
                        except ValueError:
                            send({"op": "error", "message": "Not JSON."})
                            continue
                        if not bus.receive(conn, msg):
                            time.sleep(0.05)
                            break
                        if conn.tool:
                            sock.settimeout(None)
                except (OSError, ValueError):
                    pass
                finally:
                    socks.discard(sock)
                    bus.detach(conn)
                    out.close()

        return Handler

    # ------------------------------------------------------------------ HTTP: page & triggers

    def _http_handler(self):
        hub = self

        class Handler(BaseHTTPRequestHandler):
            server_version = "LimitlessSound"

            def log_message(self, *args):
                pass

            def _host_ok(self) -> bool:
                host = (self.headers.get("Host") or "").lower()
                return host in (f"127.0.0.1:{hub.http_port}", f"localhost:{hub.http_port}")

            def _token(self, query) -> str:
                return self.headers.get("X-Limitless-Token") or (query.get("t") or [""])[0]

            def _send(self, code: int, body: bytes, ctype: str) -> None:
                self.send_response(code)
                self.send_header("Content-Type", ctype)
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-store")
                self.send_header("X-Content-Type-Options", "nosniff")
                self.send_header("Referrer-Policy", "no-referrer")
                self.send_header("Content-Security-Policy",
                                 "default-src 'self'; style-src 'self' 'unsafe-inline'; script-src 'self' 'unsafe-inline'; connect-src 'self'")
                self.end_headers()
                self.wfile.write(body)

            def _json(self, data, code=200) -> None:
                self._send(code, json.dumps(data).encode(), "application/json")

            def _text(self, text, code=200) -> None:
                self._send(code, text.encode(), "text/plain; charset=utf-8")

            def do_GET(self):
                url = urlparse(self.path)
                query = parse_qs(url.query)
                if not self._host_ok():
                    return self._text("Wrong host.", 403)
                if url.path == "/favicon.ico":
                    return self._send(204, b"", "image/x-icon")
                authed = secrets.compare_digest(self._token(query), hub.token)
                if url.path in ("/", "/index.html"):
                    if not authed:
                        return self._text("Open Limitless Sound from its icon to see this page.", 403)
                    page = resources.files("limitless_hub").joinpath("web/index.html").read_bytes()
                    return self._send(200, page, "text/html; charset=utf-8")
                if not authed:
                    return self._text("Missing or wrong token.", 403)
                if url.path == "/api/state":
                    since = int((query.get("since") or ["0"])[0] or 0)
                    return self._json(hub.bus.snapshot(since))
                if url.path.startswith("/do/"):
                    action = unquote(url.path[4:])
                    args = {k: v[0] for k, v in query.items() if k != "t"}
                    r = hub.invoke_wait(action, args, "http")
                    return self._text(r.get("message") or ("Done" if r.get("ok") else "Failed"), 200 if r.get("ok") else 409)
                return self._text("Not found.", 404)

            def do_POST(self):
                url = urlparse(self.path)
                if not self._host_ok():
                    return self._json({"error": "Wrong host."}, 403)
                # POSTs need the header, which other websites can't send without asking first.
                if not secrets.compare_digest(self.headers.get("X-Limitless-Token") or "", hub.token):
                    return self._json({"error": "Missing or wrong token."}, 403)
                try:
                    length = min(int(self.headers.get("Content-Length") or 0), 256 * 1024)
                    body = json.loads(self.rfile.read(length) or b"{}")
                except ValueError:
                    return self._json({"error": "Not JSON."}, 400)
                if not isinstance(body, dict):
                    return self._json({"error": "Expected an object."}, 400)
                bus = hub.bus
                p = url.path
                if p == "/api/invoke":
                    args = body.get("args") if isinstance(body.get("args"), dict) else {}
                    return self._json(hub.invoke_wait(str(body.get("action") or ""), args, "page"))
                if p == "/api/prefs":
                    prefs = bus.set_prefs(body.get("prefs") or {})
                    return self._json({"prefs": prefs, "languageVoice": bus.has_voice(prefs["language"])})
                if p == "/api/routes":
                    problems = bus.set_routes(body.get("routes"))
                    return self._json({"ok": not problems, "problems": problems}, 200 if not problems else 400)
                if p == "/api/intent-order":
                    bus.set_intent_order(body.get("order") or [])
                    return self._json({"ok": True})
                if p == "/api/start-tools":
                    with bus.lock:
                        hub.settings["startTools"] = [t for t in body.get("tools") or [] if t in catalog.TOOLS]
                        hub._save(hub.settings)
                    return self._json({"ok": True})
                if p == "/api/autostart":
                    try:
                        launcher_mod.set_autostart(bool(body.get("on")))
                        with bus.lock:
                            hub.settings["autostart"] = bool(body.get("on"))
                            hub._save(hub.settings)
                    except OSError as e:
                        return self._json({"ok": False, "message": str(e)}, 500)
                    return self._json({"ok": True})
                if p == "/api/setup":
                    # The guided setup: apply the answers, remember them, open the apps.
                    if body.get("skip"):
                        with bus.lock:
                            hub.settings["setupDone"] = True
                            hub._save(hub.settings)
                        return self._json({"ok": True})
                    plan = setup_mod.plan(body.get("inputs") or [], body.get("look") or {})
                    with bus.lock:
                        hub.settings.update(startTools=plan["tools"], setupDone=True, setupInputs=plan["inputs"])
                        hub._save(hub.settings)
                    prefs = bus.set_prefs(plan["prefs"])
                    opened = hub.launcher.open_many(plan["tools"]) if plan["tools"] else {"message": ""}
                    return self._json({"ok": True, **plan, "prefs": prefs, "message": opened.get("message", "")})
                if p == "/api/quit":
                    hub.quit.set()
                    return self._json({"ok": True})
                if p == "/api/open":
                    tool = str(body.get("tool") or "")
                    if tool not in catalog.TOOLS:
                        return self._json({"ok": False, "message": "Unknown tool."}, 400)
                    return self._json(hub.launcher.open(tool))
                if p == "/api/open-logs":
                    return self._json(hub.launcher.open_folder(applog.log_dir()))
                if p == "/api/install-path":
                    tool = str(body.get("tool") or "")
                    if tool not in catalog.TOOLS:
                        return self._json({"ok": False, "message": "Unknown tool."}, 400)
                    with bus.lock:
                        paths_map = hub.settings.setdefault("installPaths", {})
                        if body.get("path"):
                            paths_map[tool] = str(body["path"])
                        else:
                            paths_map.pop(tool, None)
                        hub._save(hub.settings)
                    found = hub.launcher.find(tool)
                    return self._json({"ok": bool(found), "message": "Found it." if found else "Nothing there."})
                return self._json({"error": "Not found."}, 404)

        return Handler


def running_hub(timeout: float = 0.5) -> dict | None:
    """The link.json of a hub that is running now, or None."""
    info = paths.read_json(paths.link_file())
    if not info or not info.get("port") or not info.get("token"):
        return None
    try:
        with socket.create_connection(("127.0.0.1", int(info["port"])), timeout=timeout):
            return info
    except OSError:
        return None
