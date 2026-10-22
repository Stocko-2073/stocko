"""
A2 — figures. The height-band overlay is the by-eye check the roadmap asks for.

    chunks/A1/.venv/bin/python chunks/A2/figures.py [--tag primary_raster]

Band edges are multiples of the *measured* datum roughness sigma, not round
numbers picked to make the picture look right, so the overlay is readable as a
statement about the fit rather than as decoration.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from matplotlib.colors import ListedColormap, BoundaryNorm  # noqa: E402
from matplotlib.patches import Patch, Rectangle  # noqa: E402
from PIL import Image  # noqa: E402

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent

BAND_COLOURS = ["#3b4cc0", "#7ba7d7", "#d9d9a0", "#f0a860", "#c0392b"]
COVER_COLOURS = ["#2c7a3f", "#d9b44a", "#8e44ad"]


def load(tag: str):
    pdir = HERE / ("products" if tag == "primary_raster" else f"products_{tag}")
    R = json.loads((HERE / "results" / f"fit_report_{tag}.json").read_text())
    A = {p.stem: np.load(p) for p in pdir.glob("*.npy")}
    return pdir, R, A


def rgb_on_grid(shape):
    im = Image.open(ROOT / "plants.jpeg").convert("RGB")
    return np.asarray(im.resize((shape[1], shape[0]), Image.BILINEAR)) / 255.0


def band_edges(sigma: float) -> np.ndarray:
    return np.array([-np.inf, 1, 3, 10, 30, np.inf]) * sigma


def band_labels(sigma: float) -> list[str]:
    e = [1, 3, 10, 30]
    return [
        f"at datum  (< {e[0]}σ = {e[0]*sigma:.3f})",
        f"just above ({e[0]}–{e[1]}σ, {e[0]*sigma:.3f}–{e[1]*sigma:.3f})",
        f"low       ({e[1]}–{e[2]}σ, {e[1]*sigma:.3f}–{e[2]*sigma:.3f})",
        f"mid       ({e[2]}–{e[3]}σ, {e[2]*sigma:.3f}–{e[3]*sigma:.3f})",
        f"high      (> {e[3]}σ = {e[3]*sigma:.3f} rdu)",
    ]


def bandify(height, sigma):
    return np.clip(np.digitize(height, band_edges(sigma)[1:-1]), 0, 4)


# ------------------------------------------------------------------ figures


def fig_overlay(tag, R, A, out):
    h_ras = A["height_above_soil"]
    sigma = R["coverage"]["sigma_datum_rdu"]
    rgb = rgb_on_grid(h_ras.shape)
    bands = bandify(h_ras, sigma)
    cmap = ListedColormap(BAND_COLOURS)

    fig, axes = plt.subplots(1, 3, figsize=(16.5, 8.2))
    axes[0].imshow(rgb)
    axes[0].set_title("RGB (resampled to the depth grid)")

    axes[1].imshow(rgb)
    axes[1].imshow(bands, cmap=cmap, norm=BoundaryNorm(np.arange(-0.5, 5), 5),
                   alpha=0.55, interpolation="nearest")
    axes[1].set_title("height above the straw datum, banded")
    axes[1].legend(
        handles=[Patch(color=c, label=l)
                 for c, l in zip(BAND_COLOURS, band_labels(sigma))],
        loc="lower left", fontsize=7, framealpha=0.9,
        title=f"σ(datum) = {sigma:.4f} rdu", title_fontsize=7,
    )

    hv = np.where(A["validity_mask"], h_ras, np.nan)
    im = axes[2].imshow(hv, cmap="turbo",
                        vmin=float(np.nanpercentile(hv, 1)),
                        vmax=float(np.nanpercentile(hv, 99)))
    axes[2].set_title("height (rdu), invalid pixels blanked")
    plt.colorbar(im, ax=axes[2], fraction=0.04, label="rdu above straw")
    for a in axes:
        a.set_xticks([]); a.set_yticks([])
    fig.suptitle(
        f"A2 height above soil — {tag} — scale_free, all distances in rdu. "
        "DATUM = STRAW SURFACE, not bare soil.", fontsize=11)
    fig.tight_layout()
    fig.savefig(out, dpi=130)
    plt.close(fig)


def fig_zooms(tag, R, A, out, crops):
    h_ras = A["height_above_soil"]
    sigma = R["coverage"]["sigma_datum_rdu"]
    rgb = rgb_on_grid(h_ras.shape)
    bands = bandify(h_ras, sigma)
    cmap = ListedColormap(BAND_COLOURS)
    n = len(crops)
    fig, axes = plt.subplots(2, n, figsize=(3.4 * n, 7.2))
    for j, (name, (r0, r1, c0, c1)) in enumerate(crops.items()):
        sub = h_ras[r0:r1, c0:c1]
        axes[0, j].imshow(rgb[r0:r1, c0:c1])
        axes[0, j].set_title(f"{name}\nmedian {np.median(sub):+.3f} rdu "
                             f"= {np.median(sub)/sigma:.0f}σ", fontsize=9)
        axes[1, j].imshow(rgb[r0:r1, c0:c1])
        axes[1, j].imshow(bands[r0:r1, c0:c1], cmap=cmap,
                          norm=BoundaryNorm(np.arange(-0.5, 5), 5), alpha=0.6,
                          interpolation="nearest")
        for a in (axes[0, j], axes[1, j]):
            a.set_xticks([]); a.set_yticks([])
    fig.suptitle("A2 — by-eye check on named regions (bands as in the overlay)",
                 fontsize=11)
    fig.tight_layout()
    fig.savefig(out, dpi=130)
    plt.close(fig)


def fig_coverage(tag, R, A, out):
    rgb = rgb_on_grid(A["coverage_class"].shape)
    fig, axes = plt.subplots(1, 3, figsize=(16.5, 8.2))
    cmap = ListedColormap(COVER_COLOURS)
    axes[0].imshow(rgb)
    axes[0].imshow(A["coverage_class"], cmap=cmap,
                   norm=BoundaryNorm(np.arange(-0.5, 3), 3), alpha=0.55,
                   interpolation="nearest")
    cov = R["coverage"]
    axes[0].legend(handles=[
        Patch(color=COVER_COLOURS[0],
              label=f"observed  {cov['observed_fraction']*100:.1f} %"),
        Patch(color=COVER_COLOURS[1],
              label=f"interpolated {cov['interpolated_fraction']*100:.1f} %"),
        Patch(color=COVER_COLOURS[2],
              label=f"extrapolated {cov['extrapolated_fraction']*100:.1f} %"),
    ], loc="lower left", fontsize=8, framealpha=0.9)
    axes[0].set_title("coverage: where the datum is observed vs. inferred")

    im = axes[1].imshow(A["support_distance_px"], cmap="magma")
    plt.colorbar(im, ax=axes[1], fraction=0.04, label="px to nearest ground observation")
    axes[1].set_title(f"support distance (trust limit "
                      f"{cov['max_trusted_support_px']:.0f} px)")

    im = axes[2].imshow(A["height_sigma"], cmap="viridis")
    plt.colorbar(im, ax=axes[2], fraction=0.04, label="rdu")
    axes[2].set_title("datum 1σ uncertainty (measured hold-out curve)")
    for a in axes:
        a.set_xticks([]); a.set_yticks([])
    fig.tight_layout()
    fig.savefig(out, dpi=130)
    plt.close(fig)


def fig_diagnostics(tag, R, A, out):
    fig, ax = plt.subplots(2, 3, figsize=(16, 9))

    # local-planarity curve
    c = R["local_planarity_curve_rdu"]
    wins = sorted(int(k[3:]) for k in c)
    ax[0, 0].loglog(wins, [c[f"win{w}"]["p10"] for w in wins], "o-", label="p10 (floor)")
    ax[0, 0].loglog(wins, [c[f"win{w}"]["p50"] for w in wins], "s-", label="p50")
    ax[0, 0].axhline(R["ransac"]["threshold_rdu"], color="k", ls="--",
                     label=f"RANSAC thr {R['ransac']['threshold_rdu']:.1e}")
    ax[0, 0].axhline(R["coverage"]["sigma_datum_rdu"], color="r", ls=":",
                     label=f"datum σ {R['coverage']['sigma_datum_rdu']:.1e}")
    ax[0, 0].set_xlabel("plane-fit window (px)"); ax[0, 0].set_ylabel("rdu")
    ax[0, 0].set_title("local-planarity curve, extended to the A2 fit scale")
    ax[0, 0].legend(fontsize=7)

    # CV curves
    cvd = R["cross_validation"]
    for key, style, lab in (("curve_lam_rmse_gap", "o-", "gap design (selects)"),
                            ("curve_lam_rmse_block", "s--", "block design")):
        arr = np.array(cvd[key], float)
        ax[0, 1].loglog(arr[:, 0], arr[:, 1], style, ms=3, label=lab)
    ax[0, 1].axvline(cvd["lam_selected"], color="k", ls="--",
                     label=f"λ = {cvd['lam_selected']:.3g}")
    ax[0, 1].set_xlabel("λ"); ax[0, 1].set_ylabel("held-out RMSE (rdu)")
    ax[0, 1].set_title("cross-validation on inliers")
    ax[0, 1].legend(fontsize=7)

    # variogram
    v = R["variogram"]
    ax[0, 2].plot(v["lag_centres_px"], v["semivariance"], "-")
    ax[0, 2].axvline(v["practical_range_px"], color="k", ls="--",
                     label=f"practical range {v['practical_range_px']:.0f} px")
    ax[0, 2].set_xlabel("lag (px)"); ax[0, 2].set_ylabel("semivariance (rdu²)")
    ax[0, 2].set_title("residual autocorrelation")
    ax[0, 2].legend(fontsize=7)

    # residual histogram
    hgt = A["height_above_soil_plane_normal"]
    g = A["ground_inliers"]
    sigma = R["coverage"]["sigma_datum_rdu"]
    ax[1, 0].hist(hgt.ravel(), bins=400, range=(-0.15, 0.6), log=True,
                  color="0.7", label="all pixels")
    ax[1, 0].hist(hgt[g], bins=400, range=(-0.15, 0.6), log=True,
                  color="#2c7a3f", label="ground inliers")
    for k in (-3, 3):
        ax[1, 0].axvline(k * sigma, color="r", ls=":")
    ax[1, 0].set_xlabel("height above datum (rdu)")
    ax[1, 0].set_title("height distribution; dotted = ±3σ ground band")
    ax[1, 0].legend(fontsize=7)

    # hold-out error vs support
    b = R["holdout_error_vs_support"]["bins"]
    x = [0.5 * (d["support_px_lo"] + d["support_px_hi"]) for d in b]
    ax[1, 1].plot(x, [d["rms_rdu"] for d in b], "o-", label="RMS")
    ax[1, 1].plot(x, [np.abs(d["bias_rdu"]) for d in b], "s--", label="|bias|")
    ax[1, 1].axhline(sigma, color="r", ls=":", label="datum σ")
    ax[1, 1].axhline(R["holdout_error_vs_support"]["ground_band_rdu"], color="k",
                     ls="--", label="ground band 3σ")
    ax[1, 1].axvline(R["coverage"]["max_trusted_support_px"], color="k", lw=0.8)
    ax[1, 1].set_yscale("log")
    ax[1, 1].set_xlabel("distance to nearest ground observation (px)")
    ax[1, 1].set_ylabel("gap-fill error (rdu)")
    ax[1, 1].set_title("measured cost of interpolating under canopy")
    ax[1, 1].legend(fontsize=7)

    # surface departure from the plane
    S = A["soil_surface_plane_offset"]
    im = ax[1, 2].imshow(S, cmap="coolwarm",
                         vmin=-np.abs(S).max(), vmax=np.abs(S).max())
    plt.colorbar(im, ax=ax[1, 2], fraction=0.04, label="rdu")
    ax[1, 2].set_title("fitted datum minus the RANSAC plane\n"
                       f"peak-to-peak {S.max()-S.min():.3f} rdu "
                       f"= {(S.max()-S.min())/sigma:.0f}σ")
    ax[1, 2].set_xticks([]); ax[1, 2].set_yticks([])

    fig.suptitle(f"A2 fit diagnostics — {tag}", fontsize=12)
    fig.tight_layout()
    fig.savefig(out, dpi=130)
    plt.close(fig)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tag", default="primary_raster")
    args = ap.parse_args()
    pdir, R, A = load(args.tag)
    fdir = HERE / "results"
    h, w = A["height_above_soil"].shape
    sc = h / 1344.0  # crops are written for the 1344x1008 grid

    def C(r0, r1, c0, c1):
        return (int(r0 * sc), int(r1 * sc), int(c0 * sc), int(c1 * sc))

    # Named by eye from the RGB on the 1344x1008 grid. These are the regions the
    # roadmap says the overlay has to get right.
    crops = {
        "straw only (the datum)": C(1180, 1340, 230, 430),
        "low broadleaf weed": C(980, 1200, 60, 330),
        "grass blades over straw": C(380, 580, 20, 250),
        "squash fruit + crown": C(780, 980, 350, 600),
        "squash leaf, near camera": C(1000, 1300, 600, 950),
    }
    fig_overlay(args.tag, R, A, fdir / f"fig_height_overlay_{args.tag}.png")
    fig_zooms(args.tag, R, A, fdir / f"fig_zooms_{args.tag}.png", crops)
    fig_coverage(args.tag, R, A, fdir / f"fig_coverage_{args.tag}.png")
    fig_diagnostics(args.tag, R, A, fdir / f"fig_diagnostics_{args.tag}.png")
    print("wrote figures to", fdir)


if __name__ == "__main__":
    main()
