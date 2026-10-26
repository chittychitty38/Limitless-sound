"""The code that differs per operating system: catching shortcuts everywhere,
pressing keys, menus and buttons in other apps, watching plugin-window clicks,
permissions and open at login. The Mac is the real target; Linux is for tests."""

import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

from .keys import MAC_BY_CODE, MAC_KEYCODES, flags_for, mods_from_flags
from .settings import os_name


class Backend:
    os_name = "linux"
    ax = None             # the Accessibility helpers, on a Mac

    def frontmost(self):
        """(app_id, pid) of the app in front, or (None, None)."""
        return None, None

    def app_id_for_pid(self, pid):
        return None

    def is_self(self, pid):
        return pid == os.getpid()

    def running_apps(self):
        """[(name, app_id)] of apps with windows, for adding an app's own shortcuts."""
        return []

    def send(self, combo, pid=None):
        raise RuntimeError("Pressing keys needs a Mac")

    def type_text(self, text):
        raise RuntimeError("Typing needs a Mac")

    def press_menu(self, pid, path):
        return False, "Choosing menu items needs a Mac."

    def press_button(self, pid, name):
        return False, "Pressing buttons needs a Mac."

    def window_report(self, pid):
        return ""

    def start_keys(self, engine):
        """Start catching shortcuts system-wide. Returns something with stop()."""
        return None

    def start_mouse(self, on_mouse):
        """on_mouse(x, y, kind) for left clicks ("down", "up") and scrolls."""
        return None

    def keep_responsive(self):
        pass

    def bring_to_front(self):
        pass

    def permissions(self):
        return []

    def request_permission(self, key):
        pass

    def can_open_at_login(self):
        return False

    def open_at_login(self):
        return False

    def set_open_at_login(self, on):
        pass

    def bundled_plugins(self):
        """The Uncommando plugins that came inside this app, if any."""
        places = [Path(__file__).resolve().parent.parent / "plugins"]
        if getattr(sys, "frozen", False):
            places = [Path(getattr(sys, "_MEIPASS", "")) / "plugins",
                      Path(sys.executable).resolve().parent.parent / "Resources" / "plugins"] + places
        for folder in places:
            if folder.is_dir():
                found = sorted(p for p in folder.iterdir()
                               if p.suffix in (".component", ".vst3", ".aaxplugin"))
                if found:
                    return found
        return []

    def install_plugins(self):
        return False, "Installing plugins needs a Mac."

    def reveal(self, path):
        pass


class MacBackend(Backend):
    os_name = "mac"

    def __init__(self):
        from . import macax

        self.ax = macax
        self._bundle_ids = {}

    # Apps ------------------------------------------------------------------------

    def frontmost(self):
        from AppKit import NSWorkspace

        app = NSWorkspace.sharedWorkspace().frontmostApplication()
        if app is None:
            return None, None
        pid = app.processIdentifier()
        app_id = app.bundleIdentifier() or app.localizedName()
        self._bundle_ids[pid] = app_id
        return app_id, pid

    def app_id_for_pid(self, pid):
        if not pid:
            return None
        if pid not in self._bundle_ids:
            from AppKit import NSRunningApplication

            app = NSRunningApplication.runningApplicationWithProcessIdentifier_(pid)
            self._bundle_ids[pid] = (app.bundleIdentifier() or app.localizedName()) if app else None
        return self._bundle_ids[pid]

    def running_apps(self):
        from AppKit import NSWorkspace

        out = []
        for app in NSWorkspace.sharedWorkspace().runningApplications():
            if app.activationPolicy() == 0 and app.bundleIdentifier():
                out.append((app.localizedName() or app.bundleIdentifier(), app.bundleIdentifier()))
        return sorted(set(out), key=lambda a: a[0].lower())

    def pid_for(self, daw_key):
        """The process id of a running DAW, e.g. 'logic'."""
        from AppKit import NSWorkspace

        from .daws import find_daw

        for app in NSWorkspace.sharedWorkspace().runningApplications():
            if find_daw(app.bundleIdentifier()) == daw_key:
                return app.processIdentifier()
        return None

    def activate(self, pid):
        from AppKit import NSRunningApplication

        app = NSRunningApplication.runningApplicationWithProcessIdentifier_(pid)
        if app is not None:
            app.activateWithOptions_(1 << 1)

    # Pressing keys -------------------------------------------------------------------

    def send(self, combo, pid=None):
        import Quartz

        # A private event source: the keys you're holding down to trigger the
        # shortcut don't mix into the keys it presses.
        src = Quartz.CGEventSourceCreate(Quartz.kCGEventSourceStatePrivate)
        code, flags = MAC_KEYCODES[combo.key], flags_for(combo.mods)
        for down in (True, False):
            ev = Quartz.CGEventCreateKeyboardEvent(src, code, down)
            Quartz.CGEventSetFlags(ev, flags)
            Quartz.CGEventPost(Quartz.kCGHIDEventTap, ev)
            time.sleep(0.008)
        time.sleep(0.02)

    def type_text(self, text):
        import Quartz

        src = Quartz.CGEventSourceCreate(Quartz.kCGEventSourceStatePrivate)
        for i in range(0, len(text), 16):
            chunk = text[i:i + 16]
            for down in (True, False):
                ev = Quartz.CGEventCreateKeyboardEvent(src, 0, down)
                Quartz.CGEventSetFlags(ev, 0)
                Quartz.CGEventKeyboardSetUnicodeString(ev, len(chunk.encode("utf-16-le")) // 2, chunk)
                Quartz.CGEventPost(Quartz.kCGHIDEventTap, ev)
            time.sleep(0.01)

    def press_menu(self, pid, path):
        if not pid:
            return False, "No app is in front."
        return self.ax.press_menu(pid, path)

    def press_button(self, pid, name):
        if not pid:
            return False, "No app is in front."
        return self.ax.press_button(pid, name)

    def window_report(self, pid):
        win = self.ax.front_window(pid) if pid else None
        return self.ax.report(win) if win is not None else "No window in front."

    # Catching shortcuts and clicks ------------------------------------------------------

    def start_keys(self, engine):
        import Quartz
        from pynput import keyboard

        me = os.getpid()
        get = Quartz.CGEventGetIntegerValueField

        def intercept(event_type, event):
            if event_type not in (Quartz.kCGEventKeyDown, Quartz.kCGEventKeyUp):
                return event
            if get(event, Quartz.kCGEventSourceUnixProcessID) == me:
                return event      # keys this app pressed itself
            try:
                key = MAC_BY_CODE.get(get(event, Quartz.kCGKeyboardEventKeycode))
                mods = mods_from_flags(Quartz.CGEventGetFlags(event))
                repeat = bool(get(event, Quartz.kCGKeyboardEventAutorepeat))
                pid = get(event, Quartz.kCGEventTargetUnixProcessID)
                app_id = self.app_id_for_pid(pid) if pid else None
                if app_id is None:
                    app_id, pid = self.frontmost()
                hide = engine.handle(mods, key, event_type == Quartz.kCGEventKeyDown, repeat, app_id, pid)
            except Exception:
                return event      # never lose a key because of a mistake here
            return None if hide else event

        listener = keyboard.Listener(darwin_intercept=intercept)
        listener.daemon = True
        listener.start()
        return listener

    def start_mouse(self, on_mouse):
        from pynput import mouse

        def click(x, y, button, pressed):
            if button == mouse.Button.left:
                on_mouse(x, y, "down" if pressed else "up")

        def scroll(x, y, dx, dy):
            on_mouse(x, y, "scroll")

        listener = mouse.Listener(on_click=click, on_scroll=scroll)
        listener.daemon = True
        listener.start()
        return listener

    def keep_responsive(self):
        # Uncommando works from behind the DAW, where App Nap would slow it down.
        try:
            from Foundation import NSProcessInfo

            self._activity = NSProcessInfo.processInfo().beginActivityWithOptions_reason_(
                0x00EFFFFF | 0xFF00000000, "Answering shortcuts")
        except Exception:
            self._activity = None

    def bring_to_front(self):
        try:
            from AppKit import NSApplication

            NSApplication.sharedApplication().activateIgnoringOtherApps_(True)
        except Exception:
            pass

    # Permissions ------------------------------------------------------------------------

    SETTINGS = "x-apple.systempreferences:com.apple.preference.security?Privacy_"

    def _accessibility(self):
        try:
            from ApplicationServices import AXIsProcessTrusted

            return "ok" if AXIsProcessTrusted() else "missing"
        except Exception:
            return "unknown"

    def _iokit(self):
        import ctypes

        lib = ctypes.cdll.LoadLibrary("/System/Library/Frameworks/IOKit.framework/IOKit")
        lib.IOHIDCheckAccess.restype = ctypes.c_int
        lib.IOHIDCheckAccess.argtypes = [ctypes.c_int]
        lib.IOHIDRequestAccess.restype = ctypes.c_bool
        lib.IOHIDRequestAccess.argtypes = [ctypes.c_int]
        return lib

    def _input_monitoring(self):
        try:
            return "ok" if self._iokit().IOHIDCheckAccess(1) == 0 else "missing"
        except Exception:
            return "unknown"

    def permissions(self):
        return [
            {"key": "accessibility", "title": "Accessibility",
             "why": "Lets your shortcuts press keys, menus and plugin Undo buttons in Logic, "
                    "Pro Tools and other apps.",
             "state": self._accessibility(), "required": True},
            {"key": "input", "title": "Input Monitoring",
             "why": "Lets Uncommando notice your shortcuts in every app.",
             "state": self._input_monitoring(), "required": True},
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

    def _open(self, url):
        subprocess.Popen(["open", url])

    def reveal(self, path):
        subprocess.Popen(["open", "-R", str(path)])

    # Open at login -------------------------------------------------------------------

    def _bundle(self):
        exe = Path(sys.executable)
        return exe.parents[2] if getattr(sys, "frozen", False) and exe.parent.name == "MacOS" else None

    def _agent(self):
        return Path.home() / "Library" / "LaunchAgents" / "org.limitlesssound.uncommando.plist"

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
                plistlib.dump({"Label": "org.limitlesssound.uncommando", "RunAtLoad": True,
                               "ProgramArguments": ["/usr/bin/open", "-a", str(self._bundle())]}, f)
        elif not on and agent.exists():
            agent.unlink()

    # The Uncommando plugin ----------------------------------------------------------

    def install_plugins(self):
        """Copies the bundled AU and VST3 into your own plug-in folders."""
        plugins = self.bundled_plugins()
        if not plugins:
            return False, "This copy of Uncommando has no plugin inside. See the README to build it."
        lib = Path.home() / "Library" / "Audio" / "Plug-Ins"
        where = {".component": lib / "Components", ".vst3": lib / "VST3"}
        done, aax = [], []
        for p in plugins:
            if p.suffix == ".aaxplugin":
                aax.append(p)
                continue
            dest_dir = where.get(p.suffix)
            if dest_dir is None:
                continue
            dest_dir.mkdir(parents=True, exist_ok=True)
            dest = dest_dir / p.name
            if dest.exists():
                shutil.rmtree(dest)
            shutil.copytree(p, dest, symlinks=True)
            subprocess.run(["xattr", "-dr", "com.apple.quarantine", str(dest)], capture_output=True)
            done.append(dest.name)
        if aax:
            # Pro Tools only looks in a shared folder, which needs your password.
            target = "/Library/Application Support/Avid/Audio/Plug-Ins"
            cmds = [f"mkdir -p '{target}'"] + [f"rm -rf '{target}/{p.name}' && cp -R '{p}' '{target}/'"
                                                for p in aax]
            script = f'do shell script "{" && ".join(cmds)}" with administrator privileges'
            r = subprocess.run(["osascript", "-e", script], capture_output=True, text=True)
            if r.returncode == 0:
                done += [p.name for p in aax]
        if not done:
            return False, "Nothing was installed."
        # Logic finds new Audio Units the next time it opens.
        subprocess.run(["killall", "-9", "AudioComponentRegistrar"], capture_output=True)
        return True, "Installed " + ", ".join(done) + ". Restart your DAW to see the Uncommando plugin."


class LinuxBackend(Backend):
    """For trying things out and for tests. X11 can't keep a key from other apps."""

    def __init__(self):
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
                return f.read().strip(), int(pid)
        except Exception:
            return None, None

    def start_keys(self, engine):
        from pynput import keyboard

        held = set()

        def event(k, down):
            name = getattr(k, "char", None) or getattr(k, "name", None)
            if name in ("cmd", "cmd_l", "cmd_r", "ctrl", "ctrl_l", "ctrl_r", "alt", "alt_l", "alt_r",
                        "alt_gr", "shift", "shift_l", "shift_r"):
                base = name.split("_")[0].replace("gr", "")
                (held.add if down else held.discard)(base)
                return
            if name:
                app_id, pid = self.frontmost()
                engine.handle(frozenset(held), str(name).lower(), down, False, app_id, pid)

        listener = keyboard.Listener(on_press=lambda k: event(k, True),
                                     on_release=lambda k: event(k, False))
        listener.daemon = True
        listener.start()
        return listener


def get_backend():
    name = os_name()
    if name == "mac":
        return MacBackend()
    return LinuxBackend()
