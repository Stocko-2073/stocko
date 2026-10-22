"""A0 step 1 — propose crisp region boundaries with SAM ViT-H.

SAM is used ONLY to draw boundaries. Every class label attached to a proposal
later is assigned by human/agent visual verification of that region (see
chunks/A0/FINDINGS.md). Nothing here classifies anything.

Run from the ZeroPlantSeg directory so the venv and weights resolve:

    cd ZeroPlantSeg
    export PYTORCH_ENABLE_MPS_FALLBACK=1 PYTHONPATH=.
    .venv/bin/python ../chunks/A0/sam_propose.py
"""
import os
import sys
import numpy as np
import torch
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))
ROOT = os.path.abspath(os.path.join(ROOT, ".."))  # plant_segmentation/
ZPS = os.path.join(ROOT, "ZeroPlantSeg")
sys.path.insert(0, ZPS)

from segment_anything import sam_model_registry, SamAutomaticMaskGenerator

# GT canonical grid: 768x1024 (native 3000x4000 / 3.90625). See FINDINGS.md.
GT_W, GT_H = 768, 1024
OUT = os.path.join(HERE, "work")
os.makedirs(OUT, exist_ok=True)


def main():
    device = "mps" if torch.backends.mps.is_available() else "cpu"
    img = Image.open(os.path.join(ROOT, "plants.jpeg")).resize((GT_W, GT_H), Image.LANCZOS)
    img.save(os.path.join(OUT, "rgb_gtgrid.png"))
    arr = np.array(img)

    sam = sam_model_registry["vit_h"](checkpoint=os.path.join(ZPS, "weights/sam_vit_h_4b8939.pth"))
    sam.to(device=device)
    gen = SamAutomaticMaskGenerator(
        sam,
        points_per_side=48,
        pred_iou_thresh=0.80,
        stability_score_thresh=0.88,
        crop_n_layers=1,
        crop_n_points_downscale_factor=2,
        min_mask_region_area=60,
    )
    masks = gen.generate(arr)
    masks.sort(key=lambda m: -m["area"])
    print(f"{len(masks)} masks")

    seg = np.zeros((GT_H, GT_W), np.uint8)  # bool-packed store
    stack = np.zeros((len(masks), GT_H, GT_W), bool)
    meta = []
    for i, m in enumerate(masks):
        stack[i] = m["segmentation"]
        meta.append(dict(idx=i, area=int(m["area"]), bbox=[int(v) for v in m["bbox"]],
                         iou=float(m["predicted_iou"]), stab=float(m["stability_score"]),
                         point=[float(v) for v in m["point_coords"][0]]))
    np.save(os.path.join(OUT, "sam_masks.npy"), np.packbits(stack, axis=-1))
    np.save(os.path.join(OUT, "sam_masks_shape.npy"), np.array(stack.shape))
    import json
    json.dump(meta, open(os.path.join(OUT, "sam_meta.json"), "w"), indent=1)
    print("saved", stack.shape)


if __name__ == "__main__":
    main()
