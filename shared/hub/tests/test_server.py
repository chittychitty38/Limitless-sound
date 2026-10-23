"""The real hub on real sockets, with tools connected through the Python Limitless Link client."""

import json
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "clients" / "python"))
from limitless_link import Link  # noqa: E402

from limitless_hub import paths  # noqa: E402
from limitless_hub.server import Hub, running_hub  # noqa: E402


class Speaker:
    def __init__(self):
        self.said = []

    def say(self, text, lang="en"):
        self.said.append(text)


def wait_for(cond, timeout=3.0):
    end = time.time() + timeout
    while time.time() < end:
        if cond():
            return True
        time.sleep(0.02)
    return False


@pytest.fixture
def hub(tmp_path, monkeypatch):
    monkeypatch.setenv("LIMITLESS_SOUND_HOME", str(tmp_path))
    h = Hub({}, port=0, http_port=0, speaker=Speaker()).start()
    yield h
    h.stop()


def tool(tool_id, actions=(), **kw):
    seen = {"invokes": [], "events": [], "prefs": []}

    def on_invoke(action, args, source):
        seen["invokes"].append((action, args, source))
        return True, f"did {action}"

    link = Link(tool_id, tool_id.title(), "1.0", actions=list(actions), on_invoke=kw.pop("on_invoke", on_invoke),
                on_event=lambda n, v, s: seen["events"].append((n, v, s)),
                on_prefs=lambda p: seen["prefs"].append(p), retry=0.1, **kw).start()
    assert wait_for(lambda: link.connected), f"{tool_id} never connected"
    return link, seen


def http(hub, method, path, body=None, token=True, host=None):
    req = urllib.request.Request(f"http://127.0.0.1:{hub.http_port}{path}", method=method,
                                 data=json.dumps(body).encode() if body is not None else None)
    if token:
        req.add_header("X-Limitless-Token", hub.token)
    if host:
        req.add_header("Host", host)
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


def test_link_file_is_written_and_private(hub, tmp_path):
    info = json.loads((tmp_path / "link.json").read_text())
    assert info["port"] == hub.port and info["token"] == hub.token
    if sys.platform != "win32":
        assert (tmp_path / "link.json").stat().st_mode & 0o077 == 0
    assert running_hub()["token"] == hub.token


def test_settings_page_starts_without_looking_up_the_computers_name(tmp_path, monkeypatch):
    """http.server looks up the computer's full name as it starts (socket.getfqdn), which can
    wait half a minute on a Mac's multicast DNS (Limitless Control took 35 s to start that way)."""
    import socket
    monkeypatch.setenv("LIMITLESS_SOUND_HOME", str(tmp_path))
    monkeypatch.setattr(socket, "getfqdn", lambda *a: pytest.fail("looked up the computer's name"))
    h = Hub({}, port=0, http_port=0, speaker=Speaker()).start()
    try:
        assert http(h, "GET", "/api/state")[0] == 200
    finally:
        h.stop()


def test_tools_trigger_each_other_through_the_hub(hub):
    zoom, zseen = tool("zoom", [{"id": "in", "label": "Zoom in", "intent": "daw.zoomIn"}])
    control, _ = tool("control", [{"id": "record", "label": "Record", "intent": "daw.record"}])
    results = []
    control.invoke("zoom.in", on_result=results.append)
    assert wait_for(lambda: results)
    assert results[0]["ok"] and results[0]["message"] == "did in"
    assert zseen["invokes"][0][:1] == ("in",) and zseen["invokes"][0][2] == "control"
    zoom.stop(); control.stop()


def test_intent_from_eyes_reaches_controller(hub):
    """GazeStage can't press keys; asking for daw.record gets the controller to press them."""
    control, cseen = tool("control", [{"id": "record", "label": "Record", "intent": "daw.record"}])
    gaze, _ = tool("gaze")
    gaze.invoke("daw.record")
    assert wait_for(lambda: cseen["invokes"])
    assert cseen["invokes"][0][0] == "record"
    control.stop(); gaze.stop()


def test_take_guard_end_to_end(hub):
    voice, vseen = tool("voice", [{"id": "takeGuard", "label": "Take mode"}, {"id": "takeGuardOff", "label": "Off"}])
    control, _ = tool("control", [{"id": "record", "label": "Record", "intent": "daw.record"}])
    control.did("record")
    assert wait_for(lambda: vseen["invokes"])
    assert vseen["invokes"][0][0] == "takeGuard"
    assert ("daw.record", {"by": "control", "action": "record"}, "control") in vseen["events"]
    voice.stop(); control.stop()


def test_did_inside_a_handler_carries_depth(hub):
    """A tool reporting what it did because of a link must not restart the chain from zero."""
    hub.bus.settings["routes"] = [
        {"id": "ping", "name": "", "when": {"event": "zoom.in"}, "do": [{"action": "zoom.out"}], "on": True},
        {"id": "pong", "name": "", "when": {"event": "zoom.out"}, "do": [{"action": "zoom.in"}], "on": True},
    ]
    calls = []
    holder = {}

    def on_invoke(action, args, source):
        calls.append(action)
        holder["link"].did(action)
        return True

    zoom, _ = tool("zoom", [{"id": "in", "label": "in"}, {"id": "out", "label": "out"}], on_invoke=on_invoke)
    holder["link"] = zoom
    zoom.did("in")
    time.sleep(0.5)
    assert 1 <= len(calls) <= 6  # stopped by depth, not by luck
    zoom.stop()


def test_say_goes_through_one_voice(hub):
    zoom, _ = tool("zoom")
    assert zoom.say("Zoom in")
    assert wait_for(lambda: hub.bus.speaker.said == ["Zoom in"])
    hub.bus.set_prefs({"oneVoice": False})
    assert wait_for(lambda: zoom.prefs.get("oneVoice") is False)
    assert not zoom.say("Zoom out")  # the tool speaks for itself again
    zoom.stop()


def test_prefs_reach_tools(hub):
    zoom, zseen = tool("zoom")
    status, _ = http(hub, "POST", "/api/prefs", {"prefs": {"textScale": 1.5}})
    assert status == 200
    assert wait_for(lambda: zseen["prefs"] and zseen["prefs"][-1]["textScale"] == 1.5)
    zoom.stop()


def test_hub_restart_tools_reconnect(tmp_path, monkeypatch):
    monkeypatch.setenv("LIMITLESS_SOUND_HOME", str(tmp_path))
    h1 = Hub({}, port=0, http_port=0, speaker=Speaker()).start()
    zoom, _ = tool("zoom")
    h1.stop()
    assert wait_for(lambda: not zoom.connected)
    h2 = Hub({}, port=0, http_port=0, speaker=Speaker()).start()
    assert wait_for(lambda: zoom.connected, 5)
    assert "zoom" in h2.bus.tools
    zoom.stop(); h2.stop()


def test_link_without_hub_is_harmless(tmp_path, monkeypatch):
    monkeypatch.setenv("LIMITLESS_SOUND_HOME", str(tmp_path))
    link = Link("zoom", "Zoom", retry=0.05).start()
    time.sleep(0.2)
    assert not link.connected
    assert link.invoke("daw.record") is False
    assert link.say("hi") is False
    link.did("in"); link.state("keys", True)  # no errors
    link.stop()


def test_http_needs_token_and_local_host(hub):
    assert http(hub, "GET", "/api/state", token=False)[0] == 403
    assert http(hub, "GET", "/", token=False)[0] == 403
    assert http(hub, "GET", "/api/state", host="evil.example:80")[0] == 403
    assert http(hub, "POST", f"/api/prefs?t={hub.token}", {"prefs": {}}, token=False)[0] == 403
    status, body = http(hub, "GET", f"/?t={hub.token}", token=False)
    assert status == 200 and b"Limitless Sound" in body


def test_http_do_trigger(hub):
    zoom, zseen = tool("zoom", [{"id": "fit", "label": "Fit"}])
    status, body = http(hub, "GET", f"/do/zoom.fit?t={hub.token}", token=False)
    assert status == 200 and body == b"did fit"
    assert zseen["invokes"][0][2] == "http"
    status, body = http(hub, "GET", f"/do/daw.record?t={hub.token}", token=False)
    assert status == 409
    zoom.stop()


def test_http_routes_and_state(hub):
    status, body = http(hub, "GET", "/api/state")
    state = json.loads(body)
    assert {t["id"] for t in state["tools"]} >= {"voice", "onehand", "zoom", "color", "control", "gaze"}
    routes = state["routes"]
    routes[0]["on"] = False
    status, _ = http(hub, "POST", "/api/routes", {"routes": routes})
    assert status == 200
    saved = json.loads(paths.settings_file().read_text())
    assert saved["routes"][0]["on"] is False
    status, body = http(hub, "POST", "/api/routes", {"routes": [{"id": "x"}]})
    assert status == 400 and json.loads(body)["problems"]


def test_garbage_on_the_socket_is_survived(hub):
    import socket
    s = socket.create_connection(("127.0.0.1", hub.port))
    s.sendall(b"not json\n{\"op\":\"invoke\"}\n")
    s.settimeout(2)
    data = s.recv(4096)
    assert b"error" in data
    s.close()
    zoom, _ = tool("zoom")  # hub still fine
    zoom.stop()


def test_cli_do_against_running_hub(hub, capsys):
    from limitless_hub import cli
    zoom, zseen = tool("zoom", [{"id": "in", "label": "in"}])
    assert cli.main(["do", "zoom.in"]) == 0
    assert "did in" in capsys.readouterr().out
    assert cli.main(["do", "voice.do", "solo", "track"]) == 1  # voice not open, not installed here
    zoom.stop()


def test_cli_autostart(tmp_path, monkeypatch, capsys):
    from limitless_hub import cli, launcher
    monkeypatch.setenv("LIMITLESS_SOUND_HOME", str(tmp_path))
    calls = []
    monkeypatch.setattr(launcher, "set_autostart", calls.append)
    assert cli.main(["autostart", "on"]) == 0
    assert calls == [True]
    assert json.loads(paths.settings_file().read_text())["autostart"] is True
    assert cli.main(["autostart", "off"]) == 0 and calls == [True, False]


def test_two_copies_of_one_app_do_not_fight(hub):
    first, _ = tool("zoom")
    second, _ = tool("zoom")
    flips = []
    deadline = time.time() + 1.0
    while time.time() < deadline:
        flips.append(hub.bus.tools.get("zoom"))
        time.sleep(0.01)
    assert second.connected and not first.connected
    assert len({id(c) for c in flips}) == 1, "the two copies kept kicking each other off"
    first.stop()
    second.stop()


def test_answers_are_never_dropped_behind_a_burst_of_events():
    from limitless_hub.server import Outbox
    box = Outbox()
    for i in range(3000):
        box.put(f"event {i}", True)
        if i % 150 == 0:
            box.put(f"result {i}", False)
    lines = []
    box.close()
    while (line := box.get()) is not None:
        lines.append(line)
    assert len([x for x in lines if x.startswith("result")]) == 20
    assert len([x for x in lines if x.startswith("event")]) == Outbox.MAX_EVENTS
    assert lines[-1] == "event 2999"


def test_opening_settings_answers_without_waiting_for_the_browser(monkeypatch):
    """The hub must answer hub.settings within 3 s even when the browser takes half a minute."""
    import webbrowser
    from limitless_hub import launcher

    monkeypatch.setattr(launcher.sys, "platform", "linux")
    monkeypatch.setattr(webbrowser, "open", lambda url: time.sleep(5))
    started = time.monotonic()
    r = launcher.Launcher({}, settings_url=lambda: "http://127.0.0.1:1/").open_settings()
    assert r["ok"] and time.monotonic() - started < 0.5


def test_open_the_log_folder(hub, tmp_path, monkeypatch):
    logs = tmp_path / "Logs"
    monkeypatch.setenv("LIMITLESS_SOUND_LOGS", str(logs))
    opened = []
    hub.launcher.popen = lambda cmd, **kw: opened.append(cmd)
    assert http(hub, "POST", "/api/open-logs", {}, token=False)[0] == 403
    status, body = http(hub, "POST", "/api/open-logs", {})
    assert status == 200 and json.loads(body)["ok"] is True
    # Made if no app has written a log yet, so the file manager never says it's missing.
    assert logs.is_dir() and opened == [[opened[0][0], str(logs)]]


@pytest.mark.parametrize("platform, opener", [("darwin", "open"), ("win32", "explorer"), ("linux", "xdg-open")])
def test_open_folder_uses_the_computers_file_manager(tmp_path, monkeypatch, platform, opener):
    from limitless_hub.launcher import Launcher
    opened = []
    monkeypatch.setattr(sys, "platform", platform)
    result = Launcher({}, popen=lambda cmd, **kw: opened.append(cmd)).open_folder(tmp_path)
    assert result["ok"] is True and opened == [[opener, str(tmp_path)]]

    def broken(cmd, **kw):
        raise OSError("no file manager")
    result = Launcher({}, popen=broken).open_folder(tmp_path)
    assert result == {"ok": False, "message": f"Couldn't open {tmp_path}: no file manager"}
