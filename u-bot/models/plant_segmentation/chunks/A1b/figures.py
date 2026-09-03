"""A1b figures. Every one is meant to be looked at, not just produced.

    chunks/A1/.venv/bin/python chunks/A1b/figures.py

fig_refinement.png   the refinement curve the roadmap asked for, on both depth
                     products, in all three normalisations — plus the synthetic
                     control with a known focal length, which is the panel that
                     settles it.
fig_shape.png        what `f` actually does: the soil band's own cross-section
                     reconstructed at three focal lengths. The bed is the same
                     bed; only the rake changes.
fig_normals.png      the 7.6 deg plane-normal disagreement between A1's two
                     depth products, as a function of `f`.
fig_sensitivity.png  the downstream stack across the sweep: what moves and what
                     does not.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from a1b_common import (A2, DA3_F_MAX, DA3_F_MEAN, DA3_F_MIN, F_CHOSEN,  # noqa: E402
                        F_INITIAL, FIGS, RESULTS, SWEEP_F, depth_product_dir)
from depth_to_cloud import load_depth_product  # noqa: E402

CAPTION = ("scale_free — all distances in rdu (1 rdu = median scene depth). "
           "Datum = the STRAW mulch surface, not soil. Absolute scale UNRESOLVED.")


def band(ax):
    ax.axvspan(DA3_F_MIN, DA3_F_MAX, color="tab:orange", alpha=0.12, zorder=0)
    ax.axvline(DA3_F_MEAN, color="tab:orange", lw=1.0, ls="--", zorder=1)
    ax.axvline(F_INITIAL, color="tab:blue", lw=1.0, ls=":", zorder=1)
    ax.axvline(F_CHOSEN, color="tab:red", lw=1.2, zorder=1)
    ax.set_xscale("log")
    ax.grid(alpha=0.25)


def fig_refinement():
    d = json.loads((RESULTS / "focal_refinement.json").read_text())
    fig, axes = plt.subplots(2, 3, figsize=(16, 8.5))
    keys = [("planarity_rms_rdu", "planarity residual RMS (rdu)\nthe literal instruction"),
            ("surface_variation_median", "surface variation  λ3/Σλ\nscale-invariant"),
            ("roughness_slope_median", "roughness slope  √(λ3/(λ1+λ2))\nscale-invariant")]
    for j, (k, title) in enumerate(keys):
        ax = axes[0, j]
        for name, sty in (("primary_raster", "-"), ("primary_geometry", "--")):
            c = d["products"][name]["curve"]
            ax.plot([r["f_native_px"] for r in c], [r[k] for r in c], sty,
                    label=f"{name} (res {d['products'][name]['process_res']})")
        if k == "planarity_rms_rdu":
            c = d["products"]["primary_raster"]["curve"]
            ax.fill_between([r["f_native_px"] for r in c],
                            [r["planarity_rms_rdu_boot_p05"] for r in c],
                            [r["planarity_rms_rdu_boot_p95"] for r in c],
                            alpha=0.2, color="tab:blue", lw=0)
        band(ax)
        ax.set_yscale("log")
        ax.set_title(title, fontsize=10)
        ax.set_xlabel("assumed f (px at 3000×4000)")
        if j == 0:
            ax.legend(fontsize=7)

    # bottom row: the control
    for j, ft in enumerate(sorted(d["control_synthetic_known_f"], key=float)):
        ax = axes[1, j]
        c = d["control_synthetic_known_f"][ft]["curve"]
        f = [r["f_native_px"] for r in c]
        for k, lab in (("planarity_rms_rdu", "planarity RMS"),
                       ("surface_variation_median", "surface variation"),
                       ("roughness_slope_median", "roughness slope")):
            v = np.array([r[k] for r in c], float)
            ax.plot(f, v / np.nanmax(v), label=lab)
        ax.axvline(float(ft), color="k", lw=2.0)
        ax.set_xscale("log")
        ax.grid(alpha=0.25)
        ax.set_title(f"CONTROL: synthetic surface, TRUE f = {int(float(ft))} px\n"
                     f"(black line). No curve has a minimum there.", fontsize=10)
        ax.set_xlabel("assumed f (px at 3000×4000)")
        ax.set_ylabel("normalised to its own max")
        if j == 0:
            ax.legend(fontsize=7)

    fig.suptitle("A1b — the planarity refinement of `f`, and why it is degenerate\n"
                 "orange band = DA3's own camera head (4159–4695 px) · red = A1b's "
                 "chosen f · blue dotted = the 26 mm-equivalent prior (3005 px)\n"
                 + CAPTION, fontsize=10)
    fig.tight_layout(rect=(0, 0, 1, 0.90))
    p = FIGS / "fig_refinement.png"
    fig.savefig(p, dpi=130)
    plt.close(fig)
    print(f"wrote {p}")


def fig_shape():
    """The same bed, back-projected at three focal lengths."""
    prod = load_depth_product(depth_product_dir("primary_raster"))
    d = np.asarray(prod.depth, np.float64)
    d = d / np.median(d[np.isfinite(d) & (d > 0)])
    g = np.load(A2 / "products" / "ground_inliers.npy")
    h, w = d.shape
    cx, cy = (w - 1) / 2.0, (h - 1) / 2.0
    v, u = np.nonzero(g)
    step = max(1, v.size // 40000)
    v, u = v[::step], u[::step]
    z = d[v, u]

    fig, axes = plt.subplots(1, 3, figsize=(15, 4.2), sharex=True, sharey=True)
    for ax, f_native in zip(axes, (1502.0, F_INITIAL, 6009.0)):
        f = f_native * w / 3000.0
        Y = (v - cy) * z / f
        ax.scatter(Y, z, s=0.3, alpha=0.15, c="tab:green", lw=0)
        A = np.polyfit(Y, z, 1)
        xs = np.linspace(-2.2, 1.6, 10)
        ax.plot(xs, np.polyval(A, xs), "r-", lw=1.5)
        tilt = np.degrees(np.arctan(abs(A[0])))
        ax.set_title(f"f = {int(f_native)} px  "
                     f"({f_native*43.2666/5000:.0f} mm-eq)\n"
                     f"ground rakes {tilt:.0f}° across the frame", fontsize=10)
        ax.set_xlabel("y (rdu, image-plane direction)")
        ax.grid(alpha=0.25)
    # one common frame, equal aspect: the point is that the bed changes SHAPE,
    # and it is invisible if each panel is allowed to autoscale
    axes[0].set_xlim(-2.2, 1.6)
    axes[0].set_ylim(1.85, 0.85)
    for ax in axes:
        ax.set_aspect("equal", adjustable="box")
    axes[0].set_ylabel("z, depth (rdu)")
    fig.suptitle("A1b — what the focal-length assumption actually changes: the "
                 "SHAPE of the reconstruction.\nSame depth raster, same soil "
                 "band, three assumed focal lengths. Each is an exact axial "
                 "rescale of the others, so each is exactly as planar as the "
                 "others.\n" + CAPTION, fontsize=10)
    fig.tight_layout(rect=(0, 0.0, 1, 0.80))
    p = FIGS / "fig_shape.png"
    fig.savefig(p, dpi=130)
    plt.close(fig)
    print(f"wrote {p}")


def fig_normals():
    d = json.loads((RESULTS / "normal_reconciliation.json").read_text())
    pw = d["pairwise"]
    f = [r["f_native_px"] for r in pw]
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.6))
    ax = axes[0]
    for k, lab in (("disagreement_deg_closed_form", "closed form from A2's normals"),
                   ("disagreement_deg_least_squares", "least-squares refit"),
                   ("disagreement_deg_ransac", "RANSAC refit")):
        ax.plot(f, [r[k] for r in pw], label=lab)
    ax.axhline(7.6, color="k", ls=":", lw=1)
    ax.annotate("A2's recorded 7.6°", (f[2], 7.9), fontsize=8)
    band(ax)
    ax.set_ylabel("angle between the two products' ground normals (deg)")
    ax.set_xlabel("assumed f (px at 3000×4000)")
    ax.legend(fontsize=8)
    ax.set_title("The disagreement A2 left for A1b\nno interior minimum: it "
                 "shrinks to zero only as f → 0", fontsize=10)

    ax = axes[1]
    ax.plot(f, [r["tilt_raster_deg"] for r in pw], label="primary_raster (res 1344)")
    ax.plot(f, [r["tilt_geometry_deg"] for r in pw], "--",
            label="primary_geometry (res 504)")
    band(ax)
    ax.set_ylabel("ground tilt from the optical axis (deg)")
    ax.set_xlabel("assumed f (px at 3000×4000)")
    ax.legend(fontsize=8)
    ax.set_title("…and what f costs in absolute terms: the assumed focal length\n"
                 "decides how steeply the bed is believed to rake away", fontsize=10)
    fig.suptitle("A1b — plane-normal reconciliation.  " + CAPTION, fontsize=9)
    fig.tight_layout(rect=(0, 0, 1, 0.92))
    p = FIGS / "fig_normals.png"
    fig.savefig(p, dpi=130)
    plt.close(fig)
    print(f"wrote {p}")


PANELS = [
    ("A2 inlier residual RMS (rdu)", "A2 soil-fit residual", True),
    ("A2 datum sigma (rdu)", "A2 datum roughness σ", True),
    ("A2 ground tilt from optical axis (deg)", "A2 ground tilt", False),
    ("A4 split continuity tol (rdu)", "A4 continuity tolerance", True),
    ("A4 split components", "A4 components (split)", False),
    ("A4 split instance F1", "A4 instance F1 (split)", False),
    ("A4 split squash best IoU", "A4 squash best IoU", False),
    ("A4 split grass absorbed", "A4 grass absorbed into crop", False),
    ("A4 split clover fraction in crop", "A4 clover inside crop", False),
    ("A5 split observed", "A5 observed contacts", False),
    ("A5 split occluded", "A5 occluded", False),
    ("A5 split GT-consistency median (px)", "A5 GT-consistency median (px)", False),
]


def fig_sensitivity():
    d = json.loads((RESULTS / "sensitivity.json").read_text())
    tags = d["swept_tags_in_order"]
    fs = [d["f_native_px_by_tag"][t] for t in tags]
    fig, axes = plt.subplots(4, 3, figsize=(14, 13))
    for ax, (col, title, logy) in zip(axes.ravel(), PANELS):
        c = d["columns"][col]
        y = [c["by_tag"][t] for t in tags]
        y = [np.nan if v is None else float(v) for v in y]
        ax.plot(fs, y, "o-", ms=4)
        m = c["by_tag"].get("manifest")
        mf = d["f_native_px_by_tag"].get("manifest")
        if m is not None and mf is not None:
            ax.plot([float(mf)], [float(m)], "k*", ms=13, zorder=5,
                    label="A1's own camera (shipped)")
            ax.legend(fontsize=7, loc="best")
        band(ax)
        if logy:
            ax.set_yscale("log")
        s = c["sensitivity"]
        ax.set_title(f"{title}\nspread {s.get('spread_over_median', float('nan'))*100:.1f} %"
                     f" · slope {s.get('loglog_slope') if s.get('loglog_slope') is None else round(s['loglog_slope'],2)}"
                     f" · {s.get('verdict','?')}", fontsize=9)
        ax.set_xlabel("assumed f (px at 3000×4000)")
    fig.suptitle("A1b — the Phase A stack across the focal-length sweep.\n"
                 "orange band = DA3's own camera head · red = A1b's chosen f · "
                 "blue dotted = the 26 mm prior\n" + CAPTION, fontsize=10)
    fig.tight_layout(rect=(0, 0, 1, 0.94))
    p = FIGS / "fig_sensitivity.png"
    fig.savefig(p, dpi=120)
    plt.close(fig)
    print(f"wrote {p}")


def main():
    FIGS.mkdir(parents=True, exist_ok=True)
    fig_refinement()
    fig_shape()
    if (RESULTS / "normal_reconciliation.json").exists():
        fig_normals()
    if (RESULTS / "sensitivity.json").exists():
        fig_sensitivity()


if __name__ == "__main__":
    main()
