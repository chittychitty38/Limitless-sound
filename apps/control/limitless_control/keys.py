"""Shortcut strings such as "mod+shift+z" and how they become real key presses.

Modifiers:
  mod    Command on Mac, Ctrl on Windows and Linux (the "main" shortcut key)
  cmd    Command on Mac, Ctrl elsewhere (same as mod, for readability in Mac profiles)
  ctrl   the Control key on every system
  alt    Option on Mac, Alt elsewhere ("opt" and "option" also work)
  shift  Shift
  win    the Windows / Super key ("super" also works)

A profile can give different keys per system: {"mac": "ctrl+p", "windows": "win+p"}.
"""

from __future__ import annotations

import sys
from typing import Union

Keys = Union[str, dict]

MODIFIERS = {
    "mod": "mod", "cmd": "mod", "command": "mod",
    "ctrl": "ctrl", "control": "ctrl",
    "alt": "alt", "opt": "alt", "option": "alt",
    "shift": "shift",
    "win": "win", "super": "win",
}

NAMED = {
    "space", "return", "enter", "tab", "delete", "backspace", "forwarddelete", "escape", "esc",
    "up", "down", "left", "right", "home", "end", "pageup", "pagedown",
    *(f"f{i}" for i in range(1, 13)),
    *(f"keypad{i}" for i in range(10)),
    "keypadenter", "keypadplus", "keypadminus", "keypadmultiply", "keypaddivide", "keypaddecimal",
}

CHARS = set("abcdefghijklmnopqrstuvwxyz0123456789-=[]\\;',./`")


def platform_name() -> str:
    if sys.platform == "darwin":
        return "mac"
    if sys.platform.startswith("win"):
        return "windows"
    return "linux"


def resolve(keys: Keys, platform: str | None = None) -> str | None:
    """Pick the shortcut for this system from a string or a per-system dict."""
    if isinstance(keys, str):
        return keys
    if isinstance(keys, dict):
        platform = platform or platform_name()
        return keys.get(platform) or keys.get("default") or (keys.get("windows") if platform == "linux" else None)
    return None


def parse(text: str) -> tuple[frozenset, str]:
    """Split "mod+shift+z" into ({"mod", "shift"}, "z"). Raises ValueError if invalid."""
    mods: set[str] = set()
    key = None
    # "+" itself cannot be a key here; use keypadplus.
    for part in (p.strip().lower() for p in text.split("+")):
        if not part:
            raise ValueError(f'Empty part in "{text}"')
        if part in MODIFIERS:
            mods.add(MODIFIERS[part])
        elif part in NAMED or part in CHARS:
            if key is not None:
                raise ValueError(f'Two keys in "{text}"')
            key = part
        else:
            raise ValueError(f'Unknown key "{part}" in "{text}"')
    if key is None:
        raise ValueError(f'No key in "{text}"')
    return frozenset(mods), key


def describe(text: str, platform: str | None = None) -> str:
    """Human-readable form for the settings page, e.g. "⌘ Shift Z" or "Ctrl+Shift+Z"."""
    platform = platform or platform_name()
    mods, key = parse(text)
    mac = platform == "mac"
    names = {
        "mod": "⌘" if mac else "Ctrl", "ctrl": "Control" if mac else "Ctrl",
        "alt": "Option" if mac else "Alt", "shift": "Shift", "win": "Win",
    }
    order = ["ctrl", "alt", "shift", "mod", "win"] if mac else ["mod", "ctrl", "win", "alt", "shift"]
    parts = [names[m] for m in order if m in mods]
    # On Windows "mod" and "ctrl" are the same key.
    parts = list(dict.fromkeys(parts))
    parts.append(key.upper() if len(key) == 1 else key.capitalize())
    return (" " if mac else "+").join(parts)
