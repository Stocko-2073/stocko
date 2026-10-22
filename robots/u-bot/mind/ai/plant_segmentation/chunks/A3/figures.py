"""A3 figures. Everything here is checked by eye before any claim rests on it.

    chunks/A3/.venv/bin/python chunks/A3/figures.py

* `fig_comparison.png`  RGB, ground truth, and the four approaches side by side
* `fig_confusion.png`   row-normalised confusion for the four approaches
* `fig_height.png`      A2 height in datum sigma, and its per-class distribution
                        against the A0 labels — A2's hand-placed-box check, redone
                        against labels
* `fig_grass_zoom.png`  three crops where grass and squash interleave, which is
                        the failure this chunk exists to fix
* `fig_seed_patches.png` where the 42 fitted patches are, so the training set is
                        inspectable rather than a number in a JSON
"""
from __future__ import annotations

import json
import os
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.patches as mpatches  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from PIL import Image  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import a3_common as A  # noqa: E402
import eval as a0eval  # noqa: E402

FIGS = os.path.join(HERE, "figs")
PREDS = os.path.join(HERE, "preds")

PALETTE = np.array([
    (0, 0, 0),          # 0 unlabelled
    (34, 120, 34),      # 1 squash_leaf
    (150, 230, 120),    # 2 squash_petiole
    (255, 205, 40),     # 3 grass
    (215, 40, 70),      # 4 broadleaf_weed
    (205, 178, 130),    # 5 straw
    (110, 70, 35),      # 6 soil
    (60, 140, 235),     # 7 fruit
    (200, 60, 200),     # 8 other
], np.uint8)

PANELS = [
    ("approach1_shape_tree_cv", "1. shape prior (tree, blocked CV)"),
    ("approach2_shape_height_tree_cv", "2. shape + A2 height"),
    ("approach3_dino_logreg", "3. DINOv2 probe, 42 patches"),
    ("approach4_openvocab_siglip2-so400m-patch14-384",
     "4. SigLIP 2 (so400m) open-vocab"),
]


def colour(lab):
    return PALETTE[np.clip(lab, 0, len(PALETTE) - 1)]


def load_pred(name):
    p = os.path.join(PREDS, f"{name}.png")
    return np.array(Image.open(p)) if os.path.exists(p) else None


def legend_handles(ids):
    return [mpatches.Patch(color=PALETTE[i] / 255.0, label=a0eval.CLASSES[i])
            for i in ids]


def fig_comparison(rgb, gt):
    panels = [(rgb, "RGB (768x1024 label grid)"),
              (colour(gt.material), "A0 ground truth")]
    for name, title in PANELS:
        m = load_pred(name)
        if m is not None:
            panels.append((colour(m), title))
    n = len(panels)
    fig, ax = plt.subplots(1, n, figsize=(3.1 * n, 4.6))
    for a, (im, t) in zip(np.atleast_1d(ax), panels):
        a.imshow(im)
        a.set_title(t, fontsize=8)
        a.set_xticks([]); a.set_yticks([])
    fig.legend(handles=legend_handles([1, 2, 3, 4, 5, 7, 8, 0]),
               loc="lower center", ncol=8, fontsize=8, frameon=False)
    fig.suptitle("A3 — material segmentation, all four approaches, on A0's "
                 "768x1024 label grid.\nApproaches 1-3 shown for one "
                 "fold-deal / patch-draw; approach 4 is zero-shot.",
                 fontsize=9)
    fig.tight_layout(rect=(0, 0.05, 1, 0.96))
    fig.savefig(os.path.join(FIGS, "fig_comparison.png"), dpi=140)
    plt.close(fig)


def fig_confusion(gt):
    keep = [1, 2, 3, 4, 5, 7, 8]
    names = [a0eval.CLASSES[i] for i in keep]
    have = [(n, t) for n, t in PANELS if load_pred(n) is not None]
    fig, axs = plt.subplots(1, len(have), figsize=(4.0 * len(have), 4.3))
    for a, (name, title) in zip(np.atleast_1d(axs), have):
        r = A.score_map(load_pred(name), gt, name)
        m = np.array(r["confusion"])[np.ix_(keep, keep)].astype(float)
        m = m / np.maximum(m.sum(1, keepdims=True), 1)
        a.imshow(m, cmap="magma", vmin=0, vmax=1)
        a.set_xticks(range(len(keep))); a.set_xticklabels(names, rotation=90, fontsize=7)
        a.set_yticks(range(len(keep))); a.set_yticklabels(names, fontsize=7)
        for i in range(len(keep)):
            for j in range(len(keep)):
                if m[i, j] > 0.005:
                    a.text(j, i, f"{100*m[i,j]:.0f}", ha="center", va="center",
                           fontsize=6, color="white" if m[i, j] < 0.6 else "black")
        a.set_title(f"{title}\nthis map's mean IoU {r['mean_iou']:.4f}", fontsize=8)
        a.set_ylabel("ground truth", fontsize=8)
        a.set_xlabel("predicted (% of GT row)", fontsize=8)
    fig.suptitle("A3 — row-normalised confusion (% of each GT row). The grass "
                 "row is the one that matters: how much of it lands in "
                 "squash_leaf / squash_petiole.\nApproaches 1-3 are shown for "
                 "ONE fold-deal / patch-draw, so these mean IoUs differ "
                 "slightly from the multi-seed means in the comparison table.",
                 fontsize=9)
    fig.tight_layout(rect=(0, 0, 1, 0.94))
    fig.savefig(os.path.join(FIGS, "fig_confusion.png"), dpi=140)
    plt.close(fig)


def fig_height(rgb, gt):
    a2 = A.a2_on_gt_grid()
    h = np.where(a2["valid"], a2["h_sigma"], np.nan)
    hr = json.load(open(os.path.join(HERE, "results", "height_report.json")))
    fig = plt.figure(figsize=(13, 5.2))
    ax1 = fig.add_subplot(1, 3, 1)
    ax1.imshow(rgb); ax1.set_xticks([]); ax1.set_yticks([])
    ax1.set_title("RGB", fontsize=9)
    ax2 = fig.add_subplot(1, 3, 2)
    im = ax2.imshow(h, cmap="viridis", vmin=-5, vmax=120)
    ax2.set_xticks([]); ax2.set_yticks([])
    ax2.set_title("A2 height above the STRAW datum, in datum sigma", fontsize=9)
    plt.colorbar(im, ax=ax2, fraction=0.046, label="datum sigma")

    ax3 = fig.add_subplot(1, 3, 3)
    cls = ["straw", "broadleaf_weed", "fruit", "grass", "squash_petiole",
           "squash_leaf"]
    data = [np.where(a2["valid"] & (gt.material == a0eval.CID[c]),
                     a2["h_sigma"], np.nan) for c in cls]
    data = [d[np.isfinite(d)] for d in data]
    ax3.boxplot(data, tick_labels=cls, showfliers=False)
    for i, c in enumerate(cls, start=1):
        box = hr["a2_hand_placed_boxes"].get(
            c if c != "broadleaf_weed" else "broadleaf_weed(clover)")
        if box is not None:
            ax3.plot([i], [box], "r*", ms=11)
    ax3.set_ylabel("height, datum sigma", fontsize=9)
    ax3.set_ylim(-10, 160)
    ax3.tick_params(axis="x", rotation=45, labelsize=8)
    ax3.set_title("per A0 class (box) vs A2's hand-placed boxes (red star)\n"
                  "grass and squash_leaf overlap: separability only 0.74",
                  fontsize=9)
    ax3.grid(alpha=0.3)
    fig.suptitle("A3 — what height_above_soil knows, scored against A0 labels. "
                 "Datum is the STRAW, not soil.", fontsize=10)
    fig.tight_layout(rect=(0, 0, 1, 0.93))
    fig.savefig(os.path.join(FIGS, "fig_height.png"), dpi=140)
    plt.close(fig)


ZOOMS = [((300, 470), (250, 420), "grass through the squash canopy"),
         ((690, 860), (90, 260), "grass tussock on straw"),
         ((430, 600), (430, 600), "petioles and grass at the crown")]


def fig_grass_zoom(rgb, gt):
    have = [(n, t) for n, t in PANELS if load_pred(n) is not None]
    cols = 2 + len(have)
    fig, axs = plt.subplots(len(ZOOMS), cols, figsize=(2.5 * cols, 2.7 * len(ZOOMS)))
    for r, ((y0, y1), (x0, x1), lab) in enumerate(ZOOMS):
        ims = [(rgb[y0:y1, x0:x1], f"RGB — {lab}"),
               (colour(gt.material[y0:y1, x0:x1]), "ground truth")]
        for name, title in have:
            ims.append((colour(load_pred(name)[y0:y1, x0:x1]), title))
        for c, (im, t) in enumerate(ims):
            a = axs[r, c]
            a.imshow(im); a.set_xticks([]); a.set_yticks([])
            if r == 0 or c == 0:
                a.set_title(t, fontsize=7)
    fig.legend(handles=legend_handles([1, 2, 3, 4, 5, 7]), loc="lower center",
               ncol=6, fontsize=8, frameon=False)
    fig.suptitle("A3 — where grass and squash interleave", fontsize=10)
    fig.tight_layout(rect=(0, 0.04, 1, 0.95))
    fig.savefig(os.path.join(FIGS, "fig_grass_zoom.png"), dpi=140)
    plt.close(fig)


def fig_seed_patches(rgb):
    doc = json.load(open(os.path.join(HERE, "seed_patches.json")))
    fig, ax = plt.subplots(figsize=(5.2, 6.6))
    ax.imshow(rgb)
    for p in doc["patches"]:
        x, y = p["label_grid_xy"]
        ax.plot(x, y, "o", ms=7, mfc=PALETTE[p["class_id"]] / 255.0,
                mec="white", mew=1.2)
    ax.set_xticks([]); ax.set_yticks([])
    ax.set_title(f"the {doc['n_patches']} labelled patches the shipped default "
                 f"is fitted on\n(each covers {A.GT_H/doc['patch_grid'][0]:.1f} "
                 f"label px; together 0.07 % of the frame)", fontsize=9)
    fig.legend(handles=legend_handles([1, 2, 3, 4, 5, 7, 8]), loc="lower center",
               ncol=4, fontsize=8, frameon=False)
    fig.tight_layout(rect=(0, 0.08, 1, 1))
    fig.savefig(os.path.join(FIGS, "fig_seed_patches.png"), dpi=140)
    plt.close(fig)


def main():
    os.makedirs(FIGS, exist_ok=True)
    gt = a0eval.load_gt()
    rgb = np.asarray(Image.open(os.path.join(A.WORK, "rgb_gtgrid.png")).convert("RGB"))
    fig_comparison(rgb, gt)
    fig_confusion(gt)
    fig_height(rgb, gt)
    fig_grass_zoom(rgb, gt)
    fig_seed_patches(rgb)
    print("wrote figures to", FIGS)


if __name__ == "__main__":
    main()
