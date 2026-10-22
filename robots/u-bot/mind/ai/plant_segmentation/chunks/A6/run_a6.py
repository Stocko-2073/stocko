"""A6 — build the keep-out volume, measure it, sweep the one constant.

    ../A3/.venv/bin/python run_a6.py            # full run (~6 min, ~4 GB peak)
    ../A3/.venv/bin/python run_a6.py --quick    # shipped config only
"""
from __future__ import annotations

import argparse
import gc
import json
import os
import time

import numpy as np

from a6_common import DatumFrame, load_crop_component, load_gt, load_scene
from keepout import (CLEARANCE_SWEEP_RDU, DEFAULT_CELL_RDU,
                     DEFAULT_CLEARANCE_RDU, TIER_OBSERVED, TIER_UNSEEN,
                     build_keepout)
from metrics import (GtProbe, circle_comparison, contact_point_report,
                     coverage_and_shielding)

HERE = os.path.dirname(os.path.abspath(__file__))
PRODUCTS = os.path.join(HERE, "products")
RESULTS = os.path.join(HERE, "results")


def _describe(vol, scene, crop) -> dict:
    return {
        "policy": crop.policy,
        "component_id": crop.component_id,
        "cell_rdu": vol.cell,
        "voxel_bracket_rdu": vol.voxel_bracket,
        "grid_shape": list(vol.shape),
        "n_voxels_M": float(np.prod(vol.shape) / 1e6),
        "occupancy": vol.occupancy,
        "include_unseen": vol.include_unseen,
        "material_volume_rdu3": vol.material_volume_rdu3(),
        "material_volume_observed_rdu3": vol.material_volume_rdu3(TIER_OBSERVED),
        "material_volume_unseen_rdu3": vol.material_volume_rdu3(TIER_UNSEEN),
        "observed_px": int(crop.observed.sum()),
        "unseen_px": int(crop.unseen.sum()),
        "frame_open": vol.frame_open,
        "unresolved_edges": crop.n_unresolved,
        "frame_fragment_px": crop.frame_fragment_px,
        "columns_without_an_observed_datum_px":
            vol.provenance["columns_without_an_observed_datum_px"],
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--quick", action="store_true")
    args = ap.parse_args()

    os.makedirs(PRODUCTS, exist_ok=True)
    os.makedirs(RESULTS, exist_ok=True)

    t0 = time.time()
    scene = load_scene()
    gt = load_gt()
    frame = DatumFrame.from_scene(scene)
    crop = load_crop_component("merge", gt=gt)
    print(f"scene + A4 loaded in {time.time()-t0:.1f}s; "
          f"crop component {crop.component_id} "
          f"({crop.observed.sum()} px observed, {crop.unseen.sum()} unseen)")

    report: dict = {
        "chunk": "A6",
        "scale_confidence": scene.a2.scale_confidence,
        "units": "rdu (1 rdu = median scene depth of the A1 primary raster)",
        "absolute_scale": ("UNRESOLVED. Every clearance below is in rdu or in "
                           "A2 datum-sigma. The tool number that eventually "
                           "replaces the placeholder will arrive in millimetres "
                           "and cannot be compared to these until C0 supplies "
                           "a scale."),
        "datum": scene.a2.datum,
        "datum_roughness_sigma_rdu": scene.a2.sigma_datum,
        "crop_identity": crop.identity_provenance,
        "clearance_placeholder_rdu": DEFAULT_CLEARANCE_RDU,
        "clearance_placeholder_datum_sigma":
            DEFAULT_CLEARANCE_RDU / scene.a2.sigma_datum,
        "camera": scene.intrinsics.as_dict(),
    }

    # ---------------------------------------------------------------- shipped
    t = time.time()
    vol = build_keepout(scene, crop, cell=DEFAULT_CELL_RDU,
                        clearance=DEFAULT_CLEARANCE_RDU, frame=frame)
    build_s = time.time() - t
    print(f"shipped volume built in {build_s:.1f}s  grid {vol.shape}")

    probe = GtProbe(scene, gt, vol)
    report["shipped"] = _describe(vol, scene, crop)
    report["shipped"]["build_seconds"] = build_s
    report["shipped"].update(
        coverage_and_shielding(scene, gt, vol, crop, CLEARANCE_SWEEP_RDU,
                               probe=probe))
    report["shipped"]["contact_points"] = contact_point_report(
        scene, gt, vol, CLEARANCE_SWEEP_RDU)
    report["shipped"]["circle_comparison"] = {
        f"{c:g}": circle_comparison(vol, scene, gt, c)
        for c in (0.0, DEFAULT_CLEARANCE_RDU, 0.05)}

    # the resolution bracket: how much does `conservative` cost?
    bracket = []
    for c in CLEARANCE_SWEEP_RDU:
        a = probe.inside(vol, c, conservative=True)
        b = probe.inside(vol, c, conservative=False)
        sq = gt.instances == 1
        bracket.append({
            "clearance_rdu": c,
            "gt_squash_covered_conservative": float((a & sq).sum() / sq.sum()),
            "gt_squash_covered_exact": float((b & sq).sum() / sq.sum()),
            "volume_ratio_conservative_over_exact":
                float(vol.volume_rdu3(min(c + vol.voxel_bracket, vol.max_clearance_rdu))
                      / max(vol.volume_rdu3(c), 1e-12))})
    report["shipped"]["resolution_bracket"] = bracket

    # How much of the photograph the volume occludes, seen from where the photo
    # was taken. Ray-marched, ~1 min per clearance, so only four are computed.
    sil = {}
    for c in (0.0, 5.0e-3, DEFAULT_CLEARANCE_RDU, 5.0e-2):
        s = vol.silhouette(scene, c)
        sil[f"{c:g}"] = float(s.mean())
        if c == DEFAULT_CLEARANCE_RDU:
            np.save(os.path.join(PRODUCTS, "silhouette_default_clearance.npy"), s)
        print(f"  silhouette @ {c:g} rdu = {100*s.mean():.1f} % of frame")
    report["shipped"]["silhouette_fraction_of_frame"] = sil

    vol.save(os.path.join(PRODUCTS, "keepout_squash_merge.npz"))
    json.dump(report, open(os.path.join(RESULTS, "a6_report.json"), "w"),
              indent=1)
    print("shipped report written")

    if args.quick:
        return

    # ------------------------------------------------------------- ablations
    sweeps: dict = {"note": (
        "Every row rebuilds the volume from scratch. `clearance` is the one "
        "constant the roadmap asks for; the rest are here to show which "
        "conclusions depend on a choice A6 made rather than on the plant.")}

    del probe
    gc.collect()

    # 1. voxel resolution — is the reported volume a property of the plant or
    #    of the grid?
    rows = []
    for cell in (7.0e-3, 5.0e-3, DEFAULT_CELL_RDU):
        v = build_keepout(scene, crop, cell=cell,
                          clearance=DEFAULT_CLEARANCE_RDU, frame=frame)
        p = GtProbe(scene, gt, v)
        sq = gt.instances == 1
        ins = p.inside(v, DEFAULT_CLEARANCE_RDU)
        weed = (gt.material == 3) | (gt.material == 4)
        rows.append({"cell_rdu": cell, "grid": list(v.shape),
                     "voxel_bracket_rdu": v.voxel_bracket,
                     "material_volume_rdu3": v.material_volume_rdu3(),
                     "volume_at_default_rdu3":
                         v.volume_rdu3(DEFAULT_CLEARANCE_RDU),
                     "gt_squash_covered": float((ins & sq).sum() / sq.sum()),
                     "gt_weed_inside": float((ins & weed).sum() / weed.sum())})
        print("cell", cell, rows[-1]["volume_at_default_rdu3"])
        del v, p
        gc.collect()
    sweeps["voxel_resolution"] = rows

    # 2. the occupancy assumption
    rows = []
    for occ in ("column", "shell"):
        v = build_keepout(scene, crop, cell=DEFAULT_CELL_RDU, occupancy=occ,
                          clearance=DEFAULT_CLEARANCE_RDU, frame=frame)
        p = GtProbe(scene, gt, v)
        sq = gt.instances == 1
        weed = (gt.material == 3) | (gt.material == 4)
        r = {"occupancy": occ, "material_volume_rdu3": v.material_volume_rdu3(),
             "by_clearance": []}
        for c in CLEARANCE_SWEEP_RDU:
            ins = p.inside(v, c)
            r["by_clearance"].append({
                "clearance_rdu": c, "volume_rdu3": v.volume_rdu3(c),
                "gt_squash_covered": float((ins & sq).sum() / sq.sum()),
                "gt_weed_inside": float((ins & weed).sum() / weed.sum())})
        rows.append(r)
        print("occupancy", occ, r["material_volume_rdu3"])
        del v, p
        gc.collect()
    sweeps["occupancy"] = rows

    # 3. the unseen halo (A4's unresolved edges)
    rows = []
    for inc in (False, True):
        v = build_keepout(scene, crop, cell=DEFAULT_CELL_RDU,
                          include_unseen=inc,
                          clearance=DEFAULT_CLEARANCE_RDU, frame=frame)
        p = GtProbe(scene, gt, v)
        sq = gt.instances == 1
        weed = (gt.material == 3) | (gt.material == 4)
        ins = p.inside(v, DEFAULT_CLEARANCE_RDU)
        rows.append({"include_unseen": inc,
                     "material_volume_rdu3": v.material_volume_rdu3(),
                     "volume_at_default_rdu3":
                         v.volume_rdu3(DEFAULT_CLEARANCE_RDU),
                     "gt_squash_covered": float((ins & sq).sum() / sq.sum()),
                     "gt_weed_inside": float((ins & weed).sum() / weed.sum())})
        print("include_unseen", inc, rows[-1]["volume_at_default_rdu3"])
        del v, p
        gc.collect()
    sweeps["unseen_halo"] = rows

    # 4. the A4 policy — merge (shipped, A4's instruction) vs the largest
    #    component of split
    rows = []
    for policy in ("merge", "default"):
        cp = load_crop_component(policy, gt=gt)
        v = build_keepout(scene, cp, cell=DEFAULT_CELL_RDU,
                          clearance=DEFAULT_CLEARANCE_RDU, frame=frame)
        p = GtProbe(scene, gt, v)
        sq = gt.instances == 1
        weed = (gt.material == 3) | (gt.material == 4)
        r = {"a4_policy": policy, "component_id": cp.component_id,
             "component_px": int(cp.observed.sum()),
             "unseen_px": int(cp.unseen.sum()),
             "unresolved_edges": cp.n_unresolved,
             "material_volume_rdu3": v.material_volume_rdu3(),
             "by_clearance": []}
        for c in CLEARANCE_SWEEP_RDU:
            ins = p.inside(v, c)
            r["by_clearance"].append({
                "clearance_rdu": c, "volume_rdu3": v.volume_rdu3(c),
                "gt_squash_covered": float((ins & sq).sum() / sq.sum()),
                "gt_weed_inside": float((ins & weed).sum() / weed.sum())})
        rows.append(r)
        print("policy", policy, r["by_clearance"][-1])
        del v, p, cp
        gc.collect()
    sweeps["a4_policy"] = rows

    json.dump(sweeps, open(os.path.join(RESULTS, "sweeps.json"), "w"), indent=1)
    print(f"done in {time.time()-t0:.0f}s")


if __name__ == "__main__":
    main()
