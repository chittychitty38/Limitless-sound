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

from limitless_zoom.voice import LANGUAGES, Hearing, Language, VoiceListener, recognize_file  # noqa: E402

LANG = LANGUAGES[os.environ.get("ZOOM_LANGUAGE") or "en"]
MODEL = os.environ.get("VOSK_MODEL")
WORDS_DIR = os.environ.get("SPEECH_COMMANDS_DIR") if LANG.code == "en" else None
TALK_DIR = os.environ.get("TALK_DIR") or os.environ.get("LIBRISPEECH_DIR")
PER_WORD = int(os.environ.get("REAL_SPEECH_PER_WORD", "100"))
WORKERS = int(os.environ.get("REAL_SPEECH_WORKERS") or os.cpu_count() or 2)
RATE = 16000

# Other ways to say Zoom's commands, measured but not listened for by the app: what Zoom would
# hear of real people saying them (test_zoom_language.py), and what an hour of ordinary talk
# would set off, if it listened for them too.
CANDIDATES = {
    "es": {"acerca": "in", "aleja": "out", "reduce": "out", "aumenta": "magIn", "disminuye": "magOut",
           "ajusta": "fit", "repetir": "again", "de nuevo": "again", "más zoom": "in", "menos zoom": "out",
           "encajar": "fit", "agrandar": "in", "achicar": "out"},
}.get(LANG.code, {})

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


def trying(language, extra):
    """The language with extra phrases listened for too."""
    return Language(language.code, language.name, language.model, language.size, {**language.phrases, **extra},
                    language.fillers, language.others)


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
    listener; a "go to sleep" counts as fired, and listening starts again after it.
    Returns the seconds heard and [(recording, action, what was heard)]."""
    import vosk
    rec = vosk.KaldiRecognizer(_model(), RATE, language.grammar())
    rec.SetWords(True)
    fired, now = [], {}
    zoom = VoiceListener(MODEL, lambda action: fired.append((now["utt"], action, now["text"])),
                         lambda status: None, language=language)

    def result(res):
        now["text"] = res.get("text", "")
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
    return " ".join(w for w in text.split() if w != "[unk]" and w not in language.filler_words)


def _report(fired, said, language):
    for phrase, k in Counter(_phrase(f[2], language) for f in fired).most_common():
        utt, action, text = next(f for f in fired if _phrase(f[2], language) == phrase)
        print(f"  {k:>3} × “{phrase}” → {action:<9} e.g. heard “{text}” (reading about “{said.get(utt, '')[:70]}”)")


@pytest.mark.skipif(not (MODEL and TALK_DIR), reason="set VOSK_MODEL and LIBRISPEECH_DIR or TALK_DIR")
def test_ordinary_talk_rarely_zooms():
    root = Path(TALK_DIR)
    said = dict(line.partition(" ")[::2]
                for line in (root / "transcripts.txt").read_text(encoding="utf-8").splitlines() if line)
    people = sorted(d for d in root.iterdir() if d.is_dir())
    started = time.monotonic()
    with ThreadPoolExecutor(WORKERS) as pool:
        streams = list(pool.map(hear, people))
    hours = sum(s for s, _ in streams) / 3600
    fired = [f for _, fs in streams for f in fs]
    print(f"\n{hours * 60:.1f} minutes of {len(people)} people reading aloud in {LANG.name} in "
          f"{time.monotonic() - started:.0f} s: Zoom acted {len(fired)} times ({len(fired) / hours:.1f} an hour)")
    _report(fired, said, LANG)

    if CANDIDATES:
        lang = trying(LANG, CANDIDATES)
        with ThreadPoolExecutor(WORKERS) as pool:
            more = [f for _, fs in pool.map(lambda folder: hear(folder, lang), people) for f in fs]
        print(f"\nWhat if Zoom listened for {', '.join(f'“{p}”' for p in CANDIDATES)} too? It would act "
              f"{len(more)} times ({len(more) / hours:.1f} an hour):")
        _report(more, said, lang)

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
