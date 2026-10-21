"""Limitless Zoom in the Limitless Sound suite (the hub link is replaced by a recorder)."""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from limitless_zoom.suite import actions
from test_ui import make_app, wait_sent


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
    app, _, _ = linked(tmp_path)
    app.suite.on_prefs({"dwellMs": 1500, "scanMs": 2000})
    assert app.panel.scan_timer.interval() == 2000
    assert all(btn.dwell_ms == 1500 for btn in app.panel.buttons)


def test_action_list():
    acts = {a["id"]: a for a in actions()}
    assert acts["in"]["intent"] == "daw.zoomIn" and "zoom in" in acts["in"]["phrases"]
    assert "keysOff" in acts and "sleep" not in acts
