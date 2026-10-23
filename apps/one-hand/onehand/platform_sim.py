"""Stand-in backend for systems without keyboard support (and for trying the window)."""

from .words import t

# Shown in the window, which puts it in the suite's language.
UNSUPPORTED = "Keyboard control works on Mac and Windows. This computer can only show the window."


class SimBackend:
    platform = "mac"

    def __init__(self, front_app=None, error=None, permissions=None):
        self.engine = None
        self._perms = permissions or {}
        self._front = front_app
        self._fail = error
        self.error = None

    def start(self, engine):
        self.engine = engine
        if self._fail:
            raise PermissionError(self._fail)

    def stop(self):
        pass

    def front_app(self):
        return self._front

    def play_sound(self, on):
        pass

    def speak(self, text):
        pass

    def permission_help(self):
        return t("This computer is not supported yet. The window works, but keys are not changed.")

    def open_permission_settings(self, which=None):
        pass

    def permission_status(self):
        return dict(self._perms)

    @property
    def running(self):
        return self.engine is not None and not self._fail

    def relaunch(self):
        pass

    def own_app_id(self):
        return "limitless.sim"

    def login_item_supported(self):
        return False

    def set_login_item(self, on):
        pass

    def float_window(self, widget):
        pass

    def announce(self, text):
        pass


def get_backend():
    import sys
    if sys.platform == "darwin":
        from .platform_mac import MacBackend
        return MacBackend()
    if sys.platform == "win32":
        from .platform_win import WindowsBackend
        return WindowsBackend()
    return SimBackend(error=UNSUPPORTED)
