"""Screen readers and the keyboard alone, in every window Voice shows: the main window, the
command list, settings, every page of the setup guide, and the floating display.

Blind and low-vision musicians run their DAW with VoiceOver. What it reads is what Qt's
accessibility interface gives it, so that's what these tests read too (no mic, no real OS)."""
import os
import re
import unicodedata
import unittest
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtGui import QAccessible  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import (QAbstractButton, QAbstractItemView, QAbstractSlider, QAbstractSpinBox,  # noqa: E402
                               QApplication, QComboBox, QDialogButtonBox, QLabel, QLineEdit, QPushButton,
                               QScrollBar, QWidget)

from test_setup import make  # noqa: E402  (the main window with a dry-run computer, no mic)
from limitless_voice.app import CommandsDialog, SettingsDialog  # noqa: E402
from limitless_voice.onboarding import MicCheckPage, PreferencesPage  # noqa: E402

app = QApplication.instance() or QApplication([])
CONTROLS = (QAbstractButton, QComboBox, QAbstractSlider, QAbstractSpinBox, QLineEdit, QAbstractItemView)


# ---- what a screen reader and the Tab key find -------------------------------------------

def said(widget, what=QAccessible.Name):
    """What a screen reader is given for the widget."""
    return QAccessible.queryAccessibleInterface(widget).text(what).strip()


def handles(widget, *events):
    """Whether Voice's own class for the widget, not Qt's, handles any of these events."""
    return any(e in vars(c) for c in type(widget).__mro__
               if c.__module__.startswith("limitless_voice") for e in events)


def controls(window):
    """Every control a person can use in the window as it is now, Voice's own ones too."""
    return [w for w in window.findChildren(QWidget) if w.isVisibleTo(window)
            and (isinstance(w, CONTROLS) or handles(w, "mousePressEvent", "mouseReleaseEvent", "enterEvent"))
            and not isinstance(w, QScrollBar)   # the list or scroll area scrolls by keyboard itself
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
        if not w.focusPolicy() & Qt.TabFocus:
            found.append(f"{kind} {name!r}: Tab can't reach it")
    for w in window.findChildren(QLabel):
        if w.isVisibleTo(window) and w.accessibleName() and re.search(r"[^\W\d_]{2}", w.text()):
            # On a Mac, VoiceOver reads a label's name as its words: a fixed name hides them.
            found.append(f"label {w.text()!r}: read as {w.accessibleName()!r}")
    for w in [window] + window.findChildren(QWidget):
        if handles(w, "paintEvent") and (w is window or w.isVisibleTo(window)):
            role = QAccessible.queryAccessibleInterface(w).role()
            if w.isWindow() and not (in_words(w.windowTitle()) and in_words(said(w))):
                found.append(f"{type(w).__name__}: a window drawn by Voice with no title or name")
            elif not w.isWindow() and (role in (QAccessible.NoRole, QAccessible.Client, QAccessible.Border)
                                       or not in_words(said(w))):
                found.append(f"{type(w).__name__}: drawn by Voice with role {role.name}, name {said(w)!r}")
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


def button(window, text):
    return next(b for b in window.findChildren(QPushButton) if b.text() == text)


class Base(unittest.TestCase):
    mic = "granted"   # and keys not allowed yet: the main window shows a box about that

    def setUp(self):
        self.w, self.platform, self.settings = make(mic=self.mic, control=False)
        self.w._check_permissions()
        self.posted = []
        real = QAccessible.updateAccessibility

        def post(event):
            value = event.value() if event.type() == QAccessible.ValueChanged else None
            self.posted.append((event.object(), event.type(), value))
            real(event)

        patch = mock.patch.object(QAccessible, "updateAccessibility", post)
        patch.start()
        self.addCleanup(patch.stop)

    def tearDown(self):
        if self.w.wizard is not None:
            self.w.wizard.reject()
        self.w.shutdown()
        self.w.hide()
        self.w.deleteLater()

    def assert_tab_order(self, window, expected):
        stops = tab_stops(window)
        self.assertTrue(all(in_words(said(w)) for w in stops), [said(w) for w in stops])   # each is named
        start = stops.index(expected[0]) if expected[0] in stops else 0
        stops = stops[start:] + stops[:start]
        self.assertEqual([said(w) for w in stops], [said(w) for w in expected])

    def assert_read(self, label, text):
        """A screen reader reads the label's new words, knows what they are, and is told they changed."""
        self.assertEqual(said(label), text)
        self.assertTrue(in_words(said(label, QAccessible.Description)), f"{text!r} doesn't say what it is")
        self.assertTrue(any(o is label and kind == QAccessible.ValueChanged and v == text
                            for o, kind, v in self.posted), f"no event when it became {text!r}")


class MainWindowAndDialogs(Base):
    def test_every_window_names_its_controls(self):
        w = self.w
        w.on_heard("solo track", "solo track")
        w.on_mic_error("Couldn't open the microphone")
        self.assertEqual(problems(w), [])
        self.assertEqual(problems(w.hud), [])
        for dialog in (CommandsDialog(w, w.engine), SettingsDialog(w, w.settings)):
            self.assertEqual(problems(dialog), [], dialog.windowTitle())
            dialog.reject()

    def test_tab_goes_through_each_window_in_order(self):
        w = self.w
        self.assert_tab_order(w, [w.listen_btn, w.permission_open, w.permission_check, w.mic_combo,
                                  button(w, "Refresh"), w.history, button(w, "What can I say?"),
                                  button(w, "Settings"), button(w, "My commands folder")])
        dialog = CommandsDialog(w, w.engine)
        self.assert_tab_order(dialog, [dialog.search, dialog.list, button(dialog, "Close")])
        dialog.reject()
        dialog = SettingsDialog(w, w.settings)
        dialog.show()
        save_cancel = sorted(dialog.findChild(QDialogButtonBox).buttons(), key=lambda b: b.x())   # as shown here
        self.assert_tab_order(dialog, [dialog.speak, dialog.rate, dialog.start_listening, dialog.vocab,
                                       dialog.on_top, dialog.scale, dialog.contrast, dialog.hotkey,
                                       dialog.language, dialog.model, *save_cancel])
        dialog.reject()

    def test_status_text_is_read_and_its_changes_posted(self):
        w = self.w
        w.on_heard("solo track", "solo track")
        self.assert_read(w.heard_label, "Heard: “solo track”")
        self.assert_read(w.did_label, w.did_label.text())
        w.hud.show_message("solo track", "Solo track")   # the display, when the window is behind
        self.assert_read(w.hud.heard, "“solo track”")
        self.assert_read(w.hud.did, "✓ Solo track")
        w.engine.awake = False
        w._update_state()
        self.assert_read(w.hud.state_label, "Asleep")
        w._track_focus()
        self.assert_read(w.target_label, "Sending commands to: Pro Tools")
        w.on_mic_error("Couldn't open the microphone")
        self.assert_read(w.mic_error, "Couldn't open the microphone")
        self.assertEqual(said(w.permission_text, QAccessible.Description), "Permission needed")
        self.assertIn("control the computer", said(w.permission_text))

    def test_the_floating_display_is_named(self):
        hud = self.w.hud
        self.assertEqual(hud.windowTitle(), "Limitless Voice")
        self.assertTrue(in_words(said(hud)))


class SetupGuide(Base):
    mic = "ask"   # first launch: nothing allowed yet

    def setUp(self):
        super().setUp()
        self.w.show_setup()
        self.wiz = self.w.wizard

    def go(self, i):
        self.wiz._show(i)
        return self.wiz.page

    def test_every_page_names_its_controls(self):
        for i in range(len(self.wiz.pages)):
            self.go(i)
            self.assertEqual(problems(self.wiz), [], type(self.wiz.page).__name__)

    def test_tab_goes_through_each_page_in_order(self):
        wiz = self.wiz
        back, nxt = wiz.back_btn, wiz.next_btn
        self.assert_tab_order(wiz, [nxt])   # welcome: Back is off on the first page
        page = self.go(1)
        self.assert_tab_order(wiz, [page.button, back])   # Continue waits for the microphone
        page = self.go(2)
        self.assert_tab_order(wiz, [page.button, page.skip, back])
        page = self.go(3)
        self.assertIsInstance(page, MicCheckPage)
        self.assert_tab_order(wiz, [page.mics, back, nxt])
        page = self.go(4)
        self.assertIsInstance(page, PreferencesPage)
        self.assert_tab_order(wiz, [page.speak, page.hud, page.big, page.contrast, page.start, back, nxt])
        self.go(5)
        self.assert_tab_order(wiz, [back, nxt])

    def test_status_text_is_read_and_its_changes_posted(self):
        wiz = self.wiz
        page = self.go(1)
        self.assert_read(wiz.step_label, "Step 2 of 6")
        page.button.click()   # the dry run allows the microphone at once
        wiz._refresh()
        self.assert_read(page.status, "✓ Microphone allowed")
        page = self.go(2)
        self.assert_read(page.status, "Waiting for the switch to be turned on…")
        page = self.go(3)
        self.w.on_heard("what can i say", "what can i say")
        self.assert_read(page.result, "✓ Heard “what can i say”. Your microphone works.")


if __name__ == "__main__":
    unittest.main()
