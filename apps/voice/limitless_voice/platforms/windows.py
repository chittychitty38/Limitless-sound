"""Windows: keys through pynput (SendInput), apps through the Win32 API."""

import ctypes
import os
import time
from ctypes import wintypes
from pathlib import Path

from .base import AppRef, Platform

PROCESS_QUERY_LIMITED_INFORMATION = 0x1000

# Friendly names for common music apps' executables
EXE_NAMES = {
    "protools.exe": "Pro Tools",
    "ableton live 12 suite.exe": "Ableton Live", "ableton live 11 suite.exe": "Ableton Live",
    "studio one.exe": "Studio One", "reaper.exe": "REAPER", "cubase14.exe": "Cubase",
    "fl64.exe": "FL Studio", "bitwig studio.exe": "Bitwig Studio",
}


class WindowsPlatform(Platform):
    os_name = "windows"
    NUMPAD_VK = {
        **{f"numpad{i}": 0x60 + i for i in range(10)},
        "numpad*": 0x6A, "numpad+": 0x6B, "numpad-": 0x6D, "numpad.": 0x6E,
        "numpad/": 0x6F, "numpadclear": 0x0C,
    }

    def __init__(self):
        super().__init__()
        self.user32 = ctypes.windll.user32
        self.kernel32 = ctypes.windll.kernel32

    def frontmost(self):
        hwnd = self.user32.GetForegroundWindow()
        if not hwnd:
            return None
        pid = wintypes.DWORD()
        self.user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        handle = self.kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid.value)
        exe = ""
        if handle:
            try:
                buf = ctypes.create_unicode_buffer(1024)
                size = wintypes.DWORD(len(buf))
                if self.kernel32.QueryFullProcessImageNameW(handle, 0, buf, ctypes.byref(size)):
                    exe = os.path.basename(buf.value)
            finally:
                self.kernel32.CloseHandle(handle)
        name = EXE_NAMES.get(exe.lower()) or Path(exe).stem or "Unknown"
        return AppRef(name, hwnd)

    def focus(self, app):
        hwnd = app.handle
        if not hwnd:
            return False
        if self.user32.IsIconic(hwnd):
            self.user32.ShowWindow(hwnd, 9)  # SW_RESTORE
        ok = bool(self.user32.SetForegroundWindow(hwnd))
        time.sleep(0.05)
        return ok

    def open_app(self, name):
        """Find a Start menu shortcut whose name matches and launch it."""
        wanted = name.lower().replace(" ", "")
        roots = [
            Path(os.environ.get("PROGRAMDATA", r"C:\ProgramData")) / "Microsoft/Windows/Start Menu/Programs",
            Path(os.environ.get("APPDATA", "")) / "Microsoft/Windows/Start Menu/Programs",
        ]
        best = None
        for root in roots:
            if not root.exists():
                continue
            for lnk in root.rglob("*.lnk"):
                stem = lnk.stem.lower().replace(" ", "")
                if stem == wanted:
                    best = lnk
                    break
                if wanted in stem and (best is None or len(stem) < len(best.stem)):
                    best = lnk
            if best and best.stem.lower().replace(" ", "") == wanted:
                break
        if not best:
            raise RuntimeError(f"Couldn't find an app called {name}")
        os.startfile(str(best))

    def permission_problems(self):
        return []

    def open_settings(self, link):
        os.startfile(link)
