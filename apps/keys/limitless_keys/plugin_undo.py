"""Plugin undo: undo and redo only plugin changes, newest first, across every plugin.

Changes come from two places, kept in one Timeline:
  - Limitless Undo plugins, over the link (undo_link.py), in any DAW;
  - Logic Pro's own plugin windows, each of which has an Undo and Redo button
    (logic_windows.py), so in Logic it works with every plugin, no setup needed.

Everything here can be called from any thread.
"""

import itertools
import threading
import time

from .daws import DAWS, find_daw
from .timeline import Timeline

# A click in a Logic plugin window that is followed this quickly by a change from
# a Limitless Undo plugin in the same DAW was that plugin's change, not a separate one.
SAME_CHANGE = 0.6


class PluginUndo:
    def __init__(self, timeline=None, clock=time.time):
        self.clock = clock
        self.timeline = timeline or Timeline(clock)
        self.lock = threading.RLock()
        self.link = None          # LinkServer, once started
        self.windows = None       # LogicWindows on a Mac
        self.last_daw = (None, None)
        self._ids = itertools.count(1)
        self._compare = None
        self._last_window_step = None   # (key, step id, time, pid)

    # Which DAW ---------------------------------------------------------------

    def _where(self, ctx):
        app_id, pid = (ctx.app_id, ctx.pid) if ctx is not None else (None, None)
        if not find_daw(app_id):
            app_id, pid = self.last_daw    # e.g. a voice command while our window is in front
        return pid, find_daw(app_id)

    # From Limitless Undo plugins ---------------------------------------------------

    def link_message(self, key, msg):
        op = msg.get("op")
        with self.lock:
            tl = self.timeline
            if op == "hello":
                tl.add_source(key, "link", pid=msg.get("pid"), daw=find_daw(msg.get("host")),
                              plugin=msg.get("plugin") or "", track=msg.get("track") or "")
            elif key not in tl.sources:
                return
            elif op == "meta":
                tl.update_source(key, plugin=msg.get("plugin"), track=msg.get("track"))
            elif op == "sync":
                tl.sync(key, msg.get("undo") or [], msg.get("redo") or [])
            elif op == "step":
                tl.push(key, msg.get("id"), msg.get("label", ""), msg.get("before", ""),
                        msg.get("after", ""))
                self._forget_matching_click(tl.sources[key].pid)
            elif op == "undone":
                tl.mark_undone(key, msg.get("id"))
            elif op == "redone":
                tl.mark_redone(key, msg.get("id"))

    def link_closed(self, key):
        with self.lock:
            self.timeline.remove_source(key)

    def _forget_matching_click(self, pid):
        last = self._last_window_step
        if last and last[3] == pid and self.clock() - last[2] <= SAME_CHANGE:
            self.timeline.drop(last[0], last[1])
            self._last_window_step = None

    # From Logic's plugin windows --------------------------------------------------

    def window_touch(self, key, pid, title):
        """A click, drag or scroll in a Logic plugin window: probably a change."""
        with self.lock:
            tl = self.timeline
            if key not in tl.sources:
                tl.add_source(key, "window", pid=pid, daw="logic", plugin=title)
            elif title:
                tl.update_source(key, plugin=title)
            step_id = next(self._ids)
            tl.push(key, step_id)
            self._last_window_step = (key, step_id, self.clock(), pid)
            return step_id

    def window_manual(self, key, which):
        """Someone clicked the Undo or Redo button in a Logic plugin window themselves."""
        with self.lock:
            src = self.timeline.sources.get(key)
            if src is None:
                return
            if which == "undo" and src.undo:
                self.timeline.mark_undone(key, src.undo[-1].id)
            elif which == "redo" and src.redo:
                self.timeline.mark_redone(key, src.redo[-1].id)

    def window_gone(self, key):
        with self.lock:
            self.timeline.remove_source(key)

    # Doing it ---------------------------------------------------------------------

    def _perform(self, src, step, which):
        if src.kind == "link":
            return self.link is not None and self.link.send(src.key, {"op": which, "id": step.id})
        if src.kind == "window":
            return self.windows is not None and self.windows.press(src.key, which)
        return False

    def _step_undo(self, pid, daw):
        """Undo the newest change; returns (source, step) or (None, None)."""
        tl = self.timeline
        for _ in range(50):
            src, step = tl.next_undo(pid, daw)
            if src is None:
                return None, None
            if self._perform(src, step, "undo"):
                tl.mark_undone(src.key, step.id)
                return src, step
            # That plugin window closed, or its plugin went away: forget it and go on.
            tl.clear(src.key)
        return None, None

    def _step_redo(self, pid, daw):
        tl = self.timeline
        for _ in range(50):
            src, step = tl.next_redo(pid, daw)
            if src is None:
                return None, None
            if self._perform(src, step, "redo"):
                tl.mark_redone(src.key, step.id)
                return src, step
            tl.clear(src.key)
        return None, None

    def undo(self, ctx=None):
        with self.lock:
            pid, daw = self._where(ctx)
            src, step = self._step_undo(pid, daw)
            if src is None:
                return False, self._nothing("undo", pid, daw)
            return True, self._said("Plugin undo", src, step, step.before, "back to")

    def redo(self, ctx=None):
        with self.lock:
            pid, daw = self._where(ctx)
            src, step = self._step_redo(pid, daw)
            if src is None:
                return False, self._nothing("redo", pid, daw)
            return True, self._said("Plugin redo", src, step, step.after, "to")

    def compare(self, down, ctx=None):
        """Hold to hear the sound before the last plugin change; let go to hear it after."""
        with self.lock:
            pid, daw = self._where(ctx)
            if down:
                src, step = self._step_undo(pid, daw)
                if src is None:
                    self._compare = None
                    return False, self._nothing("compare", pid, daw)
                self._compare = (src.key, step.id)
                return True, f"Before: {step.label or src.title}"
            held, self._compare = self._compare, None
            if held is None:
                return None
            src = self.timeline.sources.get(held[0])
            if src is None or not src.redo or src.redo[-1].id != held[1]:
                return False, "Can't go back to after: that plugin changed meanwhile"
            step = src.redo[-1]
            if self._perform(src, step, "redo"):
                self.timeline.mark_redone(src.key, step.id)
                return True, "After"
            return False, "Can't go back to after: the plugin window closed"

    def undo_front(self, ctx=None):
        return self._front("undo", ctx)

    def redo_front(self, ctx=None):
        return self._front("redo", ctx)

    def _front(self, which, ctx):
        pid, daw = self._where(ctx)
        if self.windows is None or daw != "logic":
            return False, "This works in Logic Pro's plugin windows."
        key, title = self.windows.front(pid)
        if key is None:
            return False, "No plugin window is in front."
        if not self.windows.press(key, which):
            return False, f"Nothing to {which} in {title}."
        with self.lock:
            if key not in self.timeline.sources:
                self.timeline.add_source(key, "window", pid=pid, daw="logic", plugin=title)
        self.window_manual(key, which)
        return True, f"Plugin {which} in {title}"

    # Words ------------------------------------------------------------------------

    def _said(self, what, src, step, value, joiner):
        if src.kind == "window" or not step.label:
            return f"{what} in {src.title}"
        if value:
            return f"{what}: {step.label} {joiner} {value} · {src.title}"
        return f"{what}: {step.label} · {src.title}"

    def _nothing(self, which, pid, daw):
        what = {"undo": "No plugin changes to undo", "redo": "No plugin changes to redo",
                "compare": "No plugin change to compare"}[which]
        if daw is None:
            return what + "."
        if DAWS[daw].get("plugin_windows"):
            if self.timeline.has_sources(pid, daw):
                return what + "."
            return what + ". Change a plugin in its window first."
        if not self.timeline.has_sources(pid, daw, kind="link"):
            return (f"{what}. In {DAWS[daw]['name']}, load your plugins inside "
                    f"Limitless Undo to undo their changes.")
        return what + "."
