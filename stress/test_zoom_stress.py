"""Limitless Zoom's key layer and router under tremor, auto-repeat and floods."""

from __future__ import annotations

import random

from conftest import Soak, need

need("zoom")

from limitless_zoom.actions import DEFAULT_LAYER_MAP, ZOOM_ACTIONS  # noqa: E402
from limitless_zoom.hotkeys import REPEAT_GAP, KeyLogic  # noqa: E402
from limitless_zoom.keymaps import TARGETS  # noqa: E402
from limitless_zoom.router import Router  # noqa: E402


class Clock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t


def logic():
    clock = Clock()
    seen = {"actions": [], "layer": [], "switch": 0}
    k = KeyLogic("f13", "f19", DEFAULT_LAYER_MAP, seen["actions"].append, seen["layer"].append,
                 lambda: seen.__setitem__("switch", seen["switch"] + 1), clock=clock)
    return k, clock, seen


def test_held_switch_key_fires_once():
    k, clock, seen = logic()
    for i in range(20):  # auto-repeat while a foot pedal is held
        clock.t = i * 0.03
        k.handle("f19", True, False)
    k.handle("f19", False, False)
    assert seen["switch"] == 1


def test_held_zoom_key_repeats_at_a_steady_pace():
    """Holding a zoom key keeps zooming, but never faster than the repeat gap, however fast the OS repeats."""
    k, clock, seen = logic()
    k.set_layer(True)
    key = next(iter(DEFAULT_LAYER_MAP))
    for i in range(1000):  # 10 seconds of a very fast auto-repeat (every 10 ms)
        clock.t = i * 0.01
        k.handle(key, True, False)
    assert len(seen["actions"]) <= 10 / REPEAT_GAP + 2


def test_a_lost_key_up_costs_at_most_one_press():
    """If a key-up goes missing (password field, sleep), the switch must work again straight after."""
    k, clock, seen = logic()
    k.handle("f19", True, False)  # its release is lost
    clock.t = 5
    k.handle("f19", True, False)
    k.handle("f19", False, False)
    clock.t = 6
    k.handle("f19", True, False)
    k.handle("f19", False, False)
    assert seen["switch"] >= 2


def test_key_storm():
    rng = random.Random(1)
    k, clock, seen = logic()
    keys = list(DEFAULT_LAYER_MAP) + ["f13", "f19", "esc", "a", "s", "space", None]
    for i in range(200_000):
        clock.t += rng.expovariate(30)
        hide = k.handle(rng.choice(keys), rng.random() < 0.55, rng.random() < 0.1)
        assert hide in (True, False)
    for key in keys:
        k.handle(key, False, False)
    assert not k.down


def test_router_every_action_in_every_app_on_both_systems():
    for os_name in ("mac", "win"):
        r = Router(os_name)
        apps = [None, "com.apple.TextEdit"] + [m for t in TARGETS.values() for m in t.get("match", [])]
        for _ in range(3):
            for app in apps:
                for action in ZOOM_ACTIONS:
                    plan = r.plan(action, app)
                    assert plan.message
                    assert len(plan.combos) <= 10


def test_soak():
    rng = random.Random(2)
    k, clock, seen = logic()
    r = Router("mac")

    def step(n):
        for _ in range(500):
            clock.t += 0.02
            k.handle(rng.choice(list(DEFAULT_LAYER_MAP) + ["f13"]), rng.random() < 0.5, False)
            r.plan(rng.choice(sorted(ZOOM_ACTIONS)), rng.choice([None, "com.apple.logic10"]))
        seen["actions"].clear()
        seen["layer"].clear()

    soak = Soak()
    n = soak.run(step)
    mem, _ = soak.growth()
    print(f"\nzoom soak: {n * 500} events. {soak.report()}")
    assert mem < 15, soak.report()
