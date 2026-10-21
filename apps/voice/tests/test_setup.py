"""First launch: the setup guide, permissions, and the floating display (no mic, no real OS)."""
import os
import tempfile
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
_home = tempfile.mkdtemp()
os.environ["XDG_CONFIG_HOME"] = os.path.join(_home, "config")
os.environ["XDG_DATA_HOME"] = os.path.join(_home, "data")

from PySide6.QtWidgets import QApplication  # noqa: E402

from limitless_voice.app import MainWindow  # noqa: E402
from limitless_voice.onboarding import (  # noqa: E402
    ControlPermissionPage, MicCheckPage, MicPermissionPage, PreferencesPage, ReadyPage, WelcomePage)
from limitless_voice.platforms.dryrun import DryRunPlatform  # noqa: E402
from limitless_voice.settings import Settings  # noqa: E402

app = QApplication.instance() or QApplication([])


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


def make(mic="ask", control=False):
    p = DryRunPlatform("mac", app="Pro Tools")
    p.mic_state, p.control_state = mic, control
    s = Settings(speak_feedback=False)
    w = MainWindow(s, p, model_path="unused")
    w.listener.stop()
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


if __name__ == "__main__":
    unittest.main()
