"""A0 step 6 — assign.npy = heuristic proposal, overridden by my visual calls.

`corrections.json` is the ground-truth record. Each pass names a class and
either explicit region ids, or strokes: polylines I drew by eye over the
photograph (coordinates read off the labelled grid in `zoom.py --grid`). A
stroke assigns every region it passes through — it is a way of pointing at
regions, not a classifier. Later passes win, so a region can be revisited.

    .venv/bin/python ../chunks/A0/apply_assign.py
"""
import json
import os

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "work")
CLASSES = ["unlabelled", "squash_leaf", "squash_petiole", "grass",
           "broadleaf_weed", "straw", "soil", "fruit", "other"]
CID = {c: i for i, c in enumerate(CLASSES)}


def stroke_ids(lab, pts):
    pts = np.asarray(pts, float)
    ids = []
    if len(pts) == 1:
        return [int(lab[int(pts[0][1]), int(pts[0][0])])]
    for a, b in zip(pts[:-1], pts[1:]):
        k = max(2, int(np.hypot(*(b - a)) * 3))
        for t in np.linspace(0, 1, k):
            p = a + (b - a) * t
            x, y = int(round(p[0])), int(round(p[1]))
            if 0 <= y < lab.shape[0] and 0 <= x < lab.shape[1]:
                v = int(lab[y, x])
                if v and v not in ids:
                    ids.append(v)
    return ids


def build(verbose=False):
    prop = np.load(os.path.join(OUT, "proposal.npy")).copy()
    lab = np.load(os.path.join(OUT, "regions.npy"))
    corr = json.load(open(os.path.join(HERE, "corrections.json")))
    touched = np.zeros(len(prop), bool)
    for pass_name in sorted(k for k in corr if not k.startswith("_")):
        for cls, spec in corr[pass_name].items():
            if cls.startswith("_"):
                continue
            if cls not in CID:
                raise KeyError(f"{pass_name}: unknown class {cls}")
            ids = list(spec.get("ids", []))
            for s in spec.get("strokes", []):
                ids += stroke_ids(lab, s)
            for i in sorted(set(ids)):
                if not (1 <= i <= len(prop)):
                    raise IndexError(f"{pass_name}/{cls}: region {i} out of range")
                prop[i - 1] = CID[cls]
                touched[i - 1] = True
            if verbose:
                print(f"  {pass_name}/{cls}: {sorted(set(ids))}")
    np.save(os.path.join(OUT, "assign.npy"), prop)
    return prop, touched


if __name__ == "__main__":
    import sys
    prop, touched = build(verbose="-v" in sys.argv)
    lab = np.load(os.path.join(OUT, "regions.npy"))
    area = np.bincount(lab.ravel(), minlength=len(prop) + 1)[1:]
    print(f"regions={len(prop)}  hand-set={touched.sum()} "
          f"({100*area[touched].sum()/area.sum():.1f}% of pixels)")
    for c in CLASSES:
        k = prop == CID[c]
        print(f"  {c:16s} regions={k.sum():4d}  px%={100*area[k].sum()/area.sum():5.2f}")
