"""Which app is in front, so the right profile is used.

Returns a Mac bundle ID ("com.apple.logic10"), a Windows program file name
("protools.exe") or a Linux window class, all lower case. None if unknown.
"""

from __future__ import annotations

import shutil
import subprocess
import sys


def _mac():
    try:
        from AppKit import NSWorkspace
    except Exception:
        return lambda: None

    def get():
        app = NSWorkspace.sharedWorkspace().frontmostApplication()
        ident = app.bundleIdentifier() if app else None
        return str(ident).lower() if ident else None

    return get


def _windows():
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32
    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000

    def get():
        hwnd = user32.GetForegroundWindow()
        if not hwnd:
            return None
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid.value)
        if not handle:
            return None
        try:
            buf = ctypes.create_unicode_buffer(1024)
            size = wintypes.DWORD(len(buf))
            if not kernel32.QueryFullProcessImageNameW(handle, 0, buf, ctypes.byref(size)):
                return None
            return buf.value.replace("/", "\\").rsplit("\\", 1)[-1].lower()
        finally:
            kernel32.CloseHandle(handle)

    return get


def _linux():
    if not shutil.which("xdotool"):
        return lambda: None

    def get():
        try:
            out = subprocess.run(["xdotool", "getactivewindow", "getwindowclassname"],
                                 capture_output=True, text=True, timeout=0.5)
            return out.stdout.strip().lower() or None
        except Exception:
            return None

    return get


if sys.platform == "darwin":
    frontmost_app = _mac()
elif sys.platform.startswith("win"):
    frontmost_app = _windows()
else:
    frontmost_app = _linux()
