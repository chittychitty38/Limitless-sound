"""The test kit against a stand-in product built on the shared Python client."""

import argparse
import sys
import tempfile
import time
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(ROOT / "shared" / "clients" / "python"))

import las_check  # noqa: E402
from limitless_link import Link  # noqa: E402


def args(**kw):
    base = dict(tool="demo", try_ids=[], try_all=True, wait=5, attest=set(), evidence="")
    return argparse.Namespace(**{**base, **kw})


@pytest.fixture
def hub(monkeypatch):
    home = Path(tempfile.mkdtemp(prefix="las-test-"))
    monkeypatch.setenv("LIMITLESS_SOUND_HOME", str(home))
    real, api = las_check.start_private_hub(home)
    yield api
    real.stop()


def product(actions=None, on_invoke=None, honors=("textScale", "highContrast", "reduceMotion")):
    link = None

    def prefs(p):
        if honors:
            link.state("prefs.applied", {k: p[k] for k in honors if k in p})

    link = Link("demo", "Demo", "1.0", start_hub=False, retry=0.2,
                actions=actions if actions is not None else [{"id": "go", "label": "Go"}, {"id": "play", "label": "Play",
                                                                                            "intent": "daw.play"}],
                on_invoke=on_invoke or (lambda action, a, src: (True, "")),
                on_prefs=prefs if honors is not None else None).start()
    return link


def test_a_good_product_is_adaptive(hub):
    link = product()
    try:
        rep = las_check.check(hub, args())
    finally:
        link.stop()
    assert rep.level_ok("connected"), rep.checks
    assert rep.level_ok("adaptive"), rep.checks
    assert not rep.level_ok("hands-free")


def test_nothing_connects(hub):
    rep = las_check.check(hub, args(wait=0.5))
    assert not rep.level_ok("connected")
    assert [c["id"] for c in rep.checks] == ["C1"]


def test_slow_and_silent_actions_fail(hub):
    def invoke(action, a, src):
        if action == "slow":
            time.sleep(3.5)
            return True, ""
        return False, ""

    link = product(actions=[{"id": "slow", "label": "Slow"}, {"id": "mute", "label": "Mute"}], on_invoke=invoke)
    try:
        rep = las_check.check(hub, args())
    finally:
        link.stop()
    c4 = next(c for c in rep.checks if c["id"] == "C4")
    assert not c4["ok"]
    assert "too slow" in c4["detail"] and "without saying why" in c4["detail"]


def test_bad_intent_and_long_label_fail(hub):
    link = product(actions=[{"id": "x", "label": "L" * 61}, {"id": "y", "label": "Y", "intent": "daw.launchRockets"}])
    try:
        rep = las_check.check(hub, args(try_all=False))
    finally:
        link.stop()
    c3 = next(c for c in rep.checks if c["id"] == "C3")
    assert not c3["ok"] and "labels" in c3["detail"]
    c4 = next(c for c in rep.checks if c["id"] == "C4")
    assert not c4["ok"] and "Not run" in c4["detail"]


def test_ignoring_settings_is_not_adaptive(hub):
    link = product(honors=None)
    try:
        rep = las_check.check(hub, args())
    finally:
        link.stop()
    assert rep.level_ok("connected")
    assert not rep.level_ok("adaptive")


def test_partial_settings_fail_a2(hub):
    link = product(honors=("textScale",))
    try:
        rep = las_check.check(hub, args())
    finally:
        link.stop()
    a1, a2 = (next(c for c in rep.checks if c["id"] == i) for i in ("A1", "A2"))
    assert a1["ok"] and not a2["ok"] and "highContrast" in a2["detail"]


def test_settings_are_put_back(hub):
    before = dict(hub.state()["prefs"])
    link = product()
    try:
        las_check.check(hub, args())
    finally:
        link.stop()
    assert hub.state()["prefs"] == before


def test_attested_levels(hub):
    link = product()
    try:
        rep = las_check.check(hub, args(attest={"hands-free", "co-designed"}, evidence="https://example.org/v"))
    finally:
        link.stop()
    assert all(rep.level_ok(level) for level in las_check.LEVELS)
