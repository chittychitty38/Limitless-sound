"""A pretend platform that records what it would do. Used by tests and --dry-run."""

from .base import AppRef, NotSupported
from ..keys import for_platform, parse_chord


class DryRunPlatform:
    def __init__(self, os_name="mac", echo=False, app=None):
        self.os_name = os_name
        self.echo = echo
        self.app = AppRef(app) if app else None
        self.log = []

    def _record(self, *entry):
        self.log.append(entry)
        if self.echo:
            print("  [would " + " ".join(str(e) for e in entry) + "]")

    def resolve_chord(self, chord, literal=False):
        mods, key = parse_chord(chord)
        return for_platform(mods, self.os_name, literal), key

    def press(self, chord, literal=False):
        mods, key = self.resolve_chord(chord, literal)
        self._record("press", "+".join(mods + [key]))

    def type_text(self, text):
        self._record("type", text)

    def frontmost(self):
        return self.app

    def focus(self, app):
        self._record("focus", app.name)
        return True

    def open_app(self, name):
        self._record("open", name)

    def applescript(self, script):
        if self.os_name != "mac":
            raise NotSupported("AppleScript only works on a Mac")
        self._record("applescript", script)

    def shell(self, cmd):
        self._record("shell", cmd)

    def wait(self, seconds):
        self._record("wait", seconds)

    def permission_problems(self):
        return []

    def open_settings(self, link):
        self._record("open settings", link)
