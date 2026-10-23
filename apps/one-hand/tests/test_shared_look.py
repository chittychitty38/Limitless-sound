"""The suite's text size, high contrast and reduced motion settings, on the real window and badge."""
import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")   # no windows pop up while testing

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtGui import QPalette  # noqa: E402
from PySide6.QtWidgets import QApplication, QBoxLayout, QCheckBox, QLabel  # noqa: E402

from onehand import limitless_link  # noqa: E402
from onehand.app import MainWindow, style  # noqa: E402
from onehand.platform_sim import SimBackend  # noqa: E402
from onehand.settings import Prefs, load_layouts  # noqa: E402

DEFAULTS = {"speak": True, "oneVoice": True, "textScale": 1.0, "highContrast": False, "reduceMotion": False,
            "dwellMs": 800, "scanMs": 1200, "language": "en"}


@pytest.fixture
def win(tmp_path, monkeypatch):
    monkeypatch.setenv("LIMITLESS_SOUND_HOME", str(tmp_path))         # no hub here...
    monkeypatch.setattr(limitless_link, "launch_hub", lambda: False)  # ...and don't open one
    monkeypatch.setattr(Prefs, "save", lambda self: None)              # leave the real settings alone
    QApplication.instance() or QApplication([])
    QApplication.setEffectEnabled(Qt.UIEffect.UI_General, True)
    QApplication.setEffectEnabled(Qt.UIEffect.UI_AnimateCombo, True)
    w = MainWindow(SimBackend(front_app="limitless.sim"), Prefs(), load_layouts())
    w.sent = []
    w.suite.link.state = lambda key, value: w.sent.append((key, value))
    yield w
    w.shutdown()


def hub(w, op, **prefs):
    """A welcome or prefs message from the hub, as the link receives it."""
    w.suite.link._handle({"op": op, "prefs": {**DEFAULTS, **prefs}, "actions": [], "states": {}})


def applied(w):
    return [v for k, v in w.sent if k == "prefs.applied"][-1]


def color(widget, role=QPalette.ColorRole.WindowText):
    return widget.palette().color(role).name()


def key_card(w, key):
    return next(card for _, _, card in w.cards if card.key == key)


def test_without_the_hub_nothing_changes(win):
    assert win.styleSheet() == style(1.0)
    assert win.power.font().pixelSize() == 30
    assert "font-size: 17px" in win.badge.label.styleSheet()
    assert QApplication.isEffectEnabled(Qt.UIEffect.UI_AnimateCombo)
    win.engine.set_enabled(True)
    win.show_practice("e", "Record")
    assert key_card(win, "e")._unflash.isActive()   # the usual short flash


def test_welcome_settings_reach_window_and_badge(win):
    hint = win.findChild(QLabel, "hint")
    assert color(hint) == "#c8c8c8"
    win.engine.set_enabled(True)
    win.refresh_power()   # the ON badge is showing
    badge_width = win.badge.width()
    hub(win, "welcome", textScale=1.5, highContrast=True, reduceMotion=True)

    assert win.power.font().pixelSize() == 45
    assert win.badge.label.font().pixelSize() == 26 and win.badge.width() > badge_width
    assert color(hint) == "#ffffff"
    assert color(win, QPalette.ColorRole.Window) == "#000000"
    assert "border: 4px solid #000" in win.badge.label.styleSheet()
    assert not QApplication.isEffectEnabled(Qt.UIEffect.UI_AnimateCombo)
    assert applied(win) == {"textScale": 1.5, "highContrast": True, "reduceMotion": True,
                            "language": "en"}


def test_reduced_motion_keeps_the_pressed_key_lit(win):
    hub(win, "welcome", reduceMotion=True)
    win.engine.set_enabled(True)
    win.show_practice("e", "Record")
    e = key_card(win, "e")
    assert e.property("flash") and not e._unflash.isActive()
    win.show_practice("r", "Split")
    assert not e.property("flash") and key_card(win, "r").property("flash")
    win.engine.set_enabled(False)
    win.refresh_power()
    assert not any(card.property("flash") for _, _, card in win.cards)


def test_changes_apply_live_and_go_back(win):
    hub(win, "welcome")
    assert applied(win) == {"textScale": 1.0, "highContrast": False, "reduceMotion": False, "language": "en"}
    hub(win, "prefs", highContrast=True, reduceMotion=True)
    assert "background: #000" in win.styleSheet()
    assert applied(win) == {"textScale": 1.0, "highContrast": True, "reduceMotion": True, "language": "en"}
    hub(win, "prefs")
    assert win.styleSheet() == style(1.0)
    assert QApplication.isEffectEnabled(Qt.UIEffect.UI_AnimateCombo)
    assert not any(card.steady for _, _, card in win.cards)
    assert applied(win) == {"textScale": 1.0, "highContrast": False, "reduceMotion": False, "language": "en"}


def test_larger_text_and_the_suite_text_size_use_the_bigger(win):
    hub(win, "welcome")
    larger = next(b for b in win.findChildren(QCheckBox) if b.text() == "Larger text")
    larger.click()
    assert win.power.font().pixelSize() == 38
    assert applied(win)["textScale"] == 1.25
    hub(win, "prefs", textScale=1.5)
    assert win.power.font().pixelSize() == 45 and applied(win)["textScale"] == 1.5
    hub(win, "prefs", textScale=1.0)
    assert win.power.font().pixelSize() == 38 and applied(win)["textScale"] == 1.25
    larger.click()
    assert win.power.font().pixelSize() == 30 and applied(win)["textScale"] == 1.0


def test_large_text_gets_the_room_it_needs(win):
    before = win.wide_width
    hub(win, "welcome", textScale=2.0)
    assert win.wide_width > before and win.minimumWidth() > 760
    win.fit_columns(win.wide_width - 1)
    assert win.cols.direction() == QBoxLayout.Direction.TopToBottom
    win.fit_columns(win.wide_width)
    assert win.cols.direction() == QBoxLayout.Direction.LeftToRight
