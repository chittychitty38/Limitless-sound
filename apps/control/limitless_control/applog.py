"""A log file for a Limitless Sound app, so a problem can be found after the fact.

  Mac      ~/Library/Logs/Limitless Sound/<App>.log
  Windows  %LOCALAPPDATA%\\Limitless Sound\\Logs\\<App>.log
  Linux    ~/.local/state/Limitless Sound/<App>.log

A packaged app has no console, so without this an error or a crash leaves no trace.
This keeps the newest megabyte (plus one older file), records every Python error that
nothing caught, in any thread, and where the app was if it crashes outright. The log
never leaves the computer; a musician can send it when asking for help.

Copy this file into the app next to limitless_link.py and call start() first thing:

    applog.start("Limitless Zoom", __version__)

Standard library only.
"""

from __future__ import annotations

import faulthandler
import logging
import logging.handlers
import os
import platform
import sys
import threading
from pathlib import Path

__all__ = ["log_dir", "start"]

KEEP_BYTES = 1_000_000
_crash_file = None  # faulthandler writes here; it must stay open


def log_dir() -> Path:
    override = os.environ.get("LIMITLESS_SOUND_LOGS")
    if override:
        return Path(override)
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Logs" / "Limitless Sound"
    if sys.platform.startswith("win"):
        base = os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local"
        return Path(base) / "Limitless Sound" / "Logs"
    return Path(os.environ.get("XDG_STATE_HOME") or Path.home() / ".local" / "state") / "Limitless Sound"


class _ToLog:
    """Stands in for stdout/stderr in a packaged app, so stray prints land in the log."""

    def __init__(self, logger: logging.Logger, level: int):
        self.logger, self.level, self.buf = logger, level, ""

    def write(self, text) -> int:
        self.buf += str(text)
        while "\n" in self.buf:
            line, self.buf = self.buf.split("\n", 1)
            if line.strip():
                self.logger.log(self.level, line.rstrip())
        return len(text)

    def flush(self) -> None:
        pass

    def isatty(self) -> bool:
        return False


def start(app: str, version: str = "") -> Path | None:
    """Start logging for this app. Returns the log file, or None if it can't be written."""
    global _crash_file
    log = logging.getLogger(app)
    try:
        folder = log_dir()
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / f"{app}.log"
        handler = logging.handlers.RotatingFileHandler(path, maxBytes=KEEP_BYTES, backupCount=1, encoding="utf-8")
    except OSError:
        return None
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)-7s %(name)s: %(message)s"))
    root = logging.getLogger()
    root.addHandler(handler)
    if root.level == logging.NOTSET or root.level > logging.INFO:
        root.setLevel(logging.INFO)

    # Where the app was if it crashes outright (a native crash Python can't catch).
    try:
        crash = folder / f"{app} crash.log"
        if crash.exists() and crash.stat().st_size > KEEP_BYTES:
            crash.unlink()
        _crash_file = open(crash, "a", encoding="utf-8")
        faulthandler.enable(_crash_file, all_threads=True)
    except OSError:
        pass

    # Errors nothing caught, on the main thread or any other, still get written down.
    previous = sys.excepthook

    previous_thread = threading.excepthook
    from_source = not getattr(sys, "frozen", False)  # run from source: still show it in the terminal

    def excepthook(kind, value, tb):
        log.critical("Uncaught error", exc_info=(kind, value, tb))
        if from_source:
            previous(kind, value, tb)

    def thread_excepthook(a):
        log.critical("Uncaught error in thread %s", a.thread.name if a.thread else "?",
                     exc_info=(a.exc_type, a.exc_value, a.exc_traceback))
        if from_source:
            previous_thread(a)

    sys.excepthook = excepthook
    threading.excepthook = thread_excepthook

    if getattr(sys, "frozen", False):
        sys.stdout = _ToLog(logging.getLogger(f"{app}.stdout"), logging.INFO)
        sys.stderr = _ToLog(logging.getLogger(f"{app}.stderr"), logging.WARNING)

    log.info("Started %s %s on %s %s (%s), Python %s", app, version, platform.system(),
             platform.mac_ver()[0] or platform.release(), platform.machine(), platform.python_version())
    return path
