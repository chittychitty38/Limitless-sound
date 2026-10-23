"""Play, stop and record go the moment they're heard, not at the end of the utterance.

The listener is fed scripted recognizers, 100 ms at a time, so no speech model is needed.
"""

import json
import unittest

from limitless_voice.audio import Listener
from limitless_voice.engine import Engine
from limitless_voice.grammar import DEFAULT_PACK_DIR, load_packs
from limitless_voice.platforms.dryrun import DryRunPlatform

PACKS = load_packs([DEFAULT_PACK_DIR], "mac")
BLOCK = b"\0\0" * 1600   # 100 ms at 16 kHz


class Scripted:
    """A recognizer following a script: for each 100 ms block, everything said since the
    start (what a recognizer that was never reset would show) and whether the recognizer ends
    the utterance there. A reset, or an ended utterance, starts it afresh from that point."""

    def __init__(self, script):
        self.script, self.i, self.base, self.heard = script, 0, "", ""

    def _now(self):
        return self.heard[len(self.base):].strip() if self.heard.startswith(self.base) else self.heard

    def AcceptWaveform(self, data):
        self.heard, ends = self.script[min(self.i, len(self.script) - 1)]
        self.i += 1
        return ends

    def PartialResult(self):
        return json.dumps({"partial": self._now()})

    def Result(self):
        text, self.base = self._now(), self.heard
        return json.dumps({"text": text})

    FinalResult = Result

    def Reset(self):
        self.base = self.heard


def run(commands, open_, instant=True):
    """Feed the scripts block by block; what the listener reported, and at which block."""
    engine = Engine(DryRunPlatform("mac", app="Logic Pro"), PACKS)
    heard, block = [], [0]
    lis = Listener("model", [], on_text=lambda c, o: heard.append((block[0], c, o)),
                   instant=engine.instant if instant else None)
    recs = {"commands": Scripted(commands), "open": Scripted(open_)}
    for block[0] in range(1, max(len(commands), len(open_)) + 1):
        lis._feed(recs, BLOCK)
    return heard


def said(words, blocks, ends=False):
    """So many blocks of having heard words so far; the last one ends the utterance if ends."""
    return [(words, False)] * (blocks - 1) + [(words, ends)]


class Instant(unittest.TestCase):
    def test_stop_goes_as_soon_as_it_is_heard(self):
        # "stop" is heard from block 3; the open recognizer ends the utterance at block 13
        commands = said("", 2) + said("stop", 11)
        open_ = said("", 2) + said("stop", 11, ends=True)
        self.assertEqual(run(commands, open_), [(6, "stop", "stop")])   # 300 ms after it stopped changing
        self.assertEqual(run(commands, open_, instant=False), [(13, "stop", "stop")])   # as before

    def test_other_commands_wait_for_the_end_of_the_utterance(self):
        # "nudge right" can be followed by "four times", even after a pause
        commands = said("nudge right", 11)
        open_ = said("nudge right", 11, ends=True)
        self.assertEqual(run(commands, open_), [(11, "nudge right", "nudge right")])

    def test_a_command_inside_a_sentence_never_goes_early(self):
        commands = said("stop [unk]", 11)
        open_ = said("stop the bus", 11, ends=True)
        self.assertEqual(run(commands, open_), [(11, "stop [unk]", "stop the bus")])

    def test_what_comes_after_an_instant_command_still_counts(self):
        # "stop" ... "undo" in one breath: stop goes at once, undo when the utterance ends
        commands = said("stop", 6) + said("stop undo", 5)
        open_ = said("stop", 6) + said("stop undo", 5, ends=True)
        self.assertEqual(run(commands, open_), [(4, "stop", "stop"), (11, "undo", "stop undo")])

    def test_the_end_of_an_instant_command_is_not_reported_twice(self):
        # the command recognizer ends "record" itself, before 300 ms are up
        commands = said("record", 3, ends=True) + said("record", 8)
        open_ = said("record", 11, ends=True)
        self.assertEqual(run(commands, open_), [(3, "record", "record")])


class Engine_(unittest.TestCase):
    def engine(self):
        return Engine(DryRunPlatform("mac", app="Logic Pro"), PACKS)

    def test_which_commands_are_instant(self):
        e = self.engine()
        for words in ("play", "stop", "record", "start recording", "stop playback"):
            self.assertTrue(e.instant(words), words)
        for words in ("nudge right", "undo", "stop [unk]", "[unk] play", "go to bar 3", "delete", ""):
            self.assertFalse(e.instant(words), words)

    def test_only_when_plain_commands_are_listened_for(self):
        e = self.engine()
        e.awake = False
        self.assertFalse(e.instant("stop"))
        e.awake, e.dictating = True, True
        self.assertFalse(e.instant("stop"))
        e.dictating, e.take = False, True        # a take: "stop" ends it, and nothing else counts
        self.assertTrue(e.instant("stop"))
        self.assertTrue(e.instant("stop recording"))
        self.assertFalse(e.instant("play"))

    def test_an_instant_stop_runs_like_any_other(self):
        e = self.engine()
        r = e.handle("stop", "stop")
        self.assertTrue(r.handled)
        self.assertEqual([x[1] for x in e.platform.log if x[0] == "press"], ["space"])


if __name__ == "__main__":
    unittest.main()
