"""Command line.

  Limitless Sound                      start the hub (or show its page if it's running)
  Limitless Sound --background         start without opening the page (used at sign-in)
  Limitless Sound do zoom.in           run any action in the suite, then exit
  Limitless Sound do voice.do phrase="solo track"
  Limitless Sound do daw.record        whichever open tool can press Record does it
  Limitless Sound list                 every action
  Limitless Sound status               which tools are connected
"""

from __future__ import annotations

import argparse
import json
import signal
import sys
import threading
import urllib.error
import urllib.request
import webbrowser

from . import catalog, paths
from .launcher import Launcher
from .server import Hub, running_hub


def _call(info: dict, method: str, path: str, body: dict | None = None) -> dict:
    req = urllib.request.Request(
        f"http://127.0.0.1:{info['http']}{path}", method=method,
        data=json.dumps(body).encode() if body is not None else None,
        headers={"X-Limitless-Token": info["token"], "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            return json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        try:
            return json.loads(e.read() or b"{}")
        except ValueError:
            return {"ok": False, "message": str(e)}


def _parse_args(pairs: list[str]) -> dict:
    out = {}
    for p in pairs:
        k, sep, v = p.partition("=")
        if sep:
            out[k] = v
        elif "phrase" not in out:
            out["phrase"] = p
        else:
            out["phrase"] += " " + p
    return out


def do(action: str, args: dict) -> int:
    info = running_hub()
    if info:
        r = _call(info, "POST", "/api/invoke", {"action": action, "args": args})
    else:
        # No hub: still reach tools that have their own command line.
        tool, _, act = action.partition(".")
        if tool not in catalog.TOOLS:
            print("Limitless Sound isn't running, so only zoom.* and voice.do work without it.")
            return 1
        settings = paths.read_json(paths.settings_file()) or {}
        ok, msg = Launcher(settings).run_cli(tool, act, args)
        r = {"ok": ok, "message": msg or ("Done" if ok else f"Open {catalog.TOOLS[tool]['name']} or Limitless Sound first.")}
    print(r.get("message") or ("Done" if r.get("ok") else "Failed"))
    return 0 if r.get("ok") else 1


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    argv = [a for a in argv if not a.startswith("-psn")]  # macOS Finder adds this
    p = argparse.ArgumentParser(prog="limitless-sound", description="Limitless Sound hub")
    p.add_argument("command", nargs="?", choices=["run", "do", "list", "status", "say"], default="run")
    p.add_argument("rest", nargs="*")
    p.add_argument("--background", action="store_true", help="don't open the settings page")
    p.add_argument("--port", type=int, default=paths.DEFAULT_PORT)
    p.add_argument("--http-port", type=int, default=paths.DEFAULT_HTTP_PORT)
    a = p.parse_args(argv)

    if a.command == "do":
        if not a.rest:
            print("Which action? For example: do zoom.in")
            return 2
        return do(a.rest[0], _parse_args(a.rest[1:]))
    if a.command == "say":
        return do("hub.say", {"text": " ".join(a.rest)})
    if a.command in ("list", "status"):
        info = running_hub()
        if not info:
            if a.command == "status":
                print("Limitless Sound isn't running.")
                return 1
            for tool, spec in catalog.TOOLS.items():
                for act in spec["actions"]:
                    print(f"{tool}.{act['id']:<14} {act['label']}")
            for intent, label in catalog.INTENTS.items():
                print(f"{intent:<20} {label}")
            return 0
        state = _call(info, "GET", "/api/state")
        if a.command == "status":
            for t in state.get("tools", []):
                print(f"{t['name']:<20} {'connected' if t['connected'] else 'installed' if t['installed'] else 'not installed'}")
        else:
            for act in state.get("actions", []):
                print(f"{act['id']:<22} {act['label']}{'' if act.get('live') else '  (closed)'}")
        return 0

    other = running_hub()
    if other:
        if not a.background:
            webbrowser.open(f"http://127.0.0.1:{other['http']}/?t={other['token']}")
        return 0
    hub = Hub(port=a.port, http_port=a.http_port).start()
    print(f"Limitless Sound is running. Settings: {hub.page_url()}")
    start_tools = hub.settings.get("startTools") or []
    if start_tools:
        hub.launcher.open_many([t for t in start_tools if t in catalog.TOOLS])
    if not a.background:
        webbrowser.open(hub.page_url())
    stop = threading.Event()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            signal.signal(sig, lambda *_: stop.set())
        except (ValueError, OSError):
            pass
    try:
        while not stop.wait(1):
            pass
    finally:
        hub.stop()
    return 0
