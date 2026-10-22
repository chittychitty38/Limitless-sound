"""
The Panda Drums promo video: titles, captions and key badges over the panda playing through
five keys, with a pad and bass that follow the same keys so you hear the drums sit in them.

    PandaDrumsRender promo <dir>                          the performance: frames, drums, timeline
    python promo.py <dir> <hero.png> <out.mp4>            this: the finished 1920 x 1080 video

Needs numpy, Pillow and ffmpeg. Fonts come from ../Resources/fonts.
"""

import json
import math
import os
import subprocess
import sys
import wave

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
FONTS = os.path.join(HERE, "..", "Resources", "fonts")
W, H, FPS, SR = 1920, 1080, 30, 48000
BRAND = "PURAFIED"

PLUM, PLUM_LIGHT, INK = (36, 16, 41), (58, 29, 68), (21, 16, 22)
HOT, PINK, CREAM, GOLD, MINT, TEXT_DIM = (255, 79, 163), (243, 182, 214), (251, 242, 220), (255, 200, 69), (62, 224, 196), (199, 169, 201)


def font(name, size):
    return ImageFont.truetype(os.path.join(FONTS, {"display": "Anton-Regular.ttf", "title": "LilitaOne-Regular.ttf",
                                                   "body": "VarelaRound-Regular.ttf"}[name]), size)


# ---------------------------------------------------------------------------- easing and drawing
def clamp(x, a=0.0, b=1.0):
    return max(a, min(b, x))


def ease_out(t):
    t = clamp(t)
    return 1 - (1 - t) ** 3


def ease_in_out(t):
    t = clamp(t)
    return t * t * (3 - 2 * t)


def pop(t):
    """0 -> overshoot -> 1 over t in 0..1 (a sticker landing)."""
    t = clamp(t)
    return 1 + 2.2 * (t - 1) ** 3 + 1.2 * (t - 1) ** 2 if t < 1 else 1.0


_text_cache = {}


def text(s, face, size, fill, stroke=0, stroke_fill=INK, shadow=True, tracking=0):
    """A line of text as an RGBA image, with an outline and a soft drop shadow."""
    key = (s, face, size, fill, stroke, stroke_fill, shadow, tracking)
    if key in _text_cache:
        return _text_cache[key]
    f = font(face, size)
    pad = stroke + 24
    widths = [f.getlength(ch) + tracking for ch in s] if tracking else [f.getlength(s)]
    w = int(sum(widths)) + pad * 2
    asc, desc = f.getmetrics()
    h = asc + desc + pad * 2
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    if tracking:
        x = pad
        for ch, cw in zip(s, widths):
            d.text((x, pad), ch, font=f, fill=fill, stroke_width=stroke, stroke_fill=stroke_fill)
            x += cw
    else:
        d.text((pad, pad), s, font=f, fill=fill, stroke_width=stroke, stroke_fill=stroke_fill)
    if shadow:
        a = img.getchannel("A").filter(ImageFilter.GaussianBlur(8))
        sh = Image.new("RGBA", img.size, (0, 0, 0, 0))
        sh.putalpha(a.point(lambda v: int(v * 0.55)))
        out = Image.new("RGBA", img.size, (0, 0, 0, 0))
        out.alpha_composite(sh, (0, 6))
        out.alpha_composite(img)
        img = out
    _text_cache[key] = img
    return img


def wrap(s, face, size, width):
    """Split s into lines no wider than width."""
    f = font(face, size)
    lines, line = [], ""
    for word in s.split():
        trial = (line + " " + word).strip()
        if f.getlength(trial) > width and line:
            lines.append(line)
            line = word
        else:
            line = trial
    return lines + [line] if line else lines


def paragraph(canvas, s, x, y, alpha=1.0, size=34, colour=CREAM, gap=1.25):
    """Left-aligned wrapped text in the caption column; returns the y under it."""
    for line in wrap(s, "body", size, CAPTION_W):
        place(canvas, text(line, "body", size, colour), x, y, 1.0, alpha, "l")
        y += size * gap
    return y


def place(canvas, img, cx, cy, scale=1.0, alpha=1.0, anchor="c"):
    """Composite img centred (or left-aligned with anchor 'l') at (cx, cy)."""
    if alpha <= 0.01 or scale <= 0.01:
        return
    if abs(scale - 1.0) > 1e-3:
        img = img.resize((max(1, int(img.width * scale)), max(1, int(img.height * scale))), Image.LANCZOS)
    if alpha < 0.999:
        img = img.copy()
        img.putalpha(img.getchannel("A").point(lambda v: int(v * alpha)))
    x = int(cx - (0 if anchor == "l" else img.width / 2))
    y = int(cy - img.height / 2)
    canvas.alpha_composite(img, (max(0, x), max(0, y)), (max(0, -x), max(0, -y)))


def background(t):
    """Plum with a slow pink glow and drifting sparkles."""
    base = BG.copy()
    d = ImageDraw.Draw(base)
    rng = np.random.default_rng(3)
    for i in range(70):
        x0, y0, sp, ph = rng.uniform(0, W), rng.uniform(0, H), rng.uniform(8, 30), rng.uniform(0, 6.28)
        x = (x0 + t * sp * 0.6) % W
        y = (y0 - t * sp) % H
        a = int(90 + 80 * math.sin(t * 2 + ph))
        r = 1.5 + (i % 3)
        d.ellipse((x - r, y - r, x + r, y + r), fill=(255, 210, 235, max(0, a)))
    return base


def make_bg():
    y = np.linspace(0, 1, H)[:, None]
    x = np.linspace(0, 1, W)[None, :]
    top, bottom = np.array(PLUM_LIGHT, float), np.array(PLUM, float)
    img = top * (1 - y[..., None]) + bottom * y[..., None]
    glow = np.exp(-(((x - 0.5) / 0.45) ** 2 + ((y - 0.55) / 0.5) ** 2))[..., None]
    img = img * (1 - 0.3 * glow) + np.array(HOT, float) * 0.3 * glow
    img = np.broadcast_to(img, (H, W, 3)).clip(0, 255).astype(np.uint8)
    return Image.fromarray(img, "RGB").convert("RGBA")


def rounded(img, radius):
    mask = Image.new("L", img.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, img.width - 1, img.height - 1), radius, fill=255)
    img = img.convert("RGBA")
    img.putalpha(mask)
    return img


def shadow_for(size, radius, blur=30, alpha=0.55):
    w, h = size
    pad = blur * 3
    sh = Image.new("RGBA", (w + pad * 2, h + pad * 2), (0, 0, 0, 0))
    ImageDraw.Draw(sh).rounded_rectangle((pad, pad + 18, pad + w, pad + h + 18), radius, fill=(10, 0, 12, int(255 * alpha)))
    return sh.filter(ImageFilter.GaussianBlur(blur)), pad


# ---------------------------------------------------------------------------- audio
def read_wav(path):
    with wave.open(path, "rb") as w:
        n, ch, width, sr = w.getnframes(), w.getnchannels(), w.getsampwidth(), w.getframerate()
        raw = np.frombuffer(w.readframes(n), np.uint8)
    if width == 3:
        b = raw.reshape(-1, 3).astype(np.int32)
        v = (b[:, 0] | (b[:, 1] << 8) | (b[:, 2] << 16))
        v = np.where(v & 0x800000, v - 0x1000000, v) / 8388608.0
    else:
        v = np.frombuffer(raw.tobytes(), np.int16) / 32768.0
    return v.reshape(-1, ch).T.astype(np.float64), sr


def chords_for(tl):
    """(start, end, root midi, minor?) for every bar: i VI III VII in minor, I V vi IV in major."""
    bar = 240.0 / tl["bpm"]
    minor_prog, major_prog = [(0, True), (8, False), (3, False), (10, False)], [(0, False), (7, False), (9, True), (5, False)]
    out = [(0.0, tl["intro"], 2, True)]
    secs = tl["sections"]
    tour = [s for s in secs if s["caption"] in ("lab", "mixer", "mapping", "fill")]
    for s in secs:
        n = int(round((s["end"] - s["time"]) / bar))
        prog = major_prog if s["major"] else minor_prog
        if s in tour:
            k = tour.index(s)            # the four one-bar tour sections share one progression
            off, minor = prog[k % 4]
            out.append((s["time"], s["end"], s["root"] + off, minor))
            continue
        if n == 2:
            prog = [prog[0], prog[3]] if s["major"] else [prog[0], prog[1]]
        for b in range(n):
            off, minor = prog[b % len(prog)]
            out.append((s["time"] + b * bar, s["time"] + (b + 1) * bar, s["root"] + off, minor))
    last = secs[-1]
    out.append((tl["end"], tl["total"], last["root"], not last["major"]))
    return out


def synth(tl, length):
    t = np.arange(length) / SR
    pad = np.zeros(length)
    bass = np.zeros(length)
    chords = chords_for(tl)
    rng = np.random.default_rng(5)
    for start, end, root, minor in chords:
        a, b = int(start * SR), min(length, int((end + 0.25) * SR))
        if b <= a:
            continue
        tt = t[a:b] - start
        env = np.minimum(1.0, tt / (0.9 if start == 0.0 else 0.08))
        tail = end + 0.25 - t[a:b]
        env *= np.clip(tail / 0.25, 0, 1)
        if start == 0.0:
            env *= np.clip(tt / 2.2, 0, 1) ** 2          # the intro swells into the title hit
        if end >= tl["total"] - 1e-3:
            env *= np.clip((tl["total"] - t[a:b]) / 2.5, 0, 1)
        third = 3 if minor else 4
        notes = [root % 12 + 57 + i for i in (0, third, 7, 12)]
        notes = [n - 12 if n > 72 else n for n in notes]
        voice = np.zeros(b - a)
        for n in notes:
            f0 = 440.0 * 2 ** ((n - 69) / 12)
            for det in (-0.0035, 0.0035):
                ph = rng.uniform(0, 6.28)
                for k in range(1, 11):
                    voice += np.sin(2 * np.pi * f0 * (1 + det) * k * tt + ph * k) / k ** 1.25
        pad[a:b] += voice * env / 8.0
    # Bass on every kick, on the chord's root.
    kicks = sorted(tl["kicks"])
    for i, k in enumerate(kicks):
        chord = next((c for c in reversed(chords) if c[0] <= k + 0.02), chords[0])
        n = chord[2] % 12 + 33
        f0 = 440.0 * 2 ** ((n - 69) / 12)
        dur = min(0.45, (kicks[i + 1] - k) if i + 1 < len(kicks) else 1.5)
        a, b = int(k * SR), min(length, int((k + dur + 0.05) * SR))
        tt = t[a:b] - k
        env = np.exp(-tt / 0.35) * np.clip(tt / 0.004, 0, 1) * np.clip((dur + 0.05 - tt) / 0.05, 0, 1)
        bass[a:b] += (np.sin(2 * np.pi * f0 * tt) + 0.35 * np.sin(4 * np.pi * f0 * tt) + 0.12 * np.sin(6 * np.pi * f0 * tt)) * env
    # The pad ducks under the kick.
    duck = np.ones(length)
    for k in kicks:
        a = int(k * SR)
        b = min(length, a + int(0.4 * SR))
        duck[a:b] = np.minimum(duck[a:b], 1 - 0.5 * np.exp(-(t[a:b] - k) / 0.12))
    return pad * duck, bass


def mix_audio(d, tl, out_wav):
    drums, sr = read_wav(os.path.join(d, "drums.wav"))
    assert sr == SR
    length = drums.shape[1]
    pad, bass = synth(tl, length)
    # A reversed crash swelling into the title hit.
    hit = int(2.2 * SR)
    crash = drums[:, hit:hit + int(1.4 * SR)][:, ::-1] * np.linspace(0, 1, int(1.4 * SR)) ** 2
    rev = np.zeros_like(drums)
    rev[:, hit - crash.shape[1]:hit] = crash * 0.6
    music = np.vstack([pad * 0.23, pad * 0.26]) + np.vstack([bass, bass]) * 0.26
    out = drums + rev + music
    out = np.tanh(out * 1.1) / np.tanh(1.1)
    out *= 0.89 / max(1e-6, np.abs(out).max())
    pcm = (out.T * 32767).astype(np.int16)
    with wave.open(out_wav, "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm.tobytes())


# ---------------------------------------------------------------------------- the picture
EDITOR = (1920, 1290)                       # the window at 1.5x
FULL = ((0, 90, 1920, 1080), (0, 0, 1920, 1080))
WINDOW = ((0, 0, 1920, 1290), (610, 120, 1260, 847))
CAPTION_W = 500                             # the caption column left of the window


def zoom(cx, cy, z):
    w, h = 1920 / z, 1080 / z
    x, y = clamp(cx - w / 2, 0, 1920 - w), clamp(cy - h / 2, 0, 1290 - h)
    return ((x, y, w, h), (0, 0, 1920, 1080))


def lerp_rect(a, b, k):
    return tuple(x + (y - x) * k for x, y in zip(a, b))


def lerp_layout(a, b, k):
    return lerp_rect(a[0], b[0], k), lerp_rect(a[1], b[1], k)


def layout_at(tl, t):
    """Where the window's picture goes on screen at time t: full bleed on the stage, a card
    beside the captions for the keys and the page tour, zoomed in on the hit pop-ups."""
    bar = 240.0 / tl["bpm"]
    intro = tl["intro"]
    keys = [s for s in tl["sections"] if s["caption"] == "key"]
    tour = [s for s in tl["sections"] if s["caption"] in ("lab", "mixer", "mapping")]
    plan = [(intro, FULL), (intro + 2 * bar, zoom(980, 560, 1.4)), (keys[0]["time"], WINDOW),
            (tour[-1]["end"], FULL)]
    current = plan[0][1]
    for i, (start, lay) in enumerate(plan):
        if t >= start:
            prev = plan[i - 1][1] if i > 0 else lay
            k = ease_in_out((t - start) / 0.5)
            current = lerp_layout(prev, lay, k)
    return current


FLATS = {"C#": "Db", "D#": "Eb", "F#": "Gb", "G#": "Ab", "A#": "Bb"}


def spell(note, root, major):
    """Note names the way the key spells them: flats in C minor, sharps in E major."""
    flat_key = (major and root in (5, 10, 3, 8, 1)) or (not major and root in (0, 2, 5, 7, 10, 3))
    if flat_key and note[:2] in FLATS:
        return FLATS[note[:2]] + note[2:]
    return note


def captions(tl, t, canvas):
    bar = 240.0 / tl["bpm"]
    intro = tl["intro"]
    secs = tl["sections"]

    def lower_third(s, start, end, size=64, colour=CREAM, y=960):
        if start <= t < end:
            a = min(ease_out((t - start) / 0.3), ease_out((end - t) / 0.25))
            img = text(s, "title", size, colour, stroke=6)
            place(canvas, img, W / 2, y + 30 * (1 - a), 1.0, a)

    lower_third("MEET THE DRUMMER.", intro + 0.2, intro + 2.3)
    lower_third("HE PLAYS EVERY HIT OF YOUR MIDI.", intro + 2.4, intro + 2 * bar - 0.1)
    lower_third("ROUND ROBIN + VELOCITY ON EVERY HIT", intro + 2 * bar + 0.4, intro + 4 * bar - 0.3, colour=GOLD)

    keys = [s for s in secs if s["caption"] == "key"]
    lines = ["Pick your song's key.", "Every kick, snare and tom tunes itself.", "The floor tom plays melodies, in key.",
             "No matter what you work on."]
    if keys[0]["time"] - 0.2 <= t < keys[-1]["end"]:
        a = min(ease_out((t - keys[0]["time"] + 0.2) / 0.4), ease_out((keys[-1]["end"] - t) / 0.3))
        place(canvas, text("CHROMATIC", "display", 116, HOT, stroke=8), 60, 230, 1.0, a, "l")
        place(canvas, text("DRUMS IN KEY WITH ANY SONG", "title", 34, CREAM, stroke=4), 66, 315, 1.0, a, "l")
        for i, s in enumerate(keys):
            if s["time"] <= t < s["end"]:
                k = (t - s["time"]) / 0.45
                name = s["key"].upper()
                place(canvas, text("KEY OF", "title", 36, TEXT_DIM, stroke=0), 66, 430, 1.0, a, "l")
                place(canvas, text(name, "display", 104, GOLD if s["major"] else MINT, stroke=8),
                      60 - 40 * (1 - ease_out(k)), 520, pop(k) if k < 1 else 1.0, a * clamp(k * 3), "l")
                y = 640
                for drum, pitch in list(s["pitches"].items())[:5]:
                    row = text("%s  %s" % (drum.upper(), spell(pitch, s["root"], s["major"])), "title", 34, CREAM, stroke=4)
                    place(canvas, row, 66, y, 1.0, a * clamp((t - s["time"] - 0.15 - 0.06 * (y - 640) / 46) / 0.25), "l")
                    y += 46
                paragraph(canvas, lines[i], 66, 900, a * clamp((t - s["time"] - 0.3) / 0.3))

    titles = {"lab": ("THE LAB", "Velocity zones and round robins.", "Find the weird hit. Take it out."),
              "mixer": ("THE MIXER", "A channel for every real mic.", "Open the rooms. Panda FX on every fader."),
              "mapping": ("MAPPING", "Superior Drummer, EZdrummer,", "GM and V-Drums maps. Or learn your pads.")}
    for s in secs:
        if s["caption"] in titles and s["time"] <= t < s["end"]:
            k = (t - s["time"]) / 0.4
            a = min(ease_out(k), ease_out((s["end"] - t) / 0.2) if s["caption"] == "mapping" else 1.0)
            big, l1, l2 = titles[s["caption"]]
            place(canvas, text(big, "display", 104, HOT, stroke=8), 60 - 40 * (1 - ease_out(k)), 400, 1.0, a, "l")
            y = paragraph(canvas, l1, 66, 520, a * clamp(k * 2 - 0.3), size=36)
            paragraph(canvas, l2, 66, y + 10, a * clamp(k * 2 - 0.6), size=36)


def outro(tl, t, canvas):
    start = tl["end"] + 0.9
    if t < start:
        return
    k = t - start
    dim = Image.new("RGBA", (W, H), (20, 6, 24, int(185 * ease_out(k / 0.6))))
    canvas.alpha_composite(dim)
    place(canvas, text("PANDA DRUMS", "display", 190, CREAM, stroke=12), W / 2, 330, pop(k / 0.5), clamp(k / 0.15))
    place(canvas, text("vol. one", "title", 54, HOT, stroke=5), W / 2, 470, 1.0, clamp((k - 0.3) / 0.3))
    place(canvas, text("Chromatic. In key with any song.", "title", 60, GOLD, stroke=6), W / 2, 580, 1.0, clamp((k - 0.6) / 0.3))
    place(canvas, text("AU  ·  VST3  ·  Standalone   |   macOS & Windows", "body", 38, CREAM), W / 2, 680, 1.0, clamp((k - 0.9) / 0.3))
    place(canvas, text(BRAND, "display", 84, PINK, stroke=6, tracking=14), W / 2, 880, 1.0, clamp((k - 1.2) / 0.4))


def intro_frame(t, hero):
    canvas = background(t)
    # PURAFIED presents
    if t < 2.1:
        a = min(ease_out(t / 0.6), clamp((2.05 - t) / 0.25))
        place(canvas, text(BRAND, "display", 180, CREAM, stroke=10, tracking=int(10 + 18 * ease_out(t / 1.6))), W / 2, 470,
              1.0 + 0.04 * t, a)
        place(canvas, text("presents", "title", 52, HOT, stroke=5), W / 2, 640, 1.0, a * clamp((t - 0.7) / 0.4))
    if t >= 2.0:
        k = t - 2.0
        z = 1.12 - 0.12 * ease_out(k / 1.4)
        img = hero.resize((int(hero.width * z), int(hero.height * z)), Image.LANCZOS)
        flash = clamp(1 - (t - 2.2) / 0.25) if t >= 2.2 else 0.0
        img = img.copy()
        img.putalpha(int(255 * clamp(k / 0.2)))
        canvas.alpha_composite(img, (int((W - img.width) / 2), int((H - img.height) / 2)))
        if flash > 0:
            canvas.alpha_composite(Image.new("RGBA", (W, H), (255, 255, 255, int(200 * flash))))
        if t >= 2.2:
            # Dark bands top and bottom for the title and the line under it.
            for y0, y1, h in ((0, 0, 250), (H - 150, 1, 150)):
                grad = np.linspace(160, 0, h) if y1 == 0 else np.linspace(0, 170, h)
                band = Image.new("RGBA", (W, h), (12, 2, 14, 0))
                band.putalpha(Image.fromarray(grad[:, None].repeat(W, 1).astype(np.uint8), "L"))
                canvas.alpha_composite(band, (0, y0))
            place(canvas, text("PANDA DRUMS", "display", 150, CREAM, stroke=10), W / 2, 112, pop((t - 2.2) / 0.45))
            place(canvas, text("CHROMATIC DRUMS  ·  IN KEY WITH ANY SONG", "title", 44, GOLD, stroke=5), W / 2, 1036, 1.0,
                  clamp((t - 2.6) / 0.3))
    return canvas


def main(d, hero_path, out):
    global BG
    BG = make_bg()
    with open(os.path.join(d, "timeline.json")) as f:
        tl = json.load(f)
    wav = os.path.join(d, "promo_mix.wav")
    mix_audio(d, tl, wav)
    hero = Image.open(hero_path).convert("RGBA")
    hero = hero.resize((W, int(hero.height * W / hero.width)), Image.LANCZOS)
    if hero.height > H:
        top = (hero.height - H) // 2
        hero = hero.crop((0, top, W, top + H))
    frames = int(tl["total"] * FPS)
    ff = subprocess.Popen(["ffmpeg", "-loglevel", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", "%dx%d" % (W, H),
                           "-r", str(FPS), "-i", "-", "-i", wav, "-c:v", "libx264", "-preset", "slow", "-crf", "17",
                           "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "256k", "-shortest", "-movflags", "+faststart", out],
                          stdin=subprocess.PIPE)
    window_mask = None
    for i in range(frames):
        t = i / FPS
        if t < tl["intro"]:
            canvas = intro_frame(t, hero)
        else:
            canvas = background(t)
            path = os.path.join(d, "frames", "%04d.jpg" % (i + 1))
            src = Image.open(path).convert("RGB")
            (sx, sy, sw, sh), (dx, dy, dw, dh) = layout_at(tl, t)
            pic = src.crop((int(sx), int(sy), int(sx + sw), int(sy + sh))).resize((int(dw), int(dh)), Image.LANCZOS)
            card = dw < W - 2
            if card:
                radius = int(26 * (1 - dw / W) / (1 - WINDOW[1][2] / W))
                sh_img, pad = shadow_for((int(dw), int(dh)), radius)
                canvas.alpha_composite(sh_img, (int(dx) - pad, int(dy) - pad))
                canvas.alpha_composite(rounded(pic, radius), (int(dx), int(dy)))
            else:
                canvas.alpha_composite(pic.convert("RGBA"), (int(dx), int(dy)))
            captions(tl, t, canvas)
            outro(tl, t, canvas)
        fade = min(clamp(t / 0.4), clamp((tl["total"] - t) / 0.6))
        if fade < 1:
            canvas = Image.blend(Image.new("RGBA", (W, H), (0, 0, 0, 255)), canvas, fade)
        ff.stdin.write(canvas.convert("RGB").tobytes())
        if i % 150 == 0:
            print("frame", i, "/", frames, flush=True)
    ff.stdin.close()
    ff.wait()
    print("wrote", out)


if __name__ == "__main__":
    main(*sys.argv[1:4])
