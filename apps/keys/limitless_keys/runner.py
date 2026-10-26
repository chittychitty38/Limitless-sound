"""Does what a shortcut says, one shortcut at a time, off the keyboard thread."""

import queue
import threading
import time

from .keys import parse_sequence
from .profiles import menu_path


class Context:
    """Where a shortcut was pressed: the app in front and its process id."""

    def __init__(self, app_id=None, pid=None):
        self.app_id, self.pid = app_id, pid

    def __repr__(self):
        return f"Context({self.app_id!r}, {self.pid!r})"


class Runner:
    def __init__(self, backend, plugins, dispatch, feedback, app_action, suite_invoke=None, did=None):
        """dispatch(fn) runs fn on the UI thread; feedback(text, ok, speak) shows and says it;
        did(action, message) hears about each plugin undo or redo that worked."""
        self.backend, self.plugins = backend, plugins
        self.dispatch, self._feedback = dispatch, feedback
        self.app_action, self.suite_invoke = app_action, suite_invoke
        self.did = did
        self._queue = queue.Queue()
        self._thread = None

    def start(self):
        if self._thread is None:
            self._thread = threading.Thread(target=self._loop, daemon=True, name="limitless-keys-runner")
            self._thread.start()
        return self

    def submit(self, binding, phase, app_id=None, pid=None):
        """Called from the keyboard thread: just queue it."""
        self._queue.put((binding.action, phase, Context(app_id, pid)))

    def submit_action(self, action, phase="down", ctx=None):
        self._queue.put((action, phase, ctx or Context()))

    def run_now(self, action, phase="down", ctx=None):
        """Runs an action on this thread. Used by tests and by the queue."""
        self._do(action, phase, ctx or Context())

    def _loop(self):
        while True:
            action, phase, ctx = self._queue.get()
            try:
                self._do(action, phase, ctx)
            except Exception as e:  # one bad shortcut must never stop the others
                self.feedback(f"That shortcut didn't work: {e}", ok=False)

    def feedback(self, text, ok=True, speak=True):
        if text:
            self.dispatch(lambda: self._feedback(text, ok, speak))

    def _do(self, action, phase, ctx):
        if "plugin" in action:
            self._plugin(action["plugin"], phase, ctx)
            return
        if phase == "up":
            return
        if "steps" in action:
            for step in action["steps"]:
                self._do(step, phase, ctx)
        elif "keys" in action:
            for combo in parse_sequence(action["keys"]):
                self.backend.send(combo, ctx.pid)
        elif "menu" in action:
            ok, message = self.backend.press_menu(ctx.pid, menu_path(action["menu"]))
            if not ok:
                self.feedback(message, ok=False)
        elif "button" in action:
            ok, message = self.backend.press_button(ctx.pid, action["button"])
            if not ok:
                self.feedback(message, ok=False)
        elif "type" in action:
            self.backend.type_text(action["type"])
        elif "say" in action:
            self.feedback(action["say"])
        elif "wait" in action:
            time.sleep(float(action["wait"]))
        elif "suite" in action:
            if self.suite_invoke is None or not self.suite_invoke(action["suite"], action.get("args") or {}):
                self.feedback("The Limitless Sound hub isn't running.", ok=False)
        elif "app" in action:
            name = action["app"]
            self.dispatch(lambda: self.app_action(name, ctx))

    def _plugin(self, what, phase, ctx):
        p = self.plugins
        if what == "compare":
            result = p.compare(phase == "down", ctx)
        elif phase == "up":
            return
        elif what == "undo":
            result = p.undo(ctx)
        elif what == "redo":
            result = p.redo(ctx)
        elif what == "undoFront":
            result = p.undo_front(ctx)
        elif what == "redoFront":
            result = p.redo_front(ctx)
        elif what == "history":
            self.dispatch(lambda: self.app_action("history", ctx))
            return
        else:
            return
        if result:
            ok, message = result
            if ok and self.did is not None and what in ("undo", "redo"):
                self.dispatch(lambda: self.did("plugin" + what.title(), message))
            if message:
                # Holding a shortcut down shows each step but only says the first.
                self.feedback(message, ok, speak=phase != "repeat" or not ok)
