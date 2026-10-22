"""Held keys, tremor and lost modifier releases."""
import json
from pathlib import Path

from onehand.engine import PASS, SUPPRESS, Engine, Settings, Tap

LAYOUTS = json.loads((Path(__file__).parents[1] / "onehand" / "layouts.json").read_text())
LOGIC = "com.apple.logic10"


def mac(**kw):
    return Engine(LAYOUTS, "mac", Settings(**kw))


def press(e, key, t=0.0, app=LOGIC):
    return e.handle(key, True, t, app), e.handle(key, False, t + 0.05, app)


def test_holding_a_command_key_fires_it_once():
    # Auto-repeat (or a tremor holding the key a moment long) must not toggle Record ten times.
    e = mac()
    e.set_enabled(True)
    out = [e.handle("e", True, i * 0.03, LOGIC) for i in range(10)]
    assert out[0] == Tap("r") and set(out[1:]) == {SUPPRESS}
    assert e.handle("e", False, 0.5, LOGIC) == SUPPRESS
    assert press(e, "e", 1.0)[0] == Tap("r")  # the next real press works


def test_holding_the_toggle_key_switches_once():
    e = mac()
    for i in range(8):
        e.handle("f18", True, i * 0.03)
    assert e.enabled and e.changes == 1
    e.handle("f18", False, 0.5)
    press(e, "f18", 1.0)
    assert not e.enabled


def test_moves_keep_repeating_while_held():
    e = mac()
    e.set_enabled(True)
    out = [e.handle("3", True, i * 0.03, LOGIC) for i in range(5)]
    assert all(isinstance(t, Tap) and t.key == "period" for t in out)


def test_a_lost_modifier_release_does_not_kill_the_layer():
    e = mac()
    e.set_enabled(True)
    e.handle("cmd_l", True, 0, LOGIC)   # its release never arrives
    assert press(e, "q") == (PASS, PASS)
    e.sync_mods(set())                  # the next key event says no modifiers are down
    assert press(e, "q")[0] == Tap("z", ("cmd_l",))
