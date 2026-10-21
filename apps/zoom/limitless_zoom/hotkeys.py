"""System-wide keys: the one-handed zoom layer, the accessibility switch,
and "press the key you want to use" capture.

KeyLogic decides what each key press means and whether to hide it from other
apps. GlobalKeys feeds it real key events on each OS.
"""

import os
import threading
import time

from .keys import MAC_BY_CODE, WIN_BY_VK, normalize_key

REPEAT_GAP = 0.12  # seconds between actions while a layer key is held down


class KeyLogic:
    def __init__(self, layer_key, switch_key, layer_map, on_action, on_layer, on_switch,
                 clock=time.monotonic):
        self.layer_key = normalize_key(layer_key)
        self.switch_key = normalize_key(switch_key)
        self.layer_map = {normalize_key(k): v for k, v in layer_map.items()}
        self.on_action, self.on_layer, self.on_switch = on_action, on_layer, on_switch
        self.clock = clock
        self.layer_on = False
        self.down = set()
        self.last_fire = {}
        self.capture = None  # callback waiting for the next key press
        self.lock = threading.Lock()

    def set_layer(self, on):
        with self.lock:
            changed = self.layer_on != on
            self.layer_on = on
        if changed:
            self.on_layer(on)

    def capture_next(self, callback):
        self.capture = callback

    def handle(self, name, is_down, has_mods):
        """Returns True if the key should be hidden from other apps."""
        if name is None:
            return False
        repeat = is_down and name in self.down
        if is_down:
            self.down.add(name)
        else:
            self.down.discard(name)

        if self.capture is not None and is_down:
            cb, self.capture = self.capture, None
            cb(name)
            return True

        if name == self.switch_key and not has_mods:
            if is_down and not repeat:
                self.on_switch()
            return True

        if name == self.layer_key and not has_mods:
            if is_down and not repeat:
                self.set_layer(not self.layer_on)
            return True

        if self.layer_on and not has_mods:
            if name == "esc":
                if is_down:
                    self.set_layer(False)
                return True
            action = self.layer_map.get(name)
            if action:
                if is_down:
                    now = self.clock()
                    if not repeat or now - self.last_fire.get(name, 0) >= REPEAT_GAP:
                        self.last_fire[name] = now
                        self.on_action(action)
                return True
        return False


class GlobalKeys:
    """Listens to the whole keyboard. Needs Accessibility + Input Monitoring on macOS."""

    def __init__(self, logic, os_name):
        self.logic, self.os_name = logic, os_name
        self.listener = None

    def start(self):
        from pynput import keyboard

        if self.os_name == "mac":
            self.listener = keyboard.Listener(darwin_intercept=self._mac_intercept)
        elif self.os_name == "win":
            self.listener = keyboard.Listener(win32_event_filter=self._win_filter)
        else:
            # X11 can't hide keys from other apps, so layer keys also reach the
            # app in front. Fine for testing; Mac and Windows are the targets.
            self.listener = keyboard.Listener(on_press=lambda k: self._x_event(k, True),
                                              on_release=lambda k: self._x_event(k, False))
        self.listener.daemon = True
        self.listener.start()

    def stop(self):
        if self.listener:
            self.listener.stop()

    def _mac_intercept(self, event_type, event):
        import Quartz

        if event_type not in (Quartz.kCGEventKeyDown, Quartz.kCGEventKeyUp):
            return event
        # Ignore the keys this app presses itself (e.g. "z" for Logic's fit).
        if Quartz.CGEventGetIntegerValueField(event, Quartz.kCGEventSourceUnixProcessID) == os.getpid():
            return event
        code = Quartz.CGEventGetIntegerValueField(event, Quartz.kCGKeyboardEventKeycode)
        flags = Quartz.CGEventGetFlags(event)
        has_mods = bool(flags & (Quartz.kCGEventFlagMaskCommand | Quartz.kCGEventFlagMaskControl
                                 | Quartz.kCGEventFlagMaskAlternate))
        hide = self.logic.handle(MAC_BY_CODE.get(code), event_type == Quartz.kCGEventKeyDown, has_mods)
        return None if hide else event

    def _win_filter(self, msg, data):
        if data.flags & 0x10:  # LLKHF_INJECTED: our own key presses
            return True
        if msg not in (0x100, 0x101, 0x104, 0x105):
            return True
        import ctypes

        state = ctypes.windll.user32.GetAsyncKeyState
        has_mods = any(state(vk) & 0x8000 for vk in (0x11, 0x12, 0x5B, 0x5C))
        if self.logic.handle(WIN_BY_VK.get(data.vkCode), msg in (0x100, 0x104), has_mods):
            self.listener.suppress_event()
        return True

    def _x_event(self, key, is_down):
        name = getattr(key, "char", None) or getattr(key, "name", None)
        if name:
            self.logic.handle(normalize_key(name), is_down, False)
