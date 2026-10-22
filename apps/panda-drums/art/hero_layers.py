"""
Separates the Panda Drums hero picture (the panda at the kit) into the layers the stage draws,
so the stage is that picture, alive.

    ESRGAN=RealESRGAN_x4plus.pth LAMA=big-lama.pt python hero_layers.py hero.jpg <outdir>

The picture is upscaled 4x with Real-ESRGAN first (kept as <outdir>/hero4x.png; an already
upscaled picture is used as it is).

Every piece is traced here in the hero's own pixels (1206 x 667): each cymbal's disc, each drum,
the panda's head, torso, sleeves, arms and fists with their sticks, and the china's stand where
it stands in front of the floor tom. Inside its outline a piece takes everything that isn't the
pink wall. The wall is spread smoothly back in behind everything that moves; LaMa paints in the
parts of a piece that another one hid (the crash behind the ride, the bottom hi-hat under the top one, the floor tom
behind the china's stand, the shirt under the arms and the chin), and a guided filter softens
each edge (fur, cymbal rims), with the wall's pink taken back out of the edge colour. What stays
in the room is its stands and the panda's legs.

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


# The pieces, back to front, in hero pixels. Options: "all" takes every pixel inside a shape (a
# drum head, whatever its colour); "complete" is the piece's whole shape, for painting in what
# was hidden; "cream" keeps only fur and face low on the head (not the collar).
PIECES = [
    ("ride", [ellipse(200, 218, 144, 34, 9), rect(180, 172, 212, 200)], {"complete": [ellipse(200, 218, 140, 31, 9)], "all": [ellipse(200, 218, 140, 31, 9)]}),
    ("crash_alt", [ellipse(352, 178, 144, 42, 11), rect(312, 126, 344, 164)], {"complete": [ellipse(352, 178, 140, 39, 11)], "all": [ellipse(352, 178, 140, 39, 11)]}),
    ("crash", [ellipse(1050, 127, 143, 35, -11), rect(1036, 76, 1068, 112)], {"complete": [ellipse(1050, 127, 139, 32, -11)], "all": [ellipse(1050, 127, 139, 32, -11)]}),
    ("hat_bottom", [ellipse(998, 273, 110, 11, 1)], {"complete": [ellipse(998, 272, 106, 9, 1)], "all": [ellipse(998, 272, 106, 9, 1)]}),
    ("hat_top", [ellipse(997, 257, 112, 13, 2), rect(989, 210, 1013, 250)], {"all": [ellipse(997, 257, 106, 9, 2)]}),
    ("torso", [poly((560, 220), (612, 226), (700, 236), (790, 238), (842, 262), (862, 300), (860, 338), (556, 338), (560, 300))], {}),
    ("sleeve_r", [poly((568, 220), (604, 226), (610, 262), (604, 308), (566, 310))], {"purple": True}),
    ("sleeve_l", [poly((798, 262), (846, 264), (858, 290), (852, 312), (800, 306))], {"purple": True}),
    ("head", [ellipse(720, 162, 142, 114), ellipse(650, 52, 50, 46), ellipse(856, 102, 50, 50),
              ellipse(636, 228, 46, 24), ellipse(806, 242, 46, 22)],
     {"all": [ellipse(720, 161, 132, 104)], "no_collar_below": 228}),
    ("floor", [poly((295, 370), (306, 360), (522, 360), (530, 372), (530, 552), (520, 568), (305, 568), (295, 552))], {}),
    ("drum_center", [poly((552, 322), (560, 316), (738, 316), (745, 324), (745, 396), (552, 396))],
     {"complete": [poly((556, 318), (742, 318), (742, 392), (556, 392))]}),
    ("drum_right", [poly((748, 354), (756, 348), (946, 348), (952, 356), (952, 444), (748, 444))], {}),
    ("kick", [ellipse(689, 520, 176, 150), poly((518, 400), (560, 392), (560, 640), (518, 620))], {"all": [ellipse(690, 520, 150, 124)]}),
    ("arm_r", [poly((466, 186), (568, 186), (580, 222), (576, 314), (520, 318), (466, 284)), line(551, 96, 510, 264, 18)], {"not_purple": True}),
    ("arm_l", [poly((812, 274), (872, 272), (898, 300), (898, 349), (812, 354), (802, 300)), line(848, 336, 963, 299, 18)], {"not_purple": True}),
    ("front_stand", [rect(438, 345, 468, 560), poly((452, 505), (580, 667), (325, 667))], {}),
    ("china", [ellipse(452, 325, 148, 27, 5), rect(441, 281, 472, 312)], {"no_fur": True, "all": [ellipse(452, 326, 140, 21, 5)]}),
]

# Pieces that are completed with LaMa where others hid them, and what they're painted against.
COMPLETE = ["ride", "crash_alt", "crash", "hat_bottom", "drum_center"]

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


def wall_fill(rgb, hole, wall):
    """The room behind the kit and the panda: the wall's own colours spread smoothly into the hole
    from all round it (normalised convolution, finest scale that reaches), with its grain."""
    # Only wall well clear of the pieces: their shaded rims can pass for pink.
    near = cv2.dilate(hole.astype(np.uint8), np.ones((31, 31), np.uint8)) > 0
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
    edge = cv2.GaussianBlur(hole.astype(np.float32), (0, 0), 3)
    out = rgb * (1 - edge[..., None]) + out * edge[..., None]
    return out.clip(0, 255).astype(np.uint8)


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


def soften(rgb, mask, room):
    """A soft alpha for a hard mask (edge-aware), and the edge's colour with the room's taken out."""
    grey = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY).astype(np.float32) / 255
    a = guided(grey, mask.astype(np.float32), 3, 1e-3)
    inner = cv2.erode(mask.astype(np.uint8), np.ones((5, 5), np.uint8)) > 0
    outer = cv2.dilate(mask.astype(np.uint8), np.ones((5, 5), np.uint8)) > 0
    a = np.where(inner, 1.0, np.where(outer, np.clip(a, 0, 1), 0.0)).astype(np.float32)
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
            gold = (hsv_h >= 6) & (hsv_h <= 30) & (hsv_s > 70) & (hsv_v > 70)
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
            taken |= m
        masks[name] = m
    # The sleeves are copies of the torso's own pixels, drawn again over the arms.
    masks["sleeve_r"] &= masks["torso"]
    masks["sleeve_l"] &= masks["torso"]

    # ---- the room: everything but the stands and the legs painted out
    gone = np.zeros(hw, bool)
    for name, shapes, opts in PIECES:
        if name not in ("front_stand", "sleeve_r", "sleeve_l"):
            gone |= region(shapes, hw)
    gone |= region([TORSO_SHAPE], hw) & ~region([rect(0, 400, HERO_W, HERO_H)], hw)
    gone = cv2.dilate(gone.astype(np.uint8), np.ones((9, 9), np.uint8)) > 0
    print("room: painting out", int(gone.sum()), "px", flush=True)
    room = wall_fill(rgb, gone, wall)
    Image.fromarray(room).save(os.path.join(outdir, "room.png"))

    # ---- each piece: soft edge, completed where hidden
    info = {}
    for name, shapes, opts in PIECES:
        m = masks[name]
        if not m.any():
            continue
        F, a = soften(rgb, m, room)
        if name in COMPLETE:
            F, a = complete_over_green(F, a, region(opts["complete"], hw))
        if name == "floor":
            F, a = complete_over_green(F, a, region([FLOOR_HIDDEN], hw) & region(shapes, hw))
        if name == "torso":
            # Under the arms, the chin and the drums: the shirt goes on.
            shape = region([TORSO_SHAPE], hw)
            for other in ("arm_r", "arm_l", "head", "drum_center", "drum_right", "kick", "china", "floor"):
                near = cv2.dilate(masks[other].astype(np.uint8), np.ones((7, 7), np.uint8)) > 0
                a = np.where(near & shape, 0.0, a)
            F, a = complete_over_green(F, a, shape)
        out = np.dstack([F, (a * 255 + 0.5).clip(0, 255).astype(np.uint8)])
        save_layer(out, name, outdir, info)

    # ---- the rig: the right fist (with the stick where it crosses the fingers), the stick on
    # its own (straight, upright, from the grip to the tip), and the arm
    hsv = (hsv_h, hsv_s, hsv_v)
    save_layer(clean_fist(rgb, masks["arm_r"], room, hsv, FIST_R, [STICK_R], [SHAFT_R], [STICK_R]), "fist", outdir, info)
    save_layer(clean_fist(rgb, masks["arm_l"], room, hsv, FIST_L, [STICK_L], [], [line(848, 336, 963, 299, 18)]), "fist_l", outdir, info)
    save_layer(clean_stick(rgb, masks["arm_r"], room), "stick", outdir, info, keep_box=True)
    save_layer(fur_ball(rgb), "fur", outdir, info, keep_box=True)
    # The picture's arms as they are (fist, fur and stick), for him at rest.
    for name in ("arm_r", "arm_l"):
        F, a = soften(rgb, largest(masks[name]), room)
        save_layer(np.dstack([F, (a * 255 + 0.5).astype(np.uint8)]), "rest_" + name[-1], outdir, info)

    rig = {k: list(v) for k, v in RIG.items()}
    rig.update(grip=list(GRIP), tip=list(TIP), pivot_in=PIVOT_IN, butt_in=BUTT_IN, pivot_l=list(PIVOT_L), tip_l=list(TIP_L),
               shoulders=[list(p) for p in SHOULDERS], wrists=[list(p) for p in WRISTS], fur_r=FUR_R)
    with open(os.path.join(outdir, "layers.json"), "w") as f:
        json.dump(dict(scale=SCALE, size=[HERO_W, HERO_H], layers=info, rig=rig), f, indent=1)
    print("wrote", len(info), "layers", flush=True)


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
