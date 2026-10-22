"""
Cuts the Panda Drums sprite sheet into the layers the plugin draws, at 4x.

    python sheet_cut.py <source_sprite_sheet.png> <RealESRGAN_x4plus.pth> <outdir>

The sheet (the "Panda Drums GUI assets" source sheet) has every piece on a transparent
background: the twelve faces, the poses, the paws with sticks, the kit, the hardware and the
stage. Each piece is cut out by its box below, its colours are bled out under the transparent
edge (so no dark fringe appears when it is scaled), and it is upscaled 4x with Real-ESRGAN
(colour and alpha separately). Writes <name>.png at 4x and sheet.json with each piece's size.

Needs torch, numpy, Pillow and OpenCV.
"""

import json
import os
import sys

import cv2
import numpy as np
import torch
from torch import nn
from torch.nn import functional as F

# name: (x, y, w, h) on the 1536 x 1024 sheet, the label underneath left out.
PIECES = {
    # Faces (they end in a little purple collar).
    "face_neutral": (10, 8, 120, 117), "face_happy": (145, 8, 121, 117), "face_open_mouth": (280, 8, 120, 117),
    "face_smile": (413, 8, 115, 117), "face_focused": (539, 8, 114, 117), "face_excited": (663, 8, 114, 117),
    "face_wink": (786, 8, 114, 117), "face_laugh": (913, 8, 115, 117), "face_surprised": (1036, 8, 112, 117),
    "face_tongue_out": (1155, 8, 116, 117), "face_angry": (1283, 7, 121, 118), "face_sad": (1414, 8, 119, 117),
    # Whole-body poses.
    "pose_idle": (3, 162, 121, 152), "pose_blink": (127, 161, 122, 152), "pose_kick": (255, 154, 149, 161),
    "pose_snare": (414, 159, 114, 155), "pose_hi_hat": (530, 162, 108, 152), "pose_tom_left": (661, 161, 133, 156),
    "pose_tom_right": (805, 154, 123, 164), "pose_crash_left": (904, 166, 188, 154), "pose_crash_right": (1055, 168, 174, 152),
    "pose_fill": (1204, 168, 186, 151), "pose_cheer": (1382, 149, 142, 167),
    # Paws with sticks, and motion streaks.
    "stick_1": (14, 343, 45, 92), "stick_2": (84, 348, 62, 89), "stick_3": (172, 348, 49, 89), "stick_4": (242, 348, 81, 86),
    "stick_5": (335, 341, 59, 97), "stick_6": (437, 381, 70, 63), "stick_7": (518, 343, 64, 101), "stick_8": (608, 369, 109, 72),
    "stick_9": (767, 351, 49, 95), "stick_10": (883, 345, 52, 95), "stick_11": (955, 358, 112, 86),
    "blur_1": (1089, 370, 111, 58), "blur_2": (1231, 387, 121, 44), "blur_3": (1385, 382, 119, 58),
    # Kit.
    "kick": (3, 472, 205, 170), "snare": (212, 522, 132, 93), "tom_left": (356, 501, 122, 132), "tom_right": (493, 509, 107, 124),
    "floor_tom": (618, 500, 126, 133), "hihat_top": (763, 507, 118, 120), "hihat_bottom": (890, 522, 139, 105),
    "crash_left": (1034, 512, 177, 120), "crash_right": (1214, 523, 137, 106), "ride": (1354, 505, 179, 121),
    # Hardware.
    "kick_pedal": (8, 671, 89, 125), "hihat_stand": (120, 653, 131, 143), "snare_stand": (263, 674, 91, 123),
    "tom_stand": (368, 659, 85, 136), "cymbal_stand": (463, 666, 129, 132), "throne": (616, 690, 96, 108),
    # Stage.
    "heart_red": (743, 719, 49, 45), "heart_pink": (825, 721, 46, 43), "heart_yellow": (904, 720, 47, 44),
    "bamboo_left": (960, 660, 100, 135), "bamboo_right": (1058, 662, 96, 133), "lights_string": (1166, 692, 364, 75),
    "background": (14, 824, 410, 170), "rug": (429, 860, 344, 102), "spotlights": (769, 828, 315, 150),
    "hit_spark": (1143, 869, 92, 91), "heart_particles": (1270, 852, 66, 101), "glow_particles": (1396, 852, 92, 100),
}


# ---------------------------------------------------------------------------- Real-ESRGAN
class RDB(nn.Module):
    def __init__(self, nf=64, gc=32):
        super().__init__()
        self.conv1 = nn.Conv2d(nf, gc, 3, 1, 1)
        self.conv2 = nn.Conv2d(nf + gc, gc, 3, 1, 1)
        self.conv3 = nn.Conv2d(nf + 2 * gc, gc, 3, 1, 1)
        self.conv4 = nn.Conv2d(nf + 3 * gc, gc, 3, 1, 1)
        self.conv5 = nn.Conv2d(nf + 4 * gc, nf, 3, 1, 1)

    def forward(self, x):
        l = lambda t: F.leaky_relu(t, 0.2)
        x1 = l(self.conv1(x))
        x2 = l(self.conv2(torch.cat((x, x1), 1)))
        x3 = l(self.conv3(torch.cat((x, x1, x2), 1)))
        x4 = l(self.conv4(torch.cat((x, x1, x2, x3), 1)))
        return self.conv5(torch.cat((x, x1, x2, x3, x4), 1)) * 0.2 + x


class RRDB(nn.Module):
    def __init__(self, nf=64):
        super().__init__()
        self.rdb1, self.rdb2, self.rdb3 = RDB(nf), RDB(nf), RDB(nf)

    def forward(self, x):
        return self.rdb3(self.rdb2(self.rdb1(x))) * 0.2 + x


class RRDBNet(nn.Module):
    def __init__(self, nf=64, blocks=23):
        super().__init__()
        self.conv_first = nn.Conv2d(3, nf, 3, 1, 1)
        self.body = nn.Sequential(*[RRDB(nf) for _ in range(blocks)])
        self.conv_body = nn.Conv2d(nf, nf, 3, 1, 1)
        self.conv_up1 = nn.Conv2d(nf, nf, 3, 1, 1)
        self.conv_up2 = nn.Conv2d(nf, nf, 3, 1, 1)
        self.conv_hr = nn.Conv2d(nf, nf, 3, 1, 1)
        self.conv_last = nn.Conv2d(nf, 3, 3, 1, 1)

    def forward(self, x):
        l = lambda t: F.leaky_relu(t, 0.2)
        feat = self.conv_first(x)
        feat = feat + self.conv_body(self.body(feat))
        feat = l(self.conv_up1(F.interpolate(feat, scale_factor=2, mode="nearest")))
        feat = l(self.conv_up2(F.interpolate(feat, scale_factor=2, mode="nearest")))
        return self.conv_last(l(self.conv_hr(feat)))


def upscale(model, rgb, tile=192, pad=12):
    """rgb: HxWx3 float 0..1 -> 4H x 4W x 3, in tiles."""
    h, w, _ = rgb.shape
    out = np.zeros((h * 4, w * 4, 3), np.float32)
    x_t = torch.from_numpy(rgb.transpose(2, 0, 1)).unsqueeze(0)
    with torch.no_grad():
        for y0 in range(0, h, tile):
            for x0 in range(0, w, tile):
                y1, x1 = min(h, y0 + tile), min(w, x0 + tile)
                py0, px0, py1, px1 = max(0, y0 - pad), max(0, x0 - pad), min(h, y1 + pad), min(w, x1 + pad)
                res = model(x_t[:, :, py0:py1, px0:px1]).clamp(0, 1)[0].numpy().transpose(1, 2, 0)
                oy, ox = (y0 - py0) * 4, (x0 - px0) * 4
                out[y0 * 4:y1 * 4, x0 * 4:x1 * 4] = res[oy:oy + (y1 - y0) * 4, ox:ox + (x1 - x0) * 4]
    return out


# ---------------------------------------------------------------------------- cutting
def bleed(rgb, alpha, steps=12):
    """Spread the colours of the opaque pixels into the transparent ones around them."""
    rgb = rgb.copy()
    known = alpha > 0.5
    k = np.ones((3, 3), np.float32)
    for _ in range(steps):
        w = cv2.filter2D(known.astype(np.float32), -1, k)
        acc = cv2.filter2D(rgb * known[..., None], -1, k)
        grow = (~known) & (w > 0)
        rgb[grow] = acc[grow] / w[grow][:, None]
        known = known | grow
    return rgb


def main(sheet_path, weights, outdir):
    os.makedirs(outdir, exist_ok=True)
    torch.set_num_threads(os.cpu_count() or 4)
    model = RRDBNet()
    state = torch.load(weights, map_location="cpu")
    model.load_state_dict(state.get("params_ema", state.get("params", state)), strict=True)
    model.eval()
    sheet = cv2.imread(sheet_path, cv2.IMREAD_UNCHANGED)
    rgb_all = cv2.cvtColor(sheet[..., :3], cv2.COLOR_BGR2RGB).astype(np.float32) / 255.0
    alpha_all = sheet[..., 3].astype(np.float32) / 255.0
    only = set(sys.argv[4].split(",")) if len(sys.argv) > 4 else None
    info = {}
    for name, (x, y, w, h) in PIECES.items():
        if only and name not in only:
            continue
        p = 6
        x0, y0, x1, y1 = max(0, x - p), max(0, y - p), min(sheet.shape[1], x + w + p), min(sheet.shape[0], y + h + p)
        rgb, alpha = rgb_all[y0:y1, x0:x1], alpha_all[y0:y1, x0:x1].copy()
        # Keep the largest pieces only: drop specks from neighbours and label letters.
        mask = (alpha > 0.12).astype(np.uint8)
        n, lab, stats, _ = cv2.connectedComponentsWithStats(mask, 8)
        if n > 2:
            biggest = stats[1:, 4].max()
            keep = np.zeros(n, bool)
            keep[1:] = stats[1:, 4] >= max(25, 0.08 * biggest)
            alpha *= keep[lab] | (cv2.dilate((keep[lab]).astype(np.uint8), np.ones((5, 5), np.uint8)) > 0)
        rgb = bleed(rgb, alpha)
        big_rgb = upscale(model, rgb)
        big_a = upscale(model, np.repeat(alpha[..., None], 3, 2)).mean(2)
        big_a = np.clip((big_a - 0.02) / 0.96, 0, 1)
        out = np.dstack([big_rgb, big_a])
        out = (out * 255 + 0.5).clip(0, 255).astype(np.uint8)
        # Trim to the content.
        ys, xs = np.nonzero(out[..., 3] > 6)
        if len(xs):
            out = out[ys.min():ys.max() + 1, xs.min():xs.max() + 1]
        cv2.imwrite(os.path.join(outdir, name + ".png"), cv2.cvtColor(out, cv2.COLOR_RGBA2BGRA))
        info[name] = dict(w=int(out.shape[1]), h=int(out.shape[0]), sheet=[x0 + int(xs.min()) / 4 if len(xs) else x0,
                                                                            y0 + int(ys.min()) / 4 if len(ys) else y0])
        print(name, out.shape[1], "x", out.shape[0], flush=True)
    path = os.path.join(outdir, "sheet.json")
    old = json.load(open(path)) if os.path.exists(path) else {}
    old.update(info)
    json.dump(old, open(path, "w"), indent=1)


if __name__ == "__main__":
    main(*sys.argv[1:4])
