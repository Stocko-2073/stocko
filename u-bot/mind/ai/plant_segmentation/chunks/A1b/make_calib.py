"""A1b — write `calib/plants_assumed.json`.

The chunk's contract deliverable: the camera A1b adopts for `plants.jpeg`, with
its provenance, the planarity-refinement curve that was supposed to choose it,
and the honest record of what that refinement actually returned.

    chunks/A1/.venv/bin/python chunks/A1b/make_calib.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from a1b_common import (CALIB, CHOSEN_NOTE, DA3_F_MAX, DA3_F_MEAN,  # noqa: E402
                        DA3_F_MIN, DA3_F_RES504_FX, F_CHOSEN, F_INITIAL,
                        NATIVE_H, NATIVE_W, RESULTS, SWEEP_F,
                        assumed_intrinsics, equiv_mm_from_f_px)

GRIDS = {"native_3000x4000": (3000, 4000),
         "a1_primary_raster_1008x1344": (1008, 1344),
         "a1_primary_geometry_378x504": (378, 504),
         "a0_gt_grid_768x1024": (768, 1024)}


def main():
    ref = json.loads((RESULTS / "focal_refinement.json").read_text())
    nrm = json.loads((RESULTS / "normal_reconciliation.json").read_text())

    def slim(rows):
        keep = ("f_native_px", "f_equiv_mm", "planarity_rms_rdu",
                "planarity_rms_rdu_boot_p05", "planarity_rms_rdu_boot_p95",
                "planarity_median_rdu", "surface_variation_median",
                "roughness_slope_median", "patch_tilt_median_deg")
        return [{k: r[k] for k in keep} for r in rows]

    doc = {
        "image": "plants.jpeg",
        "image_size_wh": [NATIVE_W, NATIVE_H],
        "chunk": "A1b",
        "date": "2026-09-01",

        "model": {
            "type": "pinhole",
            "distortion": {"model": "none", "coefficients": [0.0] * 5,
                           "category": "(d) assumed",
                           "why": "no calibration target and no camera; phone "
                                  "ISPs pre-correct most lens distortion. The "
                                  "residual is NOT bounded by this chunk — see "
                                  "`unbounded_assumptions` below."},
            "skew": 0.0,
            "pixel_aspect": {"fx_over_fy": 1.0, "category": "(d) assumed",
                             "why": "square pixels. DA3's own head reports "
                                    "fx/fy = 0.991 at res 504, inside A1's "
                                    "registered 5 % tolerance; the cost of "
                                    "forcing it to 1 is the `manifest` row of "
                                    "the A1b sensitivity table."},
        },

        "intrinsics": {
            "fx": F_CHOSEN, "fy": F_CHOSEN,
            "cx": (NATIVE_W - 1) / 2.0, "cy": (NATIVE_H - 1) / 2.0,
            "principal_point": {"value": "image centre",
                                "category": "(d) assumed",
                                "why": "no calibration available. DA3 makes the "
                                       "same assumption internally."},
            "f_px_at_3000x4000": F_CHOSEN,
            "f_equivalent_mm": equiv_mm_from_f_px(F_CHOSEN),
            "fov_horizontal_deg": float(np.degrees(
                2 * np.arctan(NATIVE_W / (2 * F_CHOSEN)))),
            "fov_vertical_deg": float(np.degrees(
                2 * np.arctan(NATIVE_H / (2 * F_CHOSEN)))),
        },

        "provenance": "assumed+refined",
        "provenance_detail": {
            "category": "(d) assumed, with the sensitivity sweep this chunk ran",
            "starting_point_px": F_INITIAL,
            "starting_point_why": "26 mm-equivalent phone main camera at "
                                  "3000x4000, f_px = f_eq * diag_px / 43.27 mm",
            "chosen_px": F_CHOSEN,
            "chosen_why": CHOSEN_NOTE,
            "refinement_attempted": "planarity of the straw datum over A2's "
                                    "`ground_inliers`, both A1 depth products, "
                                    "72 focal lengths from 400 to 60 000 px",
            "refinement_outcome": "DEGENERATE — no interior optimum exists",
            "refinement_outcome_detail": (
                "Changing f while holding the depth raster fixed maps the point "
                "cloud by the linear map diag(f0/f1, f0/f1, 1). Linear maps take "
                "planes to planes, so planarity is preserved exactly at every f: "
                "an exactly planar depth map has residual 1e-16 rdu at f = 500 and "
                "at f = 20 000 alike. On the real datum the raw residual is "
                "monotone decreasing in f (its minimum is wherever the grid ends), "
                "and the two scale-invariant normalisations put their extrema at "
                "the grid edges or at an interior *maximum*. The control that "
                "settles it: the same estimator on a synthetic locally-planar "
                "surface rendered through a KNOWN camera recovers nothing — for "
                "f_true = 1502, 3005 and 6009 px it returns the grid edge every "
                "time. The degeneracy is therefore a property of the "
                "parametrisation, not of Depth Anything 3 having assumed an FOV."),
            "comparison_to_da3_camera_head": {
                "da3_f_px_at_3000x4000_mean": DA3_F_MEAN,
                "da3_f_px_range": [DA3_F_MIN, DA3_F_MAX],
                "da3_f_px_res504_nested_giant": DA3_F_RES504_FX,
                "ratio_da3_mean_over_initial_3005": DA3_F_MEAN / F_INITIAL,
                "reading": "A1 read DA3's own camera head at the processing "
                           "resolutions where it stays physically consistent and "
                           "got 4159-4695 px, 1.49x A1b's 3005 px prior. Nothing "
                           "in this image can adjudicate between them; A1b adopts "
                           "DA3's res-504 value because the depth field being "
                           "back-projected is conditioned on it, and bounds the "
                           "cost of being wrong with the sweep."},
        },

        "planarity_refinement_curve": {
            "units": "rdu (1 rdu = median scene depth of the raster)",
            "soil_band": "A2 ground_inliers for the same depth product",
            "columns": {
                "planarity_rms_rdu": "RMS point-to-plane distance over local "
                                     "windows of the soil band — the literal "
                                     "reading of the roadmap's instruction",
                "surface_variation_median": "lambda3/(lambda1+lambda2+lambda3), "
                                            "scale-invariant",
                "roughness_slope_median": "sqrt(lambda3/(lambda1+lambda2)) — the "
                                          "residual as a fraction of the patch's "
                                          "own in-plane extent",
                "patch_tilt_median_deg": "median tilt of the fitted soil patches "
                                         "away from the optical axis; this is what "
                                         "f actually changes",
            },
            "primary_raster_res1344": slim(
                ref["products"]["primary_raster"]["curve"]),
            "primary_geometry_res504": slim(
                ref["products"]["primary_geometry"]["curve"]),
            "extrema": {k: {kk: vv for kk, vv in v.items()
                            if kk.startswith("argm")}
                        for k, v in [("primary_raster",
                                      ref["products"]["primary_raster"]),
                                     ("primary_geometry",
                                      ref["products"]["primary_geometry"])]},
            "synthetic_control": ref["verdict"]["synthetic_recovery"],
            "exact_plane_control": ref["control_exact_plane"],
        },

        "sensitivity_sweep": {
            "f_px_at_3000x4000": list(SWEEP_F),
            "f_equivalent_mm": [round(equiv_mm_from_f_px(f), 1) for f in SWEEP_F],
            "widened_from_roadmap": "the roadmap's {1502, 2774, 3005, 3236, 6009} "
                                    "steps over DA3's own 4159-4695 px band; "
                                    "4159 / 4453 / 4489 / 4695 were added as A1's "
                                    "FINDINGS required",
            "plus_reference_row": "`manifest` — A1's own anisotropic camera "
                                  "(fx 4453, fy 4492 at 3000x4000), i.e. exactly "
                                  "what every shipped Phase A number used",
            "results": "chunks/A1b/results/sensitivity.json and "
                       "chunks/A1b/FINDINGS.md",
        },

        "plane_normal_reconciliation": {
            "what": "A2 left A1b a 7.6 deg disagreement between the ground "
                    "normals fitted on A1's two depth products",
            "at_f_chosen_deg": nrm["verdict"]["at_f_chosen"]["disagreement_deg_ransac"],
            "at_f_3005_deg": nrm["verdict"]["at_f_initial_3005"],
            "monotone_increasing_in_f": nrm["verdict"]["monotone_increasing_in_f"],
            "reading": nrm["verdict"]["reading"],
            "detail": "chunks/A1b/results/normal_reconciliation.json",
        },

        "absolute_scale": {
            "status": "UNRESOLVED",
            "why": "no fiducial, no known dimension in frame, no EXIF, camera "
                   "unavailable. DA3's metric head multiplies depth by f/300, so "
                   "its metres are proportional to a focal length this file has "
                   "just declared assumed. Deriving scale from plant size would "
                   "violate R1.",
            "consequence": "Any coordinate produced with these intrinsics carries "
                           "`scale_confidence = 'assumed_scale'` "
                           "(`depth_to_cloud.save_cloud` enforces it). Phase A "
                           "reports every distance in rdu instead and never uses "
                           "this file for a metric claim.",
            "retired_by": "C0 (calibrated camera) plus an ArUco fiducial",
        },

        "unbounded_assumptions": [
            {"assumption": "zero distortion", "category": "(d)",
             "bounded_by_this_chunk": False,
             "why_not": "bounding it needs a second image of a straight edge or "
                        "a calibration target; `plants.jpeg` contains no straight "
                        "line long enough to test against. Registered, retired by C0."},
            {"assumption": "principal point at the image centre", "category": "(d)",
             "bounded_by_this_chunk": "partially",
             "why_not": "swept in `principal_point_sweep.json` for its effect on "
                        "the soil-band geometry only; the downstream stack was not "
                        "re-run per principal point. Retired by C0."},
            {"assumption": "absolute scale", "category": "not assigned",
             "bounded_by_this_chunk": False,
             "why_not": "deliberately absent; see `absolute_scale`."},
        ],

        "usage": {
            "python": ("import sys; sys.path.insert(0, 'chunks/A1'); "
                       "from depth_to_cloud import Intrinsics; "
                       "Intrinsics.from_focal_px(f, W, H, 'assumed+refined', "
                       "principal_point_at_centre=True)"),
            "note": "`depth_to_cloud(mode='assumed')` flags the result "
                    "`assumed_scale`. It refuses `model_estimated` intrinsics by "
                    "design (A1 decision 3); A1b supplies its own object with "
                    "provenance 'assumed+refined', which is honest about the "
                    "value coinciding with DA3's res-504 estimate.",
            "on_other_grids": {},
        },
    }

    for name, (w, h) in GRIDS.items():
        intr = assumed_intrinsics(F_CHOSEN, w, h, provenance="assumed+refined")
        doc["usage"]["on_other_grids"][name] = {
            "fx": intr.fx, "fy": intr.fy, "cx": intr.cx, "cy": intr.cy,
            "width": w, "height": h,
        }

    CALIB.mkdir(parents=True, exist_ok=True)
    p = CALIB / "plants_assumed.json"
    p.write_text(json.dumps(doc, indent=1))
    print(f"wrote {p}")
    print(json.dumps({k: doc["intrinsics"][k] for k in
                      ("fx", "fy", "cx", "cy", "f_equivalent_mm",
                       "fov_horizontal_deg", "fov_vertical_deg")}, indent=1))


if __name__ == "__main__":
    main()
