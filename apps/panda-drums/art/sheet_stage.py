"""
Builds the plugin's stage from the sprite sheet pieces (cut and upscaled by sheet_cut.py).

    LAMA=big-lama.pt python sheet_stage.py <pieces dir> <outdir>

Lays the kit out where the plugin puts each kind of drum, sizes every piece to the stage,
takes the props out of the panda's poses (each pose came with a drum or a cymbal), measures
the anchors the plugin needs (drum heads, cymbal discs, the head in every pose and face) and
writes each layer at 1x and 2x the 1280 x 736 stage with manifest.json, in the layout
Source/gui/Skin.cpp reads.

Needs numpy, Pillow and OpenCV; with LAMA set, torch too (LaMa paints back the panda's arms
and legs where a pose's drum or cymbal covered them; without it those spots are cut out).
"""

import json
import os
import sys

import cv2
import numpy as np
from PIL import Image, ImageFilter

STAGE_W, STAGE_H = 1280, 736
SCALES = (1, 2)

# Where the panda sits: every pose is scaled and moved so its head lands here.
HEAD = (640.0, 205.0)
HEAD_RX = 132.0

# Slots: where each kind of drum goes (stage px) and its radius in px per inch of diameter.
SLOTS = {
    "kick": [(640, 588)],
    "rack1": [(640, 398)],
    "rack2": [(712, 410), (565, 412)],
    "rack3": [(738, 410), (640, 395), (542, 410)],
    "rack4": [(762, 412), (682, 396), (598, 396), (518, 412)],
    "floor": [(432, 515), (322, 568)],
    "snare": [(800, 505), (1060, 575)],
    "hihat": [(950, 418)],
    "crash": [(955, 228), (330, 228), (1112, 300), (170, 340)],
    "ride": [(298, 395), (1105, 345)],
    "china": [(205, 262), (1098, 160)],
    "splash": [(820, 150), (468, 150)],
    "perc": [(1095, 560), (190, 565)],
}
PPI = {"kick": 5.2, "rack1": 4.7, "rack2": 4.7, "rack3": 4.7, "rack4": 4.7, "floor": 4.6, "snare": 4.6,
       "hihat": 5.4, "crash": 5.2, "ride": 5.0, "china": 5.0, "splash": 5.2, "perc": 4.4}
FLOOR_FRONT, FLOOR_BACK = 694.0, 640.0       # where stands touch the floor, front pieces and back
# The factory kit's default sizes, for the default picture.
DEFAULT = {"kick": 22, "rack": [10, 13], "floor": 16, "snare": 14, "hihat": 14, "crash": [18, 19], "ride": 21,
           "china": 16, "splash": 10}

# Pieces of the poses that are props (the drum or cymbal each pose came with), in the 4x
# piece's pixels: "drop" is cut away (a neighbour's leftovers), "all" takes everything in the
# rectangle, "metal" only the gold and chrome. What was behind them is painted back in.
PROPS = {
    "pose_kick": dict(all=[(325, 405, 9999, 9999)]),
    "pose_snare": dict(all=[(195, 422, 9999, 9999)]),
    "pose_hi_hat": dict(all=[(190, 405, 9999, 9999)]),
    "pose_tom_left": dict(all=[(258, 415, 9999, 9999)]),
    "pose_tom_right": dict(all=[(190, 440, 9999, 9999)]),
    "pose_crash_left": dict(drop=[(0, 385, 100, 9999)], all=[(600, 390, 9999, 9999), (615, 255, 9999, 9999)], metal=[(440, 240, 9999, 9999)]),
    "pose_crash_right": dict(all=[(505, 390, 9999, 9999), (560, 260, 9999, 9999)], metal=[(390, 255, 9999, 9999)]),
    "pose_fill": dict(all=[(320, 430, 9999, 9999), (560, 300, 9999, 9999)], metal=[(425, 215, 9999, 9999)]),
}
LAMA = os.environ.get("LAMA")      # big-lama.pt (TorchScript): paints in what the props hid
# The head in each pose (centre and radii, 4x pixels), where the measured one was off.
HEADS = {
    "pose_kick": (261, 180, 171, 140), "pose_snare": (201, 170, 155, 138), "pose_hi_hat": (228, 170, 172, 135),
    "pose_tom_left": (272, 162, 167, 138), "pose_tom_right": (185, 162, 160, 138), "pose_crash_right": (360, 175, 160, 135),
}
POSES = ["idle", "blink", "kick", "snare", "hi_hat", "tom_left", "tom_right", "crash_left", "crash_right", "fill", "cheer"]
FACES = ["neutral", "happy", "open_mouth", "smile", "focused", "excited", "wink", "laugh", "surprised", "tongue_out",
         "angry", "sad"]


# ---------------------------------------------------------------------------- measuring
def rgba(img):
    return np.asarray(img.convert("RGBA"))


def hsv_of(a):
    return cv2.cvtColor(np.ascontiguousarray(a[..., :3]), cv2.COLOR_RGB2HSV)


def bbox(mask):
    ys, xs = np.nonzero(mask)
    return xs.min(), ys.min(), xs.max(), ys.max()


def largest(mask, close=0):
    m = mask.astype(np.uint8)
    if close:
        m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (close, close)))
    n, lab, st, _ = cv2.connectedComponentsWithStats(m, 8)
    i = 1 + int(np.argmax(st[1:, 4]))
    return lab == i


def head_of(img, top_frac):
    a = rgba(img)
    hsv = hsv_of(a)
    cream = (hsv[..., 2] > 170) & (hsv[..., 1] < 90) & (a[..., 3] > 128)
    cream[int(a.shape[0] * top_frac):] = False
    x0, y0, x1, y1 = bbox(largest(cream, 71))
    return ((x0 + x1) / 2, (y0 + y1) / 2, (x1 - x0) / 2, (y1 - y0) / 2)


def drum_head(img):
    """The batter head: the white ellipse at the top."""
    a = rgba(img)
    hsv = hsv_of(a)
    white = (hsv[..., 2] > 185) & (hsv[..., 1] < 55) & (a[..., 3] > 200)
    white[int(a.shape[0] * 0.3):] = False
    x0, y0, x1, y1 = bbox(largest(white, 9))
    # The hoop runs round the head: widen to the drum's full width there.
    rows = np.nonzero(a[y0:y1 + 1, :, 3].max(1) > 128)[0]
    xs = np.nonzero(a[(y0 + y1) // 2, :, 3] > 128)[0]
    return ((xs.min() + xs.max()) / 2, (y0 + y1) / 2, (xs.max() - xs.min()) / 2, (y1 - y0) / 2 + 6)


def kick_head(img):
    a = rgba(img)
    hsv = hsv_of(a)
    cream = (hsv[..., 2] > 170) & (hsv[..., 1] < 80) & (a[..., 3] > 200)
    x0, y0, x1, y1 = bbox(largest(cream, 41))
    r = max(x1 - x0, y1 - y0) / 2
    return ((x0 + x1) / 2, (y0 + y1) / 2, r, r)


def cymbal_disc(img):
    """Centre and radii of the bronze disc, and the bottom of the post under it."""
    a = rgba(img)
    hsv = hsv_of(a)
    gold = (hsv[..., 0] >= 6) & (hsv[..., 0] <= 32) & (hsv[..., 1] > 60) & (hsv[..., 2] > 60) & (a[..., 3] > 128)
    x0, y0, x1, y1 = bbox(largest(gold, 15))
    cx = (x0 + x1) / 2
    col = a[:, int(cx) - 12:int(cx) + 12, 3].max(1)
    post = np.nonzero(col > 128)[0].max()
    return ((x0 + x1) / 2, (y0 + y1) / 2, (x1 - x0) / 2, (y1 - y0) / 2), float(post)


# ---------------------------------------------------------------------------- cleaning
_lama = None


def lama(rgb, mask):
    """Inpaint rgb (uint8 HxWx3) where mask is set, with LaMa."""
    global _lama
    import torch
    if _lama is None:
        _lama = torch.jit.load(LAMA, map_location="cpu").eval()
    h, w = rgb.shape[:2]
    ph, pw = (8 - h % 8) % 8, (8 - w % 8) % 8
    img = torch.from_numpy(np.pad(rgb, ((0, ph), (0, pw), (0, 0)), mode="edge").transpose(2, 0, 1)).float().unsqueeze(0) / 255
    m = torch.from_numpy((np.pad(mask, ((0, ph), (0, pw))) > 0).astype(np.float32))[None, None]
    with torch.no_grad():
        out = _lama(img, m)
    return (out[0].permute(1, 2, 0).numpy().clip(0, 1) * 255).astype(np.uint8)[:h, :w]


def clean_pose(img, name):
    a = rgba(img).copy()
    props = PROPS.get(name, {})
    for x0, y0, x1, y1 in props.get("drop", []):
        a[y0:y1, x0:x1, 3] = 0
    hsv = hsv_of(a)
    mask = np.zeros(a.shape[:2], bool)
    for x0, y0, x1, y1 in props.get("all", []):
        mask[y0:y1, x0:x1] = True
    for x0, y0, x1, y1 in props.get("metal", []):
        sub = hsv[y0:y1, x0:x1]
        gold = (sub[..., 0] >= 5) & (sub[..., 0] <= 34) & (sub[..., 1] > 55) & (sub[..., 2] > 50)
        chrome = (sub[..., 1] < 40) & (sub[..., 2] > 120)
        mask[y0:y1, x0:x1] |= gold | chrome
    mask &= a[..., 3] > 30
    if mask.any():
        mask = cv2.dilate(mask.astype(np.uint8), np.ones((9, 9), np.uint8)) > 0
        if LAMA:
            # Over green, paint in what the prop hid; the green that comes back is background again.
            green = np.array([0, 255, 0], np.float32)
            al = a[..., 3:4] / 255.0
            comp = (a[..., :3] * al + green * (1 - al)).astype(np.uint8)
            res = lama(comp, mask.astype(np.uint8)).astype(np.float32)
            r, g, b = res[..., 0], res[..., 1], res[..., 2]
            greenness = g - np.maximum(r, b)
            fill_alpha = np.clip(1 - (greenness - 8) / 36, 0, 1) ** 1.5
            res[..., 1] = np.minimum(g, np.maximum(r, b))               # no green fringe
            a[mask, :3] = res[mask].astype(np.uint8)
            a[mask, 3] = (fill_alpha[mask] * 255).astype(np.uint8)
        else:
            a[mask, 3] = 0
    # Keep the panda (the largest piece) and what touches it.
    keep = largest(a[..., 3] > 40)
    keep = cv2.dilate(keep.astype(np.uint8), np.ones((5, 5), np.uint8)) > 0
    a[..., 3] = np.where(keep, a[..., 3], 0)
    return Image.fromarray(a, "RGBA")


def fill_holes(mask):
    m = mask.astype(np.uint8)
    flood = np.pad(m, 1).copy()
    cv2.floodFill(flood, None, (0, 0), 2)
    return mask | (flood[1:-1, 1:-1] == 0)


def split_head(img, ell):
    """Cuts the head (ears and all) off a pose, so it can nod and tilt on its own. Returns the
    head and the body. The body keeps the bottom of the head, narrowed from the sides: the neck
    under the chin, hidden under the head however it moves, so the body never shows a second
    outline or a gap."""
    a = rgba(img).copy()
    h, w = a.shape[:2]
    hsv = hsv_of(a)
    cx, cy, rx, ry = ell
    yy, xx = np.mgrid[0:h, 0:w]
    solid = a[..., 3] > 20
    inside = ((xx - cx) / (rx * 1.03)) ** 2 + ((yy - cy) / (ry * 1.03)) ** 2 < 1
    cream = (hsv[..., 2] > 150) & (hsv[..., 1] < 110)
    # Low on the head only the fur of the chin belongs to it: not a paw, a stick or the collar.
    head = inside & solid & ((yy < cy + 0.55 * ry) | cream)
    # The ears: dark blobs above the head that don't run down into an arm.
    band = (yy > cy - 1.7 * ry) & (yy < cy - 0.25 * ry) & (np.abs(xx - cx) < 1.5 * rx)
    dark = (hsv[..., 2] < 90) & solid & band & ~inside
    n, lab, st, cen = cv2.connectedComponentsWithStats(dark.astype(np.uint8), 8)
    bottom = cy - 0.25 * ry - 2
    for i in range(1, n):
        x, y, bw, bh, area = st[i]
        if area > 0.02 * rx * rx and y + bh < bottom and abs(cen[i][0] - cx) < 1.2 * rx:
            head |= lab == i
    head = cv2.morphologyEx(head.astype(np.uint8), cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (15, 15))) > 0
    head = fill_holes(largest(head) | (head & (yy < cy - 0.25 * ry)))
    soft = cv2.GaussianBlur(head.astype(np.float32), (0, 0), 1.6)
    head_a = a.copy()
    head_a[..., 3] = (a[..., 3] * np.where(yy > cy + 0.55 * ry, soft, head)).astype(np.uint8)

    # The neck the body keeps: the bottom of the head, its sides pulled in by a fifth of the head.
    m = int(rx * 0.2)
    neck = cv2.erode(head.astype(np.uint8), np.ones((1, 2 * m + 1), np.uint8)) > 0
    ramp = np.clip((yy - (cy + 0.1 * ry)) / (0.25 * ry), 0, 1)
    gone = cv2.dilate(head.astype(np.uint8), np.ones((7, 7), np.uint8)) > 0     # past the head's soft outline too
    keep = np.where(gone, neck * ramp, 1.0)
    keep = cv2.GaussianBlur(keep.astype(np.float32), (0, 0), 2.0)
    body = a.copy()
    body[..., 3] = (a[..., 3] * np.clip(keep, 0, 1)).astype(np.uint8)
    return Image.fromarray(head_a, "RGBA"), Image.fromarray(body, "RGBA")


def glasses_box(img, ell):
    """The glasses' frame: the rows of the head where dark pixels span most of its width."""
    a = rgba(img)
    hsv = hsv_of(a)
    cx, cy, rx, ry = ell
    dark = (hsv[..., 2] < 70) & (a[..., 3] > 128)
    yy, xx = np.mgrid[0:a.shape[0], 0:a.shape[1]]
    inside = ((xx - cx) / (rx * 1.05)) ** 2 + ((yy - cy) / (ry * 1.05)) ** 2 < 1
    dark &= inside
    rows = []
    for y in range(int(cy - ry), int(cy + ry * 0.5)):
        xs = np.nonzero(dark[y])[0]
        if len(xs) and xs.max() - xs.min() > 1.3 * rx:
            rows.append((y, xs.min(), xs.max()))
    ys = [r[0] for r in rows]
    return (min(r[1] for r in rows), min(ys), max(r[2] for r in rows), max(ys))


def face_patch(img, ell):
    """The face (brows, glasses, eyes, nose, mouth, cheeks) with a soft edge, to lay over a
    pose's face. Returns the patch and the glasses box in the patch's pixels."""
    gx0, gy0, gx1, gy1 = glasses_box(img, ell)
    gw, gh = gx1 - gx0, gy1 - gy0
    x0, x1 = int(gx0 - 0.07 * gw), int(gx1 + 0.07 * gw)
    y0, y1 = int(gy0 - 0.55 * gh), int(gy1 + 1.45 * gh)
    a = rgba(img)[max(0, y0):y1, max(0, x0):x1].copy()
    h, w = a.shape[:2]
    yy, xx = np.mgrid[0:h, 0:w]
    # A rounded rectangle, feathered: solid over the features, fading into the fur.
    nx, ny = np.abs(xx - w / 2) / (w / 2), np.abs(yy - h / 2) / (h / 2)
    d = (nx ** 4 + ny ** 4) ** 0.25
    mask = np.clip((1.0 - d) / 0.16, 0, 1)
    a[..., 3] = (a[..., 3] * mask).astype(np.uint8)
    return Image.fromarray(a, "RGBA"), (gx0 - max(0, x0), gy0 - max(0, y0), gx1 - max(0, x0), gy1 - max(0, y0))


# ---------------------------------------------------------------------------- output
class Out:
    def __init__(self, outdir):
        self.dir = outdir
        os.makedirs(outdir, exist_ok=True)
        self.files = {}

    def layer(self, name, img, x, y, scale):
        """img (4x piece) drawn at stage (x, y) top-left, scaled by `scale` stage px per piece px."""
        w, h = img.width * scale, img.height * scale
        for k in SCALES:
            sw, sh = max(1, round(w * k)), max(1, round(h * k))
            im = img.resize((sw, sh), Image.LANCZOS)
            im.save(os.path.join(self.dir, "%s%s.png" % (name, "@2x" if k == 2 else "")), optimize=True)
        self.files[name] = dict(file=name, x=round(x, 2), y=round(y, 2), w=round(w, 2), h=round(h, 2))
        return self.files[name]

    def opaque(self, name, img):
        for k in SCALES:
            im = img.convert("RGB").resize((STAGE_W * k, STAGE_H * k), Image.LANCZOS)
            im.save(os.path.join(self.dir, "%s%s.jpg" % (name, "@2x" if k == 2 else "")), quality=90)
        self.files[name] = dict(file=name, x=0, y=0, w=STAGE_W, h=STAGE_H)


def P(x, y):
    return [round(float(x), 2), round(float(y), 2)]


def main(src, outdir):
    piece = lambda n: Image.open(os.path.join(src, n + ".png")).convert("RGBA")
    out = Out(outdir)
    man = dict(stage=dict(w=STAGE_W, h=STAGE_H), files=out.files, kit={}, slots={}, panda=dict(mode="poses"))

    # ---- the room: the background plate filling the stage, bamboo at the sides, the rug
    bg = piece("background")
    bg = bg.crop((round(bg.width * 0.012), round(bg.height * 0.015), round(bg.width * 0.988), round(bg.height * 0.985)))
    s = max(STAGE_W / bg.width, STAGE_H / bg.height)
    big = bg.resize((round(bg.width * s * 2), round(bg.height * s * 2)), Image.LANCZOS)
    ox = (big.width - STAGE_W * 2) // 2
    room = Image.new("RGBA", (STAGE_W * 2, STAGE_H * 2), (240, 160, 196, 255))
    room.alpha_composite(big.crop((ox, 0, ox + STAGE_W * 2, STAGE_H * 2)))
    rug = piece("rug")
    rw = 1120 * 2
    rug_s = rug.resize((rw, round(rug.height * rw / rug.width)), Image.LANCZOS)
    room.alpha_composite(rug_s, ((STAGE_W * 2 - rw) // 2, 2 * 700 - rug_s.height // 2 - 40))
    # The plate is wider than the stage: its own bamboo, cut off by the crop, goes back in at the sides.
    side = round(bg.width * 0.115)
    for x0, at in ((0, 0), (bg.width - side, STAGE_W * 2)):
        strip = bg.crop((x0, 0, x0 + side, bg.height))
        strip = strip.resize((round(side * s * 2), round(bg.height * s * 2)), Image.LANCZOS)
        mask = np.ones((strip.height, strip.width), np.float32)
        ramp = np.clip(np.linspace(0, 1, strip.width) / 0.45, 0, 1)
        mask *= ramp[::-1] if x0 == 0 else ramp
        sa = np.asarray(strip).copy()
        sa[..., 3] = (sa[..., 3] * mask).astype(np.uint8)
        strip = Image.fromarray(sa, "RGBA")
        room.alpha_composite(strip, (0 if x0 == 0 else at - strip.width, 0))
    out.opaque("stage", room)
    # The heart lights' bulbs, for the glow: bright saturated blobs along the top.
    hsv = hsv_of(rgba(room.resize((STAGE_W, STAGE_H))))
    lit = ((hsv[..., 1] > 120) & (hsv[..., 2] > 200)).astype(np.uint8)
    lit[int(STAGE_H * 0.2):] = 0
    n, lab, st, ce = cv2.connectedComponentsWithStats(lit, 8)
    bulbs = []
    for i in range(1, n):
        if st[i][4] > 30:
            rgb = rgba(room.resize((STAGE_W, STAGE_H)))[lab == i][:, :3].mean(0) / 255
            bulbs.append(dict(at=P(*ce[i]), colour=[round(float(c), 3) for c in rgb]))
    man["stage"]["bulbs"] = bulbs
    # The rug's top, for its glow, and where the rug sits.
    rug_h = rug_s.height / 2
    man["stage"]["rug"] = [640.0, round(700 - 20 - rug_h * 0.06, 2), round(rw / 2 * 0.47, 2), round(rug_h * 0.33, 2)]

    # The spotlights' three beams, without their lamps, wire and labels: they sway over the room
    # and flare on the big hits.
    sp = rgba(piece("spotlights")).copy()
    h, w = sp.shape[:2]
    hsv = hsv_of(sp)
    dark_rows = np.nonzero(((hsv[..., 2] < 60) & (sp[..., 3] > 200)).sum(1) > w * 0.12)[0]
    label_top = int(dark_rows[dark_rows > h * 0.6].min()) - 6 if len(dark_rows[dark_rows > h * 0.6]) else int(h * 0.85)
    lamp = (hsv[..., 2] < 120) & (sp[..., 3] > 60)
    lamp = cv2.dilate(lamp.astype(np.uint8), np.ones((9, 9), np.uint8)) > 0
    sp[lamp, 3] = 0
    sp[..., :3] = (255, 244, 250)
    beams = []
    for i, cx in enumerate((300.0, 640.0, 980.0)):
        x0, x1 = int(w * i / 3), int(w * (i + 1) / 3)
        crop = sp[:label_top, x0:x1].copy()
        ys, xs = np.nonzero(crop[..., 3] > 8)
        crop = crop[ys.min():, xs.min():xs.max() + 1]
        cw = crop.shape[1]
        # Soft light, not a cut-out: the holes the lamps left closed, the edges blurred well out.
        al = crop[..., 3].astype(np.float32)
        al = cv2.morphologyEx(al, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (41, 41)))
        al = cv2.GaussianBlur(al, (0, 0), cw * 0.05)
        al *= 210.0 / max(1.0, al.max())
        edge = np.clip(np.minimum(np.arange(cw), cw - 1 - np.arange(cw)) / (cw * 0.12), 0, 1)
        fade = np.clip((crop.shape[0] - np.arange(crop.shape[0])) / (crop.shape[0] * 0.3), 0, 1)
        top = np.clip(np.arange(crop.shape[0]) / (crop.shape[0] * 0.08), 0, 1)
        crop[..., 3] = (al * edge[None, :] * (fade * top)[:, None]).clip(0, 255).astype(np.uint8)
        s = 600 / crop.shape[0]
        out.layer("beam_%d" % i, Image.fromarray(crop, "RGBA"), cx - cw * s / 2, -30, s)
        beams.append(dict(file="beam_%d" % i, pivot=P(cx, -30)))
    man["stage"]["beams"] = beams

    # ---- slots
    for kind, slots in SLOTS.items():
        man["slots"][kind] = [dict(at=list(xy), ppi=PPI[kind]) for xy in slots]

    # ---- drums: one picture each (every wrap uses it), placed at the factory kit's slot. The
    # left rack tom ("tom_alt") has a picture of its own.
    wraps = ["purple", "brass", "maple", "chrome", "walnut", "black"]
    drums = {"kick": ("kick", "kick", 0, DEFAULT["kick"], 0), "tom": ("tom_right", "rack2", 0, DEFAULT["rack"][0], 8),
             "tom_alt": ("tom_left", "rack2", 1, DEFAULT["rack"][1], 10),
             "floor": ("floor_tom", "floor", 0, DEFAULT["floor"], 16), "snare": ("snare", "snare", 0, DEFAULT["snare"], 5.5)}
    for kind, (src_name, slot_kind, slot, size, depth) in drums.items():
        img = piece(src_name)
        ell = kick_head(img) if kind == "kick" else drum_head(img)
        at = SLOTS[slot_kind][slot]
        radius = size * PPI[slot_kind]
        s = radius / ell[2]
        x, y = at[0] - ell[0] * s, at[1] - ell[1] * s
        info = out.layer(kind, img, x, y, s)
        head = [at[0], at[1], radius, ell[3] * s]
        entry = dict(anchor=P(*at), radius=round(radius, 2), size=size, head=[round(v, 2) for v in head],
                     wraps={w: kind for w in wraps})
        if kind != "kick":
            entry["shell"] = round(info["y"] + info["h"] - at[1], 2)
            entry["depth"] = depth
        man["kit"][kind] = entry

    # ---- cymbals: the disc on its post; stands per slot
    cymbals = {"crash": ("crash_right", "crash", 0, DEFAULT["crash"][0]), "crash_alt": ("crash_left", "crash", 1, DEFAULT["crash"][1]),
               "ride": ("ride", "ride", 0, DEFAULT["ride"]), "china": ("crash_left", "china", 0, DEFAULT["china"]),
               "splash": ("crash_right", "splash", 0, DEFAULT["splash"])}
    for kind, (src_name, slot_kind, slot, size) in cymbals.items():
        img = piece(src_name)
        ell, post = cymbal_disc(img)
        at = SLOTS[slot_kind][slot]
        radius = size * PPI[slot_kind]
        s = radius / ell[2]
        out.layer(kind, img, at[0] - ell[0] * s, at[1] - ell[1] * s, s)
        man["kit"][kind] = dict(anchor=P(*at), size=size, radius=round(radius, 2), file=kind,
                                ellipse=[at[0], at[1], round(radius, 2), round(ell[3] * s, 2)],
                                post=round(at[1] + (post - ell[1]) * s, 2))

    stand = piece("tom_stand")
    sa = rgba(stand)
    s_top = np.nonzero(sa[..., 3].max(1) > 128)[0].min()
    s_bot = np.nonzero(sa[..., 3].max(1) > 128)[0].max()
    s_cx = (lambda xs: (xs.min() + xs.max()) / 2)(np.nonzero(sa[s_top + 4, :, 3] > 128)[0])
    man["kit"]["stands"] = {}
    for kind in ("crash", "ride", "china", "splash"):
        man["kit"]["stands"][kind] = []
        disc = man["kit"][kind]
        for i, (x, y) in enumerate(SLOTS[kind]):
            # The stand runs from under the cymbal's post to the floor behind the kit.
            top = y + (disc["post"] - disc["anchor"][1]) - 4
            floor = FLOOR_BACK if y < 300 else FLOOR_FRONT - 20
            h = floor - top
            s = h / (s_bot - s_top)
            sx = min(s, 0.45)                       # tall stands keep a sensible tripod
            img = stand.resize((max(1, round(stand.width * sx / s)), stand.height)) if sx < s else stand
            scale_x = img.width / stand.width
            name = "stand_%s%d" % (kind, i)
            out.layer(name, img, x - s_cx * scale_x * s, top - s_top * s, s)
            man["kit"]["stands"][kind].append(dict(top=P(x, y), file=name))

    # ---- hi-hat: bottom and top cymbals and the stand
    hb, ht, hs = piece("hihat_bottom"), piece("hihat_top"), piece("hihat_stand")
    at = SLOTS["hihat"][0]
    radius = DEFAULT["hihat"] * PPI["hihat"]
    ellb, postb = cymbal_disc(hb)
    sb = radius / ellb[2]
    out.layer("hat_bottom", hb, at[0] - ellb[0] * sb, at[1] + 4 - ellb[1] * sb, sb)
    ellt, postt = cymbal_disc(ht)
    st_ = radius / ellt[2]
    out.layer("hat_top", ht, at[0] - ellt[0] * st_, at[1] - 4 - ellt[1] * st_, st_)
    ha = rgba(hs)
    rows = np.nonzero(ha[..., 3].max(1) > 128)[0]
    h_top, h_bot = rows.min(), rows.max()
    h_cx = (lambda xs: (xs.min() + xs.max()) / 2)(np.nonzero(ha[h_top + 4, :, 3] > 128)[0])
    top = at[1] + 4 + (postb - ellb[1]) * sb - 6
    s = (FLOOR_FRONT - 10 - top) / (h_bot - h_top)
    out.layer("hat_stand", hs, at[0] - h_cx * s, top - h_top * s, s)
    man["kit"]["hihat"] = dict(anchor=P(*at), size=DEFAULT["hihat"], top=P(at[0], at[1] - 4), bottom=P(at[0], at[1] + 4),
                               ellipse=[at[0], at[1], round(radius, 2), round(ellb[3] * sb, 2)], radius=round(radius, 2),
                               top_file="hat_top", bottom_file="hat_bottom", stand_file="hat_stand")

    # The snare's stand and the kick pedal are part of the picture under them.
    sn = man["kit"]["snare"]
    sstand = piece("snare_stand")
    ssa = rgba(sstand)
    rows = np.nonzero(ssa[..., 3].max(1) > 128)[0]
    top = sn["anchor"][1] + sn["shell"] - 10
    s = (FLOOR_FRONT - top) / (rows.max() - rows.min())
    cx = (lambda xs: (xs.min() + xs.max()) / 2)(np.nonzero(ssa[rows.max() - 4, :, 3] > 128)[0])
    out.layer("snare_stand", sstand, sn["anchor"][0] - cx * s, top - rows.min() * s, s)
    man["kit"]["snare"]["stand_file"] = "snare_stand"
    pedal = piece("kick_pedal")
    s = 120 / pedal.height
    out.layer("kick_pedal", pedal, 640 + 40, FLOOR_FRONT + 14 - pedal.height * s, s)
    man["kit"]["kick"]["pedal_file"] = "kick_pedal"

    # ---- the panda: poses lined up on the head, each also cut into its head and its body (so
    # the head can nod and tilt on its own); faces laid over each pose's own face, lined up on
    # the glasses. A face is placed for the idle pose; each pose says how to move it.
    pan = man["panda"]
    pan["head"] = dict(anchor=P(*HEAD), radius=HEAD_RX)
    pan["poses"] = {}
    glasses = {}
    for pose in POSES:
        name = "pose_" + pose
        img = clean_pose(piece(name), name)
        ell = HEADS.get(name) or head_of(img, 0.6)
        s = HEAD_RX / ell[2]
        x, y = HEAD[0] - ell[0] * s, HEAD[1] - ell[1] * s
        head, body = split_head(img, ell)
        out.layer(name + "_head", head, x, y, s)
        out.layer(name + "_body", body, x, y, s)
        g = glasses_box(img, ell)
        glasses[pose] = (x + g[0] * s, y + g[1] * s, x + g[2] * s, y + g[3] * s)
        pan["poses"][pose] = dict(head_file=name + "_head", body_file=name + "_body",
                                  head=[HEAD[0], HEAD[1], HEAD_RX, round(ell[3] * s, 2)],
                                  neck=P(HEAD[0], HEAD[1] + ell[3] * s * 0.92),
                                  glasses=[round(v, 2) for v in glasses[pose]])
    ref = glasses["idle"]
    for pose, g in glasses.items():
        k = (g[2] - g[0]) / (ref[2] - ref[0])
        pan["poses"][pose]["face"] = [round(k, 4), round((g[0] + g[2]) / 2 - k * (ref[0] + ref[2]) / 2, 2),
                                      round((g[1] + g[3]) / 2 - k * (ref[1] + ref[3]) / 2, 2)]
    pan["poses"]["cheer"]["own_face"] = True     # the cheer keeps its own winking grin
    pan["faces"] = {}
    for face in FACES + ["blink"]:
        src_img = piece("pose_blink") if face == "blink" else piece("face_" + face)
        ell = (HEADS.get("pose_blink") or head_of(clean_pose(src_img, "pose_blink"), 0.6)) if face == "blink" else head_of(src_img, 0.9)
        patch, g = face_patch(src_img, ell)
        s = (ref[2] - ref[0]) / (g[2] - g[0])
        name = "face_" + face
        out.layer(name, patch, (ref[0] + ref[2]) / 2 - (g[0] + g[2]) / 2 * s, (ref[1] + ref[3]) / 2 - (g[1] + g[3]) / 2 * s, s)
        pan["faces"][face] = dict(file=name)

    # The whole happy head (ears and all) for the logo badge and the app icon.
    src_img = piece("face_happy")
    ell = head_of(src_img, 0.9)
    a = rgba(src_img).copy()
    chin = int(ell[1] + ell[3] * 1.04)
    a[..., 3] = (a[..., 3] * np.clip((chin - np.arange(a.shape[0])) / 14, 0, 1)[:, None]).astype(np.uint8)
    badge = Image.fromarray(a[:chin + 1], "RGBA")
    out.layer("badge", badge, 0, 0, 256 / badge.width)
    pan["badge"] = "badge"

    # ---- effects
    fx = {}
    for name, height in (("blur_1", 70), ("blur_2", 50), ("blur_3", 70), ("hit_spark", 90), ("heart_red", 30),
                         ("heart_pink", 30), ("heart_yellow", 30), ("glow_particles", 120), ("heart_particles", 130)):
        img = piece(name)
        s = height / img.height
        out.layer("fx_" + name, img, 0, 0, s)
        fx[name] = "fx_" + name
    pan["fx"] = fx

    with open(os.path.join(outdir, "manifest.json"), "w") as f:
        json.dump(man, f, indent=1)
    print("wrote", len(out.files), "layers to", outdir)


if __name__ == "__main__":
    main(*sys.argv[1:3])
