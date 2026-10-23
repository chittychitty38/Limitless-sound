"""Key chords: parse them from pack files or speech.

A chord is written like "cmd+shift+n", "space", "numpad*" or "f12".
Packs are written with Mac modifier names. On Windows they're translated
the way Avid and most cross-platform apps do it: Command becomes Ctrl,
Option becomes Alt, and Control becomes the Windows (Start) key.
"""

import re

# every spelling -> canonical modifier name
MODIFIERS = {
    "cmd": "cmd", "command": "cmd",
    "shift": "shift",
    "opt": "opt", "option": "opt", "alt": "opt",
    "ctrl": "ctrl", "control": "ctrl",
    "win": "win", "windows": "win", "start": "win",
}

NAMED_KEYS = {
    "return", "enter", "tab", "space", "delete", "escape", "esc", "forwarddelete",
    "home", "end", "pageup", "pagedown", "left", "right", "down", "up",
    *(f"f{i}" for i in range(1, 21)),
    *(f"numpad{i}" for i in range(10)),
    "numpad.", "numpad+", "numpad-", "numpad*", "numpad/", "numpad=",
    "numpadenter", "numpadclear",
    "volumeup", "volumedown", "mute", "playpause", "nexttrack", "previoustrack",
}

# Mac modifier -> Windows modifier
WINDOWS_MODIFIERS = {"cmd": "ctrl", "opt": "alt", "ctrl": "win", "shift": "shift", "win": "win"}
MAC_MODIFIERS = {"cmd": "cmd", "opt": "opt", "ctrl": "ctrl", "shift": "shift", "win": "cmd"}
# For chords the user speaks ("press control z"), the words mean the keys on
# their own keyboard, so Control stays Control on Windows.
WINDOWS_LITERAL = {"cmd": "ctrl", "opt": "alt", "ctrl": "ctrl", "shift": "shift", "win": "win"}

# What people say for each key ("command", "period", "november") is the language's: its
# keys section (languages/<code>.yaml).


class KeyChordError(ValueError):
    pass


def parse_chord(chord):
    """"cmd+shift+n" -> (["cmd", "shift"], "n"). Modifiers are canonical names."""
    # split on "+" only when something follows it, so "cmd++" and "numpad+" work
    parts = [p.lower() for p in re.split(r"\+(?=.)", chord.replace(" ", ""))]
    *mods, key = parts
    if not key:
        raise KeyChordError(f"no key in chord {chord!r}")
    try:
        mods = [MODIFIERS[m] for m in mods]
    except KeyError as e:
        raise KeyChordError(f"unknown modifier {e.args[0]!r} in {chord!r}") from None
    if len(key) != 1 and key not in NAMED_KEYS:
        raise KeyChordError(f"unknown key {key!r} in {chord!r}")
    return mods, key


def for_platform(mods, platform, literal=False):
    """Translate Mac-style modifiers for the platform we're running on."""
    if platform == "windows":
        table = WINDOWS_LITERAL if literal else WINDOWS_MODIFIERS
    else:
        table = MAC_MODIFIERS
    out = []
    for m in mods:
        t = table[m]
        if t not in out:
            out.append(t)
    return out


def spoken_to_chord(words, language=None):
    """"command shift n" -> "cmd+shift+n". Raises KeyChordError if unclear."""
    if language is None:
        from .language import ENGLISH as language
    names, letters = language.spoken_keys, language.letters
    tokens = words.lower().split()
    mods, key = [], None
    i = 0
    while i < len(tokens):
        if tokens[i] in language.f_keys and i + 1 < len(tokens) and tokens[i + 1].isdigit():
            tok, i = names.get("f" + tokens[i + 1]), i + 2   # "f 5" -> F5
        else:
            # the longest name that fits: "punto y coma" before "punto"
            for n in (3, 2, 1):
                said = " ".join(tokens[i:i + n])
                if n == 1 or i + n <= len(tokens) and said in names:
                    break
            if said in names:
                tok, i = names[said], i + n
            else:
                tok = letters.get(said) or (said if len(said) == 1 else None)
                i += 1
        if tok is None:
            raise KeyChordError(f"don't know the key {tokens[i - 1]!r}")
        if tok in ("cmd", "ctrl", "opt", "shift", "win"):
            mods.append(tok)
        elif key is None:
            key = tok
        else:
            raise KeyChordError("only one non-modifier key per chord")
    if key is None:
        raise KeyChordError("no key to press")
    return "+".join(mods + [key])


def spoken_vocabulary():
    """Every key name the English "press ..." command understands, for the recognizer."""
    from .language import ENGLISH
    return ENGLISH.key_vocabulary()
