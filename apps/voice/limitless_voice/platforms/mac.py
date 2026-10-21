"""macOS: keys through pynput (Quartz events), apps through AppKit."""

import subprocess

from .base import AppRef, Platform

ACCESSIBILITY_PANE = "x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility"
MICROPHONE_PANE = "x-apple.systempreferences:com.apple.preference.security?Privacy_Microphone"


class MacPlatform(Platform):
    os_name = "mac"
    NUMPAD_VK = {
        "numpad0": 82, "numpad1": 83, "numpad2": 84, "numpad3": 85, "numpad4": 86,
        "numpad5": 87, "numpad6": 88, "numpad7": 89, "numpad8": 91, "numpad9": 92,
        "numpad.": 65, "numpad+": 69, "numpad-": 78, "numpad*": 67, "numpad/": 75,
        "numpad=": 81, "numpadenter": 76, "numpadclear": 71,
    }

    def frontmost(self):
        from AppKit import NSWorkspace
        app = NSWorkspace.sharedWorkspace().frontmostApplication()
        if app is None:
            return None
        return AppRef(str(app.localizedName()), int(app.processIdentifier()))

    def focus(self, app):
        from AppKit import NSApplicationActivateIgnoringOtherApps, NSRunningApplication
        running = NSRunningApplication.runningApplicationWithProcessIdentifier_(app.handle)
        return bool(running and running.activateWithOptions_(NSApplicationActivateIgnoringOtherApps))

    def open_app(self, name):
        r = subprocess.run(["open", "-a", name], capture_output=True, text=True)
        if r.returncode != 0:
            raise RuntimeError(f"Couldn't find an app called {name}")

    def applescript(self, script):
        r = subprocess.run(["osascript", "-e", script], capture_output=True, text=True)
        if r.returncode != 0:
            raise RuntimeError(r.stderr.strip() or "AppleScript failed")
        return r.stdout.strip()

    def permission_problems(self):
        problems = []
        try:
            from ApplicationServices import AXIsProcessTrusted
            trusted = AXIsProcessTrusted()
        except Exception:
            trusted = True  # can't tell; don't nag
        if not trusted:
            problems.append((
                "Allow Limitless Voice to control the computer",
                "Open Accessibility settings, turn on Limitless Voice, then come back. "
                "This is what lets spoken commands press keys in Logic and Pro Tools.",
                ACCESSIBILITY_PANE,
            ))
        return problems

    def open_settings(self, link):
        subprocess.run(["open", link])
