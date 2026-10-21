"""The bus without sockets: tools are lists that collect what the hub sends them."""

import pytest

from limitless_hub import routes
from limitless_hub.bus import Bus

TOKEN = "secret"


class FakeLauncher:
    def __init__(self, installed=()):
        self.installed = set(installed)
        self.cli_calls = []

    def find(self, tool):
        return f"/apps/{tool}" if tool in self.installed else None

    def run_cli(self, tool, action, args):
        self.cli_calls.append((tool, action, args))
        return True, "ok"

    def open(self, tool):
        return {"ok": True, "message": f"Opening {tool}"}

    def open_many(self, tools):
        return {"ok": True, "message": "many"}

    def open_settings(self):
        return {"ok": True, "message": "settings"}


class FakeSpeaker:
    def __init__(self):
        self.said = []

    def say(self, text):
        self.said.append(text)


class Clock:
    t = 0.0

    def __call__(self):
        return self.t


@pytest.fixture
def bus():
    clock = Clock()
    b = Bus({}, TOKEN, speaker=FakeSpeaker(), launcher=FakeLauncher(), clock=clock)
    b.clock_obj = clock
    return b


def connect(bus, tool, actions=(), subscribe=None):
    inbox = []
    conn = bus.attach(inbox.append)
    hello = {"op": "hello", "token": TOKEN, "tool": tool, "name": tool.title(), "actions": list(actions)}
    if subscribe is not None:
        hello["subscribe"] = subscribe
    assert bus.receive(conn, hello)
    assert inbox[0]["op"] == "welcome"
    inbox.clear()
    return conn, inbox


def of(inbox, op):
    return [m for m in inbox if m["op"] == op]


def test_wrong_token_is_refused(bus):
    inbox = []
    conn = bus.attach(inbox.append)
    assert not bus.receive(conn, {"op": "hello", "token": "nope", "tool": "zoom"})
    assert "zoom" not in bus.tools


def test_must_say_hello_first(bus):
    inbox = []
    conn = bus.attach(inbox.append)
    assert not bus.receive(conn, {"op": "invoke", "action": "zoom.in"})


def test_reserved_and_bad_tool_ids_refused(bus):
    for bad in ("hub", "daw", "Zoom", "a b", "x" * 40, 5):
        conn = bus.attach(lambda m: None)
        assert not bus.receive(conn, {"op": "hello", "token": TOKEN, "tool": bad})


def test_any_tool_can_trigger_any_other(bus):
    zoom, zin = connect(bus, "zoom", [{"id": "in", "label": "Zoom in"}])
    control, cin = connect(bus, "control")
    bus.receive(control, {"op": "invoke", "id": 7, "action": "zoom.in"})
    inv = of(zin, "invoke")[0]
    assert inv["action"] == "in" and inv["source"] == "control"
    bus.receive(zoom, {"op": "result", "id": inv["id"], "ok": True, "message": "Zoomed in"})
    assert of(cin, "result") == [{"op": "result", "id": 7, "ok": True, "message": "Zoomed in"}]


def test_unknown_action_on_connected_tool(bus):
    connect(bus, "zoom", [{"id": "in", "label": "Zoom in"}])
    got = []
    bus.invoke("zoom.sideways", on_result=got.append)
    assert not got[0]["ok"] and "sideways" in got[0]["message"]


def test_intent_goes_to_preferred_provider(bus):
    _, voice_in = connect(bus, "voice", [{"id": "rec", "label": "Record", "intent": "daw.record"}])
    _, control_in = connect(bus, "control", [{"id": "record", "label": "Record", "intent": "daw.record"}])
    bus.invoke("daw.record", source="gaze")
    assert of(control_in, "invoke")[0]["action"] == "record"
    assert not of(voice_in, "invoke")
    bus.set_intent_order(["voice", "control"])
    bus.invoke("daw.record", source="gaze")
    assert of(voice_in, "invoke")[0]["action"] == "rec"


def test_intent_with_nobody_open_explains(bus):
    got = []
    bus.invoke("daw.record", on_result=got.append)
    assert not got[0]["ok"] and "Record" in got[0]["message"]


def test_intent_falls_back_to_closed_tool_command_line(bus):
    bus.launcher.installed.add("zoom")
    got = []
    bus.invoke("daw.zoomIn", on_result=got.append)
    assert got[0]["ok"]
    assert bus.launcher.cli_calls == [("zoom", "in", {})]


def test_closed_tool_without_command_line(bus):
    bus.launcher.installed.add("color")
    bus.launcher.run_cli = lambda *a: (False, "Open Limitless Color so it can do that.")
    got = []
    bus.invoke("color.on", on_result=got.append)
    assert not got[0]["ok"] and "Limitless Color" in got[0]["message"]


def test_not_installed(bus):
    got = []
    bus.invoke("color.on", on_result=got.append)
    assert "isn't installed" in got[0]["message"]


def test_did_emits_tool_event_and_intent(bus):
    control, _ = connect(bus, "control", [{"id": "record", "label": "Record", "intent": "daw.record"}])
    _, gin = connect(bus, "gaze")
    bus.receive(control, {"op": "did", "action": "record"})
    names = [m["name"] for m in of(gin, "event")]
    assert names == ["control.record", "daw.record"]


def test_sender_does_not_hear_its_own_event(bus):
    control, cin = connect(bus, "control")
    bus.receive(control, {"op": "state", "key": "enabled", "value": False})
    assert not of(cin, "event")


def test_subscriptions_filter_events(bus):
    control, _ = connect(bus, "control")
    _, vin = connect(bus, "voice", subscribe=["daw.*"])
    bus.receive(control, {"op": "state", "key": "layer", "value": 2})
    bus.receive(control, {"op": "did", "action": "record", "intent": "daw.record"})
    assert [m["name"] for m in of(vin, "event")] == ["daw.record"]


def test_take_guard_sidechain(bus):
    """The signature link: recording from any input puts voice in take mode."""
    _, vin = connect(bus, "voice", [{"id": "takeGuard", "label": "x"}, {"id": "takeGuardOff", "label": "y"}])
    control, _ = connect(bus, "control", [{"id": "record", "label": "Record", "intent": "daw.record"}])
    bus.receive(control, {"op": "did", "action": "record"})
    assert [m["action"] for m in of(vin, "invoke")] == ["takeGuard"]
    assert of(vin, "invoke")[0]["source"] == "link:take-guard"
    vin.clear()
    bus.receive(control, {"op": "did", "action": "stop", "intent": "daw.stop"})
    assert [m["action"] for m in of(vin, "invoke")] == ["takeGuardOff"]


def test_value_condition(bus):
    onehand, _ = connect(bus, "onehand")
    _, zin = connect(bus, "zoom", [{"id": "keysOff", "label": "off"}])
    bus.receive(onehand, {"op": "state", "key": "mode", "value": False})
    assert not of(zin, "invoke")
    bus.receive(onehand, {"op": "state", "key": "mode", "value": True})
    assert [m["action"] for m in of(zin, "invoke")] == ["keysOff"]
    zin.clear()
    bus.receive(onehand, {"op": "state", "key": "mode", "value": True})  # unchanged: no event
    assert not of(zin, "invoke")


def test_disabled_link_does_nothing(bus):
    _, vin = connect(bus, "voice", [{"id": "takeGuard", "label": "x"}])
    control, _ = connect(bus, "control")
    for r in bus.settings["routes"]:
        r["on"] = False
    bus.receive(control, {"op": "did", "action": "record", "intent": "daw.record"})
    assert not of(vin, "invoke")


def test_runaway_link_gets_paused(bus):
    bus.settings["routes"] = [
        {"id": "a", "name": "a", "when": {"event": "zoom.in"}, "do": [{"action": "zoom.out"}], "on": True},
        {"id": "b", "name": "b", "when": {"event": "zoom.out"}, "do": [{"action": "zoom.in"}], "on": True},
    ]
    zoom, zin = connect(bus, "zoom", [{"id": "in", "label": "in"}, {"id": "out", "label": "out"}])
    # A misbehaving tool that reports every action without depth would loop forever.
    for _ in range(40):
        bus.receive(zoom, {"op": "did", "action": "in"})
        bus.receive(zoom, {"op": "did", "action": "out"})
    assert not all(r["on"] for r in bus.settings["routes"])
    assert any("kept setting itself off" in e["text"] for e in bus.log)


def test_depth_stops_chains(bus):
    got = []
    bus.invoke("hub.say", {"text": "hi"}, depth=99, on_result=got.append)
    assert not got[0]["ok"]


def test_timeout_answers_for_silent_tool(bus):
    connect(bus, "zoom", [{"id": "in", "label": "in"}])
    got = []
    bus.invoke("zoom.in", on_result=got.append)
    assert got == []
    bus.clock_obj.t += 10
    bus.tick()
    assert got and not got[0]["ok"]


def test_hub_say_and_speech_pref(bus):
    bus.invoke("hub.say", {"text": "Hello"})
    assert bus.speaker.said == ["Hello"]
    bus.set_prefs({"speak": False})
    bus.invoke("hub.say", {"text": "Quiet"})
    assert bus.speaker.said == ["Hello"]


def test_prefs_are_clamped_and_broadcast(bus):
    _, zin = connect(bus, "zoom")
    prefs = bus.set_prefs({"textScale": 9, "dwellMs": 10, "unknown": 1, "highContrast": 1})
    assert prefs["textScale"] == 2.0 and prefs["dwellMs"] == 250 and prefs["highContrast"] is True
    assert "unknown" not in prefs
    assert of(zin, "prefs")[0]["prefs"]["textScale"] == 2.0


def test_routes_are_validated(bus):
    assert bus.set_routes([{"id": "x", "when": {"event": "daw.record"}, "do": [{"action": "zoom.nope"}]}])
    assert bus.set_routes([{"id": "x", "when": {}, "do": []}])
    good = [{"id": "x", "name": "x", "when": {"event": "daw.record"}, "do": [{"action": "zoom.fit"}], "on": True}]
    assert bus.set_routes(good) == []
    assert bus.settings["routes"] == good


def test_catalog_lists_closed_tools_and_live_actions(bus):
    connect(bus, "zoom", [{"id": "in", "label": "Zoom in", "intent": "daw.zoomIn"}])
    acts = {a["id"]: a for a in bus.all_actions()}
    assert acts["zoom.in"]["live"] is True
    assert "zoom.out" not in acts           # the live list replaces the catalog for that tool
    assert acts["color.on"]["live"] is False
    assert acts["daw.zoomIn"]["live"] is True
    assert acts["daw.record"]["live"] is False
    assert "hub.say" in acts


def test_new_tool_is_announced_to_others(bus):
    _, zin = connect(bus, "zoom")
    connect(bus, "color", [{"id": "on", "label": "Colors on"}])
    assert any(a["id"] == "color.on" and a["live"] for a in of(zin, "actions")[-1]["actions"])
    assert [m["name"] for m in of(zin, "event")] == ["color.connected"]


def test_reconnect_replaces_old_connection(bus):
    old, oin = connect(bus, "zoom")
    new, _ = connect(bus, "zoom")
    assert bus.tools["zoom"] is new and old.closed
    bus.detach(old)  # the old socket closing later must not unregister the new one
    assert bus.tools["zoom"] is new


def test_third_party_tool_can_join(bus):
    deck, _ = connect(bus, "streamdeck", [{"id": "page", "label": "Next page"}])
    control, cin = connect(bus, "control")
    bus.receive(control, {"op": "invoke", "id": 1, "action": "streamdeck.page"})
    snap = bus.snapshot()
    assert any(t["id"] == "streamdeck" for t in snap["tools"])


def test_bad_intents_and_actions_are_cleaned(bus):
    conn, _ = connect(bus, "zoom", [{"id": "in", "label": "in", "intent": "rm -rf"}, {"label": "no id"}, "junk"])
    assert list(conn.actions) == ["in"] and "intent" not in conn.actions["in"]


def test_snapshot_log_since(bus):
    bus.invoke("hub.say", {"text": "one"})
    connect(bus, "zoom")
    snap = bus.snapshot()
    last = snap["log"][-1]["seq"]
    assert bus.snapshot(last)["log"] == []


def test_default_routes_are_valid(bus):
    known = bus.known_action_ids()
    for r in routes.DEFAULT_ROUTES:
        assert routes.validate(r, known) == [], r["id"]


def test_link_to_closed_app_is_quiet(bus):
    control, _ = connect(bus, "control")
    bus.receive(control, {"op": "did", "action": "record", "intent": "daw.record"})
    assert not any(e["kind"] == "warn" for e in bus.log)


def test_vendored_clients_match_shared_copy():
    """Apps carry a copy of the Python client; it must not drift from shared/."""
    from pathlib import Path
    root = Path(__file__).resolve().parents[3]
    shared = (root / "shared" / "clients" / "python" / "limitless_link.py").read_text()
    for copy in (root / "apps").rglob("limitless_link.py"):
        assert copy.read_text() == shared, f"{copy} differs from shared/clients/python/limitless_link.py"


def test_mac_executable_reads_info_plist(tmp_path):
    import plistlib
    from limitless_hub.catalog import mac_executable
    app = tmp_path / "Limitless Color.app"
    (app / "Contents" / "MacOS").mkdir(parents=True)
    with open(app / "Contents" / "Info.plist", "wb") as f:
        plistlib.dump({"CFBundleExecutable": "limitless-color"}, f)
    assert mac_executable(app, "Limitless Color").name == "limitless-color"
    assert mac_executable(tmp_path / "Missing.app", "Fallback").name == "Fallback"
