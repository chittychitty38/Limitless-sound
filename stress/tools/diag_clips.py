"""Temporary (to be removed): is it the clips or the model? For one language (VOICE_LANGUAGE,
VOSK_MODEL, COMMAND_WORDS_DIR, TALK_DIR as the tests take them):

1. For the words given, through the tests' own harness (stress/test_voice_real_speech.py), how
   often the app hears nothing at all, and how often the word itself, with four paddings:
   as the tests feed it (0.5 s of digital silence before), none before, 0.5 s of quiet room
   noise each side, 1 s of it each side.
2. The clips themselves: how loud, how long the speech in them, how near the edges it is.
3. The speech model alone on read sentences: word error rate of the open recognizer on the
   first recordings of the FLEURS hour, against FLEURS's transcripts.

    python stress/tools/diag_clips.py WORD,WORD,...
"""

import math
import os
import random
import re
import sys
import time
import unicodedata
import wave
from array import array
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import test_voice_real_speech as h  # noqa: E402

PER_WORD = int(os.environ.get("DIAG_PER_WORD", "25"))
words = sys.argv[1].split(",")
root = Path(os.environ["COMMAND_WORDS_DIR"])
random.seed(7)
NOISE = array("h", (max(-32768, min(32767, int(random.gauss(0, 25)))) for _ in range(16000))).tobytes()  # ~-62 dBFS


def noise(seconds):
    n = int(seconds * 16000) * 2
    return (NOISE * (n // len(NOISE) + 1))[:n]


def hear(pcm, lead):
    listener, heard = h._listener()
    recs = h._start(listener, heard)
    h._feed(listener, recs, lead + pcm)
    for _ in range(60):
        if heard:
            break
        listener.hear(recs, h.QUIET)
    return list(heard)


VARIANTS = {
    "as tested (0.5 s silence before)": lambda pcm: hear(pcm, h.QUIET * 5),
    "nothing before": lambda pcm: hear(pcm, b""),
    "0.5 s room noise each side": lambda pcm: hear(pcm + noise(0.5), noise(0.5)),
    "1 s room noise each side": lambda pcm: hear(pcm + noise(1.0), noise(1.0)),
}


def stats(pcm):
    s = array("h")
    s.frombytes(pcm)
    n = 160
    peaks = [max(map(abs, s[i:i + n]), default=0) for i in range(0, len(s), n)]
    loud = max(peaks, default=0)
    on = [i for i, p in enumerate(peaks) if p >= loud / 10]
    first, last = (on[0], on[-1]) if on else (0, 0)
    return (20 * math.log10(max(loud, 1) / 32768), (last - first + 1) * n / 16000, first * n / 16000,
            (len(peaks) - 1 - last) * n / 16000)


jobs = [(w, f) for w in words if (root / w).is_dir() for f in h._pick(root / w)[:PER_WORD]]
pcms = {f: h._read(f) for _, f in jobs}
print(f"\n== {h.LANG.english_name}: {len(jobs)} clips of {len({w for w, _ in jobs})} words, {Path(h.MODEL).name}")
st = [stats(p) for p in pcms.values()]
med = lambda xs: sorted(xs)[len(xs) // 2]  # noqa: E731
print(f"clips: peak median {med([s[0] for s in st]):.1f} dBFS; speech median {med([s[1] for s in st]):.2f} s; "
      f"starts a median {med([s[2] for s in st]):.2f} s in, ends {med([s[3] for s in st]):.2f} s before the end; "
      f"speech within 50 ms of an edge: {sum(s[2] < 0.05 or s[3] < 0.05 for s in st)}/{len(st)}")
for name, fn in VARIANTS.items():
    started = time.monotonic()
    with ThreadPoolExecutor(h.WORKERS) as pool:
        heard = list(pool.map(lambda job: fn(pcms[job[1]]), jobs))
    nothing, itself = Counter(), Counter()
    tries = Counter(w for w, _ in jobs)
    for (w, _), got in zip(jobs, heard):
        nothing[w] += not got
        itself[w] += h._heard_word(got, w)
    total = len(jobs)
    print(f"{name}: heard nothing {sum(nothing.values())}/{total} ({sum(nothing.values()) / total:.0%}), "
          f"the word itself {sum(itself.values())}/{total} ({sum(itself.values()) / total:.0%}) "
          f"[{time.monotonic() - started:.0f} s]. Per word, nothing/itself: "
          + ", ".join(f"{w} {nothing[w]}/{itself[w]} of {tries[w]}" for w in tries))


# 3. The open recognizer alone on read sentences
def plain(text):
    text = unicodedata.normalize("NFC", text.lower())
    return re.sub(r"[^\w\s]", " ", text).split()


def errors(ref, hyp):
    d = list(range(len(hyp) + 1))
    for i, r in enumerate(ref, 1):
        prev, d[0] = d[0], i
        for j, x in enumerate(hyp, 1):
            prev, d[j] = d[j], min(d[j] + 1, d[j - 1] + 1, prev + (r != x))
    return d[-1]


talk = Path(os.environ["TALK_DIR"])
said = dict(line.partition(" ")[::2] for line in (talk / "transcripts.txt").read_text(encoding="utf-8").splitlines()
            if line)
files = sorted(talk.glob("*/*.wav"))[:int(os.environ.get("WER_FILES", "100"))]


def transcribe(path):
    import json

    import vosk
    rec = vosk.KaldiRecognizer(h._listener()[0].load_model(), 16000)
    pcm = h.QUIET * 3 + h._read(path) + h.QUIET * 10
    out = []
    for i in range(0, len(pcm), 3200):
        if rec.AcceptWaveform(pcm[i:i + 3200]):
            out.append(json.loads(rec.Result())["text"])
    out.append(json.loads(rec.FinalResult())["text"])
    return " ".join(t for t in out if t)


started = time.monotonic()
with ThreadPoolExecutor(h.WORKERS) as pool:
    hyps = list(pool.map(transcribe, files))
ref_words = err = empty = 0
for path, hyp in zip(files, hyps):
    ref = plain(said.get(path.stem, ""))
    ref_words += len(ref)
    err += errors(ref, plain(hyp))
    empty += not hyp.strip()
print(f"FLEURS, the open recognizer alone on {len(files)} recordings ({ref_words} words): word error rate "
      f"{err / max(ref_words, 1):.1%}; {empty} heard as nothing [{time.monotonic() - started:.0f} s]. "
      f"e.g. “{said.get(files[0].stem, '')[:80]}” → “{hyps[0][:80]}”")
