"""Sidechain links: when something happens in one tool, another tool reacts.

Like a sidechain on a compressor, one signal shapes another. A link is
  {"id", "name", "when": {"event": "daw.record", "value": ...}, "do": [{"action", "args"}], "on": bool}
"event" may end in ".*" to match a family ("control.*"). "value" is optional;
when it is given the event's value has to equal it.
"""

from __future__ import annotations

import time
from fnmatch import fnmatchcase

DEFAULT_ROUTES = [
    {
        "id": "take-guard",
        "name": "While recording, Limitless Voice only listens for stop and wake words, so singing or talking in a take can't trigger commands.",
        "when": {"event": "daw.record"},
        "do": [{"action": "voice.takeGuard"}],
        "on": True,
    },
    {
        "id": "take-guard-off",
        "name": "When the take stops, Limitless Voice goes back to hearing every command.",
        "when": {"event": "daw.stop"},
        "do": [{"action": "voice.takeGuardOff"}],
        "on": True,
    },
    {
        "id": "take-guard-off-playstop",
        "name": "Play/stop after a take also ends take mode.",
        "when": {"event": "daw.playStop"},
        "do": [{"action": "voice.takeGuardOff"}],
        "on": True,
    },
    {
        "id": "keys-dont-fight",
        "name": "When one-hand mode turns on, the zoom keys layer turns off, so the two never fight over the same keys.",
        "when": {"event": "onehand.mode", "value": True},
        "do": [{"action": "zoom.keysOff"}],
        "on": True,
    },
    {
        "id": "keys-dont-fight-2",
        "name": "When the zoom keys layer turns on, one-hand mode turns off.",
        "when": {"event": "zoom.keys", "value": True},
        "do": [{"action": "onehand.off"}],
        "on": True,
    },
    {
        "id": "rest-voice-with-controller",
        "name": "When the controller is switched off to rest, Limitless Voice stops listening too.",
        "when": {"event": "control.enabled", "value": False},
        "do": [{"action": "voice.sleep"}],
        "on": False,
    },
    {
        "id": "colors-follow-daw",
        "name": "Screen colors turn on whenever a DAW comes to the front.",
        "when": {"event": "app.daw", "value": True},
        "do": [{"action": "color.on"}],
        "on": False,
    },
]

# A link that fires this often in this many seconds is feeding itself; it gets paused.
RUNAWAY_COUNT = 8
RUNAWAY_WINDOW = 2.0


def matches(route: dict, event: str, value) -> bool:
    if not route.get("on", True):
        return False
    when = route.get("when") or {}
    pattern = when.get("event")
    if not pattern or not fnmatchcase(event, pattern):
        return False
    if "value" in when and when["value"] != value:
        return False
    return True


def validate(route: dict, known_actions: set[str] | None = None) -> list[str]:
    problems = []
    if not isinstance(route, dict):
        return ["A link must be an object."]
    if not str(route.get("id") or "").strip():
        problems.append("A link needs an id.")
    when = route.get("when")
    if not isinstance(when, dict) or not str(when.get("event") or "").strip():
        problems.append("A link needs a 'when' event.")
    do = route.get("do")
    if not isinstance(do, list) or not do:
        problems.append("A link needs at least one action to do.")
    else:
        for step in do:
            if not isinstance(step, dict) or not str(step.get("action") or "").count("."):
                problems.append("Each step needs an action like 'zoom.in'.")
            elif known_actions is not None and step["action"] not in known_actions:
                problems.append(f"Unknown action '{step['action']}'.")
    return problems


class RunawayGuard:
    """Pauses a link that keeps re-triggering itself (A makes B, B makes A...)."""

    def __init__(self, clock=time.monotonic):
        self.clock = clock
        self.fired: dict[str, list[float]] = {}

    def allow(self, route_id: str) -> bool:
        now = self.clock()
        times = [t for t in self.fired.get(route_id, []) if now - t < RUNAWAY_WINDOW]
        times.append(now)
        self.fired[route_id] = times
        return len(times) <= RUNAWAY_COUNT
