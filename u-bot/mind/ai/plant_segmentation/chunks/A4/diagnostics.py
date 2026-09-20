"""A4 — the measurements that decided the design, kept so the decision is auditable.

Three questions, answered with numbers before anything was shipped:

1. **What is the ceiling?** If grouping were perfect on A3's plant mask, what
   instance F1 would A4 score? (Answer: 1.0000 — the material map is not the
   binding constraint; the graph is.)
2. **Which continuity statistic separates best?** Three candidates are scored by
   how well a boundary's residual distinguishes "these two fragments are the
   same ground-truth plant" from "they are different plants".
3. **How far can adjacency-plus-continuity go at all?** An oracle that is told
   the true answer for every edge is run through the same union-find, to
   separate "the graph cannot express this" from "the edge test is wrong".

Run:  ../A3/.venv/bin/python diagnostics.py
"""
from __future__ import annotations

import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import a4_common as C          # noqa: E402
import a4_graph as G           # noqa: E402
import fast_eval as FE         # noqa: E402
import eval as a0eval          # noqa: E402


def frag_majority_instance(frag, gt, n):
    ginst = C._nearest_to_depth_grid(gt.instances).astype(np.int64)
    M = np.zeros((n + 1, 257), np.int64)
    np.add.at(M, (frag.ravel(), ginst.ravel()), 1)
    return M.argmax(1), M


def auc_lower_is_same(v, same, diff):
    from scipy.stats import rankdata
    x = np.concatenate([v[same], v[diff]])
    y = np.concatenate([np.ones(same.sum()), np.zeros(diff.sum())])
    rk = rankdata(x)
    ns, nd = same.sum(), diff.sum()
    a = (rk[y == 1].sum() - ns * (ns + 1) / 2) / (ns * nd)
    return float(1 - a)


def main():
    gt = a0eval.load_gt()
    inp = C.load_inputs()
    out = {"scale_confidence": "scale_free"}

    # -- 1. ceilings ---------------------------------------------------------
    plant_gt = np.isin(inp.material_gt, C.PLANT_IDS)
    lab = np.where(plant_gt, gt.instances, 0).astype(np.int32)
    lab[lab == 255] = 0
    out["ceiling_perfect_grouping_on_a3_mask"] = FE.summary(lab, gt)
    gtp = np.isin(gt.material, C.PLANT_IDS)
    lab2 = np.where(gtp, gt.instances, 0).astype(np.int32)
    lab2[lab2 == 255] = 0
    out["ceiling_perfect_grouping_on_gt_mask"] = FE.summary(lab2, gt)
    out["a3_plant_mask_iou"] = float((plant_gt & gtp).sum() / (plant_gt | gtp).sum())
    out["a3_plant_recall_per_gt_instance"] = {
        int(i): float(plant_gt[gt.instances == i].mean()) for i in range(1, 11)}

    # -- 2. which statistic --------------------------------------------------
    frag, finfo = G.build_fragments(inp)
    n = int(frag.max())
    out["fragments"] = finfo
    maj, _ = frag_majority_instance(frag, gt, n)
    out["fragments_per_gt_instance"] = {
        int(i): int((maj[1:] == i).sum()) for i in list(range(1, 11)) + [255]}

    stats = {}
    for stat in ("step", "secdiff", "plane5"):
        b = G.boundary_residuals(inp, frag, intra=False, statistic=stat)
        s = G.summarise_boundaries(b, n)
        ma, mb = maj[s["pairs"][:, 0]], maj[s["pairs"][:, 1]]
        same = (ma == mb) & (ma > 0)
        diff = (ma != mb) & (ma > 0) & (mb > 0)
        sq_grass = ((ma == 1) & (mb == 255)) | ((mb == 1) & (ma == 255))
        sq_int = (ma == 1) & (mb == 1)
        row = {"n_pairs": int(len(s["n"])), "n_same": int(same.sum()),
               "n_diff": int(diff.sum()), "n_squash_internal": int(sq_int.sum()),
               "n_squash_grass": int(sq_grass.sum())}
        for q in ("p25", "p50", "p75"):
            row[f"auc_{q}_same_vs_diff"] = auc_lower_is_same(s[q], same, diff)
            row[f"auc_{q}_squashint_vs_squashgrass"] = auc_lower_is_same(
                s[q], sq_int, sq_grass)
            row[f"{q}_same_median"] = float(np.median(s[q][same]))
            row[f"{q}_diff_median"] = float(np.median(s[q][diff]))
        stats[stat] = row
        np.savez(os.path.join(C.WORK, f"summary_{stat}.npz"), **s)
    out["boundary_statistics"] = stats
    intra = {st: G.boundary_residuals(inp, frag, intra=True, statistic=st)["resid"]
             for st in ("step", "secdiff", "plane5")}
    out["within_fragment_residual_percentiles_rdu"] = {
        st: {str(p): float(np.percentile(v, p))
             for p in (10, 25, 50, 75, 90, 95, 99)} for st, v in intra.items()}
    out["a1_local_planarity_p10_rdu"] = {str(k): v
                                         for k, v in C.LOCAL_PLANARITY_P10_RDU.items()}

    # -- 3. the oracle edge test --------------------------------------------
    s = dict(np.load(os.path.join(C.WORK, "summary_secdiff.npz")))
    ma, mb = maj[s["pairs"][:, 0]], maj[s["pairs"][:, 1]]
    oracle = (ma == mb) & (ma > 0)
    comp = G.components(n, s["pairs"], oracle)
    labo = C.to_gt_grid_nearest(comp[frag].astype(np.int32))
    out["oracle_edges"] = FE.summary(labo, gt)
    out["oracle_edges"]["note"] = (
        "every adjacent fragment pair that really belongs to one ground-truth "
        "plant is linked and no other pair is. This is the best any method whose "
        "nodes are these fragments and whose edges are these adjacencies could "
        "possibly do; it is an upper bound on the graph, not a result.")

    os.makedirs(C.RESULTS, exist_ok=True)
    p = os.path.join(C.RESULTS, "diagnostics.json")
    json.dump(out, open(p, "w"), indent=1, default=float)
    print(json.dumps(out, indent=1, default=float))
    print("wrote", p)


if __name__ == "__main__":
    main()
