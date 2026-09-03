"""By-eye spot check of the A3 material map on plants2.

NOT ground truth. Boxes were placed by the author on a gridded 768x1024 view
(figs/grid_reference.png) inside regions whose material is unambiguous to a
human, deliberately away from boundaries. Same idea as A2's material_check.py.
Reports the predicted-class histogram inside each box and whether the majority
class matches the author's label.
"""
import json
import numpy as np
from PIL import Image
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from probe_common import FIGS, IMAGE, P, RESULTS, on_path
on_path("A0")
import eval as a0eval  # noqa: E402

# name: (x0, y0, x1, y1, expected_class)  on the 768x1024 grid
BOXES = {
    "fruit_top":        (398, 330, 435, 365, "fruit"),
    "fruit_right":      (595, 470, 635, 560, "fruit"),
    "fruit_bottomleft": (105, 880, 160, 935, "fruit"),
    "leaf_top_centre":  (380, 225, 450, 285, "squash_leaf"),
    "leaf_bottom":      (370, 770, 450, 830, "squash_leaf"),
    "leaf_right":       (640, 455, 705, 520, "squash_leaf"),
    "leaf_left_pale":   (150, 495, 235, 550, "squash_leaf"),
    "lawn_topright":    (620, 60, 740, 140, "grass"),
    "grass_bottomright":(630, 910, 740, 990, "grass"),
    "fence_post":       (352, 70, 385, 160, "other"),
    "lattice_lowerleft":(5, 520, 50, 660, "other"),
    "lattice_upper":    (20, 60, 120, 140, "other"),
    "groundivy_bl":     (50, 705, 170, 765, "broadleaf_weed"),
    "deadleaf_on_fruit":(515, 500, 560, 570, "straw"),
    "vine_stem":        (405, 120, 428, 200, "squash_petiole"),
}
W, H = 768, 1024
mat = np.load(P["A3"] / "material.npy")
conf = np.load(P["A3"] / "confidence.npy")
rgb = np.asarray(Image.open(IMAGE).convert("RGB").resize((W, H), Image.LANCZOS))
COL = {1: (0.10, 0.75, 0.20), 2: (0.95, 0.85, 0.10), 3: (1.00, 0.55, 0.00),
       4: (0.90, 0.15, 0.15), 5: (0.55, 0.40, 0.20), 6: (0.30, 0.30, 0.30),
       7: (0.95, 0.40, 0.85), 8: (0.20, 0.55, 1.00)}
over = rgb / 255.0 * 0.35
for cid, c in COL.items():
    m = mat == cid
    over[m] = over[m] * 0.4 + np.array(c) * 0.6

rows = []
n = len(BOXES)
fig, ax = plt.subplots(2, n, figsize=(1.6 * n, 4.2), dpi=110)
for i, (name, (x0, y0, x1, y1, exp)) in enumerate(BOXES.items()):
    sub = mat[y0:y1, x0:x1]
    hist = {a0eval.CLASSES[c]: round(float((sub == c).mean()), 3) for c in np.unique(sub)}
    maj = a0eval.CLASSES[int(np.bincount(sub.ravel()).argmax())]
    rows.append({"box": name, "xyxy": [x0, y0, x1, y1], "expected": exp, "majority": maj,
                 "hit": maj == exp, "expected_fraction": hist.get(exp, 0.0),
                 "median_conf": float(np.median(conf[y0:y1, x0:x1])), "hist": hist})
    pad = 12
    Y0, Y1, X0, X1 = max(0, y0 - pad), min(H, y1 + pad), max(0, x0 - pad), min(W, x1 + pad)
    for r_, img in ((0, rgb), (1, (over * 255).astype(np.uint8))):
        ax[r_, i].imshow(img[Y0:Y1, X0:X1])
        ax[r_, i].add_patch(plt.Rectangle((x0 - X0, y0 - Y0), x1 - x0, y1 - y0, fill=False, color="w", lw=1))
        ax[r_, i].set_xticks([]); ax[r_, i].set_yticks([])
    ax[0, i].set_title(f"{name}\nexp {exp}", fontsize=6.5)
    ax[1, i].set_title(f"{maj} {hist.get(exp,0)*100:.0f}%", fontsize=6.5, color="green" if maj == exp else "red")
fig.suptitle("plants2 - by-eye spot boxes (top: photo, bottom: A3 prediction). Author's labels, not ground truth.", fontsize=9)
fig.tight_layout(); fig.savefig(FIGS / "a3_spot_check.png")
hits = sum(r["hit"] for r in rows)
summary = {"n_boxes": n, "majority_hits": hits, "hit_rate": hits / n,
           "mean_expected_fraction": float(np.mean([r["expected_fraction"] for r in rows])),
           "by_expected_class": {}}
for exp in sorted({r["expected"] for r in rows}):
    rs = [r for r in rows if r["expected"] == exp]
    summary["by_expected_class"][exp] = {"n": len(rs), "hits": sum(r["hit"] for r in rs),
                                        "mean_expected_fraction": float(np.mean([r["expected_fraction"] for r in rs]))}
json.dump({"summary": summary, "boxes": rows,
           "caveat": "author-placed boxes on a gridded view; not ground truth; boundaries avoided"},
          open(RESULTS / "a3_spot_check.json", "w"), indent=1)
print(json.dumps(summary, indent=1))
for r in rows:
    print(f"{r['box']:20} exp {r['expected']:15} got {r['majority']:15} {'HIT ' if r['hit'] else 'miss'} exp-frac {r['expected_fraction']:.2f} conf {r['median_conf']:.2f}")
