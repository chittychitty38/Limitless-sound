"""Limitless Zoom listening in another of its languages: Spanish (ZOOM_LANGUAGE=es).

1. Vocabulary. Zoom's recognizer can only hear a word its speech model knows: given one it
   doesn't, it drops the word and warns. So every word of every phrase Zoom listens for in the
   language must be one the model knows, spelled its way ("más", not "mas"). For each word it
   doesn't know, the nearest words it does are printed.
2. Real people saying Zoom's command words: one-second clips from the Multilingual Spoken Words
   Corpus, cut out of sentences people read aloud for Common Voice, each through recognize_file,
   as test_command_words.py hears Zoom's English words. A word that's a command alone
   ("ampliar", "reducir", "repite") should do exactly that. MSWC has no clips of some commands
   ("acercar", "alejar"): each of those is heard through the nearest word it has, the same verb
   with one sound less ("acerca", "aleja"), which should be heard as the command. Every other
   word ("cerca", "otra", "todo", "aumento") should do nothing.
   And what if Zoom listened for other words too (test_zoom_real_speech.py's CANDIDATES):
   measured here, not in the app, to choose its words by.

Ordinary talk (an hour of people reading aloud in the language) is test_zoom_real_speech.py's,
with TALK_DIR. In English, test_command_words.py hears Zoom's words, so only the vocabulary is
checked here.

Needs VOSK_MODEL (the language's model) and ZOOM_WORDS_DIR, which
`stress/tools/get_command_words.py OUT --lang es --zoom` makes. Skipped otherwise.
"""

from __future__ import annotations

import difflib
import os
import time
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from conftest import need

need("zoom")

from limitless_zoom.voice import LANGUAGES, recognize_file  # noqa: E402
from test_voice_language import vocabulary  # noqa: E402
from test_zoom_real_speech import CANDIDATES, _model, _pick, trying  # noqa: E402

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
    tried = {w for p in CANDIDATES for w in p.split()} - words
    if tried:
        print("Words only tried here: " + ", ".join(f"{w}{'' if w in known else ' (unknown)'}" for w in sorted(tried)))
    for w in unknown:
        print(f"  {w}: closest it knows: {', '.join(difflib.get_close_matches(w, known, n=6, cutoff=0.6)) or '-'}")
    assert not unknown, f"the {Path(MODEL).name} model doesn't know: {', '.join(unknown)}"


def hear_all(clips, language):
    with ThreadPoolExecutor(WORKERS) as pool:
        return list(pool.map(lambda f: recognize_file(MODEL, f, model=_model(), language=language), clips))


def tally(clips, results, language):
    """Per word: tries, right, wrong action; and what was heard instead."""
    t, instead = defaultdict(Counter), defaultdict(Counter)
    for (word, _), (text, action) in zip(clips, results):
        want = expected(word, language)
        t[word]["tries"] += 1
        t[word]["right"] += action == want
        t[word]["wrong"] += action is not None and action != want
        if action != want:
            instead[word][f"{text or '(nothing)'} → {action or 'nothing'}"] += 1
    return t, instead


@needs_words
def test_real_people_saying_zoom_commands():
    root = Path(WORDS_DIR)
    words = sorted(d.name for d in root.iterdir() if d.is_dir() and any(d.glob("*.wav")))
    clips = [(w, f) for w in words for f in _pick(root / w)]
    started = time.monotonic()
    results = hear_all([f for _, f in clips], LANG)
    print(f"\n{len(clips)} clips of {len(words)} {LANG.name} words through Zoom in {time.monotonic() - started:.0f} s")
    t, instead = tally(clips, results, LANG)

    commands = [w for w in words if w in LANG.phrases]
    alike = [w for w in words if w not in LANG.phrases and expected(w, LANG)]
    others = [w for w in words if not expected(w, LANG)]
    for group, ws in (("command", commands), ("sounds like a command", alike), ("not a command", others)):
        for w in ws:
            what = f"→ {expected(w, LANG)}" if expected(w, LANG) else "did nothing"
            print(f"{w:<12} {group:<22} {what:<14} {t[w]['right']:>3}/{t[w]['tries']:<3} ({t[w]['right'] / t[w]['tries']:.0%})"
                  + (f"; instead: {', '.join(f'“{k}” ×{n}' for k, n in instead[w].most_common(3))}" if instead[w] else ""))

    def rate(ws, key="right"):
        n = sum(t[w]["tries"] for w in ws)
        return sum(t[w][key] for w in ws) / n if n else None

    right, alike_right = rate(commands), rate(alike)
    fired = 1 - rate(others) if others else 0.0
    wrong = sum(t[w]["wrong"] for w in commands + alike)
    print(f"\nCommands said alone: {right:.1%} right" + (f"; said like one ({', '.join(alike)}): {alike_right:.1%}" if alike else "")
          + f"; a different action {wrong} times. Other words zoomed {fired:.1%} of the time.")

    # What if Zoom listened for the candidates too: their clips, and what they'd do to the rest.
    if CANDIDATES:
        lang = trying(LANG, CANDIDATES)
        results2 = hear_all([f for _, f in clips], lang)
        t2, instead2 = tally(clips, results2, lang)
        print("\nWhat if Zoom listened for " + ", ".join(f"“{p}”" for p in CANDIDATES) + " too?")
        for w in words:
            if (t2[w]["right"], expected(w, lang)) != (t[w]["right"], expected(w, LANG)):
                what = f"→ {expected(w, lang)}" if expected(w, lang) else "did nothing"
                print(f"  {w:<12} {what:<14} {t2[w]['right']:>3}/{t2[w]['tries']:<3} (now {t[w]['right']})"
                      + (f"; instead: {', '.join(f'“{k}” ×{n}' for k, n in instead2[w].most_common(3))}" if instead2[w] else ""))

    # Floors from what CI measured (ubuntu-latest, up to 100 clips a word), less a margin.
    assert right >= 0.5, f"only {right:.1%} of Zoom's {LANG.name} commands were right"
    assert fired <= 0.2, f"words that aren't commands zoomed {fired:.1%} of the time"
