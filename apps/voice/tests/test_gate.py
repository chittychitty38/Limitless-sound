"""Silence isn't decoded: the listener's gate passes the recognizers only sound, with the second
before it and a second and a half after. No speech model needed."""

import json
import unittest
from array import array

from limitless_voice.audio import Listener

BLOCK = 1600   # samples: 100 ms at 16 kHz


def block(level):
    return array("h", [level] * BLOCK).tobytes()


class Counting:
    """A recognizer that counts the blocks it's fed; once fed, it has heard `words`."""

    def __init__(self, words=""):
        self.words, self.fed, self.finals = words, 0, 0

    def AcceptWaveform(self, data):
        self.fed += 1
        return False

    def PartialResult(self):
        return json.dumps({"partial": self.words if self.fed else ""})

    def FinalResult(self):
        self.finals += 1
        return json.dumps({"text": self.words if self.fed else ""})

    def Reset(self):
        pass


def listen(levels, open_words="", command_words=""):
    heard = []
    lis = Listener("model", [], on_text=lambda c, o: heard.append((c, o)))
    recs = {"commands": Counting(command_words), "open": Counting(open_words)}
    for level in levels:
        lis.hear(recs, block(level))
    return recs, heard


class Gate(unittest.TestCase):
    def test_a_quiet_room_costs_nothing(self):
        # a steady quiet room (a fan, a laptop's own noise), a little louder after a while
        recs, heard = listen([40] * 100 + [55] * 100)
        self.assertEqual((recs["open"].fed, recs["commands"].fed), (0, 0))
        self.assertEqual(heard, [])
        recs, heard = listen([0] * 100)          # a muted input
        self.assertEqual((recs["open"].fed, recs["commands"].fed), (0, 0))

    def test_a_sound_brings_the_second_before_it_and_the_quiet_after(self):
        # 2 s of a quiet room, 0.3 s of speech, 3 s of the room again
        recs, heard = listen([40] * 20 + [3000] * 3 + [40] * 30, open_words="stop the music")
        self.assertEqual(recs["open"].fed, 10 + 3 + 15)          # 1 s before, the sound, 1.5 s after
        self.assertEqual(recs["commands"].fed, 10 + 3 + 15)
        # the open recognizer hadn't ended the utterance itself: it's read out when the sound stops
        self.assertEqual(heard, [("stop the music", "stop the music")])

    def test_soft_speech_in_a_quiet_room_is_heard(self):
        # quieter than SOUND, but four times the room's noise floor
        recs, _ = listen([30] * 20 + [120] * 5 + [30] * 20)
        self.assertEqual(recs["open"].fed, 10 + 5 + 15)

    def test_nothing_held_nothing_read_out(self):
        # a click: the recognizers heard nothing, so they're left be (no FinalResult, which would
        # make them forget what they've learned about the room)
        recs, heard = listen([40] * 20 + [3000] + [40] * 20)
        self.assertEqual(heard, [])
        self.assertEqual(recs["open"].finals, 0)


if __name__ == "__main__":
    unittest.main()
