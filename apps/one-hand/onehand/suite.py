"""Joining the Limitless Sound suite.

With the Limitless Sound hub running, any other app can switch one-hand mode
(a controller button, a voice command, a glance in GazeStage), and One-Hand can
press DAW commands for them: when GazeStage asks for "Record", the layout for the
app in front knows the keys. Without the hub, none of this does anything.
"""

from .engine import Tap
from .keys import MOD_TO_KEY
from .limitless_link import Link

VERSION = "0.1.0"

# Shared DAW intents -> the command label in layouts.json that does that job.
INTENT_LABELS = {
    "daw.record": "Record",
    "daw.undo": "Undo",
    "daw.redo": "Redo",
    "daw.start": "Go to start",
    "daw.save": "Save",
    "daw.mute": "Mute track",
    "daw.solo": "Solo track",
    "daw.metronome": "Metronome on/off",
    "daw.zoomIn": "Zoom in",
    "daw.zoomOut": "Zoom out",
    "daw.zoomFit": "Zoom to fit",
    "daw.mixer": "Mixer",
}

ACTIONS = [
    {"id": "on", "label": "One-hand mode on"},
    {"id": "off", "label": "One-hand mode off"},
    {"id": "toggle", "label": "One-hand mode on or off"},
    {"id": "left", "label": "Left-hand layout"},
    {"id": "right", "label": "Right-hand layout"},
] + [{"id": intent.split(".")[1], "label": label, "intent": intent} for intent, label in INTENT_LABELS.items()]


class Suite:
    def __init__(self, engine, backend, set_hand, dispatch=None):
        self.engine = engine
        self.backend = backend
        self.set_hand = set_hand
        self.link = Link("onehand", "Limitless One-Hand", VERSION, actions=ACTIONS,
                         on_invoke=self.invoke, dispatch=dispatch, subscribe=["daw.*", "zoom.keys"])

    def start(self):
        self.link.start()
        return self

    def stop(self):
        self.link.stop()

    def invoke(self, action, args, source):
        if action in ("on", "off", "toggle"):
            self.engine.set_enabled(not self.engine.enabled if action == "toggle" else action == "on")
            return True, "One-hand mode " + ("on" if self.engine.enabled else "off")
        if action in ("left", "right"):
            self.set_hand(action)
            self.link.state("hand", action)
            return True, f"{action.title()}-hand layout"
        intent = f"daw.{action}"
        if intent in INTENT_LABELS:
            return self.press(intent)
        return False, f"One-Hand has no action {action!r}."

    def press(self, intent):
        """Press the keys for an intent in the app in front, using its one-hand layout."""
        app = self.engine.profile_for(self.backend.front_app())
        if not app:
            return False, "No app One-Hand knows is in front."
        label = INTENT_LABELS[intent].lower()
        cmd = next((c for c in app["commands"] if c["label"].lower() == label), None)
        if not cmd:
            return False, f"{app['name']} has no {INTENT_LABELS[intent]} in the one-hand layout."
        send = getattr(self.backend, "send", None)
        if send is None:
            return False, "This computer can't press keys."
        names = MOD_TO_KEY[self.engine.platform]
        send(Tap(cmd["send"], tuple(names[m] for m in cmd.get("mods", []))))
        self.link.did(intent.split(".")[1], intent)
        return True, f"{INTENT_LABELS[intent]} in {app['name']}"

    def mode_changed(self, on):
        self.link.state("mode", bool(on))

    def say(self, text):
        """True when the suite's one voice said it."""
        return self.link.say(text)
