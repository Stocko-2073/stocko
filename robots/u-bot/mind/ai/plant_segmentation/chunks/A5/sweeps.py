"""A5 — sensitivity sweeps.

    ../A3/.venv/bin/python sweeps.py

`MAX_EXTRAPOLATION_SIGMA` is the chunk's one (b) tool-geometry placeholder, so
under R1 it has to arrive with a sweep. The other four knobs are conventions
inherited or derived, and they are swept too so the conclusions are bounded
rather than asserted.

Also writes the **extrapolation-distance CDF**, which is the artifact C3 should
actually use: rather than inheriting A5's placeholder, C3 reads its own tool's
budget off this curve and gets the resulting status counts directly.
"""
from __future__ import annotations

import json
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from a5_common import load_a3_material_depth_grid, load_a4, load_scene  # noqa: E402
import contact_points as cp  # noqa: E402

RESULTS = os.path.join(HERE, "results")
POLICIES = {"split": "default", "merge": "merge"}


def row(cs):
    d = {"observed": 0, "extrapolated": 0, "occluded": 0}
    for c in cs:
        d[c.status] += 1
    d["with_a_point"] = sum(1 for c in cs if c.point is not None)
    d["arm_admissible"] = sum(1 for c in cs if c.arm_admissible)
    d["fabricated"] = sum(1 for c in cs if c.status == "occluded" and c.point)
    ex = [c.extrapolation_distance_sigma for c in cs if c.status == "extrapolated"]
    d["extrap_sigma_median"] = float(np.median(ex)) if ex else None
    return d


def main():
    os.makedirs(RESULTS, exist_ok=True)
    scene = load_scene()
    material = load_a3_material_depth_grid()
    a4 = {p: load_a4(tag=t) for p, t in POLICIES.items()}
    out = {"chunk": "A5", "note": "counts by status under each setting"}

    grids = {
        "max_extrapolation_sigma": [0.0, 2.0, 5.0, 10.0, 20.0, 40.0, 80.0, 160.0, 1e9],
        "ground_band_k": [2.0, 3.0, 4.0, 5.0],
        "basal_band_k": [0.5, 1.0, 2.0, 3.0],
        "min_axis_points": [5, 9, 25, 49],
        "median_window": [1, 3, 5],
    }
    default = {"max_extrapolation_sigma": cp.MAX_EXTRAPOLATION_SIGMA,
               "ground_band_k": cp.GROUND_BAND_K,
               "basal_band_k": cp.BASAL_BAND_K,
               "min_axis_points": cp.MIN_AXIS_POINTS,
               "median_window": cp.MEDIAN_WINDOW}
    out["default"] = dict(default)

    for knob, values in grids.items():
        out[knob] = {}
        for v in values:
            kw = dict(default)
            kw[knob] = v
            out[knob][str(v)] = {}
            for policy in POLICIES:
                cs = cp.contact_points(scene, a4[policy].components_depth,
                                       material, a4[policy].unresolved, **kw)
                out[knob][str(v)][policy] = row(cs)
            print(knob, v, out[knob][str(v)]["split"], flush=True)

    # ---- the CDF C3 should read its budget off -----------------------------
    cs = cp.contact_points(scene, a4["split"].components_depth, material,
                           a4["split"].unresolved,
                           max_extrapolation_sigma=1e9)
    d = sorted(c.extrapolation_distance_sigma for c in cs
               if c.status == "extrapolated"
               and c.extrapolation_distance_sigma is not None)
    out["extrapolation_distance_cdf_split"] = {
        "note": "distance in datum-σ (σ = 5.47e-3 rdu) from the lowest visible "
                "material to the datum along the basal axis, measured with the "
                "tool budget removed. Read a budget off this to get the number "
                "of components that would be admitted at that budget.",
        "n": len(d),
        "sigma": d,
        "quantiles": {str(q): (float(np.percentile(d, q)) if d else None)
                      for q in (0, 10, 25, 50, 75, 90, 100)},
    }
    json.dump(out, open(os.path.join(RESULTS, "sweeps.json"), "w"), indent=1)
    print("wrote results/sweeps.json")


if __name__ == "__main__":
    main()
