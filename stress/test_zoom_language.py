"""Limitless Zoom listening in another of its languages: Spanish (ZOOM_LANGUAGE=es).

1. Vocabulary. Zoom's recognizer can only hear a word its speech model knows: given one it
   doesn't, it drops the word and warns. So every word of every phrase Zoom listens for in the
   language must be one the model knows, spelled its way ("más", not "mas"). For each word it
   doesn't know, the nearest words it does are printed.
2. Real people saying Zoom's command words: one-second clips from the Multilingual Spoken Words
   Corpus, cut out of sentences people read aloud for Common Voice, each through Zoom's gate and
   recognizer, as test_command_words.py hears Zoom's English words. A word that's a command alone
   ("ampliar", "reducir", "repite") should do exactly that. MSWC has no clips of some commands
   ("acercar", "alejar"): each of those is heard through the nearest word it has, the same verb
   with one sound less ("acerca", "aleja"), which should be heard as the command unless Zoom
   listens for that word itself. Every other word ("cerca", "otra", "todo", "aumento") should do
   nothing. And what other ways of listening (test_zoom_real_speech.py's variants) would do:
   measured here, not in the app, to choose by.

Ordinary talk (an hour of people reading aloud in the language) is test_zoom_real_speech.py's,
with TALK_DIR. In English, test_command_words.py hears Zoom's words, so only the vocabulary is
checked here.

Needs VOSK_MODEL (the language's model) and ZOOM_WORDS_DIR, which
`stress/tools/get_command_words.py OUT --lang es --zoom` makes. Skipped otherwise.
"""

from __future__ import annotations

import difflib
import os
import threading
import time
import wave
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from conftest import need

need("zoom")

from limitless_zoom.voice import LANGUAGES, Hearing, pick_channel  # noqa: E402
from test_voice_language import vocabulary  # noqa: E402
from test_zoom_real_speech import MIN_CONF, THRESHOLDS, _model, _pick, variants  # noqa: E402

LANG = LANGUAGES[os.environ.get("ZOOM_LANGUAGE") or "en"]
MODEL = os.environ.get("VOSK_MODEL")
WORDS_DIR = os.environ.get("ZOOM_WORDS_DIR")
WORKERS = int(os.environ.get("REAL_SPEECH_WORKERS") or os.cpu_count() or 2)

# Commands MSWC has no clips of, heard through the nearest word it has.
SOUNDS_LIKE = {"es": {"acerca": "acercar", "aleja": "alejar", "ajuste": "ajustar"}}.get(LANG.code, {})

needs_words = pytest.mark.skipif(not (MODEL and WORDS_DIR and LANG.code != "en"),
                                 reason="set VOSK_MODEL, ZOOM_WORDS_DIR and ZOOM_LANGUAGE (English: test_command_words.py)")


def expected(word, language):
    """What a clip of this word should make Zoom do: its action, or None."""
    if word in language.phrases:
        return language.phrases[word]
    if word in SOUNDS_LIKE and word not in language.words():
        return language.phrases.get(SOUNDS_LIKE[word])
    return None


@pytest.mark.skipif(not MODEL, reason="set VOSK_MODEL")
def test_every_word_zoom_listens_for_is_known():
    known = vocabulary(MODEL)
    words = LANG.words()
    unknown = sorted(words - known)
    print(f"\n{Path(MODEL).name}: {len(known)} words. {LANG.name}: {len(words)} words Zoom listens for, "
          f"{len(unknown)} unknown: {', '.join(unknown) or 'none'}")
    for name, lang in variants().items():
        extra = lang.words() - words
        print(f"{name}: {len(extra)} words more, unknown: {', '.join(sorted(extra - known)) or 'none'}")
    for w in unknown:
        print(f"  {w}: closest it knows: {', '.join(difflib.get_close_matches(w, known, n=6, cutoff=0.6)) or '-'}")
    assert not unknown, f"the {Path(MODEL).name} model doesn't know: {', '.join(unknown)}"


_recognizers = threading.local()


def hear_clip(path, language):
    """One clip through Zoom's gate and recognizer, as voice.recognize_file hears it: what the
    last thing heard was, the action it would be at any confidence, and how sure the recognizer
    was. One recognizer per worker and way of listening, started afresh for each clip."""
    import vosk
    recs = _recognizers.__dict__.setdefault("recs", {})
    with wave.open(str(path), "rb") as w:
        rate, channels = w.getframerate(), w.getnchannels()
        key = (id(language), rate)
        if key not in recs:
            recs[key] = vosk.KaldiRecognizer(_model(), rate, language.grammar())
            recs[key].SetWords(True)
        rec = recs[key]
        rec.Reset()
        heard = []
        hearing = Hearing(rec, heard.append)
        while data := w.readframes(rate // 10):
            hearing.hear(pick_channel(data, channels))
        hearing.finish()
    res = next((r for r in reversed(heard) if r.get("text")), {})
    text = res.get("text", "")
    return text, language.match(text, res.get("result"), 0.0), language.confidence(res.get("result"))


def hear_all(clips, language):
    with ThreadPoolExecutor(WORKERS) as pool:
        return list(pool.map(lambda job: hear_clip(job[1], language), clips))


def tally(clips, results, language, min_conf=MIN_CONF):
    """Per word: tries, right, wrong action; and what was heard instead."""
    t, instead = defaultdict(Counter), defaultdict(Counter)
    for (word, _), (text, action, conf) in zip(clips, results):
        action = action if conf >= min_conf else None
        want = expected(word, language)
        t[word]["tries"] += 1
        t[word]["right"] += action == want
        t[word]["wrong"] += action is not None and action != want
        if action != want:
            instead[word][f"{text or '(nothing)'} → {action or 'nothing'}"] += 1
    return t, instead


def groups(words, language):
    commands = [w for w in words if w in language.phrases]
    alike = [w for w in words if w not in language.phrases and expected(w, language)]
    others = [w for w in words if not expected(w, language)]
    return commands, alike, others


def rates(t, words, language):
    """Commands right, sounding like one right, and other words zoomed: each a fraction or None."""
    def rate(ws, key="right"):
        n = sum(t[w]["tries"] for w in ws)
        return sum(t[w][key] for w in ws) / n if n else None
    commands, alike, others = groups(words, language)
    quiet = rate(others)
    return rate(commands), rate(alike), None if quiet is None else 1 - quiet


def shown(x):
    return "-" if x is None else f"{x:.1%}"


@needs_words
def test_real_people_saying_zoom_commands():
    root = Path(WORDS_DIR)
    words = sorted(d.name for d in root.iterdir() if d.is_dir() and any(d.glob("*.wav")))
    clips = [(w, f) for w in words for f in _pick(root / w)]
    started = time.monotonic()
    results = hear_all(clips, LANG)
    print(f"\n{len(clips)} clips of {len(words)} {LANG.name} words through Zoom in {time.monotonic() - started:.0f} s")
    t, instead = tally(clips, results, LANG)
    commands, alike, others = groups(words, LANG)
    for group, ws in (("command", commands), ("sounds like a command", alike), ("not a command", others)):
        for w in ws:
            what = f"→ {expected(w, LANG)}" if expected(w, LANG) else "did nothing"
            print(f"{w:<12} {group:<22} {what:<14} {t[w]['right']:>3}/{t[w]['tries']:<3} ({t[w]['right'] / t[w]['tries']:.0%})"
                  + (f"; instead: {', '.join(f'“{k}” ×{n}' for k, n in instead[w].most_common(3))}" if instead[w] else ""))
    right, alike_right, fired = rates(t, words, LANG)
    wrong = sum(t[w]["wrong"] for w in commands + alike)
    print(f"\nCommands said alone: {shown(right)} right" + (f"; said like one ({', '.join(alike)}): {shown(alike_right)}" if alike else "")
          + f"; a different action {wrong} times. Other words zoomed {shown(fired)} of the time.")
    confs = sorted(c for (w, _), (_, a, c) in zip(clips, results) if a and a == expected(w, LANG))
    if confs:
        print("How sure the recognizer was of the commands it got right: "
              + ", ".join(f"{p:.0%} under {confs[int(len(confs) * p)]:.2f}" for p in (0.05, 0.1, 0.25, 0.5)))

    # Other ways of listening, at each confidence: commands right / sounding like one / others zoomed.
    tried = {"as the app listens": (LANG, results)}
    for name, lang in variants().items():
        started = time.monotonic()
        tried[name] = (lang, hear_all(clips, lang))
        print(f"{name}: heard in {time.monotonic() - started:.0f} s")
    if len(tried) > 1:
        print(f"\nCommands right / said like one right / other words zoomed, at {' / '.join(map(str, THRESHOLDS))} sure or more:")
        for name, (lang, res) in tried.items():
            cells = [" ".join(shown(x) for x in rates(tally(clips, res, lang, th)[0], words, lang)) for th in THRESHOLDS]
            print(f"  {name:<24} " + "  |  ".join(cells))
        for name, (lang, res) in list(tried.items())[1:]:
            t2, instead2 = tally(clips, res, lang)
            changed = [w for w in words if t2[w]["right"] != t[w]["right"] or expected(w, lang) != expected(w, LANG)]
            print(f"{name}, at {MIN_CONF}: " + "; ".join(
                f"{w} {t[w]['right']}→{t2[w]['right']}/{t2[w]['tries']}"
                + (f" ({instead2[w].most_common(1)[0][0]})" if instead2[w] else "") for w in changed))

    # Floors from what CI measured (ubuntu-latest, up to 100 clips a word), less a margin.
    assert right >= 0.80, f"only {right:.1%} of Zoom's {LANG.name} commands were right"
    assert fired <= 0.16, f"words that aren't commands zoomed {fired:.1%} of the time"
