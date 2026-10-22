"""Limitless Voice against real people.

Every other voice test hears a synthetic voice (espeak-ng, or the Mac's `say`). This one hears
recordings of real people, through the app's own two recognizers and its command engine:

1. Hit rate. Google Speech Commands: one-second clips of single words, each said by a
   different person into their own phone or laptop. For each word Voice listens for
   ("stop", "no", "forward", "up", "yes", "zero" to "nine" ...), how often does the app do
   exactly what it does when it hears the word perfectly? The dataset's other words ("go",
   "off", "bird", "happy" ...) aren't commands on their own, so they should do nothing.
2. False triggers. LibriSpeech: an hour of people reading books aloud. None of it is meant
   as a command, so every command it fires is a false trigger. Counted per hour of talk,
   with the destructive ones (delete, cut, paste ...) apart.

Needs VOSK_MODEL (the model folder the app ships) and SPEECH_COMMANDS_DIR and
LIBRISPEECH_DIR, which stress/tools/get_real_speech.py makes. Skipped otherwise.
"""

from __future__ import annotations

import hashlib
import os
import threading
import time
import wave
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from conftest import need

need("voice")

from limitless_voice.actions import APP_ALIASES  # noqa: E402
from limitless_voice.engine import BUILTIN_PHRASES, DESTRUCTIVE_KEYS, Engine, normalize  # noqa: E402
from limitless_voice.grammar import DEFAULT_PACK_DIR, load_packs, recognizer_phrases  # noqa: E402
from limitless_voice.keys import spoken_vocabulary  # noqa: E402
from limitless_voice.numbers import HOMOPHONES, NUMBER_WORDS  # noqa: E402
from limitless_voice.platforms.dryrun import DryRunPlatform  # noqa: E402
from test_voice_stress import DESTRUCTIVE  # noqa: E402

MODEL = os.environ.get("VOSK_MODEL")
WORDS_DIR = os.environ.get("SPEECH_COMMANDS_DIR")
TALK_DIR = os.environ.get("LIBRISPEECH_DIR")
PER_WORD = int(os.environ.get("REAL_SPEECH_PER_WORD", "100"))
WORKERS = int(os.environ.get("REAL_SPEECH_WORKERS") or os.cpu_count() or 2)

RATE = 16000
BLOCK = RATE // 10 * 2              # 100 ms of 16-bit audio: what the app takes from the mic at a time
QUIET = b"\0\0" * (RATE // 10)      # 100 ms of silence

PACKS = load_packs([DEFAULT_PACK_DIR], "mac")
# What the app's command recognizer listens for. A copy of app.command_phrases, because
# importing app.py needs Qt.
PHRASES = recognizer_phrases(
    PACKS, BUILTIN_PHRASES | NUMBER_WORDS | spoken_vocabulary() | set(APP_ALIASES) | {"please", "and"})
# Keys that throw work away: this suite's list and the engine's own.
DESTRUCTIVE_PRESSES = {k.replace(" ", "").lower() for k in DESTRUCTIVE | DESTRUCTIVE_KEYS}
LISTENING = (True, False, False, False)   # awake, not dictating, not asking "say yes to ...", no take

needs_words = pytest.mark.skipif(not (MODEL and WORDS_DIR), reason="set VOSK_MODEL and SPEECH_COMMANDS_DIR")
needs_talk = pytest.mark.skipif(not (MODEL and TALK_DIR), reason="set VOSK_MODEL and LIBRISPEECH_DIR")


# ---------------------------------------------------------------- hearing, the app's way

_mine = threading.local()


def _listener():
    """One listener per worker thread, the way the app has one per microphone."""
    if not hasattr(_mine, "listener"):
        from limitless_voice.audio import Listener
        heard = []
        _mine.heard = heard
        _mine.listener = Listener(MODEL, PHRASES, on_text=lambda c, o: heard.append((c, o)))
        _mine.listener.load_model()
    return _mine.listener, _mine.heard


_making = []    # seconds each worker spent building recognizers, to see where the time goes


def _start(listener, heard):
    heard.clear()
    listener._cmd_parts = []
    started = time.perf_counter()
    recs = listener._make_recognizers(RATE)
    _making.append(time.perf_counter() - started)
    return recs


def _feed(listener, recs, pcm):
    for i in range(0, len(pcm), BLOCK):
        listener._feed(recs, pcm[i:i + BLOCK])


def _read(path):
    with wave.open(str(path)) as w:
        assert (w.getframerate(), w.getnchannels(), w.getsampwidth()) == (RATE, 1, 2), path
        return w.readframes(w.getnframes())


def hear_word(path):
    """One clip through fresh recognizers, as apps/voice/tests/test_audio.py does: half a
    second of quiet, the clip, then quiet until the app reports what it heard. Once it has
    heard a word the recognizer ends the utterance after half a second of quiet; if it heard
    nothing it could write down, only after five seconds. So wait up to six, as the app would."""
    listener, heard = _listener()
    recs = _start(listener, heard)
    _feed(listener, recs, QUIET * 5 + _read(path))
    for _ in range(60):
        if heard:
            break
        listener._feed(recs, QUIET)
    return list(heard)


def hear_talk(folder):
    """One person reading, as one long stretch of microphone audio: each recording, then the
    short pause a reader takes between sentences. Fresh recognizers for each person."""
    listener, heard = _listener()
    recs = _start(listener, heard)
    seconds, out = 0.0, []
    for path in sorted(folder.glob("*.wav")):
        pcm = _read(path)
        seconds += len(pcm) / 2 / RATE
        _feed(listener, recs, pcm + QUIET * 5)
        out += [(path.stem, c, o) for c, o in heard]
        heard.clear()
    _feed(listener, recs, QUIET * 20)
    out += [(path.stem, c, o) for c, o in heard]
    return seconds, out


# ---------------------------------------------------------------- what the engine does with it


def _engine(app):
    p = DryRunPlatform("mac", app=app)
    return Engine(p, PACKS, own_names=["Limitless Voice"]), p


def _state(e):
    return (e.awake, e.dictating, e.pending is not None, e.take)


def _destructive(log):
    return [e for e in log if e[0] == "press" and str(e[1]).replace(" ", "").lower() in DESTRUCTIVE_PRESSES]


def outcome(heard, app="Logic Pro"):
    """What one clip made the app do: (its replies, the keys and actions, whether its mode changed)."""
    e, p = _engine(app)
    replies = []
    for c, o in heard:
        r = e.handle(c, o)
        if r.handled:
            replies.append(r.message)
    return tuple(replies), tuple(p.log), _state(e) != LISTENING


def kind(word):
    """command: the app does something when it hears this word alone ("stop", "no", "forward").
    word:    the command recognizer listens for it alone, but alone it does nothing ("up", "nine").
    other:   not something Voice listens for on its own ("go", "off", "bird")."""
    replies, log, changed = outcome([(word, word)])
    if replies or log or changed:
        return "command"
    return "word" if word in PHRASES else "other"


def _heard_word(heard, word):
    """Did the engine get this word? Each utterance's text is what the engine reads first
    (the command transcript, or the open one when that's empty). A number counts when it
    was heard as a word the engine itself reads as that number after "bar", "track",
    "tempo" and the like: "to" for "two", "for" for "four"."""
    want = normalize(word)
    for c, o in heard:
        text = normalize(c) or normalize(o)
        if text == want or (word in NUMBER_WORDS and normalize(HOMOPHONES.get(text, text)) == want):
            return True
    return False


def _pick(folder):
    """Up to PER_WORD clips, each from a different person where there are enough people:
    everyone's first take before anyone's second, in an order fixed by a hash so every run
    uses the same clips."""
    def order(f):
        speaker, _, take = f.stem.partition("_nohash_")
        return int(take or 0), hashlib.sha1(speaker.encode()).hexdigest()
    return sorted(folder.glob("*.wav"), key=order)[:PER_WORD]


def _shown(heard):
    """What was heard, as "command transcript / open transcript" when the two differ."""
    parts = []
    for c, o in heard:
        c, o = " ".join(c.split()), " ".join(o.split())
        parts.append(c if c == o else f"{c or '-'} / {o or '-'}")
    return " | ".join(parts) or "(nothing)"


def score(words, jobs, heard, kinds):
    """Per word: tries, right, wrong command fired, destructive; and what was heard instead."""
    tally, instead, wrong = defaultdict(Counter), defaultdict(Counter), Counter()
    for (word, _), h in zip(jobs, heard):
        want, got = outcome([(word, word)]), outcome(h)
        fired = bool(got[1]) or got[2]
        if kinds[word] == "command":
            hit = got == want
        elif kinds[word] == "word":
            hit = got == want and _heard_word(h, word)
        else:
            hit = not fired
        t = tally[word]
        t["tries"] += 1
        t["hits"] += hit
        if fired and got != want:
            t["wrong"] += 1
            t["destructive"] += bool(_destructive(got[1]))
            wrong[(got[0] or ("(mode change)",))[0]] += 1
        if not hit:
            instead[word][_shown(h)] += 1
    return tally, instead, wrong


def _sums(tally, words):
    return sum(tally[w]["hits"] for w in words), sum(tally[w]["tries"] for w in words)


def _agreeing(heard, only_destructive=False):
    """A possible fix, measured here (not in the app): a one-word command only counts when
    the open recognizer heard that word too; otherwise the engine reads the open transcript."""
    out = []
    for c, o in heard:
        cmd = normalize(c).split()
        if len(cmd) == 1 and cmd[0] not in normalize(o).split():
            _, log, changed = outcome([(c, c)])
            if _destructive(log) if only_destructive else (log or changed):
                c = o
        out.append((c, o))
    return out


# ---------------------------------------------------------------- the tests


@needs_words
def test_real_people_saying_command_words():
    """Thousands of real people, one word each: is the word heard, and does the right thing happen?"""
    words = sorted(d.name for d in Path(WORDS_DIR).iterdir() if d.is_dir())
    jobs = [(w, f) for w in words for f in _pick(Path(WORDS_DIR) / w)]
    _making.clear()
    started = time.monotonic()
    with ThreadPoolExecutor(WORKERS) as pool:
        heard = list(pool.map(lambda job: hear_word(job[1]), jobs))
    took = time.monotonic() - started

    kinds = {w: kind(w) for w in words}
    tally, instead, wrong = score(words, jobs, heard, kinds)
    print(f"\n{len(jobs)} clips of {len(words)} words, {len({f.stem.split('_')[0] for _, f in jobs})} different "
          f"people, heard in {took:.0f} s with {WORKERS} at once ({sum(_making):.0f} s of it building "
          f"recognizers). In front: Logic Pro. Heard as “command transcript / open transcript”.")
    print(f"\n{'word':<9} {'kind':<8} {'right':>13}  {'wrong cmd':>9}  most often heard instead")
    for group in ("command", "word", "other"):
        for w in [w for w in words if kinds[w] == group]:
            t = tally[w]
            miss = ", ".join(f"“{k}” ×{n}" for k, n in instead[w].most_common(3))
            wrong_cmd = f"{t['wrong']}" + (f" ({t['destructive']} destr.)" if t["destructive"] else "")
            print(f"{w:<9} {group:<8} {t['hits']:>4}/{t['tries']:<4} {t['hits'] / t['tries']:>4.0%}  {wrong_cmd:>9}  {miss}")

    known = [w for w in words if kinds[w] != "other"]
    others = [w for w in words if kinds[w] == "other"]
    hits, tries = _sums(tally, known)
    quiet, stray_tries = _sums(tally, others)
    destroyed = sum(tally[w]["destructive"] for w in words)
    print(f"\nWords Voice listens for: {hits}/{tries} right ({hits / tries:.1%})")
    for group in ("command", "word"):
        g = [w for w in words if kinds[w] == group]
        gh, gt = _sums(tally, g)
        print(f"  {group}s ({', '.join(g)}): {gh}/{gt} ({gh / gt:.1%})")
    print(f"Words that aren't commands alone: fired something {stray_tries - quiet}/{stray_tries} times "
          f"({1 - quiet / stray_tries:.1%})")
    print(f"A command other than the one said: {sum(wrong.values())} times, {destroyed} destructive. "
          f"Most often: {wrong.most_common(8)}")

    # Stray words firing commands is the weak spot this test found. Two possible fixes, tried on
    # what was just heard so their cost and gain can be weighed before changing the app.
    for only_destructive in (False, True):
        t2, _, _ = score(words, jobs, [_agreeing(h, only_destructive) for h in heard], kinds)
        h2, _ = _sums(t2, known)
        q2, _ = _sums(t2, others)
        print(f"\nWhat if a one-word {'destructive ' if only_destructive else ''}command needed the open "
              f"recognizer to hear that word too? Right {h2 / tries:.1%} (now {hits / tries:.1%}); stray words "
              f"fire {1 - q2 / stray_tries:.1%} (now {1 - quiet / stray_tries:.1%}); destructive "
              f"{sum(t2[w]['destructive'] for w in words)} (now {destroyed}). Per word: "
              + ", ".join(f"{w} {tally[w]['hits']}→{t2[w]['hits']}" for w in words if t2[w]["hits"] != tally[w]["hits"]))

    # Floors from what CI measured (ubuntu-latest, 100 clips a word, October 2026), less a margin:
    # results move a little from one runner's CPU to another's. Measured: 91.2% and 91.6% right;
    # "stop" 96%; the weakest word, "eight", 82% (people's "eight" often comes back as "a").
    rate = {w: tally[w]["hits"] / tally[w]["tries"] for w in words}
    assert hits / tries >= 0.87, f"only {hits / tries:.1%} of the words Voice listens for were right"
    if "stop" in rate:
        assert rate["stop"] >= 0.90, f"“stop”, which ends a take, was right only {rate['stop']:.0%} of the time"
    worst = min(known, key=rate.get)
    assert rate[worst] >= 0.72, f"“{worst}” was right only {rate[worst]:.0%} of the time"
    # Measured: stray words fired a command 21.6% of the time, and pressed a destructive key on
    # 3.8% of them (people's "cat" heard as "cut"). That's a known problem (stress/README.md);
    # these ceilings only stop it getting worse. Bring them down when it's fixed.
    assert 1 - quiet / stray_tries <= 0.25, f"stray words fired a command {1 - quiet / stray_tries:.1%} of the time"
    assert destroyed / stray_tries <= 0.045, f"stray words pressed a destructive key {destroyed} times"


@needs_talk
def test_ordinary_talk_rarely_fires_commands():
    """An hour of people reading aloud with Voice listening: how many commands fire?"""
    root = Path(TALK_DIR)
    said = dict(line.partition(" ")[::2] for line in (root / "transcripts.txt").read_text().splitlines() if line)
    people = sorted(d for d in root.iterdir() if d.is_dir())
    started = time.monotonic()
    with ThreadPoolExecutor(WORKERS) as pool:
        streams = list(pool.map(hear_talk, people))
    took = time.monotonic() - started
    hours = sum(s for s, _ in streams) / 3600
    utterances = sum(len(h) for _, h in streams)
    print(f"\n{hours * 60:.1f} minutes of {len(people)} people reading aloud, heard as {utterances} utterances "
          f"in {took:.0f} s with {WORKERS} at once")

    # Most commands an hour of reading aloud may fire. Measured on two runners: Logic Pro 1.9 and
    # 4.7 an hour, Pro Tools 4.7 and 7.6, none destructive. Only a handful in the hour, so a
    # different CPU moves them by two or three.
    ceiling = {"Logic Pro": 8, "Pro Tools": 12}
    too_many = []
    for app, most in ceiling.items():
        fired = []
        for _, heard in streams:
            # Each reader is a fresh session: "again" repeats only that reader's last command.
            e, p = _engine(app)
            for utt, c, o in heard:
                before = len(p.log)
                r = e.handle(c, o)
                acts = p.log[before:]
                if acts or _state(e) != LISTENING:
                    fired.append((utt, c, o, r.message, acts))
                    # Judge every utterance from plain listening, so one false trigger
                    # (falling asleep, dictation on) neither hides nor causes the rest.
                    e.awake, e.dictating, e.pending, e.take = True, False, None, False
        bad = [f for f in fired if _destructive(f[4])]
        print(f"\n{app}: {len(fired)} commands fired ({len(fired) / hours:.1f} an hour), "
              f"{len(bad)} destructive ({len(bad) / hours:.1f} an hour)")
        for message, n in Counter(f[3] for f in fired).most_common(12):
            utt, c, o, _, acts = next(f for f in fired if f[3] == message)
            print(f"  {n:>3} × {message!r:<28} e.g. heard “{c}” / “{o}” {list(acts)[:3]}  (reading about “{said.get(utt, '')[:70]}”)")
        for utt, c, o, message, acts in bad:
            print(f"  DESTRUCTIVE: {message!r} {list(acts)} heard “{c}” / “{o}” (reading about “{said.get(utt, '')[:70]}”)")
        if len(fired) / hours > most or len(bad) / hours > 1:
            too_many.append(f"{app}: {len(fired) / hours:.1f} an hour (most {most}), {len(bad) / hours:.1f} destructive (most 1)")
    assert not too_many, too_many
