"""System-wide keys: the one-handed zoom layer, the accessibility switch,
and "press the key you want to use" capture.

KeyLogic decides what each key press means and whether to hide it from other
apps. GlobalKeys feeds it real key events on each OS.
"""

import os
import threading
import time

from .keys import MAC_BY_CODE, MAC_RIGHT_MOD_BITS, MODIFIER_TAPS, WIN_BY_VK, normalize_key

REPEAT_GAP = 0.12  # seconds between actions while a layer key is held down
TAP_TIME = 0.6     # a modifier pressed and let go within this, alone, is a tap


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
        self.tap = None      # (modifier, time) while a modifier might become a tap
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
        if name in MODIFIER_TAPS:
            self._modifier(name, is_down)
            return False  # modifiers always reach other apps
        self.tap = None   # Right Option + another key is a shortcut, not a tap
        repeat = is_down and name in self.down
        if is_down:
            self.down.add(name)
        else:
            self.down.discard(name)

        if self.capture is not None and is_down:
            cb, self.capture = self.capture, None
            cb(None if name == "esc" else name)   # Escape cancels, so the keyboard alone can back out
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

    def _modifier(self, name, is_down):
        if is_down:
            self.tap = (name, self.clock())
            return
        tap, self.tap = self.tap, None
        if not tap or tap[0] != name or self.clock() - tap[1] > TAP_TIME:
            return
        if self.capture is not None:
            cb, self.capture = self.capture, None
            cb(name)
        elif name == self.switch_key:
            self.on_switch()
        elif name == self.layer_key:
            self.set_layer(not self.layer_on)


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

        if event_type == Quartz.kCGEventFlagsChanged:
            code = Quartz.CGEventGetIntegerValueField(event, Quartz.kCGKeyboardEventKeycode)
            name = MAC_BY_CODE.get(code)
            if name in MAC_RIGHT_MOD_BITS:
                down = bool(Quartz.CGEventGetFlags(event) & MAC_RIGHT_MOD_BITS[name])
                self.logic.handle(name, down, False)
            elif name is None:
                self.logic.tap = None  # another modifier joined in
            return event
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
        name = WIN_BY_VK.get(data.vkCode)
        if data.vkCode in (0xA0, 0xA2, 0xA4, 0x5B):  # left-hand modifiers break a tap
            self.logic.tap = None
            return True
        has_mods = any(state(vk) & 0x8000 for vk in (0x11, 0x12, 0x5B, 0x5C))
        if self.logic.handle(name, msg in (0x100, 0x104), has_mods):
            self.listener.suppress_event()
        return True

    def _x_event(self, key, is_down):
        name = getattr(key, "char", None) or getattr(key, "name", None)
        if name:
            self.logic.handle(normalize_key(name), is_down, False)
