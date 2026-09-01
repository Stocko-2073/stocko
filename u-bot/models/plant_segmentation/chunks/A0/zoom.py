"""A0 helper — zoom on an arbitrary box of the GT grid: plain | assigned classes.

    .venv/bin/python ../chunks/A0/zoom.py X0 Y0 X1 Y1 [--zoom 8] [--name foo]
"""
import argparse
import os

import numpy as np
from PIL import Image, ImageDraw, ImageFont
from scipy import ndimage

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "work")
PALETTE = np.array([
    [255, 0, 255], [0, 190, 0], [0, 255, 255], [255, 240, 0],
    [255, 0, 0], [255, 150, 0], [110, 60, 20], [60, 60, 255], [255, 255, 255],
], np.uint8)


def font(sz):
    p = "/System/Library/Fonts/Supplemental/Arial Bold.ttf"
    return ImageFont.truetype(p, sz) if os.path.exists(p) else ImageFont.load_default()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("box", nargs=4, type=int)
    ap.add_argument("--zoom", type=int, default=8)
    ap.add_argument("--name", default="zoom")
    ap.add_argument("--assign", default="assign.npy")
    ap.add_argument("--alpha", type=float, default=0.42)
    ap.add_argument("--grid", type=int, default=16)
    a = ap.parse_args()
    x0, y0, x1, y1 = a.box
    z = a.zoom

    rgb = Image.open(os.path.join(OUT, "rgb_gtgrid.png")).convert("RGB")
    lab = np.load(os.path.join(OUT, "regions.npy"))
    per = np.load(os.path.join(OUT, a.assign))
    cm = np.concatenate([[0], per]).astype(np.uint8)[lab]

    sub = np.asarray(rgb.crop((x0, y0, x1, y1)), float)
    sl = lab[y0:y1, x0:x1]
    sc = cm[y0:y1, x0:x1]
    plain = Image.fromarray(sub.astype(np.uint8)).resize(
        ((x1 - x0) * z, (y1 - y0) * z), Image.LANCZOS)
    blend = (sub * (1 - a.alpha) + PALETTE[sc].astype(float) * a.alpha).astype(np.uint8)
    right = Image.fromarray(blend).resize(((x1 - x0) * z, (y1 - y0) * z), Image.NEAREST)
    d = ImageDraw.Draw(right)
    diff = np.zeros(sc.shape, bool)
    diff[:, :-1] |= sl[:, :-1] != sl[:, 1:]
    diff[:-1, :] |= sl[:-1, :] != sl[1:, :]
    ys, xs = np.nonzero(diff)
    for y, x in zip(ys, xs):
        d.rectangle([x * z, y * z, x * z + z - 1, y * z + z - 1], fill=(0, 0, 0))
    f = font(max(11, z + 4))
    for v in np.unique(sl):
        m = sl == v
        if m.sum() < 12:
            continue
        dt = ndimage.distance_transform_edt(np.pad(m, 1))[1:-1, 1:-1]
        yy, xx = np.unravel_index(dt.argmax(), dt.shape)
        t = str(int(v))
        d.text((xx * z - 4 * len(t), yy * z - 8), t, font=f, fill=(255, 255, 255),
               stroke_width=2, stroke_fill=(0, 0, 0))
    # coordinate grid on the plain panel so strokes can be read off directly
    dg = ImageDraw.Draw(plain)
    fg = font(11)
    step = a.grid
    if step:
        for x in range(((x0 + step - 1) // step) * step, x1, step):
            dg.line([((x - x0) * z, 0), ((x - x0) * z, (y1 - y0) * z)], fill=(255, 0, 255))
            dg.text(((x - x0) * z + 2, 2), str(x), font=fg, fill=(255, 255, 0),
                    stroke_width=2, stroke_fill=(0, 0, 0))
        for y in range(((y0 + step - 1) // step) * step, y1, step):
            dg.line([(0, (y - y0) * z), ((x1 - x0) * z, (y - y0) * z)], fill=(255, 0, 255))
            dg.text((2, (y - y0) * z + 2), str(y), font=fg, fill=(255, 255, 0),
                    stroke_width=2, stroke_fill=(0, 0, 0))

    W, H = plain.size
    canvas = Image.new("RGB", (W * 2 + 8, H), (20, 20, 20))
    canvas.paste(plain, (0, 0))
    canvas.paste(right, (W + 8, 0))
    p = os.path.join(OUT, f"{a.name}.png")
    canvas.save(p)
    print(p, canvas.size)


if __name__ == "__main__":
    main()
