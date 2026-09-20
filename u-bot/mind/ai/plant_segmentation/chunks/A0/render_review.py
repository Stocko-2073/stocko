"""A0 step 5 — render review tiles: plain 4x zoom | current class assignment.

Left panel is the raw image so I can see what is actually there; right panel is
the same pixels tinted by the class currently assigned, with region ids drawn so
I can name a region when correcting it. Iterating on these tiles *is* the
labelling process.

    .venv/bin/python ../chunks/A0/render_review.py --tag review [--ids]
"""
import argparse
import os

import numpy as np
from PIL import Image, ImageDraw, ImageFont
from scipy import ndimage

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "work")
TILE_W, TILE_H = 192, 256

CLASSES = ["unlabelled", "squash_leaf", "squash_petiole", "grass",
           "broadleaf_weed", "straw", "soil", "fruit", "other"]
PALETTE = np.array([
    [255, 0, 255],    # unlabelled  magenta
    [0, 190, 0],      # squash_leaf green
    [0, 255, 255],    # squash_petiole cyan
    [255, 240, 0],    # grass       yellow
    [255, 0, 0],      # broadleaf_weed red
    [255, 150, 0],    # straw       orange
    [110, 60, 20],    # soil        brown
    [60, 60, 255],    # fruit       blue
    [255, 255, 255],  # other       white
], np.uint8)


def font(sz):
    for p in ("/System/Library/Fonts/Supplemental/Arial Bold.ttf",
              "/System/Library/Fonts/Helvetica.ttc"):
        if os.path.exists(p):
            return ImageFont.truetype(p, sz)
    return ImageFont.load_default()


def class_map(lab, per_region):
    lut = np.concatenate([[0], per_region]).astype(np.uint8)
    return lut[lab]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tag", default="review")
    ap.add_argument("--zoom", type=int, default=4)
    ap.add_argument("--assign", default="assign.npy")
    ap.add_argument("--alpha", type=float, default=0.45)
    ap.add_argument("--only", default=None, help="comma list of r{r}c{c} tiles")
    a = ap.parse_args()

    rgb = Image.open(os.path.join(OUT, "rgb_gtgrid.png")).convert("RGB")
    lab = np.load(os.path.join(OUT, "regions.npy"))
    per = np.load(os.path.join(OUT, a.assign))
    cm = class_map(lab, per)
    H, W = lab.shape
    z, f = a.zoom, font(13)
    os.makedirs(os.path.join(OUT, a.tag), exist_ok=True)
    only = set(a.only.split(",")) if a.only else None

    diff = np.zeros((H, W), bool)
    diff[:, :-1] |= cm[:, :-1] != cm[:, 1:]
    diff[:-1, :] |= cm[:-1, :] != cm[1:, :]

    for r in range(H // TILE_H):
        for c in range(W // TILE_W):
            name = f"r{r}c{c}"
            if only and name not in only:
                continue
            x0, y0 = c * TILE_W, r * TILE_H
            box = (x0, y0, x0 + TILE_W, y0 + TILE_H)
            plain = rgb.crop(box).resize((TILE_W * z, TILE_H * z), Image.LANCZOS)
            sub = np.asarray(rgb.crop(box), float)
            col = PALETTE[cm[y0:y0 + TILE_H, x0:x0 + TILE_W]].astype(float)
            blend = (sub * (1 - a.alpha) + col * a.alpha).astype(np.uint8)
            right = Image.fromarray(blend).resize((TILE_W * z, TILE_H * z), Image.NEAREST)
            d = ImageDraw.Draw(right)
            sd = diff[y0:y0 + TILE_H, x0:x0 + TILE_W]
            ys, xs = np.nonzero(sd)
            for y, x in zip(ys, xs):
                d.rectangle([x * z, y * z, x * z + z - 1, y * z + z - 1], fill=(0, 0, 0))
            sl = lab[y0:y0 + TILE_H, x0:x0 + TILE_W]
            for v in np.unique(sl):
                if v == 0:
                    continue
                m = sl == v
                if m.sum() < 40:
                    continue
                dt = ndimage.distance_transform_edt(np.pad(m, 1))[1:-1, 1:-1]
                yy, xx = np.unravel_index(dt.argmax(), dt.shape)
                t = str(int(v))
                d.text((xx * z - 4 * len(t), yy * z - 7), t, font=f,
                       fill=(255, 255, 255), stroke_width=2, stroke_fill=(0, 0, 0))
            canvas = Image.new("RGB", (TILE_W * z * 2 + 8, TILE_H * z), (20, 20, 20))
            canvas.paste(plain, (0, 0))
            canvas.paste(right, (TILE_W * z + 8, 0))
            canvas.save(os.path.join(OUT, a.tag, name + ".png"))
    print("->", os.path.join(OUT, a.tag))


if __name__ == "__main__":
    main()
