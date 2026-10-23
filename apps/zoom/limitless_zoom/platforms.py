"""The small amount of code that differs per operating system:
which app is in front, bringing it back to the front, pressing keys,
and keeping the zoom panel from stealing focus from the DAW."""

import ctypes
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

from .keys import MAC_KEYCODES, WIN_VK
from .settings import os_name


class KeySender:
    """Presses key combos with pynput (Quartz on macOS, SendInput on Windows, XTest on Linux)."""

    def __init__(self, os_name):
        from pynput.keyboard import Controller, Key, KeyCode

        self.os_name, self.Key, self.KeyCode = os_name, Key, KeyCode
        self.kb = Controller()
        self.mods = {"cmd": Key.cmd, "ctrl": Key.ctrl, "alt": Key.alt,
                     "shift": Key.shift, "win": Key.cmd}
        self.special = {
            "left": Key.left, "right": Key.right, "up": Key.up, "down": Key.down,
            "esc": Key.esc, "enter": Key.enter, "tab": Key.tab, "space": Key.space,
            "backspace": Key.backspace, "delete": Key.delete, "home": Key.home,
            "end": Key.end, "pageup": Key.page_up, "pagedown": Key.page_down,
        }
        for n in range(1, 21):
            k = getattr(Key, f"f{n}", None)
            if k is not None:
                self.special[f"f{n}"] = k

    def _key(self, name):
        if name in self.special:
            return self.special[name]
        if self.os_name == "win" and name in WIN_VK:
            return self.KeyCode.from_vk(WIN_VK[name])
        return self.KeyCode.from_char(name)

    def send(self, combo):
        mods, key = combo
        pressed = []
        try:
            for m in mods:
                self.kb.press(self.mods[m])
                pressed.append(self.mods[m])
            k = self._key(key)
            self.kb.press(k)
            time.sleep(0.01)
            self.kb.release(k)
        finally:
            for m in reversed(pressed):
                self.kb.release(m)
        time.sleep(0.02)


class Backend:
    os_name = "linux"

    def __init__(self):
        self._sender = None

    def send(self, combo):
        if self._sender is None:
            self._sender = KeySender(self.os_name)
        self._sender.send(combo)

    def frontmost(self):
        """(app_id, handle) for the app in front, or (None, None)."""
        return None, None

    def is_self(self, handle):
        return False

    def activate(self, handle):
        pass

    def prepare_panel(self, widget):
        pass

    def bring_to_front(self):
        """Put our own windows in front (a menu-bar app isn't in front by default)."""

    def keep_responsive(self):
        """Stop the OS slowing this app down while another app is in front."""

    def permissions(self):
        """What the OS must allow, as a list of dicts with key, title, why,
        state ("ok", "missing" or "unknown") and required. Title and why are in English;
        the setup window shows them in the suite's language."""
        return []

    def request_permission(self, key):
        pass

    # Open at login -------------------------------------------------------------

    def can_open_at_login(self):
        return False

    def open_at_login(self):
        return False

    def set_open_at_login(self, on):
        pass


class MacBackend(Backend):
    os_name = "mac"

    def frontmost(self):
        from AppKit import NSWorkspace

        app = NSWorkspace.sharedWorkspace().frontmostApplication()
        if app is None:
            return None, None
        return app.bundleIdentifier() or app.localizedName(), app.processIdentifier()

    def is_self(self, handle):
        return handle == os.getpid()

    def activate(self, handle):
        from AppKit import NSRunningApplication

        app = NSRunningApplication.runningApplicationWithProcessIdentifier_(handle)
        if app is not None:
            app.activateWithOptions_(1 << 1)  # NSApplicationActivateIgnoringOtherApps

    def prepare_panel(self, widget):
        # Qt tool windows are NSPanels; making them non-activating means
        # clicking or dwelling on a button leaves Logic or Pro Tools in front.
        try:
            import objc

            view = objc.objc_object(c_void_p=ctypes.c_void_p(int(widget.winId())))
            win = view.window()
            win.setStyleMask_(win.styleMask() | (1 << 7))  # NSWindowStyleMaskNonactivatingPanel
            win.setHidesOnDeactivate_(False)
            # Show on every Space and over full-screen DAW windows.
            win.setCollectionBehavior_((1 << 0) | (1 << 8))
        except Exception:
            pass

    def keep_responsive(self):
        # Limitless Zoom is always in the background behind the DAW, and App Nap
        # would otherwise slow its timers: dwell, scanning and voice would lag.
        try:
            from Foundation import NSProcessInfo

            # NSActivityUserInitiatedAllowingIdleSystemSleep | NSActivityLatencyCritical
            user_initiated, latency_critical = 0x00EFFFFF, 0xFF00000000
            self._activity = NSProcessInfo.processInfo().beginActivityWithOptions_reason_(
                user_initiated | latency_critical, "Listening for zoom commands")
        except Exception:
            self._activity = None

    def bring_to_front(self):
        try:
            from AppKit import NSApplication

            NSApplication.sharedApplication().activateIgnoringOtherApps_(True)
        except Exception:
            pass

    # Permissions -------------------------------------------------------------

    SETTINGS = "x-apple.systempreferences:com.apple.preference.security?Privacy_"

    def _accessibility(self):
        try:
            from ApplicationServices import AXIsProcessTrusted

            return "ok" if AXIsProcessTrusted() else "missing"
        except Exception:
            return "unknown"

    def _iokit(self):
        # Loaded once: permissions are checked every second while one is missing.
        lib = getattr(self, "_iokit_lib", None)
        if lib is None:
            lib = ctypes.cdll.LoadLibrary("/System/Library/Frameworks/IOKit.framework/IOKit")
            lib.IOHIDCheckAccess.restype = ctypes.c_int
            lib.IOHIDCheckAccess.argtypes = [ctypes.c_int]
            lib.IOHIDRequestAccess.restype = ctypes.c_bool
            lib.IOHIDRequestAccess.argtypes = [ctypes.c_int]
            self._iokit_lib = lib
        return lib

    def _input_monitoring(self):
        try:
            # kIOHIDRequestTypeListenEvent = 1; kIOHIDAccessTypeGranted = 0
            return "ok" if self._iokit().IOHIDCheckAccess(1) == 0 else "missing"
        except Exception:
            return "unknown"

    def _microphone(self):
        try:
            from AVFoundation import AVCaptureDevice, AVMediaTypeAudio

            status = AVCaptureDevice.authorizationStatusForMediaType_(AVMediaTypeAudio)
            return {3: "ok", 0: "ask"}.get(status, "missing")
        except Exception:
            return "unknown"

    @staticmethod
    def read_pref(domain, key):
        """Another app's setting, read in this process, as `defaults read` would see it.
        (Running `defaults` every second while Setup was open cost a few percent of the CPU.)"""
        from Foundation import CFPreferencesAppSynchronize, CFPreferencesCopyAppValue

        CFPreferencesAppSynchronize(domain)  # see changes made since by System Settings
        return CFPreferencesCopyAppValue(key, domain)

    def _zoom_shortcuts(self):
        try:
            value = self.read_pref("com.apple.universalaccess", "closeViewHotkeysEnabled")
        except Exception:
            return "unknown"
        if value is None:
            return "unknown"
        return "ok" if bool(value) else "missing"

    def permissions(self):
        mic = self._microphone()
        return [
            {"key": "accessibility", "title": "Accessibility",
             "why": "Lets Limitless Zoom press zoom keys in Logic, Pro Tools and other apps.",
             "state": self._accessibility(), "required": True},
            {"key": "input", "title": "Input Monitoring",
             "why": "Lets your zoom key and switch work in every app.",
             "state": self._input_monitoring(), "required": True},
            {"key": "microphone", "title": "Microphone",
             "why": "For voice commands. Audio is understood on this Mac and never sent anywhere.",
             "state": "missing" if mic == "ask" else mic, "required": False},
            {"key": "zoom", "title": "Screen zoom shortcuts",
             "why": "In Accessibility > Zoom, turn on \"Use keyboard shortcuts to zoom\" so the "
                    "whole screen can zoom outside your DAW.",
             "state": self._zoom_shortcuts(), "required": False},
        ]

    def request_permission(self, key):
        if key == "accessibility":
            try:
                from ApplicationServices import AXIsProcessTrustedWithOptions, kAXTrustedCheckOptionPrompt

                AXIsProcessTrustedWithOptions({kAXTrustedCheckOptionPrompt: True})
            except Exception:
                pass
            self._open(self.SETTINGS + "Accessibility")
        elif key == "input":
            try:
                if self._iokit().IOHIDRequestAccess(1):
                    return
            except Exception:
                pass
            self._open(self.SETTINGS + "ListenEvent")
        elif key == "microphone":
            if self._microphone() == "ask":
                try:
                    from AVFoundation import AVCaptureDevice, AVMediaTypeAudio

                    AVCaptureDevice.requestAccessForMediaType_completionHandler_(
                        AVMediaTypeAudio, lambda granted: None)
                    return
                except Exception:
                    pass
            self._open(self.SETTINGS + "Microphone")
        elif key == "zoom":
            self._open("x-apple.systempreferences:com.apple.preference.universalaccess?Seeing_Zoom")

    def _open(self, url):
        subprocess.Popen(["open", url])

    # Open at login: a LaunchAgent that opens the app bundle ------------------------

    def _bundle(self):
        exe = Path(sys.executable)
        return exe.parents[2] if getattr(sys, "frozen", False) and exe.parent.name == "MacOS" else None

    def _agent(self):
        return Path.home() / "Library" / "LaunchAgents" / "org.limitlesssound.zoom.plist"

    def can_open_at_login(self):
        return self._bundle() is not None

    def open_at_login(self):
        return self._agent().exists()

    def set_open_at_login(self, on):
        import plistlib

        agent = self._agent()
        if on and self._bundle():
            agent.parent.mkdir(parents=True, exist_ok=True)
            with open(agent, "wb") as f:
                plistlib.dump({"Label": "org.limitlesssound.zoom", "RunAtLoad": True,
                               "ProgramArguments": ["/usr/bin/open", "-a", str(self._bundle())]}, f)
        elif not on and agent.exists():
            agent.unlink()


class WinBackend(Backend):
    os_name = "win"

    def __init__(self):
        super().__init__()
        from ctypes import wintypes

        self.wt = wintypes
        self.user32 = ctypes.windll.user32
        self.kernel32 = ctypes.windll.kernel32
        self.user32.GetForegroundWindow.restype = wintypes.HWND

    def frontmost(self):
        hwnd = self.user32.GetForegroundWindow()
        if not hwnd:
            return None, None
        pid = self.wt.DWORD()
        self.user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        name = None
        h = self.kernel32.OpenProcess(0x1000, False, pid.value)  # QUERY_LIMITED_INFORMATION
        if h:
            buf = ctypes.create_unicode_buffer(1024)
            size = self.wt.DWORD(1024)
            if self.kernel32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(size)):
                name = os.path.basename(buf.value)
            self.kernel32.CloseHandle(h)
        return name, (hwnd, pid.value)

    def is_self(self, handle):
        return handle is not None and handle[1] == os.getpid()

    def activate(self, handle):
        hwnd = handle[0]
        # Windows only lets the app that last had input change the foreground
        # window; a tap of Alt counts as input.
        self.user32.keybd_event(0x12, 0, 0, 0)
        self.user32.keybd_event(0x12, 0, 2, 0)
        self.user32.SetForegroundWindow(hwnd)

    RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"

    def can_open_at_login(self):
        return getattr(sys, "frozen", False)

    def open_at_login(self):
        import winreg

        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, self.RUN_KEY) as k:
                winreg.QueryValueEx(k, "Limitless Zoom")
            return True
        except OSError:
            return False

    def set_open_at_login(self, on):
        import winreg

        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, self.RUN_KEY, 0, winreg.KEY_SET_VALUE) as k:
            if on:
                winreg.SetValueEx(k, "Limitless Zoom", 0, winreg.REG_SZ, f'"{sys.executable}"')
            else:
                try:
                    winreg.DeleteValue(k, "Limitless Zoom")
                except OSError:
                    pass

    def prepare_panel(self, widget):
        hwnd = int(widget.winId())
        GWL_EXSTYLE, WS_EX_NOACTIVATE, WS_EX_TOPMOST = -20, 0x08000000, 0x00000008
        style = self.user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
        self.user32.SetWindowLongW(hwnd, GWL_EXSTYLE, style | WS_EX_NOACTIVATE | WS_EX_TOPMOST)


class LinuxBackend(Backend):
    os_name = "linux"

    def __init__(self):
        super().__init__()
        self.xdotool = shutil.which("xdotool")

    def frontmost(self):
        if not self.xdotool:
            return None, None
        try:
            wid = subprocess.run([self.xdotool, "getactivewindow"], capture_output=True,
                                 text=True, timeout=1).stdout.strip()
            pid = subprocess.run([self.xdotool, "getwindowpid", wid], capture_output=True,
                                 text=True, timeout=1).stdout.strip()
            with open(f"/proc/{pid}/comm") as f:
                return f.read().strip(), (wid, int(pid))
        except Exception:
            return None, None

    def is_self(self, handle):
        return handle is not None and handle[1] == os.getpid()

    def activate(self, handle):
        if self.xdotool and handle:
            subprocess.run([self.xdotool, "windowactivate", handle[0]], timeout=1)


def get_backend():
    name = os_name()
    if name == "mac":
        return MacBackend()
    if name == "win":
        return WinBackend()
    return LinuxBackend()
