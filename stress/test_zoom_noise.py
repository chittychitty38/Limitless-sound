"""Limitless Zoom's voice commands with a band playing: is each still heard, and does the music
zoom anything by itself?

Each command is said with the band playing before, during and after it, the way a musician
says "zoom in" over a take, at three loudness levels. Needs VOSK_MODEL and TTS_WAV_DIR
(stress/tools/make_speech.py makes the clips), the same as test_voice_stress.py; skipped
otherwise.

ZOOM_LANGUAGE=es hears Zoom's Spanish phrases, every one of them, with VOSK_MODEL the Spanish
model and TTS_WAV_DIR made by `make_speech.py OUT --zoom es`.
"""

from __future__ import annotations

import json
import os
import threading
from array import array
from collections import Counter
from pathlib import Path

import pytest

from conftest import need

need("zoom")

from limitless_zoom.actions import VOICE_PHRASES  # noqa: E402
from limitless_zoom.voice import FILLERS, LANGUAGES, Hearing  # noqa: E402
from test_voice_stress import _noise, _pcm, _wav  # noqa: E402

LANG = LANGUAGES[os.environ.get("ZOOM_LANGUAGE") or "en"]
MODEL = os.environ.get("VOSK_MODEL")
TTS = os.environ.get("TTS_WAV_DIR")
RATE = 16000
MIN_CONF = LANG.threshold(0.55)   # with the app's default voice_confidence

needs_tts = pytest.mark.skipif(not (MODEL and TTS), reason="set VOSK_MODEL and TTS_WAV_DIR")
_mine = threading.local()


def _model():
    if not hasattr(_mine, "model"):
        import vosk
        vosk.SetLogLevel(-1)
        _mine.model = vosk.Model(MODEL)
    return _mine.model


def _hear(samples):
    """Audio through Zoom's own gate and recognizer, in 100 ms blocks the way the
    microphone's goes. Every result the recognizer gives."""
    import vosk
    rec = vosk.KaldiRecognizer(_model(), RATE, LANG.grammar())
    rec.SetWords(True)
    results = []
    hearing = Hearing(rec, results.append)
    pcm = array("h")
    pcm.frombytes(_pcm(samples))
    for i in range(0, len(pcm), RATE // 10):
        hearing.hear(pcm[i:i + RATE // 10])
    hearing.finish()
    return [r for r in results if r.get("text")]


def _before(text, words):
    """What Zoom 0.1.2 did with a result: any number of unknown words around a command."""
    text = " ".join(w for w in text.split() if w not in ("[unk]", *FILLERS))
    action = VOICE_PHRASES.get(text)
    words = [w for w in (words or []) if w.get("word") != "[unk]"]
    if action and words and sum(w.get("conf", 1.0) for w in words) / len(words) < MIN_CONF:
        return None
    return action


@needs_tts
def test_music_alone_does_not_zoom():
    import numpy as np
    heard = _hear(_noise("band", 120, np.random.default_rng(3)))
    fired = [(r["text"], LANG.match(r["text"], r.get("result"), MIN_CONF)) for r in heard]
    fired = [f for f in fired if f[1]]
    print(f"\nA band playing, 2 min, Zoom listening in {LANG.name}: {len(heard)} results, Zoom acted on "
          f"{len(fired)}: {fired[:8]}")
    assert len(fired) <= 1, fired


@needs_tts
@pytest.mark.parametrize("snr_db", [30, 15, 6])
def test_commands_get_through_music(snr_db):
    import numpy as np
    clips = json.loads((Path(TTS) / "zoom.json").read_text(encoding="utf-8"))
    rng = np.random.default_rng(4)
    right = Counter()
    wrong, missed = [], []
    for item in clips:
        speech = _wav(Path(TTS) / item["file"])
        speech = np.concatenate([np.zeros(2 * RATE), speech, np.zeros(3 * RATE)])
        band = _noise("band", len(speech) / RATE + 0.01, rng)[: len(speech)]
        voiced = speech[2 * RATE: -3 * RATE]
        gain = np.sqrt((voiced ** 2).mean() / ((band ** 2).mean() * 10 ** (snr_db / 10)))
        heard = _hear(speech + band * gain)
        rules = [("now", lambda r: LANG.match(r["text"], r.get("result"), MIN_CONF))]
        if LANG.code == "en":   # how Zoom 0.1.2 judged English
            rules.append(("before", lambda r: _before(r["text"], r.get("result"))))
        for rule, judge in rules:
            acts = [judge(r) for r in heard]
            right[rule] += item["expect"] in acts
            if rule == "now":
                wrong += [(item["say"], r["text"], a) for r, a in zip(heard, acts) if a and a != item["expect"]]
                if item["expect"] not in acts:
                    missed.append((item["say"], [r["text"] for r in heard]))
    n = len(clips)
    print(f"\nBand at {snr_db} dB below the voice, {LANG.name}: {right['now']}/{n} commands heard ({right['now'] / n:.0%})"
          + (f"; as Zoom 0.1.2 judged them (any unknown words around a command allowed), {right['before']}/{n}"
             if LANG.code == "en" else "")
          + f". Wrong action {len(wrong)} times: {wrong[:6]}. Missed: {missed[:12]}")
    # Measured on CI: every command at all three levels on Linux (espeak-ng, 14 clips), and 41 of 42
    # on a Mac (three of its voices), where "magnify" was once heard as "magnifier". The floor
    # allows two misses on Linux and six on the Mac.
    assert right["now"] / n >= 0.85, f"only {right['now'] / n:.0%} of Zoom's commands heard over music at {snr_db} dB"
    assert len(wrong) <= max(1, n // 10), wrong
