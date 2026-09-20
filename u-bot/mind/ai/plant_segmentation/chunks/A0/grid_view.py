"""A0 helper — the image with a labelled coordinate grid, so I can read GT-grid
coordinates straight off a picture and feed them to trace.py / zoom.py.

    .venv/bin/python ../chunks/A0/grid_view.py [X0 Y0 X1 Y1] [--zoom 2] [--step 32]
"""
import argparse
import os

from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "work")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("box", nargs="*", type=int, default=[0, 0, 768, 1024])
    ap.add_argument("--zoom", type=int, default=2)
    ap.add_argument("--step", type=int, default=32)
    ap.add_argument("--name", default="grid_view")
    a = ap.parse_args()
    x0, y0, x1, y1 = a.box
    z, s = a.zoom, a.step
    im = Image.open(os.path.join(OUT, "rgb_gtgrid.png")).convert("RGB").crop((x0, y0, x1, y1))
    im = im.resize(((x1 - x0) * z, (y1 - y0) * z), Image.LANCZOS)
    d = ImageDraw.Draw(im)
    fp = "/System/Library/Fonts/Supplemental/Arial Bold.ttf"
    f = ImageFont.truetype(fp, 12) if os.path.exists(fp) else ImageFont.load_default()
    for x in range(((x0 + s - 1) // s) * s, x1, s):
        d.line([((x - x0) * z, 0), ((x - x0) * z, (y1 - y0) * z)], fill=(255, 0, 255))
        d.text(((x - x0) * z + 2, 2), str(x), font=f, fill=(255, 255, 0),
               stroke_width=2, stroke_fill=(0, 0, 0))
    for y in range(((y0 + s - 1) // s) * s, y1, s):
        d.line([(0, (y - y0) * z), ((x1 - x0) * z, (y - y0) * z)], fill=(255, 0, 255))
        d.text((2, (y - y0) * z + 2), str(y), font=f, fill=(255, 255, 0),
               stroke_width=2, stroke_fill=(0, 0, 0))
    p = os.path.join(OUT, a.name + ".png")
    im.save(p)
    print(p, im.size)


if __name__ == "__main__":
    main()
