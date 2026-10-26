import os
import time

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QEvent, Qt  # noqa: E402
from PySide6.QtGui import QKeyEvent  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from limitless_keys.app import KeysApp  # noqa: E402
from limitless_keys.keys import parse_combo  # noqa: E402
from limitless_keys.platforms import Backend  # noqa: E402
from limitless_keys.profiles import Profiles  # noqa: E402
from limitless_keys.runner import Context  # noqa: E402
from limitless_keys.settings import Settings  # noqa: E402
from limitless_keys.ui import (BindingDialog, CheatSheet, HistoryWindow, Setup,  # noqa: E402
                               ShortcutsWindow, qt_event_to_combo)


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture(autouse=True)
def homes(tmp_path, monkeypatch):
    monkeypatch.setenv("LIMITLESS_KEYS_HOME", str(tmp_path / "keys"))
    monkeypatch.setenv("LIMITLESS_SOUND_HOME", str(tmp_path / "suite"))


class FakeBackend(Backend):
    def __init__(self):
        self.sent = []
        self.front_app = ("com.apple.logic10", 100)

    def frontmost(self):
        return self.front_app

    def send(self, combo, pid=None):
        self.sent.append(str(combo))

    def permissions(self):
        return [{"key": "accessibility", "title": "Accessibility", "why": "x", "state": "missing",
                 "required": True}]


def pump(qapp, cond=lambda: False, timeout=2.0):
    end = time.time() + timeout
    while time.time() < end:
        qapp.processEvents()
        if cond():
            return True
        time.sleep(0.01)
    return False


def make_app(tmp_path):
    settings = Settings(tmp_path / "settings.json")
    settings["first_run"] = False
    settings["speak"] = False
    profiles = Profiles(path=tmp_path / "shortcuts.json")
    app = KeysApp(settings, profiles, FakeBackend(), use_keys=False, use_tray=False,
                  link_path=tmp_path / "undo-link.json")
    app.start()
    return app


def test_app_starts_and_shortcuts_run(qapp, tmp_path):
    app = make_app(tmp_path)
    try:
        app.profiles.set_binding("logic", {"keys": "f13", "do": {"keys": "cmd+s"}})
        b = app.profiles.find("com.apple.logic10", parse_combo("f13"))
        app._shortcut(b, "down", "com.apple.logic10", 100)
        assert pump(qapp, lambda: app.backend.sent == ["cmd+s"])
        assert app.link.port and (tmp_path / "undo-link.json").exists()
    finally:
        app.stop()


def test_plugin_undo_from_the_menu_or_hub_goes_to_the_last_daw(qapp, tmp_path):
    app = make_app(tmp_path)
    try:
        sent = []
        app.plugins.link = type("L", (), {"send": lambda self, k, m: sent.append(m) or True})()
        app._poll_front()
        app.plugins.link_message("x", {"op": "hello", "pid": 100, "host": "Apple Logic", "plugin": "EQ"})
        app.plugins.link_message("x", {"op": "step", "id": 4, "label": "Gain"})
        app.backend.front_app = ("org.limitlesssound.keys", 5)   # our own window in front
        app._poll_front()
        assert app.suite_action("pluginUndo", {}) == (True, "")
        assert pump(qapp, lambda: sent == [{"op": "undo", "id": 4}])
        assert pump(qapp, lambda: app.toast.isVisible() and "Gain" in app.toast.label.text())
    finally:
        app.stop()


def test_suite_press_runs_a_shortcut_and_pause(qapp, tmp_path):
    app = make_app(tmp_path)
    try:
        app._poll_front()
        app.profiles.set_binding("logic", {"keys": "f14", "do": {"keys": "cmd+b"}})
        ok, label = app.suite_action("press", {"shortcut": "f14"})
        assert ok and pump(qapp, lambda: app.backend.sent == ["cmd+b"])
        assert app.suite_action("press", {"shortcut": "f19"})[0] is False
        app.suite_action("pause", {})
        assert app.engine.enabled is False and app.settings["enabled"] is False
        app.suite_action("resume", {})
        assert app.engine.enabled
        assert app.suite_action("nope", {})[0] is False
    finally:
        app.stop()


def test_cheat_sheet_lists_the_front_apps_shortcuts(qapp, tmp_path):
    app = make_app(tmp_path)
    try:
        app.app_action("cheatSheet", Context("com.avid.ProTools", 1))
        assert app.cheat.isVisible()
        texts = [w.text() for w in app.cheat.findChildren(type(app.toast.label))]
        assert "Your shortcuts in Pro Tools" in texts
        assert "Undo the last plugin change" in texts
        app.app_action("cheatSheet", Context("com.avid.ProTools", 1))
        assert not app.cheat.isVisible()
    finally:
        app.stop()


def test_windows_open(qapp, tmp_path):
    app = make_app(tmp_path)
    try:
        app.show_shortcuts()
        app.show_history()
        app.show_setup()
        assert app.shortcuts_window.isVisible() and app.history_window.isVisible()
        assert app.setup_window.isVisible()
        assert app.setup_window.perm_rows["accessibility"][2].isVisibleTo(app.setup_window)
    finally:
        app.stop()


def test_shortcut_editor_saves_a_binding(qapp, tmp_path):
    profiles = Profiles(path=tmp_path / "shortcuts.json")
    dlg = BindingDialog(profiles, "protools")
    with pytest.raises(ValueError):
        dlg.result_binding()               # no shortcut yet
    dlg.start_recording("trigger")
    dlg.got_combo(parse_combo("alt+cmd+z"))
    assert "Restore Last Selection" in dlg.notes.text()
    dlg.kind.setCurrentIndex(dlg.kind.findData("menu"))
    dlg.menu_edit.setText("Edit")
    with pytest.raises(ValueError):
        dlg.result_binding()
    dlg.menu_edit.setText("Edit > Restore Last Selection")
    dlg._save()
    assert profiles.find("com.avid.ProTools", parse_combo("alt+cmd+z")).action == \
        {"menu": "Edit > Restore Last Selection"}


def test_shortcut_editor_records_keys_to_press_and_loads_existing(qapp, tmp_path):
    profiles = Profiles()
    dlg = BindingDialog(profiles, "logic", {"keys": "f2", "do": {"keys": "cmd+a, cmd+c"}, "repeat": True})
    assert dlg.keys_edit.text() == "cmd+a, cmd+c" and dlg.repeat.isChecked()
    dlg.start_recording("keys")
    dlg.got_combo(parse_combo("cmd+v"))
    assert dlg.result_binding()["do"] == {"keys": "cmd+a, cmd+c, cmd+v"}
    dlg.kind.setCurrentIndex(dlg.kind.findData("steps"))
    dlg.steps_edit.setPlainText('[{"keys": "cmd+a"}, {"wait": 0.1}]')
    assert dlg.result_binding()["do"] == {"steps": [{"keys": "cmd+a"}, {"wait": 0.1}]}
    dlg.steps_edit.setPlainText("[oops")
    with pytest.raises(ValueError):
        dlg.result_binding()


def test_key_typed_into_the_editor_is_a_fallback_recording(qapp):
    dlg = BindingDialog(Profiles(), "logic")
    dlg.start_recording("trigger")
    mods = Qt.AltModifier | Qt.ShiftModifier
    dlg.keyPressEvent(QKeyEvent(QEvent.KeyPress, Qt.Key_K, mods, "k"))
    assert dlg.combo == parse_combo("alt+shift+k")
    assert qt_event_to_combo(QKeyEvent(QEvent.KeyPress, Qt.Key_F13, Qt.NoModifier)) == parse_combo("f13")


def test_shortcuts_window_lists_profiles_and_removes(qapp, tmp_path):
    profiles = Profiles(path=tmp_path / "shortcuts.json")
    w = ShortcutsWindow(profiles)
    assert w.current_scope() == "daws"
    assert w.table.rowCount() == len(profiles.bindings("daws"))
    w.table.selectRow(0)
    w.remove()
    assert w.table.rowCount() == len(profiles.bindings("daws"))
    assert (tmp_path / "shortcuts.json").exists()
    w.add_scope("com.example.synth", "Synth")
    assert w.current_scope() == "com.example.synth" and w.remove_app.isEnabled()
    w._remove_scope()
    assert "com.example.synth" not in profiles.data["apps"]


def test_history_window_shows_changes(qapp):
    from limitless_keys.plugin_undo import PluginUndo

    pu = PluginUndo()
    w = HistoryWindow(pu)
    w.show()
    assert "No plugin changes" in w.list.item(0).text()
    pu.link_message("a", {"op": "hello", "pid": 1, "host": "Avid Pro Tools", "plugin": "Pro-Q 3",
                          "track": "Bass"})
    pu.link_message("a", {"op": "step", "id": 1, "label": "Gain", "before": "0 dB", "after": "3 dB"})
    w.refresh()
    assert "Pro-Q 3 on Bass — Gain: 0 dB → 3 dB" in w.list.item(0).text()
    w.close()


def test_setup_and_cheat_sheet_widgets(qapp):
    s = Setup(login=False)
    s.set_permissions([{"key": "input", "title": "Input Monitoring", "why": "y", "state": "ok",
                        "required": True}])
    assert not s.perm_rows["input"][2].isVisibleTo(s)
    s.set_heard("✓ ⌥⌘Z")
    assert s.heard.text() == "✓ ⌥⌘Z"
    c = CheatSheet()
    c.show_for("Logic Pro", [])
    assert c.isVisible()
