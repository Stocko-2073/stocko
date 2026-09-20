"""
A2 — fit the soil (straw) surface and derive `height_above_soil`.

    chunks/A1/.venv/bin/python chunks/A2/fit_soil_surface.py [--product primary_raster]

Reads A1's depth products through `chunks/A1/products/MANIFEST.json`, works in
`scale_free` mode throughout (every distance in **rdu**), and writes:

    products/height_above_soil.npy       (H, W) float32, rdu, +ve = above datum
    products/validity_mask.npy           (H, W) bool
    products/soil_surface_depth.npy      (H, W) float32, z-depth of the datum
    products/support_distance_px.npy     (H, W) float32
    products/coverage_class.npy          (H, W) uint8  0 observed 1 interpolated 2 extrapolated
    products/ground_inliers.npy          (H, W) bool
    products/A2_MANIFEST.json            provenance + every measured number
    results/fit_report.json              the fit-quality report

**The datum is the straw mulch surface, not bare soil.** Bare soil is barely
visible in this scene, so what the depth actually observes is the top of the
mulch. Every height in these products is therefore height above *straw*, and is
offset from height above soil by the (unmeasured, unobservable-from-one-photo)
straw depth. Stated in the manifest as well as here.

The pipeline, and where each number comes from:

1.  Back-project the float depth to a camera-space cloud (A1's
    `depth_to_cloud`, `scale_free`, the res-504 camera rescaled as the A1
    manifest requires).
2.  Extend A1's local-planarity curve to the window sizes A2 actually fits over,
    so the RANSAC inlier threshold is read off *at the fit scale* — category (a).
3.  RANSAC plane as the initial estimate. Its normal is oriented toward the
    camera; nothing assumes level ground or a known camera height.
4.  Iterate: robust penalised-spline surface over ground candidates; re-estimate
    the datum roughness from the *below-surface* half of the residual
    distribution (nothing in a scene lies under the ground, so that half is
    roughness and noise, never canopy); re-select candidates within 3x that.
5.  Smoothing `lam` by spatially-blocked cross-validation on the inliers, with
    the block size set by the measured residual autocorrelation range.
6.  Heights measured along the *local* surface normal of the fitted field.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np
import scipy.ndimage as ndi
import scipy.sparse as sp
from scipy.sparse.linalg import splu

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
A1 = ROOT / "chunks" / "A1"
sys.path.insert(0, str(A1))
sys.path.insert(0, str(HERE))

from depth_to_cloud import Intrinsics, depth_to_cloud, load_depth_product  # noqa: E402
from soil_fit import (  # noqa: E402
    PSpline2D,
    block_cv_folds,
    disk_fold_masks,
    local_plane_residuals,
    noise_floor,
    ransac_plane,
    variogram_range,
)

# ---------------------------------------------------------------- conventions
# R1 audit note. Exactly one number here is a threshold, and it is swept:
# BAND_SIGMA. The rest are compute budgets (how many folds, how many outer
# rounds, how wide a search grid, which seed) — they change how long this runs
# and whether it is reproducible, not what counts as ground. Nothing here is a
# statement about gardens.
BAND_SIGMA = 3.0  # ground band = BAND_SIGMA x datum roughness. THE threshold.
BAND_SIGMA_SWEEP = (2.0, 3.0, 4.0, 5.0)
CV_K = 5  # folds; with coverage 0.2 per fold this is the usual 5-fold split
LAM_GRID = np.logspace(-3, 7, 21)  # search range for CV, wide enough to bracket
N_SEG = (24, 32)  # (u, v) spline segments; a resolution ceiling, not a tuning
N_SEG_ALT = (16, 21)  # second basis size, to show lam and not the basis decides
MAX_OUTER = 8  # compute budget; the loop reports its own churn at exit
RNG_SEED = 20260901  # reproducibility, nothing else


def log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


# --------------------------------------------------------------------- inputs


def load_product(name: str):
    manifest = json.loads((A1 / "products" / "MANIFEST.json").read_text())
    entry = manifest["products"][name]
    prod = load_depth_product(A1 / Path(entry["depth"]).parent)
    cam = entry["camera"]
    intr = Intrinsics(
        fx=cam["fx"], fy=cam["fy"], cx=cam["cx"], cy=cam["cy"],
        width=cam["width"], height=cam["height"],
        provenance=cam["provenance"], note=cam["note"],
    )
    return manifest, entry, prod, intr


# ------------------------------------------------------------ geometry helpers


def ray_directions(h: int, w: int, intr: Intrinsics) -> np.ndarray:
    v, u = np.mgrid[0:h, 0:w].astype(np.float64)
    return np.stack(
        [(u - intr.cx) / intr.fx, (v - intr.cy) / intr.fy, np.ones_like(u)], axis=-1
    )


def surface_points(dirs: np.ndarray, normal: np.ndarray, offset: float, s: np.ndarray):
    """3-D points where each pixel ray meets the surface whose plane-signed
    distance field is `s`."""
    denom = dirs @ normal
    t = (s + offset) / denom
    return dirs * t[..., None]


def local_normals(P: np.ndarray, normal: np.ndarray) -> np.ndarray:
    """Unit normals of a 3-D surface raster, from central differences, oriented
    to the same side as the global plane normal."""
    du = np.gradient(P, axis=1)
    dv = np.gradient(P, axis=0)
    n = np.cross(du, dv)
    n /= np.linalg.norm(n, axis=-1, keepdims=True) + 1e-300
    flip = np.sign(n @ normal)[..., None]
    flip[flip == 0] = 1.0
    return n * flip


def effective_dof(spl: PSpline2D, B: sp.csr_matrix, w: np.ndarray, lam: float) -> float:
    """trace of the hat matrix = effective number of parameters actually used.
    Turns `lam` into a length: sqrt(area / edf) is the patch size the fit
    resolves, which is the scale the RANSAC threshold must be read at."""
    BtWB = (B.T @ sp.diags(w) @ B).toarray()
    A = BtWB + lam * spl.penalty.toarray()
    return float(np.trace(np.linalg.solve(A, BtWB)))


# ------------------------------------------------------------------- the fit


def fit_surface(
    u: np.ndarray, v: np.ndarray, d: np.ndarray, cand: np.ndarray,
    spl: PSpline2D, lam: float,
):
    spl, w, scale = spl.fit_robust(u[cand], v[cand], d[cand], lam)
    return spl, w, scale


def below_surface_sigma(resid: np.ndarray) -> float:
    """Robust roughness of the datum, estimated from the *below-surface* half of
    the residual distribution only.

    Nothing in the scene is under the ground, so residuals below the fitted
    surface are roughness plus depth noise and cannot be canopy. For a symmetric
    error distribution the median of |r| over r < 0 is the half-normal median,
    so 1.4826 x that is the same sigma the two-sided MAD would give — but it
    cannot be inflated by the plants, which is the whole point.
    """
    neg = resid[resid < 0]
    if neg.size < 100:
        return float("nan")
    return float(1.4826 * np.median(np.abs(neg)))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--product", default="primary_raster")
    ap.add_argument("--out", default=None, help="subdirectory tag for artifacts")
    ap.add_argument("--quick", action="store_true")
    args = ap.parse_args()

    tag = args.out or args.product
    prod_dir = HERE / "products" if tag == "primary_raster" else HERE / f"products_{tag}"
    res_dir = HERE / "results"
    prod_dir.mkdir(parents=True, exist_ok=True)
    res_dir.mkdir(parents=True, exist_ok=True)

    R: dict = {"product": args.product, "scale_confidence": "scale_free",
               "units": "rdu (relative depth units; 1 rdu = median scene depth)"}

    # ---------------------------------------------------------------- 1. cloud
    manifest, entry, prod, intr = load_product(args.product)
    h, w = prod.depth.shape
    log(f"{args.product}: depth {h}x{w}, camera f=({intr.fx:.1f},{intr.fy:.1f}) "
        f"provenance={intr.provenance} usable={entry['camera_usable']}")
    cloud = depth_to_cloud(prod.depth, intr, mode="scale_free")
    xyz = cloud.as_raster((h, w))
    pts = cloud.xyz
    R["cloud"] = {
        "n_points": len(cloud), "normaliser_depth_units_per_rdu": cloud.normaliser,
        "camera": intr.as_dict(), "camera_usable_per_A1": entry["camera_usable"],
        "camera_note": entry["why"],
    }

    # -------------------------------- 2. local-planarity curve at the fit scale
    windows = (9, 17, 33, 49, 65, 97, 129) if not args.quick else (33, 65)
    curve = {}
    for win in windows:
        r = local_plane_residuals(xyz, win=win, stride=win)
        curve[f"win{win}"] = noise_floor(r)
        log(f"  local planarity win{win}: p10={curve[f'win{win}']['p10']:.3e} "
            f"p50={curve[f'win{win}']['p50']:.3e} rdu (n={r.size})")
    R["local_planarity_curve_rdu"] = curve

    def sigma_at_scale(px: float) -> tuple[float, str]:
        """p10 of the local-plane residual at the window closest to `px`."""
        keys = sorted(curve, key=lambda k: abs(int(k[3:]) - px))
        return curve[keys[0]]["p10"], keys[0]

    # ------------------------------------------------- 3. RANSAC plane + sweep
    sigma33 = curve.get("win33", curve[list(curve)[0]])["p10"]
    plane = ransac_plane(pts, threshold=sigma33, seed=RNG_SEED)
    log(f"  RANSAC @ {sigma33:.3e} rdu: inliers {plane.inliers.mean()*100:.2f}%, "
        f"normal {np.round(plane.normal,3)}")

    sweep = {}
    for mult in (1, 3, 10, 30, 100, 300):
        p = ransac_plane(pts, threshold=sigma33 * mult, seed=RNG_SEED)
        r = p.signed_distance(pts)
        sweep[f"{mult}x"] = {
            "threshold_rdu": sigma33 * mult,
            "inlier_fraction": float(p.inliers.mean()),
            "inlier_rms_rdu": float(np.sqrt((r[p.inliers] ** 2).mean())),
            "normal": p.normal.tolist(),
            "angle_to_base_normal_deg": float(
                np.degrees(np.arccos(np.clip(abs(p.normal @ plane.normal), -1, 1)))
            ),
            "tilt_from_camera_axis_deg": float(
                np.degrees(np.arccos(min(1.0, abs(p.normal[2]))))
            ),
        }
    R["ransac"] = {
        "threshold_rdu": sigma33,
        "threshold_source": "A1 local-planarity p10 at win33, re-measured here",
        "normal": plane.normal.tolist(),
        "offset_rdu": plane.offset,
        "inlier_fraction": float(plane.inliers.mean()),
        "tilt_from_camera_axis_deg": float(
            np.degrees(np.arccos(min(1.0, abs(plane.normal[2]))))
        ),
        "threshold_sweep": sweep,
    }

    # ------------------------------------------------------- 4/5. outer loop
    vv, uu = np.mgrid[0:h, 0:w]
    u_f = uu.ravel().astype(np.float64)
    v_f = vv.ravel().astype(np.float64)
    d_plane = plane.signed_distance(pts)          # ravel order == raster order
    assert pts.shape[0] == h * w, "depth raster must be dense for this path"

    spl = PSpline2D((0, w - 1), (0, h - 1), n_seg_u=N_SEG[0], n_seg_v=N_SEG[1])
    s_field = np.zeros(h * w)                      # surface, plane-relative
    cand = plane.inliers.copy()
    lam = 1.0
    history = []
    sigma_datum = float("nan")
    fit_scale_px = float("nan")
    edf = float("nan")
    cv_record: dict = {}
    vario: dict = {}

    for it in range(MAX_OUTER):
        resid_all = d_plane - s_field
        sigma_datum_new = below_surface_sigma(resid_all[cand]) if it else \
            below_surface_sigma(resid_all)
        if not np.isfinite(sigma_datum_new):
            sigma_datum_new = sigma33
        band = BAND_SIGMA * sigma_datum_new
        cand_new = np.abs(resid_all) < band

        # --- lam by cross-validation on the inliers ---------------------------
        # Two CV designs, both on inliers only, reported side by side:
        #   * "gap"   holds out compact disks the size of the canopy holes this
        #             scene actually has, measured from the support-distance
        #             distribution over non-ground pixels;
        #   * "block" holds out square blocks two decorrelation lengths across,
        #             the textbook design for autocorrelated residuals.
        # The gap design is the one that selects lam, because filling canopy
        # holes is the job. The block design is reported so the difference
        # between "the surface that predicts its own neighbours" and "the
        # surface that predicts a hole" is on the record, not hidden.
        vario = variogram_range(
            resid_all.reshape(h, w), cand_new.reshape(h, w),
            lags=np.arange(1, 200, 3.0),
        )
        gap_support = ndi.distance_transform_edt(~cand_new.reshape(h, w))
        gap_radii = [float(np.percentile(gap_support[~cand_new.reshape(h, w)], p))
                     for p in (50, 75, 90)]
        gap_radii = [max(4.0, r) for r in gap_radii]

        idx_all = np.nonzero(cand_new)[0]
        rng_cv = np.random.default_rng(RNG_SEED)
        idx_cv = (rng_cv.choice(idx_all, 150_000, replace=False)
                  if idx_all.size > 150_000 else idx_all)
        cu, cv_, cd = u_f[idx_cv], v_f[idx_cv], d_plane[idx_cv]
        Bc = spl.design(cu, cv_)

        cvr = cu.astype(int), cv_.astype(int)
        hold_masks = disk_fold_masks((h, w), gap_radii, k=CV_K, seed=RNG_SEED % 997)
        gap_folds = [m[cvr[1], cvr[0]] for m in hold_masks]
        block_px = max(8.0, 2.0 * vario["practical_range_px"])
        blk = block_cv_folds(cu, cv_, block_px, k=CV_K)
        block_folds = [blk == k for k in range(CV_K)]

        curves = {}
        for name, folds in (("gap", gap_folds), ("block", block_folds)):
            cv_pts = []
            for lam_try in LAM_GRID:
                errs = []
                for te in folds:
                    if te.sum() < 200 or (~te).sum() < 1000:
                        continue
                    s2 = PSpline2D((0, w - 1), (0, h - 1),
                                   n_seg_u=N_SEG[0], n_seg_v=N_SEG[1])
                    s2.fit(cu[~te], cv_[~te], cd[~te], lam_try, B=Bc[~te])
                    pr = Bc[te] @ s2.coef
                    errs.append(float(np.sqrt(((cd[te] - pr) ** 2).mean())))
                cv_pts.append(
                    (float(lam_try), float(np.mean(errs)) if errs else float("nan"))
                )
            curves[name] = cv_pts
        lam = min((t for t in curves["gap"] if np.isfinite(t[1])), key=lambda t: t[1])[0]
        lam_block = min((t for t in curves["block"] if np.isfinite(t[1])),
                        key=lambda t: t[1])[0]
        cv_record = {
            "design": "disks sized to the measured canopy-hole scale; inliers only",
            "gap_radii_px": gap_radii,
            "gap_radii_source": ("p50/p75/p90 of the distance from a non-ground "
                                 "pixel to the nearest ground observation"),
            "block_px": block_px,
            "variogram_practical_range_px": vario["practical_range_px"],
            "k": CV_K,
            "curve_lam_rmse_gap": curves["gap"],
            "curve_lam_rmse_block": curves["block"],
            "lam_selected": lam,
            "lam_block_design_would_pick": lam_block,
        }

        # --- robust fit -----------------------------------------------------
        spl, wts, irls_scale = fit_surface(u_f, v_f, d_plane, cand_new, spl, lam)
        s_field = spl.eval_grid(np.arange(w, dtype=float), np.arange(h, dtype=float)).ravel()
        edf = effective_dof(spl, spl.design(cu, cv_), np.ones(cu.size), lam)
        fit_scale_px = float(np.sqrt((h * w) / max(edf, 1e-9)))
        sigma_datum = sigma_datum_new

        moved = float(np.abs(cand_new.astype(np.int8) - cand.astype(np.int8)).mean())
        history.append({
            "iter": it, "sigma_datum_rdu": sigma_datum, "band_rdu": band,
            "candidate_fraction": float(cand_new.mean()), "lam": lam,
            "edf": edf, "fit_scale_px": fit_scale_px,
            "irls_scale_rdu": irls_scale,
            "candidate_churn": moved,
        })
        log(f"  outer {it}: sigma_datum={sigma_datum:.4e} band={band:.4e} "
            f"cand={cand_new.mean()*100:.1f}% lam={lam:.3g} edf={edf:.1f} "
            f"scale={fit_scale_px:.0f}px churn={moved*100:.2f}%")
        cand = cand_new
        if it and moved < 1e-3:
            break

    R["outer_loop"] = history
    R["cross_validation"] = cv_record
    R["variogram"] = vario

    # the threshold, re-read at the scale the fit actually resolves
    sig_fit, key_fit = sigma_at_scale(fit_scale_px)
    R["threshold_at_fit_scale"] = {
        "fit_scale_px": fit_scale_px, "nearest_window": key_fit,
        "local_planarity_p10_rdu": sig_fit,
        "ransac_threshold_used_rdu": sigma33,
        "note": ("the RANSAC seed threshold is read at win33; this row records "
                 "what the same curve says at the scale the converged spline "
                 "resolves, so the choice is auditable rather than assumed"),
    }

    # ------------------------------------------------------------ 6. heights
    dirs = ray_directions(h, w, intr)
    S = s_field.reshape(h, w)
    P_soil = surface_points(dirs, plane.normal, plane.offset, S)
    n_loc = local_normals(P_soil, plane.normal)
    delta = xyz - P_soil
    height = np.einsum("ijk,ijk->ij", delta, n_loc)
    height_planeaxis = (d_plane - s_field).reshape(h, w)

    tilt = np.degrees(np.arccos(np.clip(n_loc @ plane.normal, -1, 1)))
    R["surface_shape"] = {
        "local_tilt_from_plane_deg": {
            "p50": float(np.percentile(tilt, 50)),
            "p90": float(np.percentile(tilt, 90)),
            "max": float(tilt.max()),
        },
        "height_diff_local_vs_plane_normal_rdu": {
            "rms": float(np.sqrt(((height - height_planeaxis) ** 2).mean())),
            "p95_abs": float(np.percentile(np.abs(height - height_planeaxis), 95)),
        },
        "surface_departure_from_plane_rdu": {
            "rms": float(np.sqrt((S**2).mean())),
            "min": float(S.min()), "max": float(S.max()),
            "peak_to_peak": float(S.max() - S.min()),
        },
    }

    # ------------------------------------------------------------ 7. coverage
    ground = cand.reshape(h, w)
    support = ndi.distance_transform_edt(~ground).astype(np.float32)
    R["coverage_raw"] = {
        "observed_fraction": float(ground.mean()),
        "support_distance_px": {
            f"p{p}": float(np.percentile(support, p)) for p in (50, 90, 95, 99)
        },
        "max_support_distance_px": float(support.max()),
    }

    # ------------------------- 8. how wrong is the surface where it is guessed?
    holdout = holdout_curve(
        u_f, v_f, d_plane, cand, lam, h, w, sigma_datum, quick=args.quick
    )
    R["holdout_error_vs_support"] = holdout

    # validity: the surface is trusted out to the support distance at which the
    # measured gap-fill error first exceeds the ground band itself. Beyond that
    # the surface's own error is larger than the tolerance with which a pixel is
    # called ground, so a height there cannot distinguish ground from not-ground.
    # Observed from the hold-out curve, not assumed.
    max_support = holdout["support_px_where_error_exceeds_band"]
    height_sigma = np.interp(
        support,
        [b["support_px_lo"] for b in holdout["bins"]] or [0.0],
        [b["rms_rdu"] for b in holdout["bins"]] or [np.nan],
    ).astype(np.float32)
    valid = np.isfinite(height) & (support <= max_support)
    cov_class = np.where(ground, 0, np.where(support <= max_support, 1, 2)).astype(np.uint8)

    R["coverage"] = {
        "sigma_datum_rdu": sigma_datum,
        "max_trusted_support_px": max_support,
        "observed_fraction": float((cov_class == 0).mean()),
        "interpolated_fraction": float((cov_class == 1).mean()),
        "extrapolated_fraction": float((cov_class == 2).mean()),
        "valid_fraction": float(valid.mean()),
    }

    # --------------------------------------------------------- 9. fit quality
    r_in = (d_plane - s_field)[cand]
    r_all = (d_plane - s_field)
    plane_resid_in = d_plane[cand]
    R["fit_quality"] = {
        "inlier_fraction": float(cand.mean()),
        "n_inliers": int(cand.sum()),
        "inlier_residual_rms_rdu": float(np.sqrt((r_in**2).mean())),
        "inlier_residual_mad_rdu": float(1.4826 * np.median(np.abs(r_in - np.median(r_in)))),
        "inlier_residual_p95_abs_rdu": float(np.percentile(np.abs(r_in), 95)),
        "all_pixel_residual_rms_rdu": float(np.sqrt((r_all**2).mean())),
        "plane_only_inlier_residual_rms_rdu": float(np.sqrt((plane_resid_in**2).mean())),
        "improvement_over_plane": float(
            1 - np.sqrt((r_in**2).mean()) / np.sqrt((plane_resid_in**2).mean())
        ),
    }
    log(f"  fit: inliers {cand.mean()*100:.1f}%  rms {R['fit_quality']['inlier_residual_rms_rdu']:.4e} rdu "
        f"(plane-only {R['fit_quality']['plane_only_inlier_residual_rms_rdu']:.4e})")

    # ------------------------------------------------- 10. sensitivity sweeps
    R["sweeps"] = sweeps(u_f, v_f, d_plane, lam, h, w,
                         sigma_datum, quick=args.quick)

    # ----------------------------------------------------------- 11. artifacts
    np.save(prod_dir / "height_above_soil.npy", height.astype(np.float32))
    np.save(prod_dir / "height_above_soil_plane_normal.npy",
            height_planeaxis.astype(np.float32))
    np.save(prod_dir / "validity_mask.npy", valid)
    np.save(prod_dir / "ground_inliers.npy", ground)
    np.save(prod_dir / "support_distance_px.npy", support)
    np.save(prod_dir / "coverage_class.npy", cov_class)
    np.save(prod_dir / "soil_surface_depth.npy", P_soil[..., 2].astype(np.float32))
    np.save(prod_dir / "soil_surface_plane_offset.npy", S.astype(np.float32))
    np.save(prod_dir / "height_sigma.npy", height_sigma)

    R["height_stats_rdu"] = {
        "p01": float(np.percentile(height, 1)), "p50": float(np.percentile(height, 50)),
        "p90": float(np.percentile(height, 90)), "p99": float(np.percentile(height, 99)),
        "max": float(height.max()), "min": float(height.min()),
    }
    (res_dir / f"fit_report_{tag}.json").write_text(json.dumps(R, indent=2))
    write_manifest(prod_dir, tag, args.product, manifest, entry, intr, cloud, R)
    log(f"wrote {prod_dir} and results/fit_report_{tag}.json")


# ------------------------------------------------------------------ hold-out


def holdout_curve(u_f, v_f, d_plane, cand, lam, h, w, sigma_datum, quick=False):
    """Blank out ground observations in disks and measure how wrong the surface
    becomes as a function of distance from the nearest surviving observation.

    This is the honest answer to "how far can the surface be interpolated under
    a canopy", and it is measured on this scene rather than assumed.
    """
    rng = np.random.default_rng(RNG_SEED)
    radii = [20, 40, 80, 160] if not quick else [40, 120]
    out = {"radii_px": radii, "bins": []}
    cand_img = cand.reshape(h, w)
    per_r = {}
    for rad in radii:
        # scatter non-overlapping disks over ground-rich territory
        n_disk = max(4, int(0.15 * (h * w) / (np.pi * rad**2)))
        centres = []
        gy, gx = np.nonzero(cand_img)
        pick = rng.choice(gy.size, size=min(gy.size, n_disk * 40), replace=False)
        for i in pick:
            c = np.array([gy[i], gx[i]], float)
            if all(np.hypot(*(c - o)) > 2.5 * rad for o in centres):
                centres.append(c)
            if len(centres) >= n_disk:
                break
        hole = np.zeros((h, w), bool)
        yy, xx = np.mgrid[0:h, 0:w]
        for c in centres:
            hole |= (yy - c[0]) ** 2 + (xx - c[1]) ** 2 <= rad**2
        train = cand & ~hole.ravel()
        test = cand & hole.ravel()
        if test.sum() < 500:
            continue
        s2 = PSpline2D((0, w - 1), (0, h - 1), n_seg_u=N_SEG[0], n_seg_v=N_SEG[1])
        s2.fit_robust(u_f[train], v_f[train], d_plane[train], lam)
        pred = s2.eval_grid(
            np.arange(w, dtype=float), np.arange(h, dtype=float)
        ).ravel()
        err = d_plane[test] - pred[test]
        dist = ndi.distance_transform_edt(~train.reshape(h, w)).ravel()[test]
        per_r[rad] = (dist, err, len(centres))

    bins = np.array([0, 5, 10, 20, 40, 60, 80, 120, 160, 240])
    all_d = np.concatenate([v[0] for v in per_r.values()]) if per_r else np.zeros(0)
    all_e = np.concatenate([v[1] for v in per_r.values()]) if per_r else np.zeros(0)
    for lo, hi in zip(bins[:-1], bins[1:]):
        m = (all_d >= lo) & (all_d < hi)
        if m.sum() < 200:
            continue
        out["bins"].append({
            "support_px_lo": int(lo), "support_px_hi": int(hi), "n": int(m.sum()),
            "rms_rdu": float(np.sqrt((all_e[m] ** 2).mean())),
            "mae_rdu": float(np.abs(all_e[m]).mean()),
            "bias_rdu": float(all_e[m].mean()),
            "p95_abs_rdu": float(np.percentile(np.abs(all_e[m]), 95)),
        })
    out["n_disks_per_radius"] = {str(k): v[2] for k, v in per_r.items()}

    # The trust distance: the support distance at which the *measured* gap-fill
    # error first exceeds the datum's own roughness. Past that point the surface
    # is no longer as good as the thing it is a surface of, so it is reported as
    # extrapolated rather than trusted. Observed, not assumed.
    out["sigma_datum_rdu"] = float(sigma_datum)
    band = BAND_SIGMA * sigma_datum
    out["ground_band_rdu"] = float(band)
    for key, ref in (("support_px_where_error_exceeds_sigma_datum", sigma_datum),
                     ("support_px_where_error_exceeds_band", band)):
        limit = None
        for b in out["bins"]:
            if b["rms_rdu"] > ref:
                limit = float(b["support_px_lo"])
                break
        if limit is None:
            limit = float(out["bins"][-1]["support_px_hi"]) if out["bins"] else 0.0
            out.setdefault("notes", []).append(
                f"gap-fill error never exceeded {key.split('exceeds_')[1]} inside "
                f"the radii tested; that trust distance is a lower bound set by "
                f"the largest disk measured"
            )
        out[key] = limit
    return out


# ------------------------------------------------------------------- sweeps


def sweeps(u_f, v_f, d_plane, lam, h, w, sigma_datum, quick=False):
    """The two conventions in the pipeline, swept: the band multiplier and the
    spline basis size. A convention with a sweep is a bounded choice; without
    one it is a hidden bias."""
    out = {"band_sigma": [], "basis": []}
    grid_u = np.arange(w, dtype=float)
    grid_v = np.arange(h, dtype=float)
    for k in (BAND_SIGMA_SWEEP if not quick else (2.0, 5.0)):
        # start each variant from the plane, converge three inner rounds
        s_field = np.zeros_like(d_plane)
        for _ in range(3):
            cand = np.abs(d_plane - s_field) < k * sigma_datum
            s = PSpline2D((0, w - 1), (0, h - 1), n_seg_u=N_SEG[0], n_seg_v=N_SEG[1])
            s.fit_robust(u_f[cand], v_f[cand], d_plane[cand], lam)
            s_field = s.eval_grid(grid_u, grid_v).ravel()
        r = (d_plane - s_field)[cand]
        out["band_sigma"].append({
            "k": k, "inlier_fraction": float(cand.mean()),
            "inlier_rms_rdu": float(np.sqrt((r**2).mean())),
            "surface_rms_vs_plane_rdu": float(np.sqrt((s_field**2).mean())),
            "_field": s_field,
        })
    base = [d for d in out["band_sigma"] if d["k"] == BAND_SIGMA]
    base_field = base[0]["_field"] if base else out["band_sigma"][0]["_field"]
    for d in out["band_sigma"]:
        f = d.pop("_field")
        d["surface_rms_diff_from_k3_rdu"] = float(np.sqrt(((f - base_field) ** 2).mean()))

    for nseg in (N_SEG, N_SEG_ALT):
        s_field = np.zeros_like(d_plane)
        for _ in range(3):
            cand = np.abs(d_plane - s_field) < BAND_SIGMA * sigma_datum
            s = PSpline2D((0, w - 1), (0, h - 1), n_seg_u=nseg[0], n_seg_v=nseg[1])
            s.fit_robust(u_f[cand], v_f[cand], d_plane[cand], lam)
            s_field = s.eval_grid(grid_u, grid_v).ravel()
        out["basis"].append({
            "n_seg_uv": list(nseg),
            "inlier_fraction": float(cand.mean()),
            "inlier_rms_rdu": float(np.sqrt(((d_plane - s_field)[cand] ** 2).mean())),
            "surface_rms_diff_from_default_rdu": float(
                np.sqrt(((s_field - base_field) ** 2).mean())
            ),
        })
    return out


# ----------------------------------------------------------------- manifest


def write_manifest(prod_dir, tag, product, a1_manifest, entry, intr, cloud, R):
    m = {
        "chunk": "A2",
        "scale_confidence": "scale_free",
        "units": "rdu (relative depth units; 1 rdu = median scene depth of the "
                 "source raster). No metric claim. Do not convert to metres.",
        "DATUM": (
            "THE DATUM IS THE STRAW MULCH SURFACE, NOT BARE SOIL. Bare soil is "
            "largely invisible in this scene; what the depth observes, and what "
            "this surface is fitted to, is the top of the mulch. Every height "
            "here is height above straw and is offset from height above soil by "
            "the straw depth, which is unmeasured and unobservable from a single "
            "overhead photograph. An arm targeting the soil must add that offset."
        ),
        "source": {
            "a1_product": product,
            "a1_manifest": "chunks/A1/products/MANIFEST.json",
            "depth": entry["depth"],
            "model": a1_manifest["model"],
            "camera": intr.as_dict(),
            "camera_usable_per_A1": entry["camera_usable"],
            "camera_note": entry["why"],
            "rdu_normaliser_depth_units": cloud.normaliser,
        },
        "grid": {"shape_hw": list(np.load(prod_dir / "validity_mask.npy").shape),
                 "aligned_to": "the A1 depth raster; map to plants.jpeg "
                               "(3000x4000) by bilinear resampling of the raster "
                               "coordinates, image_xy = raster_xy * 3000/W"},
        "rasters": {
            "height_above_soil.npy": "float32 rdu, height above the fitted straw "
                                     "surface along the LOCAL surface normal; "
                                     "positive = toward the camera / above datum",
            "height_above_soil_plane_normal.npy": "same but measured along the "
                                     "global RANSAC plane normal (reference)",
            "validity_mask.npy": "bool; the surface is supported by observation "
                                 "within the measured trust distance",
            "coverage_class.npy": "uint8 0=observed 1=interpolated 2=extrapolated",
            "support_distance_px.npy": "float32 px to the nearest ground inlier",
            "ground_inliers.npy": "bool; pixels used to fit the surface",
            "soil_surface_depth.npy": "float32 rdu z-depth of the datum along each ray",
            "soil_surface_plane_offset.npy": "float32 rdu; datum height relative "
                                             "to the RANSAC plane",
            "height_sigma.npy": "float32 rdu; 1-sigma uncertainty of the datum "
                                "under each pixel, read off the MEASURED "
                                "gap-fill error-vs-support curve. Use this, not "
                                "the height alone, for any go/no-go decision.",
        },
        "key_numbers": {
            "inlier_fraction": R["fit_quality"]["inlier_fraction"],
            "inlier_residual_rms_rdu": R["fit_quality"]["inlier_residual_rms_rdu"],
            "datum_roughness_sigma_rdu": R["coverage"]["sigma_datum_rdu"],
            "ransac_threshold_rdu": R["ransac"]["threshold_rdu"],
            "lam": R["cross_validation"]["lam_selected"],
            "fit_scale_px": R["outer_loop"][-1]["fit_scale_px"],
            "observed_fraction": R["coverage"]["observed_fraction"],
            "interpolated_fraction": R["coverage"]["interpolated_fraction"],
            "extrapolated_fraction": R["coverage"]["extrapolated_fraction"],
            "max_trusted_support_px": R["coverage"]["max_trusted_support_px"],
        },
        "report": f"chunks/A2/results/fit_report_{tag}.json",
    }
    (prod_dir / "A2_MANIFEST.json").write_text(json.dumps(m, indent=2))


if __name__ == "__main__":
    main()
