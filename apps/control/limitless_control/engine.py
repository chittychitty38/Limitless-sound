"""Turns switch presses and releases into actions.

Applies the timing rules (tremor filter, cooldown, long press, repeat), the layer
switch and the on/off switch. Time is passed in so everything here can be tested
without a controller.
"""

from __future__ import annotations

import fnmatch
from dataclasses import dataclass
from typing import Callable, Optional, Protocol

ON_OFF = "toggleEnabled"


class Output(Protocol):
    def send(self, keys: str) -> None: ...
    def speak(self, text: str) -> None: ...
    def log(self, text: str) -> None: ...


@dataclass
class _Press:
    binding: dict
    start: float
    tap_fired: bool = False
    hold_fired: bool = False
    last_repeat: float = 0.0


def _is_on_off(binding: dict) -> bool:
    return any((binding.get(k) or {}).get("command") == ON_OFF for k in ("tap", "hold"))


def find_profile(config: dict, app_id: Optional[str]) -> Optional[dict]:
    """The profile whose `apps` patterns match the app, else the one with "*"."""
    profiles = config.get("profiles", [])
    if app_id:
        app = app_id.lower()
        for profile in profiles:
            for pattern in profile.get("apps", []):
                if pattern != "*" and fnmatch.fnmatch(app, pattern.lower()):
                    return profile
    return next((p for p in profiles if "*" in p.get("apps", [])), None)


class Engine:
    def __init__(self, config: dict, output: Output):
        self.output = output
        self.config = config
        self.profile: Optional[dict] = find_profile(config, None)
        self.layer = 0
        self.enabled = True
        self.on_change: Callable[[], None] = lambda: None
        self.on_suite: Callable[[str], None] = lambda action: None   # another Limitless Sound app's action
        self.on_fired: Callable[[dict], None] = lambda action: None  # after keys were sent
        # Called with (input name, action) each time an action fires, for the live display.
        self.on_fire: Callable[[str, dict], None] = lambda name, action: None
        self._pressed: dict[str, _Press] = {}
        self._last_fired: dict[str, float] = {}

    @property
    def timing(self) -> dict:
        return self.config.get("timing", {})

    def _t(self, key: str, default: float) -> float:
        return float(self.timing.get(key, default))

    # Profiles

    def reload(self, config: dict, app_id: Optional[str]) -> None:
        self.config = config
        self._pressed.clear()
        self.profile = None
        self.app_changed(app_id)

    def app_changed(self, app_id: Optional[str]) -> None:
        nxt = find_profile(self.config, app_id)
        if nxt is self.profile or (nxt and self.profile and nxt.get("name") == self.profile.get("name")):
            return
        self.profile = nxt
        self.layer = 0
        if nxt:
            self._say(nxt.get("name", ""))
        self.on_change()

    # Switch input

    def press(self, name: str, now: float) -> None:
        if name in self._pressed:
            return
        last = self._last_fired.get(name)
        if last is not None and now - last < self._t("cooldownSeconds", 0.15):
            return
        binding = self.binding_for(name)
        if not binding:
            return
        # While switched off, only the on/off switch itself responds.
        if not self.enabled and not _is_on_off(binding):
            return
        self._pressed[name] = _Press(binding, now)
        self.tick(now)

    def release(self, name: str, now: float) -> None:
        press = self._pressed.pop(name, None)
        if press is None:
            return
        held = now - press.start
        # A switch with a hold action decides tap vs hold on release.
        b = press.binding
        if b.get("hold") and not press.hold_fired and held >= self._t("minPressSeconds", 0.05) and b.get("tap"):
            self._fire(b["tap"], name, now)

    @property
    def busy(self) -> bool:
        """A switch is held down, so tick() has long presses or repeats to time."""
        return bool(self._pressed)

    def tick(self, now: float) -> None:
        """Call every 10 to 20 ms so long presses and repeats fire while a switch is held."""
        min_press = self._t("minPressSeconds", 0.05)
        for name, press in list(self._pressed.items()):
            held = now - press.start
            b = press.binding
            if b.get("hold"):
                if not press.hold_fired and held >= self._t("longPressSeconds", 0.8):
                    press.hold_fired = True
                    self._fire(b["hold"], name, now)
            elif b.get("tap"):
                if not press.tap_fired and held >= min_press:
                    press.tap_fired = True
                    press.last_repeat = now
                    self._fire(b["tap"], name, now)
                elif (press.tap_fired and b.get("repeats")
                      and held >= min_press + self._t("repeatDelaySeconds", 0.5)
                      and now - press.last_repeat >= self._t("repeatIntervalSeconds", 0.12)):
                    press.last_repeat = now
                    # Repeats stay quiet so speech does not pile up.
                    quiet = {k: v for k, v in b["tap"].items() if k != "say"}
                    self._fire(quiet, name, now)

    def binding_for(self, name: str) -> Optional[dict]:
        glob = self.config.get("global", {})
        if name in glob:
            return glob[name]
        layers = (self.profile or {}).get("layers", [])
        if self.layer < len(layers):
            return layers[self.layer].get(name)
        return None

    # Actions

    def _fire(self, action: dict, name: str, now: float) -> None:
        self._last_fired[name] = now
        command = action.get("command")
        if command:
            self._run(command, action)
            self.on_fire(name, action)
            # Another app's action counts as the one action a one-shot layer allows.
            if command == "suite" and self.enabled and self.layer != 0 \
                    and self.config.get("layerMode", "oneShot") == "oneShot":
                self.layer = 0
            self.on_change()
            return
        if not self.enabled:
            return
        self.on_fire(name, action)
        keys = action.get("keys")
        if keys:
            self.output.send(keys)
            self.on_fired(action)
        if action.get("say"):
            self._say(action["say"])
        # A one-shot layer drops back after one action, like Sticky Keys.
        if self.layer != 0 and self.config.get("layerMode", "oneShot") == "oneShot":
            self.layer = 0
            self.on_change()

    def _run(self, command: str, action: dict) -> None:
        if command == "layer":
            count = len((self.profile or {}).get("layers", [])) or 1
            self.layer = (self.layer + 1) % count if count > 1 else 0
            self._say(action.get("say") or ("Layer one" if self.layer == 0 else f"Layer {self.layer + 1}"))
        elif command == ON_OFF:
            self.enabled = not self.enabled
            self.layer = 0
            # Drop other held switches so nothing fires after switching off.
            self._pressed = {k: p for k, p in self._pressed.items() if _is_on_off(p.binding)}
            self._say("Controller on" if self.enabled else "Controller off")
        elif command == "suite":
            if self.enabled:
                self.on_suite(action.get("suite", ""))
                if action.get("say"):
                    self._say(action["say"])
        elif command == "announce":
            if self.profile:
                self._say(f"{self.profile.get('name', '')}, layer {self.layer + 1}")
            else:
                self._say("No profile")
        else:
            self.output.log(f'Unknown command "{command}"')

    def set_enabled(self, enabled: bool) -> None:
        if enabled != self.enabled:
            self._run(ON_OFF, {})
            self.on_change()

    def _say(self, text: str) -> None:
        if text and self.config.get("speak", True):
            self.output.speak(text)
