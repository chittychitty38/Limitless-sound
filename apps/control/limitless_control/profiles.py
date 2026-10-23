"""Built-in profiles, the action menus shown in settings, and saving the user's setup."""

from __future__ import annotations

import copy
import json
import os
import sys
from pathlib import Path

APP_NAME = "Limitless Control"
CONFIG_VERSION = 1

# Actions per app, offered as a pick list in settings. Keys use "mod" for
# Command (Mac) / Ctrl (Windows). A dict gives different keys per system.
CATALOG: dict[str, dict[str, dict]] = {
    "Logic Pro": {
        "play": {"label": "Play / stop", "keys": "space", "say": "Play stop"},
        "record": {"label": "Record", "keys": "r", "say": "Record"},
        "start": {"label": "Go to start", "keys": "return", "say": "Start"},
        "undo": {"label": "Undo", "keys": "mod+z", "say": "Undo"},
        "redo": {"label": "Redo", "keys": "mod+shift+z", "say": "Redo"},
        "cycle": {"label": "Cycle on/off", "keys": "c", "say": "Cycle"},
        "rewind": {"label": "Rewind", "keys": ","},
        "forward": {"label": "Forward", "keys": "."},
        "track_up": {"label": "Previous track", "keys": "up"},
        "track_down": {"label": "Next track", "keys": "down"},
        "mute": {"label": "Mute track", "keys": "m", "say": "Mute"},
        "solo": {"label": "Solo track", "keys": "s", "say": "Solo"},
        "arm": {"label": "Record-arm track", "keys": "ctrl+r", "say": "Armed"},
        "zoom_out": {"label": "Zoom out", "keys": "mod+left"},
        "zoom_in": {"label": "Zoom in", "keys": "mod+right"},
        "vzoom_out": {"label": "Zoom out vertically", "keys": "mod+up"},
        "vzoom_in": {"label": "Zoom in vertically", "keys": "mod+down"},
        "zoom_fit": {"label": "Zoom to fit", "keys": "z", "say": "Zoom to fit"},
        "metronome": {"label": "Metronome on/off", "keys": "k", "say": "Metronome"},
        "mixer": {"label": "Show mixer", "keys": "x", "say": "Mixer"},
        "editor": {"label": "Show editor", "keys": "e", "say": "Editor"},
        "inspector": {"label": "Show inspector", "keys": "i", "say": "Inspector"},
        "piano_roll": {"label": "Show piano roll", "keys": "p", "say": "Piano roll"},
        "library": {"label": "Show library", "keys": "y", "say": "Library"},
        "smart_controls": {"label": "Show smart controls", "keys": "b", "say": "Smart controls"},
        "save": {"label": "Save", "keys": "mod+s", "say": "Saved"},
        "prev_region": {"label": "Previous region", "keys": "left"},
        "next_region": {"label": "Next region", "keys": "right"},
    },
    "Pro Tools": {
        "play": {"label": "Play / stop", "keys": "space", "say": "Play stop"},
        "record": {"label": "Record", "keys": "f12", "say": "Record"},
        "start": {"label": "Go to start", "keys": "return", "say": "Start"},
        # Option+Return on a Mac (Alt on Windows); Command+Return isn't Go to end.
        "end": {"label": "Go to end", "keys": "alt+return", "say": "End"},
        "undo": {"label": "Undo", "keys": "mod+z", "say": "Undo"},
        "redo": {"label": "Redo", "keys": "mod+shift+z", "say": "Redo"},
        "arm": {"label": "Record-arm selected tracks", "keys": "shift+r", "say": "Armed"},
        "loop": {"label": "Loop playback on/off", "keys": "mod+shift+l", "say": "Loop playback"},
        "rewind": {"label": "Rewind (keypad 1)", "keys": "keypad1"},
        "forward": {"label": "Fast forward (keypad 2)", "keys": "keypad2"},
        "track_up": {"label": "Previous track", "keys": {"mac": "ctrl+p", "windows": "win+p"}},
        "track_down": {"label": "Next track", "keys": {"mac": "ctrl+;", "windows": "win+;"}},
        "mute": {"label": "Mute selected tracks", "keys": "shift+m", "say": "Mute"},
        "solo": {"label": "Solo selected tracks", "keys": "shift+s", "say": "Solo"},
        "zoom_out": {"label": "Zoom out", "keys": "mod+["},
        "zoom_in": {"label": "Zoom in", "keys": "mod+]"},
        "click": {"label": "Click on/off (keypad 7)", "keys": "keypad7", "say": "Click"},
        "mix_edit": {"label": "Switch Mix / Edit window", "keys": "mod+=", "say": "Mix edit"},
        "separate": {"label": "Separate clip", "keys": "mod+e", "say": "Separate"},
        "save": {"label": "Save", "keys": "mod+s", "say": "Saved"},
        "left": {"label": "Left arrow", "keys": "left"},
        "right": {"label": "Right arrow", "keys": "right"},
    },
    "Ableton Live": {
        "play": {"label": "Play / stop", "keys": "space", "say": "Play stop"},
        "record": {"label": "Arrangement record", "keys": "f9", "say": "Record"},
        "undo": {"label": "Undo", "keys": "mod+z", "say": "Undo"},
        # Live's redo differs by system (Ableton's shortcut chapter).
        "redo": {"label": "Redo", "keys": {"mac": "mod+shift+z", "windows": "mod+y"}, "say": "Redo"},
        "loop": {"label": "Loop selection", "keys": "mod+l", "say": "Loop"},
        "view": {"label": "Switch Session / Arrangement", "keys": "tab", "say": "Switch view"},
        "track_up": {"label": "Up", "keys": "up"},
        "track_down": {"label": "Down", "keys": "down"},
        "left": {"label": "Left", "keys": "left"},
        "right": {"label": "Right", "keys": "right"},
        "zoom_in": {"label": "Zoom in", "keys": "="},
        "zoom_out": {"label": "Zoom out", "keys": "-"},
        "activate": {"label": "Track on/off (mute)", "keys": "0", "say": "Track on off"},
        "save": {"label": "Save", "keys": "mod+s", "say": "Saved"},
    },
    "Everyday": {
        "enter": {"label": "Enter / OK", "keys": "return"},
        "escape": {"label": "Escape / cancel", "keys": "escape"},
        "space": {"label": "Space", "keys": "space"},
        "switch_app": {"label": "Switch app", "keys": {"mac": "cmd+tab", "windows": "alt+tab", "linux": "alt+tab"},
                       "say": "Switch app"},
        "up": {"label": "Up arrow", "keys": "up"},
        "down": {"label": "Down arrow", "keys": "down"},
        "left": {"label": "Left arrow", "keys": "left"},
        "right": {"label": "Right arrow", "keys": "right"},
        "tab": {"label": "Next item (Tab)", "keys": "tab"},
        "shift_tab": {"label": "Previous item (Shift Tab)", "keys": "shift+tab"},
        "zoom_in": {"label": "Zoom in", "keys": "mod+=", "say": "Zoom in"},
        "zoom_out": {"label": "Zoom out", "keys": "mod+-", "say": "Zoom out"},
        "undo": {"label": "Undo", "keys": "mod+z", "say": "Undo"},
        "save": {"label": "Save", "keys": "mod+s", "say": "Saved"},
    },
}

# Built-in commands, offered in every profile.
COMMANDS = {
    "layer": {"label": "Layer 2 for the next switch", "command": "layer"},
    "toggleEnabled": {"label": "Controller on / off", "command": "toggleEnabled"},
    "announce": {"label": "Say profile and layer", "command": "announce"},
}

APPS = {
    "Logic Pro": ["com.apple.logic10"],
    "Pro Tools": ["com.avid.protools", "protools.exe"],
    "Ableton Live": ["com.ableton.live", "ableton live*.exe"],
    "Everyday": ["*"],
}

# Default layouts: input -> (tap action, hold action, repeats).
# The Adaptive Controller's two big buttons are A (left) and B (right).
_LAYOUTS = {
    "Logic Pro": [
        {
            "a": ("play", None, False), "b": ("start", "record", False),
            "x": ("undo", "redo", False), "y": ("cycle", None, False),
            "dpad_up": ("track_up", None, True), "dpad_down": ("track_down", None, True),
            "dpad_left": ("rewind", None, True), "dpad_right": ("forward", None, True),
            "lb": ("mute", None, False), "rb": ("solo", None, False),
            "lt": ("zoom_out", None, True), "rt": ("zoom_in", None, True),
            "lstick_up": ("vzoom_out", None, True), "lstick_down": ("vzoom_in", None, True),
            "ls": ("metronome", None, False), "rs": ("mixer", None, False),
        },
        {
            "a": ("save", None, False), "x": ("zoom_fit", None, False), "y": ("editor", None, False),
            "b": ("arm", None, False),
            "lb": ("inspector", None, False), "rb": ("piano_roll", None, False),
            "lt": ("library", None, False), "rt": ("smart_controls", None, False),
            "dpad_left": ("prev_region", None, True), "dpad_right": ("next_region", None, True),
        },
    ],
    "Pro Tools": [
        {
            "a": ("play", None, False), "b": ("start", "record", False),
            "x": ("undo", "redo", False), "y": ("loop", None, False),
            "dpad_up": ("track_up", None, True), "dpad_down": ("track_down", None, True),
            "dpad_left": ("rewind", None, True), "dpad_right": ("forward", None, True),
            "lb": ("mute", None, False), "rb": ("solo", None, False),
            "lt": ("zoom_out", None, True), "rt": ("zoom_in", None, True),
            "ls": ("click", None, False), "rs": ("mix_edit", None, False),
        },
        {
            "a": ("save", None, False), "b": ("arm", None, False), "x": ("separate", None, False),
            "y": ("end", None, False),
            "dpad_left": ("left", None, True), "dpad_right": ("right", None, True),
        },
    ],
    "Ableton Live": [
        {
            "a": ("play", None, False), "b": (None, "record", False),
            "x": ("undo", "redo", False), "y": ("loop", None, False),
            "dpad_up": ("track_up", None, True), "dpad_down": ("track_down", None, True),
            "dpad_left": ("left", None, True), "dpad_right": ("right", None, True),
            "lb": ("activate", None, False), "rb": ("view", None, False),
            "lt": ("zoom_out", None, True), "rt": ("zoom_in", None, True),
        },
        {"a": ("save", None, False)},
    ],
    "Everyday": [
        {
            "a": ("enter", None, False), "b": ("escape", None, False),
            "x": ("switch_app", None, False), "y": ("space", None, False),
            "dpad_up": ("up", None, True), "dpad_down": ("down", None, True),
            "dpad_left": ("left", None, True), "dpad_right": ("right", None, True),
            "lb": ("shift_tab", None, True), "rb": ("tab", None, True),
            "lt": ("zoom_out", None, False), "rt": ("zoom_in", None, False),
        },
        {"a": ("save", None, False), "x": ("undo", None, False)},
    ],
}


# Timing presets offered in settings. "Steady" is the default.
TIMING_PRESETS = {
    "steady": {
        "label": "Steady hands",
        "timing": {"minPressSeconds": 0.05, "cooldownSeconds": 0.15, "longPressSeconds": 0.8,
                   "repeatDelaySeconds": 0.5, "repeatIntervalSeconds": 0.12},
        "analogThreshold": 0.6,
    },
    "some_tremor": {
        "label": "Some tremor or shaking",
        "timing": {"minPressSeconds": 0.08, "cooldownSeconds": 0.4, "longPressSeconds": 1.0,
                   "repeatDelaySeconds": 0.7, "repeatIntervalSeconds": 0.15},
        "analogThreshold": 0.65,
    },
    "strong_tremor": {
        "label": "Strong tremor, or presses that bounce",
        "timing": {"minPressSeconds": 0.12, "cooldownSeconds": 0.7, "longPressSeconds": 1.3,
                   "repeatDelaySeconds": 0.9, "repeatIntervalSeconds": 0.2},
        "analogThreshold": 0.7,
    },
}


def action(profile: str, action_id: str) -> dict:
    """A copy of a catalog action, tagged with its id so settings can show its label."""
    src = COMMANDS.get(action_id) or CATALOG[profile][action_id]
    out = {k: copy.deepcopy(v) for k, v in src.items() if k != "label"}
    out["id"] = action_id
    return out


def default_config() -> dict:
    profiles = []
    for name, layers in _LAYOUTS.items():
        built = []
        for layer in layers:
            bindings = {}
            for inp, (tap, hold, repeats) in layer.items():
                b: dict = {}
                if tap:
                    b["tap"] = action(name, tap)
                if hold:
                    b["hold"] = action(name, hold)
                if repeats:
                    b["repeats"] = True
                bindings[inp] = b
            built.append(bindings)
        profiles.append({"name": name, "apps": APPS[name], "layers": built})
    return {
        "version": CONFIG_VERSION,
        "timing": {
            "minPressSeconds": 0.05,
            "cooldownSeconds": 0.15,
            "longPressSeconds": 0.8,
            "repeatDelaySeconds": 0.5,
            "repeatIntervalSeconds": 0.12,
        },
        "speak": True,
        "layerMode": "oneShot",
        "analogThreshold": 0.6,
        "global": {
            "view": {"tap": action("", "layer")},
            "menu": {"tap": action("", "announce"), "hold": action("", "toggleEnabled")},
        },
        "profiles": profiles,
    }


def config_dir() -> Path:
    if sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    elif sys.platform.startswith("win"):
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return base / APP_NAME


def config_path() -> Path:
    return Path(os.environ.get("LIMITLESS_CONFIG", config_dir() / "settings.json"))


def load(path: Path | None = None) -> dict:
    path = path or config_path()
    try:
        with open(path, encoding="utf-8") as f:
            config = json.load(f)
        if isinstance(config, dict) and config.get("profiles"):
            return config
    except FileNotFoundError:
        pass
    except (OSError, ValueError):
        # Keep the broken file for reference and start fresh.
        try:
            path.replace(path.with_suffix(".broken.json"))
        except OSError:
            pass
    return default_config()


def save(config: dict, path: Path | None = None) -> None:
    path = path or config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2)
    tmp.replace(path)
