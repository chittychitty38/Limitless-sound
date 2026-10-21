"""Linux (X11): keys through pynput. Useful for development; not a target yet."""

import subprocess

from .base import AppRef, Platform


class LinuxPlatform(Platform):
    os_name = "linux"

    def frontmost(self):
        try:
            name = subprocess.run(["xdotool", "getactivewindow", "getwindowname"],
                                  capture_output=True, text=True, timeout=1).stdout.strip()
        except (OSError, subprocess.TimeoutExpired):
            return None
        return AppRef(name) if name else None

    def open_app(self, name):
        subprocess.Popen([name.lower().replace(" ", "-")])
