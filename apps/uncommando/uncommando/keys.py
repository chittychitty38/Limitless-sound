"""Key names and shortcuts.

A shortcut is written the way people read it: "alt+cmd+z", "shift+cmd+=", "f13".
Inside the app it is a Combo: the set of modifiers plus one key, so "cmd+alt+z"
and "alt+cmd+z" are the same shortcut.
"""

from typing import NamedTuple

MODIFIERS = {
    "cmd": "cmd", "command": "cmd", "meta": "cmd", "⌘": "cmd",
    "ctrl": "ctrl", "control": "ctrl", "⌃": "ctrl",
    "alt": "alt", "option": "alt", "opt": "alt", "⌥": "alt",
    "shift": "shift", "⇧": "shift",
}

# The order Mac menus show modifiers in: ⌃⌥⇧⌘.
MOD_ORDER = ("ctrl", "alt", "shift", "cmd")
MAC_SYMBOL = {"ctrl": "⌃", "alt": "⌥", "shift": "⇧", "cmd": "⌘"}
SPOKEN_MOD = {"ctrl": "Control", "alt": "Option", "shift": "Shift", "cmd": "Command"}

ALIASES = {
    "escape": "esc", "return": "enter", "plus": "=", "minus": "-",
    "arrowleft": "left", "arrowright": "right", "arrowup": "up", "arrowdown": "down",
    "page_up": "pageup", "page_down": "pagedown", "del": "backspace",
    "forwarddelete": "delete", "spacebar": "space", " ": "space",
    "←": "left", "→": "right", "↑": "up", "↓": "down",
}


class Combo(NamedTuple):
    mods: frozenset
    key: str

    def __str__(self):
        return "+".join([m for m in MOD_ORDER if m in self.mods] + [self.key])


def normalize_key(name):
    name = name.strip().lower() if name.strip() else name.lower()
    return ALIASES.get(name, name)


def parse_combo(text):
    """'alt+cmd+z' -> Combo({'alt', 'cmd'}, 'z'). Raises ValueError if it can't."""
    if isinstance(text, Combo):
        return text
    text = str(text).strip().lower()
    if text.endswith("++"):          # "cmd++": the key itself is "+"
        text = text[:-2] + "+plus"
    elif text == "+":
        text = "plus"
    parts = [p.strip() for p in text.split("+")]
    parts = [p for p in parts if p]
    if not parts:
        raise ValueError("empty shortcut")
    *mods, key = parts
    out = set()
    for m in mods:
        if m not in MODIFIERS:
            raise ValueError(f"unknown modifier {m!r} in {text!r}")
        out.add(MODIFIERS[m])
    key = normalize_key(key)
    if key in MODIFIERS:
        raise ValueError(f"{text!r} has no key, only modifiers")
    if key not in MAC_KEYCODES:
        raise ValueError(f"unknown key {key!r} in {text!r}")
    return Combo(frozenset(out), key)


def parse_sequence(value):
    """'cmd+a, cmd+c' or ['cmd+a', 'cmd+c'] -> [Combo, Combo]."""
    items = value if isinstance(value, (list, tuple)) else str(value).split(",")
    combos = [parse_combo(v) for v in items if str(v).strip()]
    if not combos:
        raise ValueError("no keys")
    return combos


KEY_SYMBOL = {"left": "←", "right": "→", "up": "↑", "down": "↓", "enter": "↩", "esc": "⎋",
              "tab": "⇥", "backspace": "⌫", "delete": "⌦", "space": "Space",
              "pageup": "Page Up", "pagedown": "Page Down", "home": "Home", "end": "End"}
SPOKEN_KEY = {"left": "Left Arrow", "right": "Right Arrow", "up": "Up Arrow", "down": "Down Arrow",
              "enter": "Return", "esc": "Escape", "tab": "Tab", "backspace": "Delete",
              "delete": "Forward Delete", "space": "Space", "=": "Equals", "-": "Minus",
              "[": "Left Bracket", "]": "Right Bracket", ";": "Semicolon", "'": "Quote",
              ",": "Comma", ".": "Period", "/": "Slash", "\\": "Backslash", "`": "Backtick",
              "pageup": "Page Up", "pagedown": "Page Down", "home": "Home", "end": "End"}


def _key_text(key, table):
    if key in table:
        return table[key]
    if len(key) > 1 and key[0] == "f" and key[1:].isdigit():
        return key.upper()
    if key.startswith("num"):
        return "Keypad " + key[3:].upper()
    return key.upper()


def format_combo(combo):
    """Combo -> '⌥⌘Z', the way Mac menus show it."""
    combo = parse_combo(combo)
    mods = "".join(MAC_SYMBOL[m] for m in MOD_ORDER if m in combo.mods)
    return mods + _key_text(combo.key, KEY_SYMBOL)


def speak_combo(combo):
    """Combo -> 'Option Command Z', for speech and screen readers."""
    combo = parse_combo(combo)
    words = [SPOKEN_MOD[m] for m in MOD_ORDER if m in combo.mods]
    return " ".join(words + [_key_text(combo.key, SPOKEN_KEY)])


# macOS virtual key codes (kVK_*). They are key positions on a US keyboard, so
# a shortcut means the same physical key whatever keyboard layout is chosen.
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
    # The number keypad, which many DAWs use for transport and markers.
    "num0": 82, "num1": 83, "num2": 84, "num3": 85, "num4": 86, "num5": 87,
    "num6": 88, "num7": 89, "num8": 91, "num9": 92, "num.": 65, "num*": 67,
    "num+": 69, "num-": 78, "num/": 75, "numenter": 76, "num=": 81, "numclear": 71,
}
MAC_BY_CODE = {v: k for k, v in MAC_KEYCODES.items()}

# Modifier bits in a Quartz event's flags (kCGEventFlagMask*).
MAC_FLAG = {"shift": 0x20000, "ctrl": 0x40000, "alt": 0x80000, "cmd": 0x100000}
MAC_MOD_KEYCODES = {"cmd": 55, "shift": 56, "alt": 58, "ctrl": 59}


def mods_from_flags(flags):
    return frozenset(m for m, bit in MAC_FLAG.items() if flags & bit)


def flags_for(mods):
    out = 0
    for m in mods:
        out |= MAC_FLAG[m]
    return out
