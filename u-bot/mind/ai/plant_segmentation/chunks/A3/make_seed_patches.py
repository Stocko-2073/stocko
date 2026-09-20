"""A3 — freeze the 42 labelled patches the shipped default is fitted on.

The winning approach is a probe over a few dozen labelled patches. To ship it as
a callable default the patch set has to be a committed artifact rather than
something re-drawn from the ground truth at import time, so this writes
`seed_patches.json`: 6 patches per class x 7 classes, each recorded as a
(row, col) on the 292x219 DINOv2 fine-patch grid, its class, and its centre in
A0 label-grid pixels so a human can look at it.

Provenance, stated plainly: these 42 labels came from the A0 ground truth (draw
0 of `dino_probe.py`, RNG seed 1000, patches whose label-grid footprint is 100 %
one class), not from a fresh human pass. They are the stand-in for the clicks a
user would make. On any new image they would have to be re-made by hand — that
is what "a few dozen hand-labelled patches" costs, and it is the honest price of
this approach. Their pixels are 0.07 % of the frame and every A3 score is
reported both with and without them.
"""
from __future__ import annotations

import json
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import a3_common as A  # noqa: E402
import eval as a0eval  # noqa: E402
from dino_probe import DEFAULT_PER_CLASS, FINE_H, FINE_W, PATCH, patch_gt  # noqa: E402

SEED = 1000     # draw 0 of dino_probe.py, so the shipped set is the one scored


def main(per_class=DEFAULT_PER_CLASS, seed=SEED):
    gt = a0eval.load_gt()
    grid = (FINE_H // PATCH, FINE_W // PATCH)
    ygrid, purity, _ = patch_gt(grid, gt)
    PH, PW = grid
    y, pur = ygrid.ravel(), purity.ravel()

    rng = np.random.default_rng(seed)
    out = []
    for c in A.PREDICT_CLASSES:
        cid = a0eval.CID[c]
        idx = np.where((y == cid) & (pur >= 1.0))[0]
        if len(idx) == 0:
            print(f"WARNING: no pure patch for {c}")
            continue
        take = rng.choice(idx, size=min(per_class, len(idx)), replace=False)
        for t in take:
            r, col = int(t // PW), int(t % PW)
            out.append({"class": c, "class_id": int(cid),
                        "patch_row": r, "patch_col": col,
                        "label_grid_xy": [round((col + 0.5) * A.GT_W / PW, 1),
                                          round((r + 0.5) * A.GT_H / PH, 1)]})
    doc = {
        "provenance": "sampled from A0 ground truth, draw 0 of dino_probe.py "
                      f"(rng seed {seed}); patches with a 100 % pure label-grid "
                      "footprint. NOT an independent human pass.",
        "patch_grid": [PH, PW], "fine_image": [FINE_H, FINE_W],
        "patch_px": PATCH, "per_class": per_class,
        "n_patches": len(out), "classes": A.PREDICT_CLASSES,
        "patches": out,
    }
    p = os.path.join(HERE, "seed_patches.json")
    json.dump(doc, open(p, "w"), indent=1)
    print(f"{len(out)} patches -> {p}")
    counts = {}
    for e in out:
        counts[e["class"]] = counts.get(e["class"], 0) + 1
    print(counts)


if __name__ == "__main__":
    main()
