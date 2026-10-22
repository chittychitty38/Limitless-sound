"""
Prepares the interface pieces of the Panda Drums GUI asset pack for the plugin.

    python ui_prep.py <pack's ui dir> <RealESRGAN_x4plus.pth> <outdir>

Every panel, button, tile, readout, toggle and icon of the pack is upscaled 4x with Real-ESRGAN
(colour and alpha separately) and written at 1x and 2x from that, so its edges and lettering stay
smooth at any window size and on Retina screens. A few pieces are also taken apart so the plugin
can use them for any value or label:

- knob_face, knob_needle, knob_dot: the pack's knob without its needle, the needle on its own
  (pointing straight up, straightened) and the centre dot, so the needle turns smoothly to any
  value instead of jumping between the pack's nine frames.
- button_key_selector_blank, button_kit_selector_blank, tile_blank: the key and kit selectors
  and an instrument tile with their lettering painted out, for any key, kit or drum name.
- readout_*_v: the readouts stood on end, for the faders.
- toggle_*_track, toggle_thumb: the toggles without their thumb, and the thumb, so the thumb
  can slide across when a toggle is switched.

The pack's lettering is DejaVu Sans Bold, so labels the plugin writes on the blank pieces match
the ones already on the buttons and tiles.

Writes ui.json with each piece's size and where its parts are: the lettering on a button, the
label and arrows on a tile, the dot on a readout, the thumb on a toggle and the knob's pivot.
"""

import json
import os
import sys

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

PINK = (255, 67, 157)
TEAL = (42, 171, 156)


def load(path):
    return np.asarray(Image.open(path).convert("RGBA")).copy()


def is_colour(a, rgb, tol=40):
    return (np.abs(a[..., :3].astype(int) - np.array(rgb)).max(2) < tol) & (a[..., 3] > 100)


def bbox(mask):
    ys, xs = np.nonzero(mask)
    if not len(xs):
        return None
    return [int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1]


def lettering(a):
    return (a[..., :3].min(2) > 185) & (a[..., 3] > 100)


def paint_out(a, box):
    """Paint the lettering in box out with the colour around it."""
    x0, y0, x1, y1 = box
    region = a[y0:y1, x0:x1, :3].reshape(-1, 3)
    colours, counts = np.unique(region, axis=0, return_counts=True)
    fill = colours[np.argmax(counts)]
    mask = lettering(a)
    grown = mask.copy()
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            grown |= np.roll(np.roll(mask, dy, 0), dx, 1)
    sel = np.zeros_like(mask)
    sel[y0:y1, x0:x1] = True
    a[grown & sel, :3] = fill
    return a


def corner(a):
    """How far the rounded corner reaches in (the part of a panel that must not be stretched)."""
    h, w = a.shape[:2]
    top = int(np.argmax(a[:, w // 2, 3] > 200))
    left = int(np.argmax(a[h // 2, :, 3] > 200))
    radius = int(np.argmax(a[top, :, 3] > 200))
    return max(top, left, radius) + 3


def knob_parts(k):
    h, w = k.shape[:2]
    needle = is_colour(k, PINK, 60)
    dot = is_colour(k, TEAL, 60)
    ys, xs = np.nonzero(dot)
    cy, cx = ys.mean(), xs.mean()
    face = k.copy()
    # The face under the needle is the same as on the opposite side of the dial.
    for y, x in zip(*np.nonzero(needle | dot)):
        oy, ox = int(round(2 * cy - y)), int(round(2 * cx - x))
        if 0 <= oy < h and 0 <= ox < w and not (needle[oy, ox] or dot[oy, ox]):
            face[y, x] = k[oy, ox]
        else:
            face[y, x] = k[int(cy) + 14, int(cx)]
    only = lambda m: np.where(m[..., None], k, 0).astype(np.uint8)
    # The needle is drawn again as a straight bar of the same colour, width and reach: the pack's
    # has a one-pixel jog that would wobble as it turns.
    rows = np.nonzero(needle.any(1))[0]
    width = int(np.median(needle.sum(1)[rows]))
    top = int(rows.min())
    big = Image.new("RGBA", (w * 16, h * 16), (0, 0, 0, 0))
    from PIL import ImageDraw
    ImageDraw.Draw(big).rectangle([(cx + 0.5 - width / 2) * 16, top * 16, (cx + 0.5 + width / 2) * 16, (cy + 0.5) * 16], fill=PINK + (255,))
    straight = big.resize((w * 4, h * 4), Image.LANCZOS)
    return face, only(needle), only(dot), [float(cx + 0.5), float(cy + 0.5)], straight


def main(src, weights, outdir):
    os.makedirs(outdir, exist_ok=True)
    pieces, info = {}, {}
    for sub, prefix in (("panels", "panel_"), ("buttons", "button_"), ("controls", ""), ("icons", "icon_")):
        for f in sorted(os.listdir(os.path.join(src, sub))):
            if not f.endswith(".png") or f.startswith("knob_"):
                continue
            name = prefix + f[:-4].replace("instrument_tile_", "tile_")
            pieces[name] = load(os.path.join(src, sub, f))

    face, needle, dot, pivot, straight = knob_parts(load(os.path.join(src, "controls", "knob_volume_04.png")))
    pieces.update(knob_face=face, knob_needle=needle, knob_dot=dot)
    drawn = {"knob_needle": straight}
    info["knob_face"] = dict(pivot=pivot)

    for name in ("button_key_selector", "button_kit_selector"):
        a = pieces[name]
        pieces[name + "_blank"] = paint_out(a.copy(), [8, 6, a.shape[1] - 8, a.shape[0] - 6])
    pieces["tile_blank"] = paint_out(pieces["tile_kick"].copy(), [6, 4, 110, 32])
    for name in [n for n in pieces if n.startswith("readout_")]:
        pieces[name + "_v"] = np.ascontiguousarray(np.rot90(pieces[name]))
    for name in [n for n in pieces if n.startswith("toggle_")]:
        a = pieces[name]
        thumb = is_colour(a, (235, 255, 251), 90)
        ys, xs = np.nonzero(thumb)
        cx, cy = (xs.min() + xs.max() + 1) / 2, (ys.min() + ys.max() + 1) / 2
        r = (xs.max() + 1 - xs.min()) / 2 + 1.5
        yy, xx = np.mgrid[:a.shape[0], :a.shape[1]]
        disc = (xx + 0.5 - cx) ** 2 + (yy + 0.5 - cy) ** 2 <= r * r
        track = a.copy()
        track[disc & (a[..., 3] > 0), :3] = a[a.shape[0] // 2, int(a.shape[1] - cx), :3]
        pieces[name + "_track"] = track
        if name == "toggle_pink_on":
            x0, y0, x1, y1 = int(cx - r - 1), int(cy - r - 1), int(cx + r + 2), int(cy + r + 2)
            t = np.zeros((y1 - y0, x1 - x0, 4), np.uint8)
            t[...] = a[y0:y1, x0:x1]
            t[~is_colour(t, (235, 255, 251), 90)] = 0
            pieces["toggle_thumb"] = t

    # Where the parts are.
    for name, a in pieces.items():
        e = info.setdefault(name, {})
        e.update(w=int(a.shape[1]), h=int(a.shape[0]))
        if name.startswith(("panel_", "button_", "tile_", "readout_")):
            e["corner"] = corner(a)
        if name.startswith("button_") or name.startswith("tile_"):
            t = bbox(lettering(a) & (np.arange(a.shape[0])[:, None] < (36 if name.startswith("tile_") else 99)))
            if t:
                e["text"] = t
        if name.startswith("tile_"):
            pink = is_colour(a, PINK, 60)
            half = a.shape[1] // 2
            left, right = pink.copy(), pink.copy()
            left[:, half:] = False
            right[:, :half] = False
            e["prev"], e["next"] = bbox(left), bbox(right)
        if name.startswith("readout_") and not name.endswith("_v"):
            # The dot is in the outline's colour, inside the pill near its left end.
            h, w = a.shape[:2]
            ring = a[h // 2, :6, :3].astype(int)
            outline = ring[np.argmax(np.abs(ring - a[h // 2, w // 2, :3].astype(int)).max(1))]
            dot = is_colour(a, tuple(int(v) for v in outline), 50)
            dot[:5], dot[h - 5:], dot[:, :5], dot[:, w // 3:] = False, False, False, False
            e["dot"] = bbox(dot)
        if name.startswith("toggle_") and not name.endswith(("_track", "_thumb")):
            e["thumb"] = bbox(is_colour(a, (235, 255, 251), 30))

    import torch
    from sheet_cut import RRDBNet, upscale, bleed
    torch.set_num_threads(os.cpu_count() or 4)
    model = RRDBNet()
    state = torch.load(weights, map_location="cpu")
    model.load_state_dict(state.get("params_ema", state.get("params", state)))
    model.eval()
    only = set(sys.argv[4].split(",")) if len(sys.argv) > 4 else None
    for name, a in pieces.items():
        if only and not any(name.startswith(o) for o in only):
            continue
        if name in drawn:
            big_im = drawn[name]
        else:
            p = 4
            rgb = a[..., :3].astype(np.float32) / 255
            alpha = a[..., 3].astype(np.float32) / 255
            rgb = np.pad(bleed(rgb, alpha), ((p, p), (p, p), (0, 0)), mode="edge")
            alpha = np.pad(alpha, p)
            big = upscale(model, rgb)
            big_a = upscale(model, np.repeat(alpha[..., None], 3, 2)).mean(2)
            out = np.dstack([big, np.clip((big_a - 0.02) / 0.96, 0, 1)])
            out = (out[p * 4:-p * 4, p * 4:-p * 4] * 255 + 0.5).clip(0, 255).astype(np.uint8)
            big_im = Image.fromarray(out, "RGBA")
        h, w = a.shape[:2]
        big_im.resize((w, h), Image.LANCZOS).save(os.path.join(outdir, name + ".png"), optimize=True)
        big_im.resize((w * 2, h * 2), Image.LANCZOS).save(os.path.join(outdir, name + "@2x.png"), optimize=True)
        print(name, info[name], flush=True)
    path = os.path.join(outdir, "ui.json")
    if only and os.path.exists(path):
        old = json.load(open(path))
        old.update({k: v for k, v in info.items() if any(k.startswith(o) for o in only)})
        info = old
    with open(path, "w") as f:
        json.dump(info, f, indent=1, sort_keys=True)


if __name__ == "__main__":
    main(*sys.argv[1:4])
