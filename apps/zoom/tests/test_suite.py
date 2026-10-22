"""Limitless Zoom in the Limitless Sound suite (the hub link is replaced by a recorder)."""
import json
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from limitless_zoom.suite import actions
from limitless_zoom.ui import HC_HIGHLIGHT, KeyCaptureDialog, Look
from test_ui import make_app, wait_sent

# The hub's own defaults, as it sends them in "welcome" and "prefs".
SHARED = {"speak": True, "oneVoice": True, "textScale": 1.0, "highContrast": False,
          "reduceMotion": False, "dwellMs": 800, "scanMs": 1200}


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


class Recorder:
    def __init__(self):
        self.log = []

    def did(self, action, intent=None, value=None):
        self.log.append(("did", action, intent))

    def state(self, key, value):
        self.log.append(("state", key, value))

    def say(self, text):
        return False

    def start(self):
        pass

    def stop(self):
        pass


def linked(tmp_path, **kw):
    app, b = make_app(tmp_path, **kw)
    app.suite.link = Recorder()
    return app, b, app.suite.link.log


def test_other_apps_can_zoom(qapp, tmp_path):
    app, b, log = linked(tmp_path)
    assert app.suite.invoke("in", {}, "control") == (True, "Zoom in")
    wait_sent(b, 1)
    assert b.sent == [(("cmd",), "right")]
    assert ("did", "in", "daw.zoomIn") in log


def test_every_input_reports_what_it_did(qapp, tmp_path):
    app, b, log = linked(tmp_path)
    app.run("fit")
    app.run("taller")
    wait_sent(b, 2)
    assert ("did", "fit", "daw.zoomFit") in log and ("did", "taller", None) in log


def test_keys_layer_on_off_and_reported(qapp, tmp_path):
    app, b, log = linked(tmp_path)
    app.suite.invoke("keysOn", {}, "voice")
    assert app.logic.layer_on
    QTest.qWait(50)
    app.suite.invoke("keysOff", {}, "link:keys-dont-fight")
    assert not app.logic.layer_on
    QTest.qWait(50)
    assert [e for e in log if e[0] == "state"] == [("state", "keys", True), ("state", "keys", False)]


def test_unknown_and_local_only_actions(qapp, tmp_path):
    app, _, _ = linked(tmp_path)
    assert not app.suite.invoke("sideways", {}, "x")[0]
    assert not app.suite.invoke("sleep", {}, "x")[0]


def test_shared_dwell_and_scan(qapp, tmp_path):
    app, _, log = linked(tmp_path)
    app.suite.on_prefs({"dwellMs": 1500, "scanMs": 2000})
    assert app.panel.scan_timer.interval() == 2000
    assert all(btn.dwell_ms == 1500 for btn in app.panel.buttons)
    assert log[-1] == ("state", "prefs.applied", {"dwellMs": 1500, "scanMs": 2000})


def hub_link(app):
    """The real link, with no hub behind it: what it would send is kept in a list."""
    sent = []
    app.suite.link._send = lambda msg: sent.append(msg) or True
    return app.suite.link, sent


def applied(sent):
    return [m["value"] for m in sent if m["op"] == "state" and m["key"] == "prefs.applied"]


def test_shared_look_reaches_every_window(qapp, tmp_path):
    effects = QApplication.isEffectEnabled(Qt.UI_General)
    QApplication.setEffectEnabled(Qt.UI_General, True)   # like a desktop whose menus slide and fade
    try:
        app, _ = make_app(tmp_path)
        link, sent = hub_link(app)
        app.run("keys")   # the "ZOOM KEYS ON" badge is showing
        app.show_setup()
        app.capture_dialog = KeyCaptureDialog("Switch", "Press your switch now.", lambda cb: None)
        link._handle({"op": "welcome", "prefs": {**SHARED, "textScale": 1.5, "highContrast": True,
                                                 "reduceMotion": True, "dwellMs": 1200, "scanMs": 1500}})
        assert applied(sent) == [{"textScale": 1.5, "highContrast": True, "reduceMotion": True,
                                  "dwellMs": 1200, "scanMs": 1500}]

        for toast in (app.toast, app.badge):
            assert toast.label.font().pointSizeF() == 45   # 30 pt, half as big again
            assert "background:#000000; border:4px solid #ffffff" in toast.label.styleSheet()
        assert app.badge.isVisible() and app.badge.width() >= app.badge.label.sizeHint().width()
        panel = app.panel
        assert "font-size:33px" in panel.styleSheet() and "background:#000" in panel.styleSheet()
        assert HC_HIGHLIGHT in panel.keys_label.styleSheet()
        assert all(b.look == Look(1.5, True, True) for b in panel.buttons)
        assert all(b.dwell_ms == 1200 for b in panel.buttons) and panel.scan_timer.interval() == 1500
        setup = app.setup_window
        assert "font-size:28px" in setup.styleSheet() and "border:3px solid #fff" in setup.styleSheet()
        assert HC_HIGHLIGHT in setup.key_state.styleSheet()
        assert "font-size:39px" in app.capture_dialog.styleSheet()
        assert not QApplication.isEffectEnabled(Qt.UI_General)   # no sliding or fading menus

        # Back to the defaults: Zoom looks as it does on its own, and says so.
        link._handle({"op": "prefs", "prefs": SHARED})
        assert applied(sent)[-1] == {"textScale": 1.0, "highContrast": False, "reduceMotion": False,
                                     "dwellMs": 800, "scanMs": 1200}
        assert app.toast.label.font().pointSizeF() == 30 and "#ffcc00" in app.toast.label.styleSheet()
        assert "font-size:22px" in panel.styleSheet() and "background:#000" not in panel.styleSheet()
        assert "font-size:19px" in setup.styleSheet() and "border:3px solid #fff" not in setup.styleSheet()
        assert QApplication.isEffectEnabled(Qt.UI_General)
    finally:
        QApplication.setEffectEnabled(Qt.UI_General, effects)


def test_more_accessible_look_wins():
    assert Look(1.0).combined(Look(1.5)) == Look(1.5)
    assert Look(1.8).combined(Look(1.5, True, False)) == Look(1.8, True, False)
    assert Look(1.0, False, True).combined(Look(1.25)) == Look(1.25, False, True)
    assert Look().combined(Look()) == Look()


def test_panel_keeps_its_own_bigger_text(qapp, tmp_path):
    (tmp_path / "s.json").write_text(json.dumps({"button_scale": 1.8}))
    app, _, log = linked(tmp_path)
    app.suite.on_prefs({**SHARED, "textScale": 1.5})
    assert app.panel.look.text_scale == 1.8 and "font-size:39px" in app.panel.styleSheet()
    assert app.toast.label.font().pointSizeF() == 45   # every other window: the suite's 1.5
    assert log[-1][2]["textScale"] == 1.5
    app.show_setup()   # opened later, it starts with the suite's look
    assert "font-size:28px" in app.setup_window.styleSheet()
    app.suite.on_prefs({**SHARED, "textScale": 2.0})
    assert app.panel.look.text_scale == 2.0   # now the suite's is bigger
    assert log[-1][2]["textScale"] == 2.0


def test_reports_only_settings_it_honors(qapp, tmp_path):
    app, _, log = linked(tmp_path)
    app.suite.on_prefs({"speak": False, "oneVoice": False, "textScale": 1.25})
    assert log[-1] == ("state", "prefs.applied", {"textScale": 1.25})


def test_action_list():
    acts = {a["id"]: a for a in actions()}
    assert acts["in"]["intent"] == "daw.zoomIn" and "zoom in" in acts["in"]["phrases"]
    assert "keysOff" in acts and "sleep" not in acts
