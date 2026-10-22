"""Joining the Limitless Sound suite.

With the Limitless Sound hub running, any other app can switch one-hand mode
(a controller button, a voice command, a glance in GazeStage), and One-Hand can
press DAW commands for them: when GazeStage asks for "Record", the layout for the
app in front knows the keys. The suite's shared text size, high contrast and
reduce motion settings reach One-Hand's window and badge too. Without the hub,
none of this does anything.
"""

from .engine import Tap
from .keys import MOD_TO_KEY
from .limitless_link import Link

from . import __version__ as VERSION

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
# Other labels that do the same job in some DAWs.
ALIASES = {"daw.mixer": ["Edit/Mix window"]}

ACTIONS = [
    {"id": "on", "label": "One-hand mode on"},
    {"id": "off", "label": "One-hand mode off"},
    {"id": "toggle", "label": "One-hand mode on or off"},
    {"id": "left", "label": "Left-hand layout"},
    {"id": "right", "label": "Right-hand layout"},
] + [{"id": intent.split(".")[1], "label": label, "intent": intent} for intent, label in INTENT_LABELS.items()]

LARGER_TEXT = 1.25   # the text size of One-Hand's own "Larger text" option


def combine(larger_text, shared):
    """The text size, contrast and motion to use, from One-Hand's own option and the suite's
    shared settings: whichever is more accessible. These are the only shared settings One-Hand honors."""
    scale = min(2.0, max(1.0, float(shared.get("textScale") or 1.0)))
    return {"textScale": max(LARGER_TEXT if larger_text else 1.0, scale),
            "highContrast": bool(shared.get("highContrast")),
            "reduceMotion": bool(shared.get("reduceMotion"))}


class Suite:
    def __init__(self, engine, backend, set_hand, dispatch=None, prefs_changed=None):
        self.engine = engine
        self.backend = backend
        self.set_hand = set_hand
        self.prefs_changed = prefs_changed
        self.shared = {}   # the suite's shared settings, once the hub sends them
        self.link = Link("onehand", "Limitless One-Hand", VERSION, actions=ACTIONS,
                         on_invoke=self.invoke, on_connected=self._connected, on_prefs=self._prefs,
                         dispatch=dispatch, subscribe=["daw.*", "zoom.keys"])

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
        labels = {l.lower() for l in [INTENT_LABELS[intent], *ALIASES.get(intent, [])]}
        cmd = next((c for c in app["commands"] if c["label"].lower() in labels), None)
        if not cmd:
            return False, f"{app['name']} has no {INTENT_LABELS[intent]} in the one-hand layout."
        send = getattr(self.backend, "send", None)
        if send is None:
            return False, "This computer can't press keys."
        names = MOD_TO_KEY[self.engine.platform]
        send(Tap(cmd["send"], tuple(names[m] for m in cmd.get("mods", []))))
        self.link.did(intent.split(".")[1], intent)
        return True, f"{INTENT_LABELS[intent]} in {app['name']}"

    def _connected(self, up):
        if up:  # tell a newly started hub where things stand
            self.mode_changed(self.engine.enabled)
            self.hand_changed(self.engine.settings.hand)

    def _prefs(self, prefs):
        # Sent when the hub connects and whenever the musician changes a shared setting.
        self.shared = prefs
        if self.prefs_changed:
            self.prefs_changed()

    def look(self, larger_text):
        return combine(larger_text, self.shared)

    def prefs_applied(self, applied):
        """Tell the suite which shared settings are now in use, so its settings page knows they arrived."""
        self.link.state("prefs.applied", dict(applied))

    def mode_changed(self, on):
        self.link.state("mode", bool(on))

    def hand_changed(self, hand):
        self.link.state("hand", hand)

    def say(self, text):
        """True when the suite's one voice said it."""
        return self.link.say(text)
