"""Joining the Limitless Sound suite.

With the Limitless Sound hub running, any other app can zoom (a controller
button, a glance in GazeStage, a One-Hand key, a voice command), Zoom answers
the shared "daw.zoomIn / zoomOut / zoomFit" requests, and it tells the suite
when its zoom keys layer turns on or off so One-Hand can step aside.
Without the hub, none of this does anything.
"""

import weakref

from . import __version__
from .actions import LABELS, VOICE_PHRASES
from .limitless_link import Link

INTENTS = {"in": "daw.zoomIn", "out": "daw.zoomOut", "fit": "daw.zoomFit"}
EXTRA = {"keysOn": "Zoom keys on", "keysOff": "Zoom keys off"}
LOCAL_ONLY = {"sleep", "wake"}   # Zoom's own voice; the suite has Limitless Voice for that


def actions():
    by_action = {}
    for phrase, action in VOICE_PHRASES.items():
        by_action.setdefault(action, []).append(phrase)
    out = []
    for action, label in {**LABELS, **EXTRA}.items():
        if action in LOCAL_ONLY:
            continue
        a = {"id": action, "label": label}
        if action in INTENTS:
            a["intent"] = INTENTS[action]
        if by_action.get(action):
            a["phrases"] = by_action[action][:6]
        out.append(a)
    return out


class Suite:
    def __init__(self, app, dispatch=None):
        self.app = weakref.proxy(app)   # the app owns the suite, not the other way round
        self.link = Link("zoom", "Limitless Zoom", __version__, actions=actions(), on_invoke=self.invoke,
                         on_prefs=self.on_prefs, on_connected=self.on_connected, dispatch=dispatch,
                         subscribe=["onehand.mode", "hub.*"])

    def start(self):
        self.link.start()
        return self

    def stop(self):
        self.link.stop()

    def invoke(self, action, args, source):
        if action in ("keysOn", "keysOff"):
            on = action == "keysOn"
            if self.app.logic.layer_on != on:
                self.app.logic.set_layer(on)
            return True, EXTRA[action]
        if action not in LABELS or action in LOCAL_ONLY:
            return False, f"Limitless Zoom has no action {action!r}."
        self.app.run(action)
        return True, LABELS[action]

    def did(self, action):
        self.link.did(action, INTENTS.get(action))

    def keys_changed(self, on):
        self.link.state("keys", bool(on))

    def on_connected(self, connected):
        if connected:
            self.keys_changed(self.app.logic.layer_on)

    def on_prefs(self, prefs):
        """The suite's dwell time and scan speed apply to the zoom panel too."""
        panel = self.app.panel
        if "dwellMs" in prefs:
            for b in panel.findChildren(type(panel.scan_button)):
                b.dwell_ms = int(prefs["dwellMs"])
        if "scanMs" in prefs:
            panel.scan_timer.setInterval(int(prefs["scanMs"]))

    def say(self, text):
        return self.link.say(text)
