"""Plugin undo in Logic Pro, with every plugin and no setup.

Each Logic plugin window has its own Undo and Redo buttons at the top. Logic
has no command for "undo the last change in whichever plugin I touched last",
so this watches which plugin windows you click, drag or scroll in, keeps them in
the plugin Timeline in that order, and presses the right window's Undo button.

ax is the macax module on a Mac (tests pass a stand-in).
"""

import itertools
import queue
import threading
import time

CHROME = {"AXCloseButton", "AXMinimizeButton", "AXZoomButton", "AXFullScreenButton"}
SCROLL_GAP = 0.8      # scrolling the same window within this counts as one change
RECHECK = 10.0        # seconds before looking at a window's buttons again


class Window:
    def __init__(self, el, key, title, undo, redo, wrapped):
        self.el, self.key, self.title = el, key, title
        self.undo, self.redo, self.wrapped = undo, redo, wrapped
        self.checked = time.monotonic()


class LogicWindows:
    # A Logic plugin window has Undo and Redo, and at least one of these too, which
    # tells it apart from a main window whose control bar has Undo and Redo added.
    MARKERS = ("compare", "bypass", "link", "copy", "paste")

    def __init__(self, plugins, ax, is_logic, markers=None):
        """is_logic(pid) says whether a process is Logic Pro."""
        self.plugins, self.ax, self.is_logic = plugins, ax, is_logic
        self.markers = tuple(m.lower() for m in (markers or self.MARKERS))
        self.windows = []            # Window, newest last
        self._not_plugin = []        # (element, title, time) of windows that aren't plugin windows
        self._ids = itertools.count(1)
        self._down = None
        self._last_scroll = {}
        self._queue = queue.Queue()
        self._lock = threading.RLock()
        self._thread = None

    def start(self):
        if self._thread is None:
            self._thread = threading.Thread(target=self._loop, daemon=True, name="logic-windows")
            self._thread.start()
        return self

    def mouse(self, x, y, kind):
        """From the mouse listener: kind is "down", "up" or "scroll". Never blocks."""
        self._queue.put((x, y, kind, time.monotonic()))

    def _loop(self):
        while True:
            x, y, kind, at = self._queue.get()
            try:
                self.handle(x, y, kind, at)
            except Exception:
                pass

    # Reading windows -------------------------------------------------------------

    def _classify(self, win):
        """The Window for a Logic plugin window, or None if it isn't one."""
        ax = self.ax
        title = ax.attr(win, "AXTitle", "") or ""
        with self._lock:
            for w in self.windows:
                if ax.same(w.el, win) and w.title == title and time.monotonic() - w.checked < RECHECK:
                    return w
            now = time.monotonic()
            for el, t, at in self._not_plugin:
                if t == title and now - at < RECHECK and ax.same(el, win):
                    return None
        undo = redo = None
        marker = wrapped = False
        for el in ax.walk(win, max_nodes=800, max_depth=14):
            role = ax.attr(el, "AXRole")
            if role in ax.PRESSABLE:
                if undo is None and ax.matches(el, "undo"):
                    undo = el
                elif redo is None and ax.matches(el, "redo"):
                    redo = el
                elif not marker and any(ax.matches(el, m) for m in self.markers):
                    marker = True
            elif role == "AXStaticText" and not wrapped:
                text = ax.attr(el, "AXValue") or ax.attr(el, "AXTitle") or ""
                wrapped = isinstance(text, str) and text.strip().lower() == "uncommando"
        if ax.attr(win, "AXSubrole") == "AXFloatingWindow":
            marker = True
        with self._lock:
            if undo is None or redo is None or not marker:
                self._not_plugin = [n for n in self._not_plugin if time.monotonic() - n[2] < RECHECK][-20:]
                self._not_plugin.append((win, title, time.monotonic()))
                return None
            for w in self.windows:
                if ax.same(w.el, win) and w.title == title:
                    w.undo, w.redo, w.wrapped, w.checked = undo, redo, wrapped, time.monotonic()
                    return w
            w = Window(win, f"logic-window:{next(self._ids)}", title, undo, redo, wrapped)
            self.windows.append(w)
            del self.windows[:-40]
            return w

    def _alive(self, w):
        ax = self.ax
        return ax.attr(w.el, "AXRole") == "AXWindow" and (ax.attr(w.el, "AXTitle", "") or "") == w.title

    # Mouse ---------------------------------------------------------------------

    def handle(self, x, y, kind, at=None):
        ax = self.ax
        at = time.monotonic() if at is None else at
        if kind == "up":
            down, self._down = self._down, None
            if down is None:
                return
            w, hit, pid = down
            if hit in ("undo", "redo"):
                self.plugins.window_manual(w.key, hit)
            elif hit == "content":
                self.plugins.window_touch(w.key, pid, w.title)
            return

        el = ax.element_at(x, y)
        if el is None:
            self._down = None
            return
        pid = ax.pid_of(el)
        if pid is None or not self.is_logic(pid):
            self._down = None
            return
        win = ax.window_of(el)
        w = self._classify(win) if win is not None else None
        if w is None or w.wrapped:
            # The Uncommando plugin reports its own changes exactly, so its window is left to it.
            self._down = None
            return

        if kind == "scroll":
            if at - self._last_scroll.get(w.key, -1e9) > SCROLL_GAP:
                self.plugins.window_touch(w.key, pid, w.title)
            self._last_scroll[w.key] = at
            return

        if ax.same(el, w.undo) or (ax.attr(el, "AXRole") in ax.PRESSABLE and ax.matches(el, "undo")):
            hit = "undo"
        elif ax.same(el, w.redo) or (ax.attr(el, "AXRole") in ax.PRESSABLE and ax.matches(el, "redo")):
            hit = "redo"
        elif ax.attr(el, "AXSubrole") in CHROME:
            hit = "chrome"
        else:
            hit = "content"
        self._down = (w, hit, pid)

    # Pressing -------------------------------------------------------------------

    def press(self, key, which):
        ax = self.ax
        with self._lock:
            w = next((w for w in self.windows if w.key == key), None)
        if w is None or not self._alive(w):
            return False
        button = ax.find_pressable(w.el, which, max_nodes=800)
        if button is None or ax.attr(button, "AXEnabled", True) is False:
            return False
        return ax.press(button)

    def front(self, pid):
        """(key, title) of the plugin window in front, or (None, None)."""
        win = self.ax.front_window(pid)
        w = self._classify(win) if win is not None else None
        if w is None:
            return None, None
        return w.key, w.title or "the plugin window"
