"""One undo history for every plugin in the session.

Each DAW keeps plugin changes either inside its main undo (where they get in the
way of undoing edits) or nowhere at all. Limitless Keys keeps them here instead,
in time order across every plugin, so "undo the last plugin change" always
means the one you actually made last, whichever plugin it was in.

A Source is one place plugin changes can be undone:
  - a Limitless Undo plugin (kind "link"), which reports each change exactly, or
  - a Logic Pro plugin window (kind "window"), which has its own Undo button.

This module is plain logic with no threads or OS calls, so it can be tested.
"""

import time


class Step:
    __slots__ = ("id", "label", "before", "after", "time")

    def __init__(self, id, label="", before="", after="", time=0.0):
        self.id, self.label, self.before, self.after, self.time = id, label, before, after, time

    def __repr__(self):
        return f"Step({self.id!r}, {self.label!r})"

    def describe(self):
        if self.label and self.before and self.after:
            return f"{self.label}: {self.before} → {self.after}"
        return self.label or "a change"


class Source:
    def __init__(self, key, kind, pid=None, daw=None, plugin="", track=""):
        self.key, self.kind, self.pid, self.daw = key, kind, pid, daw
        self.plugin, self.track = plugin, track
        self.undo = []   # oldest first: undo[-1] is undone next
        self.redo = []   # redo[-1] is redone next

    @property
    def title(self):
        if self.plugin and self.track:
            return f"{self.plugin} on {self.track}"
        return self.plugin or self.track or "a plugin"

    def __repr__(self):
        return f"Source({self.key!r}, {self.kind!r}, undo={len(self.undo)}, redo={len(self.redo)})"


class Timeline:
    MAX_STEPS = 500   # per source; older steps are forgotten

    def __init__(self, clock=time.time):
        self.clock = clock
        self.sources = {}
        self.redo_order = []   # (source key, step id), most recently undone last
        self.version = 0       # goes up on every change, for windows that show the history

    def _changed(self):
        self.version += 1

    # Sources ------------------------------------------------------------------

    def add_source(self, key, kind, pid=None, daw=None, plugin="", track=""):
        src = self.sources.get(key)
        if src is None:
            src = self.sources[key] = Source(key, kind, pid, daw, plugin, track)
        else:
            src.kind, src.pid, src.daw = kind, pid, daw
            src.plugin, src.track = plugin or src.plugin, track or src.track
        self._changed()
        return src

    def update_source(self, key, **meta):
        src = self.sources.get(key)
        if src is not None:
            for k, v in meta.items():
                if v is not None and hasattr(src, k):
                    setattr(src, k, v)
            self._changed()

    def remove_source(self, key):
        if self.sources.pop(key, None) is not None:
            self.redo_order = [e for e in self.redo_order if e[0] != key]
            self._changed()

    # Changes ------------------------------------------------------------------

    def push(self, key, step_id, label="", before="", after="", at=None):
        """A new change in one source. Like any undo, it ends that source's redo."""
        src = self.sources[key]
        step = Step(step_id, label, before, after, self.clock() if at is None else at)
        src.undo.append(step)
        del src.undo[:-self.MAX_STEPS]
        src.redo.clear()
        self._changed()
        return step

    def sync(self, key, undo, redo):
        """Replace a source's whole history: lists of dicts with id, label, before,
        after and age (seconds since the change), oldest first."""
        src = self.sources[key]
        now = self.clock()

        def make(d):
            return Step(d["id"], d.get("label", ""), d.get("before", ""), d.get("after", ""),
                        now - float(d.get("age", 0)))

        src.undo = [make(d) for d in undo][-self.MAX_STEPS:]
        src.redo = [make(d) for d in redo][-self.MAX_STEPS:]
        self._changed()

    def mark_undone(self, key, step_id):
        """The source undid step_id. False if that wasn't its next undo."""
        src = self.sources.get(key)
        if src is None or not src.undo or src.undo[-1].id != step_id:
            return False
        src.redo.append(src.undo.pop())
        self.redo_order.append((key, step_id))
        del self.redo_order[:-self.MAX_STEPS * 4]
        self._changed()
        return True

    def mark_redone(self, key, step_id):
        src = self.sources.get(key)
        if src is None or not src.redo or src.redo[-1].id != step_id:
            return False
        src.undo.append(src.redo.pop())
        self._changed()
        return True

    def drop(self, key, step_id):
        """Forget one step, e.g. a click in a window that turned out not to be a change."""
        src = self.sources.get(key)
        if src is None:
            return
        src.undo = [s for s in src.undo if s.id != step_id]
        src.redo = [s for s in src.redo if s.id != step_id]
        self._changed()

    def clear(self, key):
        """Forget a source's history, e.g. when its window has closed."""
        src = self.sources.get(key)
        if src is not None:
            src.undo.clear()
            src.redo.clear()
            self._changed()

    # Choosing what to undo -------------------------------------------------------

    def _belongs(self, src, pid, daw):
        if pid is None and daw is None:
            return True
        # A plugin that couldn't tell which DAW it is in (some DAWs run plugins in a
        # helper process) belongs to whichever DAW you're using.
        return (src.daw is None or (pid is not None and src.pid == pid)
                or (daw is not None and src.daw == daw))

    def next_undo(self, pid=None, daw=None):
        """(source, step) for the most recent change in this DAW, or (None, None)."""
        best = (None, None)
        for src in self.sources.values():
            if src.undo and self._belongs(src, pid, daw):
                if best[1] is None or src.undo[-1].time >= best[1].time:
                    best = (src, src.undo[-1])
        return best

    def next_redo(self, pid=None, daw=None):
        """(source, step) for the most recently undone change in this DAW."""
        i = len(self.redo_order) - 1
        while i >= 0:
            key, step_id = self.redo_order[i]
            src = self.sources.get(key)
            if src is None or not src.redo or not any(s.id == step_id for s in src.redo):
                del self.redo_order[i]       # redone already, or redo was ended by a new change
            elif src.redo[-1].id == step_id and self._belongs(src, pid, daw):
                return src, src.redo[-1]
            i -= 1
        return None, None

    def has_sources(self, pid=None, daw=None, kind=None):
        return any(self._belongs(s, pid, daw) and (kind is None or s.kind == kind)
                   for s in self.sources.values())

    def recent(self, limit=200, pid=None, daw=None):
        """Newest first: (source, step, undone) for the history window."""
        rows = []
        for src in self.sources.values():
            if not self._belongs(src, pid, daw):
                continue
            rows += [(src, s, False) for s in src.undo]
            rows += [(src, s, True) for s in src.redo]
        rows.sort(key=lambda r: r[1].time, reverse=True)
        return rows[:limit]
