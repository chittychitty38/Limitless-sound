"""Every app presses the same key for the same thing in the same DAW.

Voice's command packs, Control's profiles and Zoom's key maps were written separately. When
they were first compared (October 2026), three disagreed, and each time one of them was wrong:
Voice muted and soloed Logic's regions instead of the track (Control-M, Control-S), recorded in
Pro Tools on a Mac with Command+Space (which opens Spotlight), and moved between Pro Tools
tracks with keys that only work in Commands Focus mode; Control redid in Ableton Live on
Windows with Ctrl+Shift+Z instead of Ctrl+Y. A musician would get a different result from the
same request depending on which app they used.
"""

from __future__ import annotations

import pytest

from conftest import need

need("voice")
need("control")
need("zoom")

from limitless_control import keys as control_keys  # noqa: E402
from limitless_control.profiles import CATALOG  # noqa: E402
from limitless_voice.engine import Engine  # noqa: E402
from limitless_voice.grammar import DEFAULT_PACK_DIR, load_packs  # noqa: E402
from limitless_voice.platforms.dryrun import DryRunPlatform  # noqa: E402
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
}
# The same with Zoom's key maps: Voice's words, and Zoom's.
ZOOM = {
    "Logic Pro": ("logic", {"zoom in": "in", "zoom out": "out", "zoom in vertical": "taller",
                            "zoom out vertical": "shorter", "zoom to fit": "fit"}),
    "Pro Tools": ("protools", {"zoom in": "in", "zoom out": "out"}),
    "Ableton Live": ("ableton", {"zoom in": "in", "zoom out": "out", "zoom to selection": "fit"}),
}
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
            if daw == "Logic Pro" and os_name == "windows":
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
