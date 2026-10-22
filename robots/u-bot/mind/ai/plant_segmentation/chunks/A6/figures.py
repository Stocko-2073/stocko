"""A6 — figures. Every one of these is meant to be looked at, not skimmed.

    ../A3/.venv/bin/python figures.py
"""
from __future__ import annotations

import json
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt          # noqa: E402
import numpy as np                        # noqa: E402
from PIL import Image                     # noqa: E402
from scipy import ndimage                 # noqa: E402

from a6_common import (DatumFrame, ROOT, gt_rc_to_depth_rc,  # noqa: E402
                       load_crop_component, load_gt, load_scene)
from keepout import (CLEARANCE_SWEEP_RDU, DEFAULT_CELL_RDU,  # noqa: E402
                     DEFAULT_CLEARANCE_RDU, TIER_OBSERVED, TIER_UNSEEN,
                     build_keepout)

HERE = os.path.dirname(os.path.abspath(__file__))
FIGS = os.path.join(HERE, "figs")


def rgb_on_depth_grid(shape):
    im = Image.open(os.path.join(ROOT, "plants.jpeg")).convert("RGB")
    return np.asarray(im.resize((shape[1], shape[0]), Image.LANCZOS))


def gt_mask_on_depth_grid(mask, shape):
    """Lift an A0-grid mask to the depth grid by *pulling* each depth pixel from
    its GT pixel. Scattering the other way leaves a lattice of holes (1344/1024
    is not an integer) that reads as speckle in a figure."""
    h, w = shape
    rr, cc = np.meshgrid(np.arange(h), np.arange(w), indexing="ij")
    gr = np.clip(np.rint(rr / (h / mask.shape[0])).astype(int), 0, mask.shape[0] - 1)
    gc = np.clip(np.rint(cc / (w / mask.shape[1])).astype(int), 0, mask.shape[1] - 1)
    return mask[gr, gc]


def outline(mask, width=2):
    return mask & ~ndimage.binary_erosion(mask, iterations=width)


def _tint(rgb, mask, colour, alpha):
    out = rgb.astype(np.float32).copy()
    c = np.array(colour, dtype=np.float32)
    out[mask] = (1 - alpha) * out[mask] + alpha * c
    return out.astype(np.uint8)


def fig_overlay(scene, gt, vol, crop, sigma):
    """The done-criterion figure: does the volume hug the sprawl?"""
    rgb = rgb_on_depth_grid(scene.shape)
    sq_gt = gt_mask_on_depth_grid(gt.instances == 1, scene.shape)

    show = [0.0, 5.0e-3, DEFAULT_CLEARANCE_RDU, 5.0e-2]
    fig, axes = plt.subplots(1, 5, figsize=(26, 9))
    axes[0].imshow(rgb)
    axes[0].set_title("plants.jpeg (depth grid 1344x1008)", fontsize=11)
    for ax, c in zip(axes[1:], show):
        sil = vol.silhouette(scene, c)
        img = _tint(rgb, sil, (255, 40, 40), 0.42)
        img[outline(sq_gt)] = (60, 255, 60)
        ax.imshow(img)
        ax.set_title(f"clearance = {c:g} rdu  ({c/sigma:.2f} datum-$\\sigma$)\n"
                     f"silhouette {100*sil.mean():.1f} % of frame",
                     fontsize=11)
    for ax in axes:
        ax.set_xticks([]); ax.set_yticks([])
    fig.suptitle(
        "A6 keep-out volume for the squash (A4 `merge` component 1), seen from "
        "the camera.\nred = the keep-out silhouette;  green outline = A0 "
        "ground-truth squash.  Scale-free: every length in rdu.", fontsize=13)
    fig.tight_layout()
    p = os.path.join(FIGS, "fig_keepout_overlay.png")
    fig.savefig(p, dpi=95, bbox_inches="tight")
    plt.close(fig)
    return p


def fig_zoom(scene, gt, vol, sigma):
    """Does it reach the vines and the corner leaves, or only the crown?"""
    rgb = rgb_on_depth_grid(scene.shape)
    sil = vol.silhouette(scene, DEFAULT_CLEARANCE_RDU)
    img = _tint(rgb, sil, (255, 40, 40), 0.40)
    h, w = scene.shape
    boxes = {
        "crown (A0 contact point)": (int(552 * 1.3125), int(330 * 1.3125)),
        "vine / petiole run, upper right": (int(300 * 1.3125), int(600 * 1.3125)),
        "corner leaf, top left": (int(90 * 1.3125), int(90 * 1.3125)),
        "corner leaf, bottom right": (int(700 * 1.3125), int(690 * 1.3125)),
    }
    fig, axes = plt.subplots(2, 4, figsize=(20, 11))
    for i, (name, (r, c)) in enumerate(boxes.items()):
        half = 150
        r0, c0 = max(0, r - half), max(0, c - half)
        r1, c1 = min(h, r + half), min(w, c + half)
        axes[0, i].imshow(rgb[r0:r1, c0:c1])
        axes[0, i].set_title(name, fontsize=10)
        axes[1, i].imshow(img[r0:r1, c0:c1])
        axes[1, i].set_title(f"keep-out @ {DEFAULT_CLEARANCE_RDU:g} rdu",
                             fontsize=10)
    for ax in axes.ravel():
        ax.set_xticks([]); ax.set_yticks([])
    fig.suptitle("A6 — the keep-out at the crown and at the extremities. "
                 "The claim under test is that it follows the sprawl, "
                 "not a radius.", fontsize=13)
    fig.tight_layout()
    p = os.path.join(FIGS, "fig_keepout_zooms.png")
    fig.savefig(p, dpi=95, bbox_inches="tight")
    plt.close(fig)
    return p


def fig_footprint(vol, report):
    """The datum-plane footprint against the best a circle can do."""
    cc = report["shipped"]["circle_comparison"][f"{DEFAULT_CLEARANCE_RDU:g}"]
    fp = vol.footprint(DEFAULT_CLEARANCE_RDU)
    nu, nv = fp.shape
    gu = vol.origin_uvw[0] + np.arange(nu) * vol.cell
    gv = vol.origin_uvw[1] + np.arange(nv) * vol.cell
    crown = cc["crown_uv"]
    RR = np.hypot(gu[:, None] - crown[0], gv[None, :] - crown[1])
    r_eq = cc["equal_area_disk"]["radius_rdu"]
    r_cov = cc["covering_disk"]["radius_rdu"]

    fig, ax = plt.subplots(figsize=(9, 8))
    ax.imshow(fp.T, origin="lower", cmap="Greys",
              extent=[gu[0], gu[-1], gv[0], gv[-1]])
    ax.contour(gu, gv, (RR <= r_eq).T.astype(float), levels=[0.5],
               colors="tab:red", linewidths=2)
    ax.contour(gu, gv, (RR <= r_cov).T.astype(float), levels=[0.5],
               colors="tab:blue", linewidths=2, linestyles="--")
    ax.plot(*crown, "y*", ms=18, mec="k")
    ax.set_xlabel("u (rdu, on the A2 datum plane)")
    ax.set_ylabel("v (rdu)")
    ax.set_title(
        "A6 keep-out footprint on the datum vs. a radius around the crown\n"
        f"black = keep-out @ {DEFAULT_CLEARANCE_RDU:g} rdu   "
        f"red = equal-area disk (r={r_eq:.3f}): covers "
        f"{100*cc['equal_area_disk']['fraction_of_sprawl_it_covers']:.0f} % of "
        f"the sprawl, {100*cc['equal_area_disk']['fraction_of_the_disk_that_is_not_plant']:.0f} % of it is not plant\n"
        f"blue = smallest covering disk (r={r_cov:.3f}): "
        f"{cc['covering_disk']['area_inflation_over_footprint']:.2f}x the area, "
        f"{100*cc['covering_disk']['fraction_of_the_disk_that_is_not_plant']:.0f} % of it is not plant",
        fontsize=10)
    fig.tight_layout()
    p = os.path.join(FIGS, "fig_footprint_vs_circle.png")
    fig.savefig(p, dpi=110, bbox_inches="tight")
    plt.close(fig)
    return p


def fig_sweep(report, sweeps, sigma):
    rows = report["shipped"]["clearances"]
    c = np.array([r["clearance_rdu"] for r in rows])
    fig, axes = plt.subplots(1, 3, figsize=(19, 5.4))

    ax = axes[0]
    ax.plot(c / sigma, [r["volume_rdu3"] for r in rows], "o-", label="volume (rdu$^3$)")
    ax.plot(c / sigma, [r["footprint_area_rdu2"] for r in rows], "s-",
            label="datum footprint (rdu$^2$)")
    ax.set_xlabel("clearance (datum $\\sigma$)"); ax.legend()
    ax.set_title("how the keep-out grows")
    ax.axvline(DEFAULT_CLEARANCE_RDU / sigma, color="k", ls=":")

    ax = axes[1]
    ax.plot(c / sigma, [100 * r["gt_squash_covered"] for r in rows], "o-",
            color="tab:green", label="GT squash covered")
    ax.plot(c / sigma, [100 * r["gt_weed_inside"] for r in rows], "o-",
            color="tab:red", label="GT weed shielded")
    ax.plot(c / sigma, [100 * r["gt_weed_inside_already_in_crop_component"]
                        for r in rows], "--", color="tab:orange",
            label="…inherited from A4's merge component")
    ax.plot(c / sigma, [100 * r["gt_ground_inside"] for r in rows], "-.",
            color="tab:brown", label="GT straw/soil inside")
    ax.set_xlabel("clearance (datum $\\sigma$)"); ax.set_ylabel("%")
    ax.set_ylim(0, 105); ax.legend(fontsize=8)
    ax.set_title("what it covers and what it shields")
    ax.axvline(DEFAULT_CLEARANCE_RDU / sigma, color="k", ls=":")

    ax = axes[2]
    for r in sweeps["a4_policy"]:
        cc = np.array([b["clearance_rdu"] for b in r["by_clearance"]]) / sigma
        ax.plot(cc, [100 * b["gt_squash_covered"] for b in r["by_clearance"]],
                "o-", label=f"{r['a4_policy']}: crop covered")
        ax.plot(cc, [100 * b["gt_weed_inside"] for b in r["by_clearance"]],
                "s--", label=f"{r['a4_policy']}: weed shielded")
    ax.set_xlabel("clearance (datum $\\sigma$)"); ax.set_ylabel("%")
    ax.set_ylim(0, 105); ax.legend(fontsize=8)
    ax.set_title("A4 policy: `merge` vs the largest `split` component")
    fig.suptitle("A6 — the clearance sweep. The clearance is a PLACEHOLDER "
                 "(category (b), awaiting C3); this is what it can change.",
                 fontsize=12)
    fig.tight_layout()
    p = os.path.join(FIGS, "fig_clearance_sweep.png")
    fig.savefig(p, dpi=110, bbox_inches="tight")
    plt.close(fig)
    return p


def fig_unseen(scene, crop, vol):
    """Where A4 refused to decide, and where the volume runs off the frame."""
    rgb = rgb_on_depth_grid(scene.shape)
    img = _tint(rgb, crop.observed, (192, 57, 43), 0.35)
    img = _tint(img, crop.unseen, (43, 108, 176), 0.85)
    h, w = scene.shape
    border = np.zeros((h, w), bool)
    border[:6, :] = border[-6:, :] = border[:, :6] = border[:, -6:] = True
    img = _tint(img, border & crop.observed, (255, 230, 0), 0.95)

    fig, axes = plt.subplots(1, 2, figsize=(16, 10))
    axes[0].imshow(img)
    axes[0].set_title(
        f"red = crop component ({crop.observed.sum():,} px)\n"
        f"blue = material behind an UNRESOLVED link, carried as unseen volume "
        f"({crop.unseen.sum():,} px)\n"
        f"yellow = where the component runs off the photograph — nearly the "
        f"whole border\n({crop.n_unresolved.get('leaves_frame', 0)} "
        f"`leaves_frame` edges, {crop.frame_fragment_px:,} px). The volume is "
        f"flagged `frame_open`.", fontsize=10)

    # a vertical slice through the occupancy, at the crown's v index
    from matplotlib.colors import ListedColormap
    tier = vol.tier
    iv = tier.shape[1] // 2
    axes[1].imshow(tier[:, iv, :].T, origin="lower", aspect="auto",
                   cmap=ListedColormap(["#f2f2f2", "#c0392b", "#2b6cb0"]),
                   vmin=0, vmax=2, interpolation="nearest")
    axes[1].set_xlabel("u index (across the datum plane)")
    axes[1].set_ylabel("w index (height above the RANSAC plane)")
    axes[1].set_title(
        "vertical slice of the occupancy grid (mid-v), same colours as the left "
        "panel.\nred = observed crop material, blue = unseen (unresolved link), "
        "white = free.\nEach bar runs from the canopy down to the A2 straw "
        "datum. That is the occupancy assumption,\nand the ragged floor is the "
        "fitted datum, not a plane.", fontsize=10)
    for ax in (axes[0],):
        ax.set_xticks([]); ax.set_yticks([])
    fig.tight_layout()
    p = os.path.join(FIGS, "fig_unseen_and_slice.png")
    fig.savefig(p, dpi=95, bbox_inches="tight")
    plt.close(fig)
    return p


def main():
    os.makedirs(FIGS, exist_ok=True)
    scene = load_scene()
    gt = load_gt()
    frame = DatumFrame.from_scene(scene)
    crop = load_crop_component("merge", gt=gt)
    vol = build_keepout(scene, crop, cell=DEFAULT_CELL_RDU,
                        clearance=DEFAULT_CLEARANCE_RDU, frame=frame)
    report = json.load(open(os.path.join(HERE, "results", "a6_report.json")))
    sweeps = json.load(open(os.path.join(HERE, "results", "sweeps.json")))
    sigma = scene.a2.sigma_datum
    for p in (fig_overlay(scene, gt, vol, crop, sigma),
              fig_zoom(scene, gt, vol, sigma),
              fig_footprint(vol, report),
              fig_sweep(report, sweeps, sigma),
              fig_unseen(scene, crop, vol)):
        print("wrote", p)


if __name__ == "__main__":
    main()
