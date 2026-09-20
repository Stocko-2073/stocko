"""A1b — collect the per-`f` runs into the sensitivity table and the invariance
verdict.

Every metric gets three numbers rather than a hand-wave:

* **spread** — (max - min) / |median| over the swept focal lengths;
* **log-log slope** — the least-squares slope of log|value| against log f. A
  slope of 0 means the quantity does not care what the focal length is; a slope
  of -1 means it is simply proportional to 1/f and carries no information the
  focal length did not put there; anything else is a real dependence;
* **verdict** — the classification those two imply, computed, not asserted.

    chunks/A1/.venv/bin/python chunks/A1b/aggregate.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from a1b_common import F_CHOSEN, F_INITIAL, RESULTS, SWEEP_F  # noqa: E402

# What to extract from a stage JSON, as (column name, path, note).
COLUMNS = [
    # --- A2 -----------------------------------------------------------------
    ("A2 inlier fraction", ("a2", "inlier_fraction")),
    ("A2 inlier residual RMS (rdu)", ("a2", "inlier_residual_rms_rdu")),
    ("A2 datum sigma (rdu)", ("a2", "datum_roughness_sigma_rdu")),
    ("A2 RANSAC threshold (rdu)", ("a2", "ransac_threshold_rdu")),
    ("A2 lam", ("a2", "lam")),
    ("A2 fit scale (px)", ("a2", "fit_scale_px")),
    ("A2 observed fraction", ("a2", "observed_fraction")),
    ("A2 extrapolated fraction", ("a2", "extrapolated_fraction")),
    ("A2 trust distance (px)", ("a2", "max_trusted_support_px")),
    ("A2 ground tilt from optical axis (deg)",
     ("scene", "plane_tilt_from_camera_axis_deg")),
    # --- A4 split ------------------------------------------------------------
    ("A4 split continuity tol (rdu)", ("a4", "split", "continuity_tolerance_rdu")),
    ("A4 split fragments", ("a4", "split", "n_fragments")),
    ("A4 split components", ("a4", "split", "n_components")),
    ("A4 split instance F1", ("a4", "split", "instances", "f1")),
    ("A4 split TP", ("a4", "split", "instances", "tp")),
    ("A4 split squash best IoU", ("a4", "split", "verdicts", "squash_best_iou")),
    ("A4 split squash one component",
     ("a4", "split", "verdicts", "squash_one_component")),
    ("A4 split clover separate",
     ("a4", "split", "verdicts", "clover_separate_from_crop")),
    ("A4 split clover fraction in crop",
     ("a4", "split", "verdicts", "clover_fraction_inside_crop_component")),
    ("A4 split grass absorbed",
     ("a4", "split", "verdicts", "grass_absorbed_fraction")),
    ("A4 split unresolved boundaries",
     ("a4", "split", "edges", "unresolved_boundary")),
    # --- A4 merge ------------------------------------------------------------
    ("A4 merge components", ("a4", "merge", "n_components")),
    ("A4 merge instance F1", ("a4", "merge", "instances", "f1")),
    ("A4 merge squash best IoU", ("a4", "merge", "verdicts", "squash_best_iou")),
    ("A4 merge squash one component",
     ("a4", "merge", "verdicts", "squash_one_component")),
    ("A4 merge clover separate",
     ("a4", "merge", "verdicts", "clover_separate_from_crop")),
    ("A4 merge grass absorbed",
     ("a4", "merge", "verdicts", "grass_absorbed_fraction")),
    # --- A5 ------------------------------------------------------------------
    ("A5 split observed", ("a5", "split", "status_counts", "observed")),
    ("A5 split extrapolated", ("a5", "split", "status_counts", "extrapolated")),
    ("A5 split occluded", ("a5", "split", "status_counts", "occluded")),
    ("A5 split arm-admissible", ("a5", "split", "arm_admissible")),
    ("A5 split median confidence", ("a5", "split", "median_confidence")),
    ("A5 split GT-consistency median (px)",
     ("a5", "split", "gt_consistency", "summary", "err_contact_px", "median_px")),
    ("A5 split GT-consistency n",
     ("a5", "split", "gt_consistency", "summary", "err_contact_px", "n")),
    ("A5 merge observed", ("a5", "merge", "status_counts", "observed")),
    ("A5 merge extrapolated", ("a5", "merge", "status_counts", "extrapolated")),
    ("A5 merge occluded", ("a5", "merge", "status_counts", "occluded")),
    ("A5 merge arm-admissible", ("a5", "merge", "arm_admissible")),
    ("A5 merge GT-consistency median (px)",
     ("a5", "merge", "gt_consistency", "summary", "err_contact_px", "median_px")),
]


def dig(d, path):
    for k in path:
        if d is None:
            return None
        d = d.get(k) if isinstance(d, dict) else None
    return d


def classify(vals, fs):
    """Turn a column into a verdict. Nothing here is hand-set."""
    v = np.asarray([np.nan if x is None else float(x) for x in vals], float)
    ok = np.isfinite(v)
    if ok.sum() < 3:
        return {"verdict": "insufficient data"}
    vv, ff = v[ok], np.asarray(fs, float)[ok]
    med = float(np.median(vv))
    if vv.max() == vv.min():
        spread = 0.0
    elif med:
        spread = float((vv.max() - vv.min()) / abs(med))
    else:
        spread = float("inf")
    slope = None
    if np.all(vv > 0):
        slope = float(np.polyfit(np.log(ff), np.log(vv), 1)[0])
    if vv.max() == vv.min():
        verdict = "EXACTLY invariant"
    elif spread < 0.01:
        verdict = "invariant to <1%"
    elif spread < 0.05:
        verdict = "invariant to <5%"
    elif slope is not None and abs(slope + 1.0) < 0.12:
        verdict = "scales as 1/f (pure units)"
    elif slope is not None and abs(slope - 1.0) < 0.12:
        verdict = "scales as f (pure units)"
    else:
        verdict = "MOVES"
    return {"min": float(vv.min()), "max": float(vv.max()), "median": med,
            "spread_over_median": spread, "loglog_slope": slope,
            "verdict": verdict}


# Derived columns: the point of the chunk is that several quantities move only
# because their UNIT moves. Each of these is a ratio of two things that rescale
# together, and each is computed here rather than eyeballed off the table.
DERIVED = [
    ("A2 residual / datum sigma", ("a2", "inlier_residual_rms_rdu"),
     ("a2", "datum_roughness_sigma_rdu")),
    ("A2 residual / RANSAC threshold", ("a2", "inlier_residual_rms_rdu"),
     ("a2", "ransac_threshold_rdu")),
    ("A4 continuity tol / A2 datum sigma",
     ("a4", "split", "continuity_tolerance_rdu"),
     ("a2", "datum_roughness_sigma_rdu")),
]


def main():
    rows = {}
    for p in sorted(RESULTS.glob("stage_*.json")):
        d = json.loads(p.read_text())
        rows[d["tag"]] = d

    if not rows:
        raise SystemExit("no stage_*.json in chunks/A1b/results — run run_stage.py")

    sweep_tags = [f"f{int(round(f))}" for f in SWEEP_F if f"f{int(round(f))}" in rows]
    fs = [float(rows[t]["f_native_px"]) for t in sweep_tags]

    table = {}
    for name, path in COLUMNS:
        table[name] = {
            "by_tag": {t: dig(rows[t], path) for t in rows},
            "sensitivity": classify([dig(rows[t], path) for t in sweep_tags], fs),
        }

    for name, num, den in DERIVED:
        vals = {}
        for t in rows:
            a, b = dig(rows[t], num), dig(rows[t], den)
            vals[t] = (None if a is None or not b else float(a) / float(b))
        table[name] = {"by_tag": vals,
                       "sensitivity": classify([vals[t] for t in sweep_tags], fs),
                       "derived": True,
                       "note": "a ratio of two quantities that carry the same "
                               "focal-length-dependent unit"}

    out = {
        "chunk": "A1b",
        "what": "sensitivity of the Phase A stack to the assumed focal length",
        "scale_confidence": "scale_free — every distance below is in rdu; no "
                            "metric claim is made anywhere in this table",
        "f_native_px_by_tag": {t: rows[t]["f_native_px"] for t in rows},
        "swept_tags_in_order": sweep_tags,
        "f_chosen_px": F_CHOSEN,
        "f_initial_px": F_INITIAL,
        "reference_row": "manifest — A1's own anisotropic camera; the only row "
                         "whose numbers must reproduce RESULTS.md",
        "columns": table,
    }

    # --- the summary the done-criteria ask for -------------------------------
    buckets = {}
    for name, c in table.items():
        buckets.setdefault(c["sensitivity"].get("verdict", "?"), []).append(name)
    out["invariance_summary"] = buckets

    # --- reference-row agreement with the shipped Phase A numbers ------------
    shipped = {
        "A2 inlier fraction": 0.291,
        "A2 inlier residual RMS (rdu)": 6.85e-3,
        "A2 datum sigma (rdu)": 5.47e-3,
        "A4 split components": 742,
        "A4 split instance F1": 0.0088,
        "A4 split squash best IoU": 0.462,
        "A4 split grass absorbed": 0.118,
        "A5 split observed": 472,
        "A5 split extrapolated": 59,
        "A5 split occluded": 211,
    }
    ref = {}
    for k, want in shipped.items():
        got = table[k]["by_tag"].get("manifest")
        ref[k] = {"shipped_RESULTS_md": want, "A1b_manifest_row": got,
                  "relative_difference":
                      (None if got in (None, 0) or want == 0
                       else float(abs(got - want) / abs(want)))}
    out["reference_row_reproduces_shipped_phase_A"] = ref

    # --- the free-RANSAC-seed control sweep ---------------------------------
    fs_tags = [t for t in rows if t.endswith("_freeseed")]
    if fs_tags:
        cmp_cols = ["A2 inlier fraction", "A2 inlier residual RMS (rdu)",
                    "A4 split components", "A4 split instance F1",
                    "A4 split squash best IoU", "A4 split grass absorbed",
                    "A5 split observed", "A5 split arm-admissible"]
        out["free_seed_control"] = {
            "what": "the same sweep with A2's RANSAC seed plane re-drawn at each "
                    "f instead of transported from the reference row",
            "why": "A2 seeds its outer loop with a RANSAC plane found at ~1.2 % "
                   "inliers. Rescaling the cloud changes which plane wins that "
                   "draw, and above f = 4159 px a different one does. The rows "
                   "below are what the shipped A2 pipeline actually produces; "
                   "the divergence is an A2 property, not a focal-length effect.",
            "rows": {t: {c: table[c]["by_tag"].get(t) for c in cmp_cols}
                     for t in sorted(fs_tags)},
            "seeded_rows_for_comparison": {
                t: {c: table[c]["by_tag"].get(t) for c in cmp_cols}
                for t in sweep_tags},
        }

    p = RESULTS / "sensitivity.json"
    p.write_text(json.dumps(out, indent=1, default=float))
    print(f"wrote {p}")

    # --- markdown, for FINDINGS / RESULTS ------------------------------------
    md = []
    hdr = ["metric"] + [f"{int(rows[t]['f_native_px'])}" for t in sweep_tags] \
        + ["manifest", "spread", "slope", "verdict"]
    md.append("| " + " | ".join(hdr) + " |")
    md.append("|" + "---|" * len(hdr))
    for name, c in table.items():
        cells = [name]
        for t in sweep_tags + ["manifest"]:
            v = c["by_tag"].get(t)
            cells.append(fmt(v))
        s = c["sensitivity"]
        cells.append("—" if "spread_over_median" not in s
                     else f"{s['spread_over_median']*100:.1f}%")
        cells.append("—" if s.get("loglog_slope") is None
                     else f"{s['loglog_slope']:+.2f}")
        cells.append(s.get("verdict", "?"))
        md.append("| " + " | ".join(cells) + " |")
    (RESULTS / "sensitivity_table.md").write_text("\n".join(md) + "\n")
    print(f"wrote {RESULTS / 'sensitivity_table.md'}")
    print("\n".join(md))
    print("\n== invariance summary ==")
    for k, v in buckets.items():
        print(f"  {k}: {len(v)}")


def fmt(v):
    if v is None:
        return "—"
    if isinstance(v, bool):
        return "yes" if v else "no"
    if isinstance(v, int):
        return str(v)
    if abs(v) >= 100 or (v != 0 and abs(v) < 1e-3):
        return f"{v:.3e}"
    return f"{v:.4g}"


if __name__ == "__main__":
    main()
