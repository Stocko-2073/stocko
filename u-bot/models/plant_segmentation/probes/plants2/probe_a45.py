"""Probe stages A4 + A5 — connectivity grouping and stem-soil contact points on
plants2, driven exactly as A1b's run_stage.py drives them: the shipped code,
imported, with the input/output directories substituted. Runs in chunks/A3/.venv.

No ground truth exists for plants2, so nothing here is SCORED. What is
recorded is descriptive: component counts, size distribution, A3-material
composition of the largest components, and A5's status counts.

Substitutions (and nothing else):
  * a2_api.load_a2            -> the probe's A2 products
  * a4_common.ROOT/WORK/...   -> the probe shadow root
  * a4_common.DEPTH_RESOLUTION_FLOOR_RDU -> re-measured on the plants2 raster
  * the A3 material cache     -> pre-populated from probe_a3.py, so A4 never
                                 calls segment_material() on the default image
"""
import json
import os
import sys
import time

import numpy as np
from PIL import Image

from probe_common import CH, IMAGE, P, PROBE, RESULTS, on_path

on_path("A0", "A1", "A2", "A3", "A4", "A5")


def log(m):
    print(f"[{time.strftime('%H:%M:%S')}] {m}", flush=True)


# ---- A2 redirect -----------------------------------------------------------
import a2_api  # noqa: E402
_orig_load_a2 = a2_api.load_a2
A2DIR = P["A2"] / "products"


def _load_a2(products=None, grid="native"):
    return _orig_load_a2(products=products or A2DIR, grid=grid)


a2_api.load_a2 = _load_a2

# ---- A4 redirect -----------------------------------------------------------
import a4_common as C  # noqa: E402
C.ROOT = str(PROBE)
C.WORK = str(P["A4"] / "work")
C.PRODUCTS = str(P["A4"] / "products")
C.RESULTS = str(P["A4"] / "results")
for d in (C.WORK, C.PRODUCTS, C.RESULTS):
    os.makedirs(d, exist_ok=True)
man = json.load(open(P["A1"] / "products" / "MANIFEST.json"))
FLOOR_PLANTS = C.DEPTH_RESOLUTION_FLOOR_RDU
C.DEPTH_RESOLUTION_FLOOR_RDU = man["instrument_constants_for_later_chunks"]["depth_resolution_floor_rdu"]

mat_gt = np.load(P["A3"] / "material.npy")
conf_gt = np.load(P["A3"] / "confidence.npy")
a3prov = json.load(open(RESULTS / "a3_material.json"))["provenance"]
np.savez(os.path.join(C.WORK, "a3_material.npz"), m=mat_gt, c=conf_gt,
         p=json.dumps(a3prov, default=str))

import run_a4 as R4  # noqa: E402
import unresolved as U  # noqa: E402
import eval as a0eval  # noqa: E402

inp = C.load_inputs(material_source="a3")
assert inp.provenance["partition"]["source"] == "chunks/A3/work/regions_a3f.npy"
log(f"inputs: plant px {int(inp.plant.sum())} / {inp.plant.size} "
    f"({inp.plant.mean()*100:.1f} %), regions {inp.provenance['partition']['n_regions']}, "
    f"datum sigma {inp.provenance['a2']['sigma_datum_rdu']:.3e} rdu")

CLASSES = a0eval.CLASSES
FRUIT = a0eval.CID["fruit"]
GRASS = a0eval.CID["grass"]
CROPISH = [a0eval.CID[c] for c in ("squash_leaf", "squash_petiole", "fruit")]

res = {"image": IMAGE.name, "scored": False,
       "why_unscored": "no ground truth for plants2; descriptive statistics only",
       "depth_resolution_floor_rdu": {"plants2": C.DEPTH_RESOLUTION_FLOOR_RDU, "plants": FLOOR_PLANTS},
       "a4": {}, "a5": {}}
built = {}
for policy in ("split", "merge"):
    t0 = time.time()
    r = R4.build(inp, "secdiff", None, unresolved_policy=policy)
    comp = r["comp_depth"]
    comp_gt = C.to_gt_grid_nearest(comp)
    edges, uinfo = U.find_unresolved(inp, r["frag"], r["summary"], r["conn"],
                                     r["unres"], r["comp_of"])
    n = int(comp.max())
    sizes = np.bincount(comp.ravel(), minlength=n + 1)[1:]
    order = np.argsort(-sizes)
    plant_px = int((comp > 0).sum())
    top = []
    for k in order[:8]:
        cid = int(k + 1)
        m = comp == cid
        comp_mat = inp.material[m]
        top.append({
            "component": cid, "px": int(sizes[k]),
            "fraction_of_plant_px": float(sizes[k] / plant_px),
            "material_mix": {CLASSES[c]: round(float((comp_mat == c).mean()), 3)
                             for c in np.unique(comp_mat)},
            "n_unresolved_edges": sum(1 for e in edges if cid in e.get("components", [])),
        })
    fruit_comps = np.unique(comp[(inp.material == FRUIT) & (comp > 0)])
    fruit_px_by_comp = {int(c): int(((comp == c) & (inp.material == FRUIT)).sum()) for c in fruit_comps}
    big_fruit = {c: v for c, v in fruit_px_by_comp.items() if v >= 200}
    grass_total = int(((inp.material == GRASS) & (comp > 0)).sum())
    biggest = int(order[0] + 1)
    grass_in_biggest = int(((comp == biggest) & (inp.material == GRASS)).sum())
    res["a4"][policy] = {
        "continuity_tolerance_rdu": r["tol"],
        "tolerance_provenance": r["tol_info"],
        "n_fragments": r["n_frag"],
        "n_components": n,
        "edges": {"adjacent_pairs": int(len(r["summary"]["n"])),
                  "connected": int(r["conn"].sum()),
                  "separated": int(r["sep"].sum()),
                  "unresolved_boundary": int(r["unres"].sum())},
        "unresolved_summary": uinfo,
        "component_size_px": {"max": int(sizes.max()), "median": float(np.median(sizes)),
                              "n_ge_1000px": int((sizes >= 1000).sum()),
                              "n_lt_100px": int((sizes < 100).sum())},
        "largest_components": top,
        "fruit_pixels_by_component_ge200": big_fruit,
        "n_components_holding_fruit_ge200px": len(big_fruit),
        "grass_absorbed_into_biggest_component_by_A3": (grass_in_biggest / grass_total) if grass_total else None,
        "seconds": time.time() - t0,
    }
    np.save(os.path.join(C.PRODUCTS, f"components_depth_grid_{policy}.npy"), comp)
    np.save(os.path.join(C.PRODUCTS, f"components_gt_grid_{policy}.npy"), comp_gt)
    Image.fromarray(np.clip(comp_gt, 0, 65535).astype(np.uint16)).save(
        os.path.join(C.PRODUCTS, f"components_gt_grid_{policy}.png"))
    json.dump({"chunk": "A4 (plants2 probe)", "tolerance_rdu": r["tol"], "summary": uinfo, "edges": edges},
              open(os.path.join(C.PRODUCTS, f"unresolved_edges_{policy}.json"), "w"), indent=1, default=float)
    built[policy] = {"comp": comp, "edges": edges}
    log(f"A4 {policy}: {n} components from {r['n_frag']} fragments, tol {r['tol']:.3e} rdu, "
        f"largest {sizes.max()} px = {sizes.max()/plant_px*100:.1f} % of plant px, "
        f"fruit in {len(big_fruit)} components, grass-in-biggest {res['a4'][policy]['grass_absorbed_into_biggest_component_by_A3']}")

# ---- A5 ----------------------------------------------------------------------
import a5_common as A5C  # noqa: E402
import contact_points as CP  # noqa: E402
from depth_to_cloud import Intrinsics, load_depth_product  # noqa: E402

entry = man["products"]["primary_raster"]
prod = load_depth_product(P["A1"] / os.path.dirname(entry["depth"]))
cam = entry["camera"]
intr = Intrinsics(fx=cam["fx"], fy=cam["fy"], cx=cam["cx"], cy=cam["cy"],
                  width=cam["width"], height=cam["height"],
                  provenance=cam["provenance"], note=cam["note"])
a2 = _load_a2()
norm = a2.manifest["source"]["rdu_normaliser_depth_units"]
depth_rdu = np.asarray(prod.depth, dtype=np.float64) / norm
h, w = depth_rdu.shape
dirs = A5C.ray_directions(h, w, intr)
rep = json.load(open(P["A2"] / "results" / "fit_report_primary_raster.json"))
plane_normal = np.asarray(rep["ransac"]["normal"], dtype=np.float64)
S = dirs * a2.soil_depth[..., None].astype(np.float64)
scene = A5C.Scene(
    depth_rdu=depth_rdu, dirs=dirs, P=dirs * depth_rdu[..., None], S=S,
    N=A5C.local_normals(S, plane_normal), height=a2.height.astype(np.float64),
    height_sigma=a2.height_sigma.astype(np.float64), valid=a2.valid,
    coverage=a2.coverage, ground=a2.ground, sigma_datum=a2.sigma_datum,
    intr=intr, plane_normal=plane_normal, a2_manifest=a2.manifest, a1_manifest=man)
material = A5C.gt_to_depth(mat_gt)
(P["A5"] / "products").mkdir(exist_ok=True)
for policy in ("split", "merge"):
    t0 = time.time()
    cs = CP.contact_points(scene, built[policy]["comp"], material, built[policy]["edges"])
    sc = CP.status_counts(cs)
    doc = CP.to_json(cs, scene, policy, {"status_counts": sc, "image": IMAGE.name, "probe": True})
    comps = doc["components"]
    res["a5"][policy] = {
        "status_counts": sc,
        "n_components": len(cs),
        "with_point": sum(1 for c in comps if c["point"]),
        "with_lowest_visible_point": sum(1 for c in comps if c["lowest_visible_point"]),
        "arm_admissible": sum(1 for c in comps if c.get("arm_admissible")),
        "median_confidence": float(np.median([c["confidence"] for c in comps if c["confidence"] is not None] or [np.nan])),
        "seconds": time.time() - t0,
    }
    json.dump(doc, open(P["A5"] / "products" / f"contacts_{policy}.json", "w"), indent=1)
    log(f"A5 {policy}: {sc}; admissible {res['a5'][policy]['arm_admissible']}")

res["scene"] = {"sigma_datum_rdu": scene.sigma_datum,
                "plane_tilt_from_camera_axis_deg": float(np.degrees(np.arccos(min(1.0, abs(plane_normal[2]))))),
                "camera": intr.as_dict()}
json.dump(res, open(RESULTS / "a45.json", "w"), indent=1, default=float)
log(f"wrote {RESULTS / 'a45.json'}")
