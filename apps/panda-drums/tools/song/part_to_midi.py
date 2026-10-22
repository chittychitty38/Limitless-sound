"""
A part (transcribe_drums.py's JSON) as a standard MIDI file, to play the panda in a DAW: put the
song on an audio track at the start of the project and this file on Panda Drums' track at the
start too, and every note lands on the song's own drums (the notes keep their exact times; the
tempo is the song's click).

    python part_to_midi.py part.json part.mid [bpm]

General MIDI drum notes on channel 10, which Panda Drums' default map plays. No dependencies.
"""

import json
import struct
import sys

PPQ = 960


def vlq(n):
    out = [n & 0x7F]
    n >>= 7
    while n:
        out.append(0x80 | (n & 0x7F))
        n >>= 7
    return bytes(reversed(out))


def main(src, dst, bpm=None):
    part = json.load(open(src))
    # The part's own grid is in sixteenths of its bpm; a half-time part (165 on the click, 82.5
    # in sixteenths) reads naturally at the click's tempo.
    bpm = float(bpm) if bpm else part["bpm"] * (2 if part["bpm"] < 100 else 1)
    tick = lambda sec: int(round(sec * bpm / 60.0 * PPQ))
    events = []
    for t, note, vel in part["notes"]:
        events.append((tick(t), 1, bytes([0x99, note, max(1, min(127, vel))])))
        events.append((tick(t) + PPQ // 8, 0, bytes([0x89, note, 0])))
    events.sort(key=lambda e: (e[0], e[1]))
    track = bytearray()
    track += vlq(0) + b"\xff\x03" + vlq(len(b"Panda Drums")) + b"Panda Drums"
    track += vlq(0) + b"\xff\x51\x03" + struct.pack(">I", int(round(60_000_000 / bpm)))[1:]
    track += vlq(0) + b"\xff\x58\x04\x04\x02\x18\x08"
    now = 0
    for at, _, msg in events:
        track += vlq(at - now) + msg
        now = at
    track += vlq(0) + b"\xff\x2f\x00"
    with open(dst, "wb") as f:
        f.write(b"MThd" + struct.pack(">IHHH", 6, 0, 1, PPQ))
        f.write(b"MTrk" + struct.pack(">I", len(track)) + track)
    print("%d notes at %.3f bpm -> %s" % (len(part["notes"]), bpm, dst))


if __name__ == "__main__":
    main(*sys.argv[1:4])
