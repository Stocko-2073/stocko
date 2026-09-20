"""A0 — final verification figures for the ground truth.

    cd ZeroPlantSeg && .venv/bin/python ../chunks/A0/render_gt_figures.py

Writes chunks/A0/figs/: the material overlay, the instance overlay with contact
points marked, and a legend. These are what I checked by eye before calling A0
done; the 4x tile set used during labelling is in chunks/A0/work/review4/.
"""
import json
import os

import numpy as np
from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
GT = os.path.join(ROOT, "groundtruth")
FIGS = os.path.join(HERE, "figs")

CLASSES = ["unlabelled", "squash_leaf", "squash_petiole", "grass",
           "broadleaf_weed", "straw", "soil", "fruit", "other"]
PALETTE = np.array([
    [255, 0, 255], [0, 190, 0], [0, 255, 255], [255, 240, 0],
    [255, 0, 0], [255, 150, 0], [110, 60, 20], [60, 60, 255], [255, 255, 255]], np.uint8)
INST_COLORS = np.array([
    [0, 0, 0], [0, 220, 60], [255, 60, 60], [255, 160, 40], [255, 240, 60],
    [200, 60, 255], [60, 200, 255], [255, 120, 200], [140, 255, 140],
    [255, 90, 0], [120, 120, 255]], np.uint8)


def font(sz):
    p = "/System/Library/Fonts/Supplemental/Arial Bold.ttf"
    return ImageFont.truetype(p, sz) if os.path.exists(p) else ImageFont.load_default()


def main():
    os.makedirs(FIGS, exist_ok=True)
    rgb = np.asarray(Image.open(os.path.join(HERE, "work/rgb_gtgrid.png")).convert("RGB"), float)
    mat = np.array(Image.open(os.path.join(GT, "plants_material.png")))
    inst = np.array(Image.open(os.path.join(GT, "plants_instances.png")))
    contacts = json.load(open(os.path.join(GT, "plants_contacts.json")))
    H, W = mat.shape

    blend = (rgb * 0.5 + PALETTE[mat].astype(float) * 0.5).astype(np.uint8)
    out = Image.new("RGB", (W * 2 + 8, H + 130), (16, 16, 16))
    out.paste(Image.fromarray(rgb.astype(np.uint8)), (0, 0))
    out.paste(Image.fromarray(blend), (W + 8, 0))
    d = ImageDraw.Draw(out)
    f = font(15)
    for i, c in enumerate(CLASSES):
        x, y = 12 + (i % 5) * 300, H + 14 + (i // 5) * 34
        d.rectangle([x, y, x + 22, y + 20], fill=tuple(int(v) for v in PALETTE[i]))
        d.text((x + 30, y + 2), f"{i}  {c}", font=f, fill=(235, 235, 235))
    out.save(os.path.join(FIGS, "gt_material.png"))

    ic = np.zeros((H, W, 3), np.uint8)
    for v in np.unique(inst):
        if v == 0:
            continue
        ic[inst == v] = ((160, 160, 160) if v == 255
                         else tuple(int(x) for x in INST_COLORS[v % len(INST_COLORS)]))
    blend = (rgb * 0.5 + ic.astype(float) * 0.5).astype(np.uint8)
    im = Image.fromarray(blend)
    d = ImageDraw.Draw(im)
    for e in contacts["instances"]:
        x, y = e["point"]
        d.ellipse([x - 9, y - 9, x + 9, y + 9], outline=(255, 255, 255), width=3)
        d.line([x - 14, y, x + 14, y], fill=(0, 0, 0), width=2)
        d.line([x, y - 14, x, y + 14], fill=(0, 0, 0), width=2)
        d.text((x + 14, y - 8), f'{e["id"]} {e["status"]}', font=font(13),
               fill=(255, 255, 255), stroke_width=2, stroke_fill=(0, 0, 0))
    out = Image.new("RGB", (W * 2 + 8, H + 60), (16, 16, 16))
    out.paste(Image.fromarray(rgb.astype(np.uint8)), (0, 0))
    out.paste(im, (W + 8, 0))
    d = ImageDraw.Draw(out)
    d.text((12, H + 16), "grey = grass, instance id 255, unresolved and excluded from "
           "instance scoring;  crosshair = stem-soil contact point",
           font=font(15), fill=(235, 235, 235))
    out.save(os.path.join(FIGS, "gt_instances.png"))
    print("wrote", FIGS)


if __name__ == "__main__":
    main()
