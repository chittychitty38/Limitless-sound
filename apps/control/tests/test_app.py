import json
import sys
import urllib.request

import pytest

from limitless_control import login, profiles


@pytest.fixture
def app(tmp_path, monkeypatch):
    monkeypatch.setenv("LIMITLESS_CONFIG", str(tmp_path / "settings.json"))
    from limitless_control.app import App
    return App(dry_run=True)


def test_action_labels(app):
    app.engine.app_changed("com.apple.logic10")
    assert app.action_label(profiles.action("Logic Pro", "record")) == "Record"
    assert app.action_label(profiles.action("", "layer")) == "Layer 2 for the next switch"
    assert app.action_label({"keys": "mod+shift+k"}) in ("Ctrl+Shift+K", "Shift ⌘ K")


def test_last_action_recorded_when_switch_fires(app):
    app.engine.app_changed("com.apple.logic10")
    app.engine.press("a", 0)
    app.engine.tick(0.1)
    assert app.last_action["input"] == "a"
    assert app.last_action["label"] == "Play / stop"


def test_finished_setup_survives_later_saves(app):
    config = profiles.default_config()
    config["setupDone"] = True
    assert app.apply(config) == []
    assert app.apply(profiles.default_config()) == []
    assert app.config["setupDone"] is True
    assert profiles.load(profiles.config_path())["setupDone"] is True


def test_suite_action_uses_up_one_shot_layer(app):
    app.engine.app_changed("com.apple.logic10")
    layers = app.engine.profile["layers"]
    layers[1]["y"] = {"tap": {"command": "suite", "suite": "zoom.in"}}
    app.engine.layer = 1
    app.engine.press("y", 0)
    app.engine.tick(0.1)
    assert app.engine.layer == 0


@pytest.mark.skipif(sys.platform in ("darwin", "win32"), reason="writes a real login item there")
def test_start_at_login_linux(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    assert not login.is_enabled()
    login.set_enabled(True)
    assert login.is_enabled()
    assert "--background" in (tmp_path / "autostart" / "limitless-control.desktop").read_text()
    login.set_enabled(False)
    assert not login.is_enabled()


def test_default_timing_is_the_steady_preset():
    config = profiles.default_config()
    steady = profiles.TIMING_PRESETS["steady"]
    assert config["timing"] == steady["timing"]
    assert config["analogThreshold"] == steady["analogThreshold"]


def test_settings_page_starts_without_looking_up_the_computers_name(app, monkeypatch):
    """http.server looks up the computer's full name as it starts (socket.getfqdn). On an
    Intel Mac that waited 35 s on multicast DNS, and the whole app waited with it."""
    import socket
    from limitless_control import app as app_module
    monkeypatch.setattr(app_module, "PORT", 0)
    monkeypatch.setattr(socket, "getfqdn", lambda *a: pytest.fail("looked up the computer's name"))
    server = app._serve()
    try:
        req = urllib.request.Request(f"http://127.0.0.1:{server.server_address[1]}/api/state",
                                     headers={"X-Token": app.token})
        assert urllib.request.urlopen(req, timeout=5).status == 200
    finally:
        server.shutdown()
        server.server_close()


def test_settings_page_waits_for_news_instead_of_asking_again_and_again(app, monkeypatch):
    """The page asked for the app's state about 6 times a second, which kept Control at about 3%
    of an Intel Mac's CPU while the page was open. It now asks with the version it has: the
    answer comes as soon as something changes (a press shows at once), or after 2 s."""
    import threading
    import time
    from limitless_control import app as app_module
    monkeypatch.setattr(app_module, "PORT", 0)
    server = app._serve()
    base = f"http://127.0.0.1:{server.server_address[1]}"

    def state(since=None):
        url = base + "/api/state" + ("" if since is None else f"?since={since}")
        t = time.monotonic()
        st = json.loads(urllib.request.urlopen(urllib.request.Request(url, headers={"X-Token": app.token}), timeout=10).read())
        return st, time.monotonic() - t

    try:
        first, took = state()
        assert took < 1 and isinstance(first["version"], int)
        same, took = state(first["version"])
        assert 1.8 <= took < 3, f"nothing new: the answer waits about 2 s ({took:.2f} s)"
        assert same["version"] == first["version"]
        threading.Timer(0.3, app._press, ["a"]).start()
        pressed, took = state(first["version"])
        assert took < 1.5, f"a press is news at once ({took:.2f} s)"
        assert pressed["lastInput"]["name"] == "a"
        app._release("a")
        _, took = state(first["version"])
        assert took < 0.5, "a page behind the times is answered at once"
        page = urllib.request.urlopen(base + "/", timeout=5).read().decode()
        assert 'api("/api/state?since=" + version)' in page
    finally:
        server.shutdown()
        server.server_close()


def test_hub_prefs_reach_the_settings_page(app, monkeypatch):
    from limitless_control import app as app_module
    monkeypatch.setattr(app_module, "PORT", 0)
    sent = []
    link = app.suite.link
    monkeypatch.setattr(link, "_send", lambda msg: sent.append(msg) or True)
    server = app._serve()
    base = f"http://127.0.0.1:{server.server_address[1]}"

    def served(key="look"):
        req = urllib.request.Request(base + "/api/state", headers={"X-Token": app.token})
        return json.loads(urllib.request.urlopen(req, timeout=5).read())[key]


    def applied():
        return [m["value"] for m in sent if m.get("op") == "state" and m.get("key") == "prefs.applied"]

    try:
        # On its own, the page looks as it always did, in the computer's language.
        assert served() == {"textScale": 1.0, "highContrast": False, "reduceMotion": False}
        assert served("language") is None
        prefs = {"speak": True, "oneVoice": True, "textScale": 1.0, "highContrast": False, "reduceMotion": False,
                 "dwellMs": 800, "scanMs": 1200}
        link._handle({"op": "welcome", "prefs": prefs, "actions": [], "states": {}})
        assert applied() == [{"textScale": 1.0, "highContrast": False, "reduceMotion": False}]

        link._handle({"op": "prefs", "prefs": {**prefs, "textScale": 1.5, "highContrast": True, "reduceMotion": True}})
        look = {"textScale": 1.5, "highContrast": True, "reduceMotion": True}
        assert served() == look
        assert applied()[-1] == look

        # The suite's language: the page shows it, and the suite hears it is in use.
        link._handle({"op": "prefs", "prefs": {**prefs, "language": "es"}})
        assert served("language") == "es"
        assert applied()[-1] == {"textScale": 1.0, "highContrast": False, "reduceMotion": False, "language": "es"}

        page = urllib.request.urlopen(base + "/", timeout=5).read().decode()
        assert "applyLook(st.look)" in page and "setLanguage(st.language || systemLanguage())" in page
        assert ":root.high-contrast {" in page and ".reduce-motion *" in page
        assert "font: calc(18px * var(--scale))" in page
    finally:
        server.shutdown()
        server.server_close()


def test_the_hub_reads_what_control_says_in_english(app, monkeypatch):
    """The page can be in Spanish, but what Control says out loud is still English."""
    sent = []
    link = app.suite.link
    monkeypatch.setattr(link, "_send", lambda msg: sent.append(msg) or True)
    link.connected, link.prefs = True, {"oneVoice": True, "language": "es"}
    assert app.suite.say("Record")
    assert sent == [{"op": "say", "text": "Record", "lang": "en"}]
    link.prefs = {"oneVoice": False}                          # one voice off: Control speaks itself
    assert not app.suite.say("Record") and len(sent) == 1
    link.connected = False
    assert not app.suite.say("Record")


def test_opening_settings_never_waits_for_the_browser(app, monkeypatch):
    """The controller loop runs on the same thread: a slow browser must not hold up a press."""
    import time
    import webbrowser
    from limitless_control import app as app_module

    monkeypatch.setattr(app_module.sys, "platform", "linux")
    monkeypatch.setattr(webbrowser, "open", lambda url: time.sleep(5))
    app.url = "http://127.0.0.1:1/?t=x"
    started = time.monotonic()
    app.open_settings()
    assert time.monotonic() - started < 0.5
