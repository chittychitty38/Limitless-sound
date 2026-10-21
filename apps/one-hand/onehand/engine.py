"""The one-hand remapping engine. Pure logic, no operating system calls.

A platform backend feeds every physical key press and release into
Engine.handle() and does what the returned action says:

  PASS      let the key through untouched
  SUPPRESS  swallow the key
  Tap(...)  swallow the key and type this key (plus modifiers) instead
"""
import threading
from dataclasses import dataclass, field

from .keys import MIRROR, MIRROR_BOTH_WAYS, MOD_TO_KEY, MODIFIER_KEYS, SHIFT_KEYS

PASS = "pass"
SUPPRESS = "suppress"

SHIFT_TAP_MAX = 0.35      # seconds a Shift press can last and still count as a tap
DOUBLE_SHIFT_GAP = 0.5    # seconds allowed between the two Shift taps


@dataclass(frozen=True)
class Tap:
    key: str
    mods: tuple = ()      # modifier keys to hold while typing key, e.g. ("cmd_l",)


@dataclass
class Settings:
    hand: str = "left"
    mirror_typing: bool = True
    double_shift: bool = True
    toggle_keys: tuple = ("f18",)


@dataclass
class Engine:
    layouts: dict
    platform: str                         # "mac" or "windows"
    settings: Settings = field(default_factory=Settings)

    def __post_init__(self):
        self.enabled = False
        self.changes = 0                  # bumps on every on/off switch, for the UI to notice
        self.lock = threading.RLock()
        self._held_mods = set()
        self._consumed = set()            # keys whose press we replaced; swallow their release
        self._space_held = False
        self._space_used = False
        self._shift_down_at = None
        self._shift_dirty = False
        self._last_shift_tap = None

    # ---- on/off -------------------------------------------------------

    def set_enabled(self, value):
        with self.lock:
            value = bool(value)
            if value != self.enabled:
                self.enabled = value
                self.changes += 1
                self._space_held = False

    def toggle(self):
        with self.lock:
            self.set_enabled(not self.enabled)

    # ---- lookups ------------------------------------------------------

    def profile_for(self, app_id):
        """The layout for the app in front, or None if it isn't one we support."""
        if not app_id:
            return None
        app_id = app_id.lower()
        for app in self.layouts["apps"]:
            if app_id in (a.lower() for a in app.get(self.platform, [])):
                return app
        return None

    def layer_key(self, cmd):
        return cmd["key"] if self.settings.hand == "left" else MIRROR[cmd["key"]]

    def layer_for(self, app_id):
        """{physical key: Tap} for the app in front."""
        app = self.profile_for(app_id)
        if not app:
            return {}
        names = MOD_TO_KEY[self.platform]
        return {self.layer_key(c): Tap(c["send"], tuple(names[m] for m in c.get("mods", [])))
                for c in app["commands"]}

    # ---- the main entry point ----------------------------------------

    def handle(self, key, down, now, app_id=None):
        with self.lock:
            if key in MODIFIER_KEYS:
                return self._modifier(key, down, now)
            if down:
                self._shift_dirty = True
            return self._key(key, down, app_id)

    def _modifier(self, key, down, now):
        if down:
            self._held_mods.add(key)
            if key in SHIFT_KEYS and self._shift_down_at is None:
                self._shift_down_at = now
                self._shift_dirty = len(self._held_mods) > 1
        else:
            self._held_mods.discard(key)
            if key in SHIFT_KEYS and self._shift_down_at is not None:
                tapped = not self._shift_dirty and now - self._shift_down_at <= SHIFT_TAP_MAX
                self._shift_down_at = None
                if tapped and self.settings.double_shift:
                    if self._last_shift_tap is not None and now - self._last_shift_tap <= DOUBLE_SHIFT_GAP:
                        self._last_shift_tap = None
                        self.toggle()
                    else:
                        self._last_shift_tap = now
                elif not tapped:
                    self._last_shift_tap = None
        return PASS

    def _key(self, key, down, app_id):
        if not down and key in self._consumed:
            self._consumed.discard(key)
            return SUPPRESS

        if key in self.settings.toggle_keys:
            if down:
                self._last_shift_tap = None
                self.toggle()
                self._consumed.add(key)
            return SUPPRESS

        if not self.enabled:
            return PASS

        if self.settings.mirror_typing and key == "spacebar":
            return self._space(down)

        if not down:
            return PASS

        self._last_shift_tap = None

        if self._space_held and key in MIRROR_BOTH_WAYS:
            self._space_used = True
            self._consumed.add(key)
            return Tap(MIRROR_BOTH_WAYS[key])   # held Shift still applies, for capitals

        if self._held_mods:
            return PASS                          # let real shortcuts like Cmd+S through

        tap = self.layer_for(app_id).get(key)
        if tap:
            self._consumed.add(key)
            return tap
        return PASS

    def _space(self, down):
        if down:
            if self._held_mods and not self._space_held:
                return PASS                      # e.g. Cmd+Space stays Cmd+Space
            if not self._space_held:
                self._space_held = True
                self._space_used = False
            return SUPPRESS                      # also swallows auto-repeat
        if not self._space_held:
            return PASS
        self._space_held = False
        return SUPPRESS if self._space_used else Tap("spacebar")

    @property
    def held_mods(self):
        with self.lock:
            return set(self._held_mods)
