"""Limitless One-Hand's key engine under tremor, floods and hours of typing.

The engine runs inside the operating system's keyboard hook: macOS switches a hook
off if it is slow, so every key must be decided in well under a millisecond, and a
key that is pressed must never leave anything stuck once it is let go.
"""

from __future__ import annotations

import json
import random
import time

from conftest import ROOT, Soak, need, percentile

need("onehand")

from onehand.engine import PASS, SUPPRESS, Engine, Settings, Tap  # noqa: E402
from onehand.keys import MAC_CODES, MODIFIER_KEYS  # noqa: E402

LAYOUTS = json.loads((ROOT / "apps" / "one-hand" / "onehand" / "layouts.json").read_text())
LOGIC = "com.apple.logic10"
APPS = [LOGIC, "com.avid.ProTools", "com.apple.TextEdit", None]
KEYS = [k for k in MAC_CODES if k != "caps_lock"]
COMMAND_KEYS = [c["key"] for c in LAYOUTS["apps"][0]["commands"] if not c.get("repeat")]


def engine(**kw):
    e = Engine(LAYOUTS, "mac", Settings(**kw))
    e.set_enabled(True)
    return e


def is_clean(e):
    return not e._consumed and not e._held_mods and not e._space_held and not getattr(e, "_held_commands", set())


def test_tremor_holding_and_bouncing_command_keys():
    """A tremor holds keys too long (auto-repeat) and bounces on them. Each real press is one command."""
    rng = random.Random(3)
    e = engine()
    presses = commands = 0
    t = 0.0
    for _ in range(5000):
        key = rng.choice(COMMAND_KEYS)
        presses += 1
        # The key goes down, auto-repeats a few times while the hand shakes on it, then comes up.
        for _ in range(1 + rng.randint(0, 8)):
            if isinstance(e.handle(key, True, t, LOGIC), Tap):
                commands += 1
            t += rng.uniform(0.01, 0.05)
        assert e.handle(key, False, t, LOGIC) in (PASS, SUPPRESS)
        t += rng.uniform(0.005, 0.3)
    print(f"\n{presses} shaky presses gave {commands} commands")
    assert commands == presses, f"{commands - presses} extra commands fired from held keys"
    assert is_clean(e)


def test_random_key_storm_never_leaves_anything_stuck():
    """A million random presses and releases in any order, across apps, hands and settings."""
    rng = random.Random(11)
    for hand in ("left", "right"):
        e = engine(hand=hand)
        down: set[str] = set()
        t = 0.0
        for i in range(250_000):
            key = rng.choice(KEYS)
            is_down = key not in down if rng.random() < 0.9 else key in down  # some repeats and stray releases
            if is_down:
                down.add(key)
            else:
                down.discard(key)
            out = e.handle(key, is_down, t, rng.choice(APPS))
            assert out in (PASS, SUPPRESS) or isinstance(out, Tap)
            t += rng.expovariate(40)
            if i % 50_000 == 0:
                e.set_enabled(rng.random() < 0.8)
        for key in list(down):
            e.handle(key, False, t, LOGIC)
        e.set_enabled(False)
        e.set_enabled(True)
        assert not e._held_mods, e._held_mods
        assert not e._consumed, e._consumed
        assert not e._space_held
        # And it still works afterwards.
        assert e.handle("q" if hand == "left" else "p", True, t + 1, LOGIC) == Tap("z", ("cmd_l",))


def test_every_key_decides_fast_enough_for_the_macos_hook():
    e = engine()
    rng = random.Random(5)
    lat = []
    for _ in range(50_000):
        key = rng.choice(KEYS)
        t0 = time.perf_counter()
        e.handle(key, True, 0.0, LOGIC)
        e.handle(key, False, 0.01, LOGIC)
        lat.append((time.perf_counter() - t0) / 2)
    print(f"\nper key: p50 {percentile(lat, .5)*1e6:.0f} µs, p99.9 {percentile(lat, .999)*1e6:.0f} µs")
    assert percentile(lat, .999) < 0.002


def test_double_shift_toggle_survives_fast_typing():
    """Typing quickly with Shift for capitals must never flip one-hand mode by accident."""
    rng = random.Random(9)
    e = engine()
    t = 0.0
    for _ in range(20_000):
        e.handle("shift_l", True, t, "com.apple.TextEdit")
        t += rng.uniform(0.03, 0.2)
        k = rng.choice("abcdefghijklmnop")
        e.handle(k, True, t, "com.apple.TextEdit")
        t += rng.uniform(0.02, 0.1)
        e.handle(k, False, t, "com.apple.TextEdit")
        e.handle("shift_l", False, t + 0.01, "com.apple.TextEdit")
        t += rng.uniform(0.05, 0.3)
    assert e.enabled and e.changes == 1  # only the set_enabled at the start


def test_soak():
    e = engine()
    rng = random.Random(2)
    state = {"t": 0.0}

    def step(n):
        for _ in range(200):
            key = rng.choice(KEYS)
            e.handle(key, True, state["t"], rng.choice(APPS))
            e.handle(key, False, state["t"] + 0.05, rng.choice(APPS))
            state["t"] += 0.1
        if n % 500 == 0:
            for m in MODIFIER_KEYS:
                e.handle(m, False, state["t"], LOGIC)

    soak = Soak()
    n = soak.run(step)
    mem, _ = soak.growth()
    print(f"\none-hand soak: {n * 400} key events. {soak.report()}")
    assert mem < 15, soak.report()
