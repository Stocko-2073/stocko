"""A8 — precompute everything `segment_garden` returns, once.

Why precompute
--------------
`segment_garden` is a *tool*: it must answer in a moment, and it must answer
the same way every time it is called with the same image. Every number it
returns is already a shipped product of A1-A6; this script assembles them into
one instance table plus one distance table and writes them to `products/`.

The distance table is the interesting half. A6's instruction was explicit:

    "The union over multiple keep-plants is a `min` over `distance_to_material`;
     do not rebuild volumes per query."

So this script builds a keep-out volume for **every** instance (207 of them,
~90 s in total) and records the exact rdu distance from every candidate contact
point to every instance's material. `plan_removals` then takes a min over
whichever instances the labels make keep-plants, at whatever clearance the tool
profile asks for, with no geometry left to compute. That also means the gate's
keep-out test is *independent* of the labels — which is R3 in the file layout,
not just in the prose.

Nothing here decides which instance is the crop. That decision arrives with the
labels, in `plan_removals`.

Run:  chunks/A3/.venv/bin/python chunks/A8/build_products.py
"""
from __future__ import annotations

import json
import os
import sys
import time

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import a8_common as C  # noqa: E402

sys.path.insert(0, os.path.join(C.ROOT, "chunks", "A6"))

from a6_common import DatumFrame, load_scene  # noqa: E402
from keepout import (DEFAULT_CELL_RDU, DEFAULT_CLEARANCE_RDU,  # noqa: E402
                     CLEARANCE_SWEEP_RDU, build_keepout)


def _stats(v: np.ndarray, sigma: float) -> dict:
    if v.size == 0:
        return {"n": 0}
    q = np.percentile(v, [0, 10, 50, 90, 100])
    return {"n": int(v.size),
            "min_rdu": float(q[0]), "p10_rdu": float(q[1]),
            "median_rdu": float(q[2]), "p90_rdu": float(q[3]),
            "max_rdu": float(q[4]),
            "median_sigma": float(q[2] / sigma),
            "max_sigma": float(q[4] / sigma)}


def main(out_dir: str = C.PRODUCTS, cell: float = DEFAULT_CELL_RDU,
         max_clearance: float = max(CLEARANCE_SWEEP_RDU)) -> dict:
    os.makedirs(out_dir, exist_ok=True)
    t_start = time.time()
    st = C.load_stack(with_gt=True)
    scene = load_scene()
    frame = DatumFrame.from_scene(scene)
    src = C.ComponentSource(st.a4_merge)
    sigma = float(st.a2.sigma_datum)

    import eval as a0eval
    class_name = {v: k for k, v in a0eval.CID.items()}
    a3 = np.load(os.path.join(C.ROOT, "chunks", "A4", "work",
                              "a3_material.npz"))["m"]

    ids = sorted(st.a4_merge.component_ids())
    comp_gt = st.a4_merge.components
    comp_dp = st.a4_merge.components_depth
    height = st.a2.height
    valid = st.a2.valid

    # ---- candidate contact points: A5 `split` records that have a point -----
    cand = []
    for rec in st.a5.components:
        r = rec.raw
        sid = int(r["component"])
        if sid not in st.s2m:                     # a split id with no depth-grid
            continue                              # pixels; A5 has one (id 26)
        if not r["point"]:
            continue
        cand.append((sid, st.s2m[sid], r))
    pts = np.array([c[2]["point"]["xyz_rdu"] for c in cand], dtype=np.float64)
    print(f"{len(ids)} instances, {len(cand)} candidate contact points")

    # off-frame test, per point, independent of instance (A6 `classify`)
    uv = scene.project(pts)
    h, w = scene.shape
    off_frame = (~np.isfinite(uv).all(1) | (uv[:, 0] < 0) | (uv[:, 0] > w - 1)
                 | (uv[:, 1] < 0) | (uv[:, 1] > h - 1) | (pts[:, 2] <= 0))

    # ---- one keep-out volume per instance ----------------------------------
    D = np.zeros((len(cand), len(ids)), dtype=np.float32)
    ko = {}
    t0 = time.time()
    for j, cid in enumerate(ids):
        comp = src.get(cid, identity_provenance=(
            "A8: identity is supplied by the caller's labels at plan_removals "
            "time. This volume is built for component id %d and knows nothing "
            "about whether it is crop (R3)." % cid))
        vol = build_keepout(scene, comp, cell=cell,
                            clearance=DEFAULT_CLEARANCE_RDU,
                            max_clearance=max_clearance, frame=frame)
        D[:, j] = vol.distance_to_material(pts)
        ko[cid] = {
            "material_volume_rdu3": vol.material_volume_rdu3(),
            "volume_rdu3_at_default_clearance": vol.volume_rdu3(),
            "footprint_rdu2_at_default_clearance":
                float(vol.footprint().sum()) * cell ** 2,
            "cell_rdu": float(vol.cell),
            "voxel_bracket_rdu": float(vol.voxel_bracket),
            "grid_shape": list(vol.shape),
            "frame_open": bool(vol.frame_open),
            "occupancy": vol.occupancy,
            "include_unseen": bool(vol.include_unseen),
            "default_clearance_rdu": float(vol.clearance_rdu),
            "max_clearance_rdu": float(vol.max_clearance_rdu),
        }
        del vol
        if (j + 1) % 25 == 0:
            print(f"  {j+1}/{len(ids)} volumes  {time.time()-t0:.0f}s")
    print(f"volumes built in {time.time()-t0:.0f}s")

    # ---- the instance table -------------------------------------------------
    instances = []
    audit = {}
    for cid in ids:
        m_gt = comp_gt == cid
        m_dp = comp_dp == cid
        mat = a3[m_gt]
        comp_counts = {class_name[int(k)]: int(v)
                       for k, v in zip(*np.unique(mat, return_counts=True))}
        total = max(sum(comp_counts.values()), 1)
        dominant = max(comp_counts, key=comp_counts.get) if comp_counts else None
        hv = height[m_dp & valid]
        hv = hv[np.isfinite(hv)]

        kids = st.m2s.get(cid, [])
        contacts = []
        for k, (sid, mid, r) in enumerate(cand):
            if mid != cid:
                continue
            p = r["point"]
            contacts.append({
                "contact_id": f"{cid}.{sid}",
                "split_component": sid,
                "row_in_distance_table": k,
                "status": r["status"],
                "status_reason": r["reason"],
                "point_xyz_rdu": [float(x) for x in p["xyz_rdu"]],
                "point_gt_grid_xy": [float(x) for x in p["gt_grid_xy"]],
                "point_depth_grid_xy": [float(x) for x in p["depth_grid_xy"]],
                "height_above_datum_rdu": p["height_above_datum_rdu"],
                "height_above_datum_sigma": p["height_above_datum_sigma"],
                # `material` / `datum_coverage` are absent on an extrapolated
                # point: there is no material at the landing site to name.
                "material_at_point": p.get("material"),
                "datum_coverage": p.get("datum_coverage", r["datum_coverage"]),
                "extrapolation_distance_rdu": r["extrapolation_distance_rdu"],
                "extrapolation_distance_sigma": r["extrapolation_distance_sigma"],
                "geometry_confidence": r["confidence"],
                "geometry_confidence_terms": r["confidence_terms"],
                "axis_half_angle_deg": r["axis_half_angle_deg"],
                "lateral_uncertainty_rdu": r["lateral_uncertainty_rdu"],
                "occluder": r["occluder"],
                "arm_admissible": bool(r["arm_admissible"]),
                "leaves_frame": bool(r["leaves_frame"]),
                "point_projects_off_frame": bool(off_frame[k]),
            })
        contacts.sort(key=lambda c: (-float(c["geometry_confidence"] or 0.0),
                                     c["split_component"]))
        # every split child, including the ones with no point at all
        no_point = []
        for sid in kids:
            rec = st.a5.by_component.get(sid)
            if rec is None or rec.raw["point"]:
                continue
            no_point.append({"split_component": sid,
                             "status": rec.raw["status"],
                             "status_reason": rec.raw["reason"],
                             "occluder": rec.raw["occluder"]})

        instances.append({
            "instance_id": cid,
            "n_px_gt_grid": int(m_gt.sum()),
            "n_px_depth_grid": int(m_dp.sum()),
            "crop": None,
            "crop_source": (
                "unassigned. segment_garden never decides crop identity: the "
                "label is a VLM output that arrives at plan_removals as an ID "
                "(R3). plan_removals echoes the caller's label here."),
            "material_class": dominant,
            "material_composition_px": comp_counts,
            "material_composition_fraction":
                {k: round(v / total, 4) for k, v in comp_counts.items()},
            "height_above_datum": _stats(hv, sigma),
            "split_children": kids,
            "n_split_children": len(kids),
            "contact_candidates": contacts,
            "n_contact_candidates": len(contacts),
            "n_contact_candidates_arm_admissible":
                sum(1 for c in contacts if c["arm_admissible"]),
            "split_children_without_a_point": no_point,
            "contact_point": contacts[0] if contacts else None,
            "contact_status": (contacts[0]["status"] if contacts
                               else "occluded"),
            "keep_out": ko[cid],
            "unresolved_edges": src.get(cid, "").n_unresolved,
        })
        # ---- ground truth: audit only, never returned by a tool ------------
        gi, gc = np.unique(st.gt.instances[m_gt], return_counts=True)
        gm, gmc = np.unique(st.gt.material[m_gt], return_counts=True)
        crop_px = int(gc[gi == 1].sum()) if (gi == 1).any() else 0
        weed_px = int(gc[(gi > 1) & (gi < 255)].sum())
        audit[str(cid)] = {
            "gt_instance_px": {int(a): int(b) for a, b in zip(gi, gc)},
            "gt_material_px": {class_name.get(int(a), str(a)): int(b)
                               for a, b in zip(gm, gmc)},
            "gt_crop_px": crop_px, "gt_weed_px": weed_px,
            "gt_crop_fraction": round(crop_px / max(int(m_gt.sum()), 1), 4),
            "crop_majority": bool(crop_px > weed_px and crop_px > 0),
        }

    doc = {
        "chunk": "A8",
        "tool": "segment_garden",
        "scale_confidence": C.SCALE_CONFIDENCE,
        "units": C.UNITS,
        "DATUM": C.DATUM,
        "product_target": st.a5.product_target,
        "instance_id_space": (
            "A4 `merge` component ids. This is the id space A7's VLM labelled "
            "and the id space A6's keep-out volumes are built on. Contact "
            "points come from A4 `split` components (A5's recommendation) and "
            "are bound to their merge parent; the map is a function, asserted "
            "in a8_common.split_to_merge."),
        "soil_surface": soil_summary(st, scene),
        "instances": instances,
        "provenance": {
            "a1_product": "primary_raster (1344x1008, never resampled)",
            "a2_manifest": "chunks/A2/products/A2_MANIFEST.json",
            "a3": "chunks/A4/work/a3_material.npz (A4's cache of A3's default)",
            "a4_policies": {"instances": C.MERGE_TAG, "contacts": C.SPLIT_TAG},
            "a5_policy": st.a5.policy,
            "a6": {"cell_rdu": cell, "max_clearance_rdu": max_clearance,
                   "occupancy": "column", "include_unseen": True,
                   "note": ("keep-out volumes rebuilt for EVERY instance with "
                            "keepout.build_keepout; A6's shipped volume is for "
                            "A0's crop instance only and is used in tests as a "
                            "reference, never in the gate.")},
            "seconds": round(time.time() - t_start, 1),
        },
    }
    with open(os.path.join(out_dir, "segment_garden_plants.json"), "w") as f:
        json.dump(C.jsonable(doc), f, indent=1)
    with open(os.path.join(out_dir, "gt_audit.json"), "w") as f:
        json.dump({"note": ("A0 ground truth per A4 merge component. Used ONLY "
                            "to score A8's gate in RESULTS.md. No tool reads "
                            "this file and no field of it reaches a tool "
                            "output."), "instances": audit}, f, indent=1)
    np.savez_compressed(
        os.path.join(out_dir, "keepout_distances.npz"),
        distance_rdu=D,
        instance_ids=np.array(ids, dtype=np.int32),
        contact_split_ids=np.array([c[0] for c in cand], dtype=np.int32),
        contact_instance_ids=np.array([c[1] for c in cand], dtype=np.int32),
        point_xyz_rdu=pts.astype(np.float64),
        point_off_frame=off_frame,
        frame_open=np.array([ko[c]["frame_open"] for c in ids], dtype=bool),
        voxel_bracket_rdu=np.float64(ko[ids[0]]["voxel_bracket_rdu"]),
        cell_rdu=np.float64(cell), max_clearance_rdu=np.float64(max_clearance))
    print("wrote", out_dir, f"in {time.time()-t_start:.0f}s")
    return doc


def soil_summary(st, scene) -> dict:
    """A2's fit, restated. Nothing recomputed."""
    m = st.a2.manifest
    kn = m.get("key_numbers", {})
    cov = st.a2.coverage[st.a2.valid]
    n = max(cov.size, 1)
    return {
        "datum": st.a2.datum,
        "datum_is_straw_not_soil": True,
        "datum_roughness_sigma_rdu": float(st.a2.sigma_datum),
        "scale_confidence": st.a2.scale_confidence,
        "coverage_fraction": {
            "observed": round(float((cov == 0).sum()) / n, 4),
            "interpolated": round(float((cov == 1).sum()) / n, 4),
            "extrapolated": round(float((cov == 2).sum()) / n, 4)},
        "valid_fraction": round(float(st.a2.valid.mean()), 4),
        "key_numbers": C.jsonable(kn),
        "plane_normal_camera_frame": [float(x) for x in scene.plane_n],
        "camera": scene.intrinsics.as_dict(),
        "caveat": ("Bare soil is 0 px of this frame. The surface fitted is the "
                   "top of the mulch and every height is measured against it."),
    }


if __name__ == "__main__":
    main()
