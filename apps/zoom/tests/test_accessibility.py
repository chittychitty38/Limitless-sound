"""Screen readers and the keyboard alone, in every window Zoom shows: the toast and the zoom keys
badge, the big-button panel, the key capture dialog and the setup assistant. In English and in Spanish.

Blind and low-vision musicians run their DAW with VoiceOver. What it reads is what Qt's
accessibility interface gives it, so that's what these tests read too."""

import os
import re
import unicodedata

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402
from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtGui import QAccessible  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import (QAbstractButton, QAbstractItemView, QAbstractSlider, QAbstractSpinBox,  # noqa: E402
                               QApplication, QComboBox, QLabel, QLineEdit, QPushButton, QScrollArea,
                               QScrollBar, QWidget)

from limitless_zoom.actions import DEFAULT_LAYER_MAP, PANEL_BUTTONS  # noqa: E402
from limitless_zoom.app import ZoomApp  # noqa: E402
from limitless_zoom.hotkeys import KeyLogic  # noqa: E402
from limitless_zoom.settings import Settings  # noqa: E402
from limitless_zoom.ui import KeyCaptureDialog  # noqa: E402
from limitless_zoom.words import t  # noqa: E402
from test_ui import PermBackend  # noqa: E402

CONTROLS = (QAbstractButton, QComboBox, QAbstractSlider, QAbstractSpinBox, QLineEdit, QAbstractItemView)


# ---- what a screen reader and the Tab key find -------------------------------------------

def said(widget, what=QAccessible.Name):
    """What a screen reader is given for the widget."""
    return QAccessible.queryAccessibleInterface(widget).text(what).strip()


def handles(widget, *events):
    """Whether Zoom's own class for the widget, not Qt's, handles any of these events."""
    return any(e in vars(c) for c in type(widget).__mro__
               if c.__module__.startswith("limitless_zoom") for e in events)


def controls(window):
    """Every control a person can use in the window as it is now, Zoom's own ones too."""
    return [w for w in window.findChildren(QWidget) if w.isVisibleTo(window)
            and (isinstance(w, CONTROLS) or handles(w, "mousePressEvent", "mouseReleaseEvent", "enterEvent"))
            and not isinstance(w, QScrollBar)   # the scroll area scrolls by keyboard itself
            and not isinstance(w.parent(), (QAbstractSpinBox, QComboBox))]   # their own text box


def words(text):
    return " ".join(re.findall(r"[^\W_]+", text.lower()))


def in_words(name):
    """A name in words, not a symbol like "+", "−", "⏻" or "✓"."""
    return bool(re.search(r"[^\W\d_]{2}", name)) and not any(unicodedata.category(c) in ("Sm", "So")
                                                             for c in name)


def problems(window):
    """Everything a screen reader or a keyboard user would trip over in the window."""
    found = []
    for w in controls(window):
        name, kind = said(w), type(w).__name__
        if not in_words(name):
            found.append(f"{kind} {name!r}: no name in words")
        elif isinstance(w, QAbstractButton) and f" {words(w.text())} " not in f" {words(name)} ":
            # Voice Control users say the words they see, so the name holds them.
            found.append(f"{kind} {w.text()!r}: named {name!r}")
        if isinstance(w, QComboBox) and not in_words(said(w, QAccessible.Description)):
            # On a Mac, Qt gives a pop-up menu's chosen item as its title and VoiceOver reads its
            # description as its label: without one, it never says what the menu chooses.
            found.append(f"{kind} {name!r}: no description saying what it chooses")
        if not w.focusPolicy() & Qt.TabFocus and not window.windowFlags() & Qt.WindowDoesNotAcceptFocus:
            found.append(f"{kind} {name!r}: Tab can't reach it")
    for w in window.findChildren(QLabel):
        if w.isVisibleTo(window) and w.accessibleName() and re.search(r"[^\W\d_]{2}", w.text()):
            # On a Mac, VoiceOver reads a label's name as its words: a fixed name hides them.
            found.append(f"label {w.text()!r}: read as {w.accessibleName()!r}")
    for w in [window] + window.findChildren(QWidget):
        if handles(w, "paintEvent") and (w is window or w.isVisibleTo(window)):
            role = QAccessible.queryAccessibleInterface(w).role()
            if w.isWindow() and not (in_words(w.windowTitle()) and in_words(said(w))):
                found.append(f"{type(w).__name__}: a window drawn by Zoom with no title or name")
            elif not w.isWindow() and (role in (QAccessible.NoRole, QAccessible.Client, QAccessible.Border)
                                       or not in_words(said(w))):
                found.append(f"{type(w).__name__}: drawn by Zoom with role {role.name}, name {said(w)!r}")
    return found


def tab_stops(window):
    """Where Tab takes the keyboard in the window, once round. Fails if Tab gets stuck or goes
    round without coming back to where it started: a keyboard trap."""
    window.show()
    window.raise_()
    window.activateWindow()
    for _ in range(100):
        if QApplication.activeWindow() is window:
            break
        QTest.qWait(20)
    assert QApplication.activeWindow() is window, f"{window.windowTitle()} never got the keyboard"
    first = QApplication.focusWidget()
    if first is None or first.window() is not window:
        first = next(w for w in controls(window) if w.isEnabled() and w.focusPolicy() & Qt.TabFocus)
        first.setFocus(Qt.TabFocusReason)
    stops = [first]
    for _ in range(100):
        QTest.keyClick(QApplication.focusWidget(), Qt.Key_Tab)
        here = QApplication.focusWidget()
        if here is first:
            return stops
        assert here not in stops, f"Tab goes round {[said(w) for w in stops]} and never back to the start"
        stops.append(here)
    raise AssertionError("Tab never comes back round")


def assert_tab_order(window, expected):
    stops = tab_stops(window)
    assert all(in_words(said(w)) for w in stops), [said(w) for w in stops]   # every stop is named
    start = stops.index(expected[0]) if expected[0] in stops else 0
    stops = stops[start:] + stops[:start]
    assert [said(w) for w in stops] == [said(w) for w in expected]


def button(window, text):
    return next(b for b in window.findChildren(QPushButton) if b.text() == text)


# ---- Zoom, every window ----------------------------------------------------------------

@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture(params=["en", "es"])
def zoom(request, qapp, tmp_path, monkeypatch):
    """Zoom on first run, with Accessibility still to allow: the panel and setup are open. In each language."""
    monkeypatch.setattr("limitless_zoom.words._computer", request.param)
    s = Settings(tmp_path / "s.json")
    s["speak"] = False
    app = ZoomApp(s, PermBackend(), use_keys=False, use_voice=False, use_tray=False)
    app.start()
    QTest.qWait(400)   # setup opens a moment after the panel
    assert app.setup_window is not None
    yield app
    for w in (app.setup_window, app.panel, app.toast, app.badge):
        w.hide()
    app.poll.stop()
    app.perm_timer.stop()
    app.server.close()   # see test_spanish.py: a later test's "--do" must reach its own app


def test_every_window_names_its_controls(zoom):
    zoom.run("in")
    zoom.run("keys")   # the toast and the badge are up
    dialog = KeyCaptureDialog(t("Zoom keys on/off"), t("Press the key you want to turn the zoom keys on and off."),
                              lambda cb: None)
    for window in (zoom.toast, zoom.badge, zoom.panel, zoom.setup_window, dialog):
        assert problems(window) == [], window.windowTitle()
    # A permission Zoom can't check shows "Open Settings…" instead of "Allow…".
    zoom.setup_window.set_permissions([{"key": "accessibility", "title": "Accessibility", "why": "keys",
                                        "state": "unknown", "required": True}])
    assert problems(zoom.setup_window) == []


def test_panel_buttons_are_named_in_words_not_symbols(zoom):
    names = [said(b) for b in zoom.panel.buttons[:len(PANEL_BUTTONS)]]
    assert names[:2] == [t("Zoom out"), t("Zoom in")]
    assert names[-2:] == [t("Zoom out a lot"), t("Zoom in a lot")]


def test_tab_goes_through_each_window_in_order(zoom):
    w = zoom.setup_window
    allow = [btn for _, _, btn in w.perm_rows.values()]
    # Step 1's buttons first, though they're added after the window is built.
    assert_tab_order(w, [w.findChild(QScrollArea), *allow, button(w, t("Use a different key…")), w.mic,
                         button(w, t("Set up my switch…")), w.start_btn])

    dialog = KeyCaptureDialog(t("Switch"), t("Press your switch now."), lambda cb: None)
    assert_tab_order(dialog, [button(dialog, t("Cancel"))])
    dialog.reject()


def test_every_panel_action_has_a_key(zoom):
    # The panel never takes the keyboard from the DAW (a screen reader presses its buttons
    # without it), so a keyboard alone reaches its actions through the zoom keys instead.
    assert zoom.panel.windowFlags() & Qt.WindowDoesNotAcceptFocus
    assert {name for name, _ in PANEL_BUTTONS} <= set(DEFAULT_LAYER_MAP.values())


@pytest.fixture
def posted(monkeypatch):
    """The accessibility events Zoom posts, as (widget, kind, value)."""
    events = []
    real = QAccessible.updateAccessibility

    def post(event):
        value = event.value() if event.type() == QAccessible.ValueChanged else None
        events.append((event.object(), event.type(), value))
        real(event)

    monkeypatch.setattr(QAccessible, "updateAccessibility", post)
    return events


def assert_read(label, posted, text):
    """A screen reader reads the label's new words, knows what they are, and is told they changed."""
    assert said(label) == text
    assert in_words(said(label, QAccessible.Description)), f"{text!r} doesn't say what it is"
    assert any(o is label and kind == QAccessible.ValueChanged and v == text for o, kind, v in posted), \
        f"no event when it became {text!r}"


def test_status_text_is_read_and_its_changes_posted(zoom, posted):
    w, panel = zoom.setup_window, zoom.panel
    zoom.run("in")
    assert_read(zoom.toast.label, posted, t("Zoom in"))
    zoom.run("keys")
    assert_read(zoom.badge.label, posted, t("ZOOM KEYS ON"))
    assert_read(w.key_state, posted, t("ZOOM KEYS ON"))
    assert_read(panel.keys_label, posted, panel.keys_label.text())
    zoom._heard("zoom in")
    assert_read(panel.voice_label, posted, t("Voice: heard “{text}”", text="zoom in"))
    assert_read(w.heard, posted, t("Heard: “{text}”", text="zoom in"))
    zoom._voice_status("listening on the built-in microphone")
    assert_read(w.voice_status, posted, "listening on the built-in microphone")
    zoom._status("Couldn't press the zoom keys")
    assert_read(panel.status, posted, "Couldn't press the zoom keys")

    # The permission marks are symbols on screen and words to a screen reader.
    mark = w.perm_rows["accessibility"][0]
    assert mark.text() == "!" and said(mark) == t("{name}: {state}", name=t("Accessibility"),
                                                  state=t("not allowed yet"))
    zoom.backend.allowed = True
    zoom._check_permissions()
    assert mark.text() == "✓"
    assert_read(mark, posted, t("{name}: {state}", name=t("Accessibility"), state=t("allowed")))


def test_escape_cancels_choosing_a_key(qapp):
    got = []
    logic = KeyLogic("ctrl_r", "f19", DEFAULT_LAYER_MAP, got.append, got.append, got.append)
    logic.capture_next(got.append)
    assert logic.handle("esc", True, False)   # kept from the DAW
    assert got == [None] and logic.capture is None

    dialog = KeyCaptureDialog("Switch", "Press your switch now.", lambda cb: None)
    dialog.got_key("")   # what arrives through the app when Escape cancels
    assert dialog.key is None and dialog.result() == KeyCaptureDialog.Rejected
