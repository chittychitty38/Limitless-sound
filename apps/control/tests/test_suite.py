"""Limitless Control in the Limitless Sound suite (the hub link is replaced by a recorder)."""
import threading

import pytest

from limitless_control import profiles
from limitless_control.engine import Engine
from limitless_control.suite import INTENT_FOR_ID, OWN_LOOK, Suite, actions, combine


class Out:
    def __init__(self):
        self.sent, self.spoken, self.suite_say = [], [], None

    def send(self, keys):
        self.sent.append(keys)

    def speak(self, text):
        self.spoken.append(text)

    def log(self, text):
        pass


class FakeApp:
    def __init__(self, app_id="com.apple.logic10"):
        self.lock = threading.RLock()
        self.output = Out()
        self.config = profiles.default_config()
        self.engine = Engine(self.config, self.output)
        self.front_app = app_id
        self.engine.app_changed(app_id)
        self.logged = []
        self.news = 0

    def log(self, text):
        self.logged.append(text)

    def changed(self):
        self.news += 1


class Link:
    def __init__(self):
        self.log, self.suite_actions = [], []

    def did(self, action, intent=None, value=None):
        self.log.append(("did", action, intent))

    def state(self, key, value):
        self.log.append(("state", key, value))

    def invoke(self, action, args=None, on_result=None):
        self.log.append(("invoke", action))
        return True

    def say(self, text):
        return False


@pytest.fixture
def setup():
    app = FakeApp()
    s = Suite(app)
    s.link = Link()
    return app, s


def test_eyes_ask_the_controller_to_record(setup):
    app, s = setup
    ok, msg = s.invoke("record", {}, "gaze")
    assert ok and "Logic Pro" in msg
    assert app.output.sent == ["r"]
    assert ("did", "record", "daw.record") in s.link.log


def test_pro_tools_metronome_uses_click(setup):
    app = FakeApp("com.avid.protools")
    s = Suite(app)
    s.link = Link()
    ok, _ = s.invoke("metronome", {}, "voice")
    assert ok and app.output.sent == ["keypad7"]


def test_switch_reports_shared_daw_commands(setup):
    app, s = setup
    app.engine.press("b", 0.0)          # B: tap = start, hold = record
    app.engine.tick(1.0)
    app.engine.release("b", 1.1)
    assert ("did", "record", "daw.record") in s.link.log


def test_a_switch_can_trigger_another_app(setup):
    app, s = setup
    app.config["profiles"][0]["layers"][0]["a"] = {"tap": {"command": "suite", "suite": "color.on", "say": "Colors on"}}
    app.engine.reload(app.config, app.front_app)
    app.engine.press("a", 0.0)
    app.engine.tick(0.1)
    assert ("invoke", "color.on") in s.link.log
    assert app.output.spoken[-1] == "Colors on"
    assert app.output.sent == []


def test_switched_off_controller_does_not_trigger_other_apps(setup):
    app, s = setup
    app.engine.enabled = False
    app.engine._fire({"command": "suite", "suite": "zoom.in"}, "a", 0.0)
    assert ("invoke", "zoom.in") not in s.link.log


def test_other_apps_switch_it_on_and_off_and_change_layer(setup):
    app, s = setup
    assert s.invoke("off", {}, "voice")[1] == "Controller off" and not app.engine.enabled
    assert s.invoke("toggle", {}, "voice")[0] and app.engine.enabled
    assert s.invoke("layer", {}, "gaze") == (True, "Layer 2")
    states = [e for e in s.link.log if e[0] == "state"]
    assert ("state", "enabled", False) in states and ("state", "layer", 2) in states


def test_reports_the_daw_in_front(setup):
    app, s = setup
    s.report_state()
    assert ("state", "app.daw", True) in s.link.log
    app.front_app = "com.apple.finder"
    app.engine.app_changed(app.front_app)
    s.report_state()
    assert ("state", "app.daw", False) in s.link.log


def test_action_list_covers_every_mapped_intent():
    ids = {a["id"] for a in actions()}
    assert {i.split(".")[1] for i in INTENT_FOR_ID.values()} <= ids
    assert {"on", "off", "toggle", "layer"} <= ids


def test_the_more_accessible_look_wins():
    assert combine(OWN_LOOK, {}) == OWN_LOOK                    # no hub: the page looks as it always did
    mine = {"textScale": 1.75, "highContrast": True, "reduceMotion": False}
    shared = {"textScale": 1.5, "highContrast": False, "reduceMotion": True, "dwellMs": 1200, "speak": False}
    assert combine(mine, shared) == {"textScale": 1.75, "highContrast": True, "reduceMotion": True}
    assert combine(OWN_LOOK, shared) == {"textScale": 1.5, "highContrast": False, "reduceMotion": True}
    assert combine(OWN_LOOK, {"textScale": 9})["textScale"] == 2.0
    assert combine(OWN_LOOK, {"textScale": "big"})["textScale"] == 1.0


def test_shared_settings_are_applied_and_reported(setup):
    app, s = setup
    prefs = {"speak": True, "oneVoice": True, "textScale": 1.5, "highContrast": True, "reduceMotion": False,
             "dwellMs": 800, "scanMs": 1200}
    s.on_prefs(prefs)
    look = {"textScale": 1.5, "highContrast": True, "reduceMotion": False}
    assert app.look == look
    assert app.news, "a settings page waiting for news hears about the new look"
    assert s.link.log == [("state", "prefs.applied", look)]   # only the settings it really honors

    s.on_prefs({**prefs, "dwellMs": 1500})                     # nothing it uses changed: nothing to say
    assert len(s.link.log) == 1
    s.on_prefs({**prefs, "reduceMotion": True})
    assert s.link.log[-1] == ("state", "prefs.applied", {**look, "reduceMotion": True})

    s.on_connected(True)                                       # joining again: say it again
    s.on_prefs({**prefs, "reduceMotion": True})
    assert s.link.log[-1] == ("state", "prefs.applied", {**look, "reduceMotion": True})


def test_the_settings_page_takes_the_suites_language_and_says_so(setup):
    app, s = setup
    s.on_prefs({"textScale": 1.0, "language": "es"})
    assert app.language == "es" and app.news
    assert s.link.log[-1] == ("state", "prefs.applied", {**OWN_LOOK, "language": "es"})
    s.on_prefs({"textScale": 1.0, "language": "fr"})          # one the page doesn't have: English
    assert app.language == "en"
    assert s.link.log[-1] == ("state", "prefs.applied", {**OWN_LOOK, "language": "en"})
    s.on_connected(False)                                      # no hub: the computer's language
    assert app.language is None
