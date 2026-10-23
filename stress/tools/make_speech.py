"""Make the spoken clips for the voice stress tests (stress/test_voice_stress.py and
stress/test_zoom_noise.py).

    python stress/tools/make_speech.py OUT_DIR [--zoom es]

Uses the Mac's own voice (`say`) on macOS and espeak-ng elsewhere. Writes 16 kHz
mono WAV files plus commands.json, which lists what each command clip should do.
What it should do comes from running the phrase through Limitless Voice's own
engine as text, so the list never drifts from the command packs. zoom.json does the
same for Limitless Zoom's phrases, from Zoom's own table.

--zoom es makes only zoom.json, in Spanish: every phrase Zoom listens for in Spanish, and two
with "por favor", in a Latin American Spanish voice (espeak-ng's es-419, or Paulina on a Mac).
"""

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(os.environ.get("STRESS_REPO_ROOT") or Path(__file__).resolve().parents[2])
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

ZOOM = [
    "zoom in", "zoom out", "closer", "taller", "shorter", "fit", "zoom to fit", "zoom way in",
    "magnifier", "magnify", "again", "do it again", "preset one", "show panel",
    "zoom in please", "fit please",
]


def speak(text, out: Path, voice=None, language=None):
    """voice: a Mac voice's name; language: espeak-ng's voice for a language ("es-419")."""
    if sys.platform == "darwin":
        cmd = ["say", "-o", str(out), "--data-format=LEI16@16000", "--file-format=WAVE"]
        if voice:
            cmd += ["-v", voice]
        subprocess.run(cmd + [text], check=True)
    else:
        exe = shutil.which("espeak-ng") or shutil.which("espeak")
        subprocess.run([exe, "-s", "150", "-w", str(out)] + (["-v", language] if language else []) + [text], check=True)


def zoom_spanish(out):
    """Every phrase Zoom listens for in Spanish, and two said with "por favor"."""
    sys.path.insert(0, str(ROOT / "apps" / "zoom"))
    from limitless_zoom.voice import SPANISH, without
    zoom = []
    for i, text in enumerate([*SPANISH.phrases, "acercar por favor", "ajustar por favor"]):
        name = f"zoom_es_{i:02d}.wav"
        speak(text, out / name, "Paulina", language="es-419")
        zoom.append({"say": text, "file": name, "expect": SPANISH.phrases[" ".join(without(text.split(), SPANISH.fillers))],
                     "voice": "Paulina" if sys.platform == "darwin" else "es-419"})
    (out / "zoom.json").write_text(json.dumps(zoom, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"{len(zoom)} Zoom command clips in Spanish in {out}")


def main(out_dir, zoom_language=None):
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    if zoom_language == "es":
        return zoom_spanish(out)
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
    if (ROOT / "apps" / "zoom" / "limitless_zoom").is_dir():
        sys.path.insert(0, str(ROOT / "apps" / "zoom"))
        from limitless_zoom.actions import VOICE_PHRASES
        from limitless_zoom.voice import FILLERS
        zoom = []
        for v_i, voice in enumerate(voices):
            for i, text in enumerate(ZOOM):
                name = f"zoom_{v_i}_{i:02d}.wav"
                try:
                    speak(text, out / name, voice)
                except subprocess.CalledProcessError:
                    continue
                phrase = " ".join(w for w in text.split() if w not in FILLERS)
                zoom.append({"say": text, "file": name, "expect": VOICE_PHRASES[phrase], "voice": voice or "default"})
        (out / "zoom.json").write_text(json.dumps(zoom, indent=1))
        print(f"{len(zoom)} Zoom command clips")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[3] if len(sys.argv) > 3 and sys.argv[2] == "--zoom" else None)
