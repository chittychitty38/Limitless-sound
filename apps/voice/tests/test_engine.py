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


def opened(p):
    return [e[1] for e in p.log if e[0] == "open"]


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

    def test_daw_command_with_no_daw_in_front_says_where_it_works(self):
        # Heard right, just not in a DAW: say so, instead of "didn't catch" (which sounds like
        # the microphone or the accent was the problem).
        e, p = engine("Finder")
        r = e.handle("play")
        self.assertFalse(r.handled)
        self.assertEqual(r.message, '"play" works in Logic Pro and Pro Tools. '
                                    'Bring one of them to the front, then say it again.')
        self.assertEqual(p.log, [])
        r = e.handle("show the piano roll")
        self.assertEqual(r.message, '"show the piano roll" works in Logic Pro. '
                                    'Bring it to the front, then say it again.')
        # Logic is Mac only, so Windows only offers Pro Tools.
        e, _ = engine("Notepad", os_name="windows")
        self.assertEqual(e.handle("record").message, '"record" works in Pro Tools. '
                                                     'Bring it to the front, then say it again.')
        # Something no app knows still says it wasn't caught.
        e, _ = engine("Finder")
        self.assertEqual(e.handle("make me a sandwich").message, 'Didn\'t catch a command in "make me a sandwich"')

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

    def test_a_question_asked_by_mistake_does_not_eat_the_next_command(self):
        e, p = engine("Logic Pro")
        e.handle("delete", "the lead")          # someone did say delete, the open recognizer misheard
        self.assertTrue(e.pending)
        e.handle("yes")
        self.assertEqual(pressed(p), ["delete"])
        e, p = engine("Logic Pro")
        e.handle("cut", "cat")                  # a stray word: Voice asks
        r = e.handle("play", "play")            # the next command still runs
        self.assertTrue(r.handled)
        self.assertEqual(pressed(p), ["space"])
        self.assertFalse(e.pending)

    def test_top_alone_is_not_go_to_start(self):
        # people's "stop" came back as "top" and sent the playhead to the start
        for app in ("Logic Pro", "Pro Tools"):
            e, p = engine(app)
            e.handle("top", "top")
            self.assertNotIn("return", pressed(p))
            e, p = engine(app)
            e.handle("go to start", "go to start")
            self.assertEqual(len(pressed(p)), 1)

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


class Dictation(unittest.TestCase):
    def test_misheard_stop_when_dictation_is_off_explains(self):
        e, p = engine("Logic Pro")
        r = e.handle("stop dictation")
        self.assertFalse(e.dictating)
        self.assertIn("begin dictation", r.message)
        self.assertEqual(pressed(p), [])
        e.handle("dictation on")
        self.assertTrue(e.dictating)
        e.handle("dictation off")
        self.assertFalse(e.dictating)


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

    def test_a_stray_word_never_cuts_pastes_or_deletes(self):
        # Real people's "cat" came back from the command recognizer as "cut" 64 times in 100.
        # A one-word Cut, Paste or Delete needs the open recognizer to have heard that word too.
        for app, said, heard_open in [("Logic Pro", "cut", "cat"), ("Logic Pro", "paste", "based"),
                                      ("Logic Pro", "delete", "the leap"), ("Pro Tools", "delete", "believe")]:
            e, p = engine(app)
            r = e.handle(said, heard_open)
            self.assertTrue(r.message.startswith("Say yes to"), f"{said} / {heard_open}: {r.message}")
            self.assertEqual(pressed(p), [], f"{said} / {heard_open}")
            e.handle("the cat sat down", "the cat sat down")                 # never confirmed
            self.assertEqual(pressed(p), [], f"{said} / {heard_open}")
        for app, said, keys in [("Logic Pro", "cut", ["cmd+x"]), ("Logic Pro", "paste", ["cmd+v"]),
                                ("Logic Pro", "delete", ["delete"])]:
            e, p = engine(app)
            self.assertTrue(e.handle(said, said).handled, said)              # both heard it
            self.assertEqual(pressed(p), keys)
            e, p = engine(app)
            self.assertTrue(e.handle(said).handled, said)                    # typed, or from another app
            self.assertEqual(pressed(p), keys)
        e, p = engine("Logic Pro")
        self.assertTrue(e.handle("cut that", "cat").message.startswith("Say yes"))   # longer, the same:
        self.assertEqual(pressed(p), [])                                   # one person's "cat" did that
        e.handle("yes")                                                    # they really said cut
        self.assertEqual(pressed(p), ["cmd+x"])
        e, p = engine("Logic Pro")
        self.assertTrue(e.handle("cut that", "cut that").handled)
        self.assertEqual(pressed(p), ["cmd+x"])
        e, p = engine("Logic Pro")
        self.assertTrue(e.handle("delete 3 times", "delete three time").handled)   # the verb is enough
        self.assertEqual(pressed(p), ["delete"] * 3)
        e, p = engine("Logic Pro")
        self.assertTrue(e.handle("copy", "happy").handled)                 # harmless: as before
        self.assertEqual(pressed(p), ["cmd+c"])

    def test_a_guess_at_a_mostly_unknown_sentence_is_not_a_command(self):
        # People reading aloud fired "[unk] enter [unk] [unk]" as Return and "stop [unk] [unk]
        # [unk]" as Play. With more unknown words than known, only the open transcript counts.
        e, p = engine("Logic Pro")
        self.assertFalse(e.handle("[unk] enter [unk] [unk]", "and then entered the room").handled)
        self.assertFalse(e.handle("stop [unk] [unk] [unk]", "stopped at the old inn").handled)
        self.assertEqual(pressed(p), [])
        self.assertTrue(e.handle("[unk] [unk] stop", "um stop").handled)     # the open one says it
        e, p = engine("Logic Pro")
        self.assertTrue(e.handle("[unk] play please", "uh play please").handled)  # mostly known: as before
        self.assertTrue(e.handle("[unk] mixer the", "show the mixer").handled)

    def test_free_text_comes_from_words_actually_heard(self):
        # "open the [unk] [unk] that" tried to open an app called "the that"
        e, p = engine("Finder")
        r = e.handle("open the [unk] [unk] that", "open the door so that")
        self.assertTrue(r.handled)
        self.assertEqual(opened(p), ["the door so that"])                 # the open recognizer's words
        self.assertFalse(e.handle("open the [unk] [unk] that", "and then the cat").handled)
        self.assertEqual(opened(p), ["the door so that"])
        e.handle("open logic pro", "open logic bro")                      # heard it all: as before
        self.assertEqual(opened(p)[-1], "Logic Pro")

    def test_windows_opens_an_app_by_whole_words(self):
        from limitless_voice.platforms.windows import best_shortcut
        links = ["Git Bash.lnk", "Logic Pro X.lnk", "Ableton Live 12 Suite.lnk", "Ableton Live 12 Suite Uninstall.lnk",
                 "Word.lnk", "FL Studio 21.lnk"]
        self.assertIsNone(best_shortcut("it", links))
        self.assertIsNone(best_shortcut("the that", links))
        self.assertEqual(best_shortcut("logic", links), "Logic Pro X.lnk")
        self.assertEqual(best_shortcut("ableton live", links), "Ableton Live 12 Suite.lnk")
        self.assertEqual(best_shortcut("word", links), "Word.lnk")
        self.assertEqual(best_shortcut("flstudio 21", links), "FL Studio 21.lnk")

    def test_harmless_commands_still_repeat(self):
        e, p = engine("Pro Tools")
        e.handle("nudge right twenty times")
        self.assertEqual(len(pressed(p)), 20)
        e, p = engine("Logic Pro")
        e.handle("press down ten times")
        self.assertEqual(len(pressed(p)), 10)


if __name__ == "__main__":
    unittest.main()
