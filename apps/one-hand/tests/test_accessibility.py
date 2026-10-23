"""Screen readers and the keyboard alone, in every window One-Hand shows: the main window, the
macOS permission page that opens on first launch, and the ON badge. In English and in Spanish.

Blind and low-vision musicians run their DAW with VoiceOver. What it reads is what Qt's
accessibility interface gives it, so that's what these tests read too."""
import os
import re
import unicodedata

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")   # no windows pop up while testing

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtGui import QAccessible  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import (QAbstractButton, QAbstractItemView, QAbstractSlider, QAbstractSpinBox,  # noqa: E402
                               QApplication, QCheckBox, QComboBox, QLabel, QLineEdit, QScrollBar, QWidget)

from onehand import limitless_link  # noqa: E402
from onehand.app import MainWindow  # noqa: E402
from onehand.platform_sim import SimBackend  # noqa: E402
from onehand.settings import Prefs, load_layouts  # noqa: E402
from onehand.words import t  # noqa: E402

CONTROLS = (QAbstractButton, QComboBox, QAbstractSlider, QAbstractSpinBox, QLineEdit, QAbstractItemView)


# ---- what a screen reader and the Tab key find -------------------------------------------

def said(widget, what=QAccessible.Text.Name):
    """What a screen reader is given for the widget."""
    return QAccessible.queryAccessibleInterface(widget).text(what).strip()


def handles(widget, *events):
    """Whether One-Hand's own class for the widget, not Qt's, handles any of these events."""
    return any(e in vars(c) for c in type(widget).__mro__ if c.__module__.startswith("onehand") for e in events)


def controls(window):
    """Every control a person can use in the window as it is now, One-Hand's own ones too."""
    return [w for w in window.findChildren(QWidget) if w.isVisibleTo(window)
            and (isinstance(w, CONTROLS) or handles(w, "mousePressEvent", "mouseReleaseEvent", "enterEvent"))
            and not isinstance(w, QScrollBar)   # the scroll area scrolls by keyboard itself
            and not isinstance(w.parent(), (QAbstractSpinBox, QComboBox))]   # their own text box


def words(text):
    return " ".join(re.findall(r"[^\W_]+", text.lower()))


def in_words(name):
    """A name in words, not a symbol like "⏻" or "✓"."""
    return bool(re.search(r"[^\W\d_]{2}", name)) and not any(unicodedata.category(c) in ("Sm", "So") for c in name)


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
        if isinstance(w, QComboBox) and not in_words(said(w, QAccessible.Text.Description)):
            # On a Mac, Qt gives a pop-up menu's chosen item as its title and VoiceOver reads its
            # description as its label: without one, it never says what the menu chooses.
            found.append(f"{kind} {name!r}: no description saying what it chooses")
        if not w.focusPolicy() & Qt.FocusPolicy.TabFocus:
            found.append(f"{kind} {name!r}: Tab can't reach it")
    for w in window.findChildren(QLabel):
        if w.isVisibleTo(window) and w.accessibleName() and re.search(r"[^\W\d_]{2}", w.text()):
            # On a Mac, VoiceOver reads a label's name as its words: a fixed name hides them.
            found.append(f"label {w.text()!r}: read as {w.accessibleName()!r}")
    for w in [window] + window.findChildren(QWidget):
        if handles(w, "paintEvent") and (w is window or w.isVisibleTo(window)):
            role = QAccessible.queryAccessibleInterface(w).role()
            if w.isWindow() and not (in_words(w.windowTitle()) and in_words(said(w))):
                found.append(f"{type(w).__name__}: a window drawn by One-Hand with no title or name")
            elif not w.isWindow() and (role in (QAccessible.Role.NoRole, QAccessible.Role.Client,
                                                QAccessible.Role.Border) or not in_words(said(w))):
                found.append(f"{type(w).__name__}: drawn by One-Hand with role {role.name}, name {said(w)!r}")
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
        first = next(w for w in controls(window) if w.isEnabled() and w.focusPolicy() & Qt.FocusPolicy.TabFocus)
        first.setFocus(Qt.FocusReason.TabFocusReason)
    stops = [first]
    for _ in range(100):
        QTest.keyClick(QApplication.focusWidget(), Qt.Key.Key_Tab)
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


@pytest.fixture
def posted(monkeypatch):
    """The accessibility events One-Hand posts, as (widget, kind, value)."""
    events = []
    real = QAccessible.updateAccessibility

    def post(event):
        value = event.value() if event.type() == QAccessible.Event.ValueChanged else None
        events.append((event.object(), event.type(), value))
        real(event)

    monkeypatch.setattr(QAccessible, "updateAccessibility", post)
    return events


def assert_read(label, posted, text):
    """A screen reader reads the label's new words, knows what they are, and is told they changed."""
    assert said(label) == text
    assert in_words(said(label, QAccessible.Text.Description)), f"{text!r} doesn't say what it is"
    assert any(o is label and kind == QAccessible.Event.ValueChanged and v == text for o, kind, v in posted), \
        f"no event when it became {text!r}"


# ---- One-Hand, every window ------------------------------------------------------------

@pytest.fixture(params=["en", "es"])
def make(request, tmp_path, monkeypatch):
    monkeypatch.setattr("onehand.words._computer", request.param)     # every window, in each language
    monkeypatch.setenv("LIMITLESS_SOUND_HOME", str(tmp_path))         # no hub here...
    monkeypatch.setattr(limitless_link, "launch_hub", lambda: False)  # ...and don't open one
    monkeypatch.setattr(Prefs, "save", lambda self: None)              # leave the real settings alone
    QApplication.instance() or QApplication([])
    made = []

    def make(**backend):
        w = MainWindow(SimBackend(front_app="limitless.sim", **backend), Prefs(), load_layouts())
        made.append(w)
        return w

    yield make
    for w in made:
        w.shutdown()
        w.hide()


def waiting_for_permission(make):
    """A Mac without keyboard access yet: One-Hand opens on its permission page."""
    w = make(error="not allowed", permissions={"Accessibility": False, "Input Monitoring": False})
    assert w.pages.currentIndex() == 0
    return w


def test_every_window_names_its_controls(make):
    w = make()
    w.engine.set_enabled(True)
    w.tick()   # the mode is on: the status, the ON badge
    w.show_practice("e", "Record")
    assert problems(w) == []
    assert problems(w.badge) == []

    w = waiting_for_permission(make)
    assert problems(w) == []
    w.permission_page.refresh({"Accessibility": True, "Input Monitoring": True}, True)   # "Reopen One-Hand"
    assert problems(w) == []
    w.show_main()   # "Look around first": the main page, with a banner about keyboard access
    assert not w.banner.isHidden()
    assert problems(w) == []


def test_tab_goes_through_each_window_in_order(make):
    w = make()
    options = [b for b in w.findChildren(QCheckBox) if b.isVisibleTo(w)]
    hands = list(w.hand_buttons.values())
    # Both hands are Tab stops: they look like two buttons, not a pair of radio buttons.
    assert_tab_order(w, [w.pages.widget(1), w.power, *hands, *options, w.app_pick])
    w.hide()

    w = waiting_for_permission(make)
    page = w.permission_page
    steps = [btn for _, _, btn in page.steps.values()]
    later = next(b for b in page.findChildren(QAbstractButton) if b.text() == t("Look around first"))
    assert_tab_order(w, [w.pages.widget(0), *steps, later])
    w.show_main()
    assert_tab_order(w, [w.pages.widget(1), w.banner_button, w.power, *hands, *options, w.app_pick])
    w.hide()


def test_status_text_is_read_and_its_changes_posted(make, posted):
    w = make()
    w.engine.set_enabled(True)
    w.tick()
    assert_read(w.status, posted, t("Try it here: press the {hand} keys below to see what they do.",
                                    hand=t("left-hand")))
    assert_read(w.badge.label, posted, t("ONE-HAND ON  ·  {hand}  ·  {where}", hand=t("Left hand"),
                                         where=t("waiting for your DAW")))
    w.show_practice("e", "Record")
    assert_read(w.practice, posted, w.practice.text())

    w = waiting_for_permission(make)
    page = w.permission_page
    assert_read(page.status, posted, t("Waiting for you to switch these on. This page updates by itself."))
    # The ticks are symbols on screen and words to a screen reader.
    _, tick, _ = page.steps["Accessibility"]
    assert tick.text() == "○" and said(tick) == t("{name} not allowed yet", name=t("Accessibility"))
    page.refresh({"Accessibility": True, "Input Monitoring": False}, False)
    assert tick.text() == "✓"
    assert_read(tick, posted, t("{name} allowed", name=t("Accessibility")))
    w.show_main()
    assert_read(w.banner_text, posted, t("One-Hand can't use the keyboard yet, so your keys won't change."))
