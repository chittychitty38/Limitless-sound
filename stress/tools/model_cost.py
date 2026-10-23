"""Diag only (branch diag/vosk-model, never merged): what a Vosk model costs Voice and Zoom.

    python model_cost.py voice MODEL --repo VOICE_CHECKOUT --talk LIBRISPEECH_DIR [--open-model BIG]
    python model_cost.py zoom  MODEL --repo ZOOM_CHECKOUT  --talk LIBRISPEECH_DIR

Each call is one fresh process holding the model the way the app does, so its peak memory is
what an app process needs for speech. It prints, on lines starting "COST":

  size on disk, and whether the model takes a grammar at run time (HCLr.fst + Gr.fst)
  words the app listens for that the model doesn't know (they can never be heard)
  model load time
  recognizer build time: Voice's open and command recognizers, Zoom's one
  decode CPU seconds per second of audio: people reading aloud, and a quiet room
  memory: after loading, after building, and the peak

--open-model gives Voice's open recognizer a second model (the big one, which can't take a
grammar) while its command recognizer keeps MODEL.
"""

from __future__ import annotations

import argparse
import json
from importlib import metadata
import platform
import resource
import statistics
import sys
import time
import wave
from pathlib import Path

RATE = 16000
BLOCK = RATE // 10                  # 100 ms, what the apps take from the mic at a time
PAUSE = b"\0\0" * (RATE // 10 * 5)  # half a second between sentences, as the tests leave
BUILDS = 10                         # timed builds after the first


def rss_mb():
    import psutil
    return psutil.Process().memory_info().rss / 1e6


def peak_mb():
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024 / 1e6   # Linux: KiB


def size_mb(path):
    return sum(f.stat().st_size for f in Path(path).rglob("*") if f.is_file()) / 1e6


def graph_kind(path):
    g = Path(path) / "graph"
    if (g / "HCLr.fst").exists() and (g / "Gr.fst").exists():
        return "runtime grammar (HCLr.fst + Gr.fst)"
    if (g / "HCLG.fst").exists():
        return "static graph (HCLG.fst): a grammar is ignored"
    return "unknown graph: " + ", ".join(sorted(p.name for p in g.iterdir())) if g.is_dir() else "no graph folder"


def vocabulary(path):
    for cand in [Path(path) / "graph" / "words.txt", *Path(path).rglob("words.txt")]:
        if cand.is_file():
            return {line.split()[0] for line in cand.read_text(errors="replace").splitlines() if line.strip()}
    return None


def talk(folder, seconds):
    """About `seconds` of people reading aloud, a few seconds from each of the first readers in
    turn, with the half-second pause the tests leave between sentences."""
    people = sorted(d for d in Path(folder).iterdir() if d.is_dir())
    each = seconds / 4
    out = bytearray()
    for person in people[:4]:
        have = 0.0
        for f in sorted(person.glob("*.wav")):
            if have >= each:
                break
            with wave.open(str(f)) as w:
                assert (w.getframerate(), w.getnchannels(), w.getsampwidth()) == (RATE, 1, 2), f
                pcm = w.readframes(w.getnframes())
            out += pcm + PAUSE
            have += len(pcm) / 2 / RATE
    return bytes(out)


def quiet_room(seconds):
    """A quiet room through a laptop mic: faint noise around -60 dBFS, not digital silence."""
    import numpy as np
    rng = np.random.default_rng(1)
    return (rng.normal(0, 33, int(seconds * RATE))).clip(-32768, 32767).astype("<i2").tobytes()


def secs(pcm):
    return len(pcm) / 2 / RATE


def timed(label, fn, pcm):
    c0, w0 = time.process_time(), time.perf_counter()
    fn(pcm)
    cpu, wall = time.process_time() - c0, time.perf_counter() - w0
    s = secs(pcm)
    print(f"COST decode {label}: {cpu / s:.3f} CPU s per audio s ({wall / s:.3f} wall), {s:.0f} s of audio, "
          f"{cpu:.1f} CPU s", flush=True)
    return round(cpu / s, 4)


def builds(label, make):
    """The first build after loading, then the median of BUILDS more."""
    t = time.perf_counter()
    make()
    first = time.perf_counter() - t
    times = []
    for _ in range(BUILDS):
        t = time.perf_counter()
        make()
        times.append(time.perf_counter() - t)
    med = statistics.median(times)
    print(f"COST build {label}: first {first * 1000:.0f} ms, then median {med * 1000:.0f} ms "
          f"(min {min(times) * 1000:.0f}, max {max(times) * 1000:.0f})", flush=True)
    return round(first * 1000), round(med * 1000)


def load(path):
    import vosk
    c0, w0 = time.process_time(), time.perf_counter()
    model = vosk.Model(str(path))
    cpu, wall = time.process_time() - c0, time.perf_counter() - w0
    print(f"COST load {Path(path).name}: {wall:.2f} s wall, {cpu:.2f} CPU s; RSS now {rss_mb():.0f} MB", flush=True)
    return model, round(wall, 2)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("app", choices=["voice", "zoom"])
    ap.add_argument("model", type=Path)
    ap.add_argument("--repo", type=Path, required=True, help="checkout whose apps/<app> to use")
    ap.add_argument("--talk", type=Path, required=True, help="LibriSpeech folder from get_real_speech.py")
    ap.add_argument("--open-model", type=Path, help="Voice only: a second model for the open recognizer")
    ap.add_argument("--speech-seconds", type=float, default=120)
    ap.add_argument("--quiet-seconds", type=float, default=60)
    args = ap.parse_args()
    out = {"app": args.app, "model": args.model.name, "open_model": args.open_model.name if args.open_model else None}

    sys.path.insert(0, str(args.repo / "apps" / args.app))
    import vosk
    vosk.SetLogLevel(-1)
    import psutil  # noqa: F401  (imported before the baseline, so it isn't counted as the model's)

    speech, quiet = talk(args.talk, args.speech_seconds), quiet_room(args.quiet_seconds)
    print(f"COST machine: {platform.processor() or platform.machine()}, Python {platform.python_version()}, "
          f"vosk {metadata.version('vosk')}", flush=True)

    if args.app == "voice":
        from limitless_voice.actions import APP_ALIASES
        from limitless_voice.audio import Listener, build_grammar
        from limitless_voice.engine import BUILTIN_PHRASES
        from limitless_voice.grammar import DEFAULT_PACK_DIR, load_packs, recognizer_phrases
        from limitless_voice.keys import spoken_vocabulary
        from limitless_voice.numbers import NUMBER_WORDS
        # The same phrase list as stress/test_voice_real_speech.py (app.command_phrases, with Logic Pro's pack).
        packs = load_packs([DEFAULT_PACK_DIR], "mac")
        phrases = recognizer_phrases(
            packs, BUILTIN_PHRASES | NUMBER_WORDS | spoken_vocabulary() | set(APP_ALIASES) | {"please", "and"})
        grammar_list = build_grammar(phrases)
    else:
        from limitless_zoom.voice import Hearing, grammar
        grammar_list = json.loads(grammar())
    grammar_json = json.dumps(grammar_list)
    words = {w for p in grammar_list for w in p.split() if w != "[unk]"}

    for label, path in (("model", args.model), ("open model", args.open_model)):
        if path is None:
            continue
        vocab = vocabulary(path)
        missing = sorted(words - vocab) if vocab is not None else None
        out[f"{label} size MB"] = round(size_mb(path), 1)
        print(f"COST {label} {path.name}: {size_mb(path):.1f} MB on disk; {graph_kind(path)}; "
              f"vocabulary {len(vocab) if vocab else '?'} words", flush=True)
        if label == "model":
            out["missing"] = missing
            print(f"COST {args.app} listens for {len(grammar_list) - 1} phrases, {len(words)} words; "
                  f"{len(missing) if missing is not None else '?'} unknown to {path.name}: {missing}", flush=True)

    base = rss_mb()
    print(f"COST RSS before any model: {base:.0f} MB (Python, vosk, the app's modules, {secs(speech) + secs(quiet):.0f} s of audio)",
          flush=True)
    model, out["load s"] = load(args.model)
    open_model = model
    if args.open_model:
        open_model, out["open load s"] = load(args.open_model)
    out["RSS after load MB"] = round(rss_mb())

    if args.app == "voice":
        out["build open ms"] = builds("open recognizer", lambda: vosk.KaldiRecognizer(open_model, RATE))
        out["build commands ms"] = builds(f"command recognizer ({len(grammar_list)} phrases)",
                                          lambda: vosk.KaldiRecognizer(model, RATE, grammar_json))
        out["RSS after builds MB"] = round(rss_mb())

        def pair(pcm):
            """Both recognizers, through the app's own Listener._feed."""
            lst = Listener(args.model, phrases, on_text=lambda c, o: None)
            lst._model = model
            recs = {"open": vosk.KaldiRecognizer(open_model, RATE),
                    "commands": vosk.KaldiRecognizer(model, RATE, grammar_json)}
            lst._cmd_parts = []
            for i in range(0, len(pcm), BLOCK * 2):
                lst._feed(recs, pcm[i:i + BLOCK * 2])
            for r in recs.values():
                r.FinalResult()

        def one(make):
            def run(pcm):
                rec = make()
                for i in range(0, len(pcm), BLOCK * 2):
                    if rec.AcceptWaveform(pcm[i:i + BLOCK * 2]):
                        rec.Result()
                rec.FinalResult()
            return run

        out["cpu open speech"] = timed("open recognizer alone, people reading",
                                       one(lambda: vosk.KaldiRecognizer(open_model, RATE)), speech)
        out["cpu commands speech"] = timed("command recognizer alone, people reading",
                                           one(lambda: vosk.KaldiRecognizer(model, RATE, grammar_json)), speech)
        out["cpu voice speech"] = timed("Voice (both, as the app runs them), people reading", pair, speech)
        out["cpu voice quiet"] = timed("Voice (both), a quiet room", pair, quiet)
    else:
        def make():
            rec = vosk.KaldiRecognizer(model, RATE, grammar_json)
            rec.SetWords(True)
            return rec
        out["build zoom ms"] = builds(f"Zoom's recognizer ({len(grammar_list)} phrases)", make)
        out["RSS after builds MB"] = round(rss_mb())

        def gated(pcm):
            """Through Zoom's own Hearing, which skips silence, as the app runs it."""
            from array import array
            hearing = Hearing(make(), lambda res: None)
            samples = array("h", pcm)
            for i in range(0, len(samples), BLOCK):
                hearing.hear(samples[i:i + BLOCK])
            hearing.finish()

        out["cpu zoom speech"] = timed("Zoom (with its gate), people reading", gated, speech)
        out["cpu zoom quiet"] = timed("Zoom (with its gate), a quiet room", gated, quiet)

    out["RSS end MB"] = round(rss_mb())
    out["peak RSS MB"] = round(peak_mb())
    out["RSS before model MB"] = round(base)
    print(f"COST memory: {base:.0f} MB before the model, {out['RSS after load MB']} after loading, "
          f"{out['RSS after builds MB']} after building, {out['RSS end MB']} after decoding; "
          f"peak {out['peak RSS MB']} MB (the model's share: {out['peak RSS MB'] - base:.0f} MB)", flush=True)
    print("COSTJSON " + json.dumps(out), flush=True)


if __name__ == "__main__":
    main()
