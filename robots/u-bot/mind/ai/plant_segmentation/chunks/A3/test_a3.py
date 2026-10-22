"""A3 tests. Run with the A3 venv; no pytest required.

    chunks/A3/.venv/bin/python chunks/A3/test_a3.py

The load-bearing ones are the honesty tests, not the plumbing tests:

* `test_cv_is_actually_blind` builds a dataset whose label is a function of the
  spatial block *only*, so a model that leaks across folds scores 1.0 and an
  honest one scores chance. If the CV in `shape_prior.py` ever stops holding
  whole blocks out, this fails.
* `test_a0_partition_ceiling_is_one` asserts the leak that made A3 run its own
  SAM: classifying A0's own partition has a ceiling of exactly 1.0, so a score
  on it is not a score on the segmentation problem.
* `test_masked_gt_cannot_change_an_iou` asserts that excluding the fitted
  patches works the way A0's `unlabelled` does.
"""
from __future__ import annotations

import os
import sys
import traceback

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import a3_common as A  # noqa: E402
import eval as a0eval  # noqa: E402


# ----------------------------------------------------------------- partition --
def test_partition_is_a_true_cover():
    m = np.zeros((3, 40, 40), bool)
    m[0, 5:35, 5:35] = True
    m[1, 10:20, 10:20] = True
    m[2, 25:30, 25:30] = True
    p = A.build_partition(m, min_region=4)
    assert p.min() >= 1, "every pixel must belong to a region"
    assert set(np.unique(p)) == set(range(1, p.max() + 1)), "ids must be contiguous"
    assert p.shape == (40, 40)


def test_partition_folds_away_tiny_fragments():
    m = np.zeros((2, 30, 30), bool)
    m[0, 2:28, 2:28] = True
    m[1, 10, 10] = True                      # a 1 px proposal, below min_region
    p = A.build_partition(m, min_region=25)
    sizes = np.bincount(p.ravel())[1:]
    assert (sizes >= 25).all(), f"a fragment below min_region survived: {sizes}"


def test_partition_splits_disconnected_pieces_of_one_proposal():
    m = np.zeros((1, 30, 30), bool)
    m[0, 2:12, 2:12] = True
    m[0, 18:28, 18:28] = True                 # same proposal, two components
    p = A.build_partition(m, min_region=4)
    assert p.max() >= 2, "two disconnected components must get two ids"


# ------------------------------------------------------------------- shapes --
def _shape_of(mask):
    ys, xs = np.nonzero(mask)
    sl = (slice(ys.min(), ys.max() + 1), slice(xs.min(), xs.max() + 1))
    from a3_common import _shape_one
    return _shape_one(mask[sl], ys, xs)


def test_disc_and_ribbon_are_told_apart_by_shape():
    yy, xx = np.mgrid[0:81, 0:81]
    disc = ((yy - 40) ** 2 + (xx - 40) ** 2) <= 30 ** 2
    ribbon = np.zeros((81, 81), bool)
    ribbon[38:43, 4:78] = True                # 5 x 74, constant width
    d, r = _shape_of(disc), _shape_of(ribbon)
    assert d["elongation"] < 1.1, d["elongation"]
    assert r["elongation"] > 8, r["elongation"]
    assert d["solidity"] > 0.9 and r["solidity"] > 0.9
    assert abs(d["ribbonness"] - 0.5) < 0.12, d["ribbonness"]
    # a ribbon approaches 1.0 (crack perimeter counts its two ends, so a
    # 5x74 bar reads ~0.78); a disc sits near 0.5
    assert r["ribbonness"] > 0.7, r["ribbonness"]
    assert r["ribbonness"] > 1.4 * d["ribbonness"]
    assert r["width_cv"] < d["width_cv"], "a ribbon has more constant width"


def test_lobed_boundary_scores_more_complex_than_a_disc():
    yy, xx = np.mgrid[0:161, 0:161]
    th = np.arctan2(yy - 80, xx - 80)
    rr = np.hypot(yy - 80, xx - 80)
    disc = rr <= 50
    lobed = rr <= (50 + 18 * np.cos(7 * th))
    assert (_shape_of(lobed)["boundary_complexity"]
            > 1.3 * _shape_of(disc)["boundary_complexity"])
    assert _shape_of(lobed)["solidity"] < _shape_of(disc)["solidity"]


# ----------------------------------------------------------------------- CV --
def test_blocked_folds_never_split_a_block():
    cent = np.stack([np.random.default_rng(0).uniform(0, A.GT_H, 500),
                     np.random.default_rng(1).uniform(0, A.GT_W, 500)], 1)
    f = A.blocked_folds(cent)
    by = np.clip((cent[:, 0] / A.GT_H * A.CV_BLOCKS[0]).astype(int),
                 0, A.CV_BLOCKS[0] - 1)
    bx = np.clip((cent[:, 1] / A.GT_W * A.CV_BLOCKS[1]).astype(int),
                 0, A.CV_BLOCKS[1] - 1)
    bid = by * A.CV_BLOCKS[1] + bx
    for b in np.unique(bid):
        assert len(np.unique(f[bid == b])) == 1, f"block {b} spans folds"
    assert len(np.unique(f)) == A.N_FOLDS


def test_cv_is_actually_blind():
    """The label is a pure function of the spatial block. A model that saw the
    held-out block would score 1.0; a blind one cannot beat chance."""
    from shape_prior import cv_predict
    from sklearn.tree import DecisionTreeClassifier

    rng = np.random.default_rng(0)
    n = 480
    cent = np.stack([rng.uniform(0, A.GT_H, n), rng.uniform(0, A.GT_W, n)], 1)
    by = np.clip((cent[:, 0] / A.GT_H * A.CV_BLOCKS[0]).astype(int),
                 0, A.CV_BLOCKS[0] - 1)
    bx = np.clip((cent[:, 1] / A.GT_W * A.CV_BLOCKS[1]).astype(int),
                 0, A.CV_BLOCKS[1] - 1)
    bid = by * A.CV_BLOCKS[1] + bx
    y = 1 + (bid % 5)                                  # 5 classes, block-determined
    X = np.stack([cent[:, 0], cent[:, 1], bid.astype(float)], 1)
    folds = A.blocked_folds(cent)
    w = np.ones(n)

    insample = DecisionTreeClassifier(max_depth=None, random_state=0)
    insample.fit(X, y, sample_weight=w)
    assert (insample.predict(X) == y).mean() > 0.99, "the task is learnable in-sample"

    p, _ = cv_predict(X, y, w, folds,
                      lambda: DecisionTreeClassifier(max_depth=None,
                                                     random_state=0))
    acc = (p == y).mean()
    assert acc < 0.60, (
        f"out-of-fold accuracy {acc:.3f} on a block-determined label means the "
        "CV is leaking across spatial blocks")


# ------------------------------------------------------------------ scoring --
def test_ground_truth_scores_one_against_itself():
    gt = a0eval.load_gt()
    r = A.score_map(gt.material, gt, "self")
    for c, v in r["per_class_iou"].items():
        if v["gt_px"]:
            assert abs(v["iou"] - 1.0) < 1e-12, (c, v["iou"])
    assert abs(r["mean_iou"] - 1.0) < 1e-12


def test_grass_squash_diagnostic_reads_the_right_way_round():
    gt = a0eval.load_gt()
    clean = A.grass_squash_confusion(A.score_map(gt.material, gt))
    assert clean["grass_as_squash"] == 0.0
    assert abs(clean["grass_as_grass"] - 1.0) < 1e-12
    bad = gt.material.copy()
    bad[bad == a0eval.CID["grass"]] = a0eval.CID["squash_leaf"]
    worst = A.grass_squash_confusion(A.score_map(bad, gt))
    assert abs(worst["grass_as_squash"] - 1.0) < 1e-12
    assert worst["grass_as_grass"] == 0.0


def test_predict_classes_exclude_soil():
    assert "soil" not in A.PREDICT_CLASSES, (
        "A0 has zero soil pixels; predicting soil can only steal pixels from "
        "classes that exist")
    assert set(A.PREDICT_CLASSES) <= set(a0eval.CLASSES)


def test_roadmap_class_mapping_covers_every_roadmap_class():
    for k, v in A.ROADMAP_TO_A0.items():
        for c in v:
            assert c in a0eval.CLASSES, (k, c)
    covered = {c for v in A.ROADMAP_TO_A0.values() for c in v}
    assert covered == set(a0eval.CLASSES) - {"unlabelled", "other"}


# ----------------------------------------------------------- the leak itself --
def test_a0_partition_ceiling_is_one():
    """A0 painted its labels on A0's partition, so classifying those regions is
    a solved segmentation problem before a classifier is even chosen. This is
    the reason A3 runs its own SAM."""
    p = os.path.join(A.ROOT, "chunks/A0/work/regions.npy")
    if not os.path.exists(p):
        print("    (skipped: chunks/A0/work/regions.npy not present)")
        return
    gt = a0eval.load_gt()
    regions = np.load(p)
    y, _, _ = A.region_gt_labels(regions, gt)
    ids = np.arange(1, regions.max() + 1)
    m = A.assemble(regions, ids, np.where(y < 0, a0eval.CID["straw"], y))
    assert A.score_map(m, gt)["mean_iou"] == 1.0


def test_independent_partition_ceiling_is_below_one():
    p = os.path.join(A.WORK, "regions_a3f.npy")
    if not os.path.exists(p):
        print("    (skipped: run sam_regions.py first)")
        return
    gt = a0eval.load_gt()
    regions = np.load(p)
    y, _, _ = A.region_gt_labels(regions, gt)
    ids = np.arange(1, regions.max() + 1)
    m = A.assemble(regions, ids, np.where(y < 0, a0eval.CID["straw"], y))
    ceil = A.score_map(m, gt)["mean_iou"]
    assert 0.5 < ceil < 1.0, (
        f"ceiling {ceil}: an independent partition must leave real boundary "
        "error, or it is not independent")


def test_masked_gt_cannot_change_an_iou():
    from dino_probe import masked_gt
    gt = a0eval.load_gt()
    rng = np.random.default_rng(0)
    drop = rng.random(gt.material.shape) < 0.02
    g2 = masked_gt(gt, drop)
    assert (g2.material[drop] == a0eval.UNLABELLED).all()
    # a prediction that is wrong ONLY on dropped pixels must score 1.0
    pred = gt.material.copy()
    pred[drop] = a0eval.CID["fruit"]
    r = A.score_map(pred, g2)
    assert abs(r["mean_iou"] - 1.0) < 1e-12, r["mean_iou"]


# ---------------------------------------------------------------- A2 bridge --
def test_a2_lands_on_the_label_grid_with_its_caveats():
    a2 = A.a2_on_gt_grid()
    assert a2["h_sigma"].shape == (A.GT_H, A.GT_W)
    assert a2["scale_confidence"] == "scale_free"
    assert "STRAW" in a2["datum"].upper(), "the straw-datum caveat must survive"
    assert 0.004 < a2["sigma_datum"] < 0.007, a2["sigma_datum"]
    assert np.isfinite(a2["h_sigma"][a2["valid"]]).all()


def test_features_are_finite():
    p = os.path.join(A.WORK, "regions_a3f.npy")
    if not os.path.exists(p):
        print("    (skipped: run sam_regions.py first)")
        return
    f = A.compute_features(np.load(p), a2=A.a2_on_gt_grid())
    assert np.isfinite(f.X).all(), "a non-finite feature would silently bias a split"
    assert len(f.names) == f.X.shape[1]
    assert set(f.group_of.values()) <= set(A.FEATURE_GROUPS)
    for g in A.FEATURE_GROUPS:
        assert len(f.cols([g])) > 0, f"group {g} is empty"


# ------------------------------------------------------------- the default ---
def test_default_module_output_is_well_formed():
    cache = os.path.join(A.WORK, "a3_default_features.npz")
    if not os.path.exists(cache):
        print("    (skipped: run a3_api.py once to build the feature cache)")
        return
    from a3_api import segment_material
    out = segment_material()
    assert out.material.shape == (A.GT_H, A.GT_W)
    assert out.material.dtype == np.uint8
    assert set(np.unique(out.material)) <= set(A.PREDICT_IDS.tolist())
    assert a0eval.CID["soil"] not in np.unique(out.material)
    assert out.confidence.shape == out.material.shape
    assert (out.confidence >= 0).all() and (out.confidence <= 1).all()
    assert out.provenance["height_above_soil_used"] is False


def test_default_module_beats_the_recorded_baseline():
    cache = os.path.join(A.WORK, "a3_default_features.npz")
    if not os.path.exists(cache):
        print("    (skipped: run a3_api.py once to build the feature cache)")
        return
    from a3_api import segment_material
    gt = a0eval.load_gt()
    r = A.score_map(segment_material().material, gt)
    assert r["mean_iou"] > 0.2534, (
        f"the default scores {r['mean_iou']:.4f}, at or below the recorded "
        "ZeroPlantSeg baseline of 0.2534")
    per = r["per_class_iou"]
    assert per["grass"]["iou"] > 0.0, "the baseline's 0.0000 on grass must be beaten"
    assert per["squash_petiole"]["iou"] > 0.0, "likewise squash_petiole"
    g = A.grass_squash_confusion(r)
    assert g["grass_as_squash"] < 0.53, (
        f"grass->squash {g['grass_as_squash']:.3f} is no better than the "
        "baseline's 53 %")


def main():
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    fails = 0
    for t in tests:
        try:
            t()
            print(f"  PASS  {t.__name__}")
        except Exception:
            fails += 1
            print(f"  FAIL  {t.__name__}")
            traceback.print_exc()
    print(f"\n{len(tests) - fails}/{len(tests)} passed")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
