"""A4 — the three verdicts the roadmap asks for, and Open Question 2.

Verdicts (roadmap A4, "Done when"):
  * does the squash come out as one component?
  * does the clover stay separate?
  * how much grass is absorbed into the crop?

Open Question 2 ("Does instance segmentation earn its place in v1? Semantic
classes plus a soil surface plus connected components may be enough for
targeting. A4 should be evaluated against that simpler alternative, not assumed
superior.") is answered by scoring four things on the same ground truth:

  S0  semantic only          — A3 class per pixel, no grouping at all. A pixel is
                               a removal target if its class is a weed class.
  S1  + soil surface         — S0 restricted to material A2 puts confidently
                               above the datum. The "semantic classes + soil
                               surface" half of the question.
  S2  + 2-D connected comps  — S1's plant mask, 8-connected in the image only.
                               No depth is consulted. The literal "connected
                               components" of the open question.
  A4  3-D connectivity       — this chunk.

The comparison that matters for R2 is not mean IoU. It is: **how often would a
tool be sent at a pixel that is really crop?** S0/S1 decide that per pixel from
an uncalibrated classifier; S2 and A4 decide it per component by majority, which
is what a grouping buys you. Both are measured.

Run:  ../A3/.venv/bin/python report.py
"""
from __future__ import annotations

import json
import os
import sys

import numpy as np
from scipy import ndimage

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import a4_common as C      # noqa: E402
import a4_graph as G       # noqa: E402
import fast_eval as FE     # noqa: E402
import run_a4 as R         # noqa: E402
import eval as a0eval      # noqa: E402

CROP_IDS = np.array([a0eval.CID[c] for c in
                     ("squash_leaf", "squash_petiole", "fruit")])
WEED_IDS = np.array([a0eval.CID[c] for c in ("grass", "broadleaf_weed")])


def verdicts(comp_gt, gt):
    """The three questions, answered from the label maps, not from an opinion."""
    s = FE.instance_scores(comp_gt, gt)
    crop_pred = a0eval.grass_absorption(comp_gt, gt)["crop_pred_id"]
    squash = gt.instances == 1
    ids, cnt = np.unique(comp_gt[squash], return_counts=True)
    keep = ids != 0
    ids, cnt = ids[keep], cnt[keep]
    largest_frac = float(cnt.max() / squash.sum()) if cnt.size else 0.0
    clover = gt.instances == 3          # the clover patch, per A0/RESULTS
    clover_in_crop = float((comp_gt[clover] == crop_pred).mean()) if clover.any() else None
    clover_best = s["best_iou_per_gt"].get(3, {"iou": 0.0})["iou"]
    grass = a0eval.grass_absorption(comp_gt, gt)
    return {
        "squash_one_component": bool(s["best_iou_per_gt"].get(1, {"iou": 0})["iou"]
                                     >= 0.5),
        "squash_best_iou": s["best_iou_per_gt"].get(1, {"iou": 0.0})["iou"],
        "squash_largest_component_covers": largest_frac,
        "squash_parts_ge_200px": FE.fragmentation(comp_gt, gt)["n_pred_parts"],
        "clover_separate_from_crop": bool((clover_in_crop or 0.0) < 0.5),
        "clover_fraction_inside_crop_component": clover_in_crop,
        "clover_best_iou": clover_best,
        "grass_absorbed_fraction": grass["absorbed_fraction"],
        "crop_pred_component_id": grass["crop_pred_id"],
        "instance_f1": s["f1"], "tp": s["tp"], "n_pred": s["n_pred"],
    }


def targeting(label_of_pixel, is_weed_pixel, gt):
    """R2's number: of the pixels this policy would send a tool at, how many are
    really crop? And of the crop, how much is at risk?"""
    gcrop = np.isin(gt.material, CROP_IDS)
    gweed = np.isin(gt.material, WEED_IDS)
    valid = gt.material != a0eval.UNLABELLED
    tgt = is_weed_pixel & valid
    return {
        "target_px": int(tgt.sum()),
        "crop_px_targeted": int((tgt & gcrop).sum()),
        "crop_px_targeted_fraction_of_crop": float((tgt & gcrop).sum() / gcrop.sum()),
        "fraction_of_targets_that_are_crop": float((tgt & gcrop).sum() / max(tgt.sum(), 1)),
        "weed_px_targeted_fraction_of_weed": float((tgt & gweed).sum() / gweed.sum()),
    }


def main():
    gt = a0eval.load_gt()
    inp = C.load_inputs()
    out = {"scale_confidence": "scale_free", "datum": inp.provenance["a2"]["datum"]}

    r = R.build(inp)
    comp = {}
    for pol in ("split", "merge"):
        comp[pol] = C.to_gt_grid_nearest(
            r["comp_" + pol][r["frag"]].astype(np.int32))
    out["continuity_tolerance_rdu"] = r["tol"]
    out["verdicts"] = {pol: verdicts(comp[pol], gt) for pol in comp}

    # the baseline, through the same code, so the verdicts are comparable
    zps = a0eval.load_zps_baseline(gt)
    out["verdicts"]["zeroplantseg_baseline"] = verdicts(zps.instances, gt)

    # ---------------- Open Question 2 ---------------------------------------
    mat = inp.material_gt
    a2 = _a2_on_gt_grid()
    plant = np.isin(mat, C.PLANT_IDS)
    above = a2["confident_above"]
    oq = {}

    weed_px = np.isin(mat, WEED_IDS)
    oq["S0_semantic_only"] = {
        "n_targets": "per pixel; no instances exist",
        "targeting": targeting(None, weed_px, gt),
        "per_class_note": "A3's own uncalibrated class per pixel; R2 forbids "
                          "gating on this confidence, and this row is what that "
                          "prohibition costs if it is ignored.",
    }
    oq["S1_semantic_plus_soil_surface"] = {
        "targeting": targeting(None, weed_px & above, gt),
        "note": "same, restricted to material A2 places confidently above the "
                "straw datum (a2.confident_above(3)).",
    }

    st = ndimage.generate_binary_structure(2, 2)
    lab2d, n2d = ndimage.label(plant & above, structure=st)
    oq["S2_2d_connected_components"] = _component_policy(lab2d, mat, gt, n2d)
    oq["S2_2d_connected_components"]["instances"] = FE.summary(
        lab2d.astype(np.int32), gt)
    oq["S2_2d_connected_components"]["n_components"] = int(n2d)

    for pol in ("split", "merge"):
        oq[f"A4_3d_connectivity_{pol}"] = _component_policy(
            comp[pol], mat, gt, int(comp[pol].max()))
        oq[f"A4_3d_connectivity_{pol}"]["instances"] = FE.summary(comp[pol], gt)
        oq[f"A4_3d_connectivity_{pol}"]["n_components"] = int(comp[pol].max())
    out["open_question_2"] = oq

    os.makedirs(C.RESULTS, exist_ok=True)
    p = os.path.join(C.RESULTS, "report.json")
    json.dump(out, open(p, "w"), indent=1, default=float)
    print(json.dumps(out, indent=1, default=float))
    print("wrote", p)


def _component_policy(lab, mat, gt, ncomp):
    """Majority-vote crop/weed per component, then the R2 targeting numbers."""
    crop = np.isin(mat, CROP_IDS).astype(np.int64)
    weed = np.isin(mat, WEED_IDS).astype(np.int64)
    nc = np.bincount(lab.ravel(), weights=crop.ravel(), minlength=ncomp + 1)
    nw = np.bincount(lab.ravel(), weights=weed.ravel(), minlength=ncomp + 1)
    is_weed_comp = np.zeros(ncomp + 1, bool)
    is_weed_comp[1:] = nw[1:] > nc[1:]
    tgt = is_weed_comp[lab] & (lab > 0)
    return {"targeting": targeting(lab, tgt, gt),
            "n_weed_components": int(is_weed_comp.sum())}


def _a2_on_gt_grid():
    sys.path.insert(0, os.path.join(C.ROOT, "chunks", "A2"))
    from a2_api import load_a2
    from PIL import Image
    a2 = load_a2()

    def rs(a, nearest=False):
        im = Image.fromarray(np.asarray(a).astype(np.float32))
        return np.asarray(im.resize((C.GT_W, C.GT_H),
                                    Image.NEAREST if nearest else Image.BILINEAR))
    return {"confident_above": rs(a2.confident_above(3.0).astype(np.float32),
                                 nearest=True) > 0.5}


if __name__ == "__main__":
    main()
