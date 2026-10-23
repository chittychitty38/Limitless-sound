"""Temporary: why does the Portuguese model hear nothing in half the clips?"""
import json
import os
import random
import sys
import wave
from pathlib import Path

import vosk

vosk.SetLogLevel(-1)
model_dir = Path(os.environ["VOSK_MODEL"])
words_dir = Path(os.environ["COMMAND_WORDS_DIR"])

print("== layout")
for p in sorted(model_dir.rglob("*")):
    print(" ", p.relative_to(model_dir), p.stat().st_size if p.is_file() else "")
for conf in sorted((model_dir / "conf").glob("*")):
    print("==", conf.name)
    print(conf.read_text(errors="replace"))
readme = model_dir / "README"
if readme.is_file():
    print("== README")
    print(readme.read_text(errors="replace")[:1500])

model = vosk.Model(str(model_dir))
random.seed(1)
NOISE = b"".join(int(random.gauss(0, 20)).to_bytes(2, "little", signed=True) for _ in range(16000))


def run(pcm, quiet):
    rec = vosk.KaldiRecognizer(model, 16000)
    lead = quiet[:16000]                     # 0.5 s
    stream = lead + pcm + quiet * 4          # then 4 s
    end = (len(lead) + len(pcm)) / 32000
    partial_at = None
    for i in range(0, len(stream), 3200):
        t = (i + 3200) / 32000
        if rec.AcceptWaveform(stream[i:i + 3200]):
            return f"{json.loads(rec.Result())['text']!r} ended {t - end:+.1f}s"
        if partial_at is None and t >= end + 1.5:
            partial_at = json.loads(rec.PartialResult())["partial"]
    return f"final {json.loads(rec.FinalResult())['text']!r} (partial at +1.5 s {partial_at!r})"


for w in ["não", "três", "uma", "volta", "dez", "toca", "parte", "aqui"]:
    clips = sorted((words_dir / w).glob("*.wav"))[:8]
    print(f"== {w}")
    for f in clips:
        with wave.open(str(f)) as wf:
            pcm = wf.readframes(wf.getnframes())
        print(f"  {f.name[:20]:<20} zeros: {run(pcm, bytes(32000))}")
        print(f"  {'':<20} noise: {run(pcm, NOISE * 2)}")
sys.stdout.flush()
