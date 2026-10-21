import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QEvent, QPointF
from PySide6.QtGui import QEnterEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from limitless_zoom.app import ZoomApp, send_remote
from limitless_zoom.platforms import Backend
from limitless_zoom.settings import Settings
from limitless_zoom.ui import Panel


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


class FakeBackend(Backend):
    os_name = "mac"

    def __init__(self, front="com.apple.logic10"):
        super().__init__()
        self.front, self.sent, self.activated = front, [], []

    def frontmost(self):
        return self.front, 123

    def send(self, combo):
        self.sent.append(combo)

    def activate(self, handle):
        self.activated.append(handle)


def hover(widget):
    pos = QPointF(5, 5)
    QApplication.sendEvent(widget, QEnterEvent(pos, pos, pos))


def test_dwell_presses_button(qapp):
    p = Panel(dwell_ms=150)
    got = []
    p.action.connect(got.append)
    p.show()
    hover(p.buttons[1])
    QTest.qWait(260)
    assert got and got[0] == "in"
    QApplication.sendEvent(p.buttons[1], QEvent(QEvent.Leave))
    n = len(got)
    QTest.qWait(250)
    assert len(got) == n  # leaving stops it


def test_dwell_can_be_turned_off(qapp):
    p = Panel(dwell_ms=100)
    got = []
    p.action.connect(got.append)
    p.toggle_dwell()
    hover(p.buttons[0])
    QTest.qWait(200)
    assert got == []
    assert p.dwell_button.dwell_enabled


def test_switch_scanning(qapp):
    p = Panel(scan_ms=100)
    got = []
    p.action.connect(got.append)
    p.switch_pressed()  # starts scanning on the first button
    assert p.scanning() and p.scan_index == 0
    p.switch_pressed()
    assert got == ["out"]
    QTest.qWait(150)
    assert p.scan_index == 1
    p.switch_pressed()
    assert got == ["out", "in"]
    p.toggle_scan()
    assert not p.scanning()


def make_app(tmp_path, front="com.apple.logic10"):
    s = Settings(tmp_path / "s.json")
    s["first_run"] = False
    s["speak"] = False
    b = FakeBackend(front)
    app = ZoomApp(s, b, use_keys=False, use_voice=False, use_tray=False)
    return app, b


def wait_sent(b, n):
    for _ in range(50):
        if len(b.sent) >= n:
            return
        QTest.qWait(20)


def test_app_sends_logic_keys(qapp, tmp_path):
    app, b = make_app(tmp_path)
    app.start()
    app.run("in")
    app.run("fit")
    wait_sent(b, 2)
    assert b.sent == [(("cmd",), "right"), ((), "z")]
    assert app.toast.label.text() == "Fit to window"


def test_again_repeats_last_action(qapp, tmp_path):
    app, b = make_app(tmp_path)
    app.run("taller")
    app.run("again")
    wait_sent(b, 2)
    assert b.sent == [(("cmd",), "down")] * 2


def test_panel_button_reaches_daw(qapp, tmp_path):
    app, b = make_app(tmp_path, front="com.avid.ProTools")
    app.show_panel()
    app.panel.buttons[1].click()
    wait_sent(b, 1)
    assert b.sent == [(("cmd",), "]")]


def test_layer_from_voice_and_badge(qapp, tmp_path):
    app, b = make_app(tmp_path)
    app.run("keys")
    assert app.logic.layer_on and app.badge.isVisible()
    app.run("keys")
    assert not app.logic.layer_on and not app.badge.isVisible()


def test_remote_command(qapp, tmp_path):
    app, b = make_app(tmp_path)
    assert send_remote("out")
    for _ in range(50):
        QTest.qWait(20)
        if b.sent:
            break
    assert b.sent == [(("cmd",), "left")]
