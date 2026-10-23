import json
from pathlib import Path

import pytest

from onehand.engine import PASS, SUPPRESS, Engine, Settings, Tap
from onehand.keys import MAC_CODES, MIRROR, WIN_CODES

LAYOUTS = json.loads((Path(__file__).parents[1] / "onehand" / "layouts.json").read_text())
LOGIC = "com.apple.logic10"
PT_WIN = "ProTools.exe"


def mac(**kw):
    return Engine(LAYOUTS, "mac", Settings(**kw))


def press(e, key, t=0.0, app=LOGIC):
    return e.handle(key, True, t, app), e.handle(key, False, t + 0.05, app)


def test_off_by_default_everything_passes():
    e = mac()
    assert press(e, "q") == (PASS, PASS)


def test_toggle_key_switches_and_is_swallowed():
    e = mac()
    assert press(e, "f18") == (SUPPRESS, SUPPRESS)
    assert e.enabled
    press(e, "f18")
    assert not e.enabled


def test_layer_taps_daw_shortcut_and_swallows_release():
    e = mac()
    e.set_enabled(True)
    assert press(e, "q") == (Tap("z", ("cmd_l",)), SUPPRESS)
    assert press(e, "e") == (Tap("r"), SUPPRESS)


def test_layer_only_in_supported_app():
    e = mac()
    e.set_enabled(True)
    assert press(e, "q", app="com.apple.TextEdit") == (PASS, PASS)
    assert press(e, "q", app=None) == (PASS, PASS)


def test_real_shortcuts_pass_through():
    e = mac()
    e.set_enabled(True)
    e.handle("cmd_l", True, 0, LOGIC)
    assert press(e, "s") == (PASS, PASS)


def test_right_hand_uses_mirrored_keys():
    e = mac(hand="right")
    e.set_enabled(True)
    assert press(e, "p")[0] == Tap("z", ("cmd_l",))
    assert press(e, "q") == (PASS, PASS)


def test_windows_translates_modifiers_for_pro_tools():
    e = Engine(LAYOUTS, "windows", Settings())
    e.set_enabled(True)
    assert press(e, "q", app=PT_WIN)[0] == Tap("z", ("ctrl_l",))
    assert press(e, "r", app=PT_WIN)[0] == Tap("e", ("ctrl_l",))      # Separate clip
    assert press(e, "e", app=PT_WIN)[0] == Tap("f12")                    # Record: F12, as in every app
    assert press(e, "q", app="logic.exe") == (PASS, PASS)


def test_double_shift_toggles():
    e = mac()
    for t in (0.0, 0.2):
        e.handle("shift_l", True, t)
        e.handle("shift_l", False, t + 0.08)
    assert e.enabled
    for t in (1.0, 1.2):
        e.handle("shift_r", True, t)
        e.handle("shift_r", False, t + 0.08)
    assert not e.enabled


def test_shift_used_for_typing_does_not_toggle():
    e = mac()
    e.handle("shift_l", True, 0.0)
    e.handle("a", True, 0.05)
    e.handle("a", False, 0.07)
    e.handle("shift_l", False, 0.1)
    e.handle("shift_l", True, 0.2)
    e.handle("shift_l", False, 0.25)
    assert not e.enabled


def test_slow_double_shift_does_not_toggle():
    e = mac()
    e.handle("shift_l", True, 0.0); e.handle("shift_l", False, 0.1)
    e.handle("shift_l", True, 1.0); e.handle("shift_l", False, 1.1)
    assert not e.enabled


def test_double_shift_can_be_turned_off():
    e = mac(double_shift=False)
    for t in (0.0, 0.2):
        e.handle("shift_l", True, t); e.handle("shift_l", False, t + 0.08)
    assert not e.enabled


def test_space_tap_still_plays():
    e = mac()
    e.set_enabled(True)
    assert press(e, "spacebar") == (SUPPRESS, Tap("spacebar"))


def test_hold_space_mirrors_typing():
    e = mac()
    e.set_enabled(True)
    assert e.handle("spacebar", True, 0, LOGIC) == SUPPRESS
    assert e.handle("spacebar", True, 0.1, LOGIC) == SUPPRESS      # auto-repeat
    assert press(e, "a", 0.2) == (Tap("semicolon"), SUPPRESS)
    assert press(e, "j", 0.3) == (Tap("f"), SUPPRESS)
    assert e.handle("spacebar", False, 0.4, LOGIC) == SUPPRESS


def test_mirror_typing_off_leaves_space_alone():
    e = mac(mirror_typing=False)
    e.set_enabled(True)
    assert press(e, "spacebar") == (PASS, PASS)


def test_cmd_space_is_not_eaten():
    e = mac()
    e.set_enabled(True)
    e.handle("cmd_l", True, 0)
    assert press(e, "spacebar") == (PASS, PASS)


def test_release_after_switching_off_is_still_swallowed():
    e = mac()
    e.set_enabled(True)
    assert e.handle("q", True, 0, LOGIC) == Tap("z", ("cmd_l",))
    e.set_enabled(False)
    assert e.handle("q", False, 0.1, LOGIC) == SUPPRESS


@pytest.mark.parametrize("platform", ["mac", "windows"])
def test_every_layout_key_has_a_code(platform):
    codes = MAC_CODES if platform == "mac" else WIN_CODES
    for app in LAYOUTS["apps"]:
        for c in app["commands"]:
            assert c["key"] in codes and MIRROR[c["key"]] in codes and c["send"] in codes, c


def test_no_duplicate_keys_per_app():
    for app in LAYOUTS["apps"]:
        keys = [c["key"] for c in app["commands"]]
        assert len(keys) == len(set(keys)), app["id"]


def test_mac_and_windows_codes_cover_same_keys():
    assert set(MAC_CODES) <= set(WIN_CODES)


def test_practice_in_own_window_lights_card_without_typing():
    e = mac()
    e.self_app_ids = {"org.limitlesssound.onehand"}
    e.preview_app = "protools"
    e.set_enabled(True)
    assert press(e, "e", app="org.limitlesssound.onehand") == (SUPPRESS, SUPPRESS)
    assert e.last_preview == ("e", "Record") and e.previews == 1
    assert press(e, "y", app="org.limitlesssound.onehand") == (PASS, PASS)


def test_practice_follows_hand():
    e = mac(hand="right")
    e.self_app_ids = {"me"}
    e.preview_app = "logic"
    e.set_enabled(True)
    press(e, "p", app="me")
    assert e.last_preview == ("p", "Undo")


def test_no_practice_when_off():
    e = mac()
    e.self_app_ids = {"me"}
    e.preview_app = "logic"
    assert press(e, "q", app="me") == (PASS, PASS)
