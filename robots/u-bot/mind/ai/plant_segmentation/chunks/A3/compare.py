"""A3 — assemble the one comparison table, and sweep the two constants the
winner introduces.

Reads every `results/*.json` the four approach scripts wrote, emits
`results/comparison.json` and `results/comparison.md` (the table that goes into
RESULTS.md), and runs two sweeps that would otherwise be unregistered constants:

* the probe's regularisation `C`, which is sklearn's default 1.0 and was never
  tuned — the sweep is what makes that a defensible (c) rather than a hidden (d);
* the number of labelled patches, because "a few dozen" is the brief's
  requirement and the interesting question is what it buys.

Both sweeps are run over the same five independent patch draws as the headline.
"""
from __future__ import annotations

import json
import os
import sys
import time

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import a3_common as A  # noqa: E402
import eval as a0eval  # noqa: E402

RES = os.path.join(HERE, "results")
C_GRID = [0.01, 0.1, 1.0, 10.0, 100.0]
PATCH_GRID = [2, 4, 6, 12, 24]
N_DRAWS = 5


def _load(name, default=None):
    p = os.path.join(RES, name)
    return json.load(open(p)) if os.path.exists(p) else default


def sweeps():
    """Probe-C and patch-count sweeps on the cached DINOv2 features."""
    from sklearn.linear_model import LogisticRegression
    import dino_probe as DP

    gt = a0eval.load_gt()
    z = np.load(os.path.join(A.WORK, "a3_default_features.npz"))
    F = z["F"].astype(np.float32)
    PH, PW = tuple(z["grid"])
    ygrid, purity, pid_map = DP.patch_gt((PH, PW), gt)
    y, pur = ygrid.ravel(), purity.ravel()
    eligible = {c: np.where((y == a0eval.CID[c]) & (pur >= 1.0))[0]
                for c in A.PREDICT_CLASSES}

    def draw(per_class, d):
        rng = np.random.default_rng(1000 + d)
        idx, lab = [], []
        for c, e in eligible.items():
            if len(e) == 0:
                continue
            t = rng.choice(e, size=min(per_class, len(e)), replace=False)
            idx += list(t)
            lab += [a0eval.CID[c]] * len(t)
        return np.array(idx), np.array(lab)

    def score(idx, lab, C):
        clf = LogisticRegression(max_iter=2000, C=C).fit(F[idx], lab)
        m = clf.predict(F).reshape(PH, PW).ravel()[pid_map].astype(np.uint8)
        return A.summarise(A.score_map(m, gt))

    out = {"C_sweep": {}, "patch_count_sweep": {}, "n_draws": N_DRAWS}
    for C in C_GRID:
        v = [score(*draw(6, d), C)["mean_iou"] for d in range(N_DRAWS)]
        out["C_sweep"][str(C)] = {"mean": float(np.mean(v)),
                                  "sd": float(np.std(v))}
        print(f"  C={C:<7} mIoU {np.mean(v):.4f} +-{np.std(v):.4f}")
    for k in PATCH_GRID:
        s = [score(*draw(k, d), 1.0) for d in range(N_DRAWS)]
        v = [x["mean_iou"] for x in s]
        g = [x["grass_as_squash"] for x in s]
        out["patch_count_sweep"][str(k)] = {
            "patches_total": k * len(A.PREDICT_CLASSES),
            "mean": float(np.mean(v)), "sd": float(np.std(v)),
            "grass_as_squash": float(np.mean(g))}
        print(f"  {k:2d}/class ({k*7:3d} patches) mIoU {np.mean(v):.4f} "
              f"+-{np.std(v):.4f}  grass->squash {100*np.mean(g):.1f}%")
    return out


BASELINE = {
    "name": "ZeroPlantSeg (recorded baseline, charitable mapping)",
    "mean_iou": 0.2534,
    "per_class_iou": {"squash_leaf": 0.6760, "squash_petiole": 0.0000,
                      "grass": 0.0000, "broadleaf_weed": 0.4903,
                      "straw": 0.6076, "soil": None, "fruit": 0.0000,
                      "other": 0.0000},
    "grass_as_squash": 0.530,
    "grass_note": "53.0 % of GT grass absorbed into the crop *instance*; the "
                  "class-level equivalent is undefined because ZeroPlantSeg "
                  "emits no grass class at all.",
    "compute": "~8 min/image (SAM ViT-H + OVSeg CLIP per mask + GroundingDINO "
               "per mask + DBSCAN), MPS",
}


def main():
    sp = _load("shape_prior_a3f.json")
    dp = _load("dino_probe.json")
    dr = _load("dino_region_a3f.json")
    ov = {k: _load(f"open_vocab_{k}.json") for k in
          ("siglip2-so400m-patch14-384", "siglip2-base-patch16-384",
           "clip-vit-large-patch14")}
    hr = _load("height_report.json")
    sam = json.load(open(os.path.join(A.WORK, "a3f_sam_meta.json")))
    sam_s = sam["seconds"]

    print("probe sweeps:")
    t0 = time.time()
    sw = sweeps()
    sw["seconds"] = time.time() - t0

    v = sp["variants"]
    rows = []

    def row(name, s, compute, note=""):
        rows.append({"approach": name, "mean_iou": s["mean_iou"],
                     "mean_iou_sd": s.get("mean_iou_sd"),
                     "per_class_iou": s["per_class_iou"],
                     "grass_as_squash": s["grass_as_squash"],
                     "compute": compute, "note": note})

    row(BASELINE["name"], BASELINE, BASELINE["compute"], BASELINE["grass_note"])
    row("1. shape prior over SAM regions (depth-4 tree, blocked CV)",
        v["approach1_shape"]["tree_cv"],
        f"SAM ViT-H {sam_s:.0f} s + features {sp['seconds_features']:.1f} s "
        f"+ fit <1 s",
        "out-of-fold, mean over 5 block-to-fold deals; "
        f"in-sample {v['approach1_shape']['tree_insample']['mean_iou']:.4f}")
    row("2. shape prior + A2 height_above_soil",
        v["approach2_shape_height"]["tree_cv"],
        f"as above + A2 products (already on disk; A2 itself is ~10 min)",
        "out-of-fold, mean over 5 deals; "
        f"in-sample {v['approach2_shape_height']['tree_insample']['mean_iou']:.4f}")
    row("3. frozen DINOv2 patch features + logistic probe, 42 patches",
        dp["probes"]["logreg"],
        f"DINOv2-base features {dp['seconds']['fine']+dp['seconds']['coarse']:.1f} s "
        f"(70 tiles, MPS) + fit {dp['probes']['logreg']['fit_seconds']:.2f} s "
        f"+ predict {dp['probes']['logreg']['predict_seconds']:.2f} s; no SAM",
        f"mean over 5 independent 42-patch draws; with the fitted patches' own "
        f"pixels excluded {dp['probes']['logreg']['mean_iou_heldout']:.4f}")
    best_ov = ov["siglip2-so400m-patch14-384"]
    row("4. open-vocabulary: SigLIP 2 so400m over SAM regions "
        "(crop_fill, descriptive, 12-template ensemble)",
        best_ov["headline"],
        f"SAM ViT-H {sam_s:.0f} s + crops ~6 s + SigLIP2-so400m encode "
        f"{best_ov['seconds']['image_encode']['crop_fill']:.0f} s, MPS",
        "zero-shot: nothing fitted; config fixed before scoring")

    comp = {
        "gt": "groundtruth/ (A0), 768x1024, scored with chunks/A0/eval.py",
        "partition": {
            "primary": "a3f — an INDEPENDENT SAM run (points_per_side 64, "
                       "pred_iou 0.82, stability 0.90, min area 25), 572 masks "
                       "-> 728 regions",
            "ceiling_a3f": sp["partition_ceiling"]["mean_iou"],
            "ceiling_a3_coarse": 0.8202,
            "ceiling_a0_partition": 1.0,
            "ceiling_note": "A0's ground truth was painted region-by-region on "
                            "A0's own SAM partition, so classifying those "
                            "regions has a ceiling of exactly 1.0 and zero "
                            "boundary error. A3 therefore runs SAM again with "
                            "different settings; every headline number is on "
                            "the independent partition.",
            "patch_grid_ceiling": dp["patch_grid_ceiling"]["mean_iou"],
        },
        "table": rows,
        "extensions": {
            "3b. same DINOv2 features pooled over SAM regions (logreg, blocked CV)":
                dr["models"]["logreg"],
            "3b. same, random forest": dr["models"]["forest"],
            "3b. same, depth-4 tree": dr["models"]["tree"],
            "1+2 with a random forest instead of a tree": {
                "approach1": v["approach1_shape"]["forest_cv"]["mean_iou"],
                "approach2": v["approach2_shape_height"]["forest_cv"]["mean_iou"],
                "all_handcrafted": v["abl_all_handcrafted"]["forest_cv"]["mean_iou"],
            },
        },
        "height_ablation": {
            "in_approach_2_shape_prior": {
                "shape_only": v["approach1_shape"]["tree_cv"]["mean_iou"],
                "shape_plus_height": v["approach2_shape_height"]["tree_cv"]["mean_iou"],
                "delta": v["approach2_shape_height"]["tree_cv"]["mean_iou"]
                         - v["approach1_shape"]["tree_cv"]["mean_iou"],
                "height_only": v["abl_height_only"]["tree_cv"]["mean_iou"],
                "colour_only": v["abl_colour_only"]["tree_cv"]["mean_iou"],
                "colour_plus_height": v["abl_colour_height"]["tree_cv"]["mean_iou"],
                "shape_colour": v["abl_shape_colour"]["tree_cv"]["mean_iou"],
                "shape_colour_height": v["abl_shape_colour_height"]["tree_cv"]["mean_iou"],
            },
            "in_the_winner_dinov2_probe": {
                "dino_only_scaled": dp["probes"]["logreg_scaled"]["mean_iou"],
                "dino_plus_height": dp["probes"]["logreg_scaled_height"]["mean_iou"],
                "delta": dp["probes"]["logreg_scaled_height"]["mean_iou"]
                         - dp["probes"]["logreg_scaled"]["mean_iou"],
                "height_only": dp["probes"]["logreg_height_only"]["mean_iou"],
            },
            "height_separability_vs_gt": hr["pairwise_separability_height_only"],
            "per_class_median_height_sigma": {
                c: d.get("median_sigma") for c, d in hr["per_class"].items()},
            "a2_hand_placed_boxes": hr["a2_hand_placed_boxes"],
        },
        "grass_squash": {
            r["approach"]: {"grass_as_squash": r["grass_as_squash"]} for r in rows},
        "prompt_ensembling": {
            k: {"mean_delta_mean_iou": o["prompt_ensembling_mean_delta"],
                "per_cell": o["prompt_ensembling_effect"]}
            for k, o in ov.items() if o},
        "open_vocab_model_sweep": {
            k: {"headline": o["headline"]["mean_iou"],
                "best_cell": o["best_config_selected_on_gt"]["config"],
                "best_cell_mean_iou": o["best_config_selected_on_gt"]["mean_iou"],
                "grid": {kk: vv["mean_iou"] for kk, vv in o["grid"].items()}}
            for k, o in ov.items() if o},
        "probe_sweeps": sw,
        "compute": {
            "sam_vit_h_seconds_a3f": sam_s,
            "sam_vit_h_seconds_a3_coarse": json.load(
                open(os.path.join(A.WORK, "a3_sam_meta.json")))["seconds"],
            "shape_features_seconds": sp["seconds_features"],
            "dinov2_features_seconds": dp["seconds"]["fine"] + dp["seconds"]["coarse"],
            "siglip2_so400m_encode_seconds_per_variant":
                best_ov["seconds"]["image_encode"]["crop_fill"],
            "siglip2_base_encode_seconds_per_variant":
                ov["siglip2-base-patch16-384"]["seconds"]["image_encode"]["crop_fill"],
            "device": "Apple Silicon MPS",
        },
    }
    json.dump(comp, open(os.path.join(RES, "comparison.json"), "w"), indent=1)

    # --- markdown
    cls = ["squash_leaf", "squash_petiole", "grass", "broadleaf_weed",
           "straw", "fruit", "other"]
    L = ["| approach | " + " | ".join(cls) + " | **mean IoU** | grass→squash | compute |",
         "|---|" + "---:|" * (len(cls) + 1) + "---:|---|"]
    for r in rows:
        cells = []
        for c in cls:
            x = r["per_class_iou"].get(c)
            cells.append("n/a" if x is None else f"{x:.4f}")
        sd = f" ±{r['mean_iou_sd']:.4f}" if r.get("mean_iou_sd") else ""
        L.append(f"| {r['approach']} | " + " | ".join(cells)
                 + f" | **{r['mean_iou']:.4f}**{sd}"
                 + f" | {100*r['grass_as_squash']:.1f} % | {r['compute']} |")
    md = "\n".join(L)
    open(os.path.join(RES, "comparison.md"), "w").write(md + "\n")
    print("\n" + md)
    print("\nwrote results/comparison.json and results/comparison.md")


if __name__ == "__main__":
    main()
