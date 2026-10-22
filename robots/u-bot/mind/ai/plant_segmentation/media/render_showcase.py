"""Public showcase image: what the Phase A stack sees and would do.

Every layer is a real pipeline product — nothing is drawn by hand:
  - weed detection  : chunks/A3/preds/a3_default.png (grass=3, broadleaf_weed=4)
  - crop keep-out   : chunks/A6/products/silhouette_default_clearance.npy
  - strike point    : chunks/A8/products/target_list_floor000_diagnostic.json
  - gate refusals   : chunks/A8/products/rejection_report.json (instances 5, 120)
  - components      : chunks/A4/products/components_gt_grid_merge.png
"""
import json
import numpy as np
from PIL import Image
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch
from matplotlib.lines import Line2D
from scipy import ndimage

ROOT = "/Users/samw3/prj/Make/stocko/u-bot/models/plant_segmentation"
W, H = 768, 1024          # GT grid
S = 2                     # render scale

rgb = np.array(Image.open(f"{ROOT}/plants.jpeg").resize((W * S, H * S), Image.LANCZOS)) / 255.0
mat = np.array(Image.open(f"{ROOT}/chunks/A3/preds/a3_default.png"))
merge = np.array(Image.open(f"{ROOT}/chunks/A4/products/components_gt_grid_merge.png"))
sil = np.load(f"{ROOT}/chunks/A6/products/silhouette_default_clearance.npy")

up = lambda a: np.array(Image.fromarray(a.astype(np.uint8)).resize((W * S, H * S), Image.NEAREST))
grass = up(mat == 3).astype(bool)
weedbl = up(mat == 4).astype(bool)
keep = up(sil).astype(bool)

tl = json.load(open(f"{ROOT}/chunks/A8/products/target_list_floor000_diagnostic.json"))
tgt = tl["targets"][0]
tx, ty = [c * S for c in tgt["target"]["point_gt_grid_xy"]]
inst104 = up(merge == 104).astype(bool)

rej = json.load(open(f"{ROOT}/chunks/A8/products/rejection_report.json"))
blocked = {}
for x in rej["rejections"]:
    if x["instance_id"] in (5, 120):
        m = up(merge == x["instance_id"]).astype(bool)
        cy, cx = ndimage.center_of_mass(m)
        blocked[x["instance_id"]] = (cx, cy)

img = rgb * 0.92
GRASS_C = np.array([1.00, 0.72, 0.10])
WEED_C = np.array([0.95, 0.20, 0.15])
KEEP_C = np.array([0.20, 0.85, 0.40])
img[grass] = img[grass] * 0.55 + GRASS_C * 0.45
img[weedbl] = img[weedbl] * 0.45 + WEED_C * 0.55
img[keep & ~(grass | weedbl)] = img[keep & ~(grass | weedbl)] * 0.88 + KEEP_C * 0.12

fig, ax = plt.subplots(figsize=(W * S / 200, H * S / 200), dpi=200)
ax.imshow(img)
ax.contour(keep, levels=[0.5], colors=[KEEP_C], linewidths=2.2)
ax.contour(inst104, levels=[0.5], colors=["white"], linewidths=1.8)

# strike point: crosshair
for r_, lw, col in [(34, 2.6, "white"), (34, 1.4, "#d81f14")]:
    ax.add_patch(plt.Circle((tx, ty), r_, fill=False, color=col, lw=lw))
for dx, dy in [(1, 0), (-1, 0), (0, 1), (0, -1)]:
    ax.plot([tx + dx * 14, tx + dx * 46], [ty + dy * 14, ty + dy * 46],
            color="white", lw=2.6, solid_capstyle="round")
    ax.plot([tx + dx * 14, tx + dx * 46], [ty + dy * 14, ty + dy * 46],
            color="#d81f14", lw=1.2, solid_capstyle="round")

def callout(x, y, dx, dy, text, fc):
    ax.annotate(text, xy=(x, y), xytext=(x + dx, y + dy),
                fontsize=11, fontweight="bold", color="white", ha="center",
                bbox=dict(boxstyle="round,pad=0.45", fc=fc, ec="white", lw=1.2, alpha=0.95),
                arrowprops=dict(arrowstyle="-", color="white", lw=1.6))

callout(tx, ty, 330, 60, "weed — strike point\n(lowest visible stem)", "#b3130a")
for iid, (cx, cy) in blocked.items():
    ax.plot(cx, cy, marker="o", ms=15, mfc="none", mec="#ffe45c", mew=3)
labels_xy = {5: (-330, 230), 120: (-100, 260)}
texts = {5: "'remove' refused —\ninside crop keep-out", 120: "'remove' refused —\ninside crop keep-out"}
for iid, (cx, cy) in blocked.items():
    dx, dy = labels_xy[iid]
    callout(cx, cy, dx, dy, texts[iid], "#5c5c14")

# label the protected crop at its crown (visible crown node ~ (352, 516) GT grid)
callout(352 * S, 516 * S, -120, -330, "kabocha squash —\ncrop, protected", "#116b31")

# title + caption strip
ax.text(0.5, 0.988, "u-bot weeding perception — one photo, end to end",
        transform=ax.transAxes, ha="center", va="top", fontsize=17,
        fontweight="bold", color="white",
        bbox=dict(boxstyle="round,pad=0.5", fc="black", alpha=0.65, ec="none"))

legend = [
    Line2D([0], [0], marker="s", ls="none", ms=13, mfc=GRASS_C, mec="none", label="grass detected"),
    Line2D([0], [0], marker="s", ls="none", ms=13, mfc=WEED_C, mec="none", label="broadleaf weed detected"),
    Line2D([0], [0], color=KEEP_C, lw=3, label="crop keep-out (squash, protected)"),
    Line2D([0], [0], marker="o", ls="none", ms=11, mfc="none", mec="#d81f14", mew=2.5, label="removal target (safety gate passed)"),
    Line2D([0], [0], marker="o", ls="none", ms=11, mfc="none", mec="#ffe45c", mew=2.5, label="removal refused by safety gate"),
]
leg = ax.legend(handles=legend, loc="lower left", fontsize=10.5, framealpha=0.82,
                facecolor="black", edgecolor="none", labelcolor="white")

ax.set_xlim(0, W * S); ax.set_ylim(H * S, 0)
ax.axis("off")
fig.tight_layout(pad=0.1)
fig.savefig(f"{ROOT}/media/showcase_weed_detection.png", dpi=200,
            bbox_inches="tight", pad_inches=0.02)
print("saved")
