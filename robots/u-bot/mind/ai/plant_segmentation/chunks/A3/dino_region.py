"""A3 approach 3b (an extension, clearly labelled as one) — the frozen DINOv2
features of approach 3, pooled over the SAM regions of approaches 1-2.

The brief asks for four approaches. This is not a fifth: it is the control that
separates *what the features know* from *where the boundaries are*. Approach 3
carries DINOv2 features on a 3.5-label-px patch grid; approaches 1, 2 and 4
carry hand-made or CLIP-style descriptors on SAM regions. Swapping only the
feature source, with the substrate, the classifier, the sample weighting and the
spatially blocked CV all held fixed, says which of the two mattered.

Everything about the protocol is identical to `shape_prior.py`: region labels
are the majority ground-truth class, sample weight is region area, the frame is
cut into 4x4 spatial blocks dealt to 4 folds, five block-to-fold deals are
averaged, and the in-sample score is printed next to the out-of-fold one.

A high-dimensional feature needs a different model class from a depth-4 tree, so
the headline here is a multinomial logistic regression; the tree and forest are
reported alongside on the same features so the model change and the feature
change stay separable.
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
from shape_prior import MIN_LEAF_FRAC, N_CV_SEEDS, TREE_DEPTH, _agg, cv_predict  # noqa: E402

from sklearn.ensemble import RandomForestClassifier  # noqa: E402
from sklearn.linear_model import LogisticRegression  # noqa: E402
from sklearn.pipeline import make_pipeline  # noqa: E402
from sklearn.preprocessing import StandardScaler  # noqa: E402
from sklearn.tree import DecisionTreeClassifier  # noqa: E402


def pool_dino_over_regions(regions):
    """Mean of the L2-normalised fine and coarse DINO patch features inside each
    region, re-normalised. Requires `dino_probe.py` to have been run."""
    fine = np.load(os.path.join(A.WORK, "dino_fine.npy")).astype(np.float32)
    coarse = np.load(os.path.join(A.WORK, "dino_coarse.npy")).astype(np.float32)
    PH, PW, D = fine.shape

    def l2(a):
        return a / np.maximum(np.linalg.norm(a, axis=-1, keepdims=True), 1e-8)

    F = np.concatenate([l2(fine), l2(coarse)], -1).reshape(PH * PW, 2 * D)

    yy = np.minimum(np.arange(A.GT_H) * PH // A.GT_H, PH - 1)
    xx = np.minimum(np.arange(A.GT_W) * PW // A.GT_W, PW - 1)
    pid = (yy[:, None] * PW + xx[None, :])

    R = int(regions.max())
    acc = np.zeros((R + 1, F.shape[1]), np.float64)
    cnt = np.zeros(R + 1)
    np.add.at(cnt, regions.ravel(), 1.0)
    # accumulate per patch rather than per pixel: one row per (region, patch)
    flat_r = regions.ravel()
    flat_p = pid.ravel()
    key = flat_r.astype(np.int64) * (PH * PW) + flat_p
    uk, inv, uc = np.unique(key, return_inverse=True, return_counts=True)
    ur = (uk // (PH * PW)).astype(int)
    up = (uk % (PH * PW)).astype(int)
    np.add.at(acc, ur, F[up] * uc[:, None])
    cnt[cnt == 0] = 1
    X = acc[1:] / cnt[1:, None]
    return (X / np.maximum(np.linalg.norm(X, axis=1, keepdims=True), 1e-9)).astype(
        np.float32)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--partition", default="a3f")
    ap.add_argument("--out", default=None)
    a = ap.parse_args()

    gt = a0eval.load_gt()
    regions = np.load(os.path.join(A.WORK, f"regions_{a.partition}.npy")) \
        if a.partition != "a0" else np.load(
            os.path.join(A.ROOT, "chunks/A0/work/regions.npy"))

    t0 = time.time()
    Xall = pool_dino_over_regions(regions)
    t_pool = time.time() - t0

    feats = A.compute_features(regions, a2=A.a2_on_gt_grid())
    ids = feats.ids
    X = Xall[ids - 1]
    y, _, _ = A.region_gt_labels(regions, gt)
    y = y[ids - 1]
    w = feats.area.astype(float)
    folds_by_seed = [A.blocked_folds(feats.centroid, seed=s) for s in range(N_CV_SEEDS)]
    minleaf = max(1, int(MIN_LEAF_FRAC * len(y)))

    models = {
        "logreg": lambda: make_pipeline(
            StandardScaler(),
            LogisticRegression(max_iter=3000, C=1.0)),
        "tree": lambda: DecisionTreeClassifier(max_depth=TREE_DEPTH,
                                               min_samples_leaf=minleaf,
                                               random_state=0),
        "forest": lambda: RandomForestClassifier(n_estimators=300,
                                                 min_samples_leaf=2,
                                                 random_state=0, n_jobs=-1),
    }
    res = {"partition": a.partition, "n_regions": int(regions.max()),
           "feature_dim": int(X.shape[1]), "seconds_pool": t_pool,
           "cv": {"design": "spatial 4x4 blocks dealt to 4 folds",
                  "n_seeds": N_CV_SEEDS},
           "models": {}}
    print(f"pooled DINO over {len(ids)} regions, dim {X.shape[1]}, "
          f"{t_pool:.1f}s")

    # some sklearn versions need sample_weight passed through the pipeline
    def fit(m, Xtr, ytr, wtr):
        try:
            m.fit(Xtr, ytr, sample_weight=wtr)
        except (TypeError, ValueError):
            m.fit(Xtr, ytr, logisticregression__sample_weight=wtr)
        return m

    import shape_prior
    shape_prior._fit = fit

    for name, mk in models.items():
        t0 = time.time()
        per_seed = []
        for si, folds in enumerate(folds_by_seed):
            p, _ = cv_predict(X, y, w, folds, mk)
            m = A.assemble(regions, ids, p)
            per_seed.append(A.summarise(A.score_map(m, gt, f"dinoreg/{name}/s{si}")))
            if si == 0:
                A.save_pred(f"approach3b_dinoregion_{name}", m)
        agg = _agg(per_seed)
        agg["seconds_cv_all_seeds"] = time.time() - t0
        agg["mean_iou_per_seed"] = [s["mean_iou"] for s in per_seed]
        tr = y > 0
        mm = fit(mk(), X[tr], y[tr], w[tr])
        agg["insample_mean_iou"] = A.summarise(
            A.score_map(A.assemble(regions, ids, mm.predict(X)), gt))["mean_iou"]
        res["models"][name] = agg
        print(f"  {name:7s} CV mIoU {agg['mean_iou']:.4f} +-{agg['mean_iou_sd']:.4f}"
              f"  (in-sample {agg['insample_mean_iou']:.4f})"
              f"  grass->squash {100*agg['grass_as_squash']:.1f}%")

    out = a.out or os.path.join(HERE, "results", f"dino_region_{a.partition}.json")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    json.dump(res, open(out, "w"), indent=1)
    print("wrote", out)


if __name__ == "__main__":
    main()
