"""Probe stage A1 — publish the two depth products for plants2.jpeg in A1's
manifest schema, with the instrument constants RE-MEASURED on this raster
(A1 measured them per image; they are category (a) and must not be copied
from plants.jpeg), and compare DA3's camera-head focal estimate with the one
A1b adopted for plants.jpeg.

Runs in chunks/A1/.venv. Mirrors chunks/A1/export_products.py; nothing here is
new method.
"""
import json
import time

import numpy as np

from probe_common import (CH, F_PLANTS_ASSUMED_PX, IMAGE, P, PRIMARY_GEOMETRY,
                          PRIMARY_RASTER, RESULTS, on_path)

on_path("A1")
from depth_to_cloud import depth_to_cloud, load_depth_product, save_cloud  # noqa: E402
from measure_quantisation import (immerkaer_sigma, local_plane_residuals,  # noqa: E402
                                  noise_floor, representation_step)

A1P = P["A1"]
depth_dir = A1P / "depth"
out_dir = A1P / "products"
out_dir.mkdir(exist_ok=True)


def log(m):
    print(f"[{time.strftime('%H:%M:%S')}] {m}", flush=True)


# ---------------------------------------------------------------- camera rows
TOL = 0.05   # A1's registered pixel-aspect tolerance (camera_report.py)
ref = json.load(open(CH["A1"] / "results" / "camera.json"))
ref_rows = {r["run"]: r for r in ref["runs"]}
rows = []
for d in sorted(depth_dir.iterdir()):
    if not (d / "provenance.json").exists():
        continue
    prov = json.load(open(d / "provenance.json"))
    cam = prov["camera"]["intrinsics"]
    aspect = cam["fx_px"] / cam["fy_px"]
    f0 = cam["f_at_original_resolution_px"]
    row = {
        "run": d.name,
        "process_res": prov["preprocessing"]["process_res"],
        "fx_px": cam["fx_px"], "fy_px": cam["fy_px"],
        "pixel_aspect_fx_over_fy": aspect,
        "physically_consistent": bool(abs(aspect - 1.0) <= TOL),
        "f_at_3000x4000_px": {"fx": f0["fx"], "fy": f0["fy"]},
        "f_at_3000x4000_px_mean": 0.5 * (f0["fx"] + f0["fy"]),
        "fov_h_deg": cam["fov_horizontal_deg"], "fov_v_deg": cam["fov_vertical_deg"],
        "equiv_mm": cam["implied_35mm_equiv_mm"],
    }
    r = ref_rows.get(d.name)
    if r:
        row["plants_jpeg_same_run"] = {k: r[k] for k in r if k != "run"}
    rows.append(row)

good = [r for r in rows if r["physically_consistent"]]
fs = [r["f_at_3000x4000_px_mean"] for r in good]
cam_report = {
    "image": IMAGE.name,
    "pixel_aspect_tolerance": TOL,
    "runs": rows,
    "consistent_runs": [r["run"] for r in good],
    "f_at_3000x4000_consistent_px": {
        "min": min(fs) if fs else None, "max": max(fs) if fs else None,
        "mean": float(np.mean(fs)) if fs else None,
    },
    "plants_jpeg_reference": {
        "A1b_adopted_f_px": F_PLANTS_ASSUMED_PX,
        "A1_consistent_band_px": ref["fov_stability"]["f_at_3000x4000_px"],
        "roadmap_prior_26mm_px": 3005.0,
    },
    "same_camera_evidence": (
        "plants.jpeg and plants2.jpeg have identical JPEG quantisation tables, "
        "identical 4:2:0 subsampling, identical JFIF/ICC structure, no EXIF, and "
        "identical 3000x4000 dimensions. That is consistent with the same phone, "
        "but a messaging app's re-encode would produce the same fingerprint, so "
        "it is evidence of the same DELIVERY PATH, not proof of the same lens."),
}
json.dump(cam_report, open(RESULTS / "a1_camera.json", "w"), indent=1)
print(f"{'run':32} {'res':>5} {'fx/fy':>6} {'f@3000':>7} {'mm-eq':>6} cons | plants.jpeg: keys")
for r in rows:
    pj = r.get("plants_jpeg_same_run", {})
    print(f"{r['run']:32} {r['process_res']:5d} {r['pixel_aspect_fx_over_fy']:6.3f} "
          f"{r['f_at_3000x4000_px_mean']:7.0f} {r['equiv_mm']:6.1f} "
          f"{'yes' if r['physically_consistent'] else 'NO '} | {sorted(pj)[:8]}")
print(f"consistent band plants2: {cam_report['f_at_3000x4000_consistent_px']}")

# ------------------------------------------------------------------ products
geom = load_depth_product(depth_dir / PRIMARY_GEOMETRY)
rast = load_depth_product(depth_dir / PRIMARY_RASTER)
camera_for_raster = geom.model_intrinsics.scaled_to(width=rast.shape[1], height=rast.shape[0])

c_geom = depth_to_cloud(geom, mode="scale_free")
save_cloud(c_geom, out_dir / "cloud_primary_geometry_scale_free")
c_rast = depth_to_cloud(rast, camera_for_raster, mode="scale_free")
save_cloud(c_rast, out_dir / "cloud_primary_raster_scale_free")
log(f"clouds written; raster normaliser {c_rast.normaliser:.4f} depth units per rdu")

# -------------------------------------------- instrument constants, re-measured
ras = c_rast.as_raster(rast.shape)
immerkaer = immerkaer_sigma(ras[..., 2])
by_win = {}
for win in (3, 5, 9, 17, 33):
    t0 = time.time()
    r = local_plane_residuals(ras, win=win, stride=win)
    by_win[f"win{win}"] = noise_floor(r)
    log(f"  local planarity win{win}: p10={by_win[f'win{win}']['p10']:.3e} rdu "
        f"(n={r.size}, {time.time()-t0:.0f}s)")
rep = representation_step(rast.depth.astype(np.float64))
ref_man = json.load(open(CH["A1"] / "products" / "MANIFEST.json"))
ref_ic = ref_man["instrument_constants_for_later_chunks"]

geom_aspect = geom.model_intrinsics.fx / geom.model_intrinsics.fy
rast_aspect = (rast.model_intrinsics.fx / rast.model_intrinsics.fy) if rast.model_intrinsics else float("nan")
manifest = {
    "chunk": "A1 (plants2 PROBE - not a Phase A product)",
    "image": IMAGE.name,
    "scale_confidence": "scale_free",
    "absolute_scale": ref_man["absolute_scale"],
    "model": {"hf_repo": geom.provenance["model"]["hf_repo"],
              "hf_revision": geom.provenance["model"]["hf_revision"],
              "code_commit": geom.provenance["model"]["code"]["commit"]},
    "products": {
        "primary_geometry": {
            "depth": f"depth/{PRIMARY_GEOMETRY}/depth.npy",
            "conf": f"depth/{PRIMARY_GEOMETRY}/conf.npy",
            "provenance": f"depth/{PRIMARY_GEOMETRY}/provenance.json",
            "cloud": "products/cloud_primary_geometry_scale_free.npy",
            "cloud_sidecar": "products/cloud_primary_geometry_scale_free.json",
            "shape_hw": list(geom.shape),
            "camera": geom.model_intrinsics.as_dict(),
            "camera_usable": bool(abs(geom_aspect - 1) <= TOL),
            "why": ("camera head physically consistent at this resolution"
                    if abs(geom_aspect - 1) <= TOL else
                    f"camera head NOT physically consistent even at res 504 on this image (fx/fy={geom_aspect:.3f})"),
        },
        "primary_raster": {
            "depth": f"depth/{PRIMARY_RASTER}/depth.npy",
            "conf": f"depth/{PRIMARY_RASTER}/conf.npy",
            "provenance": f"depth/{PRIMARY_RASTER}/provenance.json",
            "cloud": "products/cloud_primary_raster_scale_free.npy",
            "cloud_sidecar": "products/cloud_primary_raster_scale_free.json",
            "shape_hw": list(rast.shape),
            "camera": camera_for_raster.as_dict(),
            "camera_usable": False,
            "why": f"this run's OWN camera estimate has fx/fy = {rast_aspect:.3f}; "
                   "the camera recorded here is the res-504 estimate rescaled to this grid, as A1 did.",
        },
    },
    "depth_semantics": ref_man["depth_semantics"],
    "instrument_constants_for_later_chunks": {
        "depth_resolution_floor_rdu": immerkaer,
        "depth_resolution_floor_method": ref_ic["depth_resolution_floor_method"],
        "local_planarity_p10_rdu_by_window": {k: v["p10"] for k, v in by_win.items()},
        "for_A4_depth_continuity": ref_ic["for_A4_depth_continuity"],
        "for_A2_ransac_inlier_threshold": ref_ic["for_A2_ransac_inlier_threshold"],
        "RE_MEASURED_ON": IMAGE.name,
        "plants_jpeg_values_for_comparison": {
            "depth_resolution_floor_rdu": ref_ic["depth_resolution_floor_rdu"],
            "local_planarity_p10_rdu_by_window": ref_ic["local_planarity_p10_rdu_by_window"],
        },
    },
    "representation": rep,
    "camera_report": "probes/plants2/results/a1_camera.json",
    "downstream_rule": ref_man["downstream_rule"],
}
(out_dir / "MANIFEST.json").write_text(json.dumps(manifest, indent=2))
log(f"immerkaer floor {immerkaer:.3e} rdu (plants.jpeg {ref_ic['depth_resolution_floor_rdu']:.3e})")
log(f"-> {out_dir / 'MANIFEST.json'}")
