"""A3 approaches 1 and 2 — a geometric shape prior over SAM regions, and the
same prior plus A2's `height_above_soil`.

The roadmap's Constants table says the shape-prior thresholds are "fitted on
ground truth, reported with margins" — category (c). Fitting on ground truth
and then reporting the score on the same pixels would be worthless, so:

* the model is a **shallow decision tree** (a set of thresholds, printable, and
  therefore reportable with margins), plus a random forest reported alongside
  purely to show what the tree's simplicity costs;
* every headline number is **out-of-fold**: the frame is cut into a 4x4 grid of
  spatial blocks, whole blocks are dealt to 4 folds, and each region's
  prediction comes from a tree that never saw its block. Regions are
  contiguous, so a random split would leave a region's own neighbours (same
  leaf, same tussock, same lighting) in the training set;
* the in-sample (resubstitution) score is reported next to it, so the size of
  the overfitting gap is visible rather than implied.

Training targets are the majority ground-truth class per region over labelled
pixels; regions that are more than half `unlabelled` are excluded from training
but still predicted and still scored.

Sample weight is region area, because the metric is pixel IoU.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import a3_common as A  # noqa: E402
import eval as a0eval  # noqa: E402

from sklearn.ensemble import RandomForestClassifier  # noqa: E402
from sklearn.tree import DecisionTreeClassifier, export_text  # noqa: E402

N_CV_SEEDS = 5          # (c) how many block-to-fold deals the headline averages
TREE_DEPTH = 4          # (c) convention: a shape prior is meant to be a handful
                        #     of thresholds a human can read. Swept in run().
MIN_LEAF_FRAC = 0.01    # (c) a leaf must carry >=1 % of the training weight,
                        #     so no threshold is fitted to a single region.


def region_data(regions, gt, a2=None, with_texture=True):
    feats = A.compute_features(regions, a2=a2, with_texture=with_texture)
    y, purity, lfrac = A.region_gt_labels(regions, gt)
    y = y[feats.ids - 1]
    purity = purity[feats.ids - 1]
    lfrac = lfrac[feats.ids - 1]
    folds = A.blocked_folds(feats.centroid)
    return feats, y, purity, lfrac, folds


def _fit(model, Xtr, ytr, wtr):
    model.fit(Xtr, ytr, sample_weight=wtr)
    return model


def cv_predict(X, y, w, folds, make_model):
    """Out-of-fold predictions. Every region is predicted by a model that never
    saw any region in its spatial block."""
    pred = np.full(len(y), -1, int)
    trained = []
    for f in np.unique(folds):
        tr = (folds != f) & (y > 0)
        te = folds == f
        if tr.sum() < 10 or len(np.unique(y[tr])) < 2:
            continue
        m = _fit(make_model(), X[tr], y[tr], w[tr])
        pred[te] = m.predict(X[te])
        trained.append(m)
    # any region never predicted (empty fold) falls back to the global majority
    if (pred < 0).any():
        maj = int(np.bincount(y[y > 0], weights=w[y > 0]).argmax())
        pred[pred < 0] = maj
    return pred, trained


def _agg(summaries):
    """Mean and spread of a list of per-seed summaries."""
    keys = [k for k in summaries[0] if k != "per_class_iou"]
    out = {}
    for k in keys:
        v = [s[k] for s in summaries if s[k] is not None]
        out[k] = float(np.mean(v)) if v else None
        out[k + "_sd"] = float(np.std(v)) if v else None
    cls = {}
    for c in summaries[0]["per_class_iou"]:
        v = [s["per_class_iou"][c] for s in summaries
             if s["per_class_iou"][c] is not None]
        cls[c] = float(np.mean(v)) if v else None
        cls[c + "_sd"] = float(np.std(v)) if v else None
    out["per_class_iou"] = cls
    out["n_seeds"] = len(summaries)
    return out


def run_variant(name, groups, feats, y, w, folds_by_seed, regions, gt,
                depth=TREE_DEPTH, results=None, save=False):
    """Score one feature set. `folds_by_seed` is a list of fold assignments;
    the headline is the mean over all of them, because a single block-to-fold
    deal is itself a lucky or unlucky draw (seed 0 alone reads 0.09 higher than
    the mean for approach 2)."""
    X, names = feats.subset(groups)
    minleaf = max(1, int(MIN_LEAF_FRAC * len(y)))

    def tree():
        return DecisionTreeClassifier(max_depth=depth, min_samples_leaf=minleaf,
                                      random_state=0)

    def forest():
        return RandomForestClassifier(n_estimators=300, max_depth=None,
                                      min_samples_leaf=2, random_state=0,
                                      n_jobs=-1)

    out = {"name": name, "groups": list(groups), "n_features": len(names),
           "features": names, "tree_depth": depth}

    t0 = time.time()
    tree_s, rf_s = [], []
    for si, folds in enumerate(folds_by_seed):
        p_tree, _ = cv_predict(X, y, w, folds, tree)
        m_tree = A.assemble(regions, feats.ids, p_tree)
        tree_s.append(A.summarise(A.score_map(m_tree, gt, f"{name}/tree/s{si}")))
        if save and si == 0:
            A.save_pred(f"{name}_tree_cv", m_tree)
    out["seconds_cv_tree_all_seeds"] = time.time() - t0
    out["tree_cv"] = _agg(tree_s)
    out["tree_cv_per_seed"] = [s["mean_iou"] for s in tree_s]

    t0 = time.time()
    for si, folds in enumerate(folds_by_seed):
        p_rf, _ = cv_predict(X, y, w, folds, forest)
        m_rf = A.assemble(regions, feats.ids, p_rf)
        rf_s.append(A.summarise(A.score_map(m_rf, gt, f"{name}/rf/s{si}")))
        if save and si == 0:
            A.save_pred(f"{name}_rf_cv", m_rf)
    out["seconds_cv_forest_all_seeds"] = time.time() - t0
    out["forest_cv"] = _agg(rf_s)
    out["forest_cv_per_seed"] = [s["mean_iou"] for s in rf_s]

    # in-sample, to show the overfitting gap rather than hide it
    tr = y > 0
    m = _fit(tree(), X[tr], y[tr], w[tr])
    out["tree_insample"] = A.summarise(
        A.score_map(A.assemble(regions, feats.ids, m.predict(X)), gt,
                    f"{name}/tree/in"))
    out["tree_rules"] = export_text(m, feature_names=names, max_depth=depth)
    out["tree_full_model_classes"] = [a0eval.CLASSES[c] for c in m.classes_]
    rf = _fit(forest(), X[tr], y[tr], w[tr])
    out["forest_importance"] = dict(sorted(
        zip(names, [float(v) for v in rf.feature_importances_]),
        key=lambda kv: -kv[1]))

    if results is not None:
        results[name] = out
    print(f"{name:34s} tree CV mIoU {out['tree_cv']['mean_iou']:.4f}"
          f" +-{out['tree_cv']['mean_iou_sd']:.4f}"
          f"  (in-sample {out['tree_insample']['mean_iou']:.4f})   "
          f"forest CV {out['forest_cv']['mean_iou']:.4f}"
          f" +-{out['forest_cv']['mean_iou_sd']:.4f}   "
          f"grass->squash {100*out['tree_cv']['grass_as_squash']:.1f}%")
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--partition", default="a3f", help="a3 | a3f | a0")
    ap.add_argument("--out", default=None)
    a = ap.parse_args()

    gt = a0eval.load_gt()
    regions = np.load(os.path.join(A.WORK, f"regions_{a.partition}.npy")) \
        if a.partition != "a0" else np.load(
            os.path.join(A.ROOT, "chunks/A0/work/regions.npy"))
    print(f"partition {a.partition}: {regions.max()} regions")

    a2 = A.a2_on_gt_grid()
    t0 = time.time()
    feats, y, purity, lfrac, folds = region_data(regions, gt, a2=a2)
    folds_by_seed = [A.blocked_folds(feats.centroid, seed=s_) for s_ in range(N_CV_SEEDS)]
    t_feat = time.time() - t0
    w = feats.area.astype(float)
    print(f"features: {feats.X.shape} in {t_feat:.1f}s; "
          f"{int((y > 0).sum())}/{len(y)} regions have a majority class")

    results = {"partition": a.partition, "n_regions": int(regions.max()),
               "seconds_features": t_feat,
               "feature_groups": {g: [n for n in feats.names
                                      if feats.group_of[n] == g]
                                  for g in A.FEATURE_GROUPS},
               "cv": {"design": "spatial 4x4 blocks dealt to 4 folds",
                      "blocks": list(A.CV_BLOCKS), "n_folds": A.N_FOLDS},
               "a2": {"datum": a2["datum"][:60],
                      "scale_confidence": a2["scale_confidence"],
                      "sigma_datum_rdu": a2["sigma_datum"]},
               "variants": {}}

    # oracle ceiling of this partition
    yy = np.where(y < 0, a0eval.CID["straw"], y)
    results["partition_ceiling"] = A.summarise(
        A.score_map(A.assemble(regions, feats.ids, yy), gt, "oracle"))
    print(f"partition ceiling (majority GT class per region): "
          f"{results['partition_ceiling']['mean_iou']:.4f}")

    V = results["variants"]
    # --- the two briefed approaches
    run_variant("approach1_shape", ("SHAPE", "SIZE"), feats, y, w, folds_by_seed,
                regions, gt, results=V, save=True)
    run_variant("approach2_shape_height", ("SHAPE", "SIZE", "HEIGHT"), feats, y, w,
                folds_by_seed, regions, gt, results=V, save=True)
    # --- ablations
    run_variant("abl_shape_scalefree", ("SHAPE",), feats, y, w, folds_by_seed, regions, gt,
                results=V)
    run_variant("abl_height_only", ("HEIGHT",), feats, y, w, folds_by_seed, regions, gt,
                results=V, save=True)
    run_variant("abl_size_only", ("SIZE",), feats, y, w, folds_by_seed, regions, gt,
                results=V)
    run_variant("abl_colour_only", ("COLOUR",), feats, y, w, folds_by_seed, regions, gt,
                results=V, save=True)
    run_variant("abl_texture_only", ("TEXTURE",), feats, y, w, folds_by_seed, regions, gt,
                results=V)
    run_variant("abl_colour_height", ("COLOUR", "HEIGHT"), feats, y, w, folds_by_seed,
                regions, gt, results=V)
    run_variant("abl_shape_colour", ("SHAPE", "SIZE", "COLOUR"), feats, y, w,
                folds_by_seed, regions, gt, results=V)
    run_variant("abl_shape_colour_height", ("SHAPE", "SIZE", "COLOUR", "HEIGHT"),
                feats, y, w, folds_by_seed, regions, gt, results=V, save=True)
    run_variant("abl_all_handcrafted",
                ("SHAPE", "SIZE", "COLOUR", "HEIGHT", "TEXTURE"),
                feats, y, w, folds_by_seed, regions, gt, results=V, save=True)

    # --- tree-depth sweep on the two briefed approaches (the (c) constant)
    sweep = {}
    for d in (2, 3, 4, 6, 8):
        for nm, grp in (("approach1_shape", ("SHAPE", "SIZE")),
                        ("approach2_shape_height", ("SHAPE", "SIZE", "HEIGHT"))):
            X, _ = feats.subset(grp)
            vals = []
            for folds in folds_by_seed:
                p, _ = cv_predict(
                    X, y, w, folds,
                    lambda d=d: DecisionTreeClassifier(
                        max_depth=d,
                        min_samples_leaf=max(1, int(MIN_LEAF_FRAC * len(y))),
                        random_state=0))
                vals.append(A.summarise(A.score_map(
                    A.assemble(regions, feats.ids, p), gt, f"{nm}/d{d}"))["mean_iou"])
            sweep.setdefault(nm, {})[d] = {"mean": float(np.mean(vals)),
                                           "sd": float(np.std(vals))}
    results["tree_depth_sweep"] = sweep
    print("tree depth sweep (mean over CV seeds):", json.dumps(sweep, indent=1))

    out = a.out or os.path.join(HERE, "results", f"shape_prior_{a.partition}.json")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    json.dump(results, open(out, "w"), indent=1)
    print("wrote", out)


if __name__ == "__main__":
    main()
