"""Shared code for real platforms: sending keys and text through pynput."""

import subprocess
import time
from dataclasses import dataclass

from ..keys import for_platform, parse_chord
from ..words import t


@dataclass(frozen=True)
class AppRef:
    """The app in front: a display name plus whatever the OS needs to refocus it."""
    name: str
    handle: object = None


class NotSupported(RuntimeError):
    pass


# pynput Key attribute for each named key that isn't a single character
PYNPUT_NAMES = {
    "return": "enter", "tab": "tab", "space": "space", "delete": "backspace",
    "forwarddelete": "delete", "escape": "esc", "esc": "esc",
    "home": "home", "end": "end", "pageup": "page_up", "pagedown": "page_down",
    "left": "left", "right": "right", "up": "up", "down": "down",
    "volumeup": "media_volume_up", "volumedown": "media_volume_down",
    "mute": "media_volume_mute", "playpause": "media_play_pause",
    "nexttrack": "media_next", "previoustrack": "media_previous",
    **{f"f{i}": f"f{i}" for i in range(1, 21)},
}
PYNPUT_MODIFIERS = {"cmd": "cmd", "win": "cmd", "ctrl": "ctrl", "alt": "alt", "opt": "alt", "shift": "shift"}


class Platform:
    os_name = "generic"
    # virtual key codes for the numeric keypad, filled in per OS
    NUMPAD_VK = {}

    def __init__(self):
        from pynput.keyboard import Controller, Key, KeyCode
        self._kb = Controller()
        self._Key = Key
        self._KeyCode = KeyCode

    # -- keys ----------------------------------------------------------

    def resolve_chord(self, chord, literal=False):
        mods, key = parse_chord(chord)
        return for_platform(mods, self.os_name, literal), key

    def _key_obj(self, key):
        if key in self.NUMPAD_VK:
            return self._KeyCode.from_vk(self.NUMPAD_VK[key])
        if key == "enter" or key == "numpadenter":
            return self._Key.enter
        if key in PYNPUT_NAMES:
            return getattr(self._Key, PYNPUT_NAMES[key])
        if key.startswith("numpad"):
            # numpad key this OS has no code for: fall back to the plain character
            return self._KeyCode.from_char(key[len("numpad"):] or "=")
        return self._KeyCode.from_char(key)

    def press(self, chord, literal=False):
        mods, key = self.resolve_chord(chord, literal)
        mod_objs = [getattr(self._Key, PYNPUT_MODIFIERS[m]) for m in mods]
        for m in mod_objs:
            self._kb.press(m)
        try:
            k = self._key_obj(key)
            self._kb.press(k)
            self._kb.release(k)
        finally:
            for m in reversed(mod_objs):
                self._kb.release(m)

    def type_text(self, text):
        self._kb.type(text)

    # -- apps ----------------------------------------------------------

    def frontmost(self):
        return None

    def focus(self, app):
        """Bring a previously seen app back to the front. Best effort."""
        return False

    def open_app(self, name):
        raise NotSupported(t("opening apps isn't supported here"))   # shown as "That didn't work: ..."

    # -- misc ----------------------------------------------------------

    def applescript(self, script):
        raise NotSupported(t("AppleScript only works on a Mac"))

    def shell(self, cmd):
        subprocess.run(cmd, shell=True, check=True)

    def wait(self, seconds):
        time.sleep(seconds)

    # -- permissions -----------------------------------------------------
    # Mac asks before an app may use the microphone or press keys in other
    # apps. Other systems don't, so the defaults say "granted".

    def mic_permission(self):
        """"granted", "denied" or "ask" (never asked yet)."""
        return "granted"

    def request_mic_permission(self, done):
        """Show the system's microphone prompt; done(granted) is called on any thread."""
        done(True)

    def control_permission(self):
        """True when we're allowed to press keys in other apps."""
        return True

    def request_control_permission(self):
        """Show the system's prompt for controlling the computer, if there is one."""

    def mic_settings_link(self):
        return None

    def control_settings_link(self):
        return None

    def permission_problems(self):
        """Things the user must allow before we can work, as (title, how-to, settings link),
        in the language Voice shows (words.t)."""
        problems = []
        if self.mic_permission() == "denied":
            problems.append((
                t("Allow Limitless Voice to use the microphone"),
                t("Open Microphone settings, turn on Limitless Voice, then come back."),
                self.mic_settings_link(),
            ))
        if not self.control_permission():
            problems.append((
                t("Allow Limitless Voice to control the computer"),
                t("Open Accessibility settings, turn on Limitless Voice, then come back. "
                  "This is what lets spoken commands press keys in Logic and Pro Tools."),
                self.control_settings_link(),
            ))
        return problems

    def open_settings(self, link):
        pass

    def set_login_item(self, enabled):
        """Start (or stop starting) this app when the user logs in."""
