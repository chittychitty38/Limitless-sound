"""
The Panda Drums promo video: the plugin itself, cut on the beat, with captions, key cards and
badges made from the GUI asset pack's own panels, buttons, readouts and hearts; a pad and bass
follow the song's keys so you hear the drums sit in each one.

    PandaDrumsRender promo <dir>                          the performance: frames, drums, timeline
    python promo.py <dir> <hero.png> <out.mp4>            this: the finished 1920 x 1080 video

Needs numpy, Pillow and ffmpeg. Fonts come from ../Resources/fonts, the pack's pieces from
../Resources/ui.
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
UI = os.path.join(HERE, "..", "Resources", "ui")
W, H, FPS, SR = 1920, 1080, 30, 48000
BRAND = "PURAFIED"

# The pack's palette.
PANEL, PANEL_HI = (39, 19, 48), (58, 31, 69)
PINK, TEAL, YELLOW = (255, 67, 157), (42, 171, 156), (245, 192, 74)
TEXT, TEXT_DIM, CREAM, INK = (246, 232, 244), (185, 157, 192), (251, 242, 220), (21, 16, 22)

# Where things are in the plugin window, in its 1280 x 860 design units (the frames are 2x).
DESIGN = (1280, 860)
SCALE = 2.0
SHOTS = {
    "stage": (0, 64, 1280, 720),
    "panda": (470, 78, 640, 360),
    "hits": (0, 430, 760, 428),
    "key": (380, 0, 900, 506),
    "tiles": (0, 560, 760, 300),
}


def font(name, size):
    return ImageFont.truetype(os.path.join(FONTS, {"display": "Anton-Regular.ttf", "ui": "DejaVuSans-Bold.ttf"}[name]), size)


# ---------------------------------------------------------------------------- easing
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


# ---------------------------------------------------------------------------- the pack's pieces
_ui_json = None
_ui_cache = {}


def ui_info(name):
    global _ui_json
    if _ui_json is None:
        with open(os.path.join(UI, "ui.json")) as f:
            _ui_json = json.load(f)
    return _ui_json[name]


def ui_img(name):
    if name not in _ui_cache:
        _ui_cache[name] = Image.open(os.path.join(UI, name + "@2x.png")).convert("RGBA")
    return _ui_cache[name]


def _slices(src, k, xs, ys, dxs, dys):
    """Cut src at xs, ys (pack pixels; k image pixels each) and lay the pieces out at dxs, dys."""
    out = Image.new("RGBA", (int(round(dxs[-1])), int(round(dys[-1]))), (0, 0, 0, 0))
    for r in range(len(ys) - 1):
        for c in range(len(xs) - 1):
            sx0, sx1, sy0, sy1 = int(xs[c] * k), int(xs[c + 1] * k), int(ys[r] * k), int(ys[r + 1] * k)
            dx0, dx1, dy0, dy1 = int(round(dxs[c])), int(round(dxs[c + 1])), int(round(dys[r])), int(round(dys[r + 1]))
            if sx1 <= sx0 or sy1 <= sy0 or dx1 <= dx0 or dy1 <= dy0:
                continue
            out.alpha_composite(src.crop((sx0, sy0, sx1, sy1)).resize((dx1 - dx0, dy1 - dy0), Image.LANCZOS), (dx0, dy0))
    return out


def panel(name, w, h, s=2.0):
    """A panel stretched to w x h, its corners kept at s pixels per pack pixel."""
    info, src = ui_info(name), ui_img(name)
    k = src.width / info["w"]
    c = info["corner"]
    cs = min(c * s, w / 2, h / 2)
    return _slices(src, k, [0, c, info["w"] - c, info["w"]], [0, c, info["h"] - c, info["h"]],
                   [0, cs, w - cs, w], [0, cs, h - cs, h])


def button(name, w, h):
    """A button scaled to height h and stretched to w, its corners and any lettering kept."""
    info, src = ui_info(name), ui_img(name)
    k = src.width / info["w"]
    s = h / info["h"]
    c = info["corner"]
    b, e = info["w"] / 2, info["w"] / 2
    if "text" in info:
        b, e = max(c + 1, info["text"][0] - 3), min(info["w"] - c - 1, info["text"][2] + 3)
    mid = (e - b) * s
    m0 = w / 2 - mid / 2
    return _slices(src, k, [0, c, b, e, info["w"] - c, info["w"]], [0, info["h"]],
                   [0, c * s, m0, m0 + mid, w - c * s, w], [0, h])


def readout(name, w, h):
    """A readout pill stretched to w, its dot kept."""
    info, src = ui_info(name), ui_img(name)
    k = src.width / info["w"]
    s = h / info["h"]
    a = max(info["corner"], info["dot"][2] + 3)
    c = info["corner"]
    return _slices(src, k, [0, a, info["w"] - c, info["w"]], [0, info["h"]], [0, a * s, w - c * s, w], [0, h])


def icon(name, size):
    img = ui_img(name)
    s = size / max(img.width, img.height)
    return img.resize((max(1, int(img.width * s)), max(1, int(img.height * s))), Image.LANCZOS)


_text_cache = {}


def text(s, size, fill, face="ui", stroke=0, stroke_fill=INK, shadow=False, tracking=0):
    """A line of text as an RGBA image."""
    key = (s, size, fill, face, stroke, stroke_fill, shadow, tracking)
    if key in _text_cache:
        return _text_cache[key]
    f = font(face, size)
    pad = stroke + (24 if shadow else 4)
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
        img = drop_shadow(img, 8, 0.55, 6)
    _text_cache[key] = img
    return img


def wrap(s, size, width):
    """s split into lines no wider than width, in the pack's lettering."""
    f = font("ui", size)
    lines, line = [], ""
    for word in s.split():
        trial = (line + " " + word).strip()
        if f.getlength(trial) > width and line:
            lines.append(line)
            line = word
        else:
            line = trial
    return lines + [line] if line else lines


def place(canvas, img, cx, cy, scale=1.0, alpha=1.0, anchor="c"):
    """Composite img centred at (cx, cy) (anchor 'l': its left edge at cx)."""
    if alpha <= 0.01 or scale <= 0.01:
        return
    if abs(scale - 1.0) > 1e-3:
        img = img.resize((max(1, int(img.width * scale)), max(1, int(img.height * scale))), Image.LANCZOS)
    if alpha < 0.999:
        img = img.copy()
        img.putalpha(img.getchannel("A").point(lambda v: int(v * alpha)))
    x = int(cx - (0 if anchor == "l" else img.width / 2))
    y = int(cy - img.height / 2)
    if x >= canvas.width or y >= canvas.height or x + img.width <= 0 or y + img.height <= 0:
        return
    canvas.alpha_composite(img, (max(0, x), max(0, y)), (max(0, -x), max(0, -y)))


def drop_shadow(img, blur=22, alpha=0.6, dy=12):
    pad = blur * 3
    out = Image.new("RGBA", (img.width + pad * 2, img.height + pad * 2), (0, 0, 0, 0))
    sh = Image.new("RGBA", img.size, (8, 0, 10, 0))
    sh.putalpha(img.getchannel("A").point(lambda v: int(v * alpha)))
    out.alpha_composite(sh, (pad, pad + dy))
    out = out.filter(ImageFilter.GaussianBlur(blur))
    out.alpha_composite(img, (pad, pad))
    return out


# ---------------------------------------------------------------------------- captions from the pack
_card_cache = {}


def caption_card(line, accent=None, size=46):
    """A line on the pack's popup panel, its accent words in pink."""
    key = (line, accent, size)
    if key in _card_cache:
        return _card_cache[key]
    f = font("ui", size)
    pad_x, h = int(size * 1.0), int(size * 2.1)
    w = int(f.getlength(line)) + pad_x * 2
    card = panel("panel_popup_panel", w, h, 2.4)
    d = ImageDraw.Draw(card)
    y = (h - size * 1.18) / 2
    parts = [(line, TEXT)]
    if accent and accent in line:
        i = line.index(accent)
        parts = [(line[:i], TEXT), (accent, PINK), (line[i + len(accent):], TEXT)]
    x = pad_x
    for s, colour in parts:
        d.text((x, y), s, font=f, fill=colour)
        x += f.getlength(s)
    card = drop_shadow(card)
    _card_cache[key] = card
    return card


def key_pill(name, h=104):
    """'KEY  E MAJOR' on the pack's teal key selector, like the plugin's own."""
    key = ("pill", name, h)
    if key not in _card_cache:
        size = int(h * 0.36)
        f = font("ui", size)
        label = "KEY  " + name.upper()
        w = int(f.getlength(label) + h * 1.6)
        img = button("button_key_selector_blank", w, h)
        ImageDraw.Draw(img).text(((w - f.getlength(label)) / 2, (h - size * 1.18) / 2), label, font=f, fill=TEXT)
        _card_cache[key] = drop_shadow(img)
    return _card_cache[key]


def pitch_row(drum, pitch, w=440, h=58):
    """A drum's note on the pack's teal readout, with a heart: it's in key."""
    key = ("row", drum, pitch, w, h)
    if key not in _card_cache:
        img = readout("readout_zone", w, h)
        d = ImageDraw.Draw(img)
        size = int(h * 0.4)
        f = font("ui", size)
        y = (h - size * 1.18) / 2
        d.text((h * 0.95, y), drum.upper(), font=f, fill=TEXT_DIM)
        d.text((w - h * 1.3 - f.getlength(pitch), y), pitch, font=f, fill=TEXT)
        heart = icon("icon_heart_teal", int(h * 0.55))
        img.alpha_composite(heart, (int(w - h * 1.0), int((h - heart.height) / 2)))
        _card_cache[key] = img
    return _card_cache[key]


def feature_readout(piece, label, value, colour, w=480, h=80):
    key = ("feature", piece, label, value, w, h)
    if key not in _card_cache:
        img = readout(piece, w, h)
        d = ImageDraw.Draw(img)
        size = int(h * 0.34)
        f, fv = font("ui", size), font("ui", int(size * 1.3))
        d.text((h * 0.95, (h - size * 1.18) / 2), label, font=f, fill=TEXT_DIM)
        d.text((w - h * 0.5 - fv.getlength(value), (h - size * 1.3 * 1.18) / 2), value, font=fv, fill=colour)
        _card_cache[key] = drop_shadow(img, 16, 0.55, 8)
    return _card_cache[key]


def tab_badge(page, h=120):
    key = ("tab", page, h)
    if key not in _card_cache:
        info = ui_info("button_tab_%s_active" % page)
        img = button("button_tab_%s_active" % page, int(info["w"] * h / info["h"]), h)
        _card_cache[key] = drop_shadow(img, 20, 0.6, 10)
    return _card_cache[key]


def formats_pill():
    key = ("formats",)
    if key not in _card_cache:
        label = "AU  ·  VST3  ·  STANDALONE"
        f = font("ui", 28)
        img = button("button_primary_action", int(f.getlength(label) + 120), 76)
        ImageDraw.Draw(img).text(((img.width - f.getlength(label)) / 2, (76 - 28 * 1.18) / 2), label, font=f, fill=TEXT)
        _card_cache[key] = drop_shadow(img, 16, 0.5, 8)
    return _card_cache[key]


# ---------------------------------------------------------------------------- background
def make_bg():
    y = np.linspace(0, 1, H)[:, None]
    x = np.linspace(0, 1, W)[None, :]
    top, bottom = np.array(PANEL_HI, float), np.array(PANEL, float) * 0.7
    img = top * (1 - y[..., None]) + bottom * y[..., None]
    glow = np.exp(-(((x - 0.62) / 0.42) ** 2 + ((y - 0.5) / 0.55) ** 2))[..., None]
    img = img * (1 - 0.35 * glow) + np.array(PINK, float) * 0.22 * glow
    img = np.broadcast_to(img, (H, W, 3)).clip(0, 255).astype(np.uint8)
    return Image.fromarray(img, "RGB").convert("RGBA")


HEARTS = ["icon_heart_pink", "icon_heart_red", "icon_heart_teal", "icon_heart_yellow"]


def background(t):
    """The pack's plum, with the pack's hearts drifting up through it."""
    base = BG.copy()
    rng = np.random.default_rng(3)
    for i in range(22):
        x0, y0, sp, ph, sz = rng.uniform(0, W), rng.uniform(0, H), rng.uniform(14, 40), rng.uniform(0, 6.28), rng.uniform(18, 46)
        x = x0 + 30 * math.sin(t * 0.6 + ph)
        y = (y0 - t * sp) % (H + 100) - 50
        place(base, icon(HEARTS[i % 4], int(sz)), x, y, 1.0, 0.18 + 0.12 * math.sin(t * 1.5 + ph))
    return base


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


# ---------------------------------------------------------------------------- the cut
FLATS = {"C#": "Db", "D#": "Eb", "F#": "Gb", "G#": "Ab", "A#": "Bb"}


def spell(note, root, major):
    """Note names the way the key spells them: flats in C minor, sharps in E major."""
    flat_key = (major and root in (5, 10, 3, 8, 1)) or (not major and root in (0, 2, 5, 7, 10, 3))
    if flat_key and note[:2] in FLATS:
        return FLATS[note[:2]] + note[2:]
    return note


def plan(tl):
    """The cut, on the beat: (start, end, shot, caption)."""
    bar = 240.0 / tl["bpm"]
    i0 = tl["intro"]
    secs = tl["sections"]
    keys = [s for s in secs if s["caption"] == "key"]
    cuts = [(i0, i0 + bar, "window", "meet"),
            (i0 + bar, i0 + 2 * bar, "panda", "midi"),
            (i0 + 2 * bar, i0 + 3 * bar, "hits", "rr"),
            (i0 + 3 * bar, keys[0]["time"] - 1.2, "stage", None)]
    for n, s in enumerate(keys):
        cuts.append((s["time"] - 1.2, s["time"] + 0.5, "key", ("pick", n)))       # the key panel picks it
        cuts.append((s["time"] + 0.5, s["time"] + bar, "card", ("key", n)))
        nxt = keys[n + 1]["time"] - 1.2 if n + 1 < len(keys) else s["end"]
        cuts.append((s["time"] + bar, nxt, "tiles", ("melody", n)))
    for s in secs:
        if s["caption"] in ("lab", "mixer", "mapping"):
            cuts.append((s["time"], s["end"], "page", ("page", s["caption"])))
        if s["caption"] == "fill":
            cuts.append((s["time"], s["time"] + bar * 0.5, "panda", None))
            cuts.append((s["time"] + bar * 0.5, s["end"], "stage", None))
    cuts.append((tl["end"], tl["total"] + 1, "stage", "end"))
    return cuts


def kick_punch(tl, t):
    p = 0.0
    for k in tl["kicks"]:
        if 0 <= t - k < 0.3:
            p = max(p, 0.025 * math.exp(-(t - k) / 0.09))
    return p


def shot_picture(src, shot, k, punch):
    """Part of the window filling the screen: a slow push in, and a punch on every kick."""
    x, y, w, h = SHOTS[shot]
    z = 1.0 + 0.06 * ease_in_out(k) + punch
    cx, cy = x + w / 2, y + h / 2
    w2, h2 = w / z, h / z
    x2, y2 = clamp(cx - w2 / 2, 0, DESIGN[0] - w2), clamp(cy - h2 / 2, 0, DESIGN[1] - h2)
    box = (int(x2 * SCALE), int(y2 * SCALE), int((x2 + w2) * SCALE), int((y2 + h2) * SCALE))
    return src.crop(box).resize((W, H), Image.LANCZOS).convert("RGBA")


def window_card(src, w):
    """The whole window, its corners rounded, with its shadow."""
    h = int(w * DESIGN[1] / DESIGN[0])
    pic = src.resize((w, h), Image.LANCZOS).convert("RGBA")
    mask = Image.new("L", (w, h), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, w - 1, h - 1), int(w * 0.018), fill=255)
    pic.putalpha(mask)
    return drop_shadow(pic, 34, 0.65, 22)


def draw_frame(tl, t, i, d, hero, cuts):
    if t < tl["intro"]:
        return intro_frame(t, hero)
    start, end, shot, cap = next((c for c in cuts if c[0] <= t < c[1]), cuts[-1])
    k = (t - start) / max(0.01, end - start)
    path = os.path.join(d, "frames", "%04d.jpg" % (i + 1))
    src = Image.open(path).convert("RGB")
    punch = kick_punch(tl, t)
    keys = [s for s in tl["sections"] if s["caption"] == "key"]

    if shot in ("window", "page", "card"):
        canvas = background(t)
        if shot == "card":
            place(canvas, window_card(src, 1180), 1290, 560)
        else:
            w = int(1480 * (1.0 + 0.05 * ease_in_out(k) + punch * 0.5))
            place(canvas, window_card(src, w), W / 2 + (130 if shot == "page" else 0), H / 2 + 30)
    else:
        canvas = shot_picture(src, shot, k, punch)

    def lower(line, accent=None, appear=0.0, y=960):
        a = ease_out((t - start - appear) / 0.25)
        if a > 0:
            place(canvas, caption_card(line, accent), W / 2, y + 40 * (1 - a), 1.0, a)

    kind = cap[0] if isinstance(cap, tuple) else cap
    if kind == "meet":
        lower("MEET THE DRUMMER.", "DRUMMER", 0.15)
    elif kind == "midi":
        lower("HE PLAYS EVERY HIT OF YOUR MIDI.", "EVERY HIT", 0.1)
    elif kind == "rr":
        for n, (piece, label, value, colour) in enumerate((("readout_hit", "ROUND ROBIN", "2 / 3", TEXT),
                                                          ("readout_midi", "VELOCITY", "112", YELLOW),
                                                          ("readout_zone", "ZONE", "5 / 5", TEAL))):
            kk = (t - start - 0.25 - n * 0.22) / 0.3
            if kk > 0:
                place(canvas, feature_readout(piece, label, value, colour), 1520, 470 + n * 108, pop(kk), clamp(kk * 3))
        lower("ON EVERY HIT. CATCH THE WEIRD ONE.", "EVERY HIT", 0.9)
    elif kind == "pick":
        lower("PICK YOUR SONG'S KEY.", "KEY", 0.1, y=990)
    elif kind == "key":
        s = keys[cap[1]]
        lines = ["Every kick, snare and tom tunes itself.", "Every drum lands in key.",
                 "Major or minor. Sharps or flats.", "No matter what you work on."]
        kk = (t - start) / 0.4
        place(canvas, text("CHROMATIC DRUMS", 38, PINK), 80, 180, 1.0, ease_out(kk), "l")
        pill = key_pill(s["key"])
        place(canvas, pill, 80 + pill.width / 2 - 60 - 50 * (1 - ease_out(kk)), 270, pop(kk), clamp(kk * 3))
        y = 390
        for n, (drum, pitch) in enumerate(list(s["pitches"].items())[:5]):
            a = ease_out((t - start - 0.15 - 0.07 * n) / 0.25)
            place(canvas, pitch_row(drum, spell(pitch, s["root"], s["major"])), 90 - 30 * (1 - a), y, 1.0, a, "l")
            y += 74
        y = 800
        for line in wrap(lines[cap[1]], 30, 520):
            place(canvas, text(line, 30, TEXT), 90, y, 1.0, ease_out((t - start - 0.6) / 0.3), "l")
            y += 42
    elif kind == "melody":
        s = keys[cap[1]]
        lower("THE FLOOR TOM PLAYS THE MELODY. IN %s." % s["key"].upper(), s["key"].upper(), 0.1, y=120)
    elif kind == "page":
        page = cap[1]
        kk = (t - start) / 0.35
        place(canvas, tab_badge(page), 250 - 60 * (1 - ease_out(kk)), 150, pop(kk), clamp(kk * 3))
        line, accent = {"lab": ("VELOCITY + ROUND ROBIN LAB.", "ROUND ROBIN"), "mixer": ("A CHANNEL FOR EVERY MIC.", "EVERY MIC"),
                        "mapping": ("GM, SUPERIOR, EZDRUMMER, V-DRUMS. OR YOUR PADS.", "YOUR PADS")}[page]
        lower(line, accent, 0.15, y=1005)
    elif kind == "end":
        outro(tl, t, canvas)
    return canvas


def outro(tl, t, canvas):
    start = tl["end"] + 0.9
    if t < start:
        return
    k = t - start
    canvas.alpha_composite(Image.new("RGBA", (W, H), (20, 6, 24, int(190 * ease_out(k / 0.6)))))
    card = drop_shadow(panel("panel_modal_dialog", 1120, 680, 3.0), 30, 0.6, 18)
    place(canvas, card, W / 2, H / 2 + 10, pop(k / 0.45), clamp(k / 0.15))
    if k > 0.2:
        place(canvas, text("PANDA DRUMS", 150, CREAM, "display", stroke=10), W / 2, 350, pop((k - 0.2) / 0.45), clamp((k - 0.2) / 0.15))
    place(canvas, text("vol. one", 40, PINK), W / 2, 462, 1.0, clamp((k - 0.4) / 0.3))
    place(canvas, key_pill("of any song", 92), W / 2, 566, pop((k - 0.55) / 0.4), clamp((k - 0.55) / 0.2))
    place(canvas, formats_pill(), W / 2, 678, 1.0, clamp((k - 0.8) / 0.3))
    place(canvas, text("macOS  &  Windows", 30, TEXT_DIM), W / 2, 760, 1.0, clamp((k - 0.95) / 0.3))
    place(canvas, text(BRAND, 76, PINK, "display", stroke=5, tracking=14), W / 2, 950, 1.0, clamp((k - 1.2) / 0.4))
    # The pack's hearts burst out of the card.
    rng = np.random.default_rng(11)
    for n in range(26):
        ang, sp, sz, ph = rng.uniform(0, 6.28), rng.uniform(260, 620), rng.uniform(30, 64), rng.uniform(0, 0.5)
        kk = k - ph
        if kk <= 0:
            continue
        r = sp * ease_out(kk / 1.2)
        place(canvas, icon(HEARTS[n % 4], int(sz)), W / 2 + math.cos(ang) * r * 1.4, H / 2 + math.sin(ang) * r + 140 * kk * kk,
              1.0, clamp(1.6 - kk))


def intro_frame(t, hero):
    canvas = background(t)
    if t < 2.1:
        a = min(ease_out(t / 0.6), clamp((2.05 - t) / 0.25))
        place(canvas, text(BRAND, 180, CREAM, "display", stroke=10, tracking=int(10 + 18 * ease_out(t / 1.6))), W / 2, 470,
              1.0 + 0.04 * t, a)
        place(canvas, text("presents", 46, PINK), W / 2, 640, 1.0, a * clamp((t - 0.7) / 0.4))
    if t >= 2.0:
        k = t - 2.0
        z = 1.12 - 0.12 * ease_out(k / 1.4)
        img = hero.resize((int(hero.width * z), int(hero.height * z)), Image.LANCZOS)
        img.putalpha(int(255 * clamp(k / 0.2)))
        canvas.alpha_composite(img, (int((W - img.width) / 2), int((H - img.height) / 2)))
        flash = clamp(1 - (t - 2.2) / 0.25) if t >= 2.2 else 0.0
        if flash > 0:
            canvas.alpha_composite(Image.new("RGBA", (W, H), (255, 255, 255, int(200 * flash))))
        if t >= 2.2:
            band = Image.new("RGBA", (W, 260), (12, 2, 14, 0))
            band.putalpha(Image.fromarray(np.linspace(170, 0, 260)[:, None].repeat(W, 1).astype(np.uint8), "L"))
            canvas.alpha_composite(band, (0, 0))
            kk = pop((t - 2.2) / 0.45)
            title = text("PANDA DRUMS", 122, CREAM, "display", stroke=9, shadow=True)
            place(canvas, title, 40 + title.width * (1 - kk) / 2, 100, kk, 1.0, "l")
            pill = key_pill("of any song", 80)
            a = ease_out((t - 2.6) / 0.3)
            place(canvas, pill, 60 + pill.width / 2, 990 + 40 * (1 - a), 1.0, a)
            # The pack's hearts thrown up by the title hit.
            rng = np.random.default_rng(4)
            for n in range(14):
                ang, sp, sz = rng.uniform(3.4, 6.0), rng.uniform(300, 700), rng.uniform(34, 70)
                kk2 = t - 2.2
                place(canvas, icon(HEARTS[n % 4], int(sz)), W / 2 + math.cos(ang) * sp * kk2,
                      600 + math.sin(ang) * sp * kk2 + 500 * kk2 * kk2, 1.0, clamp(1.4 - kk2))
    return canvas


def main(d, hero_path, out):
    global BG
    BG = make_bg()
    with open(os.path.join(d, "timeline.json")) as f:
        tl = json.load(f)
    hero = Image.open(hero_path).convert("RGBA")
    hero = hero.resize((W, int(hero.height * W / hero.width)), Image.LANCZOS)
    if hero.height > H:
        top = (hero.height - H) // 2
        hero = hero.crop((0, top, W, top + H))
    cuts = plan(tl)
    frames = int(tl["total"] * FPS)
    only = os.environ.get("PROMO_FRAMES")        # "a-b": just those frames, as JPEGs named after out (to check a cut)
    if only:
        lo, hi = (int(v) for v in only.split("-"))
        for i in range(lo, min(hi, frames)):
            draw_frame(tl, i / FPS, i, d, hero, cuts).convert("RGB").save("%s.%04d.jpg" % (out, i), quality=88)
        return
    wav = os.path.join(d, "promo_mix.wav")
    mix_audio(d, tl, wav)
    ff = subprocess.Popen(["ffmpeg", "-loglevel", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", "%dx%d" % (W, H),
                           "-r", str(FPS), "-i", "-", "-i", wav, "-c:v", "libx264", "-preset", "slow", "-crf", "17",
                           "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "256k", "-shortest", "-movflags", "+faststart", out],
                          stdin=subprocess.PIPE)
    for i in range(frames):
        t = i / FPS
        canvas = draw_frame(tl, t, i, d, hero, cuts)
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
