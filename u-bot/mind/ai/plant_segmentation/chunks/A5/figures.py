"""A5 — figures, all with the datum caveat in the title.

    ../A3/.venv/bin/python figures.py

figs/fig_contacts_split.png    every component's point, coloured by status
figs/fig_contacts_merge.png    the same under the `merge` policy
figs/fig_crown_zoom.png        the squash crown, against A0's noted node (352, 516)
figs/fig_gt_instances.png      A5 vs A0's ten estimated points, and the baselines
figs/fig_below_datum.png       where the material sits BELOW the fitted datum
figs/fig_sweeps.png            the (b) placeholder's sweep and the distance CDF
"""
from __future__ import annotations

import json
import os
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from PIL import Image  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from a5_common import ROOT, load_a4, load_rgb, load_scene  # noqa: E402

FIGS = os.path.join(HERE, "figs")
PRODUCTS = os.path.join(HERE, "products")
RESULTS = os.path.join(HERE, "results")
COL = {"observed": "#22c55e", "extrapolated": "#f59e0b", "occluded": "#ef4444"}
DATUM = ("DATUM = THE STRAW MULCH SURFACE, NOT SOIL. "
         "scale_free: 3-D distances in rdu, image distances in px.")
GT_W, GT_H = 768, 1024


def rgb_gt():
    im = Image.open(os.path.join(ROOT, "plants.jpeg")).convert("RGB")
    return np.asarray(im.resize((GT_W, GT_H), Image.LANCZOS))


def load(policy):
    return json.load(open(os.path.join(PRODUCTS, f"contacts_{policy}.json")))["components"]


def scatter(ax, cs, key="point", size=14):
    for st in ("observed", "extrapolated", "occluded"):
        pts = [c[key] for c in cs if c["status"] == st and c.get(key)]
        if not pts:
            continue
        xy = np.array([p["gt_grid_xy"] for p in pts])
        ax.scatter(xy[:, 0], xy[:, 1], s=size, c=COL[st], edgecolors="k",
                   linewidths=0.3, label=f"{st} ({len(pts)})", zorder=3)


def fig_contacts(policy):
    cs = load(policy)
    img = rgb_gt()
    fig, axs = plt.subplots(1, 2, figsize=(15, 10.5))
    for ax in axs:
        ax.imshow(img)
        ax.set_xlim(0, GT_W)
        ax.set_ylim(GT_H, 0)
        ax.axis("off")
    scatter(axs[0], cs, "point")
    axs[0].set_title(f"contact point — status ({policy}, {len(cs)} components)\n"
                     "occluded components have NO point, by construction (R4)")
    axs[0].legend(loc="lower right", fontsize=8)

    # lowest visible point, always present
    lv = [c["lowest_visible_point"] for c in cs if c["lowest_visible_point"]]
    xy = np.array([p["gt_grid_xy"] for p in lv])
    hh = np.array([p["height_above_datum_sigma"] for p in lv])
    s = axs[1].scatter(xy[:, 0], xy[:, 1], s=14, c=np.clip(hh, -10, 10),
                       cmap="coolwarm", vmin=-10, vmax=10, edgecolors="k",
                       linewidths=0.3, zorder=3)
    plt.colorbar(s, ax=axs[1], fraction=0.03, label="height above datum (datum-σ)")
    axs[1].set_title(f"lowest_visible_point — always emitted ({len(lv)} of {len(cs)})\n"
                     "blue = the material sits BELOW A2's fitted datum")
    fig.suptitle(f"A5 contact points, policy `{policy}` — {DATUM}", fontsize=10)
    fig.tight_layout()
    fig.savefig(os.path.join(FIGS, f"fig_contacts_{policy}.png"), dpi=110)
    plt.close(fig)


def fig_crown():
    """A0: 'the petioles converge on a crown node near (352, 516)'. The brief
    asks whether anything A5 produces lands there."""
    img = rgb_gt()
    gt = json.load(open(os.path.join(ROOT, "groundtruth", "plants_contacts.json")))
    sq = next(e for e in gt["instances"] if e["id"] == 1)
    cx, cy = 352, 516
    fig, axs = plt.subplots(1, 2, figsize=(14, 7))
    for ax, policy in zip(axs, ("split", "merge")):
        cs = load(policy)
        ax.imshow(img)
        for c in cs:
            for key, mark in (("lowest_visible_point", "o"),
                              ("lowest_visible_stem_point", "^")):
                p = c.get(key)
                if not p:
                    continue
                x, y = p["gt_grid_xy"]
                if abs(x - cx) > 130 or abs(y - cy) > 130:
                    continue
                ax.scatter([x], [y], s=70 if mark == "^" else 30,
                           marker=mark, c=COL[c["status"]], edgecolors="k",
                           linewidths=0.5, zorder=3)
        ax.scatter([cx], [cy], marker="*", s=380, c="white", edgecolors="k",
                   zorder=4, label="A0's noted crown node (352, 516)")
        ax.scatter([sq["point"][0]], [sq["point"][1]], marker="X", s=200,
                   c="magenta", edgecolors="k", zorder=4,
                   label=f"A0 GT contact {sq['point']} (under_straw, ESTIMATED)")
        ax.set_xlim(cx - 130, cx + 130)
        ax.set_ylim(cy + 130, cy - 130)
        ax.set_title(f"`{policy}`   circles = lowest_visible_point, "
                     "triangles = lowest_visible_stem_point")
        ax.legend(loc="lower left", fontsize=7)
        ax.axis("off")
    fig.suptitle("The squash crown. Green = observed, amber = extrapolated, "
                 f"red = occluded.\n{DATUM}", fontsize=10)
    fig.tight_layout()
    fig.savefig(os.path.join(FIGS, "fig_crown_zoom.png"), dpi=120)
    plt.close(fig)


def fig_gt_instances():
    d = json.load(open(os.path.join(RESULTS, "diagnostics.json")))
    img = rgb_gt()
    fig, axs = plt.subplots(1, 3, figsize=(18, 8.5))
    for ax, key in zip(axs, ("gt_instances", "split", "merge")):
        ax.imshow(img)
        ax.axis("off")
        rows = d["gt_consistency"][key]["rows"]
        for r in rows:
            if not r.get("assigned"):
                continue
            gx, gy = r["gt_point"]
            ax.scatter([gx], [gy], marker="X", s=90, c="magenta",
                       edgecolors="k", linewidths=0.5, zorder=4)
            cs = load(key)
            c = next(x for x in cs if x["component"] == r["assigned"])
            p = c["point"] or c["lowest_visible_point"]
            if not p:
                continue
            x, y = p["gt_grid_xy"]
            ax.plot([gx, x], [gy, y], "-", c="white", lw=1.0, zorder=3)
            ax.scatter([x], [y], s=60, c=COL[c["status"]], edgecolors="k",
                       linewidths=0.5, zorder=5,
                       marker="o" if c["point"] else "s")
        s = d["gt_consistency"][key]["summary"]
        ax.set_title(f"{key}\ncontact median "
                     f"{s['err_contact_px'].get('median_px', float('nan')):.0f} px "
                     f"(n={s['err_contact_px']['n']}), "
                     f"lowest-visible median "
                     f"{s['err_lowest_visible_px'].get('median_px', float('nan')):.0f} px")
    fig.suptitle("CONSISTENCY, NOT ACCURACY — magenta X = A0's contact point, "
                 "which is `under_straw` and `estimated` for all ten instances "
                 "(A0: zero `visible` points in this image).\n"
                 "Circle = A5 contact point, square = lowest_visible_point "
                 f"where the contact is `occluded`.  {DATUM}", fontsize=9)
    fig.tight_layout(rect=(0, 0, 1, 0.90))
    fig.savefig(os.path.join(FIGS, "fig_gt_instances.png"), dpi=110)
    plt.close(fig)


def fig_below_datum():
    scene = load_scene()
    a4 = load_a4(tag="default")
    plant = a4.components_depth > 0
    h = np.where(plant & scene.valid, scene.height / scene.sigma_datum, np.nan)
    fig, axs = plt.subplots(1, 2, figsize=(13, 8))
    axs[0].imshow(load_rgb())
    im = axs[0].imshow(np.where(h < -3, h, np.nan), cmap="winter", vmin=-15, vmax=-3)
    plt.colorbar(im, ax=axs[0], fraction=0.03, label="height (datum-σ)")
    axs[0].set_title("plant material more than 3σ BELOW the datum\n"
                     "nothing lies under the ground: the surface\n"
                     "is disagreeing with the material", fontsize=10)
    axs[0].axis("off")
    v = h[np.isfinite(h)]
    axs[1].hist(np.clip(v, -20, 60), bins=160, color="#334155")
    axs[1].axvline(0, c="k", lw=1)
    axs[1].axvspan(-3, 3, color="#22c55e", alpha=0.25, label="the 3σ ground band")
    axs[1].set_xlabel("height above the straw datum (datum-σ)")
    axs[1].set_ylabel("plant pixels")
    axs[1].set_yscale("log")
    axs[1].legend()
    axs[1].set_title(f"{100*np.mean(v < -3):.1f} % of plant pixels sit below the band")
    fig.suptitle(f"Where the datum and the material disagree.  {DATUM}", fontsize=10)
    fig.tight_layout(rect=(0, 0, 1, 0.94))
    fig.savefig(os.path.join(FIGS, "fig_below_datum.png"), dpi=110)
    plt.close(fig)


def fig_sweeps():
    sw = json.load(open(os.path.join(RESULTS, "sweeps.json")))
    fig, axs = plt.subplots(1, 3, figsize=(17, 5))
    ks = [float(k) for k in sw["max_extrapolation_sigma"]]
    for st, c in COL.items():
        axs[0].plot(ks, [sw["max_extrapolation_sigma"][str(k)]["split"][st] for k in ks],
                    "o-", c=c, label=st)
    axs[0].set_xscale("symlog", linthresh=1)
    axs[0].axvline(20, ls="--", c="k")
    axs[0].set_xlabel("MAX_EXTRAPOLATION (datum-σ)  —  the (b) placeholder")
    axs[0].set_ylabel("components (split policy)")
    axs[0].set_title("the one (b) constant, swept\n"
                     "`observed` is flat: the placeholder cannot manufacture one")
    axs[0].legend()

    cdf = sw["extrapolation_distance_cdf_split"]["sigma"]
    axs[1].plot(np.sort(cdf), np.arange(1, len(cdf) + 1), lw=2)
    axs[1].axvline(20, ls="--", c="k", label="A5's placeholder (20σ)")
    axs[1].set_xlabel("extrapolation distance to the datum (datum-σ)")
    axs[1].set_ylabel("components admitted at that budget")
    axs[1].set_title("what C3 should read its budget off\n"
                     f"n = {len(cdf)} components whose axis reaches the datum")
    axs[1].legend()

    for i, knob in enumerate(("ground_band_k", "basal_band_k")):
        ks2 = [float(k) for k in sw[knob]]
        axs[2].plot(ks2, [sw[knob][str(k)]["split"]["observed"] for k in ks2],
                    "o-", label=f"{knob} → observed")
    axs[2].set_xlabel("multiplier")
    axs[2].set_ylabel("observed components")
    axs[2].set_title("the two inherited conventions")
    axs[2].legend(fontsize=8)
    fig.suptitle(f"A5 sensitivity.  {DATUM}", fontsize=10)
    fig.tight_layout()
    fig.savefig(os.path.join(FIGS, "fig_sweeps.png"), dpi=110)
    plt.close(fig)


def main():
    os.makedirs(FIGS, exist_ok=True)
    fig_contacts("split")
    fig_contacts("merge")
    fig_crown()
    fig_gt_instances()
    fig_below_datum()
    fig_sweeps()
    print("wrote", os.listdir(FIGS))


if __name__ == "__main__":
    main()
