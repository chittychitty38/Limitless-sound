"""Limitless Voice and Zoom against real people saying their command words.

Google Speech Commands (test_voice_real_speech.py) has "stop" and "forward", but none of the
words Voice is mostly used for: "record", "cut", "paste", "undo" ... These are those words said
by real people: one-second clips from the Multilingual Spoken Words Corpus, cut out of sentences
people read aloud for Common Voice. So each word was said inside a sentence rather than on its
own, which makes them harder than a command said alone; "stop" and "forward" are here too, to
compare with Speech Commands.

1. Voice, with Logic Pro in front. Each word that's a command on its own goes through the app's
   own two recognizers and command engine, judged the way test_voice_real_speech.py judges
   Speech Commands: does the app do exactly what it does when it hears the word perfectly?
   Also what it heard instead, wrong commands fired, how soon it acts, and the what-if:
   every one-word command needs the open recognizer to hear that word too. "taller",
   "shorter" and "zoom" aren't Voice commands, so for Voice they're stray words.
2. Zoom. "fit", "taller", "shorter" and "again" through recognize_file, as
   test_zoom_real_speech.py does. "zoom" alone isn't a Zoom command, so it's a stray word.

Needs VOSK_MODEL and COMMAND_WORDS_DIR, which stress/tools/get_command_words.py makes.
Skipped otherwise. REAL_SPEECH_PER_WORD sets the clips a word (default 100).

VOICE_LANGUAGE runs Voice in another of its languages ("es"), with VOSK_MODEL that language's
model and COMMAND_WORDS_DIR its words (get_command_words.py --lang es). Then the stray words
are ones that sound like a command and aren't ("grabación", "pagar"), and Zoom, which listens
in English, is left out.
"""

from __future__ import annotations

import os
import time
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from conftest import need

need("voice")
need("zoom")

from limitless_zoom.voice import recognize_file  # noqa: E402
from test_voice_real_speech import (  # noqa: E402
    LANG, MODEL, WORKERS, _agreeing, _engine, _making, _pick, _sums, _waited, hear_word, kind, normalize, right,
    score)
from test_zoom_real_speech import _model  # noqa: E402

WORDS_DIR = os.environ.get("COMMAND_WORDS_DIR")
needs_words = pytest.mark.skipif(not (MODEL and WORDS_DIR), reason="set VOSK_MODEL and COMMAND_WORDS_DIR")
needs_english = pytest.mark.skipif(not LANG.is_english, reason="Zoom listens in English")

# What each language's run must reach (see the comments where they're checked).
FLOORS = {
    "en": {"right": 0.69, "worst": 0.32, "with_yes": 0.78, "worst_with_yes": 0.62, "stray": 0.03, "after": 1.35},
    "es": {"right": 0.79, "worst": 0.30, "with_yes": 0.80, "worst_with_yes": 0.30, "stray": 0.10, "after": 1.6},
}

# Zoom's commands among the words, and what each should do. "zoom" alone should do nothing.
ZOOM = {"fit": "fit", "taller": "taller", "shorter": "shorter", "again": "again", "zoom": None}


def _trusting(heard):
    """The other way round, also measured here only: as if the open recognizer always heard
    what the command recognizer did, so no command ever waits for the two to agree."""
    return [(c, c if normalize(c) else o) for c, o in heard]


def _median(xs):
    xs = sorted(xs)
    return xs[len(xs) // 2] if xs else None


@needs_words
def test_real_people_saying_voice_commands():
    """Real people saying Voice's commands: is the word heard, and does the right thing happen?"""
    root = Path(WORDS_DIR)
    words = sorted(d.name for d in root.iterdir() if d.is_dir())
    kinds = {w: kind(w) for w in words}
    commands = [w for w in words if kinds[w] == "command"]
    strays = [w for w in words if kinds[w] == "other"]
    # Words Voice listens for that do nothing alone, like numbers: right when heard as themselves.
    listened = [w for w in words if kinds[w] == "word"]
    used = commands + listened + strays
    jobs = [(w, f) for w in used for f in _pick(root / w)]
    _making.clear()
    started = time.monotonic()
    with ThreadPoolExecutor(WORKERS) as pool:
        heard = list(pool.map(lambda job: hear_word(job[1]), jobs))
    took = time.monotonic() - started

    tally, instead, wrong = score(used, jobs, heard, kinds)
    what_if, _, _ = score(used, jobs, [_agreeing(h, False) for h in heard], kinds)
    trusting, _, _ = score(used, jobs, [_trusting(h) for h in heard], kinds)
    soon = defaultdict(list)
    for (w, f), h in zip(jobs, heard):
        if kinds[w] == "command" and f in _waited and right(w, h, kinds[w])[0]:
            soon[w].append(_waited[f])

    print(f"\n{len(jobs)} clips of {len(used)} {LANG.english_name} words, heard in {took:.0f} s with {WORKERS} at once "
          f"({sum(_making):.0f} s of it building recognizers). In front: Logic Pro. Heard as "
          f"“command transcript / open transcript”.")
    print(f"\n{'word':<12} {'right':>13}  {'asked':>5}  {'wrong cmd':>12}  {'acts after':>10}  {'what-if':>7}  most often heard instead")
    for w in commands:
        t = tally[w]
        wrong_cmd = f"{t['wrong']}" + (f" ({t['destructive']} destr.)" if t["destructive"] else "")
        after = f"{_median(soon[w]) * 1000:.0f} ms" if soon[w] else "-"
        miss = ", ".join(f"“{k}” ×{n}" for k, n in instead[w].most_common(3))
        print(f"{w:<12} {t['hits']:>4}/{t['tries']:<4} {t['hits'] / t['tries']:>4.0%}  {t['asked']:>5}  {wrong_cmd:>12}  {after:>10}  "
              f"{what_if[w]['hits'] / t['tries']:>7.0%}  {miss}")
    for w in listened:
        t = tally[w]
        print(f"{w:<12} {t['hits']:>4}/{t['tries']:<4} {t['hits'] / t['tries']:>4.0%}  heard as itself"
              + (f"; instead {', '.join(f'“{k}” ×{n}' for k, n in instead[w].most_common(3))}" if instead[w] else ""))
    for w in strays:
        t = tally[w]
        print(f"{w:<12} stray word: fired a command {t['tries'] - t['hits']}/{t['tries']}"
              + (f", {t['destructive']} destructive" if t["destructive"] else "")
              + (f"; e.g. {', '.join(f'“{k}” ×{n}' for k, n in instead[w].most_common(3))}" if instead[w] else ""))

    hits, tries = _sums(tally, commands)
    if_hits, _ = _sums(what_if, commands)
    destroyed = sum(tally[w]["destructive"] for w in used)
    every = sorted(x for xs in soon.values() for x in xs)
    assert every, "Voice got none of the command words right"
    print(f"\nCommands: {hits}/{tries} right ({hits / tries:.1%}); acted on a median {_median(every) * 1000:.0f} ms "
          f"after the word ended, 9 in 10 within {every[int(len(every) * 0.9)] * 1000:.0f} ms ({len(every)} clips).")
    print(f"A command other than the one said: {sum(wrong.values())} times, {destroyed} destructive. "
          f"Most often: {wrong.most_common(8)}")
    asked_more = sum(tally[w]["asked"] for w in commands)
    print(f"Asked to confirm instead (\"Say yes to cut, or cancel\"): {asked_more} times, so "
          f"{(hits + asked_more) / tries:.1%} were right at once or with a yes. Per word: "
          + ", ".join(f"{w} {tally[w]['asked']}" for w in commands if tally[w]["asked"]))
    if listened:
        lh, lt = _sums(tally, listened)
        print(f"Words Voice listens for that do nothing alone ({', '.join(listened)}): {lh}/{lt} heard as "
              f"themselves ({lh / lt:.1%}).")
    if strays:
        quiet, stray_tries = _sums(tally, strays)
        q2, _ = _sums(what_if, strays)
        print(f"Stray words ({', '.join(strays)}): fired a command {stray_tries - quiet}/{stray_tries} times "
              f"({1 - quiet / stray_tries:.1%}); with the what-if, {1 - q2 / stray_tries:.1%}.")
    print(f"What if every one-word command needed the open recognizer to hear that word too? Right "
          f"{if_hits / tries:.1%} (now {hits / tries:.1%}). Per word: "
          + ", ".join(f"{w} {tally[w]['hits']}→{what_if[w]['hits']}" for w in commands))
    trust_hits, _ = _sums(trusting, commands)
    print(f"And if no command needed that, not even a destructive one? Right {trust_hits / tries:.1%}, "
          f"{sum(trusting[w]['destructive'] for w in used)} destructive from a wrong word. Per word: "
          + ", ".join(f"{w} {tally[w]['hits']}→{trusting[w]['hits']}" for w in commands if trusting[w]["hits"] != tally[w]["hits"]))

    # Floors from what CI measured (ubuntu-latest, 100 clips a word, October 2026), less a margin:
    # results move a little from one runner's CPU to another's. Voice 0.3.6, three runs: 73.4% to
    # 73.5% of commands right; the weakest, "cut", 39% to 40% (the open recognizer hears people's
    # "cut" as "god", "come" or "cup", and a destructive command needs it to agree); no destructive
    # key from a word that wasn't said; stray words fired a command 0.4% to 0.9% of the time;
    # record, play and stop acted on a median 0.53 to 0.60 s after the word ended, everything a
    # median 1.11 to 1.12 s. Voice 0.3.8 asks instead of refusing when the open recognizer
    # disagrees: 73.0% right at once and 82.0% at once or with a yes; the weakest at once,
    # "delete", 37%, and with a yes, "mute", 71%; still no destructive key from a wrong word.
    # Voice 0.4.0 in Spanish, two runs, 40 words with Logic Pro in front (MSWC has only 5 to 15
    # clips of some): 83.5% to 83.6% right at once and 84.2% at once or with a yes; the weakest,
    # "unir", 7 of its 15 clips (heard as nothing, or "mil"), so its floor is low; no destructive
    # key from a word not said; stray words that sound like a command fired one 6.2% to 6.5% of
    # the time ("pagar" heard as "parar" 8 times in 36); commands acted a median 1.38 s after the
    # word ended, as the Spanish model ends an utterance later than the English one, and play,
    # stop and record 0.57 s.
    floor = FLOORS[LANG.code]
    rate = {w: tally[w]["hits"] / tally[w]["tries"] for w in commands}
    assert hits / tries >= floor["right"], f"only {hits / tries:.1%} of the command words were right"
    worst = min(commands, key=rate.get)
    assert rate[worst] >= floor["worst"], f"“{worst}” was right only {rate[worst]:.0%} of the time"
    assert (hits + asked_more) / tries >= floor["with_yes"], \
        f"only {(hits + asked_more) / tries:.1%} of the command words were right at once or with a yes"
    with_yes = {w: (tally[w]["hits"] + tally[w]["asked"]) / tally[w]["tries"] for w in commands}
    worst = min(commands, key=with_yes.get)
    assert with_yes[worst] >= floor["worst_with_yes"], \
        f"“{worst}” was right only {with_yes[worst]:.0%} of the time, even with a yes"
    assert destroyed == 0, f"a word that wasn't said pressed a destructive key {destroyed} times"
    if strays:
        assert 1 - quiet / stray_tries <= floor["stray"], \
            f"stray words fired a command {1 - quiet / stray_tries:.1%} of the time"
    # The words that go the moment they're heard: record, play and stop in English.
    instant = [x for w in commands if _engine("Logic Pro")[0].instant(w) for x in soon[w]]
    if instant:
        assert _median(instant) <= 0.8, f"record, play and stop went a median {_median(instant):.2f} s after the word"
    assert _median(every) <= floor["after"], f"commands were acted on a median {_median(every):.2f} s after the word"


@needs_words
@needs_english
def test_real_people_saying_zoom_commands():
    """Real people saying Zoom's commands, and "zoom" alone, which shouldn't do anything."""
    root = Path(WORDS_DIR)
    words = [w for w in ZOOM if (root / w).is_dir()]
    clips = [(w, f) for w in words for f in _pick(root / w)]
    started = time.monotonic()
    with ThreadPoolExecutor(WORKERS) as pool:
        results = list(pool.map(lambda job: recognize_file(MODEL, job[1], model=_model()), clips))
    print(f"\n{len(clips)} clips of {len(words)} words through Zoom in {time.monotonic() - started:.0f} s")
    tries, hits, instead = Counter(), Counter(), defaultdict(Counter)
    for (w, _), (text, action) in zip(clips, results):
        tries[w] += 1
        if action == ZOOM[w]:
            hits[w] += 1
        else:
            instead[w][f"{text or '(nothing)'} → {action or 'nothing'}"] += 1
    for w in words:
        what = "did nothing" if ZOOM[w] is None else "right"
        print(f"{w:<8} {what} {hits[w]}/{tries[w]} ({hits[w] / tries[w]:.0%})"
              + ("; instead: " + ", ".join(f"“{k}” ×{n}" for k, n in instead[w].most_common(3)) if instead[w] else ""))
    commands = [w for w in words if ZOOM[w]]
    right_all = sum(hits[w] for w in commands) / sum(tries[w] for w in commands)
    print(f"Zoom's commands: {sum(hits[w] for w in commands)}/{sum(tries[w] for w in commands)} right ({right_all:.1%})")

    # Floors from what CI measured, less a margin. Over three runs (the last with Zoom 0.1.4):
    # 91.4% to 92.0% right (fit 87%, taller 24 of 25, shorter 97%, again 89% to 91%), and "zoom"
    # alone never zoomed in 100 tries.
    assert right_all >= 0.88, f"only {right_all:.1%} of Zoom's commands were right"
    worst = min(commands, key=lambda w: hits[w] / tries[w])
    assert hits[worst] / tries[worst] >= 0.80, f"“{worst}” was right only {hits[worst] / tries[worst]:.0%} of the time"
    if "zoom" in tries:
        assert tries["zoom"] - hits["zoom"] <= 3, f"“zoom” alone zoomed {tries['zoom'] - hits['zoom']} times"
