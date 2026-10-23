"""Fetch recordings of real people for stress/test_voice_real_speech.py.

    python stress/tools/get_real_speech.py OUT_DIR [--minutes 60]

Makes two folders of 16 kHz mono WAV files:

  OUT_DIR/speech_commands/<word>/*.wav
      Google Speech Commands v0.02, the official test split: one-second clips of one word
      each, said by thousands of different people on their own phones and laptops.
      All 35 words, so the test can ask both "is a command heard?" and "does a word that
      isn't a command stay quiet?". The small test-set download only has ten of the words
      (the rest are lumped into one "unknown" folder), so this reads the full release and
      keeps the test split. That's a 2.3 GB download, once; CI caches the result.

  OUT_DIR/librispeech/<speaker>/*.wav  and  OUT_DIR/librispeech/transcripts.txt
      About an hour of LibriSpeech dev-clean: 40 people (20 women, 20 men) reading books
      aloud, the same amount from each, taken in file order so it's the same hour every time.

Both are CC BY 4.0: Speech Commands by Pete Warden (Google), LibriSpeech by Vassil
Panayotov, Guoguo Chen, Daniel Povey and Sanjeev Khudanpur. Never commit them.
Needs `pip install soundfile` to read LibriSpeech's FLAC files.
"""

import argparse
import hashlib
import io
import re
import shutil
import sys
import tarfile
import time
import urllib.request
import wave
from collections import defaultdict
from pathlib import Path

# download.tensorflow.org is a Google Cloud Storage bucket whose own name has no HTTPS
# certificate, so it's fetched over HTTPS by its storage address, and by plain HTTP if that fails.
SPEECH_COMMANDS = [
    "https://storage.googleapis.com/download.tensorflow.org/data/speech_commands_v0.02.tar.gz",
    "http://download.tensorflow.org/data/speech_commands_v0.02.tar.gz",
]
LIBRISPEECH = [
    "https://www.openslr.org/resources/12/dev-clean.tar.gz",
    "https://us.openslr.org/resources/12/dev-clean.tar.gz",
    "https://openslr.elda.org/resources/12/dev-clean.tar.gz",
]


def stream_tar(urls, handle):
    """Read a .tar.gz straight off the network, calling handle(name, read) for each file.
    Tries each mirror in turn; a dropped connection starts that file over."""
    for attempt, url in enumerate(urls * 2):
        try:
            print(f"downloading {url}", flush=True)
            started = time.monotonic()
            with urllib.request.urlopen(url, timeout=60) as resp, tarfile.open(fileobj=resp, mode="r|gz") as tar:
                for member in tar:
                    if member.isfile():
                        handle(member.name.removeprefix("./"), lambda m=member: tar.extractfile(m).read())
            print(f"  done in {time.monotonic() - started:.0f} s", flush=True)
            return
        except OSError as e:
            print(f"  failed: {e}", flush=True)
            time.sleep(5 * (attempt + 1))
    sys.exit(f"couldn't download any of {urls}")


def in_test_split(name):
    """Speech Commands' own rule for its test split (input_data.which_set in TensorFlow):
    a hash of the speaker, so one person's clips all land in the same split. Used only to
    skip the other 80% while streaming; testing_list.txt has the final word."""
    speaker = re.sub(r"_nohash_.*$", "", Path(name).name)
    n = int(hashlib.sha1(speaker.encode()).hexdigest(), 16) % (2 ** 27)
    percent = n * (100.0 / (2 ** 27 - 1))
    return 10 <= percent < 20


def speech_commands(out):
    out = out / "speech_commands"
    shutil.rmtree(out, ignore_errors=True)
    kept, listed = set(), set()

    def handle(name, read):
        if name == "testing_list.txt":
            listed.update(read().decode().split())
        elif re.fullmatch(r"[a-z]+/[^/]+\.wav", name) and in_test_split(name):
            path = out / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(read())
            kept.add(name)

    stream_tar(SPEECH_COMMANDS, handle)
    if not listed:
        sys.exit("testing_list.txt wasn't in the Speech Commands download")
    for name in kept - listed:
        (out / name).unlink()
    got = kept & listed
    print(f"Speech Commands: {len(got)} of the {len(listed)} test clips, {len({n.split('/')[0] for n in got})} words")
    if len(got) < 0.9 * len(listed):
        sys.exit("the split rule no longer matches testing_list.txt; read the list first instead")


def librispeech(out, minutes):
    import numpy as np
    import soundfile

    out = out / "librispeech"
    shutil.rmtree(out, ignore_errors=True)
    flac, said = {}, {}

    def handle(name, read):
        if name.endswith(".flac"):
            flac[Path(name).stem] = read()
        elif name.endswith(".trans.txt"):
            for line in read().decode().splitlines():
                utt, _, text = line.partition(" ")
                said[utt] = text.strip()

    stream_tar(LIBRISPEECH, handle)
    by_speaker = defaultdict(list)
    for utt in sorted(flac):
        by_speaker[utt.split("-")[0]].append(utt)
    each = minutes * 60 / len(by_speaker)
    total, lines = 0.0, []
    for speaker, utts in sorted(by_speaker.items()):
        have = 0.0
        for utt in utts:
            if have >= each:
                break
            audio, rate = soundfile.read(io.BytesIO(flac[utt]), dtype="int16")
            if rate != 16000 or audio.ndim != 1:
                sys.exit(f"{utt}: expected 16 kHz mono, got {rate} Hz {audio.shape}")
            path = out / speaker / f"{utt}.wav"
            path.parent.mkdir(parents=True, exist_ok=True)
            with wave.open(str(path), "wb") as w:
                w.setnchannels(1)
                w.setsampwidth(2)
                w.setframerate(rate)
                w.writeframes(np.ascontiguousarray(audio).tobytes())
            have += len(audio) / rate
            lines.append(f"{utt} {said.get(utt, '')}")
        total += have
    (out / "transcripts.txt").write_text("\n".join(lines) + "\n")
    print(f"LibriSpeech: {len(lines)} utterances, {len(by_speaker)} people, {total / 60:.1f} minutes")


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("out", type=Path)
    ap.add_argument("--minutes", type=float, default=60, help="how much LibriSpeech to keep (default 60)")
    ap.add_argument("--only", choices=["speech_commands", "librispeech"])
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    if args.only != "librispeech":
        speech_commands(args.out)
    if args.only != "speech_commands":
        librispeech(args.out, args.minutes)


if __name__ == "__main__":
    main()
