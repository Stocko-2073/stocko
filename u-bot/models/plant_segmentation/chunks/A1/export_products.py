"""
A1 — publish the two depth products later chunks are meant to consume, and a
manifest that makes the scale claim impossible to lose.

Two products, because one raster cannot be both:

`primary_geometry`  da3nested-giant-large @ process_res 504
    The only resolutions at which DA3's camera head stays physically consistent
    (fx/fy within 5% of 1) are <= 700. Anything that needs a camera — a
    back-projection, a plane normal, an angle — should start here.

`primary_raster`    da3nested-giant-large @ process_res 1344
    2.8x the linear sampling, which is what resolves petioles, and the same grid
    as the inherited preview. Its *own* camera estimate is not physically
    realisable and must not be used; pair it with the res-504 camera rescaled,
    or with A1b's refined f.

Both are emitted as scale-free clouds. Nothing here claims metres, even though
the nested model does: see FINDINGS.md.

Run: .venv/bin/python export_products.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from depth_to_cloud import depth_to_cloud, load_depth_product, save_cloud  # noqa: E402

PRIMARY_GEOMETRY = "da3nested-giant-large_res504"
PRIMARY_RASTER = "da3nested-giant-large_res1344"


def main() -> None:
    out_dir = HERE / "products"
    out_dir.mkdir(exist_ok=True)

    geom = load_depth_product(HERE / "depth" / PRIMARY_GEOMETRY)
    rast = load_depth_product(HERE / "depth" / PRIMARY_RASTER)

    # The camera to use with the high-resolution raster: the consistent one,
    # rescaled. Recorded explicitly rather than left as folklore.
    camera_for_raster = geom.model_intrinsics.scaled_to(
        width=rast.shape[1], height=rast.shape[0]
    )

    c_geom = depth_to_cloud(geom, mode="scale_free")
    save_cloud(c_geom, out_dir / "cloud_primary_geometry_scale_free")

    c_rast = depth_to_cloud(rast, camera_for_raster, mode="scale_free")
    save_cloud(c_rast, out_dir / "cloud_primary_raster_scale_free")

    quant = json.loads((HERE / "results" / "quantisation.json").read_text())
    cam = json.loads((HERE / "results" / "camera.json").read_text())
    prev = json.loads((HERE / "results" / "preview_vs_float.json").read_text())

    nf = quant["per_run"][PRIMARY_RASTER]
    manifest = {
        "chunk": "A1",
        "scale_confidence": "scale_free",
        "absolute_scale": (
            "UNRESOLVED. No fiducial, no known dimension, no EXIF. Every distance "
            "in every A1 product is in rdu (relative depth units), 1 rdu = the "
            "median scene depth of that raster. Do not convert to metres."
        ),
        "model": {
            "hf_repo": geom.provenance["model"]["hf_repo"],
            "hf_revision": geom.provenance["model"]["hf_revision"],
            "code_commit": geom.provenance["model"]["code"]["commit"],
        },
        "products": {
            "primary_geometry": {
                "depth": f"depth/{PRIMARY_GEOMETRY}/depth.npy",
                "conf": f"depth/{PRIMARY_GEOMETRY}/conf.npy",
                "provenance": f"depth/{PRIMARY_GEOMETRY}/provenance.json",
                "cloud": "products/cloud_primary_geometry_scale_free.npy",
                "cloud_sidecar": "products/cloud_primary_geometry_scale_free.json",
                "shape_hw": list(geom.shape),
                "camera": geom.model_intrinsics.as_dict(),
                "camera_usable": True,
                "why": "camera head physically consistent at this resolution",
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
                "why": (
                    "this run's OWN camera estimate has fx/fy = "
                    f"{[r for r in cam['runs'] if r['run'] == PRIMARY_RASTER][0]['pixel_aspect_fx_over_fy']:.3f}, "
                    "physically impossible for square pixels. The camera recorded "
                    "here is the res-504 estimate rescaled to this grid."
                ),
            },
        },
        "depth_semantics": {
            "quantity": "depth (z along the optical axis), not disparity, not ray length",
            "dtype": "float32",
            "container": ".npy — no normalisation, no clipping, no 8-bit anywhere",
        },
        "instrument_constants_for_later_chunks": {
            "depth_resolution_floor_rdu": nf["immerkaer_sigma_rdu"],
            "depth_resolution_floor_method": (
                "robust second-difference (Immerkaer) estimator on the primary "
                "raster, MAD-based; the smallest pixel-to-pixel depth step the "
                "raster can express distinguishably"
            ),
            "local_planarity_p10_rdu_by_window": {
                k: v["p10"] for k, v in nf["noise_floor_by_window_rdu"].items()
            },
            "for_A4_depth_continuity": (
                "a tolerance below the resolution floor "
                f"({nf['immerkaer_sigma_rdu']:.2e} rdu) is meaningless; the "
                "practical value should be read off local_planarity_p10 at the "
                "window size A4 actually links over"
            ),
            "for_A2_ransac_inlier_threshold": (
                "the surface's own roughness dominates: p10 at win33 is "
                f"{nf['noise_floor_by_window_rdu']['win33']['p10']:.2e} rdu and the "
                "whole-scene dominant-plane fit only stabilises around 1e-2 rdu — "
                "see results/quantisation.json soil_fit_sensitivity"
            ),
        },
        "known_limits": {
            "accuracy_is_not_resolution": (
                "the resolution floor above is smoothness, not correctness. "
                "Independent DA3 variants disagree by 0.08-0.14 rdu rms after "
                "affine alignment — three orders of magnitude above the floor."
            ),
            "model_estimated_fov": cam.get("fov_stability", {}),
            "preview_verdict": prev.get("headline", {}),
        },
        "downstream_rule": (
            "every artifact derived from these products must carry "
            "scale_confidence='scale_free' (or 'assumed_scale' if A1b intrinsics "
            "were substituted). depth_to_cloud.save_cloud enforces this."
        ),
    }
    (out_dir / "MANIFEST.json").write_text(json.dumps(manifest, indent=2))

    print(f"primary_geometry cloud: {len(c_geom):,} pts, {c_geom.scale_confidence}")
    print(f"primary_raster   cloud: {len(c_rast):,} pts, {c_rast.scale_confidence}")
    print(f"-> {out_dir / 'MANIFEST.json'}")


if __name__ == "__main__":
    main()
