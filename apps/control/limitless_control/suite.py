"""Joining the Limitless Sound suite.

With the Limitless Sound hub running:
- Any switch can trigger any Limitless Sound app: pick "Screen colors on",
  "Zoom in" or "One-hand mode on" for a button on the settings page.
- Other apps can switch the controller on or off, change layer, and ask it to
  press DAW commands (record, undo, save...) for the app in front. GazeStage
  uses this to reach the keyboard.
- The controller reports what it did, its on/off state, its layer and the app
  in front, so links can react ("while recording, Voice only hears stop").
Without the hub, none of this does anything.
"""

from __future__ import annotations

from . import __version__, profiles
from .limitless_link import Link

# Catalog action ids (per DAW) -> shared DAW intent.
INTENT_FOR_ID = {
    "play": "daw.playStop", "record": "daw.record", "start": "daw.start",
    "undo": "daw.undo", "redo": "daw.redo", "save": "daw.save",
    "mute": "daw.mute", "activate": "daw.mute", "solo": "daw.solo",
    "track_down": "daw.nextTrack", "track_up": "daw.prevTrack",
    "zoom_in": "daw.zoomIn", "zoom_out": "daw.zoomOut", "zoom_fit": "daw.zoomFit",
    "metronome": "daw.metronome", "click": "daw.metronome",
    "mixer": "daw.mixer", "mix_edit": "daw.mixer",
}
DAWS = {"Logic Pro", "Pro Tools", "Ableton Live"}

OWN = [
    {"id": "on", "label": "Controller on"},
    {"id": "off", "label": "Controller off"},
    {"id": "toggle", "label": "Controller on or off"},
    {"id": "layer", "label": "Controller: next layer"},
    {"id": "announce", "label": "Controller: say profile and layer"},
]


def actions() -> list[dict]:
    intents = sorted(set(INTENT_FOR_ID.values()))
    labels = {"daw.playStop": "Play / stop", "daw.nextTrack": "Next track", "daw.prevTrack": "Previous track"}
    out = list(OWN)
    for intent in intents:
        name = intent.split(".")[1]
        label = labels.get(intent) or next(
            (a["label"] for cat in profiles.CATALOG.values() for i, a in cat.items() if INTENT_FOR_ID.get(i) == intent),
            name)
        out.append({"id": name, "label": label, "intent": intent})
    return out


class Suite:
    def __init__(self, app):
        """app: the running App (engine, output, lock, front_app)."""
        self.app = app
        self._sent_state: dict = {}
        self.link = Link("control", "Limitless Control", __version__, actions=actions(),
                         on_invoke=self.invoke, on_connected=self.on_connected, subscribe=["hub.*"])
        engine = app.engine
        engine.on_suite = self.trigger
        engine.on_fired = self.fired
        before = engine.on_change

        def changed():
            before()
            self.report_state()
        engine.on_change = changed

    def start(self) -> "Suite":
        self.link.start()
        return self

    def stop(self) -> None:
        self.link.stop()

    # A switch bound to another app's action
    def trigger(self, action: str) -> None:
        if not self.link.invoke(action, on_result=self._result):
            self.app.log(f"Open Limitless Sound to use “{action}”")

    def _result(self, r: dict) -> None:
        if not r.get("ok"):
            self.app.log(r.get("message") or "That didn't work")

    # Other apps using the controller
    def invoke(self, action: str, args: dict, source: str):
        with self.app.lock:
            e = self.app.engine
            if action in ("on", "off", "toggle"):
                e.set_enabled(not e.enabled if action == "toggle" else action == "on")
                return True, "Controller on" if e.enabled else "Controller off"
            if action in ("layer", "announce"):
                e._run(action, {})
                e.on_change()
                return True, f"Layer {e.layer + 1}" if action == "layer" else "Announced"
            intent = f"daw.{action}"
            if intent in INTENT_FOR_ID.values():
                return self.press(intent)
        return False, f"Limitless Control has no action {action!r}."

    def press(self, intent: str):
        profile = (self.app.engine.profile or {}).get("name") or "Everyday"
        catalog = profiles.CATALOG.get(profile, {})
        found = next(((i, a) for i, a in catalog.items() if INTENT_FOR_ID.get(i) == intent), None)
        if not found:
            return False, f"No {intent.split('.')[1]} key command for {profile}."
        action_id, a = found
        self.app.output.send(a["keys"])
        self.link.did(intent.split(".")[1], intent)
        return True, f"{a['label']} in {profile}"

    # Telling the suite
    def fired(self, action: dict) -> None:
        """After a switch fired an action: report shared DAW commands."""
        intent = INTENT_FOR_ID.get(action.get("id", ""))
        if intent and action.get("keys"):
            self.link.did(intent.split(".")[1], intent)

    def report_state(self) -> None:
        e = self.app.engine
        profile = (e.profile or {}).get("name")
        now = {"enabled": e.enabled, "layer": e.layer + 1, "app.front": self.app.front_app or "",
               "app.daw": profile in DAWS}
        for key, value in now.items():
            if self._sent_state.get(key) != value:
                self._sent_state[key] = value
                self.link.state(key, value)

    def on_connected(self, connected: bool) -> None:
        if connected:
            self._sent_state = {}
            with self.app.lock:
                self.report_state()

    def say(self, text: str) -> bool:
        return self.link.say(text)

    def suite_actions(self) -> list[dict]:
        """Other apps' actions, for the settings page's pick list."""
        return [a for a in self.link.suite_actions
                if a.get("tool") not in ("control",) and not a.get("args")]
