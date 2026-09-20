"""A3 — what `height_above_soil` knows, measured against the A0 ground truth.

A2 checked its height field against five hand-placed boxes and reported straw 0
sigma, clover 7, fruit 22, grass 52, squash leaf 93. A0 did not exist yet. This
re-runs that check over **every labelled pixel**, which is the first time the A2
product has been scored against labels rather than eyeballed, and then asks the
question A3 actually needs answered: how much of the grass/squash decision can
height alone carry?

Everything is in **datum sigma** (`a2_api.height_in_sigma()`), which is
scale-free, and every pixel is weighted by the reliability of the datum beneath
it (`height_sigma`), as A2's FINDINGS asked A3 to do.

Separability is reported as the AUC of a one-feature threshold classifier, both
per-pixel and per-SAM-region, with the caveat that a per-pixel AUC over hundreds
of thousands of correlated pixels has no useful confidence interval — it
describes this image, it does not generalise.
"""
from __future__ import annotations

import json
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import a3_common as A  # noqa: E402
import eval as a0eval  # noqa: E402


def auc(pos, neg, w_pos=None, w_neg=None):
    """Weighted AUC by rank: **P(a random `pos` value is HIGHER than a random
    `neg` value)**, ties counted as a half. 0.5 is no information; a value far
    from 0.5 in either direction is separation, so the usable summary is
    `max(auc, 1 - auc)`."""
    x = np.concatenate([pos, neg])
    w = np.concatenate([np.ones_like(pos) if w_pos is None else w_pos,
                        np.zeros_like(neg) if w_neg is None else w_neg * 0])
    lab = np.concatenate([np.ones(len(pos)), np.zeros(len(neg))])
    wt = np.concatenate([np.ones(len(pos)) if w_pos is None else w_pos,
                         np.ones(len(neg)) if w_neg is None else w_neg])
    o = np.argsort(x, kind="mergesort")
    x, lab, wt = x[o], lab[o], wt[o]
    # average ranks for ties
    ranks = np.empty(len(x))
    i = 0
    cum = np.concatenate([[0], np.cumsum(wt)])
    while i < len(x):
        j = i
        while j + 1 < len(x) and x[j + 1] == x[i]:
            j += 1
        ranks[i:j + 1] = (cum[i] + cum[j + 1] + 1) / 2
        i = j + 1
    P = wt[lab == 1].sum()
    N = wt[lab == 0].sum()
    if P == 0 or N == 0:
        return None
    s = (ranks[lab == 1] * wt[lab == 1]).sum()
    return float((s - P * (P + 1) / 2) / (P * N))


def main():
    gt = a0eval.load_gt()
    a2 = A.a2_on_gt_grid()
    h = a2["h_sigma"]
    sd = a2["sigma_datum"]
    # reliability weight: how much of the height budget is the datum's own
    # roughness rather than the local interpolation uncertainty
    rel = sd ** 2 / (sd ** 2 + np.nan_to_num(a2["height_sigma"]) ** 2)
    valid = a2["valid"] & np.isfinite(h)

    res = {"units": "datum sigma (A2 height_in_sigma)",
           "sigma_datum_rdu": sd,
           "datum": "straw mulch surface, not bare soil (A2)",
           "scale_confidence": a2["scale_confidence"],
           "valid_fraction": float(valid.mean()),
           "per_class": {}, "a2_hand_placed_boxes": {
               "straw": 0, "broadleaf_weed(clover)": 7, "fruit": 22,
               "grass": 52, "squash_leaf": 93}}

    for c in a0eval.CLASSES[1:]:
        m = (gt.material == a0eval.CID[c]) & valid
        if m.sum() < 50:
            res["per_class"][c] = {"px": int(m.sum()), "note": "too few pixels"}
            continue
        v = h[m]
        w = rel[m]
        q = np.percentile(v, [5, 25, 50, 75, 95])
        res["per_class"][c] = {
            "px": int(m.sum()),
            "median_sigma": float(np.median(v)),
            "weighted_mean_sigma": float((v * w).sum() / w.sum()),
            "p5": float(q[0]), "p25": float(q[1]), "p50": float(q[2]),
            "p75": float(q[3]), "p95": float(q[4]),
            "mean_datum_reliability": float(w.mean()),
            "observed_datum_fraction": float(a2["observed"][m].mean()),
        }

    def pair(a, b, subsample=40000, seed=0):
        rng = np.random.default_rng(seed)
        ma = (gt.material == a0eval.CID[a]) & valid
        mb = (gt.material == a0eval.CID[b]) & valid
        va, vb = h[ma], h[mb]
        if len(va) > subsample:
            va = rng.choice(va, subsample, replace=False)
        if len(vb) > subsample:
            vb = rng.choice(vb, subsample, replace=False)
        return auc(va, vb)

    def sep(v):
        return None if v is None else float(max(v, 1 - v))

    res["pairwise_auc_height_only"] = {
        "grass_vs_squash_leaf": pair("grass", "squash_leaf"),
        "grass_vs_squash_petiole": pair("grass", "squash_petiole"),
        "grass_vs_straw": pair("grass", "straw"),
        "grass_vs_broadleaf_weed": pair("grass", "broadleaf_weed"),
        "squash_leaf_vs_straw": pair("squash_leaf", "straw"),
        "broadleaf_weed_vs_straw": pair("broadleaf_weed", "straw"),
        "note": "P(height of the FIRST class > height of the second). 0.5 is "
                "no information; separability is max(auc, 1-auc). Per-pixel "
                "over correlated pixels, so it describes this image and "
                "carries no confidence interval.",
    }

    res["pairwise_separability_height_only"] = {
        k: sep(v) for k, v in res["pairwise_auc_height_only"].items()
        if k != "note"}

    # region-level version, on the A3 partition, which is the granularity the
    # classifiers actually decide at
    for part in ("a3", "a3f"):
        p = os.path.join(A.WORK, f"regions_{part}.npy")
        if not os.path.exists(p):
            continue
        regions = np.load(p)
        feats = A.compute_features(regions, a2=a2, with_texture=False)
        y, _, _ = A.region_gt_labels(regions, gt)
        y = y[feats.ids - 1]
        hcol = feats.names.index("h_wmean")
        hv = feats.X[:, hcol]
        aw = feats.area

        def rpair(a, b):
            ma = y == a0eval.CID[a]
            mb = y == a0eval.CID[b]
            if ma.sum() < 3 or mb.sum() < 3:
                return None
            return auc(hv[ma], hv[mb], aw[ma], aw[mb])

        res.setdefault("region_level_auc", {})[part] = {
            "n_regions": int(regions.max()),
            "grass_vs_squash_leaf": rpair("grass", "squash_leaf"),
            "grass_vs_squash_petiole": rpair("grass", "squash_petiole"),
            "grass_vs_straw": rpair("grass", "straw"),
            "region_counts": {c: int((y == a0eval.CID[c]).sum())
                              for c in A.PREDICT_CLASSES},
        }
        res["region_level_auc"][part]["separability"] = {
            k: sep(v) for k, v in res["region_level_auc"][part].items()
            if isinstance(v, float)}

    out = os.path.join(HERE, "results", "height_report.json")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    json.dump(res, open(out, "w"), indent=1)
    print(json.dumps({k: v for k, v in res.items()
                      if k != "per_class"}, indent=1))
    print("\nper class (median height, datum sigma):")
    for c, v in res["per_class"].items():
        if "median_sigma" in v:
            print(f"  {c:16s} {v['median_sigma']:8.1f}  "
                  f"[p25 {v['p25']:7.1f} .. p75 {v['p75']:7.1f}]  "
                  f"{v['px']:7d} px  datum reliability {v['mean_datum_reliability']:.2f}")
    print("wrote", out)


if __name__ == "__main__":
    main()
