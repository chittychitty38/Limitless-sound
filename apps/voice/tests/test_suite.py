"""Limitless Voice in the Limitless Sound suite (no hub needed: the link is replaced)."""
import unittest

from limitless_voice.engine import Engine
from limitless_voice.grammar import DEFAULT_PACK_DIR, load_packs
from limitless_voice.look import in_use
from limitless_voice.platforms.dryrun import DryRunPlatform
from limitless_voice.settings import Settings
from limitless_voice.suite import INTENT_PHRASES, OWN_ACTIONS, Suite, spoken_forms

PACKS = load_packs([DEFAULT_PACK_DIR], "mac")


class FakeLink:
    def __init__(self):
        self.did_log, self.states, self.invoked, self.said = [], [], [], []

    def did(self, action, intent=None, value=None):
        self.did_log.append((action, intent))

    def state(self, key, value):
        self.states.append((key, value))

    def invoke(self, action, args=None, on_result=None):
        self.invoked.append(action)
        return True

    def say(self, text):
        return False

    def start(self):
        pass


def make(app="Logic Pro"):
    p = DryRunPlatform("mac", app=app)
    e = Engine(p, PACKS, own_names=["Limitless Voice"])
    s = Suite(e)
    s.link = FakeLink()
    return s, e, p


def pressed(p):
    return [x[1] for x in p.log if x[0] == "press"]


SUITE_ACTIONS = [
    {"id": "color.on", "label": "Screen colors on", "tool": "color", "live": True},
    {"id": "onehand.toggle", "label": "One-hand mode on or off", "tool": "onehand", "live": True},
    {"id": "control.layer", "label": "Next layer", "tool": "control", "live": True},
    {"id": "zoom.in", "label": "Zoom in", "tool": "zoom", "live": True},
    {"id": "gaze.play", "label": "Play (Pro Tools link)", "tool": "gaze", "live": True},
    {"id": "color.off", "label": "Screen colors off", "tool": "color", "live": False},
    {"id": "hub.say", "label": "Say", "tool": "hub", "live": True, "args": {"text": "text"}},
]


class TakeMode(unittest.TestCase):
    def test_only_stop_works_during_a_take(self):
        s, e, p = make()
        s.invoke("takeGuard", {}, "link:take-guard")
        for lyric in ("solo track", "mute", "undo", "save the project", "record"):
            r = e.handle(lyric)
            self.assertFalse(r.handled, lyric)
            self.assertEqual(r.message, "take")
        self.assertEqual(pressed(p), [])
        r = e.handle("stop")
        self.assertTrue(r.handled)
        self.assertEqual(pressed(p), ["space"])
        self.assertFalse(e.take)

    def test_take_mode_off_by_words_and_by_link(self):
        s, e, _ = make()
        s.invoke("takeGuard", {}, "x")
        self.assertTrue(e.handle("all commands").handled)
        self.assertFalse(e.take)
        s.invoke("takeGuard", {}, "x")
        s.invoke("takeGuardOff", {}, "x")
        self.assertFalse(e.take)

    def test_sleep_still_works_in_a_take(self):
        s, e, _ = make()
        s.invoke("takeGuard", {}, "x")
        e.handle("go to sleep")
        self.assertFalse(e.awake)

    def test_listening_state_is_reported(self):
        s, e, _ = make()
        s.invoke("takeGuard", {}, "x")
        s.invoke("sleep", {}, "x")
        self.assertEqual(s.link.states, [("listening", "take"), ("listening", "asleep")])


class Reporting(unittest.TestCase):
    def test_spoken_record_reports_the_intent(self):
        s, e, _ = make()
        s.report(e.handle("record"))
        s.report(e.handle("start recording"))
        s.report(e.handle("solo the track"))
        self.assertEqual(s.link.did_log, [("record", "daw.record"), ("record", "daw.record"), ("solo", "daw.solo")])

    def test_stop_and_undo(self):
        s, e, _ = make("Pro Tools")
        s.report(e.handle("stop"))
        s.report(e.handle("undo"))
        self.assertEqual(s.link.did_log, [("stop", "daw.stop"), ("undo", "daw.undo")])

    def test_unrelated_commands_report_nothing(self):
        s, e, _ = make()
        s.report(e.handle("show the mixer"))
        s.report(e.handle("go to bar thirty two"))
        self.assertEqual(s.link.did_log, [("mixer", "daw.mixer")])


class ForOtherApps(unittest.TestCase):
    def test_intents_press_keys_even_when_asleep_or_in_a_take(self):
        s, e, p = make()
        e.awake = False
        ok, msg = s.invoke("record", {}, "gaze")
        self.assertTrue(ok, msg)
        self.assertEqual(pressed(p), ["r"])
        self.assertFalse(e.awake)                     # state left as it was
        e.awake, e.take = True, True
        s.invoke("undo", {}, "gaze")
        self.assertTrue(e.take)
        self.assertEqual(s.link.did_log, [("record", "daw.record"), ("undo", "daw.undo")])

    def test_do_runs_any_phrase(self):
        s, e, p = make("Pro Tools")
        ok, _ = s.invoke("do", {"phrase": "go to bar thirty two"}, "streamdeck")
        self.assertTrue(ok)
        self.assertFalse(s.invoke("do", {"phrase": "make me a sandwich"}, "x")[0])

    def test_a_refusal_always_says_why(self):
        # Limitless Access Standard C4: a refusal says why, in words a person can hear.
        s, e, p = make("Finder")
        for args in ({}, {"phrase": ""}, {"phrase": "   "}):
            ok, msg = s.invoke("do", args, "x")
            self.assertFalse(ok)
            self.assertIn("Which command", msg)
        ok, msg = s.invoke("play", {}, "gaze")         # no DAW in front
        self.assertFalse(ok)
        self.assertEqual(msg, "Play works when Logic Pro or Pro Tools is in front.")
        self.assertEqual(pressed(p), [])

    def test_commands_that_need_a_yes_are_refused(self):
        s, e, p = make()
        ok, _ = s.invoke("do", {"phrase": "quit the app"}, "streamdeck")
        self.assertFalse(ok)
        self.assertIsNone(e.pending)                  # a later "yes" from the user can't quit
        e.handle("yes")
        self.assertEqual(pressed(p), [])

    def test_every_intent_phrase_is_a_real_command(self):
        for app in ("Logic Pro", "Pro Tools"):
            s, e, _ = make(app)
            for intent, phrase in INTENT_PHRASES.items():
                if (app, intent) in {("Pro Tools", "daw.zoomFit")}:
                    continue
                r = e.handle(phrase)
                self.assertTrue(r.handled, f"{app}: {phrase}")
        self.assertIn("takeGuard", {a["id"] for a in OWN_ACTIONS})

    def test_wake_sleep_toggle(self):
        s, e, _ = make()
        changed = []
        s.on_change = lambda: changed.append(1)
        s.invoke("sleep", {}, "control")
        self.assertFalse(e.awake)
        s.invoke("toggle", {}, "control")
        self.assertTrue(e.awake)
        self.assertEqual(len(changed), 2)
        self.assertFalse(s.invoke("dance", {}, "x")[0])


class OtherAppsByVoice(unittest.TestCase):
    def test_say_another_apps_action(self):
        s, e, p = make()
        phrases = []
        s.on_phrases = lambda: phrases.append(1)
        s.on_actions(SUITE_ACTIONS)
        self.assertEqual(phrases, [1])
        self.assertIn("screen colors on", s.phrases())
        self.assertIn("one hand mode", s.phrases())
        r = e.handle("screen colors on")
        self.assertTrue(r.handled)
        self.assertEqual(s.link.invoked, ["color.on"])
        e.handle("one hand mode")
        e.handle("next layer")
        self.assertEqual(s.link.invoked, ["color.on", "onehand.toggle", "control.layer"])

    def test_own_commands_win(self):
        s, e, p = make()
        s.on_actions(SUITE_ACTIONS)
        e.handle("zoom in")
        self.assertEqual(s.link.invoked, [])
        self.assertEqual(len(pressed(p)), 1)

    def test_closed_apps_and_arg_actions_are_left_out(self):
        s, _, _ = make()
        s.on_actions(SUITE_ACTIONS)
        self.assertNotIn("screen colors off", s.phrases())
        self.assertNotIn("say", s.phrases())

    def test_spoken_forms_keep_numbers(self):
        self.assertEqual(spoken_forms({"label": "Layer 2"}), {"layer two"})
        self.assertEqual(spoken_forms({"label": "Zoom 150%"}), {"zoom one hundred fifty"})

    def test_spoken_forms(self):
        self.assertEqual(spoken_forms({"label": "Play (Pro Tools link)"}), {"play"})
        self.assertIn("one hand mode", spoken_forms({"label": "One-hand mode on or off"}))


HUB_PREFS = {"speak": True, "oneVoice": True, "textScale": 1.0, "highContrast": False,
             "reduceMotion": False, "dwellMs": 800, "scanMs": 1200}


class SharedSettings(unittest.TestCase):
    def test_the_more_accessible_of_the_two_wins(self):
        own = Settings(text_scale=1.3, high_contrast=False)
        self.assertEqual(in_use(own, {**HUB_PREFS, "textScale": 1.5, "highContrast": True, "reduceMotion": True}),
                         {"textScale": 1.5, "highContrast": True, "reduceMotion": True})
        self.assertEqual(in_use(own, {**HUB_PREFS, "textScale": 1.2}),
                         {"textScale": 1.3, "highContrast": False, "reduceMotion": False})
        own.high_contrast = True
        self.assertTrue(in_use(own, HUB_PREFS)["highContrast"])

    def test_without_the_hub_only_voices_own_settings_count(self):
        own = Settings(text_scale=0.8, high_contrast=True)
        self.assertEqual(in_use(own, {}), {"textScale": 0.8, "highContrast": True, "reduceMotion": False})

    def test_only_settings_voice_honors_are_reported(self):
        look = in_use(Settings(), HUB_PREFS)
        self.assertEqual(set(look), {"textScale", "highContrast", "reduceMotion"})   # no dwell, scan or speak

    def test_hub_prefs_restyle_and_are_reported(self):
        s, _, _ = make()
        seen = []
        s.on_look = lambda: seen.append(dict(s.prefs))
        s.on_prefs({**HUB_PREFS, "textScale": 1.5})
        self.assertEqual(seen[-1]["textScale"], 1.5)
        s.report_look({"textScale": 1.5, "highContrast": False, "reduceMotion": False})
        self.assertEqual(s.link.states, [("prefs.applied", {"textScale": 1.5, "highContrast": False,
                                                            "reduceMotion": False})])


if __name__ == "__main__":
    unittest.main()
