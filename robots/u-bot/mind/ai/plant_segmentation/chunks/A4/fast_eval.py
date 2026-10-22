"""A4 — a vectorised re-implementation of `chunks/A0/eval.py`'s instance metrics.

**A0's `eval.py` is the contract and produces every reported headline number.**
This module exists only because A4 has to score hundreds of candidate label maps
during its sweeps, and `eval.instance_scores` is a Python double loop over
(GT instance x predicted instance) with a full-image boolean op inside it — fine
for the five instances ZeroPlantSeg emits, hopeless for the tens of thousands a
too-tight tolerance produces.

`test_a4.py` asserts this module and `eval.py` agree exactly (F1, TP/FP/FN,
best-IoU-per-GT, fragmentation, grass absorption) on several label maps,
including the degenerate ones. If they ever disagree, `eval.py` is right.
"""
from __future__ import annotations

import os
import sys

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "A0"))
import eval as a0eval  # noqa: E402


def _pair_counts(g, p, ng, npd):
    """Intersection area of every (gt id, pred id) pair, as a sparse triple."""
    key = g.astype(np.int64) * (npd + 1) + p.astype(np.int64)
    k, c = np.unique(key, return_counts=True)
    return (k // (npd + 1)).astype(np.int64), (k % (npd + 1)).astype(np.int64), c


def instance_scores(pred_inst, gt, iou_threshold=a0eval.INSTANCE_MATCH_IOU):
    scoreable = (gt.material != a0eval.UNLABELLED) \
        & (gt.instances != a0eval.GRASS_UNRESOLVED)
    g = np.where(scoreable, gt.instances, 0).astype(np.int64)
    p = np.where(scoreable, pred_inst, 0).astype(np.int64)
    gids = np.array([v for v in np.unique(g) if v != 0], np.int64)
    pids = np.array([v for v in np.unique(p) if v != 0], np.int64)
    if gids.size == 0 or pids.size == 0:
        return {"iou_threshold": iou_threshold, "n_gt": int(gids.size),
                "n_pred": int(pids.size), "tp": 0, "fp": int(pids.size),
                "fn": int(gids.size), "precision": 0.0, "recall": 0.0, "f1": 0.0,
                "matches": [], "best_iou_per_gt": {}, "unmatched_gt": gids.tolist()}

    gi, pi, inter = _pair_counts(g, p, gids.max(), int(p.max()))
    keep = (gi != 0) & (pi != 0)
    gi, pi, inter = gi[keep], pi[keep], inter[keep]
    garea = np.bincount(g.ravel(), minlength=int(g.max()) + 1)
    parea = np.bincount(p.ravel(), minlength=int(p.max()) + 1)
    iou = inter / (garea[gi] + parea[pi] - inter)

    order = np.lexsort((pi, gi, -iou))
    gi, pi, iou = gi[order], pi[order], iou[order]
    mg, mp, matches = set(), set(), []
    for a, b, v in zip(gi, pi, iou):
        if v < iou_threshold:
            break
        a, b = int(a), int(b)
        if a in mg or b in mp:
            continue
        mg.add(a); mp.add(b)
        matches.append({"gt": a, "pred": b, "iou": float(v)})
    tp = len(matches)
    prec = tp / len(pids)
    rec = tp / len(gids)
    f1 = 2 * prec * rec / (prec + rec) if prec + rec else 0.0
    best = {}
    for a, b, v in zip(gi, pi, iou):
        a = int(a)
        if a not in best or v > best[a]["iou"]:
            best[a] = {"iou": float(v), "pred": int(b)}
    return {"iou_threshold": iou_threshold, "n_gt": int(len(gids)),
            "n_pred": int(len(pids)), "tp": tp, "fp": int(len(pids) - tp),
            "fn": int(len(gids) - tp), "precision": prec, "recall": rec, "f1": f1,
            "matches": matches, "best_iou_per_gt": best,
            "unmatched_gt": sorted(set(int(v) for v in gids) - mg)}


def fragmentation(pred_inst, gt, gt_instance=1, min_px=200):
    m = gt.instances == gt_instance
    ids, counts = np.unique(pred_inst[m], return_counts=True)
    parts = {int(i): int(c) for i, c in zip(ids, counts) if i != 0 and c >= min_px}
    return {"gt_instance": int(gt_instance), "n_pred_parts": len(parts),
            "parts": parts, "min_px": min_px}


def grass_absorption(pred_inst, gt, crop_pred_id=None):
    return a0eval.grass_absorption(pred_inst, gt, crop_pred_id)


def summary(pred_inst, gt, iou_threshold=a0eval.INSTANCE_MATCH_IOU):
    i = instance_scores(pred_inst, gt, iou_threshold)
    f = fragmentation(pred_inst, gt)
    a = grass_absorption(pred_inst, gt)
    return {"f1": i["f1"], "precision": i["precision"], "recall": i["recall"],
            "tp": i["tp"], "fp": i["fp"], "fn": i["fn"], "n_pred": i["n_pred"],
            "squash_best_iou": i["best_iou_per_gt"].get(1, {"iou": 0.0})["iou"],
            "squash_parts": f["n_pred_parts"],
            "grass_absorbed": a["absorbed_fraction"],
            "matched_gt": sorted(m["gt"] for m in i["matches"])}
