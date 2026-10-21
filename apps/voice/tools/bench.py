"""Speech accuracy benchmark: synthetic voices -> recognizers -> engine.

    python tools/bench.py models/vosk-model-small-en-us-0.15 models/other-model

Speaks every case with each available voice (macOS `say`, or espeak-ng
elsewhere), clean and with background noise, feeds the audio through the
same two-recognizer path the app uses, and checks the engine does what the
words should do. Prints a Markdown table (appended to $GITHUB_STEP_SUMMARY on
CI) and writes bench.json.
"""

import argparse
import json
import math
import os
import random
import shutil
import subprocess
import sys
import tempfile
import time
import wave
from array import array
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from limitless_voice.app import command_phrases  # noqa: E402
from limitless_voice.audio import Listener  # noqa: E402
from limitless_voice.engine import Engine  # noqa: E402
from limitless_voice.grammar import DEFAULT_PACK_DIR, load_packs  # noqa: E402
from limitless_voice.platforms.dryrun import DryRunPlatform  # noqa: E402

COMMANDS = [
    ("Logic Pro", "play"), ("Logic Pro", "stop"), ("Logic Pro", "record"),
    ("Logic Pro", "start recording"), ("Logic Pro", "go to start"),
    ("Logic Pro", "go to bar thirty two"), ("Logic Pro", "go to bar one twenty"),
    ("Logic Pro", "go to bar sixty four"), ("Logic Pro", "solo track"), ("Logic Pro", "mute track"),
    ("Logic Pro", "unmute"), ("Logic Pro", "arm track"), ("Logic Pro", "next track"),
    ("Logic Pro", "previous track"), ("Logic Pro", "show the mixer"), ("Logic Pro", "piano roll"),
    ("Logic Pro", "quantize"), ("Logic Pro", "zoom in twice"), ("Logic Pro", "undo"),
    ("Logic Pro", "redo"), ("Logic Pro", "save the project"), ("Logic Pro", "new track"),
    ("Logic Pro", "toggle the metronome"), ("Logic Pro", "cycle"), ("Logic Pro", "what can I say"),
    ("Logic Pro", "press command shift november"), ("Logic Pro", "go to sleep"),
    ("Pro Tools", "play"), ("Pro Tools", "record"), ("Pro Tools", "go to bar thirty two"),
    ("Pro Tools", "nudge right four times"), ("Pro Tools", "solo track"),
    ("Pro Tools", "show the mixer"), ("Pro Tools", "midi editor"), ("Pro Tools", "zoom out"),
    ("Pro Tools", "go to marker three"), ("Pro Tools", "undo"), ("Pro Tools", "save the session"),
    ("Pro Tools", "open Logic"), ("Pro Tools", "start dictation"),
]

# Things a singer or a person in the room might say. None of these may run a command.
NOT_COMMANDS = [
    "I recorded that yesterday", "can you play it back for me later", "this song is about love",
    "let's take a break", "the drummer is late again", "turn it up a little bit",
]

DICTATION = [
    "verse two lead vocal", "the bridge needs more energy", "call the drummer tomorrow morning",
]


def voices():
    if shutil.which("say"):
        out = subprocess.run(["say", "-v", "?"], capture_output=True, text=True).stdout
        have = {line.split()[0] for line in out.splitlines() if " en_" in line and line.split()}
        wanted = ["Samantha", "Daniel", "Karen", "Moira", "Rishi", "Tessa", "Fred", "Alex"]
        return [("say", v) for v in wanted if v in have][:6] or [("say", None)]
    if shutil.which("espeak-ng"):
        return [("espeak", "en-us"), ("espeak", "en-gb")]
    sys.exit("needs macOS `say` or espeak-ng")


def speak(engine, voice, text, tmp):
    wav = Path(tmp) / "s.wav"
    if engine == "say":
        aiff = Path(tmp) / "s.aiff"
        subprocess.run(["say"] + (["-v", voice] if voice else []) + ["-o", str(aiff), text], check=True)
        subprocess.run(["afconvert", "-f", "WAVE", "-d", "LEI16@16000", "-c", "1", str(aiff), str(wav)], check=True)
    else:
        subprocess.run(["espeak-ng", "-v", voice, "-s", "150", "-w", str(wav), text], check=True)
    with wave.open(str(wav)) as wf:
        return wf.getframerate(), wf.readframes(wf.getnframes())


def with_noise(pcm, snr_db, seed):
    """Lower the voice a little and add room noise (a laptop mic across a desk)."""
    rng = random.Random(seed)
    samples = array("h", pcm)
    power = sum(s * s for s in samples) / max(1, len(samples))
    noise_amp = math.sqrt(power / (10 ** (snr_db / 10))) * math.sqrt(3)
    lowpass = 0.0
    out = array("h")
    for s in samples:
        lowpass = 0.7 * lowpass + 0.3 * rng.uniform(-noise_amp, noise_amp) * 1.8
        out.append(max(-32768, min(32767, int(s * 0.7 + lowpass))))
    return out.tobytes()


def pad(rate, pcm):
    silence = b"\0\0" * int(rate * 0.5)
    return silence + pcm + silence * 2


class Run:
    def __init__(self, model, packs):
        self.heard = []
        self.listener = Listener(model, command_phrases(packs), on_text=lambda a, b: self.heard.append((a, b)))
        t = time.time()
        self.listener.load_model()
        self.load_seconds = time.time() - t
        self.audio_seconds = self.cpu_seconds = 0.0

    def transcribe(self, rate, pcm):
        self.heard.clear()
        self.listener._cmd_parts = []
        recs = self.listener._make_recognizers(rate)
        block = int(rate * 0.1) * 2
        t = time.process_time()
        for i in range(0, len(pcm), block):
            self.listener._feed(recs, pcm[i:i + block])
        self.cpu_seconds += time.process_time() - t
        self.audio_seconds += len(pcm) / 2 / rate
        return self.heard[-1] if self.heard else ("", "")


def expected(packs, app, text):
    e = Engine(DryRunPlatform("mac", app=app), packs)
    r = e.handle(text)
    return (r.command.phrases[0] if r.command else r.message, r.params, r.times)


def outcome(packs, app, heard):
    if not any(heard):
        return None
    e = Engine(DryRunPlatform("mac", app=app), packs)
    r = e.handle(*heard)
    if not r.handled:
        return None
    return (r.command.phrases[0] if r.command else r.message, r.params, r.times)


def words_error(ref, hyp):
    a, b = ref.lower().split(), hyp.replace("[unk]", "").lower().split()
    d = list(range(len(b) + 1))
    for i in range(1, len(a) + 1):
        prev, d[0] = d[0], i
        for j in range(1, len(b) + 1):
            prev, d[j] = d[j], min(d[j] + 1, d[j - 1] + 1, prev + (a[i - 1] != b[j - 1]))
    return d[len(b)] / max(1, len(a))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("models", nargs="+")
    ap.add_argument("--out", default="bench.json")
    args = ap.parse_args()

    packs = load_packs([DEFAULT_PACK_DIR], "mac")
    vs = voices()
    conditions = [("clean", None), ("noisy", 12)]
    with tempfile.TemporaryDirectory() as tmp:
        audio = {}
        for engine, voice in vs:
            for text in [t for _, t in COMMANDS] + NOT_COMMANDS + DICTATION:
                rate, pcm = speak(engine, voice, text, tmp)
                for cond, snr in conditions:
                    audio[(voice, text, cond)] = (rate, pad(rate, pcm if snr is None else with_noise(pcm, snr, hash(text) & 0xffff)))

    results = {}
    for model in args.models:
        name = Path(model).name
        run = Run(model, packs)
        res = {"load_seconds": round(run.load_seconds, 1), "misses": [], "false_triggers": []}
        for cond, _ in conditions:
            ok = total = fp = 0
            wer = []
            for _, voice in vs:
                for app, text in COMMANDS:
                    total += 1
                    heard = run.transcribe(*audio[(voice, text, cond)])
                    if outcome(packs, app, heard) == expected(packs, app, text):
                        ok += 1
                    else:
                        res["misses"].append(f"{cond} {voice}: {text!r} heard {heard[0]!r} / {heard[1]!r}")
                for text in NOT_COMMANDS:
                    heard = run.transcribe(*audio[(voice, text, cond)])
                    if outcome(packs, "Logic Pro", heard) is not None:
                        fp += 1
                        res["false_triggers"].append(f"{cond} {voice}: {text!r} heard {heard[0]!r}")
                for text in DICTATION:
                    wer.append(words_error(text, run.transcribe(*audio[(voice, text, cond)])[1]))
            res[cond] = {"commands": ok / total, "false_triggers": fp, "of": len(NOT_COMMANDS) * len(vs),
                         "dictation_wer": sum(wer) / len(wer)}
        res["realtime"] = round(run.cpu_seconds / max(1e-9, run.audio_seconds), 3)
        results[name] = res

    lines = [f"### Speech benchmark ({len(vs)} voices: {', '.join(str(v) for _, v in vs)})", "",
             "| Model | Commands (clean) | Commands (noisy) | False triggers | Dictation word errors (clean / noisy) | CPU per second of audio | Load |",
             "|---|---|---|---|---|---|---|"]
    for name, r in results.items():
        c, n = r["clean"], r["noisy"]
        lines.append(f"| {name} | {c['commands']:.0%} | {n['commands']:.0%} | "
                     f"{c['false_triggers'] + n['false_triggers']} of {c['of'] + n['of']} | "
                     f"{c['dictation_wer']:.0%} / {n['dictation_wer']:.0%} | {r['realtime']:.2f}s | {r['load_seconds']}s |")
    for name, r in results.items():
        lines += ["", f"<details><summary>{name}: {len(r['misses'])} misses, "
                  f"{len(r['false_triggers'])} false triggers</summary>", "", "```"]
        lines += r["misses"] + r["false_triggers"] + ["```", "</details>"]
    report = "\n".join(lines)
    print(report)
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as f:
            f.write(report + "\n")
    Path(args.out).write_text(json.dumps(results, indent=2))
    if os.environ.get("GITHUB_ACTIONS"):
        # annotations can be read back through the checks API, unlike logs
        for name, r in results.items():
            c, n = r["clean"], r["noisy"]
            body = (f"commands clean {c['commands']:.0%}, noisy {n['commands']:.0%}; false triggers "
                    f"{c['false_triggers'] + n['false_triggers']}/{c['of'] + n['of']}; dictation WER "
                    f"{c['dictation_wer']:.0%}/{n['dictation_wer']:.0%}; cpu {r['realtime']:.2f}s/s; "
                    f"load {r['load_seconds']}s%0A" + "%0A".join(r["misses"][:60] + r["false_triggers"]))
            print(f"::notice title=Speech benchmark {name}::{body}")


if __name__ == "__main__":
    main()
