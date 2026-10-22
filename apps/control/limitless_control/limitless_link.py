"""Limitless Link: connect a Python tool to the Limitless Sound hub.

Drop this one file into a tool. It only uses the standard library, runs on its
own thread, reconnects by itself, and does nothing at all when the hub isn't
installed or running, so a tool behaves exactly as before on its own.

    link = Link("zoom", "Limitless Zoom", "0.3.0",
                actions=[{"id": "in", "label": "Zoom in", "intent": "daw.zoomIn"}],
                on_invoke=lambda action, args, source: zoom.run(action),
                dispatch=run_on_main_thread)        # optional, e.g. for Qt
    link.start()
    link.did("in")                 # after doing something, from any input
    link.state("keys", True)       # when a state the suite cares about changes
    if not link.say("Zoom in"):    # the hub speaks for the whole suite...
        speak_myself("Zoom in")    # ...or the tool speaks as it always did
    link.invoke("daw.record")      # ask whichever tool can, to press Record

Protocol: PROTOCOL.md next to this file in the suite repository.
"""

from __future__ import annotations

import itertools
import json
import os
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Callable, Optional

__all__ = ["Link", "config_dir", "launch_hub"]
PROTOCOL = 1


def config_dir() -> Path:
    override = os.environ.get("LIMITLESS_SOUND_HOME")
    if override:
        return Path(override)
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "Limitless Sound"
    if sys.platform.startswith("win"):
        return Path(os.environ.get("APPDATA") or Path.home() / "AppData" / "Roaming") / "Limitless Sound"
    return Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config") / "Limitless Sound"


def hub_app() -> Optional[Path]:
    """The installed Limitless Sound hub, if there is one."""
    if sys.platform == "darwin":
        for root in (Path("/Applications"), Path.home() / "Applications"):
            if (root / "Limitless Sound.app").exists():
                return root / "Limitless Sound.app"
    elif sys.platform.startswith("win"):
        base = os.environ.get("LOCALAPPDATA")
        if base and (Path(base) / "Programs" / "Limitless Sound" / "Limitless Sound.exe").exists():
            return Path(base) / "Programs" / "Limitless Sound" / "Limitless Sound.exe"
    return None


def launch_hub() -> bool:
    """Start the installed hub in the background. True if it was found."""
    app = hub_app()
    if app is None:
        return False
    try:
        if sys.platform == "darwin":
            subprocess.Popen(["open", "-g", "-j", str(app), "--args", "--background"],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        else:
            flags = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(subprocess, "CREATE_NO_WINDOW", 0)
            subprocess.Popen([str(app), "--background"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                             close_fds=True, creationflags=flags)
        return True
    except OSError:
        return False


class Link:
    def __init__(self, tool: str, name: str, version: str = "", *, actions: list[dict] | None = None,
                 on_invoke: Optional[Callable[[str, dict, str], object]] = None,
                 on_event: Optional[Callable[[str, object, str], None]] = None,
                 on_prefs: Optional[Callable[[dict], None]] = None,
                 on_actions: Optional[Callable[[list[dict]], None]] = None,
                 on_connected: Optional[Callable[[bool], None]] = None,
                 dispatch: Optional[Callable[[Callable[[], None]], None]] = None,
                 subscribe: list[str] | None = None, retry: float = 2.0, start_hub: bool = True):
        self.tool, self.name, self.version = tool, name, version
        self._actions = list(actions or [])
        self.on_invoke, self.on_event, self.on_prefs = on_invoke, on_event, on_prefs
        self.on_actions, self.on_connected = on_actions, on_connected
        self.dispatch = dispatch or (lambda fn: fn())
        self.subscribe = subscribe or ["*"]
        self.retry = retry
        self.start_hub = start_hub   # open the installed hub once if it isn't running
        self._tried_hub = False
        self.connected = False
        self.prefs: dict = {}
        self.suite_actions: list[dict] = []
        self.states: dict = {}
        self._sock: Optional[socket.socket] = None
        self._send_lock = threading.Lock()
        self._stop = threading.Event()
        self._ids = itertools.count(1)
        self._waiting: dict[int, Callable[[dict], None]] = {}
        self._local = threading.local()
        self._thread: Optional[threading.Thread] = None

    # ------------------------------------------------------------------ public

    def start(self) -> "Link":
        if self._thread is None:
            self._thread = threading.Thread(target=self._run, daemon=True, name=f"limitless-link-{self.tool}")
            self._thread.start()
        return self

    def stop(self) -> None:
        self._stop.set()
        self._close()

    def set_actions(self, actions: list[dict]) -> None:
        self._actions = list(actions)
        self._send({"op": "actions", "actions": self._actions})

    def did(self, action: str, intent: str | None = None, value=None) -> None:
        msg = {"op": "did", "action": action, "depth": self._depth()}
        if intent:
            msg["intent"] = intent
        if value is not None:
            msg["value"] = value
        self._send(msg)

    def state(self, key: str, value) -> None:
        self._send({"op": "state", "key": key, "value": value, "depth": self._depth()})

    def say(self, text: str) -> bool:
        """Speak through the hub. False means the tool should speak for itself."""
        if not (self.connected and self.prefs.get("oneVoice", True)):
            return False
        return self._send({"op": "say", "text": text})

    def invoke(self, action: str, args: dict | None = None,
               on_result: Optional[Callable[[dict], None]] = None) -> bool:
        """Run any action in the suite. False when the hub isn't there."""
        rid = next(self._ids)
        if on_result:
            self._waiting[rid] = on_result
        ok = self._send({"op": "invoke", "id": rid, "action": action, "args": args or {}, "depth": self._depth()})
        if not ok:
            self._waiting.pop(rid, None)
        return ok

    # ------------------------------------------------------------------ inside

    def _depth(self) -> int:
        return getattr(self._local, "depth", 0)

    def _send(self, msg: dict) -> bool:
        sock = self._sock
        if sock is None or not self.connected and msg.get("op") != "hello":
            return False
        data = (json.dumps(msg, separators=(",", ":")) + "\n").encode()
        try:
            with self._send_lock:
                sock.sendall(data)
            return True
        except OSError:
            self._close()
            return False

    def _close(self) -> None:
        sock, self._sock = self._sock, None
        was = self.connected
        self.connected = False
        if sock is not None:
            try:
                sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            try:
                sock.close()
            except OSError:
                pass
        if was and self.on_connected:
            self.dispatch(lambda: self.on_connected(False))

    def _read_link(self) -> Optional[dict]:
        try:
            info = json.loads((config_dir() / "link.json").read_text())
            return info if isinstance(info, dict) and info.get("port") and info.get("token") else None
        except (OSError, ValueError):
            return None

    def _run(self) -> None:
        while not self._stop.is_set():
            info = self._read_link()
            reached = False
            if info:
                try:
                    self._session(info)
                    reached = True
                except OSError:
                    pass
                self._close()
            if not reached and self.start_hub and not self._tried_hub:
                # Every app brings the suite up with it: open the hub if it's installed.
                self._tried_hub = True
                launch_hub()
            self._stop.wait(self.retry)

    def _session(self, info: dict) -> None:
        sock = socket.create_connection(("127.0.0.1", int(info["port"])), timeout=2)
        sock.settimeout(None)
        try:
            sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        except OSError:
            pass
        self._sock = sock
        self._send({"op": "hello", "protocol": PROTOCOL, "token": info["token"], "tool": self.tool,
                    "name": self.name, "version": self.version, "actions": self._actions,
                    "subscribe": self.subscribe})
        buf = b""
        while not self._stop.is_set():
            chunk = sock.recv(65536)
            if not chunk:
                return
            buf += chunk
            while b"\n" in buf:
                line, buf = buf.split(b"\n", 1)
                try:
                    msg = json.loads(line)
                except ValueError:
                    continue
                if isinstance(msg, dict):
                    self._handle(msg)

    def _handle(self, msg: dict) -> None:
        op = msg.get("op")
        if op == "welcome":
            self.connected = True
            self.prefs = msg.get("prefs") or {}
            self.suite_actions = msg.get("actions") or []
            self.states = msg.get("states") or {}
            if self.on_connected:
                self.dispatch(lambda: self.on_connected(True))
            if self.on_prefs:
                prefs = dict(self.prefs)
                self.dispatch(lambda: self.on_prefs(prefs))
            if self.on_actions:
                acts = list(self.suite_actions)
                self.dispatch(lambda: self.on_actions(acts))
        elif op == "invoke":
            self.dispatch(lambda: self._run_invoke(msg))
        elif op == "event":
            name, value = msg.get("name"), msg.get("value")
            self.states[name] = value
            if self.on_event:
                self.dispatch(lambda: self.on_event(name, value, msg.get("source", "")))
        elif op == "prefs":
            self.prefs = msg.get("prefs") or {}
            if self.on_prefs:
                prefs = dict(self.prefs)
                self.dispatch(lambda: self.on_prefs(prefs))
        elif op == "actions":
            self.suite_actions = msg.get("actions") or []
            if self.on_actions:
                acts = list(self.suite_actions)
                self.dispatch(lambda: self.on_actions(acts))
        elif op == "result":
            cb = self._waiting.pop(msg.get("id"), None)
            if cb:
                self.dispatch(lambda: cb(msg))
        elif op == "error" and msg.get("code") == "replaced":
            # A newer copy of this app took over: step aside for good instead of fighting it.
            self._stop.set()
            self._close()
        elif op == "error" and not self.connected:
            self._close()

    def _run_invoke(self, msg: dict) -> None:
        self._local.depth = int(msg.get("depth") or 0)
        ok, message = True, ""
        try:
            result = self.on_invoke(msg.get("action", ""), msg.get("args") or {}, msg.get("source", "")) \
                if self.on_invoke else (False, "This tool takes no actions.")
            if isinstance(result, tuple):
                ok, message = bool(result[0]), str(result[1] if len(result) > 1 else "")
            elif isinstance(result, bool):
                ok = result
            elif isinstance(result, str):
                message = result
        except Exception as e:  # a bad action must never take the tool down
            ok, message = False, f"{type(e).__name__}: {e}"
        finally:
            self._local.depth = 0
        self._send({"op": "result", "id": msg.get("id"), "ok": ok, "message": message})
