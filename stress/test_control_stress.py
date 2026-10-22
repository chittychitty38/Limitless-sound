"""Limitless Control with shaky hands, worn switches and a controller that gets unplugged.

The controller reader is driven through SDL's real event queue (no controller needed:
the events are posted the way SDL posts them), and the engine is ticked every 10 ms
the way the app ticks it.
"""

from __future__ import annotations

import math
import os
import random

import pytest

from conftest import Soak, need

need("control")

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

from limitless_control import profiles  # noqa: E402
from limitless_control.engine import Engine  # noqa: E402

LOGIC = "com.apple.logic10"


class Out:
    def __init__(self):
        self.sent, self.spoken = [], []

    def send(self, keys):
        self.sent.append(keys)

    def speak(self, text):
        self.spoken.append(text)

    def log(self, text):
        pass


def make():
    out = Out()
    e = Engine(profiles.default_config(), out)
    e.app_changed(LOGIC)
    out.spoken.clear()
    return e, out


def run(e, timeline, until):
    """timeline: sorted (time, 'press'|'release', name). Ticks every 10 ms like the app."""
    t, i = 0.0, 0
    while t <= until:
        while i < len(timeline) and timeline[i][0] <= t:
            _, kind, name = timeline[i]
            (e.press if kind == "press" else e.release)(name, timeline[i][0])
            i += 1
        e.tick(t)
        t = round(t + 0.01, 3)


def test_switch_bounce_never_double_fires():
    """A worn switch or a tremor makes contact chatter for up to 80 ms on every press."""
    rng = random.Random(1)
    e, out = make()
    timeline, t, presses = [], 0.0, 0
    for _ in range(300):
        presses += 1
        for _ in range(rng.randint(1, 4)):  # chatter: on/off flickers of 5-20 ms
            flick = rng.uniform(0.005, 0.02)
            timeline += [(t, "press", "a"), (t + flick, "release", "a")]
            t += flick + rng.uniform(0.003, 0.01)
        timeline += [(t, "press", "a"), (t + rng.uniform(0.1, 0.25), "release", "a")]
        t += rng.uniform(0.6, 1.2)
    timeline.sort()
    run(e, timeline, t + 1)
    print(f"\n{presses} chattering presses → {len(out.sent)} key commands")
    assert len(out.sent) == presses


def test_trigger_held_at_the_threshold_with_a_tremor():
    """A trigger or stick held near the 60% line while the hand shakes must not machine-gun the DAW."""
    import pygame
    from limitless_control.controller import ControllerReader

    e, out = make()
    # Bind the right trigger like a button in this test.
    e.config["global"]["rt"] = {"tap": {"keys": "space", "say": "Play stop"}}
    t = {"now": 0.0}
    reader = ControllerReader(lambda n: e.press(n, t["now"]), lambda n: e.release(n, t["now"]), lambda m: None)
    pygame.display.init()
    rng = random.Random(2)
    for i in range(300):  # 3 seconds, one reading every 10 ms
        t["now"] = i * 0.01
        v = 0.62 + 0.07 * math.sin(2 * math.pi * 5 * t["now"]) + rng.gauss(0, 0.015)
        pygame.event.post(pygame.event.Event(pygame.CONTROLLERAXISMOTION, instance_id=0,
                                             axis=pygame.CONTROLLER_AXIS_TRIGGERRIGHT, value=int(v * 32767)))
        reader.poll()
        e.tick(t["now"])
    print(f"\nshaky trigger held for 3 s → {len(out.sent)} commands")
    assert len(out.sent) <= 2, f"a trigger held at the threshold fired {len(out.sent)} commands in 3 seconds"


def test_unplugging_mid_press_releases_everything():
    """The cable is knocked out while a repeating switch is held: the repeat must stop."""
    import pygame
    from limitless_control.controller import ControllerReader

    e, out = make()
    e.config["global"]["dpad_right"] = {"tap": {"keys": "right"}, "repeats": True}
    t = {"now": 0.0}
    reader = ControllerReader(lambda n: e.press(n, t["now"]), lambda n: e.release(n, t["now"]), lambda m: None)
    pygame.display.init()
    reader._down[0] = set()
    pygame.event.post(pygame.event.Event(pygame.CONTROLLERBUTTONDOWN, instance_id=0,
                                         button=pygame.CONTROLLER_BUTTON_DPAD_RIGHT))
    reader.poll()
    for i in range(100):
        t["now"] = i * 0.01
        e.tick(t["now"])
    held = len(out.sent)
    pygame.event.post(pygame.event.Event(pygame.CONTROLLERDEVICEREMOVED, instance_id=0))
    reader.poll()
    for i in range(100, 300):
        t["now"] = i * 0.01
        e.tick(t["now"])
    assert held > 1
    assert len(out.sent) == held, "the switch kept repeating after the controller was unplugged"


def test_every_switch_mashed_at_once():
    """All 25 inputs pressed and released at random for a long time: no crash, nothing left held."""
    from limitless_control.controller import ALL_INPUTS

    rng = random.Random(3)
    e, out = make()
    down = set()
    t = 0.0
    for i in range(100_000):
        name = rng.choice(ALL_INPUTS)
        if name in down:
            e.release(name, t)
            down.discard(name)
        else:
            e.press(name, t)
            down.add(name)
        t += rng.expovariate(50)
        e.tick(t)
        if i % 20_000 == 0:
            e.app_changed(rng.choice([LOGIC, "com.avid.ProTools", "com.ableton.live", None]))
    for name in list(down):
        e.release(name, t)
    e.tick(t + 5)
    n = len(out.sent)
    e.tick(t + 10)
    assert len(out.sent) == n, "something kept firing with every switch let go"
    assert not e._pressed


def test_soak():
    rng = random.Random(4)
    e, out = make()
    state = {"t": 0.0}

    def step(i):
        for _ in range(100):
            name = rng.choice(["a", "b", "x", "y", "lb", "rb", "view"])
            e.press(name, state["t"])
            state["t"] += rng.uniform(0.02, 1.0)
            e.tick(state["t"])
            e.release(name, state["t"])
            state["t"] += 0.2
        out.sent.clear()
        out.spoken.clear()

    soak = Soak()
    n = soak.run(step)
    mem, _ = soak.growth()
    print(f"\ncontrol soak: {n * 100} presses. {soak.report()}")
    assert mem < 15, soak.report()
