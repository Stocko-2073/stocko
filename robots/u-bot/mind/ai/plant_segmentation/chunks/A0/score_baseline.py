"""A0 — score the ZeroPlantSeg baseline against the A0 ground truth.

ZeroPlantSeg emits plant *instances*, not material classes, so a material-layer
score needs a mapping. Two are reported, both stated rather than tuned:

  charitable  every pixel of the three squash instances (2, 4, 5) is called
              `squash_leaf`, instance 3 (the clover patch it isolated) is called
              `broadleaf_weed`, and background is called `straw`. This is the
              most favourable reading of its output.
  plant/not   a config-free binary: any instance pixel vs background, scored
              against GT plant material (squash leaf/petiole/fruit + grass +
              broadleaf weed).

Both run at 768x1024, the resolution ZeroPlantSeg itself uses, so nothing is
resampled.

    cd ZeroPlantSeg && .venv/bin/python ../chunks/A0/score_baseline.py
"""
import json
import os
import sys

import numpy as np
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from eval import (CID, GT_DIR, ROOT, load_gt, load_prediction, print_report,  # noqa: E402
                  score, UNLABELLED)

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "baseline")
ZPS_INST = os.path.join(ROOT, "ZeroPlantSeg/output_p/plant_instance/squash/test/plants.png")
SQUASH_IDS = (2, 4, 5)     # from RESULTS.md, the recorded baseline run
CLOVER_ID = 3


def main():
    os.makedirs(OUT, exist_ok=True)
    gt = load_gt()
    inst = np.array(Image.open(ZPS_INST)).astype(np.int32)

    results = {}

    pred = load_prediction(instances=inst, name="ZeroPlantSeg instances "
                           "(squash.yaml, eps=100, min_samples=2)", gt=gt)
    r = score(pred, gt)
    print_report(r)
    results["instances"] = r

    mat = np.full(inst.shape, CID["straw"], np.uint8)
    for i in SQUASH_IDS:
        mat[inst == i] = CID["squash_leaf"]
    mat[inst == CLOVER_ID] = CID["broadleaf_weed"]
    pred = load_prediction(material=mat, name="ZeroPlantSeg material "
                           "(charitable mapping: squash instances -> squash_leaf, "
                           "clover instance -> broadleaf_weed, background -> straw)",
                           gt=gt)
    r = score(pred, gt)
    print_report(r)
    results["material_charitable"] = r

    plant_gt = np.isin(gt.material, [CID["squash_leaf"], CID["squash_petiole"],
                                     CID["fruit"], CID["grass"], CID["broadleaf_weed"]])
    valid = gt.material != UNLABELLED
    plant_pred = inst > 0
    inter = int((plant_gt & plant_pred & valid).sum())
    union = int(((plant_gt | plant_pred) & valid).sum())
    binary = {"plant_vs_background_iou": inter / union,
              "gt_plant_px": int((plant_gt & valid).sum()),
              "pred_plant_px": int((plant_pred & valid).sum()),
              "note": "config-free: any ZeroPlantSeg instance pixel vs any GT plant "
                      "material (squash leaf/petiole/fruit, grass, broadleaf weed)"}
    print(f"=== plant vs background ===\n  IoU {binary['plant_vs_background_iou']:.4f}"
          f"   GT plant {binary['gt_plant_px']} px, pred plant {binary['pred_plant_px']} px\n")
    results["plant_vs_background"] = binary

    json.dump(results, open(os.path.join(OUT, "zps_baseline_scores.json"), "w"), indent=1)
    print("wrote", os.path.join(OUT, "zps_baseline_scores.json"))


if __name__ == "__main__":
    main()
