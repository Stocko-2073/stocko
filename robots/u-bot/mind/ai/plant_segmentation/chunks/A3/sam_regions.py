"""A3 step 1 — an INDEPENDENT SAM region partition for A3.

Why not reuse A0's partition?
----------------------------
A0's ground truth was painted region-by-region *onto* A0's SAM partition
(`chunks/A0/work/regions.npy`). Classifying those same regions therefore has
zero boundary error by construction: every region is pure by definition, and the
achievable ceiling is IoU 1.0. Scoring a region classifier on that partition
measures the classifier's label decisions only, with the hardest half of the
problem (where does the grass blade end) handed to it for free.

So A3 runs SAM again with *different* generator settings, producing an
independent partition whose boundaries were never seen by the labeller. Every
headline A3 number is on this partition. A0's partition is kept and scored too,
but only as a clearly-labelled **oracle-boundary ceiling**.

SAM is used ONLY to draw boundaries. Nothing here assigns a class.

    cd ZeroPlantSeg && export PYTORCH_ENABLE_MPS_FALLBACK=1 PYTHONPATH=.
    .venv/bin/python ../chunks/A3/sam_regions.py
"""
import json
import os
import sys
import time

import numpy as np
import torch
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
ZPS = os.path.join(ROOT, "ZeroPlantSeg")
sys.path.insert(0, ZPS)

from segment_anything import sam_model_registry, SamAutomaticMaskGenerator  # noqa: E402

GT_W, GT_H = 768, 1024          # (a) A0's registered label grid
OUT = os.path.join(HERE, "work")

# Generator settings, deliberately different from A0's (48 / 0.80 / 0.88 / 60)
# so the proposal set is independent rather than a re-derivation of the same one.
POINTS_PER_SIDE = 32
PRED_IOU_THRESH = 0.86
STABILITY_THRESH = 0.92
MIN_MASK_REGION_AREA = 40


def main(prefix="a3_", pps=POINTS_PER_SIDE, iou=PRED_IOU_THRESH,
         stab=STABILITY_THRESH, mmra=MIN_MASK_REGION_AREA):
    os.makedirs(OUT, exist_ok=True)
    device = "mps" if torch.backends.mps.is_available() else "cpu"
    img = Image.open(os.path.join(ROOT, "plants.jpeg")).resize((GT_W, GT_H), Image.LANCZOS)
    img.save(os.path.join(OUT, "rgb_gtgrid.png"))
    arr = np.array(img)

    sam = sam_model_registry["vit_h"](
        checkpoint=os.path.join(ZPS, "weights/sam_vit_h_4b8939.pth"))
    sam.to(device=device)
    gen = SamAutomaticMaskGenerator(
        sam,
        points_per_side=pps,
        pred_iou_thresh=iou,
        stability_score_thresh=stab,
        crop_n_layers=1,
        crop_n_points_downscale_factor=2,
        min_mask_region_area=mmra,
    )
    t0 = time.time()
    masks = gen.generate(arr)
    dt = time.time() - t0
    masks.sort(key=lambda m: -m["area"])
    print(f"{len(masks)} masks in {dt:.1f}s on {device}")

    stack = np.zeros((len(masks), GT_H, GT_W), bool)
    meta = []
    for i, m in enumerate(masks):
        stack[i] = m["segmentation"]
        meta.append(dict(idx=i, area=int(m["area"]), bbox=[int(v) for v in m["bbox"]],
                         iou=float(m["predicted_iou"]),
                         stab=float(m["stability_score"])))
    np.save(os.path.join(OUT, f"{prefix}sam_masks.npy"), np.packbits(stack, axis=-1))
    np.save(os.path.join(OUT, f"{prefix}sam_masks_shape.npy"), np.array(stack.shape))
    json.dump({"n_masks": len(masks), "seconds": dt, "device": device,
               "points_per_side": pps, "pred_iou_thresh": iou,
               "stability_score_thresh": stab, "min_mask_region_area": mmra,
               "masks": meta},
              open(os.path.join(OUT, f"{prefix}sam_meta.json"), "w"), indent=1)
    print("saved", stack.shape)


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--prefix", default="a3_")
    ap.add_argument("--pps", type=int, default=POINTS_PER_SIDE)
    ap.add_argument("--iou", type=float, default=PRED_IOU_THRESH)
    ap.add_argument("--stab", type=float, default=STABILITY_THRESH)
    ap.add_argument("--mmra", type=int, default=MIN_MASK_REGION_AREA)
    a = ap.parse_args()
    main(a.prefix, a.pps, a.iou, a.stab, a.mmra)
