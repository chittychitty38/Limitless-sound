"""
Lays the hero picture's layers (hero_layers.py) out as the plugin's stage: the room, the kit and
the panda's rig, at 1x and 2x the 1280 x 736 stage, with manifest.json.

    python hero_stage.py <hero_layers out> <sheet pieces (sheet_cut.py out)> <outdir>

The stage is the hero picture, scaled to fill the stage's height. Each drum and cymbal of the
picture becomes a piece of the kit at its own place and size, so the factory kit looks exactly
like the picture; other kits put their drums in the same slots, scaled by size. Laid out the
way a real kit is around the drummer: the snare in front of him, the hi-hat, rack tom 1 and the
first crash on his left (the picture's right), a second rack tom, the floor tom, the ride, the
china and the second crash on his right.

The panda is a rig: torso, head, sleeves, an arm (a plush tube of his own fur), the fist and the
stick, with the shoulder and grip points the plugin drives them by. His face is the picture's
own: its grin for most moods, and its eyes closed (a blink), squinted (focused), turned to happy
arcs (laughing) or one of them (a wink), so the glasses and the grin never move. Only the sad
face comes from the sprite sheet, lined up on the picture's glasses and toned to its fur.
"""

import json
import math
import os
import sys

import cv2
import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

STAGE_W, STAGE_H = 1280, 736
K, OX, OY = 1.09, 16.0, 9.0            # hero pixels -> stage: ((x - OX) K, y K + OY)


def S(x, y):
    return [round((x - OX) * K, 2), round(y * K + OY, 2)]


def R(r):
    return round(r * K, 2)


def E(cx, cy, a, b):
    return S(cx, cy) + [R(a), R(b)]


# The kit in the picture, in hero pixels: head ellipse (centre, radii), bottom of the shell, size.
DRUMS = {
    "kick": dict(layer="kick", head=(690, 518, 158, 132), size=22),
    "snare": dict(layer="drum_center", head=(650, 329, 88, 9), bottom=392, size=14, depth=6.5),
    "tom": dict(layer="drum_right", head=(850, 359, 96, 10), bottom=440, size=10, depth=8),
    "floor": dict(layer="floor", head=(412, 369, 112, 12), bottom=560, size=16, depth=15),
}
CYMBALS = {
    "crash": dict(layer="crash", disc=(1050, 127, 139, 32), size=18),
    "crash_alt": dict(layer="ride", disc=(200, 218, 140, 31), size=19),
    "ride": dict(layer="crash_alt", disc=(352, 178, 140, 39), size=21),
    "china": dict(layer="china", disc=(452, 325, 146, 25), size=18, front=True, stand="front_stand"),
    "splash": dict(layer="crash", disc=(1050, 127, 139, 32), size=18),
}
HIHAT = dict(top="hat_top", bottom="hat_bottom", centre=(997, 265), top_at=(997, 257), bottom_at=(998, 273), radius=108, ry=12, size=14)

# Slots: where each kind of piece goes in the picture (hero pixels) and its radius there.
SLOTS = {
    "kick": [((690, 518), 158)],
    "rack1": [((850, 359), 96)],
    "rack2": [((850, 359), 96), ((528, 343), 82)],
    "rack3": [((850, 359), 96), ((745, 318), 74), ((528, 343), 82)],
    "rack4": [((880, 368), 88), ((775, 318), 72), ((640, 300), 70), ((528, 343), 82)],
    "floor": [((412, 369), 112), ((290, 470), 104)],
    "snare": [((650, 329), 88), ((880, 470), 74)],
    "hihat": [((997, 265), 108)],
    "crash": [((1050, 127), 139), ((200, 218), 140), ((1130, 300), 118), ((120, 330), 118)],
    "ride": [((352, 178), 140), ((1120, 330), 128)],
    "china": [((452, 325), 146), ((1150, 60), 104)],
    "splash": [((1125, 394), 60), ((560, 168), 52)],     # the first on the right crash stand's lower clamp, by the hi-hat
    "perc": [((1100, 520), 62), ((230, 520), 62)],
}
DEFAULT_SIZE = {"kick": [22], "rack1": [10], "rack2": [10, 12], "rack3": [10, 12, 13], "rack4": [10, 12, 13, 14],
                "floor": [16, 14], "snare": [14, 13], "hihat": [14], "crash": [18, 19, 18, 18], "ride": [21, 21],
                "china": [18, 16], "splash": [10, 10], "perc": [8, 8]}

# The rig, hero pixels.
RIG = dict(grip=(526, 200), tip=(549, 100),
           neck=(720, 262), head=(720, 160, 137, 105), seat=(712, 430))
FACES = ["neutral", "happy", "open_mouth", "smile", "focused", "excited", "wink", "laugh", "surprised", "tongue_out",
         "angry", "sad"]
OWN_FACES = ("excited", "happy", "open_mouth", "neutral", "smile", "surprised", "tongue_out")
EYES = [(658, 146), (789, 166)]        # a point on the white of each eye (his right, his left), hero px
SCALES = (1, 2)


class Out:
    def __init__(self, outdir):
        self.dir = outdir
        os.makedirs(outdir, exist_ok=True)
        self.files = {}

    def write(self, name, img2x, x, y, w, h):
        """img2x: the layer at 2x the stage; (x, y, w, h): its box on the stage."""
        for k in SCALES:
            sw, sh = max(1, round(w * k)), max(1, round(h * k))
            im = img2x.resize((sw, sh), Image.LANCZOS) if (sw, sh) != img2x.size else img2x
            im.save(os.path.join(self.dir, "%s%s.png" % (name, "@2x" if k == 2 else "")), optimize=True)
        self.files[name] = dict(file=name, x=round(x, 2), y=round(y, 2), w=round(w, 2), h=round(h, 2))

    def opaque(self, name, img2x):
        for k in SCALES:
            im = img2x.convert("RGB").resize((STAGE_W * k, STAGE_H * k), Image.LANCZOS)
            im.save(os.path.join(self.dir, "%s%s.jpg" % (name, "@2x" if k == 2 else "")), quality=92)
        self.files[name] = dict(file=name, x=0, y=0, w=STAGE_W, h=STAGE_H)


def hero_layer(src, info, out, name, as_name=None):
    x, y, w, h = info["layers"][name]
    img = Image.open(os.path.join(src, name + ".png")).convert("RGBA")
    sx, sy = S(x, y)
    out.write(as_name or name, img, sx, sy, w * K, h * K)


def main(src, pieces, outdir):
    with open(os.path.join(src, "layers.json")) as f:
        info = json.load(f)
    out = Out(outdir)
    man = dict(stage=dict(w=STAGE_W, h=STAGE_H, centre_x=S(712, 0)[0]), files=out.files, kit={}, slots={},
               panda=dict(mode="rig"))

    # ---- the room: the picture with everything that moves taken out, filling the stage
    room = Image.open(os.path.join(src, "room.png")).convert("RGB")
    sc = info["scale"]
    canvas = Image.new("RGB", (STAGE_W * 2, STAGE_H * 2))
    ox, oy = round(-OX * sc), round(OY * 2)
    canvas.paste(room, (ox, oy))
    top = room.crop((0, 0, room.width, 1)).resize((room.width, oy))
    canvas.paste(top, (ox, 0))
    out.opaque("stage", canvas)
    # The heart lights' bulbs, for the glow.
    small = np.asarray(canvas.resize((STAGE_W, STAGE_H)))
    hsv = cv2.cvtColor(small, cv2.COLOR_RGB2HSV)
    lit = ((hsv[..., 1] > 110) & (hsv[..., 2] > 200) & ~((hsv[..., 0] >= 150) | (hsv[..., 0] <= 8)) |
           ((hsv[..., 0] <= 8) | (hsv[..., 0] >= 170)) & (hsv[..., 1] > 150) & (hsv[..., 2] > 200)).astype(np.uint8)
    lit[int(STAGE_H * 0.14):] = 0
    n, lab, st, ce = cv2.connectedComponentsWithStats(lit, 8)
    bulbs = []
    for i in range(1, n):
        if st[i][4] > 25:
            rgb = small[lab == i].mean(0) / 255
            bulbs.append(dict(at=[round(float(ce[i][0]), 2), round(float(ce[i][1]), 2)], colour=[round(float(c), 3) for c in rgb]))
    man["stage"]["bulbs"] = bulbs

    # ---- slots
    for kind, slots in SLOTS.items():
        sizes = DEFAULT_SIZE[kind]
        man["slots"][kind] = [dict(at=S(*at), ppi=round(R(r) / sizes[min(i, len(sizes) - 1)], 4)) for i, (at, r) in enumerate(slots)]

    # ---- drums
    wraps = ["purple", "brass", "maple", "chrome", "walnut", "black"]
    for kind, d in DRUMS.items():
        hero_layer(src, info, out, d["layer"], kind)
        cx, cy, a, b = d["head"]
        entry = dict(anchor=S(cx, cy), radius=R(a), size=d["size"], head=E(cx, cy, a, b), wraps={w: kind for w in wraps})
        if "bottom" in d:
            entry["shell"] = R(d["bottom"] - cy)
            entry["depth"] = d["depth"]
        man["kit"][kind] = entry
    man["kit"]["tom_alt"] = dict(man["kit"]["tom"])          # the left rack tom: the same drum

    # ---- cymbals
    written = set()
    for kind, c in CYMBALS.items():
        if c["layer"] not in written:
            hero_layer(src, info, out, c["layer"], "cym_" + c["layer"])
            written.add(c["layer"])
        cx, cy, a, b = c["disc"]
        entry = dict(anchor=S(cx, cy), size=c["size"], radius=R(a), file="cym_" + c["layer"], ellipse=E(cx, cy, a, b), post=S(cx, cy)[1])
        if c.get("front"):
            entry["front"] = True
        man["kit"][kind] = entry
        if "stand" in c:
            hero_layer(src, info, out, c["stand"])
            man["kit"].setdefault("stands", {})[kind] = [dict(top=S(cx, cy), file=c["stand"])]
    h = HIHAT
    hero_layer(src, info, out, h["top"])
    hero_layer(src, info, out, h["bottom"])
    man["kit"]["hihat"] = dict(anchor=S(*h["centre"]), size=h["size"], top=S(*h["top_at"]), bottom=S(*h["bottom_at"]),
                               ellipse=E(h["centre"][0], h["centre"][1], h["radius"], h["ry"]), radius=R(h["radius"]),
                               top_file=h["top"], bottom_file=h["bottom"])

    # ---- the panda
    pan = man["panda"]
    for name in ("torso", "head", "sleeve_r", "sleeve_l", "fist", "fist_l", "rest_r", "rest_l"):
        hero_layer(src, info, out, name)
    # The fur ball and the stick are upright pictures of their own, kept at the origin.
    for name in ("fur", "stick"):
        x, y, w, hh = info["layers"][name]
        out.write(name, Image.open(os.path.join(src, name + ".png")).convert("RGBA"), 0, 0, w * K, hh * K)
    r = RIG
    rig = info["rig"]
    hx, hy, ha, hb = r["head"]
    gx, gy = r["grip"]
    tx, ty = r["tip"]
    grip_len = math.hypot(tx - gx, ty - gy)
    pin, butt_in = rig["pivot_in"], rig["butt_in"]
    pivot_r = (gx + (gx - tx) / grip_len * pin, gy + (gy - ty) / grip_len * pin)
    pivot_l = tuple(rig["pivot_l"])
    homes, real = hand_poses([(S(*pivot_r), S(tx, ty)), (S(*pivot_l), S(*rig["tip_l"]))])
    pan.update(
        head=dict(anchor=S(hx, hy), radius=R(ha), ellipse=E(hx, hy, ha, hb)),
        torso="torso", head_file="head", sleeves=["sleeve_r", "sleeve_l"],
        shoulders=[S(*p) for p in rig["shoulders"]], neck=S(*r["neck"]), seat=S(*r["seat"]),
        # Each hand's own fist from the picture. The stick turns about the fulcrum in it (pivot);
        # the arm meets it at the wrist. On the right the stick's butt shows below the fist.
        fists=[dict(file="fist", pivot=S(*pivot_r), wrist=S(*rig["wrists"][0]), butt_front=True),
               dict(file="fist_l", pivot=S(*pivot_l), wrist=S(*rig["wrists"][1]), butt_front=False)],
        # The picture's arms as they are, for him at rest, and how each hand holds its stick there
        # (the stick's heading across the floor and pitch above it, in radians).
        rest=["rest_r", "rest_l"],
        home=homes,
        # The stick's picture: from the fulcrum to the tip (length) and to the butt, where the
        # fulcrum is in the upright picture (pivot_y), and how long the stick really is (real).
        stick=dict(file="stick", length=R(grip_len + pin), butt=R(butt_in - pin), pivot_y=R(4 + grip_len + pin),
                   real=round(real, 2)),
        fur=dict(file="fur", radius=R(rig["fur_r"])),
    )

    # ---- faces, from the sheet, on the picture's glasses
    import sheet_stage as ss
    head_img = Image.open(os.path.join(src, "head.png")).convert("RGBA")
    hx0, hy0, hw0, hh0 = info["layers"]["head"]
    hs = head_img.width / hw0                                   # head image pixels per hero pixel
    ell = ((hx - hx0) * hs, (hy - hy0) * hs, ha * hs, hb * hs)
    g = ss.glasses_box(head_img, ell)
    gl = [S(hx0 + g[0] / hs, hy0 + g[1] / hs), S(hx0 + g[2] / hs, hy0 + g[3] / hs)]
    ref = (gl[0][0], gl[0][1], gl[1][0], gl[1][1])
    pan["glasses"] = [round(v, 2) for v in ref]
    head_rgb = np.asarray(head_img).astype(np.float32)
    pan["faces"] = {}
    piece = lambda n: Image.open(os.path.join(pieces, n + ".png")).convert("RGBA")
    for face in FACES + ["blink"]:
        src_img = piece("pose_blink") if face == "blink" else piece("face_" + face)
        e = (ss.HEADS.get("pose_blink") or ss.head_of(ss.clean_pose(src_img, "pose_blink"), 0.6)) if face == "blink" else ss.head_of(src_img, 0.9)
        patch, pg = ss.face_patch(src_img, e)
        s = (ref[2] - ref[0]) / (pg[2] - pg[0])
        x = (ref[0] + ref[2]) / 2 - (pg[0] + pg[2]) / 2 * s
        y = (ref[1] + ref[3]) / 2 - (pg[1] + pg[3]) / 2 * s
        patch = tone_to(patch, head_rgb, (x, y, s), (hx0, hy0, hs))
        w2, h2 = patch.width * s * 2, patch.height * s * 2
        out.write("face_" + face, patch.resize((max(1, round(w2)), max(1, round(h2))), Image.LANCZOS), x, y, patch.width * s, patch.height * s)
        pan["faces"][face] = dict(file="face_" + face)
        if face in OWN_FACES:
            pan["faces"][face]["own"] = True     # the picture's own grin is this face: no patch over it
    # The faces made from the picture's own eyes replace the sheet's.
    hx_stage, hy_stage = S(hx0, hy0)
    for face, patch, (bx, by) in hero_eyes(head_img, (hx0, hy0, hs)):
        out.write("face_" + face, patch, hx_stage + bx / hs * K, hy_stage + by / hs * K, patch.width / hs * K, patch.height / hs * K)
        pan["faces"][face] = dict(file="face_" + face)
    pan["faces"]["angry"] = dict(file="face_focused")    # a rock-out scowl: the same squint

    # ---- effects and the badge, from the sheet
    fx = {}
    for name, height in (("blur_1", 70), ("blur_2", 50), ("blur_3", 70), ("hit_spark", 90), ("heart_red", 30),
                         ("heart_pink", 30), ("heart_yellow", 30), ("glow_particles", 120), ("heart_particles", 130)):
        img = piece(name)
        k = height / img.height
        out.write("fx_" + name, img.resize((round(img.width * k * 2), round(height * 2)), Image.LANCZOS), 0, 0, img.width * k, height)
        fx[name] = "fx_" + name
    pan["fx"] = fx
    src_img = piece("face_happy")
    e = ss.head_of(src_img, 0.9)
    a = np.asarray(src_img).copy()
    chin = int(e[1] + e[3] * 1.04)
    a[..., 3] = (a[..., 3] * np.clip((chin - np.arange(a.shape[0])) / 14, 0, 1)[:, None]).astype(np.uint8)
    badge = Image.fromarray(a[:chin + 1], "RGBA")
    out.write("badge", badge.resize((512, round(512 * badge.height / badge.width)), Image.LANCZOS), 0, 0, 256, 256 * badge.height / badge.width)
    pan["badge"] = "badge"

    with open(os.path.join(outdir, "manifest.json"), "w") as f:
        json.dump(man, f, indent=1)
    print("wrote", len(out.files), "layers to", outdir)


def hero_eyes(head_img, head_place):
    """Faces made from the picture's own: the eyes closed (blink), squinting (focused), happy arcs
    (laugh), and a wink. Each is a patch over just the eyes, at the head picture's scale."""
    hx0, hy0, hs = head_place
    a = np.asarray(head_img).astype(np.float32)
    rgb = a[..., :3]
    bright = (rgb.min(2) > 150).astype(np.uint8)
    _, lab = cv2.connectedComponents(bright, connectivity=4)
    eyes = []
    for ex, ey in EYES:
        sx, sy = int((ex - hx0) * hs), int((ey - hy0) * hs)
        white = lab == lab[sy, sx]
        # The white wraps most of the way round the iris: its hull is the whole eye.
        hull = cv2.convexHull(cv2.findNonZero(white.astype(np.uint8)))
        m = np.zeros(white.shape, np.uint8)
        cv2.fillConvexPoly(m, hull, 1)
        m = cv2.dilate(m, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7))) > 0
        assert m.sum() < 20000, "an eye's white ran out of its patch"
        ys, xs = np.nonzero(m)
        ring = (cv2.dilate(m.astype(np.uint8), np.ones((15, 15), np.uint8)) > 0) & ~m & (rgb.max(2) < 60)
        lid = np.median(rgb[ring], axis=0) * 0.85
        eyes.append(dict(mask=m, cx=xs.mean(), cy=ys.mean(), rw=(xs.max() - xs.min()) / 2, rh=(ys.max() - ys.min()) / 2, lid=lid))
    union = np.zeros(bright.shape, bool)
    for e in eyes:
        union |= e["mask"]
    union = cv2.dilate(union.astype(np.uint8), np.ones((9, 9), np.uint8)) > 0
    ys, xs = np.nonzero(union)
    x0, y0, x1, y1 = xs.min(), ys.min(), xs.max() + 1, ys.max() + 1

    fur = np.array([246, 226, 214], np.float32)       # the cream of his face, for the lines on the dark lids

    def closed(img, e):
        """The eye shut: the lid (the patch's black, with a little sheen at the top) over the white."""
        m = e["mask"]
        yy = np.arange(img.shape[0], dtype=np.float32)[:, None]
        sheen = np.clip(1 - np.abs(yy - (e["cy"] - e["rh"] * 0.45)) / (e["rh"] * 0.5), 0, 1) * 9
        soft = cv2.GaussianBlur(m.astype(np.float32), (0, 0), 1.2)[..., None]
        img[..., :3] = img[..., :3] * (1 - soft) + (e["lid"] + sheen[..., None]) * soft

    def arc(img, e, up, width, colour, sag=0.32, span=0.78, lift=0.0):
        """A curved line across the eye: up (a happy arc) or down (a shut lid's seam)."""
        canvas = np.zeros(img.shape[:2], np.uint8)
        pts = []
        for u in np.linspace(-1, 1, 25):
            x = e["cx"] + u * e["rw"] * span
            y = e["cy"] + e["rh"] * lift + (-1 if up else 1) * e["rh"] * sag * (1 - u * u)
            pts.append((int(round(x * 4)), int(round(y * 4))))
        cv2.polylines(canvas, [np.array(pts, np.int32)], False, 255, int(width * 4), cv2.LINE_AA, shift=2)
        k = cv2.GaussianBlur(canvas.astype(np.float32) / 255, (0, 0), 0.8)[..., None]
        img[..., :3] = img[..., :3] * (1 - k) + colour * k

    def squint(img, e, inner):
        """The upper lid down past the middle, lower toward the nose: concentration."""
        m = e["mask"]
        yy, xx = np.mgrid[0:img.shape[0], 0:img.shape[1]].astype(np.float32)
        line = e["cy"] - e["rh"] * 0.08 + inner * (xx - e["cx"]) / e["rw"] * e["rh"] * 0.22
        lid = (m & (yy < line)).astype(np.float32)
        soft = cv2.GaussianBlur(lid, (0, 0), 1.0)[..., None] * m[..., None]
        img[..., :3] = img[..., :3] * (1 - soft) + e["lid"] * soft

    faces = {}
    img = a.copy()
    for e in eyes:
        closed(img, e)
        arc(img, e, False, 3.0, fur * 0.75, sag=0.22, lift=0.1)
    faces["blink"] = img
    img = a.copy()
    for e in eyes:
        closed(img, e)
        arc(img, e, True, 6.0, fur, sag=0.42, span=0.7, lift=0.3)
    faces["laugh"] = img
    img = a.copy()
    closed(img, eyes[1])
    arc(img, eyes[1], True, 6.0, fur, sag=0.42, span=0.7, lift=0.3)
    faces["wink"] = img
    img = a.copy()
    squint(img, eyes[0], 1.0)       # his right eye is on the left: its inner corner is to the right
    squint(img, eyes[1], -1.0)
    faces["focused"] = img

    out = []
    alpha = cv2.GaussianBlur(union.astype(np.float32), (0, 0), 2.0)
    for name, img in faces.items():
        rgba = img.copy()
        rgba[..., 3] = np.minimum(rgba[..., 3], alpha * 255)
        crop = rgba[y0:y1, x0:x1].clip(0, 255).astype(np.uint8)
        out.append((name, Image.fromarray(crop, "RGBA"), (x0, y0)))
    return out


CAM_TILT = 0.26          # the camera looks down on him ~15 degrees (the plugin uses the same)


def on_screen(heading, pitch):
    """A stick's direction (heading across the floor: 0 toward us, + to screen right; pitch above
    it) as it shows on screen, per unit of its length."""
    X = math.cos(pitch) * math.sin(heading)
    Y = math.sin(pitch)
    Z = math.cos(pitch) * math.cos(heading)
    return X, -Y * math.cos(CAM_TILT) + Z * math.sin(CAM_TILT)


def hand_poses(sticks, right_pitch=math.radians(75)):
    """How each hand holds its stick in the picture, in 3D: the right stick stands up (pitch 75
    degrees), which with its slant on screen gives its heading and the stick's real length; the
    left one, at that length, is whatever heading and pitch show it as it is."""
    (p0, t0), (p1, t1) = sticks
    vx, vy = t0[0] - p0[0], t0[1] - p0[1]
    best = min((abs(math.atan2(*reversed(on_screen(h, right_pitch))) - math.atan2(vy, vx)), h)
               for h in (math.radians(d / 10) for d in range(1, 890)))
    h0 = best[1]
    real = math.hypot(vx, vy) / math.hypot(*on_screen(h0, right_pitch))
    ux, uy = t1[0] - p1[0], t1[1] - p1[1]
    err, h1, q1 = min((math.hypot(on_screen(h, q)[0] * real - ux, on_screen(h, q)[1] * real - uy), h, q)
                      for h in (math.radians(d / 4) for d in range(-356, 357))
                      for q in (math.radians(d / 4) for d in range(-200, 357)))
    print("hands at rest: right heading %.1f pitch %.1f, left heading %.1f pitch %.1f (off %.2f px), stick %.1f"
          % (math.degrees(h0), math.degrees(right_pitch), math.degrees(h1), math.degrees(q1), err, real))
    return ([dict(pivot=list(p0), heading=round(h0, 4), pitch=round(right_pitch, 4)),
             dict(pivot=list(p1), heading=round(h1, 4), pitch=round(q1, 4))], real)


def tone_to(patch, head_rgb, place, head_place):
    """Shift a face patch's colours so its fur matches the picture's fur where it lies."""
    x, y, s = place
    hx0, hy0, hs = head_place
    p = np.asarray(patch).astype(np.float32)
    h, w = p.shape[:2]
    yy, xx = np.mgrid[0:h, 0:w]
    # Where each patch pixel lands in the head picture (stage -> hero -> head image).
    sx = (x + xx * s) / K + OX
    sy = (y + yy * s - OY) / K
    hxp = ((sx - hx0) * hs).astype(int)
    hyp = ((sy - hy0) * hs).astype(int)
    inside = (hxp >= 0) & (hyp >= 0) & (hxp < head_rgb.shape[1]) & (hyp < head_rgb.shape[0])
    under = np.zeros_like(p)
    under[inside] = head_rgb[hyp[inside], hxp[inside]]
    # Compare the light fur only (not the glasses, eyes or mouth), at the patch's soft rim.
    def fur(a):
        return (a[..., :3].min(2) > 150) & (a[..., 3] > 200)
    rim = (p[..., 3] > 30) & (p[..., 3] < 230)
    m = fur(p) & fur(under) & rim
    if m.sum() < 50:
        m = fur(p) & fur(under)
    if m.sum() < 50:
        return patch
    gain = under[m][:, :3].mean(0) / np.maximum(1.0, p[m][:, :3].mean(0))
    p[..., :3] = np.clip(p[..., :3] * gain, 0, 255)
    return Image.fromarray(p.astype(np.uint8), "RGBA")


if __name__ == "__main__":
    main(*sys.argv[1:4])
