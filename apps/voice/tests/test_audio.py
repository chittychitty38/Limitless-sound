"""End-to-end recognition: synthetic speech -> both recognizers -> engine.

Needs a Vosk model (set LV_MODEL or put it in ./models) and espeak-ng to
make the speech. Skipped when either is missing. espeak's robot voice is a
harder test than a real person, so passing here is a decent floor.
"""

import os
import shutil
import subprocess
import tempfile
import unittest
import wave
from pathlib import Path

from limitless_voice.engine import Engine
from limitless_voice.grammar import DEFAULT_PACK_DIR, load_packs
from limitless_voice.platforms.dryrun import DryRunPlatform

MODEL = os.environ.get("LV_MODEL") or str(Path(__file__).parent.parent / "models" / "vosk-model-small-en-us-0.15")
HAVE = Path(MODEL).is_dir() and shutil.which("espeak-ng")


def speak_to_pcm(text):
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "s.wav"
        subprocess.run(["espeak-ng", "-v", "en-us", "-s", "140", "-w", str(path), text], check=True)
        with wave.open(str(path)) as wf:
            rate = wf.getframerate()
            pcm = wf.readframes(wf.getnframes())
    silence = b"\0\0" * int(rate * 0.6)
    return rate, silence + pcm + silence * 2


@unittest.skipUnless(HAVE, "needs a Vosk model and espeak-ng")
class Recognition(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from limitless_voice.app import command_phrases
        from limitless_voice.audio import Listener
        cls.packs = load_packs([DEFAULT_PACK_DIR], "mac")
        cls.heard = []
        cls.listener = Listener(MODEL, command_phrases(cls.packs),
                                on_text=lambda a, b: cls.heard.append((a, b)))
        cls.listener.load_model()

    def run_phrase(self, text, app="Logic Pro"):
        rate, pcm = speak_to_pcm(text)
        recs = self.listener._make_recognizers(rate)
        self.heard.clear()
        block = int(rate * 0.1) * 2
        for i in range(0, len(pcm), block):
            self.listener.hear(recs, pcm[i:i + block])
        self.assertTrue(self.heard, f"nothing recognized for {text!r}")
        platform = DryRunPlatform("mac", app=app)
        engine = Engine(platform, self.packs)
        return engine.handle(*self.heard[-1]), platform

    def test_commands(self):
        cases = {
            "go to bar thirty two": ("go to bar {bar:number}", {"bar": 32}),
            "show the mixer": ("mixer", {}),
            "nudge right four times": None,  # Pro Tools below
            "solo track": ("solo", {}),
            "quantize": ("quantize", {}),
            "unmute": ("mute", {}),
            "zoom in twice": ("zoom in", {}),
            "start recording": ("record", {}),
            "record": ("record", {}),
            "press command shift november": ("press {chord:keys}", {"chord": "cmd+shift+n"}),
        }
        failures = []
        for spoken, want in cases.items():
            if want is None:
                continue
            r, _ = self.run_phrase(spoken)
            if not r.handled or r.command.phrases[0] != want[0] or r.params != want[1]:
                failures.append(f"{spoken!r} -> heard {self.heard[-1]}, got {r.message}")
        r, p = self.run_phrase("nudge right four times", app="Pro Tools")
        if r.times != 4:
            failures.append(f"nudge x4 -> {self.heard[-1]}, {r.message}")
        self.assertEqual(failures, [])

    def test_sleep(self):
        r, _ = self.run_phrase("go to sleep")
        self.assertEqual(r.message, "Going to sleep")


if __name__ == "__main__":
    unittest.main()
