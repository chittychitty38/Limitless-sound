"""macOS backend: a Quartz event tap, using pyobjc."""
import subprocess
import threading
import time

import Quartz
from AppKit import NSWorkspace

from .engine import PASS, SUPPRESS, Tap
from .keys import MAC_CODES

# Marks keys we type ourselves so the tap lets them through. Keys typed by
# other software (Accessibility Keyboard, Switch Control, Voice Control)
# still go through the engine.
MAGIC = 0x4C534F48  # "LSOH"

CODE_TO_NAME = {v: k for k, v in MAC_CODES.items()}

MOD_FLAGS = {
    "cmd_l": Quartz.kCGEventFlagMaskCommand, "cmd_r": Quartz.kCGEventFlagMaskCommand,
    "shift_l": Quartz.kCGEventFlagMaskShift, "shift_r": Quartz.kCGEventFlagMaskShift,
    "alt_l": Quartz.kCGEventFlagMaskAlternate, "alt_r": Quartz.kCGEventFlagMaskAlternate,
    "ctrl_l": Quartz.kCGEventFlagMaskControl, "ctrl_r": Quartz.kCGEventFlagMaskControl,
}
CLASS_FLAGS = {
    "cmd": Quartz.kCGEventFlagMaskCommand, "shift": Quartz.kCGEventFlagMaskShift,
    "alt": Quartz.kCGEventFlagMaskAlternate, "ctrl": Quartz.kCGEventFlagMaskControl,
}
ARROWS = {"left_arrow", "right_arrow", "up_arrow", "down_arrow"}

ACCESSIBILITY_URL = "x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility"
INPUT_MONITORING_URL = "x-apple.systempreferences:com.apple.preference.security?Privacy_ListenEvent"


class MacBackend:
    platform = "mac"

    def __init__(self):
        self.engine = None
        self._tap = None
        self._loop = None
        self._thread = None
        self._source = Quartz.CGEventSourceCreate(Quartz.kCGEventSourceStatePrivate)
        self._app = (0.0, None)
        self.error = None

    # ---- lifecycle ----------------------------------------------------

    def start(self, engine):
        self.engine = engine
        self.request_permission()
        ready = threading.Event()
        self._thread = threading.Thread(target=self._run, args=(ready,), daemon=True)
        self._thread.start()
        ready.wait(5)
        if self.error:
            raise PermissionError(self.error)

    def _run(self, ready):
        mask = (Quartz.CGEventMaskBit(Quartz.kCGEventKeyDown)
                | Quartz.CGEventMaskBit(Quartz.kCGEventKeyUp)
                | Quartz.CGEventMaskBit(Quartz.kCGEventFlagsChanged))
        self._tap = Quartz.CGEventTapCreate(Quartz.kCGSessionEventTap, Quartz.kCGHeadInsertEventTap,
                                            Quartz.kCGEventTapOptionDefault, mask, self._callback, None)
        if not self._tap:
            self.error = "macOS has not given Limitless One-Hand permission to use the keyboard yet."
            ready.set()
            return
        source = Quartz.CFMachPortCreateRunLoopSource(None, self._tap, 0)
        self._loop = Quartz.CFRunLoopGetCurrent()
        Quartz.CFRunLoopAddSource(self._loop, source, Quartz.kCFRunLoopCommonModes)
        Quartz.CGEventTapEnable(self._tap, True)
        ready.set()
        Quartz.CFRunLoopRun()

    def stop(self):
        if self._loop:
            Quartz.CFRunLoopStop(self._loop)

    # ---- the tap ------------------------------------------------------

    def _callback(self, proxy, etype, event, refcon):
        if etype in (Quartz.kCGEventTapDisabledByTimeout, Quartz.kCGEventTapDisabledByUserInput):
            Quartz.CGEventTapEnable(self._tap, True)
            return event
        if Quartz.CGEventGetIntegerValueField(event, Quartz.kCGEventSourceUserData) == MAGIC:
            return event
        code = Quartz.CGEventGetIntegerValueField(event, Quartz.kCGKeyboardEventKeycode)
        name = CODE_TO_NAME.get(code)
        if not name:
            return event
        flags = Quartz.CGEventGetFlags(event)
        if etype == Quartz.kCGEventFlagsChanged:
            if name not in MOD_FLAGS:
                return event          # Caps Lock and Fn are left alone
            # With both Command keys held, letting go of one keeps the Command flag
            # set, so the flag alone can't tell press from release. Each flags event
            # is one press or one release of this key, so flip what we know.
            down = bool(flags & MOD_FLAGS[name]) and name not in self.engine.held_mods
        else:
            down = etype == Quartz.kCGEventKeyDown
        try:
            if etype != Quartz.kCGEventFlagsChanged:
                # Every key event carries the true modifier state; drop any release we missed.
                self.engine.sync_mods({cls for cls, bit in CLASS_FLAGS.items() if flags & bit})
            action = self.engine.handle(name, down, time.monotonic(), self.front_app())
        except Exception:
            action = PASS
        if action == SUPPRESS:
            return None
        if isinstance(action, Tap):
            self.send(action)
            return None
        return event

    def send(self, tap):
        flags = 0
        for m in set(tap.mods) | self.engine.held_mods:
            flags |= MOD_FLAGS[m]
        if tap.key in ARROWS:
            flags |= Quartz.kCGEventFlagMaskNumericPad | Quartz.kCGEventFlagMaskSecondaryFn
        for down in (True, False):
            ev = Quartz.CGEventCreateKeyboardEvent(self._source, MAC_CODES[tap.key], down)
            Quartz.CGEventSetFlags(ev, flags)
            Quartz.CGEventSetIntegerValueField(ev, Quartz.kCGEventSourceUserData, MAGIC)
            Quartz.CGEventPost(Quartz.kCGHIDEventTap, ev)

    # ---- which app is in front ---------------------------------------

    def front_app(self):
        now = time.monotonic()
        if now - self._app[0] < 0.25:
            return self._app[1]
        app = NSWorkspace.sharedWorkspace().frontmostApplication()
        bundle = app.bundleIdentifier() if app else None
        self._app = (now, bundle)
        return bundle

    # ---- permission ---------------------------------------------------

    def request_permission(self):
        try:
            from ApplicationServices import AXIsProcessTrustedWithOptions, kAXTrustedCheckOptionPrompt
            AXIsProcessTrustedWithOptions({kAXTrustedCheckOptionPrompt: True})
        except Exception:
            pass
        if hasattr(Quartz, "CGRequestListenEventAccess"):
            Quartz.CGRequestListenEventAccess()

    def permission_help(self):
        return ("Open System Settings → Privacy & Security, then turn on Limitless One-Hand under "
                "both Accessibility and Input Monitoring. Then press Try again.")

    def open_permission_settings(self):
        subprocess.Popen(["open", ACCESSIBILITY_URL])

    # ---- feedback -----------------------------------------------------

    def play_sound(self, on):
        sound = "Tink" if on else "Pop"
        subprocess.Popen(["afplay", f"/System/Library/Sounds/{sound}.aiff"])

    def speak(self, text):
        subprocess.Popen(["say", text])
