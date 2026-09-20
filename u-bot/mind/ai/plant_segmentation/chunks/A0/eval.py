"""A0 — the scoring contract every later chunk reports against.

    from chunks.A0.eval import load_gt, load_prediction, score, print_report
    gt   = load_gt()
    pred = load_prediction(material=..., instances=..., contacts=...)
    print_report(score(pred, gt))

CLI:
    .venv/bin/python ../chunks/A0/eval.py --zps        # score the ZeroPlantSeg baseline
    .venv/bin/python ../chunks/A0/eval.py --material X.png --instances Y.png

Ground truth grid
-----------------
Labels live on a 768x1024 grid, a uniform 3.90625x downsample of the native
3000x4000 photograph (identical in x and y, so no aspect distortion). That is
the resolution ZeroPlantSeg runs at, so the recorded baseline is scored without
any resampling at all. A prediction on any other grid is resampled here with
nearest-neighbour — label maps must never be interpolated — and the report says
so explicitly.

Scoring rules
-------------
* Per-class IoU is computed only over pixels the ground truth labels. GT
  `unlabelled` pixels are excluded from both intersection and union for every
  class, so an honest hole in the labels cannot be scored as either a hit or a
  miss.
* Instance matching is greedy, highest IoU first, one-to-one, with a match
  accepted at IoU >= `iou_threshold` (default 0.5). The threshold is the only
  convention here and is a keyword argument, so it is swappable and any chunk
  may report a sweep instead of a single number. Instance IoU ignores GT
  `unlabelled` pixels and GT grass pixels (see below).
* Grass instances are unresolved in the ground truth: grass is clonal and the
  blades interleave below the resolution of this grid, so which blade belongs to
  which tussock is not knowable from this image. All grass pixels carry instance
  id 255 and are excluded from instance matching. The specific failure that
  matters — grass being absorbed into the squash — is reported separately as
  `grass_absorbed_into_crop`, the fraction of GT grass pixels that a prediction
  assigns to the instance it matched to the squash.
* Contact-point error is Euclidean distance in GT-grid pixels. The headline
  number covers GT points tagged `visible`; this image has none (every stem
  disappears under straw mulch), so the report also gives the error over
  `under_straw` points, flagged as not-scoreable because those GT points are
  themselves estimates.
"""
from __future__ import annotations

import argparse
import json
import os
from dataclasses import dataclass, field

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
GT_DIR = os.path.join(ROOT, "groundtruth")

CLASSES = ["unlabelled", "squash_leaf", "squash_petiole", "grass",
           "broadleaf_weed", "straw", "soil", "fruit", "other"]
CID = {c: i for i, c in enumerate(CLASSES)}
UNLABELLED = 0
GRASS_UNRESOLVED = 255

# --- constants, registered in CONSTANTS.md -----------------------------------
INSTANCE_MATCH_IOU = 0.5      # (c) convention; keyword argument, swappable


@dataclass
class GroundTruth:
    material: np.ndarray            # (H, W) uint8, class ids
    instances: np.ndarray           # (H, W) uint8, instance ids; 255 = unresolved grass
    contacts: dict
    meta: dict
    shape: tuple = field(init=False)

    def __post_init__(self):
        self.shape = self.material.shape


@dataclass
class Prediction:
    material: np.ndarray | None = None
    instances: np.ndarray | None = None
    contacts: dict | None = None     # {instance_id: (x, y)} on the GT grid
    name: str = "prediction"
    resampled_from: tuple | None = None


def load_gt(gt_dir: str = GT_DIR) -> GroundTruth:
    mat = np.array(Image.open(os.path.join(gt_dir, "plants_material.png")))
    inst = np.array(Image.open(os.path.join(gt_dir, "plants_instances.png")))
    contacts = json.load(open(os.path.join(gt_dir, "plants_contacts.json")))
    meta = json.load(open(os.path.join(gt_dir, "plants_gt.json")))
    return GroundTruth(mat, inst, contacts, meta)


def to_gt_grid(arr: np.ndarray, shape: tuple) -> tuple[np.ndarray, tuple | None]:
    """Nearest-neighbour resample a label map onto the GT grid.

    Returns (resampled, original_shape_if_changed). Never interpolates: a label
    map has no meaningful average.
    """
    if arr.shape == shape:
        return arr, None
    src = arr.shape
    im = Image.fromarray(arr.astype(np.int32), mode="I")
    out = np.array(im.resize((shape[1], shape[0]), Image.NEAREST))
    return out.astype(arr.dtype), src


def load_prediction(material=None, instances=None, contacts=None, name="prediction",
                    gt: GroundTruth | None = None) -> Prediction:
    gt = gt or load_gt()
    resampled = None
    if isinstance(material, str):
        material = np.array(Image.open(material))
    if isinstance(instances, str):
        instances = np.array(Image.open(instances))
    if material is not None:
        material, r = to_gt_grid(material, gt.shape)
        resampled = resampled or r
    if instances is not None:
        instances, r = to_gt_grid(instances, gt.shape)
        resampled = resampled or r
    return Prediction(material, instances, contacts, name, resampled)


# ---------------------------------------------------------------- material ---
def per_class_iou(pred_material, gt: GroundTruth):
    valid = gt.material != UNLABELLED
    out = {}
    for c in CLASSES:
        if c == "unlabelled":
            continue
        i = CID[c]
        g = (gt.material == i) & valid
        p = (pred_material == i) & valid
        inter = int((g & p).sum())
        union = int((g | p).sum())
        out[c] = {
            "iou": (inter / union) if union else None,
            "gt_px": int(g.sum()),
            "pred_px": int(p.sum()),
            "intersection": inter,
        }
    ious = [v["iou"] for v in out.values() if v["iou"] is not None and v["gt_px"] > 0]
    return out, (float(np.mean(ious)) if ious else None)


def confusion(pred_material, gt: GroundTruth):
    valid = gt.material != UNLABELLED
    n = len(CLASSES)
    m = np.zeros((n, n), np.int64)
    g = gt.material[valid].astype(int)
    p = np.clip(pred_material[valid].astype(int), 0, n - 1)
    np.add.at(m, (g, p), 1)
    return m


# ---------------------------------------------------------------- instances --
def instance_scores(pred_inst, gt: GroundTruth, iou_threshold=INSTANCE_MATCH_IOU):
    """Greedy one-to-one matching by IoU, accepted at >= iou_threshold."""
    scoreable = (gt.material != UNLABELLED) & (gt.instances != GRASS_UNRESOLVED)
    g = np.where(scoreable, gt.instances, 0)
    p = np.where(scoreable, pred_inst, 0)
    gids = [int(v) for v in np.unique(g) if v != 0]
    pids = [int(v) for v in np.unique(p) if v != 0]

    pairs = []
    for gi in gids:
        gm = g == gi
        for pi in pids:
            pm = p == pi
            inter = int((gm & pm).sum())
            if not inter:
                continue
            union = int((gm | pm).sum())
            pairs.append((inter / union, gi, pi))
    pairs.sort(reverse=True)

    matched_g, matched_p, matches = set(), set(), []
    for iou, gi, pi in pairs:
        if iou < iou_threshold or gi in matched_g or pi in matched_p:
            continue
        matched_g.add(gi)
        matched_p.add(pi)
        matches.append({"gt": gi, "pred": pi, "iou": iou})

    tp = len(matches)
    prec = tp / len(pids) if pids else 0.0
    rec = tp / len(gids) if gids else 0.0
    f1 = 2 * prec * rec / (prec + rec) if prec + rec else 0.0
    best = {}
    for iou, gi, pi in pairs:
        if gi not in best or iou > best[gi][0]:
            best[gi] = (iou, pi)
    return {
        "iou_threshold": iou_threshold,
        "n_gt": len(gids), "n_pred": len(pids), "tp": tp,
        "fp": len(pids) - tp, "fn": len(gids) - tp,
        "precision": prec, "recall": rec, "f1": f1,
        "matches": matches,
        "best_iou_per_gt": {gi: {"iou": v[0], "pred": v[1]} for gi, v in best.items()},
        "unmatched_gt": sorted(set(gids) - matched_g),
    }


def fragmentation(pred_inst, gt: GroundTruth, gt_instance=1, min_px=200):
    """How many predicted instances the given GT instance is split across."""
    m = gt.instances == gt_instance
    ids, counts = np.unique(pred_inst[m], return_counts=True)
    parts = {int(i): int(c) for i, c in zip(ids, counts) if i != 0 and c >= min_px}
    return {"gt_instance": gt_instance, "n_pred_parts": len(parts), "parts": parts,
            "min_px": min_px}


def grass_absorption(pred_inst, gt: GroundTruth, crop_pred_id=None):
    """Fraction of GT grass pixels assigned to the predicted crop instance."""
    grass = gt.instances == GRASS_UNRESOLVED
    total = int(grass.sum())
    if crop_pred_id is None:
        ids, counts = np.unique(pred_inst[gt.instances == 1], return_counts=True)
        ids, counts = ids[ids != 0], counts[ids != 0]
        crop_pred_id = int(ids[counts.argmax()]) if len(ids) else None
    if crop_pred_id is None:
        return {"crop_pred_id": None, "gt_grass_px": total, "absorbed_px": 0,
                "absorbed_fraction": 0.0}
    absorbed = int((grass & (pred_inst == crop_pred_id)).sum())
    return {"crop_pred_id": crop_pred_id, "gt_grass_px": total,
            "absorbed_px": absorbed,
            "absorbed_fraction": absorbed / total if total else 0.0}


# ----------------------------------------------------------------- contacts --
def contact_errors(pred_contacts, gt: GroundTruth, matches=None):
    """Euclidean error in GT-grid px, per GT instance, grouped by GT status."""
    if not pred_contacts:
        return {"scoreable": {"n": 0, "note": "prediction supplied no contact points"},
                "per_status": {}, "points": []}
    lookup = {m["gt"]: m["pred"] for m in (matches or [])}
    rows = []
    for e in gt.contacts["instances"]:
        gid = e["id"]
        key = lookup.get(gid, gid)          # match by identity if no matching given
        pt = pred_contacts.get(key, pred_contacts.get(str(key)))
        if pt is None:
            rows.append({"gt": gid, "status": e["status"], "error_px": None,
                         "reason": "no predicted point for the matched instance"})
            continue
        d = float(np.hypot(pt[0] - e["point"][0], pt[1] - e["point"][1]))
        rows.append({"gt": gid, "status": e["status"], "error_px": d,
                     "gt_localisation": e.get("localisation", "observed")})
    by_status = {}
    for st in gt.contacts["status_values"]:
        es = [r["error_px"] for r in rows if r["status"] == st and r["error_px"] is not None]
        by_status[st] = {"n": len(es),
                         "mean_px": float(np.mean(es)) if es else None,
                         "median_px": float(np.median(es)) if es else None,
                         "max_px": float(np.max(es)) if es else None}
    return {"scoreable": by_status.get("visible", {"n": 0}),
            "per_status": by_status, "points": rows}


# -------------------------------------------------------------------- score --
def score(pred: Prediction, gt: GroundTruth, iou_threshold=INSTANCE_MATCH_IOU):
    out = {"name": pred.name, "iou_threshold": iou_threshold,
           "gt_grid": list(gt.shape),
           "resampled_from": list(pred.resampled_from) if pred.resampled_from else None,
           "unlabelled_fraction": gt.meta["unlabelled_fraction"]}
    if pred.material is not None:
        cls, miou = per_class_iou(pred.material, gt)
        out["per_class_iou"] = cls
        out["mean_iou"] = miou
        out["confusion"] = confusion(pred.material, gt).tolist()
    if pred.instances is not None:
        out["instances"] = instance_scores(pred.instances, gt, iou_threshold)
        out["squash_fragmentation"] = fragmentation(pred.instances, gt, 1)
        out["grass_absorbed_into_crop"] = grass_absorption(pred.instances, gt)
        out["contacts"] = contact_errors(pred.contacts, gt,
                                         out["instances"]["matches"])
    elif pred.contacts:
        out["contacts"] = contact_errors(pred.contacts, gt)
    return out


def print_report(r):
    print(f"\n=== {r['name']} ===")
    print(f"GT grid {r['gt_grid'][1]}x{r['gt_grid'][0]}"
          + (f"  (prediction nearest-resampled from "
             f"{r['resampled_from'][1]}x{r['resampled_from'][0]})"
             if r["resampled_from"] else "  (native GT grid, no resampling)"))
    print(f"GT unlabelled and excluded from scoring: "
          f"{100*r['unlabelled_fraction']:.2f}% of pixels")
    if "per_class_iou" in r:
        print("\nPer-class IoU")
        print(f"  {'class':16s} {'IoU':>7s} {'GT px':>9s} {'pred px':>9s}")
        for c, v in r["per_class_iou"].items():
            iou = "  n/a  " if v["iou"] is None else f"{v['iou']:7.4f}"
            print(f"  {c:16s} {iou} {v['gt_px']:9d} {v['pred_px']:9d}"
                  + ("   (class absent from GT)" if v["gt_px"] == 0 else ""))
        print(f"  {'mean IoU':16s} {r['mean_iou']:7.4f}   (classes present in GT)")
    if "instances" in r:
        i = r["instances"]
        print(f"\nInstances (match rule: greedy 1-1, IoU >= {i['iou_threshold']}; "
              f"GT grass excluded as unresolved)")
        print(f"  GT {i['n_gt']}   pred {i['n_pred']}   TP {i['tp']}  FP {i['fp']}  FN {i['fn']}")
        print(f"  precision {i['precision']:.4f}  recall {i['recall']:.4f}  F1 {i['f1']:.4f}")
        print("  best IoU per GT instance: "
              + ", ".join(f"{k}:{v['iou']:.3f}" for k, v in
                          sorted(i["best_iou_per_gt"].items())))
        f = r["squash_fragmentation"]
        print(f"  squash split across {f['n_pred_parts']} predicted instance(s) "
              f"(>= {f['min_px']} px): {f['parts']}")
        g = r["grass_absorbed_into_crop"]
        print(f"  grass absorbed into predicted crop instance {g['crop_pred_id']}: "
              f"{g['absorbed_px']}/{g['gt_grass_px']} px "
              f"= {100*g['absorbed_fraction']:.1f}% of GT grass")
    if "contacts" in r:
        c = r["contacts"]
        print("\nContact points (error in GT-grid px)")
        if not c["per_status"]:
            print(f"  {c['scoreable'].get('note', 'no points')}")
        else:
            for st, v in c["per_status"].items():
                if v["n"] == 0:
                    print(f"  {st:14s} n=0")
                else:
                    print(f"  {st:14s} n={v['n']:2d}  mean {v['mean_px']:.1f}  "
                          f"median {v['median_px']:.1f}  max {v['max_px']:.1f}")
            if c["per_status"].get("visible", {}).get("n", 0) == 0:
                print("  NOTE: no GT point is tagged `visible` in this image — every "
                      "stem disappears under straw mulch. The headline "
                      "contact-point metric is therefore empty here; the "
                      "`under_straw` numbers are against estimated GT points and "
                      "are diagnostic only.")
    print()


# ------------------------------------------------------------------ ZPS load --
def load_zps_baseline(gt: GroundTruth):
    """ZeroPlantSeg output as published: plant instance map at 768x1024."""
    p = os.path.join(ROOT, "ZeroPlantSeg/output_p/plant_instance/squash/test/plants.png")
    inst = np.array(Image.open(p)).astype(np.int32)
    return load_prediction(instances=inst, name="ZeroPlantSeg (squash.yaml, eps=100)",
                           gt=gt)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--zps", action="store_true")
    ap.add_argument("--material")
    ap.add_argument("--instances")
    ap.add_argument("--contacts")
    ap.add_argument("--iou", type=float, default=INSTANCE_MATCH_IOU)
    ap.add_argument("--json", help="write the full score dict here")
    a = ap.parse_args()
    gt = load_gt()
    if a.zps:
        pred = load_zps_baseline(gt)
    else:
        contacts = json.load(open(a.contacts)) if a.contacts else None
        pred = load_prediction(a.material, a.instances, contacts, gt=gt)
    r = score(pred, gt, a.iou)
    print_report(r)
    if a.json:
        json.dump(r, open(a.json, "w"), indent=1)


if __name__ == "__main__":
    main()
