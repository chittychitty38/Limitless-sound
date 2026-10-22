import unittest

from limitless_voice.engine import Engine, normalize
from limitless_voice.grammar import DEFAULT_PACK_DIR, load_packs, vocabulary
from limitless_voice.keys import parse_chord, for_platform, spoken_to_chord
from limitless_voice.numbers import normalize_numbers
from limitless_voice.platforms.base import AppRef
from limitless_voice.platforms.dryrun import DryRunPlatform

PACKS = {os: load_packs([DEFAULT_PACK_DIR], os) for os in ("mac", "windows")}


def engine(app=None, os_name="mac", **kw):
    p = DryRunPlatform(os_name, app=app)
    return Engine(p, PACKS[os_name], own_names=["Limitless Voice"], **kw), p


def pressed(p):
    return [e[1] for e in p.log if e[0] == "press"]


class Numbers(unittest.TestCase):
    def test_runs(self):
        cases = {
            "go to bar thirty two": "go to bar 32",
            "tempo one twenty": "tempo 120",
            "tempo one two eight": "tempo 128",
            "bar one hundred and five": "bar 105",
            "nudge right four times": "nudge right 4 times",
            "solo track for": "solo track 4",
            "rock and roll": "rock and roll",
            "save it for later": "save it for later",
            "go two bar thirty two": "go to bar 32",   # recognizer's to/two mixup
            "go two sleep": "go to sleep",
            "nudge right two times": "nudge right 2 times",
        }
        for spoken, want in cases.items():
            self.assertEqual(normalize_numbers(spoken), want, spoken)


class Keys(unittest.TestCase):
    def test_parse(self):
        self.assertEqual(parse_chord("cmd+shift+n"), (["cmd", "shift"], "n"))
        self.assertEqual(parse_chord("cmd++"), (["cmd"], "+"))
        self.assertEqual(parse_chord("numpad+"), ([], "numpad+"))
        self.assertEqual(parse_chord("opt+shift+3"), (["opt", "shift"], "3"))

    def test_windows_translation(self):
        self.assertEqual(for_platform(["cmd", "shift"], "windows"), ["ctrl", "shift"])
        self.assertEqual(for_platform(["opt"], "windows"), ["alt"])
        self.assertEqual(for_platform(["ctrl"], "windows"), ["win"])        # Pro Tools: Control -> Start
        self.assertEqual(for_platform(["ctrl"], "windows", literal=True), ["ctrl"])
        self.assertEqual(for_platform(["cmd", "opt"], "mac"), ["cmd", "opt"])

    def test_every_pack_chord_parses(self):
        for os_name, packs in PACKS.items():
            for pack in packs:
                for c in pack.commands:
                    for s in c.action.get("steps", [c.action]):
                        keys = s.get("keys")
                        for chord in (keys if isinstance(keys, list) else [keys] if keys else []):
                            if "{" not in chord:
                                parse_chord(chord)

    def test_spoken(self):
        self.assertEqual(spoken_to_chord("command shift november"), "cmd+shift+n")
        self.assertEqual(spoken_to_chord("option command b"), "opt+cmd+b")
        self.assertEqual(spoken_to_chord("command period"), "cmd+.")


class Packs(unittest.TestCase):
    def test_logic_is_mac_only(self):
        self.assertIn("Logic Pro", [p.name for p in PACKS["mac"]])
        self.assertNotIn("Logic Pro", [p.name for p in PACKS["windows"]])

    def test_vocabulary(self):
        words = vocabulary(PACKS["mac"])
        for w in ("solo", "mixer", "bar", "quantize", "the"):
            self.assertIn(w, words)
        self.assertFalse(any("{" in w or "[" in w for w in words))


class Matching(unittest.TestCase):
    def test_logic_play_and_record(self):
        e, p = engine("Logic Pro")
        self.assertTrue(e.handle("play").handled)
        self.assertTrue(e.handle("Record.").handled)
        self.assertEqual(pressed(p), ["space", "r"])

    def test_pro_tools_mac_vs_windows(self):
        e, p = engine("Pro Tools")
        e.handle("record")
        e.handle("bounce")
        e.handle("midi editor")
        self.assertEqual(pressed(p), ["cmd+space", "opt+cmd+b", "ctrl+="])
        e, p = engine("ProTools", os_name="windows")   # Windows reports the exe name
        e.handle("record")
        e.handle("bounce")
        e.handle("midi editor")
        self.assertEqual(pressed(p), ["ctrl+space", "alt+ctrl+b", "win+="])

    def test_global_windows_overrides(self):
        e, p = engine("Notepad", os_name="windows")
        e.handle("redo")
        e.handle("copy")
        e.handle("show desktop")
        self.assertEqual(pressed(p), ["ctrl+y", "ctrl+c", "win+d"])

    def test_go_to_bar(self):
        e, p = engine("Pro Tools")
        r = e.handle("go to bar sixty four")
        self.assertEqual(r.params, {"bar": 64})
        self.assertIn(("type", "64"), p.log)

    def test_two_transcripts(self):
        # command-vocabulary transcript is garbled, open one is right: use the open one
        e, p = engine("Logic Pro")
        r = e.handle("[unk] mixer the", "show the mixer")
        self.assertTrue(r.handled)
        self.assertEqual(pressed(p), ["x"])

    def test_optional_words_and_filler(self):
        e, _ = engine("Logic Pro")
        self.assertTrue(e.handle("please show the mixer").handled)
        self.assertTrue(e.handle("um show mixer").handled)

    def test_fuzzy(self):
        e, _ = engine("Logic Pro")
        r = e.handle("piano rolls")
        self.assertTrue(r.handled)
        self.assertEqual(r.command.phrases[0], "piano roll")

    def test_no_fuzzy_record(self):
        # a sung lyric like "recorded" must never start a take
        e, p = engine("Logic Pro")
        self.assertFalse(e.handle("recorded").handled)
        self.assertEqual(p.log, [])

    def test_unknown(self):
        e, p = engine("Logic Pro")
        self.assertFalse(e.handle("make me a sandwich").handled)
        self.assertEqual(p.log, [])

    def test_global_in_other_app(self):
        e, _ = engine("Safari")
        self.assertTrue(e.handle("copy that").handled)
        self.assertFalse(e.handle("piano roll").handled)

    def test_press_any_chord_is_literal(self):
        e, p = engine("Notepad", os_name="windows")
        e.handle("press control shift november")
        self.assertEqual(pressed(p), ["ctrl+shift+n"])

    def test_open_app_alias(self):
        e, p = engine("Finder")
        e.handle("open logic")
        self.assertIn(("open", "Logic Pro"), p.log)


class Focus(unittest.TestCase):
    def test_commands_go_back_to_the_daw(self):
        e, p = engine("Logic Pro")
        e.note_frontmost()
        p.app = AppRef("Limitless Voice")          # user clicked our window
        r = e.handle("show the mixer")
        self.assertTrue(r.handled)                 # still uses Logic's commands
        self.assertIn(("focus", "Logic Pro"), p.log)
        self.assertEqual(pressed(p), ["x"])


class Flow(unittest.TestCase):
    def test_sleep_and_wake(self):
        e, p = engine("Logic Pro")
        e.handle("go to sleep")
        self.assertFalse(e.handle("record").handled)
        self.assertEqual(p.log, [])
        e.handle("wake up")
        self.assertTrue(e.handle("record").handled)

    def test_repeat_count_and_again(self):
        e, p = engine("Pro Tools")
        r = e.handle("nudge right three times")
        self.assertEqual(r.times, 3)
        self.assertEqual(len(pressed(p)), 3)
        e.handle("again")
        self.assertEqual(len(pressed(p)), 6)

    def test_not_repeatable(self):
        e, p = engine("Logic Pro")
        e.handle("record twice")
        self.assertEqual(len(pressed(p)), 1)

    def test_confirm(self):
        e, p = engine("Logic Pro")
        e.handle("quit the app")
        e.handle("no")
        self.assertEqual(pressed(p), [])
        e.handle("quit app")
        e.handle("yes")
        self.assertEqual(pressed(p), ["cmd+q"])

    def test_dictation_uses_open_transcript(self):
        e, p = engine("Logic Pro")
        e.handle("start dictation")
        e.handle("[unk] two needs more reverb", "verse two needs more reverb period")
        self.assertIn(("type", " verse two needs more reverb."), p.log)
        e.handle("record", "record")          # typed, not run
        self.assertIn(("type", " record"), p.log)
        e.handle("stop dictation")
        e.handle("record")
        self.assertEqual(pressed(p), ["r"])

    def test_normalize(self):
        self.assertEqual(normalize("Okay, solo the track, please!"), "solo the track")
        self.assertEqual(normalize("[unk] solo track"), "solo track")


class Destructive(unittest.TestCase):
    def test_one_utterance_never_deletes_more_than_three_times(self):
        cases = [("Logic Pro", "mac"), ("Pro Tools", "mac"), ("Pro Tools", "windows")]
        phrases = ["delete fifty times", "delete that twenty times", "cut that fifty times",
                   "paste fifty times", "duplicate fifty times", "duplicate track fifty times",
                   "press delete fifty times", "press backspace twenty times",
                   "press command x fifty times", "press command v fifty times"]
        for app, os_name in cases:
            for phrase in phrases:
                e, p = engine(app, os_name)
                e.handle(phrase)
                self.assertLessEqual(len(pressed(p)), 3, f"{app} {os_name}: {phrase} -> {pressed(p)}")

    def test_harmless_commands_still_repeat(self):
        e, p = engine("Pro Tools")
        e.handle("nudge right twenty times")
        self.assertEqual(len(pressed(p)), 20)
        e, p = engine("Logic Pro")
        e.handle("press down ten times")
        self.assertEqual(len(pressed(p)), 10)


if __name__ == "__main__":
    unittest.main()
