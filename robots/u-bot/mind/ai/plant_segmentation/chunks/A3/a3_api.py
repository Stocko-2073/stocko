"""A3 — the shipped default. Import this; do not re-derive it.

    import sys; sys.path.insert(0, "chunks/A3")
    from a3_api import segment_material
    out = segment_material()                 # A0's 768x1024 label grid
    out.material                             # (1024, 768) uint8, A0 class ids
    out.confidence                           # (1024, 768) float32, max p(class)
    out.classes                              # id -> name

What this is
------------
The winner of the A3 comparison: a multinomial logistic probe on **frozen
DINOv2 patch features**, fitted on the 42 labelled patches in
`seed_patches.json`. Nothing is fine-tuned; the backbone is frozen and the whole
fitted model is a 7 x 1538 matrix.

Scores on `plants.jpeg` (see RESULTS / FINDINGS). Two numbers, kept apart:

* **this frozen patch set** — mean IoU **0.5425**, grass predicted as squash
  material **17.8 %**. That is what this module actually produces.
* **the approach**, over five independent draws of 42 patches — mean IoU
  **0.5537 +- 0.0197** (0.5484 with the fitted patches' own pixels excluded),
  grass-as-squash 25.3 %. That is what a new draw should be expected to give.

Against a recorded ZeroPlantSeg baseline of mean IoU **0.2534** with **53.0 %**
of ground-truth grass absorbed into the crop instance, and IoU exactly 0.0000 on
`grass` and `squash_petiole`, which it cannot express at all.

Three caveats that travel with every output
-------------------------------------------
1. **The label space excludes `soil`.** A0's ground truth has zero soil pixels
   — a mulched bed does not show bare soil — so `soil` can be neither learnt nor
   scored and is never predicted. A5 must not read "not soil" as information.
2. **`confidence` is a probe probability, not a calibrated one.** It is fitted
   on 42 points. Under R2 it is usable as an ordering ("look here first"), not
   as a licence to remove anything.
3. **The 42 patches came from the A0 ground truth**, not from a separate human
   pass (`make_seed_patches.py` says so in its own provenance field). On a new
   image they must be re-made by hand. That is the running cost of this
   approach and it is the reason B1 matters.

`height_above_soil` is deliberately **not** used. It was measured (see
`height_report.py` and FINDINGS) to add +0.000 mean IoU on top of these
features: DINOv2 already knows everything the height channel was contributing.
A4 still wants the height channel for grouping; A3 does not need it to classify.
"""
from __future__ import annotations

import json
import os
import sys
import time
from dataclasses import dataclass, field

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import a3_common as A  # noqa: E402
import eval as a0eval  # noqa: E402
import dino_probe as DP  # noqa: E402

MODEL = "facebook/dinov2-base"      # DINOv3 is a gated Hugging Face repo; see FINDINGS
PROBE_C = 1.0                       # (c) sklearn's default; not tuned. Swept in FINDINGS.
CACHE = os.path.join(A.WORK, "a3_default_features.npz")


@dataclass
class MaterialMap:
    material: np.ndarray             # (H, W) uint8, A0 material class ids
    confidence: np.ndarray           # (H, W) float32, max class probability
    classes: dict                    # id -> name
    grid: tuple
    provenance: dict = field(default_factory=dict)

    def as_names(self) -> dict:
        return {n: int((self.material == i).sum()) for i, n in self.classes.items()}


def _features(image_path, use_cache=True):
    """Frozen DINOv2 fine+coarse patch features for one image."""
    if use_cache and os.path.exists(CACHE):
        z = np.load(CACHE)
        if str(z["image"]) == str(image_path):
            return z["F"].astype(np.float32), tuple(z["grid"]), float(z["seconds"])
    img = Image.open(image_path).convert("RGB")
    t0 = time.time()
    model, patch = DP.load_backbone(MODEL)
    fine, grid, _ = DP.fine_features(model, patch, img)
    coarse = DP.coarse_features(model, patch, img, grid)
    dt = time.time() - t0
    PH, PW = grid
    F = np.concatenate([DP.l2(fine), DP.l2(coarse)], -1).reshape(PH * PW, -1)
    os.makedirs(A.WORK, exist_ok=True)
    np.savez(CACHE, F=F.astype(np.float16), grid=np.array(grid),
             image=str(image_path), seconds=dt)
    return F, grid, dt


def _seed_patches():
    return json.load(open(os.path.join(HERE, "seed_patches.json")))


def segment_material(image_path: str | None = None,
                     use_cache: bool = True) -> MaterialMap:
    """Per-pixel material class on A0's 768x1024 label grid."""
    from sklearn.linear_model import LogisticRegression

    image_path = image_path or os.path.join(A.ROOT, "plants.jpeg")
    F, grid, t_feat = _features(image_path, use_cache)
    PH, PW = grid
    doc = _seed_patches()
    if list(doc["patch_grid"]) != [PH, PW]:
        raise ValueError(
            f"seed patches were placed on a {doc['patch_grid']} grid but the "
            f"features are {[PH, PW]}; re-run make_seed_patches.py")
    idx = np.array([p["patch_row"] * PW + p["patch_col"] for p in doc["patches"]])
    lab = np.array([p["class_id"] for p in doc["patches"]])

    t0 = time.time()
    clf = LogisticRegression(max_iter=2000, C=PROBE_C).fit(F[idx], lab)
    prob = clf.predict_proba(F)
    t_fit = time.time() - t0

    pred = clf.classes_[prob.argmax(1)].astype(np.uint8).reshape(PH, PW)
    conf = prob.max(1).astype(np.float32).reshape(PH, PW)

    yy = np.minimum(np.arange(A.GT_H) * PH // A.GT_H, PH - 1)
    xx = np.minimum(np.arange(A.GT_W) * PW // A.GT_W, PW - 1)
    pid = yy[:, None] * PW + xx[None, :]

    return MaterialMap(
        material=pred.ravel()[pid].astype(np.uint8),
        confidence=conf.ravel()[pid].astype(np.float32),
        classes={int(a0eval.CID[c]): c for c in A.PREDICT_CLASSES},
        grid=(A.GT_H, A.GT_W),
        provenance={
            "chunk": "A3", "method": "frozen DINOv2 patch features + logistic probe",
            "backbone": MODEL, "n_training_patches": doc["n_patches"],
            "training_patch_provenance": doc["provenance"],
            "patch_grid": [PH, PW],
            "label_px_per_patch": round(A.GT_H / PH, 2),
            "classes_never_predicted": ["soil"],
            "soil_note": "A0 has zero soil pixels; a mulched bed shows none.",
            "height_above_soil_used": False,
            "height_ablation": "adding A2 height to these features moved mean "
                               "IoU by +0.000 (0.5267 -> 0.5263)",
            "seconds_features": t_feat, "seconds_fit_and_predict": t_fit,
            # this exact frozen patch set, scored on the A0 ground truth
            "scored_mean_iou_this_patch_set": 0.5425,
            "scored_grass_as_squash_this_patch_set": 0.178,
            # the approach, over five independent draws of 42 patches
            "approach_mean_iou": 0.5537, "approach_mean_iou_sd": 0.0197,
            "approach_mean_iou_training_patches_excluded": 0.5484,
            "approach_grass_as_squash": 0.253,
            "baseline_mean_iou": 0.2534,
            "baseline_grass_absorbed_into_crop": 0.530,
        })


def main():
    import argparse
    ap = argparse.ArgumentParser(description="A3 default material segmentation")
    ap.add_argument("--out", default=os.path.join(HERE, "preds", "a3_default.png"))
    ap.add_argument("--score", action="store_true",
                    help="score against the A0 ground truth and print the report")
    a = ap.parse_args()
    out = segment_material()
    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    Image.fromarray(out.material).save(a.out)
    print(json.dumps(out.provenance, indent=1))
    print("pixels per class:", out.as_names())
    print("wrote", a.out)
    if a.score:
        gt = a0eval.load_gt()
        r = A.score_map(out.material, gt, "A3 default (DINOv2 probe)")
        a0eval.print_report(r)
        print("grass/squash:", json.dumps(A.grass_squash_confusion(r), indent=1))


if __name__ == "__main__":
    main()
