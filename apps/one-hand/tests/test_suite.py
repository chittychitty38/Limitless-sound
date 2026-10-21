"""One-Hand in the Limitless Sound suite, against a stand-in hub connection."""
import json
from pathlib import Path

from onehand.engine import Engine, Settings, Tap
from onehand.suite import ACTIONS, INTENT_LABELS, Suite

LAYOUTS = json.loads((Path(__file__).parents[1] / "onehand" / "layouts.json").read_text())


class Backend:
    platform = "mac"

    def __init__(self, front="com.apple.logic10"):
        self.front = front
        self.sent = []

    def front_app(self):
        return self.front

    def send(self, tap):
        self.sent.append(tap)


def make(front="com.apple.logic10", platform="mac"):
    b = Backend(front)
    b.platform = platform
    hands = []
    s = Suite(Engine(LAYOUTS, platform, Settings()), b, hands.append)
    reported = []
    s.link.did = lambda action, intent=None, value=None: reported.append((action, intent))
    s.link.state = lambda key, value: reported.append((key, value))
    return s, b, hands, reported


def test_switch_mode_from_another_app():
    s, _, _, _ = make()
    assert s.invoke("on", {}, "control") == (True, "One-hand mode on")
    assert s.engine.enabled
    assert s.invoke("toggle", {}, "voice")[0] and not s.engine.enabled
    s.invoke("off", {}, "voice")
    assert not s.engine.enabled


def test_hand_choice():
    s, _, hands, reported = make()
    assert s.invoke("right", {}, "gaze")[0]
    assert hands == ["right"] and ("hand", "right") in reported


def test_presses_record_for_gazestage_in_logic():
    s, b, _, reported = make()
    ok, msg = s.invoke("record", {}, "gaze")
    assert ok and msg == "Record in Logic Pro"
    assert b.sent == [Tap("r", ())]
    assert reported == [("record", "daw.record")]


def test_undo_uses_platform_modifiers():
    s, b, _, _ = make()
    s.invoke("undo", {}, "voice")
    assert b.sent == [Tap("z", ("cmd_l",))]
    s, b, _, _ = make(front="ProTools.exe", platform="windows")
    s.invoke("undo", {}, "voice")
    assert b.sent and b.sent[0].key == "z" and b.sent[0].mods == ("ctrl_l",)


def test_no_supported_app_in_front():
    s, b, _, _ = make(front="com.apple.finder")
    ok, msg = s.invoke("record", {}, "gaze")
    assert not ok and not b.sent


def test_intent_missing_from_this_daw():
    s, b, _, _ = make(front="com.avid.ProTools")
    ok, msg = s.invoke("metronome", {}, "gaze")
    assert not ok and "Pro Tools" in msg


def test_every_intent_label_exists_somewhere():
    labels = {c["label"] for a in LAYOUTS["apps"] for c in a["commands"]}
    for intent, label in INTENT_LABELS.items():
        assert label in labels, intent
    assert {a["id"] for a in ACTIONS} >= {"on", "off", "toggle", "left", "right", "record"}


def test_without_hub_nothing_breaks(tmp_path, monkeypatch):
    monkeypatch.setenv("LIMITLESS_SOUND_HOME", str(tmp_path))
    b = Backend()
    s = Suite(Engine(LAYOUTS, "mac", Settings()), b, lambda h: None).start()
    s.mode_changed(True)
    assert s.say("One hand on") is False
    s.stop()
