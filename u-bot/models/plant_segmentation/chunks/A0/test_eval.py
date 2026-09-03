"""A0 — sanity tests for eval.py. Run: .venv/bin/python ../chunks/A0/test_eval.py"""
import os
import sys

import numpy as np
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from eval import (CID, GRASS_UNRESOLVED, load_gt, load_prediction, score,  # noqa: E402
                  to_gt_grid)

ok = True


def check(name, cond):
    global ok
    print(("PASS  " if cond else "FAIL  ") + name)
    ok = ok and cond


gt = load_gt()

# 1. the ground truth scores perfectly against itself
p = load_prediction(material=gt.material.copy(), instances=gt.instances.copy(),
                    contacts={e["id"]: e["point"] for e in gt.contacts["instances"]},
                    name="self", gt=gt)
r = score(p, gt)
check("self-score: every present class has IoU 1.0",
      all(abs(v["iou"] - 1.0) < 1e-9 for v in r["per_class_iou"].values()
          if v["gt_px"] > 0))
check("self-score: instance F1 == 1.0", abs(r["instances"]["f1"] - 1.0) < 1e-9)
check("self-score: squash is one predicted instance",
      r["squash_fragmentation"]["n_pred_parts"] == 1)
check("self-score: no grass absorbed",
      r["grass_absorbed_into_crop"]["absorbed_px"] == 0)
check("self-score: contact errors are all zero",
      all(x["error_px"] == 0 for x in r["contacts"]["points"]))

# 2. unlabelled GT pixels are excluded, not scored as errors
mat = gt.material.copy()
unl = gt.material == 0
check("there are unlabelled pixels to test with", unl.sum() > 0)
mat[unl] = CID["soil"]           # garbage where GT is unlabelled
p = load_prediction(material=mat, name="unlabelled-poisoned", gt=gt)
r2 = score(p, gt)
check("unlabelled pixels do not change any IoU",
      all(abs(r2["per_class_iou"][c]["iou"] - r["per_class_iou"][c]["iou"]) < 1e-12
          for c in r["per_class_iou"] if r["per_class_iou"][c]["iou"] is not None))

# 3. grass pixels are excluded from instance matching
inst = gt.instances.copy()
inst[gt.instances == GRASS_UNRESOLVED] = 1      # dump all grass into the squash
p = load_prediction(instances=inst, name="grass-into-squash", gt=gt)
r3 = score(p, gt)
check("absorbing grass leaves instance F1 at 1.0", abs(r3["instances"]["f1"] - 1.0) < 1e-9)
check("absorbing grass is reported: 100% of GT grass",
      abs(r3["grass_absorbed_into_crop"]["absorbed_fraction"] - 1.0) < 1e-9)

# 4. splitting an instance below the threshold breaks the match
inst = gt.instances.copy()
ys, xs = np.nonzero(inst == 1)
order = np.argsort(ys)
third = len(order) // 3
inst[ys[order[:third]], xs[order[:third]]] = 200
inst[ys[order[third:2 * third]], xs[order[third:2 * third]]] = 201
p = load_prediction(instances=inst, name="squash-in-thirds", gt=gt)
r4 = score(p, gt)
check("splitting the squash in three loses its match (no part reaches IoU 0.5)",
      1 in r4["instances"]["unmatched_gt"])
check("splitting the squash in three is reported as 3 parts",
      r4["squash_fragmentation"]["n_pred_parts"] == 3)

# 5. resampling is nearest-neighbour and round-trips label values
small = np.array(Image.fromarray(gt.material).resize((384, 512), Image.NEAREST))
back, src = to_gt_grid(small, gt.shape)
check("resample reports the source shape", src == (512, 384))
check("resample invents no new label values",
      set(np.unique(back).tolist()) <= set(np.unique(gt.material).tolist()))

# 6. the threshold really is swappable
r5 = score(load_prediction(instances=gt.instances.copy(), gt=gt), gt, iou_threshold=0.9)
check("iou_threshold is honoured", r5["instances"]["iou_threshold"] == 0.9)

print("\nALL PASS" if ok else "\nFAILURES ABOVE")
sys.exit(0 if ok else 1)
