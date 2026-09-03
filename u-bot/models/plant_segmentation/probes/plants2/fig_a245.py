"""Figures for the probe's A2 (datum), A4 (components) and A5 (contact points)
outputs on plants2. Descriptive only — there is no ground truth to score against."""
import json
import numpy as np
from PIL import Image
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import ListedColormap
from probe_common import FIGS, IMAGE, P, RESULTS, on_path
on_path("A0")
import eval as a0eval  # noqa: E402

H, W = 1344, 1008
rgb = np.asarray(Image.open(IMAGE).convert("RGB").resize((W, H), Image.LANCZOS)) / 255.0
A2 = P["A2"] / "products"
height = np.load(A2 / "height_above_soil.npy")
valid = np.load(A2 / "validity_mask.npy")
cov = np.load(A2 / "coverage_class.npy")
ground = np.load(A2 / "ground_inliers.npy")
m2 = json.load(open(A2 / "A2_MANIFEST.json"))
sig = m2["key_numbers"]["datum_roughness_sigma_rdu"]

# ---------------------------------------------------------------- A2 figure
fig, ax = plt.subplots(1, 3, figsize=(15, 7), dpi=110)
g = rgb.copy(); g[ground] = g[ground] * 0.3 + np.array([0.1, 0.5, 1.0]) * 0.7
ax[0].imshow(g); ax[0].set_title(f"A2 ground inliers (blue) = what the datum was fitted to\n{ground.mean()*100:.1f} % of pixels")
hs = np.where(valid, height / sig, np.nan)
im = ax[1].imshow(hs, vmin=-3, vmax=15, cmap="RdYlGn"); ax[1].set_title(f"height above datum, in datum sigmas (sigma={sig:.2e} rdu)")
plt.colorbar(im, ax=ax[1], fraction=0.03)
cm = ListedColormap([(0.1, 0.6, 0.1), (0.9, 0.7, 0.1), (0.8, 0.1, 0.1)])
ax[2].imshow(cov, cmap=cm, vmin=0, vmax=2)
kn = m2["key_numbers"]
ax[2].set_title(f"coverage: observed {kn['observed_fraction']*100:.0f} % / interpolated {kn['interpolated_fraction']*100:.0f} % / extrapolated {kn['extrapolated_fraction']*100:.1f} %")
for a in ax: a.set_xticks([]); a.set_yticks([])
fig.suptitle("plants2 probe - A2 datum fit. The 'ground' here is whatever the fit found flattest; there is no soil in this photo.", fontsize=11)
fig.tight_layout(); fig.savefig(FIGS / "a2_datum_plants2.png")

# ---------------------------------------------------------------- A4 figure
import sys
if not (RESULTS / "a45.json").exists():
    print("A2 figure only; a45.json not yet present"); sys.exit(0)
res = json.load(open(RESULTS / "a45.json"))
fig, ax = plt.subplots(1, 3, figsize=(15, 7), dpi=110)
ax[0].imshow(rgb); ax[0].set_title("plants2.jpeg on the depth grid")
rng = np.random.default_rng(3)
for i, policy in enumerate(("split", "merge")):
    comp = np.load(P["A4"] / "products" / f"components_depth_grid_{policy}.npy")
    n = int(comp.max())
    lut = np.vstack([[0, 0, 0], rng.uniform(0.25, 1.0, (n, 3))])
    img = rgb * 0.25
    m = comp > 0
    img[m] = lut[comp[m]] * 0.75 + rgb[m] * 0.25
    ax[i + 1].imshow(img)
    top = res["a4"][policy]["largest_components"][0]
    big = comp == top["component"]
    ax[i + 1].contour(big, levels=[0.5], colors=["white"], linewidths=1.2)
    ax[i + 1].set_title(f"A4 {policy}: {n} components; largest (white) = {top['fraction_of_plant_px']*100:.0f} % of plant px\n"
                        f"fruit in {res['a4'][policy]['n_components_holding_fruit_ge200px']} components")
for a in ax: a.set_xticks([]); a.set_yticks([])
fig.suptitle("plants2 probe - A4 connectivity grouping (colours are component ids, random)", fontsize=11)
fig.tight_layout(); fig.savefig(FIGS / "a4_components_plants2.png")

# ---------------------------------------------------------------- A5 figure
fig, ax = plt.subplots(1, 2, figsize=(11, 7.5), dpi=110)
COLS = {"observed": "#2ecc40", "extrapolated": "#ffdc00", "occluded": "#ff4136"}
for i, policy in enumerate(("split", "merge")):
    doc = json.load(open(P["A5"] / "products" / f"contacts_{policy}.json"))
    ax[i].imshow(rgb * 0.8)
    comps = doc["components"]
    for c in comps:
        lv = c.get("lowest_visible_point")
        if lv:
            u, v = lv["depth_grid_xy"]
            ax[i].plot(u, v, ".", color=COLS[c["status"]], ms=4 if c["n_px"] < 2000 else 8, alpha=0.8)
        if c.get("point") and c["status"] != "occluded":
            u, v = c["point"]["depth_grid_xy"]
            ax[i].plot(u, v, "x", color="white", ms=5, mew=1)
    sc = doc["status_counts"]
    ax[i].set_title(f"A5 {policy}: {sc['total']} components - observed {sc['observed']}, extrapolated {sc['extrapolated']}, "
                    f"occluded {sc['occluded']}\narm-admissible {sc['arm_admissible']}, fabricated points {sc['fabricated_points']}", fontsize=9)
    ax[i].set_xticks([]); ax[i].set_yticks([])
from matplotlib.lines import Line2D
ax[0].legend(handles=[Line2D([], [], marker=".", ls="", color=v, label=k) for k, v in COLS.items()] +
                     [Line2D([], [], marker="x", ls="", color="white", label="emitted point (non-occluded)")],
             loc="lower left", fontsize=8, facecolor="#333", labelcolor="white")
fig.suptitle("plants2 probe - A5 lowest visible point per component, coloured by contact status", fontsize=11)
fig.tight_layout(); fig.savefig(FIGS / "a5_contacts_plants2.png")
print("ok")
