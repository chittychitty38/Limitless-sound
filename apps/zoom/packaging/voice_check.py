"""CI check: speak each phrase with the OS voice, recognise it, compare. Each recording is
also tried with 3 s of silence, and of quiet room noise, around it: the way a command
reaches the recogniser from a quiet microphone, through the gate that skips silence.
Usage: python packaging/voice_check.py MODEL_DIR WAV_DIR"""

import random
import sys
import tempfile
import wave
from array import array
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from limitless_zoom.voice import recognize_file  # noqa: E402

CASES = {"zoom_in": "in", "zoom_out": "out", "taller": "taller", "zoom_to_fit": "fit",
         "magnifier": "magToggle", "again": "again"}
AROUND = {"as recorded": None, "in silence": 0, "in a quiet room": 33}   # noise RMS, 16-bit (-60 dB)


def surround(src, out, noise):
    """The recording with 3 s of silence (or noise) before and after it."""
    with wave.open(str(src), "rb") as w:
        params, rate = w.getparams(), w.getframerate()
        speech = array("h")
        speech.frombytes(w.readframes(w.getnframes()))
    pad = array("h", [0]) * (3 * rate * params.nchannels)
    samples = pad + speech + pad
    rng = random.Random(1)
    for i in range(len(samples)):
        samples[i] = max(-32768, min(32767, samples[i] + int(rng.gauss(0, noise))))
    with wave.open(str(out), "wb") as w:
        w.setparams(params)
        w.writeframes(samples.tobytes())


def main(model_dir, wav_dir):
    import vosk

    vosk.SetLogLevel(-1)
    model = vosk.Model(model_dir)
    failed = []
    with tempfile.TemporaryDirectory() as tmp:
        for around, noise in AROUND.items():
            misses = 0
            for stem, want in CASES.items():
                wav = Path(wav_dir) / f"{stem}.wav"
                if noise is not None:
                    wav, src = Path(tmp) / f"{stem}.wav", wav
                    surround(src, wav, noise)
                text, got = recognize_file(model_dir, wav, model=model)
                misses += got != want
                print(f"{'ok ' if got == want else 'BAD'} {stem} ({around}): heard {text!r} -> {got}")
            if misses > 1:   # synthetic voices are imperfect; allow one miss
                failed.append(around)
    if failed:
        print("Too many misses:", ", ".join(failed))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1], sys.argv[2]))
