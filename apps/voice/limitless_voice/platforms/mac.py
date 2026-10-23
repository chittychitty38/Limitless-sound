"""macOS: keys through pynput (Quartz events), apps through AppKit."""

import subprocess

from .base import AppRef, Platform
from ..words import t

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
            raise RuntimeError(t("Couldn't find an app called {name}", name=name))   # shown in the window

    def applescript(self, script):
        r = subprocess.run(["osascript", "-e", script], capture_output=True, text=True)
        if r.returncode != 0:
            raise RuntimeError(r.stderr.strip() or t("AppleScript failed"))
        return r.stdout.strip()

    # -- permissions -----------------------------------------------------

    def mic_permission(self):
        try:
            from AVFoundation import AVCaptureDevice, AVMediaTypeAudio
            status = AVCaptureDevice.authorizationStatusForMediaType_(AVMediaTypeAudio)
        except Exception:
            return "granted"  # can't tell; let the system prompt when the mic opens
        # 0 not determined, 1 restricted, 2 denied, 3 authorized
        return {0: "ask", 3: "granted"}.get(int(status), "denied")

    def request_mic_permission(self, done):
        try:
            from AVFoundation import AVCaptureDevice, AVMediaTypeAudio
            AVCaptureDevice.requestAccessForMediaType_completionHandler_(
                AVMediaTypeAudio, lambda granted: done(bool(granted)))
        except Exception:
            done(True)

    def control_permission(self):
        try:
            from ApplicationServices import AXIsProcessTrusted
            return bool(AXIsProcessTrusted())
        except Exception:
            return True  # can't tell; don't nag

    def request_control_permission(self):
        """Adds us to the Accessibility list and shows macOS's own prompt."""
        try:
            from ApplicationServices import AXIsProcessTrustedWithOptions, kAXTrustedCheckOptionPrompt
            AXIsProcessTrustedWithOptions({kAXTrustedCheckOptionPrompt: True})
        except Exception:
            self.open_settings(ACCESSIBILITY_PANE)

    def mic_settings_link(self):
        return MICROPHONE_PANE

    def control_settings_link(self):
        return ACCESSIBILITY_PANE

    def set_login_item(self, enabled):
        # macOS 13+: the app appears under System Settings > General > Login Items
        from ServiceManagement import SMAppService
        service = SMAppService.mainAppService()
        ok, err = (service.registerAndReturnError_(None) if enabled
                   else service.unregisterAndReturnError_(None))
        if not ok and err is not None:
            raise RuntimeError(str(err.localizedDescription()))

    def open_settings(self, link):
        subprocess.run(["open", link])
