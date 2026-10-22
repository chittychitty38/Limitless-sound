"""Turns an action name into the key combos to press, for whatever app is in front."""

from .actions import LABELS, ZOOM_ACTIONS
from .keymaps import TARGETS, find_target, keys_for
from .keys import parse_combo


class Plan:
    def __init__(self, action, target, combos, message, ok=True):
        self.action, self.target, self.combos = action, target, combos
        self.message, self.ok = message, ok

    def __repr__(self):
        return f"Plan({self.action!r}, {self.target!r}, {self.combos!r}, ok={self.ok})"


class Router:
    def __init__(self, os_name, big_steps=3, overrides=None):
        self.os_name = os_name
        self.big_steps = big_steps
        self.overrides = overrides or {}
        self.magnifier_on = False  # only tracked where the OS has no toggle key

    def plan(self, action, app_id):
        if action not in ZOOM_ACTIONS:
            return Plan(action, None, [], f"Unknown action {action}", ok=False)

        target = find_target(app_id)
        base, steps = action, 1
        if action == "bigIn":
            base, steps = "in", self.big_steps
        elif action == "bigOut":
            base, steps = "out", self.big_steps

        keys = keys_for(target, self.os_name, self.overrides)
        mag = keys_for("magnifier", self.os_name, self.overrides)

        combo = keys.get(base)
        used = target
        if combo is None and (base.startswith("mag") or base in ("in", "out")):
            # Outside a known DAW, zoom in/out drives the screen magnifier,
            # so the same command does something useful everywhere.
            mag_action = {"in": "magIn", "out": "magOut"}.get(base, base)
            combo = self._magnifier_combo(mag_action, mag)
            used = "magnifier"

        label = LABELS[action]
        if combo is None:
            name = TARGETS[target]["name"]
            return Plan(action, target, [], f"{label} isn't available in {name}", ok=False)

        if used == "magnifier" and base in ("in", "out", "magIn"):
            self.magnifier_on = True
        combos = [parse_combo(combo)] * steps
        return Plan(action, used, combos, label)

    def _magnifier_combo(self, action, mag):
        if action == "magToggle" and "magToggle" not in mag:
            # Windows has separate start and stop keys, so remember the state.
            combo = mag.get("magOff") if self.magnifier_on else mag.get("magOn")
            self.magnifier_on = not self.magnifier_on
            return combo
        if action == "magOut" and self.os_name == "win" and not self.magnifier_on:
            return None
        return mag.get(action)
