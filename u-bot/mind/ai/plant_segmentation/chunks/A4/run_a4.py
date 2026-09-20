"""A4 — build the components, score them, and write every artifact.

    ../A3/.venv/bin/python run_a4.py            # the shipped run
    ../A3/.venv/bin/python run_a4.py --oracle-material   # diagnostic

Writes `products/` (component label map on A0's grid + the depth grid, the
unresolved-edge list, a manifest), `results/a4_scores.json`, and prints A0's own
`eval.py` report — which is the number of record.
"""
from __future__ import annotations

import argparse
import json
import os
import sys

import numpy as np
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import a4_common as C      # noqa: E402
import a4_graph as G       # noqa: E402
import fast_eval as FE     # noqa: E402
import unresolved as U     # noqa: E402
import eval as a0eval      # noqa: E402

# (c) observation — the continuity tolerance. See FINDINGS: A1's registered
# `local_planarity_p10` is a *tenth* percentile, the smoothness of the flattest
# tenth of the scene, and using it as an acceptance threshold rejects half of
# the pixel pairs that lie inside one fragment and are therefore continuous by
# construction. A4 re-measures the same quantity where it is actually needed:
# the continuity residual over pixel pairs known to be within one fragment. A
# boundary is a discontinuity when it is rougher than this fraction of material
# already known to be continuous. Swept over 50/75/90/95/99 in `sweeps.py`.
WITHIN_FRAGMENT_QUANTILE = 90.0


def measure_tolerance(inp, frag, statistic="secdiff", q=WITHIN_FRAGMENT_QUANTILE):
    r = G.boundary_residuals(inp, frag, intra=True, statistic=statistic)["resid"]
    return float(np.percentile(r, q)), {
        "quantile": q, "n_within_fragment_pairs": int(r.size),
        "percentiles_rdu": {str(p): float(np.percentile(r, p))
                            for p in (10, 25, 50, 75, 90, 95, 99)}}


def build(inp, statistic="secdiff", tol=None, use_class=True,
          unresolved_policy="split"):
    frag, finfo = G.build_fragments(inp, use_class=use_class)
    n = int(frag.max())
    tol_info = None
    if tol is None:
        tol, tol_info = measure_tolerance(inp, frag, statistic)
    if tol < C.DEPTH_RESOLUTION_FLOOR_RDU:
        raise ValueError(
            f"continuity tolerance {tol:.3e} rdu is below A1's measured depth "
            f"resolution floor {C.DEPTH_RESOLUTION_FLOOR_RDU:.3e} rdu; the "
            f"raster cannot express a step that small (A1 MANIFEST).")
    b = G.boundary_residuals(inp, frag, intra=False, statistic=statistic)
    s = G.summarise_boundaries(b, n)
    conn, sep, unres = G.classify_edges(s, tol)
    # Two policies for the edges the boundary evidence does not decide, and the
    # choice is a rules question, not a tuning one:
    #   `split` — R4 literal. An undecided link is not a link. Nothing is merged
    #             on evidence that does not exist.
    #   `merge` — R2. Splitting the crop is the failure this chunk exists to fix,
    #             and A6 builds the keep-out volume out of the crop component, so
    #             a split crop under-covers the volume a tool must stay out of.
    #             Merging a weed into the crop only means the weed survives.
    # Both are computed; both are reported. Neither is silent: the unresolved
    # edges are written out either way.
    comp_split = G.components(n, s["pairs"], conn)
    comp_merge = G.components(n, s["pairs"], conn | unres)
    comp_of = comp_split if unresolved_policy == "split" else comp_merge
    return dict(frag=frag, n_frag=n, finfo=finfo, summary=s, tol=tol,
                tol_info=tol_info, conn=conn, sep=sep, unres=unres,
                comp_of=comp_of, statistic=statistic,
                unresolved_policy=unresolved_policy,
                comp_split=comp_split, comp_merge=comp_merge,
                comp_depth=comp_of[frag].astype(np.int32))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--oracle-material", action="store_true",
                    help="diagnostic: use A0's ground-truth material map")
    ap.add_argument("--statistic", default="secdiff",
                    choices=["secdiff", "plane5", "step"])
    ap.add_argument("--tol", type=float, default=None)
    ap.add_argument("--tag", default=None)
    ap.add_argument("--unresolved-policy", default="split",
                    choices=["split", "merge"])
    a = ap.parse_args()

    src = "gt" if a.oracle_material else "a3"
    tag = a.tag or ("oracle_material" if a.oracle_material else "default")
    inp = C.load_inputs(material_source=src)
    gt = a0eval.load_gt()
    r = build(inp, a.statistic, a.tol, unresolved_policy=a.unresolved_policy)

    comp_gt = C.to_gt_grid_nearest(r["comp_depth"])
    edges, uinfo = U.find_unresolved(inp, r["frag"], r["summary"], r["conn"],
                                     r["unres"], r["comp_of"])

    # --- the number of record: A0's own eval.py, unmodified ------------------
    pred = a0eval.Prediction(instances=comp_gt, name=f"A4 connectivity ({tag})")
    rep = a0eval.score(pred, gt)
    a0eval.print_report(rep)

    # --- the symmetric-grass diagnostic --------------------------------------
    # A0 excludes GT grass instances from `n_gt` because grass is unresolved.
    # Predicted components that are themselves majority-grass in the GT are the
    # symmetric case; they are excluded here and *only* here, clearly labelled,
    # because a component that correctly isolates a grass blade should not be
    # counted as a false plant instance when the ground truth declines to
    # instance grass at all. The headline above does not use this.
    grass = gt.instances == a0eval.GRASS_UNRESOLVED
    keep = np.ones(int(comp_gt.max()) + 1, bool)
    tot = np.bincount(comp_gt.ravel(), minlength=keep.size)
    gr = np.bincount(comp_gt[grass].ravel(), minlength=keep.size)
    keep[1:] = gr[1:] <= 0.5 * np.maximum(tot[1:], 1)
    comp_nograss = np.where(keep[comp_gt], comp_gt, 0).astype(np.int32)
    sym = FE.summary(comp_nograss, gt)

    scores = {
        "name": tag, "material_source": src, "statistic": a.statistic,
        "continuity_tolerance_rdu": r["tol"],
        "tolerance_provenance": r["tol_info"],
        "scale_confidence": "scale_free",
        "n_fragments": r["n_frag"], "fragments": r["finfo"],
        "edges": {"adjacent_pairs": int(len(r["summary"]["n"])),
                  "connected": int(r["conn"].sum()),
                  "separated": int(r["sep"].sum()),
                  "unresolved_boundary": int(r["unres"].sum())},
        "n_components": int(r["comp_depth"].max()),
        "headline_eval_py": {
            "instances": {k: v for k, v in rep["instances"].items()
                          if k != "matches"},
            "matches": rep["instances"]["matches"],
            "squash_fragmentation": rep["squash_fragmentation"],
            "grass_absorbed_into_crop": rep["grass_absorbed_into_crop"],
        },
        "symmetric_grass_diagnostic": sym,
        "unresolved_policy": r["unresolved_policy"],
        "both_policies": {
            "split": FE.summary(C.to_gt_grid_nearest(
                r["comp_split"][r["frag"]].astype(np.int32)), gt),
            "merge": FE.summary(C.to_gt_grid_nearest(
                r["comp_merge"][r["frag"]].astype(np.int32)), gt)},
        "unresolved": uinfo,
        "provenance": inp.provenance,
    }
    os.makedirs(C.RESULTS, exist_ok=True)
    os.makedirs(C.PRODUCTS, exist_ok=True)
    json.dump(scores, open(os.path.join(C.RESULTS, f"a4_scores_{tag}.json"), "w"),
              indent=1, default=float)
    json.dump({"chunk": "A4", "note": U.__doc__, "tolerance_rdu": r["tol"],
               "summary": uinfo, "edges": edges},
              open(os.path.join(C.PRODUCTS, f"unresolved_edges_{tag}.json"), "w"),
              indent=1, default=float)
    np.save(os.path.join(C.PRODUCTS, f"components_gt_grid_{tag}.npy"), comp_gt)
    np.save(os.path.join(C.PRODUCTS, f"components_depth_grid_{tag}.npy"),
            r["comp_depth"])
    np.save(os.path.join(C.WORK, f"fragments_{tag}.npy"), r["frag"])
    np.savez(os.path.join(C.WORK, f"graph_{tag}.npz"),
             pairs=r["summary"]["pairs"], n=r["summary"]["n"],
             p25=r["summary"]["p25"], p50=r["summary"]["p50"],
             p75=r["summary"]["p75"], conn=r["conn"], sep=r["sep"],
             unres=r["unres"], comp_of=r["comp_of"])
    Image.fromarray(np.clip(comp_gt, 0, 65535).astype(np.uint16)).save(
        os.path.join(C.PRODUCTS, f"components_gt_grid_{tag}.png"))

    print(json.dumps({k: scores[k] for k in
                      ("continuity_tolerance_rdu", "n_fragments", "edges",
                       "n_components", "symmetric_grass_diagnostic",
                       "unresolved")}, indent=1, default=float))
    return scores


if __name__ == "__main__":
    main()
