"""A4 — the sweeps. Every knob in the code path, moved, and what it did.

The chunk exists because ZeroPlantSeg's `eps` had a usable window of 1.3x
(100 isolates the clover, 130 swallows it). Anything that replaces it has to
show its own window honestly. So every constant A4 uses is swept here over
decades, not percent, and the tables are the evidence — for the claim and
against it.

Four sweeps:

1. **tolerance**, 1e-5 .. 1 rdu (five decades), for both unresolved-edge
   policies. Includes A1's registered `local_planarity_p10` values as marked
   rows, so the literal roadmap reading is visible in the same table.
2. **the within-fragment quantile** that sets the shipped tolerance, 50..99.
3. **the continuity statistic** — raw step / directional second difference /
   5x5 in-fragment plane extrapolation.
4. **node granularity** — SAM region alone vs SAM region crossed with the A3
   material class.

Run:  ../A3/.venv/bin/python sweeps.py
"""
from __future__ import annotations

import argparse
import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import a4_common as C      # noqa: E402
import a4_graph as G       # noqa: E402
import fast_eval as FE     # noqa: E402
import run_a4 as R         # noqa: E402
import eval as a0eval      # noqa: E402

TOLS = sorted(set([1e-5, 3e-5, 1e-4, 3e-4, 1e-3, 2e-3, 3e-3, 4e-3, 6e-3, 1e-2,
                   2e-2, 3e-2, 6e-2, 1e-1, 3e-1, 1.0]
                  + list(C.LOCAL_PLANARITY_P10_RDU.values())))
QUANTILES = [50, 60, 70, 75, 80, 85, 88, 90, 92, 95, 97, 99]


def score_at(frag, s, tol, gt, policy):
    conn, sep, unres = G.classify_edges(s, tol)
    accept = conn if policy == "split" else (conn | unres)
    comp = G.components(int(frag.max()), s["pairs"], accept)
    lab = C.to_gt_grid_nearest(comp[frag].astype(np.int32))
    out = FE.summary(lab, gt)
    out.update(tol_rdu=float(tol), policy=policy,
               n_components=int(comp.max()),
               edges_connected=int(conn.sum()), edges_separated=int(sep.sum()),
               edges_unresolved=int(unres.sum()))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(C.RESULTS, "sweeps.json"))
    a = ap.parse_args()
    gt = a0eval.load_gt()
    inp = C.load_inputs()
    out = {"scale_confidence": "scale_free",
           "a1_local_planarity_p10_rdu": C.LOCAL_PLANARITY_P10_RDU,
           "a1_depth_resolution_floor_rdu": C.DEPTH_RESOLUTION_FLOOR_RDU}

    # ---- 1 + 2: the shipped configuration, tolerance and quantile ----------
    frag, finfo = G.build_fragments(inp, use_class=True)
    n = int(frag.max())
    b = G.boundary_residuals(inp, frag, intra=False, statistic="secdiff")
    s = G.summarise_boundaries(b, n)
    within = G.boundary_residuals(inp, frag, intra=True,
                                  statistic="secdiff")["resid"]
    out["within_fragment_residual_rdu"] = {
        str(p): float(np.percentile(within, p))
        for p in (10, 25, 50, 75, 90, 95, 99)}
    out["shipped_tolerance_rdu"] = float(np.percentile(
        within, R.WITHIN_FRAGMENT_QUANTILE))
    for pol in ("split", "merge"):
        out[f"tolerance_sweep_{pol}"] = [score_at(frag, s, t, gt, pol)
                                         for t in TOLS]
    out["quantile_sweep"] = [
        dict(score_at(frag, s, float(np.percentile(within, q)), gt, pol),
             quantile=q)
        for q in QUANTILES for pol in ("split", "merge")]

    # ---- 3: the statistic --------------------------------------------------
    out["statistic_sweep"] = []
    for stat in ("step", "secdiff", "plane5"):
        w = G.boundary_residuals(inp, frag, intra=True, statistic=stat)["resid"]
        tol = float(np.percentile(w, R.WITHIN_FRAGMENT_QUANTILE))
        ss = G.summarise_boundaries(
            G.boundary_residuals(inp, frag, intra=False, statistic=stat), n)
        for pol in ("split", "merge"):
            out["statistic_sweep"].append(
                dict(score_at(frag, ss, tol, gt, pol), statistic=stat))

    # ---- 4: node granularity ----------------------------------------------
    out["node_sweep"] = []
    for use_class in (False, True):
        f2, fi2 = G.build_fragments(inp, use_class=use_class)
        n2 = int(f2.max())
        w = G.boundary_residuals(inp, f2, intra=True, statistic="secdiff")["resid"]
        tol = float(np.percentile(w, R.WITHIN_FRAGMENT_QUANTILE))
        s2 = G.summarise_boundaries(
            G.boundary_residuals(inp, f2, intra=False, statistic="secdiff"), n2)
        for pol in ("split", "merge"):
            out["node_sweep"].append(dict(
                score_at(f2, s2, tol, gt, pol),
                nodes="region_x_class" if use_class else "region",
                n_fragments=fi2["n_fragments"], tol_rdu=tol))

    # ---- min-fragment-size sweep (the one size constant in the code path) --
    out["min_fragment_sweep"] = []
    for mp in (1, 9, 25, 49, 100):
        f3, fi3 = G.build_fragments(inp, min_px=mp, use_class=True)
        n3 = int(f3.max())
        w = G.boundary_residuals(inp, f3, intra=True, statistic="secdiff")["resid"]
        tol = float(np.percentile(w, R.WITHIN_FRAGMENT_QUANTILE))
        s3 = G.summarise_boundaries(
            G.boundary_residuals(inp, f3, intra=False, statistic="secdiff"), n3)
        out["min_fragment_sweep"].append(dict(
            score_at(f3, s3, tol, gt, "split"), min_fragment_px=mp,
            n_fragments=fi3["n_fragments"], tol_rdu=tol))

    json.dump(out, open(a.out, "w"), indent=1, default=float)
    _print(out)
    print("wrote", a.out)


def _print(out):
    hdr = "%10s %6s %6s %4s %5s %8s %7s %6s  %s"
    row = "%10.2e %6d %6d %4d %5d %8.4f %7.3f %6.3f  %s"
    for pol in ("split", "merge"):
        print(f"\n=== tolerance sweep, unresolved -> {pol} "
              f"(shipped tol {out['shipped_tolerance_rdu']:.3e} rdu) ===")
        print(hdr % ("tol", "ncomp", "npred", "TP", "parts", "F1", "squIoU",
                     "grass", "matched"))
        for r in out[f"tolerance_sweep_{pol}"]:
            print(row % (r["tol_rdu"], r["n_components"], r["n_pred"], r["tp"],
                         r["squash_parts"], r["f1"], r["squash_best_iou"],
                         r["grass_absorbed"], r["matched_gt"]))
    print("\n=== within-fragment quantile sweep ===")
    print("%5s %6s %10s %6s %4s %5s %8s %7s %6s" %
          ("q", "policy", "tol", "ncomp", "TP", "parts", "F1", "squIoU", "grass"))
    for r in out["quantile_sweep"]:
        print("%5d %6s %10.2e %6d %4d %5d %8.4f %7.3f %6.3f" %
              (r["quantile"], r["policy"], r["tol_rdu"], r["n_components"],
               r["tp"], r["squash_parts"], r["f1"], r["squash_best_iou"],
               r["grass_absorbed"]))
    for name, keys in (("statistic_sweep", ("statistic", "policy")),
                       ("node_sweep", ("nodes", "policy", "n_fragments")),
                       ("min_fragment_sweep", ("min_fragment_px", "n_fragments"))):
        print(f"\n=== {name} ===")
        for r in out[name]:
            print("  " + " ".join(f"{k}={r[k]}" for k in keys) +
                  f" tol={r['tol_rdu']:.2e} ncomp={r['n_components']} "
                  f"TP={r['tp']} F1={r['f1']:.4f} "
                  f"squIoU={r['squash_best_iou']:.3f} "
                  f"grass={r['grass_absorbed']:.3f}")


if __name__ == "__main__":
    main()
