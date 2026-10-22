import os
import subprocess
import sys
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QEvent, QPointF
from PySide6.QtGui import QEnterEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from limitless_zoom.app import ZoomApp
from limitless_zoom.platforms import Backend
from limitless_zoom.settings import Settings
from limitless_zoom.ui import Look, Panel, Toast


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
    for _ in range(100):  # CI machines can be slow; give it up to 2 s
        if got:
            break
        QTest.qWait(20)
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
    for _ in range(100):  # one step after 100 ms; CI machines may be slow
        if p.scan_index == 1:
            break
        QTest.qWait(20)
    assert p.scan_index == 1
    p.switch_pressed()
    assert got == ["out", "in"]
    p.toggle_scan()
    assert not p.scanning()


def test_reduced_motion_dwell_bar_steps(qapp):
    p = Panel(dwell_ms=150)
    b = p.buttons[1]
    b.progress = 0.3
    assert b.shown_progress() == 0.3   # slides
    p.set_look(Look(reduce_motion=True))
    assert b.shown_progress() == 0.5   # a quarter at a time
    b.progress = 0.8
    assert b.shown_progress() == 1.0
    b.progress = 0.0
    got = []
    p.action.connect(got.append)
    p.show()
    hover(b)
    for _ in range(100):
        if got:
            break
        QTest.qWait(20)
    assert got and got[0] == "in"   # and dwelling still presses
    QApplication.sendEvent(b, QEvent(QEvent.Leave))
    p.hide()


def test_big_text_fits_and_stays_on_screen(qapp):
    p = Panel()
    p.show()
    area = p.screen().availableGeometry()
    p.move(area.right() - p.width() - 20, area.top() + 80)
    right = p.x() + p.width()
    p.set_look(Look(2.0, high_contrast=True))
    for b in p.buttons:   # every button is big enough for its text
        assert b.width() >= b.sizeHint().width() and b.height() >= b.sizeHint().height()
    assert p.x() >= area.left() and (p.x() + p.width() == right or p.x() == area.left())
    p.set_look(Look())
    assert p.width() == 440 and p.x() + p.width() == right   # back to its usual size
    p.hide()

    t = Toast()
    t.set_look(Look(2.0))
    t.show_text("Waveform bigger isn't available in Logic Pro")
    assert t.label.wordWrap() and t.width() <= area.width()   # wraps instead of running off
    t.set_look(Look())
    t.show_text("Fit")
    assert not t.label.wordWrap()
    t.hide()


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


def test_on_its_own_zoom_looks_as_before(qapp, tmp_path):
    app, b = make_app(tmp_path)
    assert app.look == Look() and app.panel.look == Look(1.0)
    assert app.toast.label.font().pointSizeF() == 30
    assert app.toast.label.styleSheet() == ("color:#000000; background:#ffcc00; "
                                            "border-radius:18px; padding:14px 28px;")
    assert "font-size:22px" in app.panel.styleSheet() and "min-height:96px" in app.panel.styleSheet()
    assert "background:#000" not in app.panel.styleSheet()


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
    # Like "--do out": the sender is another process and waits for the app's answer.
    code = ("import sys; from PySide6.QtCore import QCoreApplication; "
            "from limitless_zoom.app import send_remote; app = QCoreApplication([]); "
            "sys.exit(0 if send_remote('out', 3000) else 1)")
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    proc = subprocess.Popen([sys.executable, "-c", code], cwd=root)
    t0 = time.monotonic()
    while proc.poll() is None and time.monotonic() - t0 < 10:
        QTest.qWait(20)
    assert proc.returncode == 0
    assert time.monotonic() - t0 < 2.5  # answered, not timed out
    for _ in range(50):
        QTest.qWait(20)
        if b.sent:
            break
    assert b.sent == [(("cmd",), "left")]


class PermBackend(FakeBackend):
    def __init__(self):
        super().__init__()
        self.allowed = False
        self.requested = []

    def permissions(self):
        state = "ok" if self.allowed else "missing"
        return [{"key": "accessibility", "title": "Accessibility", "why": "keys",
                 "state": state, "required": True},
                {"key": "microphone", "title": "Microphone", "why": "voice",
                 "state": "missing", "required": False}]

    def request_permission(self, key):
        self.requested.append(key)


def test_setup_shows_live_permissions_and_restarts_keys(qapp, tmp_path):
    s = Settings(tmp_path / "s.json")
    s["speak"] = False
    b = PermBackend()
    app = ZoomApp(s, b, use_keys=False, use_voice=False, use_tray=False)
    started = []
    app.start_keys = lambda: started.append(1)
    app.start()
    QTest.qWait(400)
    w = app.setup_window
    assert w is not None and w.isVisible()  # first run opens setup
    mark, text, btn = w.perm_rows["accessibility"]
    assert mark.text() == "!" and btn.isVisible()
    assert "still needs Accessibility" in w.start_btn.text()
    btn.click()
    assert b.requested == ["accessibility"]
    b.allowed = True
    app._check_permissions()
    assert mark.text() == "\u2713" and not btn.isVisible()
    assert started == [1, 1]  # started at launch, then again once allowed
    assert w.start_btn.text() == "Start zooming"
    app.run("keys")
    assert w.key_state.text() == "ZOOM KEYS ON"
    app._heard("zoom in")
    assert "zoom in" in w.heard.text()
    w.start_btn.click()
    assert not s["first_run"]


def test_panel_shows_key_state(qapp, tmp_path):
    app, b = make_app(tmp_path)
    assert "Tap" in app.panel.keys_label.text()
    app.run("keys")
    assert app.panel.keys_label.text().startswith("Zoom keys ON")
