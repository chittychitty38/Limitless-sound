"""First launch: the setup guide, permissions, the floating display, and the suite's
shared text size, contrast and motion settings (no mic, no real OS, no hub)."""
import os
import tempfile
import unittest
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
_home = tempfile.mkdtemp()
os.environ["XDG_CONFIG_HOME"] = os.path.join(_home, "config")
os.environ["XDG_DATA_HOME"] = os.path.join(_home, "data")

from PySide6.QtCore import QAbstractAnimation, Qt  # noqa: E402
from PySide6.QtGui import QFont  # noqa: E402
from PySide6.QtWidgets import QApplication, QLabel  # noqa: E402

from limitless_voice import app as app_module  # noqa: E402
from limitless_voice.app import HIGH_CONTRAST, MainWindow  # noqa: E402
from limitless_voice.look import TEXT_SIZE  # noqa: E402
from limitless_voice.onboarding import (  # noqa: E402
    ControlPermissionPage, MicCheckPage, MicPermissionPage, PreferencesPage, ReadyPage, WelcomePage)
from limitless_voice.platforms.dryrun import DryRunPlatform  # noqa: E402
from limitless_voice.settings import Settings, data_dir  # noqa: E402

app = QApplication.instance() or QApplication([])
SPANISH_MODEL = data_dir() / "models" / "vosk-model-small-es-0.42"


class FakeListener:
    def __init__(self):
        self.started = 0
        self.paused = False
        self.device = None

    def start(self):
        self.started += 1

    def stop(self):
        pass

    def set_device(self, device):
        self.device = device

    def set_phrases(self, phrases):
        pass


class FakeSpeaker:
    def __init__(self):
        self.said = []

    def say(self, text):
        self.said.append(text)

    def set_enabled(self, *a):
        pass

    def __getattr__(self, name):
        return lambda *a, **k: None


def make(mic="ask", control=False, language=""):
    """The main window with a dry-run Mac, Pro Tools in front, no mic. language="es": chosen in
    Settings, with its speech model here, so it listens and shows Spanish (remove SPANISH_MODEL
    after)."""
    p = DryRunPlatform("mac", app="Pro Tools")
    p.mic_state, p.control_state = mic, control
    s = Settings(speak_feedback=False, language=language)
    if language == "es":
        (SPANISH_MODEL / "conf").mkdir(parents=True, exist_ok=True)   # as if downloaded; never loaded
    with mock.patch.object(app_module, "Listener", lambda *a, **k: FakeListener()):   # no mic thread
        w = MainWindow(s, p, model_path="unused")
    w.listener = FakeListener()
    w._listening_started = False
    w.speaker = FakeSpeaker()
    w.permission_timer.stop()
    w.focus_timer.stop()
    w._last_problem = None
    return w, p, s


def pressed(p):
    return [x[1] for x in p.log if x[0] in ("press", "type")]


class Permissions(unittest.TestCase):
    def tearDown(self):
        self.w.shutdown()
        self.w.deleteLater()

    def test_mic_is_not_opened_before_permission(self):
        self.w, p, _ = make(mic="ask")
        self.w._check_permissions()
        self.assertEqual(self.w.listener.started, 0)
        p.mic_state = "granted"
        self.w._check_permissions()
        self.w._check_permissions()
        self.assertEqual(self.w.listener.started, 1)

    def test_missing_permission_shows_a_banner_once(self):
        self.w, p, _ = make(mic="granted", control=False)
        self.w._check_permissions()
        self.assertFalse(self.w.permission_box.isHidden())
        self.w._check_permissions()
        self.assertEqual(len([t for t in self.w.speaker.said if "control the computer" in t]), 1)
        p.control_state = True
        self.w._check_permissions()
        self.assertTrue(self.w.permission_box.isHidden())


class Wizard(unittest.TestCase):
    def tearDown(self):
        if self.w.wizard is not None:
            self.w.wizard.reject()
        self.w.shutdown()
        self.w.deleteLater()

    def test_full_setup(self):
        self.w, p, s = make(mic="ask", control=False)
        self.w.show_setup()
        wiz = self.w.wizard
        self.assertIsInstance(wiz.page, WelcomePage)
        wiz.forward()
        self.assertIsInstance(wiz.page, MicPermissionPage)
        self.assertFalse(wiz.next_btn.isEnabled())
        wiz.page.button.click()                    # dry run grants straight away
        wiz._refresh()
        self.assertTrue(wiz.next_btn.isEnabled())
        self.assertEqual(self.w.listener.started, 1)
        wiz.forward()
        self.assertIsInstance(wiz.page, ControlPermissionPage)
        self.assertFalse(wiz.next_btn.isEnabled())
        wiz.page.button.click()
        self.assertIn(("open settings", "settings:accessibility"), [x[:2] for x in p.log])
        p.control_state = True
        wiz._refresh()
        self.assertTrue(wiz.next_btn.isEnabled())
        wiz.forward()
        self.assertIsInstance(wiz.page, MicCheckPage)
        self.w.on_heard("what can i say", "what can i say")
        self.assertIn("microphone works", wiz.page.result.text())
        self.assertEqual(pressed(p), [])           # setup speech never reaches the DAW
        wiz.forward()
        self.assertIsInstance(wiz.page, PreferencesPage)
        wiz.page.big.setChecked(True)
        wiz.page.start.setChecked(True)
        wiz.forward()
        self.assertIsInstance(wiz.page, ReadyPage)
        self.assertEqual(s.text_scale, 1.3)
        self.assertIn(("login item", True), [x[:2] for x in p.log])
        wiz.forward()
        self.assertIsNone(self.w.wizard)
        self.assertTrue(Settings.load().first_run_done)

        self.w.on_heard("go to bar thirty two", "go to bar thirty two")
        self.assertEqual(pressed(p)[-3:], ["numpad*", "32", "return"])

    def test_done_permission_pages_are_skipped(self):
        self.w, p, _ = make(mic="granted", control=True)
        self.w.show_setup()
        wiz = self.w.wizard
        wiz.forward()
        self.assertIsInstance(wiz.page, MicCheckPage)
        wiz.back()
        self.assertIsInstance(wiz.page, WelcomePage)

    def test_skip_accessibility(self):
        self.w, p, _ = make(mic="granted", control=False)
        self.w.show_setup()
        wiz = self.w.wizard
        wiz.forward()
        self.assertIsInstance(wiz.page, ControlPermissionPage)
        wiz.page.skip.click()
        self.assertIsInstance(wiz.page, MicCheckPage)


    def test_a_page_too_big_for_the_window_scrolls_instead_of_squeezing(self):
        """At double text every wrapped line on every setup page keeps its room: a page taller than
        the window scrolls, and the window grows as wide as its widest page. Before, the window
        stayed 620 x 520 and squeezed them."""
        old = QFont(app.font())
        big = QFont(old)
        big.setPointSizeF(old.pointSizeF() * 2)
        app.setFont(big)
        self.addCleanup(app.setFont, old)
        self.w, p, _ = make(mic="ask", control=False)
        self.w.show_setup()
        wiz = self.w.wizard
        wiz.show()
        for i, page in enumerate(wiz.pages):
            wiz._show(i)
            app.processEvents()
            self.assertLessEqual(page.width(), wiz.stack.currentWidget().viewport().width(), i)   # none at the side
            for lbl in page.findChildren(QLabel):
                if lbl.isVisible() and lbl.wordWrap():
                    self.assertGreaterEqual(lbl.height() + 1, lbl.heightForWidth(lbl.width()), (i, lbl.text()[:40]))
        self.assertTrue(wiz.stack.currentWidget().verticalScrollBar().isVisible())   # the eight examples


    def test_the_main_window_scrolls_instead_of_squeezing_a_permission_still_needed(self):
        """At double text the main window keeps the whole "Allow Limitless Voice to control the
        computer" banner, scrolling if it must, and grows as wide as its words need, as before."""
        old = QFont(app.font())
        big = QFont(old)
        big.setPointSizeF(old.pointSizeF() * 2)
        app.setFont(big)
        self.addCleanup(app.setFont, old)
        self.w, p, _ = make(mic="granted", control=False)
        self.w._check_permissions()
        self.w.show()
        app.processEvents()
        banner = self.w.permission_text
        self.assertGreaterEqual(banner.height() + 1, banner.heightForWidth(banner.width()))
        self.assertGreaterEqual(self.w.centralWidget().viewport().width() + 1, self.w.listen_btn.sizeHint().width())


class Hud(unittest.TestCase):
    def test_hud_shows_when_the_window_is_in_the_background(self):
        w, p, _ = make(mic="granted", control=True)
        try:
            w.on_heard("solo track", "solo track")
            self.assertTrue(w.hud.isVisible())
            self.assertIn("solo track", w.hud.heard.text())
            self.assertTrue(w.hud.did.text().startswith("✓"))
            w.settings.show_hud = False
            w.hud.hide()
            w.on_heard("mute track", "mute track")
            self.assertFalse(w.hud.isVisible())
        finally:
            w.shutdown()
            w.deleteLater()


EN = {"language": "en"}   # what Voice listens in, reported with the look (prefs.applied)
HUB_PREFS = {"speak": True, "oneVoice": True, "textScale": 1.0, "highContrast": False,
             "reduceMotion": False, "dwellMs": 800, "scanMs": 1200}


class SharedSettings(unittest.TestCase):
    """The hub's welcome and prefs messages go through the real link; only the socket is left out."""

    def setUp(self):
        self.font, self.effects = QFont(app.font()), QApplication.isEffectEnabled(Qt.UI_General)
        QApplication.setEffectEnabled(Qt.UI_General, True)   # like a desktop with menu animations on
        self.w, _, self.s = make(mic="granted", control=True)
        self.base = app.font().pointSizeF()
        self.sent = []
        link = self.w.suite.link
        link._send = lambda msg: link.connected and (self.sent.append(msg) or True)

    def tearDown(self):
        if self.w.wizard is not None:
            self.w.wizard.reject()
        self.w.shutdown()
        self.w.deleteLater()
        app.setStyleSheet("")
        app.setFont(self.font)
        QApplication.setEffectEnabled(Qt.UI_General, self.effects)

    def hub(self, op, **prefs):
        self.w.suite.link._handle({"op": op, "prefs": {**HUB_PREFS, **prefs}})

    def applied(self):
        return [m["value"] for m in self.sent if m.get("op") == "state" and m["key"] == "prefs.applied"]

    def test_welcome_applies_them_to_the_window_and_the_card(self):
        w = self.w
        self.hub("welcome", textScale=1.5, highContrast=True, reduceMotion=True)
        self.assertAlmostEqual(app.font().pointSizeF(), self.base * 1.5)
        self.assertAlmostEqual(w.did_label.font().pointSizeF(), self.base * 1.5)
        self.assertAlmostEqual(w.listen_btn.font().pointSizeF(), self.base * 1.5 * 1.6)
        self.assertTrue(w.listen_btn.font().bold())
        self.assertAlmostEqual(w.hud.heard.font().pointSizeF(), self.base * 1.5 * 1.5)
        self.assertAlmostEqual(w.hud.state_label.font().pointSizeF(), self.base * 1.5)
        self.assertEqual(w.hud.width(), 690)
        self.assertEqual(app.styleSheet(), HIGH_CONTRAST)
        w.hud.show_message("make me a sandwich", "Didn't catch a command", ok=False)
        self.assertTrue(w.hud.high_contrast)
        self.assertIn("#ffeb3b", w.hud.did.styleSheet())
        self.assertFalse(QApplication.isEffectEnabled(Qt.UI_General))
        self.assertEqual(self.applied(), [{"textScale": 1.5, "highContrast": True, "reduceMotion": True, **EN}])

    def test_changes_apply_live_even_to_an_open_setup_guide(self):
        w = self.w
        self.hub("welcome")
        w.show_setup()
        title = next(lbl for lbl in w.wizard.pages[0].findChildren(QLabel) if lbl.property(TEXT_SIZE) == 1.8)
        width = w.wizard.width()
        self.assertAlmostEqual(title.font().pointSizeF(), self.base * 1.8)
        self.hub("prefs", textScale=2.0)
        self.assertAlmostEqual(title.font().pointSizeF(), self.base * 2.0 * 1.8)
        self.assertGreater(w.wizard.width(), width)          # it grew to make room
        self.hub("prefs", highContrast=True)
        self.assertAlmostEqual(title.font().pointSizeF(), self.base * 1.8)
        self.assertEqual(app.styleSheet(), HIGH_CONTRAST)
        self.assertEqual(self.applied(), [{"textScale": 1.0, "highContrast": False, "reduceMotion": False, **EN},
                                          {"textScale": 2.0, "highContrast": False, "reduceMotion": False, **EN},
                                          {"textScale": 1.0, "highContrast": True, "reduceMotion": False, **EN}])

    def test_reduced_motion_means_no_fading(self):
        hud = self.w.hud
        self.hub("welcome")
        hud.show_message("solo track", "Solo track")
        hud.fade_out()
        self.assertEqual(hud.fade.state(), QAbstractAnimation.Running)    # fades, as it always has
        self.hub("prefs", reduceMotion=True)
        self.assertFalse(hud.isVisible())                                 # the fade under way ends at once
        hud.show_message("mute track", "Mute track")
        self.assertTrue(hud.isVisible())
        hud.fade_out()                                                    # when its time is up
        self.assertFalse(hud.isVisible())
        self.assertNotEqual(hud.fade.state(), QAbstractAnimation.Running)
        self.assertFalse(QApplication.isEffectEnabled(Qt.UI_General))
        self.hub("prefs")
        self.assertTrue(QApplication.isEffectEnabled(Qt.UI_General))

    def test_voices_own_settings_combine_with_the_suites(self):
        self.s.text_scale, self.s.high_contrast = 1.3, True
        self.w.apply_settings()
        self.assertEqual(self.sent, [])                      # nothing to tell without the hub
        self.hub("welcome", textScale=1.2)
        self.assertAlmostEqual(app.font().pointSizeF(), self.base * 1.3)     # Voice's larger text wins
        self.assertEqual(app.styleSheet(), HIGH_CONTRAST)                    # on if either is on
        self.hub("prefs", textScale=1.75)
        self.assertAlmostEqual(app.font().pointSizeF(), self.base * 1.75)
        self.s.high_contrast = False
        self.w.apply_settings()                              # Voice's own setting changed: told again
        self.assertEqual(app.styleSheet(), "")
        self.assertEqual(self.applied(), [{"textScale": 1.3, "highContrast": True, "reduceMotion": False, **EN},
                                          {"textScale": 1.75, "highContrast": True, "reduceMotion": False, **EN},
                                          {"textScale": 1.75, "highContrast": False, "reduceMotion": False, **EN}])

    def test_without_the_hub_nothing_changes(self):
        w = self.w
        self.assertEqual(w.suite.prefs, {})
        self.assertEqual(app.styleSheet(), "")
        self.assertAlmostEqual(w.listen_btn.font().pointSizeF(), self.base * 1.6)
        self.assertTrue(QApplication.isEffectEnabled(Qt.UI_General))
        w.hud.show_message("solo track", "Solo track")
        w.hud.fade_out()
        self.assertEqual(w.hud.fade.state(), QAbstractAnimation.Running)
        self.assertEqual(self.sent, [])


if __name__ == "__main__":
    unittest.main()
