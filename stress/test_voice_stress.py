"""Limitless Voice against noise, music, chatter and mishearing.

Two layers:

1. The command engine fed what a recognizer produces on a bad day: half-heard
   phrases, word salad from the command vocabulary, numbers in the wrong place.
   Runs everywhere, no model needed.
2. The real speech recognizer (Vosk, the same model the app ships) fed real audio:
   white and pink noise, mains hum, a band playing chords, a room full of people
   talking, and spoken commands buried in noise. Needs VOSK_MODEL pointing at the
   model folder, and TTS_WAV_DIR with spoken clips (CI makes both); skipped otherwise.

What counts as a failure is what would hurt a musician: a destructive command firing
from noise or from one misheard utterance, or commands not getting through at all.
"""

from __future__ import annotations

import json
import os
import random
import wave
from pathlib import Path

import pytest

from conftest import need

need("voice")

from limitless_voice.engine import BUILTIN_PHRASES, Engine  # noqa: E402
from limitless_voice.grammar import DEFAULT_PACK_DIR, load_packs, recognizer_phrases, vocabulary  # noqa: E402
from limitless_voice.keys import spoken_vocabulary  # noqa: E402
from limitless_voice.numbers import NUMBER_WORDS  # noqa: E402
from limitless_voice.platforms.dryrun import DryRunPlatform  # noqa: E402

PACKS = load_packs([DEFAULT_PACK_DIR], "mac")
# Keys whose repeats destroy work: delete, cut, paste over, duplicate, new things.
DESTRUCTIVE = {"delete", "backspace", "forward_delete", "cmd+x", "cmd+v", "cmd+d", "cmd+backspace"}
MAX_DESTRUCTIVE_PER_UTTERANCE = 3


def engine(app="Logic Pro"):
    p = DryRunPlatform("mac", app=app)
    return Engine(p, PACKS, own_names=["Limitless Voice"]), p


def presses(p):
    return [e[1] for e in p.log if e[0] == "press"]


def destructive_count(keys):
    return sum(1 for k in keys if str(k).lower().replace(" ", "") in DESTRUCTIVE)


def command_vocab():
    return sorted(vocabulary(PACKS) | NUMBER_WORDS | {"times", "twice", "please", "and", "the"})


# ---------------------------------------------------------------- engine, no audio


@pytest.mark.parametrize("app", ["Logic Pro", "Pro Tools"])
def test_one_misheard_utterance_cannot_wreck_a_session(app):
    """Any phrase a recognizer could stitch together from the command words fires at most a few destructive keys."""
    words = command_vocab()
    rng = random.Random(1 if app == "Logic Pro" else 2)
    worst = (0, "")
    for _ in range(3000):
        heard = " ".join(rng.choice(words) for _ in range(rng.randint(1, 5)))
        e, p = engine(app)
        e.handle(heard, heard)
        n = destructive_count(presses(p))
        if n > worst[0]:
            worst = (n, heard)
    for spoken in ("delete fifty times", "cut that fifty times", "paste fifty times", "delete that twenty times"):
        e, p = engine(app)
        e.handle(spoken, spoken)
        n = destructive_count(presses(p))
        if n > worst[0]:
            worst = (n, spoken)
    print(f"\n{app}: worst single utterance: “{worst[1]}” → {worst[0]} destructive key presses")
    assert worst[0] <= MAX_DESTRUCTIVE_PER_UTTERANCE, (
        f"“{worst[1]}” pressed a destructive key {worst[0]} times from one utterance")


def test_asleep_means_asleep():
    """While asleep (a take, a conversation), nothing but the wake phrase does anything."""
    words = command_vocab()
    rng = random.Random(4)
    e, p = engine()
    e.handle("go to sleep")
    p.log.clear()
    woke = 0
    for _ in range(5000):
        heard = " ".join(rng.choice(words) for _ in range(rng.randint(1, 6)))
        if heard in ("wake up", "start listening", "computer wake up"):
            continue
        e.handle(heard, heard)
        if e.awake:
            woke += 1
            e.awake = False
    assert not presses(p), presses(p)[:10]
    assert woke == 0


def test_word_salad_from_ordinary_speech_rarely_fires():
    """Ordinary sentences (talking to a bandmate) through the engine: how often does something fire?"""
    sentences = [
        "can you turn me up a little in the headphones", "let's do that one more time from the top",
        "i think the second verse was better", "hang on i need some water", "the snare sounds a bit dull",
        "play it back for me", "that was a good take", "can we record the bridge next", "is the click too loud",
        "mute the guitar for a second", "i messed up the last bar", "okay let's go again",
        "what time is it", "my phone is ringing", "turn the lights down", "do you want a coffee",
    ]
    rng = random.Random(8)
    fired = []
    e, p = engine()
    for _ in range(2000):
        s = rng.choice(sentences)
        before = len(p.log)
        r = e.handle(s, s)
        if r.handled and len(p.log) > before:
            fired.append(s)
    rate = len(fired) / 2000
    print(f"\nchatter fired a command {rate:.0%} of the time: {sorted(set(fired))}")
    # Not zero: "play it back" and "mute the guitar" are close to real commands, which is why the
    # app has sleep and take mode. But most talk must do nothing.
    assert rate < 0.35


def test_engine_soak():
    """Hundreds of thousands of utterances; the engine must stay fast and keep no growing state."""
    import time

    words = command_vocab()
    rng = random.Random(6)
    e, p = engine()
    t0 = time.perf_counter()
    for i in range(10000):
        heard = " ".join(rng.choice(words) for _ in range(rng.randint(1, 4)))
        e.handle(heard, heard)
        if i % 1000 == 0:
            p.log.clear()
    per = (time.perf_counter() - t0) / 10000
    print(f"\n{per*1000:.2f} ms per utterance")
    assert per < 0.02


# ---------------------------------------------------------------- the real recognizer

MODEL = os.environ.get("VOSK_MODEL")
TTS = os.environ.get("TTS_WAV_DIR")
RATE = 16000


def _recognize(chunks):
    """Run audio through the app's own two-recognizer listener; return what the engine did."""
    from limitless_voice.audio import Listener

    heard = []
    phrases = recognizer_phrases(PACKS, BUILTIN_PHRASES | NUMBER_WORDS | spoken_vocabulary() | {"please", "and"})
    listener = Listener(MODEL, phrases, on_text=lambda c, o: heard.append((c, o)))
    recs = listener._make_recognizers(RATE)
    block = RATE // 10
    for chunk in chunks:
        for i in range(0, len(chunk), block * 2):
            listener._feed(recs, chunk[i:i + block * 2])
    listener._feed(recs, b"\0\0" * RATE)  # a second of silence ends the last utterance
    e, p = engine()
    fired, handled = [], []
    for c, o in heard:
        before = len(p.log)
        r = e.handle(c, o)
        if r.handled:
            handled.append(r.message)
            if len(p.log) > before:
                fired.append((c, o, r.message))
    _recognize.handled = handled
    return heard, fired, p


def _pcm(samples):
    import numpy as np
    return (np.clip(samples, -1, 1) * 32767).astype("<i2").tobytes()


def _noise(kind, seconds, rng):
    import numpy as np
    n = int(seconds * RATE)
    t = np.arange(n) / RATE
    if kind == "white":
        return rng.normal(0, 0.15, n)
    if kind == "pink":
        w = np.fft.rfft(rng.normal(0, 1, n))
        f = np.fft.rfftfreq(n, 1 / RATE)
        w[1:] /= np.sqrt(f[1:])
        x = np.fft.irfft(w, n)
        return x / np.abs(x).max() * 0.4
    if kind == "hum":
        return 0.2 * np.sin(2 * np.pi * 60 * t) + 0.1 * np.sin(2 * np.pi * 120 * t) + rng.normal(0, 0.01, n)
    if kind == "band":
        # Chords changing every half second, with a kick drum: a band playing in the room.
        out = np.zeros(n)
        roots = [110, 146.8, 164.8, 98]
        for k in range(int(seconds * 2)):
            s, e = int(k * RATE / 2), int((k + 1) * RATE / 2)
            r = roots[k % 4]
            for mult in (1, 1.26, 1.5, 2):
                out[s:e] += 0.08 * np.sign(np.sin(2 * np.pi * r * mult * t[s:e]))
            kick = np.exp(-np.arange(min(2000, e - s)) / 300) * np.sin(2 * np.pi * 55 * np.arange(min(2000, e - s)) / RATE)
            out[s:s + len(kick)] += 0.5 * kick
        return out
    raise ValueError(kind)


def _wav(path):
    import numpy as np
    with wave.open(str(path)) as w:
        data = np.frombuffer(w.readframes(w.getnframes()), "<i2").astype(float) / 32768
        if w.getnchannels() > 1:
            data = data.reshape(-1, w.getnchannels()).mean(axis=1)
        rate = w.getframerate()
    if rate != RATE:
        idx = np.arange(0, len(data), rate / RATE)
        data = np.interp(idx, np.arange(len(data)), data)
    return data


needs_model = pytest.mark.skipif(not MODEL, reason="set VOSK_MODEL to the speech model folder")
needs_tts = pytest.mark.skipif(not (MODEL and TTS), reason="set VOSK_MODEL and TTS_WAV_DIR")


@needs_model
@pytest.mark.parametrize("kind", ["white", "pink", "hum", "band"])
def test_noise_does_not_trigger_commands(kind):
    """Two minutes of each kind of noise, the way a cheap mic in a rehearsal room hears it."""
    import numpy as np
    rng = np.random.default_rng(0)
    heard, fired, p = _recognize([_pcm(_noise(kind, 120, rng))])
    print(f"\n{kind} noise, 2 min: recognizer heard {len(heard)} utterances, engine fired {len(fired)}: {fired[:8]}")
    assert destructive_count(presses(p)) == 0, fired
    assert len(fired) <= 2, f"{len(fired)} commands fired from 2 minutes of {kind} noise: {fired[:8]}"


@needs_tts
def test_chatter_through_the_recognizer():
    """People talking (no commands) through the real recognizer."""
    clips = sorted(Path(TTS).glob("chatter_*.wav"))
    assert clips, "no chatter clips"
    import numpy as np
    rng = np.random.default_rng(1)
    audio = [_pcm(_wav(c) + _noise("pink", len(_wav(c)) / RATE, rng) * 0.1) for c in clips]
    heard, fired, p = _recognize(audio)
    print(f"\nchatter: {len(clips)} sentences, heard {len(heard)}, fired {len(fired)}: {fired}")
    assert destructive_count(presses(p)) == 0, fired
    assert len(fired) <= len(clips) // 3


@needs_tts
@pytest.mark.parametrize("snr_db", [30, 15, 6])
def test_commands_get_through_noise(snr_db):
    """Spoken commands with a band playing underneath at three loudness levels."""
    import numpy as np
    manifest = json.loads((Path(TTS) / "commands.json").read_text())
    rng = np.random.default_rng(2)
    right = 0
    wrong = []
    for item in manifest:
        speech = _wav(Path(TTS) / item["file"])
        pad = np.zeros(RATE // 2)
        speech = np.concatenate([pad, speech, pad])
        noise = _noise("band", len(speech) / RATE + 0.01, rng)[: len(speech)]
        gain = np.sqrt((speech ** 2).mean() / ((noise ** 2).mean() * 10 ** (snr_db / 10)))
        heard, fired, p = _recognize([_pcm(speech + noise * gain)])
        got = _recognize.handled
        if any(item["expect"].lower() == (g or "").lower() for g in got):
            right += 1
        else:
            wrong.append((item["say"], [h[0] for h in heard], got))
    rate = right / len(manifest)
    print(f"\nSNR {snr_db} dB: {right}/{len(manifest)} commands understood ({rate:.0%}). Misses: {wrong[:10]}")
    floor = {30: 0.8, 15: 0.6, 6: 0.3}[snr_db]
    assert rate >= floor, f"only {rate:.0%} of commands understood with music at {snr_db} dB SNR"
