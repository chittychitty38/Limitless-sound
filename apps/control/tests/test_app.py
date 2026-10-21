import sys

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
