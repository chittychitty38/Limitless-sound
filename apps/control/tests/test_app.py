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


def test_hub_prefs_reach_the_settings_page(app, monkeypatch):
    from limitless_control import app as app_module
    monkeypatch.setattr(app_module, "PORT", 0)
    sent = []
    link = app.suite.link
    monkeypatch.setattr(link, "_send", lambda msg: sent.append(msg) or True)
    server = app._serve()
    base = f"http://127.0.0.1:{server.server_address[1]}"

    def served_look():
        req = urllib.request.Request(base + "/api/state", headers={"X-Token": app.token})
        return json.loads(urllib.request.urlopen(req, timeout=5).read())["look"]

    def applied():
        return [m["value"] for m in sent if m.get("op") == "state" and m.get("key") == "prefs.applied"]

    try:
        # On its own, the page looks as it always did.
        assert served_look() == {"textScale": 1.0, "highContrast": False, "reduceMotion": False}
        prefs = {"speak": True, "oneVoice": True, "textScale": 1.0, "highContrast": False, "reduceMotion": False,
                 "dwellMs": 800, "scanMs": 1200}
        link._handle({"op": "welcome", "prefs": prefs, "actions": [], "states": {}})
        assert applied() == [{"textScale": 1.0, "highContrast": False, "reduceMotion": False}]

        link._handle({"op": "prefs", "prefs": {**prefs, "textScale": 1.5, "highContrast": True, "reduceMotion": True}})
        look = {"textScale": 1.5, "highContrast": True, "reduceMotion": True}
        assert served_look() == look
        assert applied()[-1] == look

        page = urllib.request.urlopen(base + "/", timeout=5).read().decode()
        assert "applyLook(st.look)" in page
        assert ":root.high-contrast {" in page and ".reduce-motion *" in page
        assert "font: calc(18px * var(--scale))" in page
    finally:
        server.shutdown()
        server.server_close()
