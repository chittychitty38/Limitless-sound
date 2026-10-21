"""The six Limitless Sound tools: names, where they get installed, and what they can do.

Each tool sends its own list of actions when it connects, and that live list wins.
The lists here let the settings page show every tool's actions while the tool is
closed, and let the hub start a closed tool or reach the ones that have a
command line ("--do in", "do 'solo track'").
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# Shared vocabulary for the DAW. Any input can ask for "daw.record"; the hub hands it
# to whichever connected tool can press the right keys for the app in front.
INTENTS = {
    "daw.playStop": "Play / stop",
    "daw.play": "Play",
    "daw.stop": "Stop",
    "daw.record": "Record",
    "daw.start": "Go to start",
    "daw.undo": "Undo",
    "daw.redo": "Redo",
    "daw.save": "Save",
    "daw.mute": "Mute track",
    "daw.solo": "Solo track",
    "daw.nextTrack": "Next track",
    "daw.prevTrack": "Previous track",
    "daw.zoomIn": "Zoom in",
    "daw.zoomOut": "Zoom out",
    "daw.zoomFit": "Zoom to fit",
    "daw.metronome": "Metronome / click",
    "daw.mixer": "Show mixer",
}

# Who answers an intent first when several tools can. The musician can reorder it.
DEFAULT_INTENT_ORDER = ["zoom", "control", "onehand", "gaze", "voice"]


def _a(id_, label, intent=None, phrases=None, args=None):
    d = {"id": id_, "label": label}
    if intent:
        d["intent"] = intent
    if phrases:
        d["phrases"] = phrases
    if args:
        d["args"] = args
    return d


TOOLS: dict[str, dict] = {
    "voice": {
        "name": "Limitless Voice",
        "about": "Voice commands for Logic Pro, Pro Tools and the rest of the computer.",
        "mac_app": "Limitless Voice.app", "mac_exe": "Limitless Voice",
        "win_dirs": ["Limitless Voice"], "win_exe": "LimitlessVoice.exe",
        # Without the live connection, "voice.do" still works through its command line.
        "cli": {"do": ["do", "{phrase}"]},
        "actions": [
            _a("sleep", "Stop listening"),
            _a("wake", "Start listening"),
            _a("toggle", "Listening on or off"),
            _a("takeGuard", "Take mode: only hear stop and wake words"),
            _a("takeGuardOff", "Take mode off"),
            _a("do", "Run a spoken command", args={"phrase": "text"}),
        ],
    },
    "onehand": {
        "name": "Limitless One-Hand",
        "about": "One-hand mode turns the keys under one hand into DAW commands.",
        "mac_app": "Limitless One-Hand.app", "mac_exe": "Limitless One-Hand",
        "win_dirs": ["Limitless One-Hand"], "win_exe": "LimitlessOneHand.exe",
        "win_loose": ["Limitless-One-Hand-windows.exe", "LimitlessOneHand.exe"],
        "actions": [
            _a("on", "One-hand mode on"),
            _a("off", "One-hand mode off"),
            _a("toggle", "One-hand mode on or off"),
            _a("left", "Left-hand layout"),
            _a("right", "Right-hand layout"),
        ],
    },
    "zoom": {
        "name": "Limitless Zoom",
        "about": "Zoom the DAW or the whole screen by voice, one hand, dwell or one switch.",
        "mac_app": "Limitless Zoom.app", "mac_exe": "Limitless Zoom",
        "win_dirs": ["Limitless Zoom"], "win_exe": "Limitless Zoom.exe",
        "cli": {"*": ["--do", "{action}"]},
        "actions": [
            _a("in", "Zoom in", "daw.zoomIn"), _a("out", "Zoom out", "daw.zoomOut"),
            _a("bigIn", "Zoom in a lot"), _a("bigOut", "Zoom out a lot"),
            _a("taller", "Taller tracks"), _a("shorter", "Shorter tracks"),
            _a("fit", "Fit to window", "daw.zoomFit"),
            _a("wave", "Bigger waveform"), _a("waveOut", "Smaller waveform"),
            _a("magToggle", "Magnifier on or off"), _a("magIn", "Magnify more"), _a("magOut", "Magnify less"),
            _a("preset1", "Zoom preset 1"), _a("preset2", "Zoom preset 2"), _a("preset3", "Zoom preset 3"),
            _a("preset4", "Zoom preset 4"), _a("preset5", "Zoom preset 5"),
            _a("again", "Zoom again"), _a("panel", "Show or hide the zoom panel"),
            _a("keys", "Zoom keys on or off"), _a("keysOn", "Zoom keys on"), _a("keysOff", "Zoom keys off"),
        ],
    },
    "color": {
        "name": "Limitless Color",
        "about": "Recolors the whole screen for colorblind musicians.",
        "mac_app": "Limitless Color.app", "mac_exe": "Limitless Color",
        "win_dirs": ["Limitless Color"], "win_exe": "Limitless Color.exe",
        "win_alt_exes": ["limitless-color.exe", "app.exe"],
        "actions": [
            _a("on", "Screen colors on"),
            _a("off", "Screen colors off"),
            _a("toggle", "Screen colors on or off"),
            _a("tuner", "Open the color tuner"),
        ],
    },
    "control": {
        "name": "Limitless Control",
        "about": "Xbox Adaptive Controller, switches and gamepads as DAW key commands.",
        "mac_app": "Limitless Control.app", "mac_exe": "Limitless Control",
        "win_dirs": ["Limitless Control"], "win_exe": "Limitless Control.exe",
        "launch_args": ["--background"],
        "actions": [
            _a("on", "Controller on"), _a("off", "Controller off"), _a("toggle", "Controller on or off"),
            _a("layer", "Next layer"), _a("announce", "Say the profile and layer"),
            _a("play", "Play / stop", "daw.playStop"), _a("record", "Record", "daw.record"),
            _a("start", "Go to start", "daw.start"), _a("undo", "Undo", "daw.undo"),
            _a("redo", "Redo", "daw.redo"), _a("save", "Save", "daw.save"),
            _a("mute", "Mute track", "daw.mute"), _a("solo", "Solo track", "daw.solo"),
            _a("track_down", "Next track", "daw.nextTrack"), _a("track_up", "Previous track", "daw.prevTrack"),
            _a("zoom_in", "Zoom in", "daw.zoomIn"), _a("zoom_out", "Zoom out", "daw.zoomOut"),
            _a("zoom_fit", "Zoom to fit", "daw.zoomFit"),
            _a("metronome", "Metronome / click", "daw.metronome"), _a("mixer", "Show mixer", "daw.mixer"),
        ],
    },
    "gaze": {
        "name": "GazeStage",
        "about": "Play instruments and run the transport with your eyes, head, a sound or a switch.",
        "mac_app": "GazeStage.app", "mac_exe": "GazeStage",
        "win_dirs": ["GazeStage", "GazeStage-win32-x64"], "win_exe": "GazeStage.exe",
        "actions": [
            _a("play", "Play (Pro Tools link)", "daw.play"), _a("stop", "Stop (Pro Tools link)", "daw.stop"),
            _a("record", "Record (Pro Tools link)", "daw.record"),
            _a("pads", "Show the note pads"), _a("transport", "Show the transport page"),
            _a("suite", "Show the Limitless Sound page"),
            _a("octaveUp", "Octave up"), _a("octaveDown", "Octave down"), _a("scale", "Next scale"),
            _a("latch", "Hold notes on or off"), _a("panic", "All notes off"),
        ],
    },
}

HUB_ACTIONS = [
    _a("say", "Say something out loud", args={"text": "text"}),
    _a("open", "Open a tool", args={"tool": "tool"}),
    _a("openAll", "Open my tools"),
    _a("settings", "Show Limitless Sound settings"),
    _a("status", "Say which tools are running"),
]


def platform_key() -> str:
    if sys.platform == "darwin":
        return "mac"
    if sys.platform.startswith("win"):
        return "windows"
    return "linux"


def _win_roots() -> list[Path]:
    roots = []
    for var in ("LOCALAPPDATA",):
        if os.environ.get(var):
            roots.append(Path(os.environ[var]) / "Programs")
            roots.append(Path(os.environ[var]))
    for var in ("ProgramFiles", "ProgramFiles(x86)"):
        if os.environ.get(var):
            roots.append(Path(os.environ[var]))
    return roots


def find_install(tool_id: str, overrides: dict | None = None) -> Path | None:
    """Path of the program to run for a tool, or None when it isn't installed."""
    spec = TOOLS[tool_id]
    custom = (overrides or {}).get(tool_id)
    if custom:
        p = Path(custom)
        if p.suffix == ".app" and p.is_dir():
            return p / "Contents" / "MacOS" / spec.get("mac_exe", p.stem)
        return p if p.exists() else None
    plat = platform_key()
    if plat == "mac":
        for root in (Path("/Applications"), Path.home() / "Applications"):
            exe = root / spec["mac_app"] / "Contents" / "MacOS" / spec["mac_exe"]
            if exe.exists():
                return exe
        return None
    if plat == "windows":
        exes = [spec["win_exe"], *spec.get("win_alt_exes", [])]
        for root in _win_roots():
            for d in spec.get("win_dirs", []):
                for exe in exes:
                    if (root / d / exe).exists():
                        return root / d / exe
        home = Path.home()
        for folder in (home / "Downloads", home / "Desktop", home / "Documents"):
            for name in spec.get("win_loose", []):
                if (folder / name).exists():
                    return folder / name
            for d in spec.get("win_dirs", []):
                if (folder / d / spec["win_exe"]).exists():
                    return folder / d / spec["win_exe"]
        return None
    return None


def cli_command(tool_id: str, action: str, args: dict, exe: Path) -> list[str] | None:
    """Command line that performs an action on a tool that isn't connected, if it has one."""
    cli = TOOLS[tool_id].get("cli") or {}
    template = cli.get(action) or cli.get("*")
    if not template:
        return None
    values = {"action": action, **{k: str(v) for k, v in (args or {}).items()}}
    try:
        return [str(exe)] + [part.format(**values) for part in template]
    except KeyError:
        return None
