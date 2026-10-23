"""Every app presses the same key for the same thing in the same DAW.

Voice's command packs, Control's profiles, One-Hand's layouts and Zoom's key maps were written
separately. When they were first compared (October 2026) they disagreed six times, and each
time one of them was wrong:
- Voice and One-Hand muted and soloed Logic's regions instead of the track (Control-M,
  Control-S).
- Voice and One-Hand recorded in Pro Tools on a Mac with Command+Space, which opens Spotlight.
- Voice moved between Pro Tools tracks with keys that only work in Commands Focus mode.
- Control went to the end of a Pro Tools session with Command+Return instead of Option+Return.
- Control redid in Ableton Live on Windows with Ctrl+Shift+Z instead of Ctrl+Y.
A musician would get a different result from the same request depending on which app they used.

GarageBand, REAPER and FL Studio were added to every app at once (apps/voice/DAW-SHORTCUTS.md has
each key's source), and are held to the same rule from the start.
"""

from __future__ import annotations

import fnmatch
import json
from pathlib import Path

import pytest

from conftest import ROOT, need

need("voice")
need("control")
need("zoom")
need("onehand")

from limitless_control import keys as control_keys  # noqa: E402
from limitless_control.profiles import APPS, CATALOG  # noqa: E402
from limitless_voice.engine import Engine  # noqa: E402
from limitless_voice.grammar import DEFAULT_PACK_DIR, load_packs  # noqa: E402
from limitless_voice.platforms.dryrun import DryRunPlatform  # noqa: E402
from limitless_voice.platforms.windows import EXE_NAMES  # noqa: E402
from limitless_zoom.keymaps import TARGETS  # noqa: E402

# For each DAW: what Voice is told, and the same thing in Control's profile.
SAME = {
    "Logic Pro": {
        "play": "play", "record": "record", "go to start": "start", "cycle": "cycle", "back": "rewind",
        "forward": "forward", "previous track": "track_up", "next track": "track_down", "mute": "mute",
        "solo": "solo", "arm": "arm", "zoom in": "zoom_in", "zoom out": "zoom_out",
        "zoom in vertical": "vzoom_in", "zoom out vertical": "vzoom_out", "zoom to fit": "zoom_fit",
        "metronome": "metronome", "mixer": "mixer", "editor": "editor", "inspector": "inspector",
        "piano roll": "piano_roll", "library": "library", "smart controls": "smart_controls",
        "undo": "undo", "redo": "redo", "save": "save",
    },
    "Pro Tools": {
        "play": "play", "record": "record", "go to start": "start", "undo": "undo", "redo": "redo",
        "arm": "arm", "loop playback": "loop", "previous track": "track_up", "next track": "track_down",
        "mute": "mute", "solo": "solo", "zoom in": "zoom_in", "zoom out": "zoom_out", "metronome": "click",
        "mixer": "mix_edit", "separate": "separate", "save": "save",
    },
    "Ableton Live": {
        "play": "play", "record": "record", "undo": "undo", "redo": "redo", "loop selection": "loop",
        "zoom in": "zoom_in", "zoom out": "zoom_out", "mute": "activate", "save": "save",
    },
    "GarageBand": {
        "play": "play", "record": "record", "undo": "undo", "redo": "redo", "new track": "new_track",
        "automation": "automation", "musical typing": "musical_typing", "save": "save",
    },
    "REAPER": {
        "play": "play", "record": "record", "go to start": "start", "go to end": "end", "undo": "undo",
        "redo": "redo", "loop": "loop", "previous track": "track_up", "next track": "track_down",
        "new track": "new_track", "split": "split", "mixer": "mixer", "zoom to fit": "zoom_fit",
        "add marker": "marker", "save": "save",
    },
    # FL Studio has no "record" or "redo" (R only switches record mode; Ctrl/Cmd+Z undoes and
    # redoes in turn), in any app.
    "FL Studio": {
        "play": "play", "record mode": "record_mode", "go to start": "start", "undo": "undo",
        "metronome": "metronome", "previous channel": "track_up", "next channel": "track_down", "solo": "solo",
        "mixer": "mixer", "playlist": "playlist", "channel rack": "channel_rack", "piano roll": "piano_roll",
        "browser": "browser", "zoom in": "zoom_in", "zoom out": "zoom_out", "zoom to fit": "zoom_fit",
        "add marker": "marker", "save": "save",
    },
}
# DAWs that only run on a Mac.
MAC_ONLY = {"Logic Pro", "GarageBand"}
# The same with Zoom's key maps: Voice's words, and Zoom's.
ZOOM = {
    "Logic Pro": ("logic", {"zoom in": "in", "zoom out": "out", "zoom in vertical": "taller",
                            "zoom out vertical": "shorter", "zoom to fit": "fit"}),
    "Pro Tools": ("protools", {"zoom in": "in", "zoom out": "out"}),
    "Ableton Live": ("ableton", {"zoom in": "in", "zoom out": "out", "zoom to selection": "fit"}),
    "REAPER": ("reaper", {"zoom to fit": "fit"}),
    "FL Studio": ("flstudio", {"zoom in": "in", "zoom out": "out", "zoom to fit": "fit"}),
}
# One-Hand's labels, and the same thing told to Voice.
ONE_HAND = {
    "Logic Pro": {
        "Go to start": "go to start", "Back one bar": "back", "Forward one bar": "forward", "Cycle on/off": "cycle",
        "Metronome on/off": "metronome", "Undo": "undo", "Redo": "redo", "Record": "record",
        "Split at playhead": "split", "New track": "new track", "Mute track": "mute", "Solo track": "solo",
        "Duplicate track": "duplicate track", "Zoom to fit": "zoom to fit", "Save": "save",
        "Zoom out": "zoom out", "Zoom in": "zoom in", "Mixer": "mixer", "Editor": "editor", "Library": "library",
    },
    "Pro Tools": {
        "Go to start": "go to start", "Loop playback": "loop playback", "Edit/Mix window": "mixer",
        "New tracks": "new track", "Undo": "undo", "Redo": "redo", "Record": "record", "Separate clip": "separate",
        "Duplicate": "duplicate", "Mute track": "mute", "Solo track": "solo", "Copy": "copy", "Paste": "paste",
        "Save": "save", "Zoom out": "zoom out", "Zoom in": "zoom in", "Cut": "cut", "Heal separation": "heal",
        "Delete": "delete",
    },
    "GarageBand": {
        "Undo": "undo", "Redo": "redo", "Record": "record", "New track": "new track", "Save": "save",
        "Automation": "automation", "Musical Typing": "musical typing",
    },
    "REAPER": {
        "Go to start": "go to start", "Go to end": "go to end", "Add marker": "add marker",
        "Loop playback": "loop playback", "Undo": "undo", "Redo": "redo", "Record": "record",
        "Split at edit cursor": "split", "New track": "new track", "Previous track": "previous track",
        "Next track": "next track", "Zoom to fit": "zoom to fit", "Save": "save", "Mixer": "mixer",
    },
    "FL Studio": {
        "Go to start": "go to start", "Add marker": "add marker", "Playlist": "playlist",
        "Metronome on/off": "metronome", "Undo": "undo", "Record mode on/off": "record mode",
        "Channel Rack": "channel rack", "Previous channel": "previous channel", "Solo track": "solo",
        "Next channel": "next channel", "Zoom to fit": "zoom to fit", "Save": "save", "Zoom out": "zoom out",
        "Zoom in": "zoom in", "Mixer": "mixer", "Piano roll": "piano roll", "Browser": "browser",
    },
}
ONE_HAND_KEYS = {"return_or_enter": "return", "comma": ",", "period": ".", "spacebar": "space", "equal_sign": "=",
                 "hyphen": "-", "open_bracket": "[", "close_bracket": "]", "semicolon": ";",
                 "delete_or_backspace": "delete", "left_arrow": "left", "right_arrow": "right",
                 "up_arrow": "up", "down_arrow": "down", "page_up": "pageup", "page_down": "pagedown"}
ONE_HAND_MODS = {"command": "cmd", "option": "alt", "control": "ctrl", "shift": "shift"}
SYSTEMS = {"mac": "mac", "windows": "win"}   # Voice's and Control's name, Zoom's name
PACKS = {os_name: load_packs([DEFAULT_PACK_DIR], os_name) for os_name in SYSTEMS}


def same_chord(text: str, os_name: str) -> tuple[frozenset, str]:
    """A chord as the keys physically pressed, whichever app's spelling it came in."""
    names = {"mod": "cmd" if os_name == "mac" else "ctrl", "command": "cmd", "option": "alt", "opt": "alt",
             "control": "ctrl", "super": "win", "enter": "return", "esc": "escape"}
    if os_name == "windows":
        names["cmd"] = "ctrl"
    parts = [names.get(p, p) for p in text.lower().replace(" ", "").split("+")]
    key = parts[-1].replace("keypad", "numpad")
    return frozenset(parts[:-1]), key


def voice_presses(daw: str, said: str, os_name: str) -> str | None:
    p = DryRunPlatform(os_name, app=daw)
    Engine(p, PACKS[os_name], own_names=["Limitless Voice"]).handle(said, said)
    pressed = [e[1] for e in p.log if e[0] == "press"]
    return pressed[0] if pressed else None


def cases():
    for daw, pairs in SAME.items():
        for os_name in SYSTEMS:
            if daw in MAC_ONLY and os_name == "windows":
                continue
            for said, action in pairs.items():
                yield daw, os_name, said, action


@pytest.mark.parametrize("daw,os_name,said,action", list(cases()))
def test_voice_and_control_press_the_same_key(daw, os_name, said, action):
    theirs = control_keys.resolve(CATALOG[daw][action]["keys"], os_name)
    ours = voice_presses(daw, said, os_name)
    assert ours is not None, f'Voice did nothing for "{said}" in {daw} on {os_name}'
    assert same_chord(ours, os_name) == same_chord(theirs, os_name), \
        f'{daw} on {os_name}: Voice presses {ours} for "{said}", Control presses {theirs} for {action}'


@pytest.mark.parametrize("daw", list(ZOOM))
def test_voice_and_zoom_zoom_the_same_way(daw):
    target, pairs = ZOOM[daw]
    for os_name, zoom_os in SYSTEMS.items():
        keymap = TARGETS[target]["keys"].get(zoom_os)
        if not keymap:
            continue
        for said, action in pairs.items():
            ours = voice_presses(daw, said, os_name)
            assert ours is not None, f'Voice did nothing for "{said}" in {daw} on {os_name}'
            assert same_chord(ours, os_name) == same_chord(keymap[action], os_name), \
                f'{daw} on {os_name}: Voice presses {ours} for "{said}", Zoom presses {keymap[action]} for {action}'


def one_hand_layouts() -> dict:
    data = json.loads((ROOT / "apps" / "one-hand" / "onehand" / "layouts.json").read_text(encoding="utf-8"))
    return {a["name"]: {c["label"]: c for c in a["commands"]} for a in data["apps"]}


def one_hand_chord(command: dict, os_name: str) -> str:
    """One-Hand writes Mac names; on Windows Command, Option and Control become Ctrl, Alt and Win."""
    windows = {"command": "ctrl", "option": "alt", "control": "win", "shift": "shift"}
    mods = [(windows if os_name == "windows" else ONE_HAND_MODS)[m] for m in command.get("mods", [])]
    return "+".join([*mods, ONE_HAND_KEYS.get(command["send"], command["send"])])


@pytest.mark.parametrize("daw", list(ONE_HAND))
def test_voice_and_one_hand_press_the_same_key(daw):
    layouts = one_hand_layouts()[daw]
    for os_name in SYSTEMS:
        if daw in MAC_ONLY and os_name == "windows":
            continue
        for label, said in ONE_HAND[daw].items():
            theirs = one_hand_chord(layouts[label], os_name)
            ours = voice_presses(daw, said, os_name)
            assert ours is not None, f'Voice did nothing for "{said}" in {daw} on {os_name}'
            assert same_chord(ours, os_name) == same_chord(theirs, os_name), \
                f'{daw} on {os_name}: Voice presses {ours} for "{said}", One-Hand presses {theirs} for {label}'


@pytest.mark.parametrize("daw", ["GarageBand", "REAPER", "FL Studio"])
def test_every_app_finds_the_same_daw(daw):
    """The Mac bundle ID and Windows program each app looks for, so the keys above reach the DAW."""
    voice = next(p for p in PACKS["mac"] if p.name == daw)
    control = APPS[daw]
    one_hand = next(a for a in json.loads((ROOT / "apps" / "one-hand" / "onehand" / "layouts.json")
                                          .read_text(encoding="utf-8"))["apps"] if a["name"] == daw)
    zoom = next((t for t in TARGETS.values() if t["name"] == daw), None)
    for app_id in one_hand["mac"] + one_hand["windows"]:
        assert any(fnmatch.fnmatch(app_id, p) for p in control), f"Control doesn't know {app_id} as {daw}"
        if zoom:
            assert any(m in app_id for m in zoom["match"]), f"Zoom doesn't know {app_id} as {daw}"
    # Voice goes by the app's name: the Mac's, and on Windows the program's (EXE_NAMES).
    names = {"GarageBand": ["GarageBand"], "REAPER": ["REAPER", "REAPER64"], "FL Studio": ["FL Studio 2024"]}[daw]
    names += [EXE_NAMES.get(exe) or Path(exe).stem for exe in one_hand["windows"]]
    for name in names:
        assert voice.applies_to(name), f"Voice doesn't know {name} as {daw}"


def test_control_and_one_hand_go_to_the_end_the_same_way():
    one_hand = one_hand_layouts()["Pro Tools"]["Go to end"]
    for os_name in SYSTEMS:
        theirs = one_hand_chord(one_hand, os_name)
        control = control_keys.resolve(CATALOG["Pro Tools"]["end"]["keys"], os_name)
        assert same_chord(control, os_name) == same_chord(theirs, os_name), \
            f"Pro Tools on {os_name}: Control presses {control} to go to the end, One-Hand presses {theirs}"
