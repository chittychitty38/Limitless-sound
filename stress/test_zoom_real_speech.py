"""Limitless Zoom against real people: does ordinary talk zoom the screen?

Zoom listens for only a few phrases ("zoom in", "taller", "fit", "again" ...), and none of
Google Speech Commands' words is one of them, so here every action is a false trigger:

1. Stray words. Speech Commands clips ("stop", "up", "nine", "bird" ...), each through
   recognize_file, the function Zoom's own CI check uses.
2. Talk. An hour of LibriSpeech readers, through the same gate and recognizer as the
   microphone's audio, counted per hour.

Needs VOSK_MODEL, SPEECH_COMMANDS_DIR and LIBRISPEECH_DIR, the same as
test_voice_real_speech.py. Skipped otherwise.

ZOOM_LANGUAGE runs it in another of Zoom's languages ("es"), with VOSK_MODEL that language's
model and TALK_DIR an hour of people reading aloud in it (stress/tools/get_fleurs.py). Speech
Commands is English only, so then only the talk is heard. test_zoom_language.py hears real
people say Zoom's Spanish command words.
"""

from __future__ import annotations

import hashlib
import os
import threading
import time
import wave
from array import array
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from conftest import need

need("zoom")

from limitless_zoom.voice import LANGUAGES, Hearing, VoiceListener, recognize_file, without  # noqa: E402

LANG = LANGUAGES[os.environ.get("ZOOM_LANGUAGE") or "en"]
MODEL = os.environ.get("VOSK_MODEL")
WORDS_DIR = os.environ.get("SPEECH_COMMANDS_DIR") if LANG.code == "en" else None
TALK_DIR = os.environ.get("TALK_DIR") or os.environ.get("LIBRISPEECH_DIR")
PER_WORD = int(os.environ.get("REAL_SPEECH_PER_WORD", "100"))
WORKERS = int(os.environ.get("REAL_SPEECH_WORKERS") or os.cpu_count() or 2)
RATE = 16000

MIN_CONF = 0.55                      # the app's default
THRESHOLDS = (0.55, 0.7, 0.8, 0.9)   # what a higher one would do, measured here


def variants():
    """Other ways Zoom could listen in the language, measured here and not in the app: what Zoom
    would hear of real people saying its words (test_zoom_language.py), and what an hour of
    ordinary talk would set off. "others" are words listened for only to be written down instead
    of a command they sound like."""
    if LANG.code != "es":
        return {}
    from zoom_trial_words import NEAR, SHORT, TOP300, TOP1000
    return {
        "+ near": LANG.adding(others=NEAR + SHORT),
        "+ near, 300 common": LANG.adding(others=NEAR + SHORT + TOP300),
        "+ near, 1000 common": LANG.adding(others=NEAR + SHORT + TOP1000),
        "+ 1000 common": LANG.adding(others=SHORT + TOP1000),
    }

_mine = threading.local()


def _model():
    """One model per worker thread."""
    if not hasattr(_mine, "model"):
        import vosk
        vosk.SetLogLevel(-1)
        _mine.model = vosk.Model(MODEL)
    return _mine.model


def _pick(folder):
    """The same clips as test_voice_real_speech.py: a different person each, in a fixed order."""
    def order(f):
        speaker, _, take = f.stem.partition("_nohash_")
        return int(take or 0), hashlib.sha1(speaker.encode()).hexdigest()
    return sorted(folder.glob("*.wav"), key=order)[:PER_WORD]


@pytest.mark.skipif(not (MODEL and WORDS_DIR), reason="set VOSK_MODEL and SPEECH_COMMANDS_DIR (English)")
def test_stray_words_do_not_zoom():
    words = sorted(d.name for d in Path(WORDS_DIR).iterdir() if d.is_dir())
    clips = [f for w in words for f in _pick(Path(WORDS_DIR) / w)]
    started = time.monotonic()
    with ThreadPoolExecutor(WORKERS) as pool:
        results = list(pool.map(lambda f: recognize_file(MODEL, f, model=_model()), clips))
    fired = Counter((f.parent.name, text, action) for f, (text, action) in zip(clips, results) if action)
    n = sum(fired.values())
    print(f"\n{len(clips)} clips of {len(words)} words in {time.monotonic() - started:.0f} s: "
          f"Zoom acted on {n} ({n / len(clips):.1%})")
    for (word, text, action), k in fired.most_common(15):
        print(f"  {k:>3} × “{word}” heard as “{text}” → {action}")
    # Measured on CI: 2.2% to 2.3% (2.1% with 150 clips a word), mostly "bed" heard as "fit" and
    # "follow" as "taller". The ceiling leaves a margin.
    assert n / len(clips) <= 0.04, f"Zoom acted on {n / len(clips):.1%} of stray words"


def hear(folder, language=LANG):
    """One person reading, as one stretch of microphone audio with a short pause between
    sentences, through Zoom's gate and recognizer. Actions are judged by Zoom's own
    listener, at any confidence (see MIN_CONF); a "go to sleep" counts as fired, and listening
    starts again after it. Returns the seconds heard and
    [(recording, action, what was heard, how sure the recognizer was)]."""
    import vosk
    rec = vosk.KaldiRecognizer(_model(), RATE, language.grammar())
    rec.SetWords(True)
    fired, now = [], {}
    zoom = VoiceListener(MODEL, lambda action: fired.append((now["utt"], action, now["text"], now["conf"])),
                         lambda status: None, min_conf=0.0, language=language)

    def result(res):
        now["text"] = res.get("text", "")
        now["conf"] = language.confidence(res.get("result"))
        zoom._result(res)
        zoom.asleep = False

    hearing = Hearing(rec, result)
    seconds = 0.0
    pause = array("h", [0]) * (RATE // 10)
    for path in sorted(folder.glob("*.wav")):
        now["utt"] = path.stem
        with wave.open(str(path)) as w:
            samples = array("h", w.readframes(w.getnframes()))
        seconds += len(samples) / RATE
        for i in range(0, len(samples), RATE // 10):
            hearing.hear(samples[i:i + RATE // 10])
        for _ in range(5):
            hearing.hear(pause)
    for _ in range(20):
        hearing.hear(pause)
    hearing.finish()
    return seconds, fired


def _phrase(text, language):
    """The phrase in what was heard: without [unk] and fillers."""
    return " ".join(w for w in without(text.split(), language.fillers) if w != "[unk]")


def _report(fired, said, language, most=40):
    counted = Counter(_phrase(f[2], language) for f in fired)
    for phrase, k in counted.most_common(most):
        utt, action, text, conf = next(f for f in fired if _phrase(f[2], language) == phrase)
        print(f"  {k:>3} × “{phrase}” → {action:<9} e.g. heard “{text}” ({conf:.2f} sure; reading about "
              f"“{said.get(utt, '')[:60]}”)")


def _hear_all(people, language):
    with ThreadPoolExecutor(WORKERS) as pool:
        streams = list(pool.map(lambda folder: hear(folder, language), people))
    return sum(s for s, _ in streams) / 3600, [f for _, fs in streams for f in fs]


@pytest.mark.skipif(not (MODEL and TALK_DIR), reason="set VOSK_MODEL and LIBRISPEECH_DIR or TALK_DIR")
def test_ordinary_talk_rarely_zooms():
    root = Path(TALK_DIR)
    said = dict(line.partition(" ")[::2]
                for line in (root / "transcripts.txt").read_text(encoding="utf-8").splitlines() if line)
    people = sorted(d for d in root.iterdir() if d.is_dir())
    started = time.monotonic()
    hours, heard = _hear_all(people, LANG)
    fired = [f for f in heard if f[3] >= MIN_CONF]
    print(f"\n{hours * 60:.1f} minutes of {len(people)} people reading aloud in {LANG.name} in "
          f"{time.monotonic() - started:.0f} s: Zoom acted {len(fired)} times ({len(fired) / hours:.1f} an hour)")
    _report(fired, said, LANG)

    def per_hour(acts):
        return " / ".join(f"{sum(f[3] >= th for f in acts) / hours:.1f}" for th in THRESHOLDS)

    tried = variants()
    if tried:
        print(f"\nActed an hour, at {' / '.join(map(str, THRESHOLDS))} sure or more:")
        print(f"  {'as the app listens':<24} {per_hour(heard)}")
        for name, lang in tried.items():
            started = time.monotonic()
            _, acts = _hear_all(people, lang)
            print(f"  {name:<24} {per_hour(acts)}   ({len(lang.others)} other words, {time.monotonic() - started:.0f} s)")
            _report([f for f in acts if f[3] >= MIN_CONF], said, lang, most=6)

    # Most Zoom may act in an hour of reading aloud. Only a handful in the hour, so a different
    # CPU moves them by one or two.
    ceiling = {
        # LibriSpeech. Measured on CI: 3.8 an hour, all of them "shorter" or "fit" heard on its own
        # (Zoom 0.1.2: 16.1 to 17.9, nearly all a command word inside a sentence; 0.1.3: 13.2).
        "en": 7,
        # FLEURS es_419, the first hour of its dev split.
        "es": 20,
    }[LANG.code]
    assert len(fired) / hours <= ceiling, f"Zoom acted {len(fired) / hours:.1f} times an hour of talk"
