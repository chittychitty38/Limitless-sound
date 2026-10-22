"""The guided setup: answers in, the right apps and shared settings out."""

import json

from limitless_hub import catalog
from limitless_hub.setup import BIG_TEXT, INPUTS, choices, plan
from test_server import http, hub  # noqa: F401  (the real hub on real sockets)


def test_each_way_of_playing_brings_in_its_apps_in_the_suite_order():
    assert plan(["voice"], {})["tools"] == ["voice"]
    assert plan(["eyes"], {})["tools"] == ["zoom", "gaze"]
    assert plan(["switch", "controller"], {})["tools"] == ["zoom", "control"]
    every = plan(list(INPUTS), {})["tools"]
    assert every == [t for t in catalog.TOOLS if t in every] and set(every) == set(catalog.TOOLS)


def test_unknown_answers_and_bad_sizes_are_ignored():
    p = plan(["voice", "telepathy", None], {"textScale": "huge", "highContrast": 1})
    assert p["inputs"] == ["voice"] and p["prefs"] == {"textScale": 1.0, "highContrast": True}
    assert plan([], {"textScale": 9})["prefs"]["textScale"] == 2.0


def test_bigger_text_and_zoom_never_leaves_text_small():
    assert plan(["vision"], {"textScale": 1.0})["prefs"]["textScale"] == BIG_TEXT
    assert plan(["vision"], {"textScale": 2.0})["prefs"]["textScale"] == 2.0


def test_every_choice_has_plain_words():
    for c in choices():
        assert c["label"] and len(c["label"]) <= 60 and c["about"].endswith(".")


def test_the_page_applies_the_answers_for_every_app(hub):  # noqa: F811
    state = json.loads(http(hub, "GET", "/api/state")[1])
    assert state["setupDone"] is False and len(state["setupChoices"]) == len(INPUTS)
    code, body = http(hub, "POST", "/api/setup", {"inputs": ["voice", "vision"],
                                                   "look": {"textScale": 1.25, "highContrast": True}})
    r = json.loads(body)
    assert code == 200 and r["tools"] == ["voice", "zoom"]
    assert r["prefs"]["textScale"] == BIG_TEXT and r["prefs"]["highContrast"] is True
    state = json.loads(http(hub, "GET", "/api/state")[1])
    assert state["setupDone"] is True and state["startTools"] == ["voice", "zoom"]
    assert state["setupInputs"] == ["voice", "vision"] and state["prefs"]["textScale"] == BIG_TEXT


def test_skipping_the_setup_changes_nothing_else(hub):  # noqa: F811
    before = json.loads(http(hub, "GET", "/api/state")[1])
    assert http(hub, "POST", "/api/setup", {"skip": True})[0] == 200
    after = json.loads(http(hub, "GET", "/api/state")[1])
    assert after["setupDone"] is True
    assert after["prefs"] == before["prefs"] and after["startTools"] == before["startTools"]
