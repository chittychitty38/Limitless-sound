"""Joining the Limitless Sound suite.

With the Limitless Sound hub running, any other app can undo a plugin change (a
controller button, a glance in GazeStage, saying "undo plugin" to Limitless
Voice), any of your shortcuts can run any suite action, and spoken feedback goes
through the suite's one voice. Without the hub, none of this does anything.
"""

import weakref

from . import __version__
from .limitless_link import Link

ACTIONS = [
    {"id": "pluginUndo", "label": "Undo the last plugin change",
     "phrases": ["undo plugin", "plugin undo", "undo the plugin"]},
    {"id": "pluginRedo", "label": "Redo the last plugin change",
     "phrases": ["redo plugin", "plugin redo"]},
    {"id": "pluginBefore", "label": "Hear before the last plugin change",
     "phrases": ["plugin before", "hear before"]},
    {"id": "pluginAfter", "label": "Back to after the last plugin change",
     "phrases": ["plugin after", "hear after"]},
    {"id": "undoFront", "label": "Undo in the plugin window in front"},
    {"id": "pluginHistory", "label": "Show the plugin change history",
     "phrases": ["plugin history"]},
    {"id": "cheatSheet", "label": "Show my shortcuts for this app",
     "phrases": ["show my shortcuts", "what are my shortcuts"]},
    {"id": "press", "label": "Do one of my shortcuts", "args": {"shortcut": "text"}},
    {"id": "pause", "label": "Pause Limitless Keys"},
    {"id": "resume", "label": "Resume Limitless Keys"},
]


class Suite:
    def __init__(self, app, dispatch=None):
        self.app = weakref.proxy(app)
        self.link = Link("keys", "Limitless Keys", __version__, actions=ACTIONS, on_invoke=self.invoke,
                         on_connected=self.on_connected, dispatch=dispatch, subscribe=["hub.*"])

    def start(self):
        self.link.start()
        return self

    def stop(self):
        self.link.stop()

    def invoke(self, action, args, source):
        return self.app.suite_action(action, args or {})

    def run(self, action, args):
        """Run another app's action, for shortcuts that do {"suite": ...}."""
        return self.link.invoke(action, args)

    def did(self, action, value=None):
        self.link.did(action, None, value)

    def paused(self, paused):
        self.link.state("paused", bool(paused))

    def on_connected(self, connected):
        if connected:
            self.paused(not self.app.engine.enabled)

    def suite_actions(self):
        """Every action in the suite, for picking one in the shortcut editor."""
        return [a for a in self.link.suite_actions if isinstance(a, dict)]

    def say(self, text):
        return self.link.say(text)
