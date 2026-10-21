"""Key names shared by the engine, and how they map to Mac and Windows key codes.

The engine only ever sees the canonical names on the left. Each platform
backend translates its own codes to and from these names.
"""

# Canonical name -> macOS virtual keycode (ANSI layout, physical position).
MAC_CODES = {
    "a": 0, "s": 1, "d": 2, "f": 3, "h": 4, "g": 5, "z": 6, "x": 7, "c": 8, "v": 9,
    "b": 11, "q": 12, "w": 13, "e": 14, "r": 15, "y": 16, "t": 17,
    "1": 18, "2": 19, "3": 20, "4": 21, "6": 22, "5": 23, "equal_sign": 24, "9": 25,
    "7": 26, "hyphen": 27, "8": 28, "0": 29, "close_bracket": 30, "o": 31, "u": 32,
    "open_bracket": 33, "i": 34, "p": 35, "return_or_enter": 36, "l": 37, "j": 38,
    "quote": 39, "k": 40, "semicolon": 41, "backslash": 42, "comma": 43, "slash": 44,
    "n": 45, "m": 46, "period": 47, "tab": 48, "spacebar": 49, "grave": 50,
    "delete_or_backspace": 51, "escape": 53,
    "cmd_r": 54, "cmd_l": 55, "shift_l": 56, "caps_lock": 57, "alt_l": 58, "ctrl_l": 59,
    "shift_r": 60, "alt_r": 61, "ctrl_r": 62,
    "f13": 105, "f14": 107, "f15": 113, "f16": 106, "f17": 64, "f18": 79, "f19": 80,
    "left_arrow": 123, "right_arrow": 124, "down_arrow": 125, "up_arrow": 126,
}

# Canonical name -> Windows virtual-key code.
WIN_CODES = {
    **{ch: ord(ch.upper()) for ch in "abcdefghijklmnopqrstuvwxyz"},
    **{d: ord(d) for d in "0123456789"},
    "spacebar": 0x20, "return_or_enter": 0x0D, "delete_or_backspace": 0x08, "tab": 0x09,
    "escape": 0x1B, "caps_lock": 0x14,
    "left_arrow": 0x25, "up_arrow": 0x26, "right_arrow": 0x27, "down_arrow": 0x28,
    "semicolon": 0xBA, "equal_sign": 0xBB, "comma": 0xBC, "hyphen": 0xBD, "period": 0xBE,
    "slash": 0xBF, "grave": 0xC0, "open_bracket": 0xDB, "backslash": 0xDC,
    "close_bracket": 0xDD, "quote": 0xDE,
    "shift_l": 0xA0, "shift_r": 0xA1, "ctrl_l": 0xA2, "ctrl_r": 0xA3,
    "alt_l": 0xA4, "alt_r": 0xA5, "cmd_l": 0x5B, "cmd_r": 0x5C,
    "f13": 0x7C, "f14": 0x7D, "f15": 0x7E, "f16": 0x7F, "f17": 0x80, "f18": 0x81, "f19": 0x82,
}
# Windows also reports generic Shift/Ctrl/Alt codes from some devices.
WIN_GENERIC = {0x10: "shift_l", 0x11: "ctrl_l", 0x12: "alt_l"}

# Keys that need the "extended" flag when sent on Windows.
WIN_EXTENDED = {"left_arrow", "right_arrow", "up_arrow", "down_arrow", "ctrl_r", "alt_r",
                "cmd_l", "cmd_r"}

MODIFIER_KEYS = {"shift_l", "shift_r", "ctrl_l", "ctrl_r", "alt_l", "alt_r", "cmd_l", "cmd_r"}
SHIFT_KEYS = {"shift_l", "shift_r"}

# Layouts are written with Mac modifier names. On Windows, Pro Tools uses
# Ctrl for Command, Alt for Option and the Start key for Control.
MOD_TO_KEY = {
    "mac": {"command": "cmd_l", "shift": "shift_l", "option": "alt_l", "control": "ctrl_l"},
    "windows": {"command": "ctrl_l", "shift": "shift_l", "option": "alt_l", "control": "cmd_l"},
}

# Left key -> key in the same spot on the right half of the keyboard.
MIRROR = {
    "1": "0", "2": "9", "3": "8", "4": "7", "5": "6",
    "q": "p", "w": "o", "e": "i", "r": "u", "t": "y",
    "a": "semicolon", "s": "l", "d": "k", "f": "j", "g": "h",
    "z": "slash", "x": "period", "c": "comma", "v": "m", "b": "n",
    "tab": "delete_or_backspace",
}
MIRROR_BOTH_WAYS = {**MIRROR, **{v: k for k, v in MIRROR.items()}}

# The left half of the keyboard as shown in the app, row by row.
ROWS = [
    ["1", "2", "3", "4", "5"],
    ["q", "w", "e", "r", "t"],
    ["a", "s", "d", "f", "g"],
    ["z", "x", "c", "v", "b"],
]

KEY_CAPS = {
    "semicolon": ";", "slash": "/", "period": ".", "comma": ",", "quote": "'",
    "delete_or_backspace": "Delete", "tab": "Tab", "return_or_enter": "Return",
    "spacebar": "Space", "left_arrow": "←", "right_arrow": "→", "up_arrow": "↑",
    "down_arrow": "↓", "equal_sign": "=", "open_bracket": "[", "close_bracket": "]",
    "hyphen": "-", "grave": "`", "backslash": "\\", "caps_lock": "Caps Lock", "escape": "Esc",
}
MOD_CAPS = {
    "mac": {"command": "⌘", "shift": "⇧", "option": "⌥", "control": "⌃"},
    "windows": {"command": "Ctrl+", "shift": "Shift+", "option": "Alt+", "control": "Win+"},
}


def cap(key):
    return KEY_CAPS.get(key, key.upper())


def shortcut_text(send, mods, platform):
    return "".join(MOD_CAPS[platform][m] for m in mods) + cap(send)
