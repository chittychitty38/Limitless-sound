"""Key names, key-combo strings, and the native key codes for each OS.

A combo is written the way people read it: "cmd+right", "alt+cmd+=", "win+esc".
Key names are lower case: letters, digits, punctuation, f1-f20, arrows, etc.
"""

MODIFIERS = {
    "cmd": "cmd", "command": "cmd", "meta": "cmd",
    "ctrl": "ctrl", "control": "ctrl",
    "alt": "alt", "option": "alt", "opt": "alt",
    "shift": "shift",
    "win": "win", "super": "win", "start": "win",
}

ALIASES = {
    "escape": "esc", "return": "enter", "plus": "=", "minus": "-",
    "arrowleft": "left", "arrowright": "right", "arrowup": "up", "arrowdown": "down",
    "page_up": "pageup", "page_down": "pagedown", "scrolllock": "scroll_lock",
}


def normalize_key(name):
    name = name.strip().lower()
    return ALIASES.get(name, name)


def parse_combo(text):
    """'alt+cmd+=' -> (('alt', 'cmd'), '=')"""
    text = text.strip().lower()
    # A trailing '+' means the key itself is '+', written as 'plus'.
    if text.endswith("++"):
        text = text[:-2] + "+plus"
    elif text == "+":
        text = "plus"
    parts = [p for p in text.split("+") if p]
    if not parts:
        raise ValueError("empty key combo")
    *mods, key = parts
    out = []
    for m in mods:
        if m not in MODIFIERS:
            raise ValueError(f"unknown modifier {m!r} in {text!r}")
        out.append(MODIFIERS[m])
    return tuple(out), normalize_key(key)


def format_key(name):
    """Human-readable key name for on-screen text and speech."""
    pretty = {"esc": "Escape", "scroll_lock": "Scroll Lock", "pause": "Pause",
              "space": "Space", "enter": "Enter", "tab": "Tab"}
    if name in pretty:
        return pretty[name]
    if len(name) > 1 and name[0] == "f" and name[1:].isdigit():
        return name.upper()
    return name.upper() if len(name) == 1 else name.title()


# macOS virtual key codes (kVK_*), which are positional (US layout).
MAC_KEYCODES = {
    "a": 0, "s": 1, "d": 2, "f": 3, "h": 4, "g": 5, "z": 6, "x": 7, "c": 8, "v": 9,
    "b": 11, "q": 12, "w": 13, "e": 14, "r": 15, "y": 16, "t": 17,
    "1": 18, "2": 19, "3": 20, "4": 21, "6": 22, "5": 23, "=": 24, "9": 25, "7": 26,
    "-": 27, "8": 28, "0": 29, "]": 30, "o": 31, "u": 32, "[": 33, "i": 34, "p": 35,
    "l": 37, "j": 38, "'": 39, "k": 40, ";": 41, "\\": 42, ",": 43, "/": 44,
    "n": 45, "m": 46, ".": 47, "tab": 48, "space": 49, "`": 50, "backspace": 51,
    "enter": 36, "esc": 53,
    "f1": 122, "f2": 120, "f3": 99, "f4": 118, "f5": 96, "f6": 97, "f7": 98,
    "f8": 100, "f9": 101, "f10": 109, "f11": 103, "f12": 111, "f13": 105,
    "f14": 107, "f15": 113, "f16": 106, "f17": 64, "f18": 79, "f19": 80, "f20": 90,
    "left": 123, "right": 124, "down": 125, "up": 126,
    "home": 115, "end": 119, "pageup": 116, "pagedown": 121, "delete": 117,
}

# Windows virtual-key codes (VK_*).
WIN_VK = {
    **{chr(c): c - 32 for c in range(ord("a"), ord("z") + 1)},
    **{str(d): 0x30 + d for d in range(10)},
    **{f"f{n}": 0x6F + n for n in range(1, 25)},
    "=": 0xBB, "-": 0xBD, "]": 0xDD, "[": 0xDB, ";": 0xBA, "'": 0xDE, ",": 0xBC,
    ".": 0xBE, "/": 0xBF, "\\": 0xDC, "`": 0xC0,
    "tab": 0x09, "space": 0x20, "enter": 0x0D, "backspace": 0x08, "esc": 0x1B,
    "left": 0x25, "up": 0x26, "right": 0x27, "down": 0x28,
    "home": 0x24, "end": 0x23, "pageup": 0x21, "pagedown": 0x22,
    "insert": 0x2D, "delete": 0x2E, "pause": 0x13, "scroll_lock": 0x91,
}

MAC_BY_CODE = {v: k for k, v in MAC_KEYCODES.items()}
WIN_BY_VK = {v: k for k, v in WIN_VK.items()}
