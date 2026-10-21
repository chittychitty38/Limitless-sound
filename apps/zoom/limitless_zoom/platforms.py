"""The small amount of code that differs per operating system:
which app is in front, bringing it back to the front, pressing keys,
and keeping the zoom panel from stealing focus from the DAW."""

import ctypes
import os
import shutil
import subprocess
import time

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

    def permission_problems(self):
        return []


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

    def permission_problems(self):
        problems = []
        try:
            from ApplicationServices import AXIsProcessTrustedWithOptions, kAXTrustedCheckOptionPrompt

            if not AXIsProcessTrustedWithOptions({kAXTrustedCheckOptionPrompt: True}):
                problems.append(
                    "Limitless Zoom needs Accessibility permission to press zoom keys. "
                    "Open System Settings > Privacy & Security > Accessibility and switch it on, "
                    "then also allow it under Input Monitoring.")
        except Exception:
            pass
        return problems


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
