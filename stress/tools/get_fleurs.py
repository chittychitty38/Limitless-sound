"""Fetch an hour of people reading aloud in another language, for stress/test_voice_real_speech.py.

    python stress/tools/get_fleurs.py OUT_DIR [--lang es_419] [--minutes 60]

Makes OUT_DIR/<reader>/*.wav (16 kHz mono 16-bit) and OUT_DIR/transcripts.txt, laid out as
get_real_speech.py lays out LibriSpeech, so the same test reads either. The English hour is
LibriSpeech; this is the same for languages LibriSpeech doesn't have.

The recordings are FLEURS (Conneau et al., 2022, Google): sentences from Wikipedia read aloud
by native speakers, about 12 hours a language. Spanish is es_419, Latin American Spanish.
Its first split in the archive, dev, is taken in archive order until there's an hour, so it's
the same hour every time; that reads about 120 MB of the 2.3 GB archive. FLEURS doesn't say
who read what, so the hour is cut into 40 stretches of about a minute and a half, each heard
as one person reading, as LibriSpeech's 40 readers are. Licensed CC BY 4.0. Never commit it.
Needs `pip install numpy soundfile` (FLEURS's WAV files are 32-bit float).
"""

import argparse
import io
import shutil
import sys
import tarfile
import time
import urllib.request
import wave
from pathlib import Path

URL = "https://storage.googleapis.com/xtreme_translations/FLEURS102/{lang}.tar.gz"
READERS = 40


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("out", type=Path)
    ap.add_argument("--lang", default="es_419", help="FLEURS language (default es_419)")
    ap.add_argument("--minutes", type=float, default=60, help="how much to keep (default 60)")
    args = ap.parse_args()
    url = URL.format(lang=args.lang)
    for attempt in range(4):
        try:
            clips, said = fetch(url, args.minutes * 60)
            break
        except OSError as e:
            print(f"  {url}: {e}", flush=True)
            time.sleep(5 * (attempt + 1))
    else:
        sys.exit(f"couldn't download {url}")

    shutil.rmtree(args.out, ignore_errors=True)
    total = sum(len(pcm) for _, pcm in clips) / 2 / 16000
    each, have, reader, lines = total / READERS, 0.0, 0, []
    for name, pcm in clips:
        if have >= each * (reader + 1) and reader < READERS - 1:
            reader += 1
        path = args.out / f"r{reader + 1:02d}" / f"{name}.wav"
        path.parent.mkdir(parents=True, exist_ok=True)
        with wave.open(str(path), "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(16000)
            w.writeframes(pcm)
        have += len(pcm) / 2 / 16000
        lines.append(f"{name} {said.get(name, '')}")
    (args.out / "transcripts.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"FLEURS {args.lang}: {len(clips)} recordings, {reader + 1} readers, {total / 60:.1f} minutes in {args.out}")


def fetch(url, seconds):
    """[(name, 16-bit 16 kHz mono PCM)] in archive order until there's enough, and what each says."""
    import numpy as np
    import soundfile

    print(f"downloading {url}", flush=True)
    clips, said, have, split = [], {}, 0.0, None
    with urllib.request.urlopen(url, timeout=60) as resp, tarfile.open(fileobj=resp, mode="r|gz") as tar:
        for member in tar:
            parts = member.name.split("/")
            if member.name.endswith(".tsv"):
                for line in tar.extractfile(member).read().decode("utf-8").splitlines():
                    cols = line.split("\t")
                    if len(cols) > 2:
                        said[cols[1].removesuffix(".wav")] = cols[2]
            elif member.isfile() and member.name.endswith(".wav") and len(parts) >= 4:
                split = split or parts[-2]
                if parts[-2] != split:
                    break   # only the first split: the same hour every time
                # FLEURS is 16 kHz mono, as 32-bit floats
                audio, rate = soundfile.read(io.BytesIO(tar.extractfile(member).read()), dtype="float64")
                if rate != 16000 or audio.ndim != 1:
                    sys.exit(f"{member.name}: expected 16 kHz mono, got {rate} Hz {audio.shape}")
                pcm = np.clip(np.round(audio * 32767), -32768, 32767).astype("<i2").tobytes()
                clips.append((parts[-1].removesuffix(".wav"), pcm))
                have += len(pcm) / 2 / 16000
                if have >= seconds:
                    break
    return clips, said


if __name__ == "__main__":
    main()
