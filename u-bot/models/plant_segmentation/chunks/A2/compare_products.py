"""
A2 — does the answer depend on which A1 depth product it was fitted to?

    chunks/A1/.venv/bin/python chunks/A2/compare_products.py

A1 shipped two products because one raster could not be both: `primary_raster`
(res 1344, 2.8x the sampling, its own camera physically impossible so the
res-504 camera is rescaled onto it) and `primary_geometry` (res 504, camera
physically consistent). A1 asked A2 to say which it used. This says more than
that: it fits both and reports where they agree.

The two are not directly comparable in raw rdu — each raster has its own median
depth, so its own rdu — so the comparison is made in units of each fit's own
measured datum roughness, which is the scale-free quantity A3/A4/A5 should be
reasoning in anyway.
"""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from PIL import Image  # noqa: E402

HERE = Path(__file__).resolve().parent


def load(dirname: str, tag: str):
    p = HERE / dirname
    m = json.loads((p / "A2_MANIFEST.json").read_text())
    R = json.loads((HERE / "results" / f"fit_report_{tag}.json").read_text())
    return p, m, R


def main() -> None:
    pa, ma, Ra = load("products", "primary_raster")
    pb, mb, Rb = load("products_primary_geometry", "primary_geometry")

    Ha = np.load(pa / "height_above_soil.npy")
    Hb = np.load(pb / "height_above_soil.npy")
    sa = ma["key_numbers"]["datum_roughness_sigma_rdu"]
    sb = mb["key_numbers"]["datum_roughness_sigma_rdu"]
    h, w = Ha.shape
    Hb_up = np.asarray(Image.fromarray(Hb.astype(np.float32)).resize((w, h),
                                                                    Image.BILINEAR))
    a, b = Ha / sa, Hb_up / sb
    Ga = np.load(pa / "ground_inliers.npy")
    Gb = np.asarray(Image.fromarray(np.load(pb / "ground_inliers.npy").astype(np.uint8))
                    .resize((w, h), Image.NEAREST)).astype(bool)

    gain = float(np.polyfit(b.ravel(), a.ravel(), 1)[0])
    out = {
        "units": "each product's height divided by its OWN measured datum "
                 "roughness, so the two are on a common, scale-free axis",
        "per_product": {
            "primary_raster": {
                "grid": list(Ha.shape),
                "camera_usable_per_A1": ma["source"]["camera_usable_per_A1"],
                "sigma_datum_rdu": sa,
                "rdu_normaliser": ma["source"]["rdu_normaliser_depth_units"],
                "inlier_fraction": Ra["fit_quality"]["inlier_fraction"],
                "inlier_rms_rdu": Ra["fit_quality"]["inlier_residual_rms_rdu"],
                "inlier_rms_in_sigma": Ra["fit_quality"]["inlier_residual_rms_rdu"] / sa,
                "plane_normal": Ra["ransac"]["normal"],
                "fit_scale_px": Ra["outer_loop"][-1]["fit_scale_px"],
                "observed_fraction": Ra["coverage"]["observed_fraction"],
            },
            "primary_geometry": {
                "grid": list(Hb.shape),
                "camera_usable_per_A1": mb["source"]["camera_usable_per_A1"],
                "sigma_datum_rdu": sb,
                "rdu_normaliser": mb["source"]["rdu_normaliser_depth_units"],
                "inlier_fraction": Rb["fit_quality"]["inlier_fraction"],
                "inlier_rms_rdu": Rb["fit_quality"]["inlier_residual_rms_rdu"],
                "inlier_rms_in_sigma": Rb["fit_quality"]["inlier_residual_rms_rdu"] / sb,
                "plane_normal": Rb["ransac"]["normal"],
                "fit_scale_px": Rb["outer_loop"][-1]["fit_scale_px"],
                "observed_fraction": Rb["coverage"]["observed_fraction"],
            },
        },
        "plane_normal_angle_between_products_deg": float(np.degrees(np.arccos(
            np.clip(abs(np.dot(Ra["ransac"]["normal"], Rb["ransac"]["normal"])), -1, 1)))),
        "height_agreement_in_sigma": {
            "pearson_r": float(np.corrcoef(a.ravel(), b.ravel())[0, 1]),
            "best_fit_gain_raster_over_geometry": gain,
            "median_abs_diff": float(np.median(np.abs(a - b))),
            "p90_abs_diff": float(np.percentile(np.abs(a - b), 90)),
            "rms_diff": float(np.sqrt(((a - b) ** 2).mean())),
        },
        "height_agreement_in_raw_rdu": {
            "note": ("each raster has its own rdu, so this is only meaningful "
                     "alongside the sigma-normalised comparison above"),
            "best_fit_gain_raster_over_geometry": float(
                np.polyfit(Hb_up.ravel(), Ha.ravel(), 1)[0]),
            "sigma_ratio_geometry_over_raster": float(sb / sa),
            "gain_attributable_to_the_sigma_normalisation": float(
                gain / (np.polyfit(Hb_up.ravel(), Ha.ravel(), 1)[0])),
        },
        "ground_mask_agreement": {
            "iou": float((Ga & Gb).sum() / (Ga | Gb).sum()),
            "raster_only_fraction": float((Ga & ~Gb).mean()),
            "geometry_only_fraction": float((Gb & ~Ga).mean()),
        },
        "which_to_use": (
            "primary_raster. It is the finer grid, its ground mask resolves the "
            "gaps between straw stalks that the res-504 raster averages over, "
            "and A2 never uses the camera for anything the A1 manifest flags as "
            "unusable: the rescaled res-504 camera is what back-projects it. "
            "primary_geometry is kept here as the independent check."
        ),
    }
    (HERE / "results" / "product_comparison.json").write_text(json.dumps(out, indent=2))

    fig, ax = plt.subplots(1, 3, figsize=(16, 6))
    lim = (-2, 120)
    ax[0].hexbin(b.ravel(), a.ravel(), gridsize=120, bins="log", extent=(*lim, *lim))
    ax[0].plot(lim, lim, "w--", lw=1)
    ax[0].set_xlabel("height / σ  (primary_geometry, res 504)")
    ax[0].set_ylabel("height / σ  (primary_raster, res 1344)")
    ax[0].set_title(f"r = {out['height_agreement_in_sigma']['pearson_r']:.4f}, "
                    f"gain {gain:.3f}")
    d = a - b
    im = ax[1].imshow(d, cmap="coolwarm", vmin=-20, vmax=20)
    plt.colorbar(im, ax=ax[1], fraction=0.04, label="σ")
    ax[1].set_title("raster − geometry (in σ)")
    ax[2].hist(d.ravel(), bins=300, range=(-40, 40), log=True)
    ax[2].set_xlabel("difference (σ)")
    ax[2].set_title(f"median |Δ| = {out['height_agreement_in_sigma']['median_abs_diff']:.1f} σ")
    for a_ in ax[1:2]:
        a_.set_xticks([]); a_.set_yticks([])
    fig.suptitle("A2 — the same fit on both A1 depth products", fontsize=12)
    fig.tight_layout()
    fig.savefig(HERE / "results" / "fig_product_comparison.png", dpi=130)
    print(json.dumps(out["height_agreement_in_sigma"], indent=1))
    print(json.dumps(out["ground_mask_agreement"], indent=1))
    print("plane normals differ by "
          f"{out['plane_normal_angle_between_products_deg']:.2f} deg")


if __name__ == "__main__":
    main()
