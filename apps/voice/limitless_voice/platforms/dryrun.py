"""A pretend platform that records what it would do. Used by tests and --dry-run."""

from .base import AppRef, NotSupported, Platform
from ..keys import for_platform, parse_chord
from ..words import ui


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
            raise NotSupported(ui.text("AppleScript only works on a Mac"))
        self._record("applescript", script)

    def shell(self, cmd):
        self._record("shell", cmd)

    def wait(self, seconds):
        self._record("wait", seconds)

    mic_state = "granted"
    control_state = True

    def mic_permission(self):
        return self.mic_state

    def request_mic_permission(self, done):
        self.mic_state = "granted"
        done(True)

    def control_permission(self):
        return self.control_state

    def request_control_permission(self):
        self._record("ask control permission")

    def mic_settings_link(self):
        return "settings:microphone"

    def control_settings_link(self):
        return "settings:accessibility"

    permission_problems = Platform.permission_problems

    def set_login_item(self, enabled):
        self._record("login item", enabled)

    def open_settings(self, link):
        self._record("open settings", link)
