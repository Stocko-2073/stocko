"""A1b step 2 — refine `f` by scene self-consistency, and report what happened.

The roadmap's instruction:

  > the straw surface is locally planar, so back-project the A1 float depth
  > across a range of candidate `f` and choose the value minimising planarity
  > residual over the soil band.

This script does exactly that, over a fine grid of `f`, on **both** A1 depth
products (so `process_res` is fixed within each curve, as A1 required), using
A2's own `ground_inliers` as the soil band. It reports the full curve under
three different normalisations, because the choice of normalisation turns out to
decide the answer — which is the finding.

It also runs the control the roadmap did not ask for and that settles the
matter: the same estimator on a **synthetic** scene whose focal length is known.
If the estimator cannot recover a focal length it was handed, it cannot recover
DA3's either, and the degeneracy is not about DA3.

    chunks/A1/.venv/bin/python chunks/A1b/refine_focal.py
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from a1b_common import (A1, A2, DA3_F_RES504_FX, F_INITIAL, RESULTS,  # noqa: E402
                        SWEEP_F, depth_product_dir, equiv_mm_from_f_px)
from depth_to_cloud import load_depth_product  # noqa: E402

# ---------------------------------------------------------------- the products
# Both A1 products, each with the soil band A2 fitted on that same product, and
# each with the focal length DA3's own head reported for that run. Fixing
# `process_res` per curve is A1's instruction: refining `f` against a depth
# field produced under a different internal `f` is not self-consistent.
PRODUCTS = {
    "primary_raster": {
        "depth": "da3nested-giant-large_res1344",
        "ground": A2 / "products" / "ground_inliers.npy",
        "da3_internal_f_native": 2939.153035481771,
        "process_res": 1344,
        "note": "the shipped A2/A4/A5 raster. DA3's own head is physically "
                "impossible here (fx/fy = 0.543), so A1 replaced it with the "
                "res-504 camera rescaled.",
        "win": 33,
    },
    "primary_geometry": {
        "depth": "da3nested-giant-large_res504",
        "ground": A2 / "products_primary_geometry" / "ground_inliers.npy",
        "da3_internal_f_native": DA3_F_RES504_FX,
        "process_res": 504,
        "note": "the camera head is physically consistent at this resolution.",
        "win": 17,
    },
}

#: A wide, log-spaced grid so an interior optimum could not be missed, with the
#: sweep values and the two candidates forced in.
F_GRID = np.unique(np.round(np.concatenate([
    np.geomspace(400.0, 60000.0, 61),
    np.array(SWEEP_F, dtype=float),
    np.array([F_INITIAL, DA3_F_RES504_FX, 2939.153035481771]),
]), 3))


def log(m):
    print(f"[{time.strftime('%H:%M:%S')}] {m}", flush=True)


# --------------------------------------------------------------------------
# The estimator
# --------------------------------------------------------------------------


def patch_stats(depth_rdu, band, f_native, win, stride=None, min_pts=None,
                cx=None, cy=None):
    """Local-plane statistics over every window of the soil band.

    Returns three arrays, one value per patch:

    ``rms``      RMS point-to-plane distance, in rdu. The literal reading of
                 "planarity residual".
    ``surfvar``  lambda3 / (lambda1+lambda2+lambda3) — the standard
                 scale-invariant "surface variation" of a point set.
    ``slope``    sqrt(lambda3 / (lambda1+lambda2)) — the residual expressed as a
                 fraction of the patch's own in-plane extent, i.e. a roughness
                 *angle*, which is what makes it dimensionless.
    """
    h, w = depth_rdu.shape
    f = float(f_native) * w / 3000.0
    cx = (w - 1) / 2.0 if cx is None else cx
    cy = (h - 1) / 2.0 if cy is None else cy
    stride = stride or win
    min_pts = min_pts or max(12, win * win // 4)
    v, u = np.mgrid[0:h, 0:w].astype(np.float64)
    X = (u - cx) * depth_rdu / f
    Y = (v - cy) * depth_rdu / f
    rms, sv, slope, tilt = [], [], [], []
    for r0 in range(0, h - win + 1, stride):
        for c0 in range(0, w - win + 1, stride):
            m = band[r0:r0 + win, c0:c0 + win]
            k = int(m.sum())
            if k < min_pts:
                continue
            P = np.stack([X[r0:r0 + win, c0:c0 + win][m],
                          Y[r0:r0 + win, c0:c0 + win][m],
                          depth_rdu[r0:r0 + win, c0:c0 + win][m]], axis=1)
            P = P - P.mean(0)
            U_, s_, Vt = np.linalg.svd(P, full_matrices=False)
            ev = np.sort((s_ ** 2) / k)[::-1]
            rms.append(np.sqrt(max(ev[2], 0.0)))
            sv.append(ev[2] / max(ev.sum(), 1e-300))
            slope.append(np.sqrt(max(ev[2], 0.0) / max(ev[0] + ev[1], 1e-300)))
            n = Vt[2]
            tilt.append(np.degrees(np.arccos(min(1.0, abs(n[2])))))
    return (np.array(rms), np.array(sv), np.array(slope), np.array(tilt))


def curve(depth_rdu, band, win, f_grid, seed=20260901, n_boot=200):
    """The refinement curve, with a bootstrap band over patches."""
    rng = np.random.default_rng(seed)
    rows = []
    boot_idx = None
    for f in f_grid:
        rms, sv, slope, tilt = patch_stats(depth_rdu, band, f, win)
        if boot_idx is None:
            boot_idx = rng.integers(0, rms.size, size=(n_boot, rms.size))
        agg = np.sqrt(np.mean(rms ** 2))
        # the same bootstrap resample of patches at every f, so the band
        # measures how much of the curve's shape is patch sampling
        b = np.sqrt(np.mean(rms[boot_idx] ** 2, axis=1))
        rows.append({
            "f_native_px": float(f),
            "f_equiv_mm": float(equiv_mm_from_f_px(f)),
            "n_patches": int(rms.size),
            "planarity_rms_rdu": float(agg),
            "planarity_rms_rdu_boot_p05": float(np.percentile(b, 5)),
            "planarity_rms_rdu_boot_p95": float(np.percentile(b, 95)),
            "planarity_median_rdu": float(np.median(rms)),
            "surface_variation_median": float(np.median(sv)),
            "roughness_slope_median": float(np.median(slope)),
            "patch_tilt_median_deg": float(np.median(tilt)),
        })
    return rows


def extremum(rows, key, kind="min"):
    v = np.array([r[key] for r in rows])
    f = np.array([r["f_native_px"] for r in rows])
    i = int(np.argmin(v) if kind == "min" else np.argmax(v))
    interior = 0 < i < len(v) - 1
    return {"f_native_px": float(f[i]), "value": float(v[i]),
            "at_grid_edge": not interior,
            "grid_span_px": [float(f[0]), float(f[-1])],
            "monotone": bool(np.all(np.diff(v) < 0) or np.all(np.diff(v) > 0)),
            "relative_depth_of_extremum": float(
                abs(v[i] - (v.min() if kind == "max" else v.max()))
                / max(abs(v[i]), 1e-300)),
            }


# --------------------------------------------------------------------------
# Controls
# --------------------------------------------------------------------------


def linear_map_check(depth_rdu, f0, f1, cx=None, cy=None):
    """The algebra in `a1b_common`, checked numerically to machine precision:
    the cloud at f1 is exactly diag(s,s,1) times the cloud at f0."""
    h, w = depth_rdu.shape
    cx = (w - 1) / 2.0 if cx is None else cx
    cy = (h - 1) / 2.0 if cy is None else cy
    v, u = np.mgrid[0:h, 0:w].astype(np.float64)
    out = {}
    for nm, f in (("f0", f0), ("f1", f1)):
        fp = f * w / 3000.0
        out[nm] = np.stack([(u - cx) * depth_rdu / fp,
                            (v - cy) * depth_rdu / fp, depth_rdu], axis=-1)
    s = (f1 / f0)
    pred = out["f0"] * np.array([1 / s, 1 / s, 1.0])
    err = np.abs(pred - out["f1"]).max()
    scale = np.abs(out["f1"]).max()
    return {"f0": f0, "f1": f1, "max_abs_error": float(err),
            "max_abs_coordinate": float(scale),
            "relative_error": float(err / scale)}


def synthetic_control(f_true=3005.0, h=504, w=378, seed=7, roughness=0.02,
                      f_grid=None, tilt=(0.25, 0.40), undulation=1.0,
                      undulation_scale=1.0):
    """Render a rough, tilted, locally-planar surface through a *known* camera,
    then hand the depth map to the same estimator and ask it for `f`.

    This is the control that decides whether the refinement has any power at
    all, independent of DA3. The surface is built the way the straw is described
    — locally planar, globally undulating — and the depth map is exact, with no
    model in the loop.
    """
    rng = np.random.default_rng(seed)
    f = f_true * w / 3000.0
    cx, cy = (w - 1) / 2.0, (h - 1) / 2.0
    v, u = np.mgrid[0:h, 0:w].astype(np.float64)
    dx, dy = (u - cx) / f, (v - cy) / f

    # a tilted plane, plus smooth undulation, plus fine roughness — the same
    # three components A2 measured on the real datum
    n = np.array([tilt[0], tilt[1], -1.0])
    n = n / np.linalg.norm(n)
    D = -1.0                                  # plane at ~1 rdu in front

    def bump(x, y):
        s = 0.0
        for k, amp in ((1.5 * undulation_scale, 0.06 * undulation),
                       (3.0 * undulation_scale, 0.03 * undulation),
                       (6.0 * undulation_scale, 0.012 * undulation)):
            ph = rng.uniform(0, 2 * np.pi, 2)
            s = s + amp * np.sin(k * np.pi * x + ph[0]) * np.sin(k * np.pi * y + ph[1])
        return s

    xg = (u / (w - 1)) * 2 - 1
    yg = (v / (h - 1)) * 2 - 1
    offs = bump(xg, yg) + roughness * rng.standard_normal((h, w))
    # smooth the fine roughness a little so it has a correlation length, like straw
    from scipy import ndimage
    offs = ndimage.gaussian_filter(offs, 1.0)

    denom = (n[0] * dx + n[1] * dy + n[2])
    z = D / denom                                     # depth of the plane
    z = z * (1.0 + offs * 0.05)                       # displace along the ray
    z = z / np.median(z)                              # rdu, as everywhere else
    band = np.ones((h, w), bool)
    grid = F_GRID if f_grid is None else f_grid
    rows = curve(z, band, win=17, f_grid=grid, n_boot=100)
    return {
        "f_true_native_px": f_true,
        "surface": "tilted plane + 3-octave undulation + correlated roughness, "
                   "displaced along the ray; exact depth, no model",
        "params": {"tilt": list(tilt), "undulation": undulation,
                   "undulation_scale": undulation_scale, "roughness": roughness,
                   "seed": seed},
        "curve": rows,
        "argmin_planarity_rms": extremum(rows, "planarity_rms_rdu", "min"),
        "argmin_surface_variation": extremum(rows, "surface_variation_median", "min"),
        "argmax_surface_variation": extremum(rows, "surface_variation_median", "max"),
        "argmin_roughness_slope": extremum(rows, "roughness_slope_median", "min"),
    }


def exact_plane_control(f_grid=None):
    """The sharpest form of the degeneracy: an *exactly* planar depth map.

    Its planarity residual is zero at every focal length. Nothing to minimise.
    """
    h, w = 200, 150
    cx, cy = (w - 1) / 2.0, (h - 1) / 2.0
    v, u = np.mgrid[0:h, 0:w].astype(np.float64)
    f = 3005.0 * w / 3000.0
    n = np.array([0.3, 0.5, -1.0]) / np.linalg.norm([0.3, 0.5, -1.0])
    z = -1.0 / (n[0] * (u - cx) / f + n[1] * (v - cy) / f + n[2])
    z = z / np.median(z)
    band = np.ones((h, w), bool)
    out = []
    for ff in (500.0, 1502.0, 3005.0, 4453.0, 20000.0):
        rms, sv, slope, _ = patch_stats(z, band, ff, win=25)
        out.append({"f_native_px": ff,
                    "planarity_rms_rdu": float(np.sqrt(np.mean(rms ** 2))),
                    "surface_variation_median": float(np.median(sv)),
                    "roughness_slope_median": float(np.median(slope))})
    return {"note": "an exactly planar surface: residual is zero at every f, "
                    "to floating-point. Planes are preserved by diag(s,s,1).",
            "rows": out}


# --------------------------------------------------------------------------


def main():
    RESULTS.mkdir(parents=True, exist_ok=True)
    out = {
        "chunk": "A1b",
        "what": "planarity refinement of the assumed focal length",
        "scale_confidence": "scale_free",
        "units": "rdu (1 rdu = median scene depth of the raster in question)",
        "soil_band": "A2 `ground_inliers.npy` for the same depth product",
        "f_grid_native_px": [float(x) for x in F_GRID],
        "products": {},
    }

    for name, cfg in PRODUCTS.items():
        log(f"--- {name} ---")
        prod = load_depth_product(depth_product_dir(name))
        d = np.asarray(prod.depth, dtype=np.float64)
        d = d / np.median(d[np.isfinite(d) & (d > 0)])
        band = np.load(cfg["ground"])
        assert band.shape == d.shape, (band.shape, d.shape)
        rows = curve(d, band, cfg["win"], F_GRID)
        log(f"  {rows[0]['n_patches']} patches at win {cfg['win']}, "
            f"{len(rows)} focal lengths")
        out["products"][name] = {
            "depth_product": cfg["depth"],
            "process_res": cfg["process_res"],
            "da3_internal_f_native_px": cfg["da3_internal_f_native"],
            "note": cfg["note"],
            "soil_band_fraction": float(band.mean()),
            "patch_window_px": cfg["win"],
            "curve": rows,
            "argmin_planarity_rms": extremum(rows, "planarity_rms_rdu", "min"),
            "argmin_planarity_median": extremum(rows, "planarity_median_rdu", "min"),
            "argmin_surface_variation": extremum(rows, "surface_variation_median", "min"),
            "argmax_surface_variation": extremum(rows, "surface_variation_median", "max"),
            "argmin_roughness_slope": extremum(rows, "roughness_slope_median", "min"),
            "argmax_roughness_slope": extremum(rows, "roughness_slope_median", "max"),
            "linear_map_check": linear_map_check(d, 3005.0, 4453.214615110367),
        }

    log("controls")
    out["control_exact_plane"] = exact_plane_control()
    out["control_synthetic_known_f"] = {
        str(int(ft)): synthetic_control(f_true=ft) for ft in (1502.0, 3005.0, 6009.0)
    }

    # --- the one feature of the curve that is not flat ----------------------
    # The scale-invariant normalisations have an interior MAXIMUM. On the
    # synthetic control that maximum sits at a fixed multiple of the true focal
    # length, which looks like an estimator until the multiple is measured on a
    # second surface. It is a property of the surface's roughness spectrum, not
    # of the camera.
    log("peak analysis")
    peaks = {}
    variants = [
        dict(),
        dict(seed=21),
        dict(roughness=0.06), dict(roughness=0.006),
        dict(undulation=3.0), dict(undulation=0.3),
        dict(undulation_scale=2.0), dict(undulation_scale=0.5),
        dict(tilt=(0.05, 0.08)), dict(tilt=(0.6, 0.9)),
    ]
    for kw in variants:
        key = ",".join(f"{k}={v}" for k, v in kw.items()) or "baseline"
        r = synthetic_control(f_true=3005.0, **kw)
        peaks[key] = {
            "f_true": 3005.0, "params": r["params"],
            "argmax_surface_variation_f": r["argmax_surface_variation"]["f_native_px"],
            "ratio_to_f_true":
                r["argmax_surface_variation"]["f_native_px"] / 3005.0,
        }
    ratios = [v["ratio_to_f_true"] for v in peaks.values()]
    out["surface_variation_peak_analysis"] = {
        "what": "location of the interior maximum of the scale-invariant "
                "planarity measure, relative to the true focal length",
        "on_synthetic_surfaces_with_known_f": peaks,
        "ratio_min": float(min(ratios)), "ratio_max": float(max(ratios)),
        "ratio_spread_over_mean":
            float((max(ratios) - min(ratios)) / np.mean(ratios)),
        "observed_peak_primary_raster":
            out["products"]["primary_raster"]["argmax_surface_variation"]["f_native_px"],
        "observed_peak_primary_geometry":
            out["products"]["primary_geometry"]["argmax_surface_variation"]["f_native_px"],
        "reading": (
            "The peak location is proportional to the true focal length for a "
            "GIVEN surface, so it would be an estimator if the constant of "
            "proportionality were known. Measured across synthetic surfaces that "
            "differ in tilt, undulation and roughness, the constant itself moves by "
            "the spread recorded above — it is a property of the surface, not of the "
            "camera. Reading a focal length off the observed peak would therefore "
            "be assuming a roughness for the straw and calling the result a "
            "measurement, which is precisely the move R1 exists to forbid."),
    }

    # the summary statement, computed rather than asserted
    ver = {}
    for name, p in out["products"].items():
        ver[name] = {
            "planarity_rms_is_monotone_in_f": p["argmin_planarity_rms"]["monotone"],
            "planarity_rms_argmin_at_grid_edge": p["argmin_planarity_rms"]["at_grid_edge"],
            "surface_variation_argmin_at_grid_edge":
                p["argmin_surface_variation"]["at_grid_edge"],
            "surface_variation_has_interior_MAXIMUM_at_f":
                p["argmax_surface_variation"]["f_native_px"],
        }
    ver["synthetic_recovery"] = {
        k: {"f_true": float(k),
            "argmin_planarity_rms_f": v["argmin_planarity_rms"]["f_native_px"],
            "argmin_surface_variation_f": v["argmin_surface_variation"]["f_native_px"],
            "recovered": bool(abs(v["argmin_planarity_rms"]["f_native_px"] - float(k))
                              / float(k) < 0.25)}
        for k, v in out["control_synthetic_known_f"].items()
    }
    out["verdict"] = ver

    p = RESULTS / "focal_refinement.json"
    p.write_text(json.dumps(out, indent=1))
    log(f"wrote {p}")
    print(json.dumps(ver, indent=1))


if __name__ == "__main__":
    main()
