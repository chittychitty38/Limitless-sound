"""Keeps pynput from crashing an app on a Mac with Apple silicon.

pynput reads the keyboard layout (which key makes which letter) through macOS's
text input APIs whenever a keyboard Controller is created and every time a keyboard
Listener starts, on whichever thread does it. macOS 14 and later stop the app with
a trap when those APIs are called anywhere but the main thread. Limitless Zoom died
this way the first time it pressed a key from its worker thread, on a fresh
Apple silicon Mac in the nightly proof run.

Call prepare() on the main thread before anything uses pynput. It reads the layout
once, there, and gives pynput that copy from then on. Elsewhere it does nothing.

Copy this file into the app next to limitless_link.py. Standard library only.
"""

from __future__ import annotations

import contextlib
import sys

__all__ = ["prepare"]


def prepare() -> bool:
    """True if pynput will now read the keyboard layout safely from any thread."""
    if sys.platform != "darwin":
        return False
    try:
        import pynput.keyboard._darwin as keyboard
        from pynput._util import darwin as util
    except Exception:   # no pynput, or no window server to talk to
        return False
    if getattr(util, "_limitless_cached", False):
        return True
    with util.keycode_context() as context:
        layout = context

    @contextlib.contextmanager
    def cached_keycode_context():
        yield layout

    util.keycode_context = cached_keycode_context       # used by Controller()
    keyboard.keycode_context = cached_keycode_context   # used by Listener._run
    util._limitless_cached = True
    return True
