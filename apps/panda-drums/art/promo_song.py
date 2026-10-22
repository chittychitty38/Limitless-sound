"""
The Panda Drums promo cut to a song: the panda plays the song's own drum part (transcribed and
played through the plugin), the song is the soundtrack, and the cut and the captions land on its
bars. The captions, cards and badges are the GUI pack's pieces (promo.py's).

    PandaDrumsRender songpromo <notes.json> <script.json> <dir>       the plugin playing the part
    python promo_song.py <dir> <hero.png> <song audio> <out.mp4>      this: the 1920 x 1080 video

The cut below is for "This Sucks" (165 bpm, half-time, C major): the title over its sung intro,
the panda coming in with the band on its first crash, the features through the verse, and the
whole first chorus. Needs numpy, Pillow and ffmpeg.
"""

import json
import os
import subprocess
import sys
import wave

import numpy as np
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import promo as P  # noqa: E402

W, H, FPS, SR = P.W, P.H, P.FPS, P.SR
INTRO = 7.0          # the title over the song's intro, then the plugin
FADE = 4.0           # the song fades under the end card


def cut_list(tl):
    """(start, end, shot, caption) in song seconds, on the song's bars (16 steps of its click)."""
    bar = 16 * 60.0 / tl["bpm"] / 2
    b = lambda n: tl["start"] + n * bar
    key = tl["key"].upper()
    cuts = [(INTRO, b(4), "window", "meet"),
            (b(4), b(5), "panda", "midi"),          # the band comes in: so does he
            (b(5), b(6), "stage", "beat"),
            (b(6), b(7), "hits", "rr"),
            (b(7), 22.9, "stage", None),
            (22.9, 24.6, "key", "pick"),
            (24.6, b(9), "card", "key"),
            (b(9), b(10), "tiles", ("tuned", key)),
            (b(10), b(11), "page", ("page", "lab")),
            (b(11), b(12), "page", ("page", "mixer")),
            (b(12), b(13), "page", ("page", "mapping")),
            (b(13), b(14), "stage", "showtime"),
            (b(14), b(15), "panda", "lands"),
            (b(15), b(16), "hits", None),
            (b(16), b(17), "stage", "feel"),
            (b(17), b(18), "panda", None),
            (b(18), b(19), "window", None),
            (b(19), b(20), "panda", "fill"),
            (b(20), b(21), "stage", None),
            (b(21), b(22), "stage", "rock"),        # the chorus
            (b(22), b(23), "panda", None),
            (b(23), b(24), "hits", None),
            (b(24), b(25), "stage", None),
            (b(25), b(26), "panda", "anysong"),
            (b(26), b(27), "window", None),
            (b(27), b(28), "stage", None),
            (b(28), b(29), "panda", None),
            (b(29), tl["end"] + 1, "stage", "end")]
    return cuts


def kick_punch(tl, t):
    p = 0.0
    for k in tl["kicks"]:
        if 0 <= t - k < 0.3:
            p = max(p, 0.02 * np.exp(-(t - k) / 0.09))
    return p


def draw_frame(tl, t, i, d, hero, cuts):
    if t < INTRO:
        return P.intro_frame(t, hero)
    start, end, shot, cap = next((c for c in cuts if c[0] <= t < c[1]), cuts[-1])
    k = (t - start) / max(0.01, end - start)
    # The frame showing the plugin at this moment (numbered by the plugin's own frames).
    path = os.path.join(d, "frames", "%05d.jpg" % max(1, i))
    src = Image.open(path).convert("RGB")
    punch = kick_punch(tl, t)
    if shot in ("window", "page", "card"):
        canvas = P.background(t)
        if shot == "card":
            P.place(canvas, P.window_card(src, 1180), 1290, 560)
        else:
            w = int(1480 * (1.0 + 0.05 * P.ease_in_out(k) + punch * 0.5))
            P.place(canvas, P.window_card(src, w), W / 2 + (130 if shot == "page" else 0), H / 2 + 30)
    else:
        canvas = P.shot_picture(src, shot, k, punch)

    def lower(line, accent=None, appear=0.0, y=960):
        a = P.ease_out((t - start - appear) / 0.25)
        if a > 0:
            P.place(canvas, P.caption_card(line, accent), W / 2, y + 40 * (1 - a), 1.0, a)

    kind = cap[0] if isinstance(cap, tuple) else cap
    if kind == "meet":
        lower("MEET THE DRUMMER.", "DRUMMER", 0.3)
    elif kind == "midi":
        lower("HE PLAYS EVERY HIT OF YOUR MIDI.", "EVERY HIT", 0.15)
    elif kind == "beat":
        lower("EVERY STROKE LANDS ON THE BEAT.", "ON THE BEAT", 0.1)
    elif kind == "rr":
        for n, (piece, label, value, colour) in enumerate((("readout_hit", "ROUND ROBIN", "2 / 3", P.TEXT),
                                                          ("readout_midi", "VELOCITY", "112", P.YELLOW),
                                                          ("readout_zone", "ZONE", "5 / 5", P.TEAL))):
            kk = (t - start - 0.25 - n * 0.22) / 0.3
            if kk > 0:
                P.place(canvas, P.feature_readout(piece, label, value, colour), 1520, 470 + n * 108, P.pop(kk), P.clamp(kk * 3))
        lower("ON EVERY HIT. CATCH THE WEIRD ONE.", "EVERY HIT", 0.9)
    elif kind == "pick":
        lower("PICK YOUR SONG'S KEY.", "KEY", 0.1, y=990)
    elif kind == "key":
        kk = (t - start) / 0.4
        P.place(canvas, P.text("CHROMATIC DRUMS", 38, P.PINK), 80, 180, 1.0, P.ease_out(kk), "l")
        pill = P.key_pill(tl["key"])
        P.place(canvas, pill, 80 + pill.width / 2 - 60 - 50 * (1 - P.ease_out(kk)), 270, P.pop(kk), P.clamp(kk * 3))
        y = 390
        for n, (drum, pitch) in enumerate(list(tl["pitches"].items())[:5]):
            a = P.ease_out((t - start - 0.15 - 0.07 * n) / 0.25)
            P.place(canvas, P.pitch_row(drum, pitch), 90 - 30 * (1 - a), y, 1.0, a, "l")
            y += 74
        y = 800
        for line in P.wrap("Every kick, snare and tom tunes itself to the song.", 30, 520):
            P.place(canvas, P.text(line, 30, P.TEXT), 90, y, 1.0, P.ease_out((t - start - 0.6) / 0.3), "l")
            y += 42
    elif kind == "tuned":
        lower("THE WHOLE KIT, IN %s." % cap[1], cap[1], 0.1, y=120)
    elif kind == "page":
        page = cap[1]
        kk = (t - start) / 0.35
        P.place(canvas, P.tab_badge(page), 250 - 60 * (1 - P.ease_out(kk)), 150, P.pop(kk), P.clamp(kk * 3))
        line, accent = {"lab": ("VELOCITY + ROUND ROBIN LAB.", "ROUND ROBIN"), "mixer": ("A CHANNEL FOR EVERY MIC.", "EVERY MIC"),
                        "mapping": ("GM, SUPERIOR, EZDRUMMER, V-DRUMS. OR YOUR PADS.", "YOUR PADS")}[page]
        lower(line, accent, 0.15, y=1005)
    elif kind == "showtime":
        lower("SHOWTIME: HE SEES EVERY HIT COMING.", "SHOWTIME", 0.1)
    elif kind == "lands":
        lower("AND LANDS IT RIGHT ON THE BEAT.", "ON THE BEAT", 0.1)
    elif kind == "feel":
        lower("OPEN HATS. GHOST NOTES. THE GROOVE.", "THE GROOVE", 0.1)
    elif kind == "fill":
        lower("FILLS DOWN THE TOMS.", "FILLS", 0.1)
    elif kind == "rock":
        lower("A BIG ROCK KIT. A REAL DRUMMER'S HANDS.", "REAL DRUMMER'S", 0.1)
    elif kind == "anysong":
        lower("IN KEY WITH ANY SONG.", "ANY SONG", 0.1)
    elif kind == "end":
        tl2 = dict(tl, end=start - 0.9)          # the end card comes in right on the crash
        P.outro(tl2, t, canvas)
    return canvas


def song_audio(song, total, out_wav):
    """The song itself, from its first second to the end card, fading out under it."""
    raw = subprocess.run(["ffmpeg", "-loglevel", "error", "-i", song, "-t", "%.3f" % total, "-ar", str(SR), "-ac", "2",
                          "-f", "s16le", "-"], capture_output=True, check=True).stdout
    a = np.frombuffer(raw, np.int16).reshape(-1, 2).astype(np.float32) / 32768
    n = int(total * SR)
    a = np.pad(a, ((0, max(0, n - len(a))), (0, 0)))[:n]
    tt = np.arange(n) / SR
    a *= np.clip((total - tt) / FADE, 0, 1)[:, None] ** 1.5
    with wave.open(out_wav, "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes((a * 32767).clip(-32768, 32767).astype(np.int16).tobytes())


def main(d, hero_path, song, out):
    P.BG = P.make_bg()
    with open(os.path.join(d, "timeline.json")) as f:
        tl = json.load(f)
    hero = Image.open(hero_path).convert("RGBA")
    hero = hero.resize((W, int(hero.height * W / hero.width)), Image.LANCZOS)
    if hero.height > H:
        top = (hero.height - H) // 2
        hero = hero.crop((0, top, W, top + H))
    cuts = cut_list(tl)
    total = tl["end"]
    frames = int(total * FPS)
    only = os.environ.get("PROMO_FRAMES")        # "a-b": just those frames, as JPEGs named after out (to check a cut)
    if only:
        lo, hi = (int(v) for v in only.split("-"))
        for i in range(lo, min(hi, frames)):
            draw_frame(tl, i / FPS, i, d, hero, cuts).convert("RGB").save("%s.%05d.jpg" % (out, i), quality=88)
        return
    wav = os.path.join(d, "promo_song.wav")
    song_audio(song, total, wav)
    ff = subprocess.Popen(["ffmpeg", "-loglevel", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", "%dx%d" % (W, H),
                           "-r", str(FPS), "-i", "-", "-i", wav, "-c:v", "libx264", "-preset", "slow", "-crf", "17",
                           "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "256k", "-shortest", "-movflags", "+faststart", out],
                          stdin=subprocess.PIPE)
    for i in range(frames):
        t = i / FPS
        canvas = draw_frame(tl, t, i, d, hero, cuts)
        fade = min(P.clamp(t / 0.4), P.clamp((total - t) / 0.6))
        if fade < 1:
            canvas = Image.blend(Image.new("RGBA", (W, H), (0, 0, 0, 255)), canvas, fade)
        ff.stdin.write(canvas.convert("RGB").tobytes())
        if i % 300 == 0:
            print("frame", i, "/", frames, flush=True)
    ff.stdin.close()
    ff.wait()
    print("wrote", out)


if __name__ == "__main__":
    main(*sys.argv[1:5])
