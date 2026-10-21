import json

import pytest

from limitless_zoom.actions import (DEFAULT_LAYER_MAP, LABELS, PANEL_BUTTONS, VOICE_PHRASES,
                                    ZOOM_ACTIONS)
from limitless_zoom.hotkeys import KeyLogic
from limitless_zoom.keymaps import TARGETS, find_target
from limitless_zoom.keys import MAC_KEYCODES, MODIFIER_TAPS, WIN_VK, format_key, parse_combo
from limitless_zoom.router import Router
from limitless_zoom.settings import Settings
from limitless_zoom.voice import grammar, match_phrase


# Keys ----------------------------------------------------------------------

def test_parse_combo():
    assert parse_combo("alt+cmd+=") == (("alt", "cmd"), "=")
    assert parse_combo("Option+Command+Right") == (("alt", "cmd"), "right")
    assert parse_combo("win+esc") == (("win",), "esc")
    assert parse_combo("z") == ((), "z")
    assert parse_combo("cmd++") == (("cmd",), "=")
    with pytest.raises(ValueError):
        parse_combo("hyper+z")


def test_every_default_combo_is_pressable():
    for t in TARGETS.values():
        for os_name, keys in t["keys"].items():
            for action, combo in keys.items():
                _, key = parse_combo(combo)
                table = WIN_VK if os_name == "win" else MAC_KEYCODES
                assert key in table, (os_name, action, combo)


def test_layer_and_switch_keys_exist_on_both_oses():
    for key in list(DEFAULT_LAYER_MAP) + ["f13", "f19", "esc"] + sorted(MODIFIER_TAPS):
        assert key in MAC_KEYCODES and key in WIN_VK


# Routing -------------------------------------------------------------------

def test_find_target():
    assert find_target("com.apple.logic10") == "logic"
    assert find_target("ProTools.exe") == "protools"
    assert find_target("com.avid.ProTools") == "protools"
    assert find_target("Ableton Live 12 Suite.exe") == "ableton"
    assert find_target("com.google.Chrome") == "magnifier"
    assert find_target(None) == "magnifier"


def test_logic_zoom():
    p = Router("mac").plan("in", "com.apple.logic10")
    assert p.ok and p.target == "logic" and p.combos == [(("cmd",), "right")]


def test_big_steps_repeat():
    p = Router("mac", big_steps=4).plan("bigOut", "com.avid.ProTools")
    assert p.combos == [(("cmd",), "[")] * 4


def test_pro_tools_windows():
    p = Router("win").plan("in", "ProTools.exe")
    assert p.combos == [(("ctrl",), "]")]


def test_unknown_app_falls_back_to_magnifier():
    p = Router("mac").plan("in", "com.apple.finder")
    assert p.ok and p.target == "magnifier" and p.combos == [(("alt", "cmd"), "=")]


def test_not_available_is_explained():
    p = Router("mac").plan("taller", "com.apple.finder")
    assert not p.ok and "isn't available" in p.message


def test_windows_magnifier_toggle_tracks_state():
    r = Router("win")
    assert r.plan("magToggle", None).combos == [(("win",), "=")]
    assert r.plan("magToggle", None).combos == [(("win",), "esc")]
    assert r.plan("magToggle", None).combos == [(("win",), "=")]


def test_overrides():
    r = Router("win", overrides={"protools": {"win": {"taller": "ctrl+alt+down"}}})
    assert r.plan("taller", "ProTools.exe").combos == [(("ctrl", "alt"), "down")]


def test_every_zoom_action_is_routable_somewhere():
    for action in ZOOM_ACTIONS:
        assert any(Router(os_name).plan(action, app).ok
                   for os_name in ("mac", "win")
                   for app in ("com.avid.ProTools", "ProTools.exe", None)), action


# Voice ---------------------------------------------------------------------

def test_phrases_map_to_real_actions():
    assert set(VOICE_PHRASES.values()) <= set(LABELS)
    assert "[unk]" in json.loads(grammar())


def test_match_phrase_confidence():
    words = [{"word": "zoom", "conf": 0.9}, {"word": "in", "conf": 0.8}]
    assert match_phrase("zoom in", words, 0.5) == "in"
    assert match_phrase("zoom  in", words, 0.5) == "in"
    assert match_phrase("zoom in", [{"conf": 0.3}, {"conf": 0.3}], 0.5) is None
    assert match_phrase("[unk]", [], 0.5) is None
    noisy = [{"word": "[unk]", "conf": 0.2}, {"word": "again", "conf": 0.9}]
    assert match_phrase("[unk] again", noisy, 0.5) == "again"
    assert match_phrase("", [], 0.5) is None


# One-handed keys and switch -------------------------------------------------

class Recorder:
    def __init__(self):
        self.actions, self.layers, self.switches = [], [], 0


def make_logic(clock=None):
    r = Recorder()
    kw = {"clock": clock} if clock else {}
    logic = KeyLogic("f13", "f19", DEFAULT_LAYER_MAP, r.actions.append, r.layers.append,
                     lambda: setattr(r, "switches", r.switches + 1), **kw)
    return logic, r


def tap(logic, key, mods=False):
    hid = logic.handle(key, True, mods)
    logic.handle(key, False, mods)
    return hid


def test_layer_off_lets_keys_through():
    logic, r = make_logic()
    assert tap(logic, "e") is False
    assert r.actions == []


def test_layer_toggle_and_actions():
    logic, r = make_logic()
    assert tap(logic, "f13") is True
    assert r.layers == [True]
    assert tap(logic, "e") is True and tap(logic, "s") is True
    assert r.actions == ["in", "taller"]
    assert tap(logic, "k") is False          # unmapped keys still type
    assert tap(logic, "e", mods=True) is False  # Cmd+E etc. still work
    tap(logic, "f13")
    assert r.layers == [True, False]
    assert tap(logic, "e") is False


def test_escape_leaves_layer():
    logic, r = make_logic()
    tap(logic, "f13")
    assert tap(logic, "esc") is True
    assert r.layers == [True, False]


def test_holding_layer_toggle_does_not_flicker():
    logic, r = make_logic()
    for _ in range(5):
        logic.handle("f13", True, False)  # auto-repeat
    logic.handle("f13", False, False)
    assert r.layers == [True]


def test_held_key_repeats_with_throttle():
    t = [0.0]
    logic, r = make_logic(clock=lambda: t[0])
    tap(logic, "f13")
    logic.handle("e", True, False)
    for _ in range(2):
        t[0] += 0.05
        logic.handle("e", True, False)  # repeats faster than the gap: ignored
    t[0] += 0.2
    logic.handle("e", True, False)
    assert r.actions == ["in", "in"]


def test_switch_and_capture():
    logic, r = make_logic()
    assert tap(logic, "f19") is True and r.switches == 1
    got = []
    logic.capture_next(got.append)
    assert tap(logic, "f8") is True
    assert got == ["f8"]
    assert tap(logic, "f8") is False


# Settings --------------------------------------------------------------------

def test_settings_roundtrip(tmp_path):
    s = Settings(tmp_path / "s.json")
    assert s["layer_key"] is None
    assert s.get_layer_key() in ("right_alt", "right_ctrl")
    s["layer_key"] = "f8"
    s.save()
    assert Settings(tmp_path / "s.json")["layer_key"] == "f8"


def test_settings_ignore_bad_file(tmp_path):
    (tmp_path / "s.json").write_text("{not json")
    assert Settings(tmp_path / "s.json")["dwell_ms"] == 900


def test_panel_buttons_are_actions():
    assert all(a in ZOOM_ACTIONS for a, _ in PANEL_BUTTONS)


# Tapping a modifier on its own (the default zoom key is a Right Option tap) ----

def make_tap_logic(t):
    r = Recorder()
    logic = KeyLogic("right_alt", "right_cmd", DEFAULT_LAYER_MAP, r.actions.append, r.layers.append,
                     lambda: setattr(r, "switches", r.switches + 1), clock=lambda: t[0])
    return logic, r


def test_modifier_tap_toggles_layer():
    t = [0.0]
    logic, r = make_tap_logic(t)
    assert logic.handle("right_alt", True, False) is False  # never hidden from apps
    t[0] += 0.1
    assert logic.handle("right_alt", False, False) is False
    assert r.layers == [True]
    assert tap(logic, "e") is True and r.actions == ["in"]


def test_modifier_used_in_a_shortcut_is_not_a_tap():
    t = [0.0]
    logic, r = make_tap_logic(t)
    logic.handle("right_alt", True, False)
    tap(logic, "e", mods=True)  # Option+E
    logic.handle("right_alt", False, False)
    assert r.layers == [] and r.actions == []


def test_long_modifier_hold_is_not_a_tap():
    t = [0.0]
    logic, r = make_tap_logic(t)
    logic.handle("right_alt", True, False)
    t[0] += 2
    logic.handle("right_alt", False, False)
    assert r.layers == []


def test_modifier_tap_as_switch_and_capture():
    t = [0.0]
    logic, r = make_tap_logic(t)
    logic.handle("right_cmd", True, False)
    logic.handle("right_cmd", False, False)
    assert r.switches == 1
    got = []
    logic.capture_next(got.append)
    logic.handle("right_shift", True, False)
    assert got == []  # waits for the tap to finish
    logic.handle("right_shift", False, False)
    assert got == ["right_shift"]


def test_key_names_read_well():
    assert format_key("right_alt", "mac") == "Right Option"
    assert format_key("right_alt", "win") == "Right Alt"
    assert format_key("f19") == "F19"
    assert format_key(None) == "not set"
