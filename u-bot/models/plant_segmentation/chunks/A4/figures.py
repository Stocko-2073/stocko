"""A4 — figures. Each one exists to be looked at, not to decorate a document.

  fig_components.png   RGB / relief / components under both unresolved policies
  fig_unresolved.png   where connectivity was ambiguous — the roadmap's
                       "visualisation of where connectivity was ambiguous"
  fig_operating.png    squash IoU and grass absorption against the tolerance,
                       over five decades, with A1's registered constants and
                       ZeroPlantSeg's `eps` window marked
  fig_zooms.png        the crown, a grass/leaf crossing, and the clover patch

Run:  ../A3/.venv/bin/python figures.py
"""
from __future__ import annotations

import json
import os
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt      # noqa: E402
import numpy as np                   # noqa: E402
from PIL import Image                # noqa: E402

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import a4_common as C      # noqa: E402
import a4_graph as G       # noqa: E402
import run_a4 as R         # noqa: E402
import unresolved as U     # noqa: E402
import eval as a0eval      # noqa: E402

# categorical palette, validated with the dataviz skill's checker
# (light surface #fcfcfb: lightness band PASS, chroma PASS, CVD dE 28.5 PASS,
#  normal-vision dE 34.4 PASS, contrast PASS)
BLUE, ORANGE, PURPLE = "#3366CC", "#E8710A", "#7A3FBF"
INK, MUTED, GRID = "#1b1b1b", "#5c5c5c", "#dcdcd8"


def rgb_depth_grid():
    return np.asarray(Image.open(os.path.join(C.ROOT, "plants.jpeg"))
                      .convert("RGB").resize((C.DEPTH_W, C.DEPTH_H), Image.LANCZOS))


def colourise(lab, seed=0):
    rng = np.random.default_rng(seed)
    col = 0.25 + 0.7 * rng.random((int(lab.max()) + 1, 3))
    col[0] = 0.06
    return col[lab]


def fig_components(inp, r, rgb):
    fig, ax = plt.subplots(1, 4, figsize=(21, 8))
    ax[0].imshow(rgb)
    ax[0].set_title("plants.jpeg on the A1 depth grid", color=INK)
    im = ax[1].imshow(inp.relief, cmap="viridis",
                      vmin=float(np.percentile(inp.relief, 1)),
                      vmax=float(np.percentile(inp.relief, 99)))
    ax[1].set_title("relief = A2 datum depth − A1 depth  (rdu, scale_free)",
                    color=INK)
    plt.colorbar(im, ax=ax[1], fraction=0.035, pad=0.01)
    for i, pol in enumerate(("split", "merge")):
        lab = r["comp_" + pol][r["frag"]]
        ax[2 + i].imshow(colourise(lab))
        ax[2 + i].set_title(
            f"components, unresolved → {pol}  ({int(lab.max())} components)",
            color=INK)
    for a in ax:
        a.set_xticks([]); a.set_yticks([])
    fig.suptitle("A4 — grouping by observed 3-D connectivity. Datum is the "
                 "STRAW surface; every distance is scale_free (rdu).",
                 color=MUTED, y=0.995)
    fig.tight_layout()
    fig.savefig(os.path.join(C.FIGS, "fig_components.png"), dpi=90,
                facecolor="white")
    plt.close(fig)


def fig_unresolved(inp, r, rgb, edges):
    """Paint the three kinds of unresolved link onto the picture."""
    frag = r["frag"]
    H, W = frag.shape
    amb = np.zeros((H, W), bool)
    occ = np.zeros((H, W), bool)
    frame = np.zeros((H, W), bool)

    # ambiguous boundaries: the boundary pixels themselves
    pairs = r["summary"]["pairs"][r["unres"]]
    want = set(map(tuple, pairs.tolist()))
    for dy, dx in G.DIRECTIONS:
        fq = G._shift(frag, dy, dx, 0)
        m = (frag > 0) & (fq > 0) & (frag != fq)
        lo = np.minimum(frag, fq); hi = np.maximum(frag, fq)
        sel = np.zeros((H, W), bool)
        if want:
            key = lo.astype(np.int64) * (int(frag.max()) + 1) + hi
            wk = np.array(sorted({a * (int(frag.max()) + 1) + b
                                  for a, b in want}), np.int64)
            sel = np.isin(key, wk)
        amb |= m & sel
    occ_frags = {e["a"] for e in edges if e["kind"] == "occluded_by"
                 and not e["already_connected"]}
    occ_frags |= {e["b"] for e in edges if e["kind"] == "occluded_by"
                  and not e["already_connected"]}
    occ = np.isin(frag, list(occ_frags)) & ~amb
    frame_frags = {e["a"] for e in edges if e["kind"] == "leaves_frame"}
    frame = np.isin(frag, list(frame_frags))

    over = rgb.astype(np.float32) / 255.0
    over = 0.35 * over + 0.65
    out = over.copy()
    for mask, hexc, alpha in ((occ, PURPLE, 0.30), (frame, ORANGE, 0.30),
                              (amb, BLUE, 1.0)):
        c = np.array([int(hexc[i:i + 2], 16) / 255 for i in (1, 3, 5)])
        out[mask] = (1 - alpha) * out[mask] + alpha * c

    fig, ax = plt.subplots(1, 2, figsize=(13, 9))
    ax[0].imshow(rgb); ax[0].set_title("plants.jpeg", color=INK)
    ax[1].imshow(np.clip(out, 0, 1))
    ax[1].set_title("where connectivity was unresolved", color=INK)
    import matplotlib.patches as mp
    ax[1].legend(handles=[
        mp.Patch(color=BLUE, label=f"ambiguous boundary ({int(r['unres'].sum())} "
                                   f"edges) — part continuous, part step"),
        mp.Patch(color=PURPLE, alpha=0.5,
                 label=f"fragment on an occlusion-mediated link "
                       f"({len(occ_frags)} fragments)"),
        mp.Patch(color=ORANGE, alpha=0.5,
                 label=f"leaves the frame ({len(frame_frags)} fragments)")],
        loc="lower center", bbox_to_anchor=(0.5, -0.16), frameon=False,
        labelcolor=MUTED)
    for a in ax:
        a.set_xticks([]); a.set_yticks([])
    fig.tight_layout()
    fig.savefig(os.path.join(C.FIGS, "fig_unresolved.png"), dpi=95,
                facecolor="white", bbox_inches="tight")
    plt.close(fig)


def fig_operating(sw):
    fig, ax = plt.subplots(figsize=(10, 6))
    rows = sw["tolerance_sweep_split"]
    t = np.array([r["tol_rdu"] for r in rows])
    ax.plot(t, [r["squash_best_iou"] for r in rows], color=BLUE, lw=2,
            marker="o", ms=4, label="squash IoU (best single component)")
    ax.plot(t, [r["grass_absorbed"] for r in rows], color=ORANGE, lw=2,
            marker="s", ms=4, label="grass absorbed into the crop component")
    ax.axhline(0.5, color="#b9b9b3", lw=1.4, ls="--")
    ax.axhline(0.530, color="#b9b9b3", lw=1.4, ls=":")
    ax.text(0.98, 0.462, "instance match threshold 0.50", color=MUTED,
            fontsize=8, ha="right", transform=ax.get_yaxis_transform())
    ax.text(0.98, 0.555, "baseline grass absorption 53.0 %", color=MUTED,
            fontsize=8, ha="right", transform=ax.get_yaxis_transform())
    ax.axvline(sw["shipped_tolerance_rdu"], color=PURPLE, lw=2)
    ax.text(sw["shipped_tolerance_rdu"] * 1.15, 0.72,
            "shipped tolerance\n(within-fragment p90)", color=PURPLE, fontsize=8)
    for w, v in sw["a1_local_planarity_p10_rdu"].items():
        ax.axvline(float(v), color="#a8a8a2", lw=1, ls="-.")
    ax.text(2.2e-5, 0.86, "A1 local-planarity p10, win 3…33\n(the roadmap's "
                          "literal reading —\nthe scene shatters here)",
            color=MUTED, fontsize=8, va="top")
    ax.set_xscale("log")
    ax.set_xlabel("depth-continuity tolerance (rdu, scale_free)", color=INK)
    ax.set_ylabel("fraction", color=INK)
    ax.set_ylim(-0.02, 1.02)
    ax.set_title("A4 operating curve — five decades of tolerance, one graph",
                 color=INK)
    ax.grid(True, color=GRID, lw=0.6)
    for s in ax.spines.values():
        s.set_color(GRID)
    ax.tick_params(colors=MUTED)
    ax.legend(frameon=False, loc="upper left", bbox_to_anchor=(0.02, 0.44),
              labelcolor=MUTED)
    fig.tight_layout()
    fig.savefig(os.path.join(C.FIGS, "fig_operating.png"), dpi=110,
                facecolor="white")
    plt.close(fig)


def fig_zooms(inp, r, rgb, gt):
    gm = C._nearest_to_depth_grid(gt.material)
    gi = C._nearest_to_depth_grid(gt.instances)
    spots = []
    ys, xs = np.nonzero(gm == 2)
    spots.append(("crown / petioles", int(np.median(ys)), int(np.median(xs))))
    ys, xs = np.nonzero(gi == 3)
    spots.append(("clover patch (GT instance 3)", int(np.median(ys)), int(np.median(xs))))
    ys, xs = np.nonzero((gm == 3) & (C._nearest_to_depth_grid(gt.material) == 3))
    spots.append(("grass", int(np.median(ys)), int(np.median(xs))))
    lab = r["comp_split"][r["frag"]]
    col = colourise(lab)
    fig, ax = plt.subplots(len(spots), 3, figsize=(14, 4.6 * len(spots)))
    for i, (name, cy, cx) in enumerate(spots):
        sl = (slice(max(0, cy - 190), cy + 190), slice(max(0, cx - 190), cx + 190))
        ax[i, 0].imshow(rgb[sl]); ax[i, 0].set_title(f"{name} — RGB", color=INK)
        ax[i, 1].imshow(inp.relief[sl], cmap="viridis")
        ax[i, 1].set_title("relief (rdu)", color=INK)
        ax[i, 2].imshow(col[sl]); ax[i, 2].set_title("A4 components (split)",
                                                     color=INK)
        for a in ax[i]:
            a.set_xticks([]); a.set_yticks([])
    fig.tight_layout()
    fig.savefig(os.path.join(C.FIGS, "fig_zooms.png"), dpi=85, facecolor="white")
    plt.close(fig)


def main():
    os.makedirs(C.FIGS, exist_ok=True)
    inp = C.load_inputs()
    gt = a0eval.load_gt()
    r = R.build(inp)
    rgb = rgb_depth_grid()
    edges, _ = U.find_unresolved(inp, r["frag"], r["summary"], r["conn"],
                                 r["unres"], r["comp_of"])
    fig_components(inp, r, rgb)
    fig_unresolved(inp, r, rgb, edges)
    fig_zooms(inp, r, rgb, gt)
    sw = json.load(open(os.path.join(C.RESULTS, "sweeps.json")))
    fig_operating(sw)
    print("wrote", C.FIGS)


if __name__ == "__main__":
    main()
