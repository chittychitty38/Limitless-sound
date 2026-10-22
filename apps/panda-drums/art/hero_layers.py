"""
Separates the Panda Drums hero picture (the panda at the kit) into the layers the stage draws,
so the stage is that picture, alive.

    HERO_SCALE=2.725 ESRGAN=RealESRGAN_x4plus.pth LAMA=big-lama.pt python hero_layers.py hero.jpg <outdir>

The picture is upscaled 4x with Real-ESRGAN first (kept as <outdir>/hero4x.png; an already
upscaled picture is used as it is).

Every piece is traced here in the hero's own pixels (1206 x 667): each cymbal's disc, each drum,
the panda's head, torso, sleeves, arms and fists with their sticks, and the china's stand where
it stands in front of the floor tom. Inside its outline a piece takes everything that isn't the
pink wall. The wall is spread smoothly back in behind everything that moves; LaMa paints in the
parts of a piece that another one hid (the crash behind the ride, the bottom hi-hat under the top one, the floor tom
behind the china's stand, the shirt under the arms and the chin), and a guided filter softens
each edge (fur, cymbal rims), with the wall's pink taken back out of the edge colour. The kit as
it stands in the room (its stands, the drums, his legs behind them) is a layer of its own, with
the outer cymbals' stands apart, and backdrop.png is the room without it.

Writes <name>.png (RGBA, 2x the hero) for every layer and layers.json: each layer's box and the
rig's points (shoulders, wrists, stick tips), in hero pixels.
"""

import json
import os
import sys

import cv2
import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

SCALE = float(os.environ.get("HERO_SCALE", "2.18"))   # working resolution (2.18: the stage at 2x)
HERO_W, HERO_H = 1206, 667


def ellipse(cx, cy, a, b, angle=0.0):
    return ("ellipse", cx, cy, a, b, angle)


def poly(*pts):
    return ("poly", pts)


def line(x0, y0, x1, y1, w):
    return ("line", x0, y0, x1, y1, w)


def rect(x0, y0, x1, y1):
    return poly((x0, y0), (x1, y0), (x1, y1), (x0, y1))


# Where the heart lights' string passes behind something that moves (hero x, from and to).
STRING_GAPS = [(596, 704)]

# Where the hi-hat's top plate meets the bottom one, tip to tip (hero pixels).
HAT_SPLIT = [(878, 267.5), (935, 266.5), (997, 262.5), (1065, 262.5), (1112, 265.5)]

# The pieces, back to front, in hero pixels. Options: "all" takes every pixel inside a shape (a
# drum head, whatever its colour); "complete" is the piece's whole shape, for painting in what
# was hidden; "cream" keeps only fur and face low on the head (not the collar).
PIECES = [
    ("ride", [ellipse(200, 218, 144, 34, 9), rect(180, 172, 212, 200)], {"complete": [ellipse(200, 218, 140, 31, 9)], "all": [ellipse(200, 218, 140, 31, 9)]}),
    ("crash_alt", [ellipse(352, 178, 144, 42, 11), rect(312, 126, 344, 164)], {"complete": [ellipse(352, 178, 140, 39, 11)], "all": [ellipse(352, 178, 140, 39, 11)]}),
    ("crash", [ellipse(1050, 127, 143, 35, -11), rect(1036, 76, 1068, 112)], {"complete": [ellipse(1050, 127, 139, 32, -11)], "all": [ellipse(1050, 127, 139, 32, -11)]}),
    # The hi-hat's plates are lenses, not ellipses: split along the line where they meet, tip to tip.
    ("hat_bottom", [poly(*HAT_SPLIT, (1112, 278), (1060, 281), (1025, 287), (975, 287), (935, 282), (878, 279))],
     {"complete": [ellipse(998, 272, 106, 9, 1)]}),
    ("hat_top", [poly((878, 250), *HAT_SPLIT, (1112, 250), (1060, 243), (1013, 238), (1013, 208), (989, 208), (989, 238), (935, 243))], {}),
    ("torso", [poly((560, 220), (612, 226), (700, 236), (790, 238), (842, 262), (862, 300), (860, 338), (556, 338), (560, 300))], {}),
    ("sleeve_r", [poly((568, 220), (604, 226), (610, 262), (604, 308), (566, 310))], {"purple": True}),
    ("sleeve_l", [poly((798, 262), (846, 264), (858, 290), (852, 312), (800, 306))], {"purple": True}),
    ("head", [ellipse(720, 162, 146, 118), ellipse(650, 51, 52, 49), ellipse(856, 101, 53, 53),
              ellipse(636, 228, 46, 24), ellipse(806, 242, 46, 22)],
     {"all": [ellipse(720, 161, 132, 104)], "no_collar_below": 228}),
    ("floor", [poly((295, 370), (306, 360), (522, 360), (530, 372), (530, 552), (520, 568), (305, 568), (295, 552))], {}),
    ("drum_center", [poly((552, 322), (560, 316), (738, 316), (745, 324), (745, 396), (552, 396))],
     {"complete": [poly((556, 318), (742, 318), (742, 392), (556, 392))]}),
    ("drum_right", [poly((748, 354), (756, 348), (946, 348), (952, 356), (952, 444), (748, 444))], {}),
    ("kick", [ellipse(689, 520, 176, 150), poly((518, 400), (560, 392), (560, 640), (518, 620))], {"all": [ellipse(690, 520, 150, 124)]}),
    ("arm_r", [poly((481, 188), (568, 186), (580, 222), (576, 314), (520, 318), (462, 284), (465, 214), (473, 199)), line(551, 96, 510, 264, 18)], {"not_purple": True}),
    ("arm_l", [poly((812, 274), (872, 272), (898, 300), (898, 349), (812, 354), (802, 300)), line(848, 336, 963, 299, 18)], {"not_purple": True}),
    ("front_stand", [rect(438, 345, 468, 560), poly((452, 505), (580, 667), (325, 667))], {}),
    ("china", [ellipse(452, 325, 148, 27, 5), rect(441, 281, 472, 312)], {"no_fur": True, "all": [ellipse(452, 326, 140, 21, 5), rect(440, 283, 475, 312)]}),
]

# Pieces that are completed with LaMa where others hid them, and what they're painted against.
COMPLETE = ["ride", "crash_alt", "crash", "hat_bottom", "drum_center"]
# Pieces that move (cymbals swing, the panda plays): the room behind them is painted in. The drums
# and the china's stand never move, so the room keeps the picture's pixels behind them.
MOVING = ["ride", "crash_alt", "crash", "hat_bottom", "hat_top", "torso", "head", "arm_r", "arm_l", "china"]

# The torso's whole outline: under the arms, under the chin and down behind the drums.
TORSO_SHAPE = poly((562, 224), (606, 228), (650, 236), (720, 240), (790, 236), (846, 262), (866, 300), (866, 410),
                   (558, 410), (558, 300))
FLOOR_HIDDEN = rect(436, 362, 470, 568)      # the floor tom behind the china's stand

# The rig, in hero pixels: where each arm leaves its sleeve, where the fist meets the arm, and
# the stick: a point at the fist and the tip.
RIG = {
    "shoulder_r": (588, 264), "wrist_r": (546, 258), "fist_r": (522, 232), "tip_r": (549, 100),
    "shoulder_l": (836, 288), "wrist_l": (852, 312), "fist_l": (850, 322), "tip_l": (955, 301),
}
FIST_R = poly((482, 194), (564, 190), (570, 256), (540, 272), (482, 266))     # the right fist, cut from its arm
SHAFT_R = poly((530, 90), (570, 90), (546, 203), (514, 203))                   # the stick above the fist
GRIP, TIP = (526.0, 200.0), (549.0, 100.0)    # where the stick leaves the fist, and its tip
PIVOT_IN, BUTT_IN = 24.0, 66.0          # down the stick from the grip: the fulcrum in the fist, and the butt end
STICK_W = 16                            # the stick's width, with room for its soft edge
STICK_R = line(551, 96, 510, 264, 18)
# The left fist: it holds its stick level, pointing at the hi-hat, laid across its front.
FIST_L = poly((812, 280), (868, 279), (886, 298), (889, 340), (875, 355), (820, 355), (805, 337), (805, 295))
STICK_L = line(851, 331, 892, 319, 16)                                          # the stick where it crosses the fist
PIVOT_L, TIP_L = (847.2, 331.7), (954.0, 301.0)  # the left stick's fulcrum in the fist, and its tip
# Where each arm comes out of its sleeve and meets its fist, and the fur the arms are made of.
SHOULDERS = [(588, 266), (800, 296)]
WRISTS = [(546, 258), (819, 316)]
FUR_PATCH = (822, 296, 846, 326)        # plain fur on the left fist
FUR_R = 30                              # an arm's radius (hero pixels)

# The kit as it stands in the room (the stands, the drums, the pedals and his legs behind them) is
# cut out too, so the plugin can draw the whole kit bigger than the picture's. Where it may be, and
# the row where the wall ends and the floor (and the platform's edge) begins.
# (clear of the plants: the bamboo on the left, the palm behind the crash's stand on the right)
KIT_AREA = poly((150, 140), (1153, 140), (1153, 480), (1206, 500), (1206, HERO_H), (70, HERO_H), (70, 560), (150, 470))
SPECK_AREA = rect(120, 64, 1150, HERO_H)
# The outer cymbals' stands, cut apart from the rest of the kit (kit_left, kit_right) so the plugin
# can grow them with the kit but keep them within his reach: the two on the left (with the leg the
# nearer one puts out toward the floor tom), and the crash's on the right (not the hi-hat's).
STANDS_LEFT = [poly((70, 140), (298, 140), (298, 575), (270, HERO_H), (70, HERO_H)), line(262, 520, 352, 660, 16)]
STANDS_RIGHT = [poly((1036, 140), (1206, 140), (1206, HERO_H), (1060, HERO_H), (1100, 560), (1100, 252), (1036, 196))]
FLOOR_Y = 520


def draw_shape(mask, shape, value=255):
    s = SCALE
    kind = shape[0]
    if kind == "ellipse":
        _, cx, cy, a, b, ang = shape
        cv2.ellipse(mask, (int(cx * s), int(cy * s)), (int(a * s), int(b * s)), ang, 0, 360, value, -1)
    elif kind == "poly":
        pts = np.array([[int(x * s), int(y * s)] for x, y in shape[1]], np.int32)
        cv2.fillPoly(mask, [pts], value)
    elif kind == "line":
        _, x0, y0, x1, y1, w = shape
        cv2.line(mask, (int(x0 * s), int(y0 * s)), (int(x1 * s), int(y1 * s)), value, int(w * s))


def region(shapes, hw):
    m = np.zeros(hw, np.uint8)
    for sh in shapes:
        draw_shape(m, sh)
    return m > 0


def hsv_of(rgb):
    hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV).astype(int)
    return hsv[..., 0], hsv[..., 1], hsv[..., 2]


def wall_of(rgb):
    """The pink wall and floor."""
    h, s, v = hsv_of(rgb)
    return ((h >= 158) | (h <= 6)) & (s >= 28) & (s <= 175) & (v >= 105)


def purple_of(rgb):
    h, s, v = hsv_of(rgb)
    return (h >= 118) & (h <= 158) & (s >= 70) & (v >= 40)


def fill_holes(mask):
    m = np.pad(mask.astype(np.uint8), 1)
    cv2.floodFill(m, None, (0, 0), 2)
    return mask | (m[1:-1, 1:-1] == 0)


def wall_fill(rgb, hole, wall, feather=True, clear=31, ramp=None):
    """The room behind the kit and the panda: the wall's own colours spread smoothly into the hole
    from all round it (normalised convolution, finest scale that reaches), with its grain. Outside
    the hole the picture stays as it is (feather=False: not a pixel of it changes). ramp: where in
    the hole the fill eases into the picture's own wall (its weight, 0..1)."""
    # Only wall clear of the pieces: their shaded rims can pass for pink.
    near = cv2.dilate(hole.astype(np.uint8), np.ones((clear, clear), np.uint8)) > 0
    known = (wall & ~near).astype(np.float32)
    out = rgb.astype(np.float32).copy()
    img = rgb.astype(np.float32) * known[..., None]
    filled = np.zeros(hole.shape, bool)
    for sigma in (12, 30, 70, 160, 400):
        k = int(sigma * 3) | 1
        wsum = cv2.GaussianBlur(known, (k, k), sigma)
        csum = cv2.GaussianBlur(img, (k, k), sigma)
        ok = hole & ~filled & (wsum > 0.08)
        out[ok] = csum[ok] / wsum[ok, None]
        filled |= ok
    rest = hole & ~filled
    if rest.any():
        out[rest] = (img.sum((0, 1)) / max(1.0, known.sum()))
    # The wall's fine grain, so the fill isn't flat.
    rng = np.random.default_rng(7)
    grain = cv2.GaussianBlur(rng.normal(0, 2.2, hole.shape).astype(np.float32), (0, 0), 1.2)
    out[hole] += grain[hole, None]
    edge = cv2.GaussianBlur(hole.astype(np.float32), (0, 0), 3) if feather else hole.astype(np.float32)
    if ramp is not None:
        edge = ramp
    out = rgb * (1 - edge[..., None]) + out * edge[..., None]
    return out.clip(0, 255).astype(np.uint8)


def smooth_fill(rgb, hole, known):
    """The wall carried smoothly into a hole from the known wall round it: a membrane (Navier-Stokes
    inpainting) at an eighth of the size, where the wall is nothing but a gradient, brought back up
    smooth. No seams, no scales stepping."""
    f = 8
    h, w = hole.shape
    small = cv2.resize(rgb, (w // f, h // f), interpolation=cv2.INTER_AREA)
    ks = cv2.resize(known.astype(np.float32), (w // f, h // f), interpolation=cv2.INTER_AREA)
    unknown = (ks < 0.6).astype(np.uint8)
    # what's known there: the known pixels' own average, not the pieces' colours mixed in
    num = cv2.resize(rgb.astype(np.float32) * known[..., None], (w // f, h // f), interpolation=cv2.INTER_AREA)
    small = np.where(unknown[..., None] > 0, small, num / np.maximum(ks, 1e-3)[..., None]).clip(0, 255).astype(np.uint8)
    filled = cv2.inpaint(small, unknown, 6, cv2.INPAINT_NS)
    big = cv2.resize(filled.astype(np.float32), (w, h), interpolation=cv2.INTER_CUBIC)
    return cv2.GaussianBlur(big, (0, 0), f * 0.6)


def light_string(out, rgb, gone):
    """The heart lights' string, carried on behind what was painted out (it sags between the pins:
    a curve through where it shows on either side)."""
    s = SCALE
    grey = rgb.astype(np.float32).mean(2)
    for x0, x1 in STRING_GAPS:
        pts = []
        for x in list(range(x0 - 40, x0, 2)) + list(range(x1, x1 + 40, 2)):
            col = grey[int(24 * s):int(52 * s), int(x * s)]
            y = int(np.argmin(col)) + int(24 * s)
            if col.min() < 140 and not gone[y, int(x * s)]:
                pts.append((x * s, y))
        if len(pts) < 8:
            continue
        xs, ys = np.array(pts, np.float32).T
        c = np.polyfit(xs, ys, 2)
        colour = np.median([rgb[int(y), int(x)] for x, y in pts], axis=0)
        canvas = np.zeros(gone.shape, np.float32)
        line = np.array([[x, np.polyval(c, x)] for x in np.arange(x0 * s - 20, x1 * s + 20, 2)], np.float32)
        cv2.polylines(canvas, [np.round(line * 16).astype(np.int32)], False, 1.0, max(1, int(2.4 * s)), cv2.LINE_AA, shift=4)
        canvas = cv2.GaussianBlur(canvas, (0, 0), 0.7) * gone
        out[:] = out * (1 - canvas[..., None]) + colour * canvas[..., None]


def guided(I, p, r, eps):
    """He et al.'s guided filter, grey guide."""
    mean = lambda x: cv2.boxFilter(x, -1, (2 * r + 1, 2 * r + 1))
    mI, mp = mean(I), mean(p)
    a = (mean(I * p) - mI * mp) / (mean(I * I) - mI * mI + eps)
    b = mp - a * mI
    return mean(a) * I + mean(b)


_lama = None


def lama(rgb, mask):
    """Inpaint rgb (uint8 HxWx3) where mask is set, with LaMa (big-lama TorchScript, $LAMA)."""
    global _lama
    import torch
    if _lama is None:
        _lama = torch.jit.load(os.environ["LAMA"], map_location="cpu").eval()
    h, w = rgb.shape[:2]
    ph, pw = (8 - h % 8) % 8, (8 - w % 8) % 8
    img = torch.from_numpy(np.pad(rgb, ((0, ph), (0, pw), (0, 0)), mode="edge").transpose(2, 0, 1)).float().unsqueeze(0) / 255
    m = torch.from_numpy((np.pad(mask, ((0, ph), (0, pw))) > 0).astype(np.float32))[None, None]
    with torch.no_grad():
        out = _lama(img, m)
    return (out[0].permute(1, 2, 0).numpy().clip(0, 1) * 255).astype(np.uint8)[:h, :w]


def lama_crop(rgb, mask, pad=96):
    """LaMa on just the part of the picture around the mask."""
    ys, xs = np.nonzero(mask)
    if not len(xs):
        return rgb.copy()
    y0, y1 = max(0, ys.min() - pad), min(rgb.shape[0], ys.max() + pad)
    x0, x1 = max(0, xs.min() - pad), min(rgb.shape[1], xs.max() + pad)
    out = rgb.copy()
    out[y0:y1, x0:x1] = lama(rgb[y0:y1, x0:x1], mask[y0:y1, x0:x1])
    return out


def complete_over_green(rgb, alpha, shape_mask):
    """Paint in a piece where it was hidden: over green, LaMa fills the missing part of its shape;
    what comes back green is outside it."""
    missing = shape_mask & (alpha < 0.5)
    if not missing.any():
        return rgb, alpha
    green = np.array([0, 255, 0], np.float32)
    comp = (rgb * alpha[..., None] + green * (1 - alpha[..., None])).astype(np.uint8)
    res = lama_crop(comp, cv2.dilate(missing.astype(np.uint8), np.ones((5, 5), np.uint8)) > 0).astype(np.float32)
    r, g, b = res[..., 0], res[..., 1], res[..., 2]
    fill = np.clip(1 - (g - np.maximum(r, b) - 8) / 36, 0, 1)
    res[..., 1] = np.minimum(g, np.maximum(r, b))
    rgb, alpha = rgb.copy(), alpha.copy()
    rgb[missing] = res[missing].astype(np.uint8)
    alpha[missing] = fill[missing] * 1.0
    return rgb, alpha


def soften(rgb, mask, room, fur=None):
    """A soft alpha for a hard mask (edge-aware), and the edge's colour with what's behind it taken
    out (room: the picture as everything behind this piece draws it). fur: a band round the piece
    where its last tufts are told from the wall by how far they are from it in colour."""
    grey = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY).astype(np.float32) / 255
    a = guided(grey, mask.astype(np.float32), 3, 1e-3)
    inner = cv2.erode(mask.astype(np.uint8), np.ones((5, 5), np.uint8)) > 0
    outer = cv2.dilate(mask.astype(np.uint8), np.ones((5, 5), np.uint8)) > 0
    a = np.where(inner, 1.0, np.where(outer, np.clip(a, 0, 1), 0.0)).astype(np.float32)
    if fur is not None:
        d = np.linalg.norm(rgb.astype(np.float32) - room.astype(np.float32), axis=2)
        tuft = np.clip((d - 8) / 45, 0, 1)
        a = np.where(fur & ~inner, np.maximum(a, tuft), a).astype(np.float32)
        outer = outer | (fur & (tuft > 0))
    # Unmix: I = a F + (1 - a) B  ->  F = (I - (1 - a) B) / a, at the edge only.
    F = rgb.astype(np.float32)
    edge = outer & ~inner & (a > 0.05)
    B = room.astype(np.float32)
    F[edge] = np.clip((F[edge] - (1 - a[edge, None]) * B[edge]) / a[edge, None], 0, 255)
    return F.astype(np.uint8), a


def upscaled(src, outdir):
    """The hero picture at 4x: Real-ESRGAN ($ESRGAN), done once."""
    img = Image.open(src).convert("RGB")
    if img.width >= HERO_W * 2:
        return img
    cached = os.path.join(outdir, "hero4x.png")
    if os.path.exists(cached):
        return Image.open(cached).convert("RGB")
    import torch
    from sheet_cut import RRDBNet, upscale
    torch.set_num_threads(os.cpu_count() or 4)
    model = RRDBNet()
    state = torch.load(os.environ["ESRGAN"], map_location="cpu")
    model.load_state_dict(state.get("params_ema", state.get("params", state)))
    model.eval()
    print("upscaling the picture 4x", flush=True)
    out = upscale(model, np.asarray(img).astype(np.float32) / 255)
    big = Image.fromarray((out * 255 + 0.5).clip(0, 255).astype(np.uint8))
    big.save(cached)
    return big


def main(src, outdir):
    os.makedirs(outdir, exist_ok=True)
    W, H = int(round(HERO_W * SCALE)), int(round(HERO_H * SCALE))
    rgb = np.asarray(upscaled(src, outdir).resize((W, H), Image.LANCZOS)).copy()
    hw = (H, W)
    wall = wall_of(rgb)
    purple = purple_of(rgb)
    hsv_h, hsv_s, hsv_v = hsv_of(rgb)
    yy = np.mgrid[0:H, 0:W][0]

    # ---- who owns each pixel: front to back, a piece in front keeps what it covers
    taken = np.zeros(hw, bool)
    masks = {}
    for name, shapes, opts in reversed(PIECES):
        reg = region(shapes, hw)
        m = reg & ~wall
        if "all" in opts:
            m |= region(opts["all"], hw)
        if opts.get("purple"):
            m &= purple
        if opts.get("not_purple"):
            m &= ~purple
            # Not a cymbal's rim showing beside the fur, only the stick's wood.
            # (bright bronze: lit fur is brownish too, but darker)
            gold = (hsv_h >= 6) & (hsv_h <= 30) & (hsv_s > 70) & (hsv_v > 135)
            m &= ~gold | region([sh for sh in shapes if sh[0] == "line"], hw)
        if "no_collar_below" in opts:
            m &= ~((yy > opts["no_collar_below"] * SCALE) & purple)
        if opts.get("no_fur"):
            m &= ~((hsv_v < 80) & ((hsv_h < 5) | (hsv_h > 34) | (hsv_s < 90))) | (region(opts["all"], hw) if "all" in opts else False)
        m = cv2.morphologyEx(m.astype(np.uint8), cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8)) > 0
        if name not in ("sleeve_r", "sleeve_l"):
            m = fill_holes(m)
        m &= reg
        if name not in ("sleeve_r", "sleeve_l"):
            m &= ~taken
            if name in ("arm_r", "arm_l"):
                m = largest(m)      # what isn't joined to the arm (a cymbal's dark rim) goes to the piece behind
            taken |= m
        masks[name] = m
    # The sleeves are copies of the torso's own pixels, drawn again over the arms.
    masks["sleeve_r"] &= masks["torso"]
    masks["sleeve_l"] &= masks["torso"]

    # ---- the room: what moves is painted out of it (the cymbals swing, the panda leans and plays);
    # the kit that stands still is cut from it after (still_kit).
    moving = [n for n in MOVING if n in masks]
    own = np.zeros(hw, bool)
    for name in moving:
        own |= masks[name]
    # Round them a ring goes too: their fur's last tufts, their shadow on the wall, and the wall
    # itself (easing from the fill into the picture's own across it, so no edge shows when they
    # move). Not the drums, which don't move, nor a stand beside a cymbal.
    static = np.zeros(hw, bool)
    owned = np.zeros(hw, bool)
    for name in ("floor", "drum_center", "drum_right", "kick", "front_stand"):
        static |= masks[name]
    for name, _, _ in PIECES:
        owned |= masks[name]
    panda = masks["head"] | masks["torso"] | masks["arm_r"] | masks["arm_l"]
    ring_px = int(6 * SCALE) | 1
    # The panda's ring takes his tufts and his shadow (his layers take the tufts back, matted);
    # a cymbal's only the wall round it (never a stand).
    # (no stand comes this close to him; his white fur's tips look like chrome, so they're kept)
    fur_ring = (cv2.dilate(panda.astype(np.uint8), np.ones((ring_px, ring_px), np.uint8)) > 0) & ~owned & ~static
    cym_px = int(3 * SCALE) | 1
    near_cym = cv2.dilate((own & ~panda).astype(np.uint8), np.ones((cym_px * 2 + 1, cym_px * 2 + 1), np.uint8)) > 0
    fur_ring &= ~near_cym          # a cymbal's own pink-lit rim isn't his fur
    cym_ring = (cv2.dilate((own & ~panda).astype(np.uint8), np.ones((cym_px, cym_px), np.uint8)) > 0) & wall & ~owned
    ring = fur_ring | cym_ring
    gone = own | ring
    dist = cv2.distanceTransform((~own).astype(np.uint8), cv2.DIST_L2, 5)
    ease = np.clip(1.5 - 1.5 * dist / (ring_px / 2 + 1), 0, 1)
    ramp = np.where(own | (fur_ring & ~wall), 1.0, np.where(ring, ease, 0.0)).astype(np.float32)
    print("room: painting out", int(gone.sum()), "px", flush=True)
    known = wall & ~(cv2.dilate(gone.astype(np.uint8), np.ones((5, 5), np.uint8)) > 0)
    fill = smooth_fill(rgb, gone, known)
    rng = np.random.default_rng(7)
    fill += cv2.GaussianBlur(rng.normal(0, 2.2, hw).astype(np.float32), (0, 0), 1.2)[..., None]
    light_string(fill, rgb, gone)
    room = (rgb * (1 - ramp[..., None]) + fill * ramp[..., None]).clip(0, 255).astype(np.uint8)
    Image.fromarray(room).save(os.path.join(outdir, "room.png"))

    # ---- each piece, back to front: soft edge, its colour unmixed from exactly what's drawn
    # behind it, and completed only where a piece in front hides it.
    info = {}
    still_kit(room, masks, panda, gone, outdir, info)
    behind = room.astype(np.float32)
    order = [p for p in PIECES if p[0] not in ("sleeve_r", "sleeve_l")]
    in_front = {}
    for i, (name, _, _) in enumerate(order):
        cover = np.zeros(hw, bool)
        for later, _, _ in order[i + 1:]:
            cover |= masks[later]
        in_front[name] = cv2.dilate(cover.astype(np.uint8), np.ones((5, 5), np.uint8)) > 0
    for name, shapes, opts in PIECES:
        m = masks[name]
        if not m.any():
            continue
        if name in ("arm_r", "arm_l"):
            m = largest(m)
        if name in ("sleeve_r", "sleeve_l"):
            # Drawn over a playing arm, never at rest: its edge comes off the shirt it's cut from.
            F, a = soften(rgb, m, behind)
            save_layer(np.dstack([F, (a * 255 + 0.5).clip(0, 255).astype(np.uint8)]), name, outdir, info)
            continue
        fur = None
        if name in ("head", "torso", "arm_r", "arm_l"):
            fur = (cv2.dilate(m.astype(np.uint8), np.ones((ring_px, ring_px), np.uint8)) > 0) & fur_ring
        F, a = soften(rgb, m, behind, fur)
        hidden = in_front[name]
        if name in COMPLETE:
            F, a = complete_over_green(F, a, region(opts["complete"], hw) & (hidden | m))
        if name == "floor":
            F, a = complete_over_green(F, a, region([FLOOR_HIDDEN], hw) & region(shapes, hw) & hidden)
        if name == "torso":
            # Under the arms, the chin and the drums: the shirt goes on (only where they hide it).
            shape = region([TORSO_SHAPE], hw) & (hidden | m)
            for other in ("arm_r", "arm_l", "head", "drum_center", "drum_right", "kick", "china", "floor"):
                near = cv2.dilate(masks[other].astype(np.uint8), np.ones((7, 7), np.uint8)) > 0
                a = np.where(near & shape & ~cv2.erode(m.astype(np.uint8), np.ones((9, 9), np.uint8)).astype(bool), 0.0, a)
            F, a = complete_over_green(F, a, shape)
        out = np.dstack([F, (a * 255 + 0.5).clip(0, 255).astype(np.uint8)])
        # The arms as the picture has them are what he looks like at rest.
        save_layer(out, {"arm_r": "rest_r", "arm_l": "rest_l"}.get(name, name), outdir, info)
        af = a[..., None]
        behind = af * F.astype(np.float32) + (1 - af) * behind

    # ---- the rig: the right fist (with the stick where it crosses the fingers), the stick on
    # its own (straight, upright, from the grip to the tip), and the arm
    hsv = (hsv_h, hsv_s, hsv_v)
    save_layer(clean_fist(rgb, masks["arm_r"], room, hsv, FIST_R, [STICK_R], [SHAFT_R], [STICK_R]), "fist", outdir, info)
    save_layer(clean_fist(rgb, masks["arm_l"], room, hsv, FIST_L, [STICK_L], [], [line(848, 336, 963, 299, 18)]), "fist_l", outdir, info)
    save_layer(clean_stick(rgb, masks["arm_r"], room), "stick", outdir, info, keep_box=True)
    save_layer(fur_ball(rgb), "fur", outdir, info, keep_box=True)

    rig = {k: list(v) for k, v in RIG.items()}
    rig.update(grip=list(GRIP), tip=list(TIP), pivot_in=PIVOT_IN, butt_in=BUTT_IN, pivot_l=list(PIVOT_L), tip_l=list(TIP_L),
               shoulders=[list(p) for p in SHOULDERS], wrists=[list(p) for p in WRISTS], fur_r=FUR_R)
    with open(os.path.join(outdir, "layers.json"), "w") as f:
        json.dump(dict(scale=SCALE, size=[HERO_W, HERO_H], layers=info, rig=rig), f, indent=1)
    print("wrote", len(info), "layers", flush=True)


def still_kit(room, masks, panda, gone, outdir, info):
    """The kit as the room has it, as a layer of its own (kit_still), and the room without it
    (backdrop.png): the wall carried in smoothly from round it, the floor carried on along its
    rows (it runs across the picture; a fill that looks round would draw the legs back in). The
    chrome mirrors the pink room, so a stand is found by its edges, filled across, and its layer
    takes whatever differs from the room behind it."""
    s = SCALE
    hw = room.shape[:2]
    h, sat, v = hsv_of(room)
    yy = np.mgrid[0:hw[0], 0:hw[1]][0]
    # The room behind the kit: the pink wall; lower down the floor and the platform's dark edge,
    # all of them pink however dark; the plants.
    pink = ((h >= 150) | (h <= 6)) & (sat >= 45) & (v >= 30)
    green = (h >= 30) & (h <= 95) & (sat >= 40)
    behind = np.where(yy >= FLOOR_Y * s, pink, wall_of(room)) | green
    area = region([KIT_AREA], hw)
    core = area & ~behind
    # A leg's two edges, and the pink it mirrors between them.
    k = int(9 * s) | 1
    core = cv2.morphologyEx(core.astype(np.uint8), cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k))) > 0
    for name in ("floor", "drum_center", "drum_right", "kick", "front_stand"):
        core |= masks[name]
    core &= area & ~green
    # Specks (a cymbal's last flecks) aren't the kit; they go from the room too, as the bigger
    # kit's cymbals no longer hide them.
    n, lab, st, _ = cv2.connectedComponentsWithStats(core.astype(np.uint8), connectivity=8)
    big = np.zeros(n, bool)
    big[1:] = st[1:, cv2.CC_STAT_AREA] > 300 * s * s
    specks = region([SPECK_AREA], hw) & ~behind & ~big[lab] & ~panda
    core = big[lab]
    top = int((FLOOR_Y - 60) * s)
    grown = cv2.dilate(core.astype(np.uint8), np.ones((int(5 * s) | 1,) * 2, np.uint8)) > 0
    # Low down a leg's shaded side can pass for the floor: the hole is wider there.
    grown |= (cv2.dilate(core.astype(np.uint8), np.ones((int(10 * s) | 1,) * 2, np.uint8)) > 0) & (yy >= top) & area
    hole = grown | (cv2.dilate(specks.astype(np.uint8), np.ones((int(5 * s) | 1,) * 2, np.uint8)) > 0)
    # The wall: carried in smoothly from the picture's own wall clear of everything, over the kit
    # and over whatever was painted in already (behind him and the cymbals), so the room the
    # bigger kit leaves showing is the wall and nothing else.
    near = cv2.dilate((hole | gone).astype(np.uint8), np.ones((int(4 * s) | 1,) * 2, np.uint8)) > 0
    known = wall_of(room) & ~near
    redo = hole | (region([SPECK_AREA], hw) & (yy < FLOOR_Y * s) & ~known & ~green)
    fill = smooth_fill(room, redo, known)
    rng = np.random.default_rng(5)
    fill += cv2.GaussianBlur(rng.normal(0, 2.2, hw).astype(np.float32), (0, 0), 1.2)[..., None]
    # The floor: along its rows.
    wide = cv2.dilate(hole.astype(np.uint8), np.ones((int(6 * s) | 1,) * 2, np.uint8)) > 0
    painted = row_fill(room, hole, behind & ~wide & ~green, top)
    w = np.clip((yy - (FLOOR_Y - 40) * s) / (30 * s), 0, 1)[..., None]
    fill = fill * (1 - w) + painted * w
    backdrop = np.where(redo[..., None], fill, room).clip(0, 255).astype(np.uint8)
    Image.fromarray(backdrop).save(os.path.join(outdir, "backdrop.png"))
    # Its layer: the core, soft at the edge, and whatever else in the hole isn't the room behind.
    _, a = soften(room, core, backdrop)
    d = np.abs(room.astype(np.float32) - backdrop.astype(np.float32)).max(2)
    a = np.where(grown & ~green, np.maximum(a, np.clip((d - 14) / 30, 0, 1)), 0.0).astype(np.float32)
    F = room.astype(np.float32)
    edge = (a > 0.03) & (a < 0.999)
    B = backdrop.astype(np.float32)
    F[edge] = np.clip((F[edge] - (1 - a[edge, None]) * B[edge]) / a[edge, None], 0, 255)
    left, right = region(STANDS_LEFT, hw), region(STANDS_RIGHT, hw)
    for name, part in (("kit_still", ~(left | right)), ("kit_left", left), ("kit_right", right)):
        ap = a * part
        save_layer(np.dstack([F.astype(np.uint8), (ap * 255 + 0.5).clip(0, 255).astype(np.uint8)]), name, outdir, info)


def row_fill(rgb, hole, known, top):
    """Below row top, each row's hole carried across from the known pixels either side of it in
    that row, then softened (more along the row than across)."""
    out = rgb.astype(np.float32).copy()
    xs = np.arange(rgb.shape[1])
    for y in range(top, rgb.shape[0]):
        hy, ky = hole[y], known[y]
        if hy.any() and ky.sum() >= 2:
            for c in range(3):
                out[y, hy, c] = np.interp(xs[hy], xs[ky], out[y, ky, c])
    soft = cv2.GaussianBlur(out, (0, 0), sigmaX=4 * SCALE, sigmaY=1.2 * SCALE)
    out[hole] = soft[hole]
    rng = np.random.default_rng(9)
    out += cv2.GaussianBlur(rng.normal(0, 2.2, hole.shape).astype(np.float32), (0, 0), 1.2)[..., None] * hole[..., None]
    return out


def largest(mask):
    """The biggest connected piece of a mask (no stray specks)."""
    n, lab, stats, _ = cv2.connectedComponentsWithStats(mask.astype(np.uint8), connectivity=8)
    if n <= 1:
        return mask
    return lab == 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))


def clean_fist(rgb, arm, room, hsv, shape, stick, not_in, whole_stick):
    """A fist without its stick: the wood across the fingers (and, on the right, the butt below
    them) is painted out with fur, so the plugin can lay a stick across it at any angle."""
    hsv_h, hsv_s, hsv_v = hsv
    hw = arm.shape
    fist = arm & (region([shape], hw) | region(stick, hw))
    if not_in:
        fist &= ~region(not_in, hw)
    wood = fist & (hsv_h >= 5) & (hsv_h <= 35) & (hsv_s > 35) & (hsv_v > 80)
    wood = cv2.dilate(wood.astype(np.uint8), np.ones((5, 5), np.uint8)) > 0
    fur = fist & ~wood
    # The fist's outline goes on behind where the stick crossed it; the butt sticking out of it goes.
    k = int(9 * SCALE) | 1
    closed = cv2.morphologyEx(fur.astype(np.uint8), cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k))) > 0
    body = fill_holes(fur | (wood & closed))
    body = cv2.morphologyEx(body.astype(np.uint8), cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7))) > 0
    body &= region([shape], hw) | fur
    # Where the stick ran off the fist's edge, the fist's round outline carries on under it.
    hull = np.zeros(hw, np.uint8)
    cv2.fillConvexPoly(hull, cv2.convexHull(cv2.findNonZero(largest(body).astype(np.uint8))), 1)
    body |= (hull > 0) & wood & region([shape], hw)
    body = largest(body)
    hole = cv2.dilate((wood & body).astype(np.uint8), np.ones((3, 3), np.uint8)) > 0
    # The whole stick goes from the picture first, or LaMa carries it on into the fist.
    whole = region(whole_stick, hw) & (hsv_h >= 5) & (hsv_h <= 35) & (hsv_s > 35) & (hsv_v > 80)
    hole |= cv2.dilate(whole.astype(np.uint8), np.ones((7, 7), np.uint8)) > 0
    filled = lama_crop(rgb, hole, pad=64)
    F, a = soften(filled, body, room)
    return np.dstack([F, (a * 255 + 0.5).astype(np.uint8)])


def clean_stick(rgb, arm, room):
    """The whole stick, upright, tip at the top: from the picture from the tip down to the grip,
    then on down through the fist to its butt (the shaft below the grip is the shaft just above
    it, carried on, with a rounded end)."""
    s = SCALE
    (gx, gy), (tx, ty) = GRIP, TIP
    ang = np.degrees(np.arctan2(tx - gx, gy - ty))            # how far it leans right of upright
    length = np.hypot(tx - gx, ty - gy)
    F, a = soften(rgb, arm & region([SHAFT_R], arm.shape), room)
    rgba = np.dstack([F, (a * 255).astype(np.uint8)]).astype(np.uint8)
    # Turn about the grip so the stick stands straight up, then cut it out.
    M = cv2.getRotationMatrix2D((gx * s, gy * s), ang, 1.0)
    up = cv2.warpAffine(rgba, M, (rgba.shape[1], rgba.shape[0]), flags=cv2.INTER_CUBIC, borderValue=(0, 0, 0, 0))
    half = int(STICK_W * s / 2) + 2
    top = int((gy - length - 4) * s)
    crop = up[top:int(gy * s), int(gx * s) - half:int(gx * s) + half].astype(np.float32)
    # The shaft's profile across, from a stretch above the grip (clear of the fingers).
    band = crop[-int(14 * s):-int(4 * s)]
    profile = np.median(band, axis=0)
    w = profile.shape[0]
    tail = int(round((BUTT_IN + 4) * s))
    ext = np.repeat(profile[None], tail, 0)
    # A rounded butt end.
    rad = max(1.0, (profile[:, 3] > 128).sum() / 2)
    yy, xx = np.mgrid[0:tail, 0:w].astype(np.float32)
    cy = tail - rad
    cx = (w - 1) / 2
    cap = np.where(yy > cy, np.clip(rad + 0.5 - np.hypot(xx - cx, yy - cy), 0, 1), 1.0)
    ext[..., 3] *= cap
    # Where the picture's stick meets the fingers, hand over to the carried-on shaft.
    out = np.concatenate([crop[:-int(4 * s)], ext], 0)
    return out.clip(0, 255).astype(np.uint8)


def fur_ball(rgb):
    """A ball of the panda's own fur, lit from the upper left like his fists, with a tufted edge.
    The plugin strings them along a curve, overlapping, to make his arms: soft and round, any
    length, bent anywhere, and never stretched."""
    s = SCALE
    x0, y0, x1, y1 = (int(v * s) for v in FUR_PATCH)
    patch = rgb[y0:y1, x0:x1].astype(np.float32)
    r = FUR_R * s
    size = int(2 * r + 12 * s)
    tile = np.concatenate([patch, patch[:, ::-1]], 1)
    tile = np.concatenate([tile, tile[::-1]], 0)
    tex = np.tile(tile, (size // tile.shape[0] + 2, size // tile.shape[1] + 2, 1))[:size, :size]
    c = (size - 1) / 2
    yy, xx = np.mgrid[0:size, 0:size].astype(np.float32)
    dx, dy = (xx - c) / r, (yy - c) / r
    d = np.sqrt(dx * dx + dy * dy)
    theta = np.arctan2(dy, dx)
    # Tufts round the edge: the rim comes and goes with the angle, and the fur's own grain.
    rng = np.random.default_rng(11)
    tufts = sum(np.sin(k * theta + rng.uniform(0, 6.3)) / k ** 0.5 for k in (23, 37, 59, 83, 131))
    lum = tex.mean(2)
    grain = (lum - cv2.GaussianBlur(lum, (0, 0), 2.0)) / 30
    rim = 1.0 + 0.045 * tufts + 0.05 * grain
    alpha = np.clip((rim - d) * r / (2.2 * s) + 0.5, 0, 1)
    # A ball lit from the upper left (as the fists are), darker toward its rim.
    nz = np.sqrt(np.clip(1 - d * d, 0, 1))
    light = np.array([-0.45, -0.6, 0.66])
    light /= np.linalg.norm(light)
    lit = np.clip(dx * light[0] + dy * light[1] + nz * light[2], 0, 1)
    shade = 0.62 + 0.55 * lit
    out = np.clip(tex * shade[..., None], 0, 255)
    return np.dstack([out, alpha * 255]).astype(np.uint8)


def save_layer(rgba, name, outdir, info, keep_box=False):
    ys, xs = np.nonzero(rgba[..., 3] > 2)
    if not len(xs):
        return
    x0, y0, x1, y1 = xs.min(), ys.min(), xs.max() + 1, ys.max() + 1
    if keep_box:
        x0, y0, x1, y1 = 0, 0, rgba.shape[1], rgba.shape[0]
    Image.fromarray(rgba[y0:y1, x0:x1], "RGBA").save(os.path.join(outdir, name + ".png"))
    info[name] = [x0 / SCALE, y0 / SCALE, (x1 - x0) / SCALE, (y1 - y0) / SCALE]
    print(name, info[name], flush=True)


if __name__ == "__main__":
    main(*sys.argv[1:3])
