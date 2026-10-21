"""Sends key presses to the app in front and speaks confirmations."""

from __future__ import annotations

import queue
import shutil
import subprocess
import threading
import time

from . import keys as keymod

# Virtual key codes for keypad keys, which pynput has no names for.
_KEYPAD_VK = {
    "mac": {
        "keypad0": 82, "keypad1": 83, "keypad2": 84, "keypad3": 85, "keypad4": 86,
        "keypad5": 87, "keypad6": 88, "keypad7": 89, "keypad8": 91, "keypad9": 92,
        "keypadenter": 76, "keypadplus": 69, "keypadminus": 78, "keypadmultiply": 67,
        "keypaddivide": 75, "keypaddecimal": 65,
    },
    "windows": {
        **{f"keypad{i}": 0x60 + i for i in range(10)},
        "keypadmultiply": 0x6A, "keypadplus": 0x6B, "keypadminus": 0x6D,
        "keypaddecimal": 0x6E, "keypaddivide": 0x6F,
    },
}


class KeySender:
    """Presses shortcuts with pynput (Quartz on Mac, SendInput on Windows, X11 on Linux)."""

    def __init__(self, log):
        self.log = log
        self.platform = keymod.platform_name()
        try:
            from pynput.keyboard import Controller, Key, KeyCode
        except Exception as exc:  # no display on Linux, missing permission, etc.
            self.log(f"Key sending unavailable: {exc}")
            self._kb = None
            return
        self._kb = Controller()
        self._Key, self._KeyCode = Key, KeyCode
        mod = Key.cmd if self.platform == "mac" else Key.ctrl
        self._mods = {"mod": mod, "ctrl": Key.ctrl, "alt": Key.alt, "shift": Key.shift, "win": Key.cmd}
        self._named = {
            "space": Key.space, "return": Key.enter, "enter": Key.enter, "tab": Key.tab,
            "delete": Key.backspace, "backspace": Key.backspace, "forwarddelete": Key.delete,
            "escape": Key.esc, "esc": Key.esc, "up": Key.up, "down": Key.down,
            "left": Key.left, "right": Key.right, "home": Key.home, "end": Key.end,
            "pageup": Key.page_up, "pagedown": Key.page_down,
            **{f"f{i}": getattr(Key, f"f{i}") for i in range(1, 13)},
        }

    def _key(self, name: str):
        if name in self._named:
            return self._named[name]
        vk = _KEYPAD_VK.get(self.platform, {}).get(name)
        if vk is not None:
            return self._KeyCode.from_vk(vk)
        if name == "keypadenter":
            return self._Key.enter
        if name.startswith("keypad"):
            # Linux: fall back to the matching main-keyboard key.
            fallback = {"plus": "=", "minus": "-", "multiply": "8", "divide": "/", "decimal": "."}
            rest = name[6:]
            return self._KeyCode.from_char(fallback.get(rest, rest))
        return self._KeyCode.from_char(name)

    def send(self, keys) -> None:
        text = keymod.resolve(keys, self.platform)
        if not text or self._kb is None:
            return
        try:
            mods, key = keymod.parse(text)
            held = [self._mods[m] for m in ("ctrl", "alt", "shift", "mod", "win") if m in mods]
            for m in held:
                self._kb.press(m)
            k = self._key(key)
            self._kb.press(k)
            time.sleep(0.01)
            self._kb.release(k)
            for m in reversed(held):
                self._kb.release(m)
        except Exception as exc:
            self.log(f'Could not send "{text}": {exc}')


class Speaker:
    """Speaks short confirmations on a background thread. Newer messages replace older ones."""

    def __init__(self, log):
        self.log = log
        self.platform = keymod.platform_name()
        self._queue: queue.Queue[str] = queue.Queue()
        self._proc = None
        threading.Thread(target=self._run, daemon=True, name="speech").start()

    def speak(self, text: str) -> None:
        self._queue.put(text)

    def _latest(self) -> str:
        text = self._queue.get()
        while not self._queue.empty():
            text = self._queue.get_nowait()
        return text

    def _run(self) -> None:
        if self.platform == "windows":
            self._run_windows()
            return
        cmd = None
        if self.platform == "mac":
            cmd = ["say", "-r", "230"]
        elif shutil.which("spd-say"):
            cmd = ["spd-say", "-w"]
        elif shutil.which("espeak-ng") or shutil.which("espeak"):
            cmd = [shutil.which("espeak-ng") or shutil.which("espeak")]
        while True:
            text = self._latest()
            if not cmd:
                continue
            if self._proc and self._proc.poll() is None:
                self._proc.terminate()
            try:
                self._proc = subprocess.Popen(cmd + [text], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            except OSError as exc:
                self.log(f"Speech unavailable: {exc}")
                cmd = None

    def _run_windows(self) -> None:
        # SAPI through COM; pyttsx3 wraps it and is bundled in the Windows build.
        try:
            import pyttsx3
            engine = pyttsx3.init()
            engine.setProperty("rate", 210)
        except Exception as exc:
            self.log(f"Speech unavailable: {exc}")
            while True:
                self._queue.get()
        while True:
            text = self._latest()
            try:
                engine.say(text)
                engine.runAndWait()
            except Exception as exc:
                self.log(f"Speech failed: {exc}")
