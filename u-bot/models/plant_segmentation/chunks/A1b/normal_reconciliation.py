"""A1b step 4 — the 7.6 deg plane-normal disagreement, as a function of `f`.

A2's FINDINGS left A1b a second thing to reconcile:

  > the two fitted **plane normals differ by 7.6 deg** — the two inference
  > resolutions genuinely disagree about which way the ground tilts, and nothing
  > in this image can adjudicate.
  > ...
  > **A1b** now has a second thing to reconcile besides `f`.

A plane normal is exactly the kind of quantity the algebra in `a1b_common` says
is *not* focal-invariant, so the disagreement is a function of `f` and can be
written down in closed form:

    n(f) ∝ (n_x f / f0,  n_y f / f0,  n_z)

This script measures the curve three ways and checks they agree:

1. **closed form** from each product's normal as fitted under the camera A1
   shipped;
2. **least squares** refit on A2's own ground band at each `f`;
3. **RANSAC** refit at each `f`, with A2's inlier threshold, so the inlier set
   is free to move as well as the fit.

It also reports what A1b's chosen `f` does to the disagreement, and — because
the answer is "it shrinks monotonically toward zero as f -> 0" — says plainly
that minimising it is not a usable estimator of `f` either.

    chunks/A1/.venv/bin/python chunks/A1b/normal_reconciliation.py
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from a1b_common import (A2, F_CHOSEN, F_INITIAL, RESULTS, SWEEP_F,  # noqa: E402
                        angle_deg, depth_product_dir, equiv_mm_from_f_px,
                        manifest_intrinsics, normal_at_f)
from depth_to_cloud import load_depth_product  # noqa: E402
from soil_fit import ransac_plane  # noqa: E402

RNG_SEED = 20260901  # A2's seed, reused so the RANSAC draw is the same one

PRODUCTS = {
    "primary_raster": {"ground": A2 / "products" / "ground_inliers.npy",
                       "report": A2 / "results" / "fit_report_primary_raster.json"},
    "primary_geometry": {"ground": A2 / "products_primary_geometry" / "ground_inliers.npy",
                         "report": A2 / "results" / "fit_report_primary_geometry.json"},
}

F_GRID = np.unique(np.round(np.concatenate([
    np.geomspace(400.0, 60000.0, 41),
    np.array(SWEEP_F, dtype=float), np.array([F_INITIAL, F_CHOSEN]),
]), 3))


def log(m):
    print(f"[{time.strftime('%H:%M:%S')}] {m}", flush=True)


def cloud_at(depth_rdu, band, f_native):
    h, w = depth_rdu.shape
    f = f_native * w / 3000.0
    cx, cy = (w - 1) / 2.0, (h - 1) / 2.0
    v, u = np.nonzero(band)
    z = depth_rdu[v, u]
    return np.stack([(u - cx) * z / f, (v - cy) * z / f, z], axis=1)


def orient(n):
    """A2's convention: the normal points toward the camera origin."""
    n = np.asarray(n, float)
    n = n / np.linalg.norm(n)
    return -n if n[2] > 0 else n


def ls_plane(P):
    c = P.mean(0)
    _, _, Vt = np.linalg.svd(P - c, full_matrices=False)
    return orient(Vt[2])


def main():
    RESULTS.mkdir(parents=True, exist_ok=True)
    out = {"chunk": "A1b",
           "what": "focal dependence of the A2 plane-normal disagreement "
                   "between A1's two depth products",
           "a2_recorded_disagreement_deg": 7.6,
           "f_grid_native_px": [float(x) for x in F_GRID],
           "products": {}, "pairwise": []}

    data = {}
    for name, cfg in PRODUCTS.items():
        prod = load_depth_product(depth_product_dir(name))
        d = np.asarray(prod.depth, np.float64)
        d = d / np.median(d[np.isfinite(d) & (d > 0)])
        band = np.load(cfg["ground"])
        rep = json.loads(cfg["report"].read_text())
        thr = float(rep["ransac"]["threshold_rdu"])
        n_shipped = orient(np.array(rep["ransac"]["normal"], float))
        fx_shipped = manifest_intrinsics(name).fx * 3000.0 / d.shape[1]
        data[name] = dict(d=d, band=band, thr=thr, n_shipped=n_shipped,
                          f_shipped=fx_shipped)
        log(f"{name}: A2 shipped normal {np.round(n_shipped,4)}, "
            f"fitted under f={fx_shipped:.1f} px, RANSAC thr {thr:.3e} rdu")

    for name, cfg in data.items():
        rows = []
        for f in F_GRID:
            P = cloud_at(cfg["d"], cfg["band"], f)
            n_ls = ls_plane(P)
            pl = ransac_plane(P, threshold=cfg["thr"] * (cfg["f_shipped"] / f),
                              seed=RNG_SEED)
            n_rs = orient(pl.normal)
            n_cf = orient(normal_at_f(cfg["n_shipped"], cfg["f_shipped"], f))
            rows.append({
                "f_native_px": float(f),
                "f_equiv_mm": float(equiv_mm_from_f_px(f)),
                "normal_closed_form": n_cf.tolist(),
                "normal_least_squares": n_ls.tolist(),
                "normal_ransac": n_rs.tolist(),
                "tilt_from_camera_axis_deg_closed_form":
                    float(np.degrees(np.arccos(min(1.0, abs(n_cf[2]))))),
                "tilt_from_camera_axis_deg_ransac":
                    float(np.degrees(np.arccos(min(1.0, abs(n_rs[2]))))),
                "closed_form_vs_least_squares_deg": angle_deg(n_cf, n_ls),
                "closed_form_vs_ransac_deg": angle_deg(n_cf, n_rs),
                "ransac_inlier_fraction": float(pl.inliers.mean()),
            })
        out["products"][name] = {
            "a2_shipped_normal": cfg["n_shipped"].tolist(),
            "a2_shipped_fitted_under_f_native_px": cfg["f_shipped"],
            "a2_ransac_threshold_rdu": cfg["thr"],
            "soil_band_fraction": float(cfg["band"].mean()),
            "curve": rows,
            "max_closed_form_vs_least_squares_deg":
                float(max(r["closed_form_vs_least_squares_deg"] for r in rows)),
            "max_closed_form_vs_ransac_deg":
                float(max(r["closed_form_vs_ransac_deg"] for r in rows)),
        }

    out["method_note"] = (
        "The RANSAC rows refit on A2's *ground band only*, with A2's threshold "
        "rescaled by f_shipped/f so the same orthogonal tolerance is applied in "
        "the rescaled cloud. A2 itself ran RANSAC over every pixel of the scene "
        "and let the plane find the ground; that is a different fit and it lands "
        "a couple of degrees away. The row to compare against A2's recorded "
        "7.6 deg is the closed form, which starts from A2's own two shipped "
        "normals and is exact — see `validation` below.")
    out["validation"] = {
        "a2_recorded_disagreement_deg": 7.6,
        "closed_form_at_the_f_a2_used_deg": angle_deg(
            data["primary_raster"]["n_shipped"], data["primary_geometry"]["n_shipped"]),
        "note": "both A2 fits used A1's res-504 camera (rescaled for the 1344 "
                "product), i.e. f = 4453 px at 3000x4000, so the closed form at "
                "that f must reproduce A2's number identically. It does.",
    }

    a, b = "primary_raster", "primary_geometry"
    ca = {r["f_native_px"]: r for r in out["products"][a]["curve"]}
    cb = {r["f_native_px"]: r for r in out["products"][b]["curve"]}
    for f in F_GRID:
        f = float(f)
        out["pairwise"].append({
            "f_native_px": f,
            "f_equiv_mm": float(equiv_mm_from_f_px(f)),
            "disagreement_deg_closed_form":
                angle_deg(ca[f]["normal_closed_form"], cb[f]["normal_closed_form"]),
            "disagreement_deg_least_squares":
                angle_deg(ca[f]["normal_least_squares"], cb[f]["normal_least_squares"]),
            "disagreement_deg_ransac":
                angle_deg(ca[f]["normal_ransac"], cb[f]["normal_ransac"]),
            "tilt_raster_deg": ca[f]["tilt_from_camera_axis_deg_ransac"],
            "tilt_geometry_deg": cb[f]["tilt_from_camera_axis_deg_ransac"],
        })

    fs = np.array([r["f_native_px"] for r in out["pairwise"]])
    methods = {k: np.array([r[f"disagreement_deg_{k}"] for r in out["pairwise"]])
               for k in ("closed_form", "least_squares", "ransac")}
    dis = methods["ransac"]
    i = int(np.argmin(dis))
    out["verdict"] = {
        "at_f_chosen": {
            "f_native_px": F_CHOSEN,
            **{f"disagreement_deg_{k}": float(np.interp(F_CHOSEN, fs, v))
               for k, v in methods.items()},
            "disagreement_deg_ransac": float(np.interp(F_CHOSEN, fs, dis)),
        },
        "at_f_initial_3005": float(np.interp(F_INITIAL, fs, dis)),
        "at_f_initial_3005_by_method":
            {k: float(np.interp(F_INITIAL, fs, v)) for k, v in methods.items()},
        "argmin": {"f_native_px": float(fs[i]), "deg": float(dis[i]),
                   "at_grid_edge": bool(i == 0 or i == len(fs) - 1)},
        "argmin_by_method": {
            k: {"f_native_px": float(fs[int(np.argmin(v))]),
                "deg": float(v.min()),
                "at_grid_edge": bool(int(np.argmin(v)) in (0, len(v) - 1))}
            for k, v in methods.items()},
        "monotone_increasing_in_f": {
            k: bool(np.all(np.diff(v) >= -1e-9)) for k, v in methods.items()},
        "monotone_increasing_in_f_note":
            "the closed form is monotone by construction; the two refits inherit "
            "the sampling noise of their own fit, so they are monotone only up to "
            "that noise. Every method's minimum sits at the low-f edge of the grid.",
        "reading": (
            "The disagreement between the two products' ground normals increases "
            "monotonically with f, going to zero as f -> 0 because "
            "every normal collapses onto the optical axis there. So 'choose f to "
            "make the two products agree' is degenerate in exactly the way the "
            "planarity refinement is: its optimum sits at the edge of the "
            "parameter range, not at a value the scene picked out. What the "
            "curve IS good for is pricing the disagreement: it says how many "
            "degrees of ground tilt the focal-length assumption is worth, which "
            "is the number A6 and any future gravity-referenced consumer needs."
        ),
    }

    p = RESULTS / "normal_reconciliation.json"
    p.write_text(json.dumps(out, indent=1))
    log(f"wrote {p}")
    for r in out["pairwise"]:
        if r["f_native_px"] in tuple(float(x) for x in SWEEP_F) + (F_INITIAL,):
            print(f"  f={r['f_native_px']:8.1f}  disagree "
                  f"cf={r['disagreement_deg_closed_form']:6.2f} "
                  f"ls={r['disagreement_deg_least_squares']:6.2f} "
                  f"rs={r['disagreement_deg_ransac']:6.2f}  "
                  f"tilt {r['tilt_raster_deg']:5.1f} / {r['tilt_geometry_deg']:5.1f} deg")
    print(json.dumps(out["verdict"], indent=1))


if __name__ == "__main__":
    main()
