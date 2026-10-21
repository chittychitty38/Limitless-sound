"""Make the spoken clips for the voice stress tests (stress/test_voice_stress.py).

    python stress/tools/make_speech.py OUT_DIR

Uses the Mac's own voice (`say`) on macOS and espeak-ng elsewhere. Writes 16 kHz
mono WAV files plus commands.json, which lists what each command clip should do.
What it should do comes from running the phrase through Limitless Voice's own
engine as text, so the list never drifts from the command packs.
"""

import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "apps" / "voice"))

from limitless_voice.engine import Engine  # noqa: E402
from limitless_voice.grammar import DEFAULT_PACK_DIR, load_packs  # noqa: E402
from limitless_voice.platforms.dryrun import DryRunPlatform  # noqa: E402

COMMANDS = [
    "record", "play", "stop", "undo", "redo", "save", "go to start", "go to bar thirty two",
    "show the mixer", "solo the track", "mute the track", "new audio track", "zoom in", "zoom out",
    "metronome", "cycle", "go to sleep", "next track", "previous track", "delete",
]
CHATTER = [
    "can you turn me up a little in the headphones", "let's do that one more time from the top",
    "i think the second verse was better", "hang on i need some water", "the snare sounds a bit dull",
    "that was a good take", "can we record the bridge next week", "is the click too loud for you",
    "i messed up the last bar again", "do you want a coffee before we start", "my phone keeps ringing",
    "the guitar is a little out of tune", "let me stretch my hands for a minute",
]


def speak(text, out: Path, voice=None):
    if sys.platform == "darwin":
        cmd = ["say", "-o", str(out), "--data-format=LEI16@16000", "--file-format=WAVE"]
        if voice:
            cmd += ["-v", voice]
        subprocess.run(cmd + [text], check=True)
    else:
        exe = shutil.which("espeak-ng") or shutil.which("espeak")
        subprocess.run([exe, "-s", "150", "-w", str(out), text], check=True)


def main(out_dir):
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    packs = load_packs([DEFAULT_PACK_DIR], "mac")
    manifest = []
    voices = [None, "Samantha", "Daniel"] if sys.platform == "darwin" else [None]
    for v_i, voice in enumerate(voices):
        for i, text in enumerate(COMMANDS):
            e = Engine(DryRunPlatform("mac", app="Logic Pro"), packs, own_names=["Limitless Voice"])
            expect = e.handle(text, text).message
            name = f"cmd_{v_i}_{i:02d}.wav"
            try:
                speak(text, out / name, voice)
            except subprocess.CalledProcessError:
                continue  # that voice isn't installed on this Mac
            manifest.append({"say": text, "file": name, "expect": expect, "voice": voice or "default"})
    for i, text in enumerate(CHATTER):
        speak(text, out / f"chatter_{i:02d}.wav")
    (out / "commands.json").write_text(json.dumps(manifest, indent=1))
    print(f"{len(manifest)} command clips and {len(CHATTER)} chatter clips in {out}")


if __name__ == "__main__":
    main(sys.argv[1])
