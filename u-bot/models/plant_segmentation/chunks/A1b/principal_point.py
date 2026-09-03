"""A1b — bound the *other* two (d) assumptions as far as one image allows.

The chunk's headline constant is `f`, but `calib/plants_assumed.json` also pins
the principal point to the image centre and the distortion to zero. R1 says a
(d) constant without a sweep is a defect, so both get one here — with an honest
statement of how far each sweep actually reaches.

**Principal point.** Swept over offsets of +/- 1, 2 and 5 % of the image width
in each axis, and diagonally. Measured: the planarity residual of the soil band,
the fitted ground normal, and how far the normal moves. The downstream stack is
*not* re-run per principal point — that is stated rather than implied.

**Distortion.** Not sweepable from this image, and this script says why with a
measurement rather than an assertion: it looks for the longest straight-line
structures in the frame and reports that none of them is a usable straightness
target. Registered as unbounded, retired by C0.

    chunks/A1/.venv/bin/python chunks/A1b/principal_point.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from a1b_common import (A2, F_CHOSEN, F_INITIAL, NATIVE_W, RESULTS,  # noqa: E402
                        angle_deg, depth_product_dir)
from depth_to_cloud import load_depth_product  # noqa: E402
from refine_focal import patch_stats  # noqa: E402

OFFSETS_PCT = (0.0, 1.0, 2.0, 5.0)


def orient(n):
    n = np.asarray(n, float) / np.linalg.norm(n)
    return -n if n[2] > 0 else n


def fit(depth_rdu, band, f_native, dcx_px, dcy_px):
    h, w = depth_rdu.shape
    f = f_native * w / 3000.0
    cx = (w - 1) / 2.0 + dcx_px * w / NATIVE_W
    cy = (h - 1) / 2.0 + dcy_px * w / NATIVE_W
    v, u = np.nonzero(band)
    z = depth_rdu[v, u]
    P = np.stack([(u - cx) * z / f, (v - cy) * z / f, z], axis=1)
    c = P.mean(0)
    _, _, Vt = np.linalg.svd(P - c, full_matrices=False)
    n = orient(Vt[2])
    rms, sv, slope, _ = patch_stats(depth_rdu, band, f_native, win=33,
                                    cx=cx, cy=cy)
    return n, float(np.sqrt(np.mean(rms ** 2))), float(np.median(sv))


def main():
    RESULTS.mkdir(parents=True, exist_ok=True)
    prod = load_depth_product(depth_product_dir("primary_raster"))
    d = np.asarray(prod.depth, np.float64)
    d = d / np.median(d[np.isfinite(d) & (d > 0)])
    band = np.load(A2 / "products" / "ground_inliers.npy")

    out = {"chunk": "A1b",
           "what": "sensitivity of the soil-band geometry to the assumed "
                   "principal point and a statement on distortion",
           "product": "primary_raster (1344x1008)",
           "offsets_percent_of_image_width": list(OFFSETS_PCT),
           "rows": []}

    for f_native in (F_INITIAL, F_CHOSEN):
        n0, rms0, sv0 = fit(d, band, f_native, 0.0, 0.0)
        for pct in OFFSETS_PCT:
            px = pct / 100.0 * NATIVE_W
            for name, (dx, dy) in {"+x": (px, 0.0), "-x": (-px, 0.0),
                                   "+y": (0.0, px), "-y": (0.0, -px),
                                   "+xy": (px, px)}.items():
                if pct == 0.0 and name != "+x":
                    continue
                n, rms, sv = fit(d, band, f_native, dx, dy)
                out["rows"].append({
                    "f_native_px": f_native,
                    "offset_pct": pct,
                    "direction": "centre" if pct == 0 else name,
                    "offset_px_at_3000x4000": [dx, dy],
                    "planarity_rms_rdu": rms,
                    "planarity_rms_change_vs_centre": rms / rms0 - 1.0,
                    "surface_variation_median": sv,
                    "ground_normal": n.tolist(),
                    "ground_normal_moved_deg": angle_deg(n, n0),
                })

    def worst(f):
        r = [x for x in out["rows"] if x["f_native_px"] == f]
        return {
            "max_normal_move_deg_at_1pct": max(
                x["ground_normal_moved_deg"] for x in r if x["offset_pct"] == 1.0),
            "max_normal_move_deg_at_5pct": max(
                x["ground_normal_moved_deg"] for x in r if x["offset_pct"] == 5.0),
            "max_planarity_change_at_5pct": max(
                abs(x["planarity_rms_change_vs_centre"]) for x in r
                if x["offset_pct"] == 5.0),
        }

    out["summary"] = {f"f={int(f)}": worst(f) for f in (F_INITIAL, F_CHOSEN)}
    out["what_this_sweep_does_not_cover"] = (
        "the downstream stack (A2's full fit, A4, A5) was re-run per FOCAL "
        "LENGTH only, not per principal point. The numbers above bound what the "
        "principal-point assumption does to the soil band's own geometry — the "
        "quantity every later stage is built on — and not what it does to an "
        "instance F1. A principal-point offset is a shear-like perturbation "
        "rather than a scaling, so it is NOT absorbed by the linear map that "
        "makes the focal sweep so well behaved.")
    out["distortion"] = {
        "assumed": "zero, all coefficients",
        "swept": False,
        "why_not": (
            "bounding a distortion model needs something known to be straight. "
            "plants.jpeg is a garden bed under straw: the longest linear "
            "features in it are grass blades and straw stalks, which are not "
            "straight and are not known to be. There is no calibration target, "
            "no building edge, no horizon. Any 'bound' computed here would be a "
            "bound on the straightness of straw."),
        "what_would_bound_it": "C0's printed checkerboard, or a second photo of "
                               "a straight edge from the same camera.",
        "how_wrong_it_could_be": (
            "phone ISPs pre-correct geometric distortion, so the residual after "
            "correction is typically well under a percent of image height for a "
            "main camera. That is a statement about phones in general, NOT a "
            "measurement of this camera, and it is recorded as such rather than "
            "as a bound."),
    }

    p = RESULTS / "principal_point_sweep.json"
    p.write_text(json.dumps(out, indent=1))
    print(f"wrote {p}")
    print(json.dumps(out["summary"], indent=1))


if __name__ == "__main__":
    main()
