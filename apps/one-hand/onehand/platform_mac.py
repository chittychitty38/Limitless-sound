"""macOS backend: a Quartz event tap, using pyobjc."""
import plistlib
import subprocess
import sys
import threading
import time
from pathlib import Path

import Quartz
from AppKit import NSRunningApplication, NSWorkspace

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
        self._asked = False
        self.error = None

    # ---- lifecycle ----------------------------------------------------

    def start(self, engine):
        self.engine = engine
        if not self._asked:
            self._asked = True
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
        if self._tap:
            Quartz.CGEventTapEnable(self._tap, False)
            Quartz.CFMachPortInvalidate(self._tap)
            self._tap = None
        if self._loop:
            Quartz.CFRunLoopStop(self._loop)
            self._loop = None

    @property
    def running(self):
        return self._tap is not None

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

    def inject(self, key, up):
        """Type a key as if from another program (the tap will see it). Used by --self-test."""
        ev = Quartz.CGEventCreateKeyboardEvent(None, MAC_CODES[key], not up)
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

    def permission_status(self):
        """{"Accessibility": bool, "Input Monitoring": bool} as macOS reports them now."""
        try:
            from ApplicationServices import AXIsProcessTrusted
            ax = bool(AXIsProcessTrusted())
        except Exception:
            ax = self.running
        listen = bool(Quartz.CGPreflightListenEventAccess()) if hasattr(Quartz, "CGPreflightListenEventAccess") else ax
        return {"Accessibility": ax, "Input Monitoring": listen}

    def permission_help(self):
        return ("Open System Settings → Privacy & Security, then turn on Limitless One-Hand under "
                "both Accessibility and Input Monitoring.")

    def open_permission_settings(self, which="Accessibility"):
        url = INPUT_MONITORING_URL if which == "Input Monitoring" else ACCESSIBILITY_URL
        subprocess.Popen(["open", url])

    def relaunch(self):
        """Start a fresh copy of the app (macOS applies some permissions only to new processes)."""
        bundle = self.bundle_path()
        if bundle:
            subprocess.Popen(["/bin/sh", "-c", f'sleep 1; open -n "{bundle}"'])
        else:
            subprocess.Popen([sys.executable, *sys.argv])

    # ---- about this app -----------------------------------------------

    @staticmethod
    def bundle_path():
        if getattr(sys, "frozen", False):
            p = Path(sys.executable).resolve()
            for parent in p.parents:
                if parent.suffix == ".app":
                    return str(parent)
        return None

    def own_app_id(self):
        return NSRunningApplication.currentApplication().bundleIdentifier()

    LOGIN_PLIST = Path.home() / "Library" / "LaunchAgents" / "org.limitlesssound.onehand.plist"

    def login_item_supported(self):
        return self.bundle_path() is not None

    def set_login_item(self, on):
        if not on:
            self.LOGIN_PLIST.unlink(missing_ok=True)
            return
        self.LOGIN_PLIST.parent.mkdir(parents=True, exist_ok=True)
        self.LOGIN_PLIST.write_bytes(plistlib.dumps({
            "Label": "org.limitlesssound.onehand",
            "ProgramArguments": ["/usr/bin/open", "-a", self.bundle_path(), "--args", "--hidden"],
            "RunAtLoad": True,
        }))

    def float_window(self, widget):
        """Keep a small window above full-screen apps on every Space."""
        try:
            import objc
            from AppKit import (NSStatusWindowLevel, NSWindowCollectionBehaviorCanJoinAllSpaces,
                                NSWindowCollectionBehaviorFullScreenAuxiliary,
                                NSWindowCollectionBehaviorStationary)
            view = objc.objc_object(c_void_p=int(widget.winId()))
            win = view.window()
            win.setLevel_(NSStatusWindowLevel)
            win.setCollectionBehavior_(NSWindowCollectionBehaviorCanJoinAllSpaces
                                       | NSWindowCollectionBehaviorFullScreenAuxiliary
                                       | NSWindowCollectionBehaviorStationary)
            win.setIgnoresMouseEvents_(True)
            win.setHidesOnDeactivate_(False)
        except Exception:
            pass

    def announce(self, text):
        """Have VoiceOver read text out, if it is running."""
        try:
            from AppKit import (NSAccessibilityAnnouncementKey, NSAccessibilityAnnouncementRequestedNotification,
                                NSAccessibilityPostNotificationWithUserInfo, NSAccessibilityPriorityKey, NSApp)
            NSAccessibilityPostNotificationWithUserInfo(
                NSApp, NSAccessibilityAnnouncementRequestedNotification,
                {NSAccessibilityAnnouncementKey: text, NSAccessibilityPriorityKey: 90})
        except Exception:
            pass

    # ---- feedback -----------------------------------------------------

    def play_sound(self, on):
        sound = "Tink" if on else "Pop"
        subprocess.Popen(["afplay", f"/System/Library/Sounds/{sound}.aiff"])

    def speak(self, text):
        subprocess.Popen(["say", text])
