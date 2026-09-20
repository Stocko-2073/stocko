"""Probe stage A3 — the shipped material probe (frozen DINOv2 + the 42-patch
logistic probe fitted on plants.jpeg) applied unchanged to plants2.jpeg.

Runs in chunks/A3/.venv. Nothing is refitted: the seed patches are the ones
shipped in chunks/A3/seed_patches.json, so this is a pure transfer test.

The feature cache is redirected so A3's own cache for plants.jpeg is untouched.
"""
import json
import sys
import time

import numpy as np
from PIL import Image

from probe_common import CH, IMAGE, P, RESULTS, on_path

on_path("A3", "A0")
import a3_api  # noqa: E402
import eval as a0eval  # noqa: E402

WORK = P["A3"] / "work"
WORK.mkdir(exist_ok=True)
a3_api.CACHE = str(WORK / "a3_default_features_plants2.npz")   # never A3's own cache

t0 = time.time()
out = a3_api.segment_material(image_path=str(IMAGE), use_cache=True)
dt = time.time() - t0

np.save(P["A3"] / "material.npy", out.material)
np.save(P["A3"] / "confidence.npy", out.confidence)
# palette PNG for looking at, same palette as the ground-truth material map
gt_meta = json.load(open(CH["A0"].parent.parent / "groundtruth" / "plants_gt.json"))
pal = gt_meta.get("palette") or gt_meta.get("material_palette")
im = Image.fromarray(out.material.astype(np.uint8), mode="P")
if pal:
    flat = []
    for i in range(256):
        c = pal[str(i)] if isinstance(pal, dict) and str(i) in pal else (pal[i] if isinstance(pal, list) and i < len(pal) else [0, 0, 0])
        flat += list(c)[:3]
    im.putpalette(flat)
(P["A3"] / "preds").mkdir(exist_ok=True)
im.save(P["A3"] / "preds" / "material_plants2.png")

n = out.material.size
fractions = {a0eval.CLASSES[i]: round(float((out.material == i).sum()) / n, 4) for i in range(len(a0eval.CLASSES))}
conf = {a0eval.CLASSES[i]: round(float(np.median(out.confidence[out.material == i])), 3)
        for i in range(len(a0eval.CLASSES)) if (out.material == i).any()}
rep = {
    "image": str(IMAGE.name),
    "grid_hw": list(out.material.shape),
    "seconds": dt,
    "class_fraction": fractions,
    "median_confidence_by_predicted_class": conf,
    "overall_median_confidence": float(np.median(out.confidence)),
    "provenance": out.provenance,
    "note": "shipped plants.jpeg probe applied unchanged; NO ground truth for plants2, so no score",
}
json.dump(rep, open(RESULTS / "a3_material.json", "w"), indent=1, default=str)
print(json.dumps({k: rep[k] for k in ("seconds", "class_fraction", "median_confidence_by_predicted_class", "overall_median_confidence")}, indent=1))
