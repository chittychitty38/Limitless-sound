"""Decides, for every key pressed anywhere, whether it is one of your shortcuts.

This runs on the keyboard thread inside the system's key handler, so it only
looks things up and hands the work to another thread: macOS switches off a key
handler that takes too long.
"""

import threading
import time

from .keys import Combo

REPEAT_GAP = 0.09   # fastest a held shortcut repeats, in seconds


class KeyEngine:
    def __init__(self, profiles, run, clock=time.monotonic):
        """run(binding, phase, app_id, pid) is called for each shortcut to do;
        phase is "down", "repeat", or "up" (only for hold shortcuts)."""
        self.profiles = profiles
        self.run = run
        self.clock = clock
        self.enabled = True
        self.capture = None          # callback waiting for the next shortcut pressed
        self._held = {}              # key -> binding, for keys whose press we kept from the app
        self._last = {}
        self._lock = threading.Lock()

    def capture_next(self, callback):
        """The next shortcut pressed goes to callback(Combo) instead of doing anything."""
        self.capture = callback

    def handle(self, mods, key, is_down, is_repeat, app_id, pid=None):
        """Returns True if the key should be kept from the app in front."""
        if key is None:
            return False
        with self._lock:
            if not is_down:
                b = self._held.pop(key, None)
                if b is None:
                    return False
                if b is not True and b.hold:
                    self.run(b, "up", app_id, pid)
                return True

            if self.capture is not None and not is_repeat:
                cb, self.capture = self.capture, None
                self._held[key] = True
                cb(Combo(frozenset(mods), key))
                return True

            if is_repeat:
                b = self._held.get(key)
                if b is None:
                    return False
                if b is not True and b.repeat:
                    now = self.clock()
                    if now - self._last.get(key, 0) >= REPEAT_GAP:
                        self._last[key] = now
                        self.run(b, "repeat", app_id, pid)
                return True

            b = self.profiles.find(app_id, Combo(frozenset(mods), key))
            if b is None or b.passes:
                return False
            if not self.enabled and b.action.get("app") != "pause":
                return False
            self._held[key] = b
            self._last[key] = self.clock()
            self.run(b, "down", app_id, pid)
            return True

    def release_all(self):
        """Forget held keys, e.g. after the keyboard listener restarts."""
        with self._lock:
            self._held.clear()
