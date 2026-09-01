"""A1b step 3 — re-run the downstream Phase A stack at one assumed focal length.

    chunks/A1/.venv/bin/python chunks/A1b/run_stage.py --f 3005      # A2 only
    chunks/A3/.venv/bin/python chunks/A1b/run_stage.py --f 3005 --stage a45

Two venvs are involved, and that is not avoidable: A2 was built and run in
`chunks/A1/.venv`, A4/A5 in `chunks/A3/.venv` (A4's README). Each stage runs in
the venv its chunk shipped with, so nothing is re-measured under a different
numpy or scipy than the number it is being compared to.

What this does **not** do is fork the upstream chunks. A2's `fit_soil_surface`,
A4's `run_a4`/`report` and A5's `contact_points` are imported and driven, with
exactly two substitutions:

* the camera — A2's `load_product` is replaced so the back-projection uses
  A1b's assumed pinhole instead of the camera in A1's manifest;
* the output directory — so nothing lands in another chunk's `products/`.

Every other constant, threshold and code path is the shipped one. Where a chunk
*measures* a constant off the image (A4's continuity tolerance, A2's RANSAC
threshold and `lam`), it is re-measured at each `f`, because that is what those
chunks do per image and freezing them would hide the very sensitivity being
looked for.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from a1b_common import (A0, A1, A2, A3, A4, A5, WORK, assumed_intrinsics,  # noqa: E402
                        equiv_mm_from_f_px, f_native_of, manifest_intrinsics,
                        tag_for)


def log(m):
    print(f"[{time.strftime('%H:%M:%S')}] {m}", flush=True)


def _load_by_path(name, path):
    import importlib.util
    spec = importlib.util.spec_from_file_location(name, str(path))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


# --------------------------------------------------------------------------
# stage 1 — A2's soil surface, under the assumed camera
# --------------------------------------------------------------------------


def run_a2(tag: str, f_native: float | None, aspect: str, product: str,
           quick: bool, seed_plane: dict | None = None):
    sys.path.insert(0, str(A2))
    sys.path.insert(0, str(A1))
    import fit_soil_surface as FS

    outdir = WORK / tag
    outdir.mkdir(parents=True, exist_ok=True)
    (outdir / "products").mkdir(exist_ok=True)
    (outdir / "results").mkdir(exist_ok=True)

    orig_load = FS.load_product

    def patched(name):
        manifest, entry, prod, _ = orig_load(name)
        h, w = prod.depth.shape
        if aspect == "manifest":
            intr = manifest_intrinsics(name)
            if (intr.width, intr.height) != (w, h):
                intr = intr.scaled_to(width=w, height=h)
        else:
            intr = assumed_intrinsics(
                f_native, width=w, height=h, provenance="assumed",
                note=f"A1b sweep row {tag}: pinhole, square pixels, principal "
                     f"point at the grid centre, zero distortion; "
                     f"f={f_native:.1f} px at 3000x4000 "
                     f"({equiv_mm_from_f_px(f_native):.2f} mm-equivalent). "
                     f"Category (d) assumption. Absolute scale UNRESOLVED.")
        entry = dict(entry)
        entry["camera_usable"] = aspect == "manifest"
        entry["why"] = (
            "A1's shipped camera (reference row)" if aspect == "manifest"
            else f"A1b assumed camera, sweep row {tag}")
        return manifest, entry, prod, intr

    orig_ransac = FS.ransac_plane
    if seed_plane is not None:
        # --- the seed-controlled variant -----------------------------------
        # A2 seeds its outer loop with a RANSAC plane found at ~1.2 % inliers.
        # At that inlier fraction the seed is a lottery, and rescaling the cloud
        # changes which ticket wins: the seed normal jumps between two families
        # somewhere between f = 4159 and f = 4453. That is an A2 property, not a
        # focal-length effect, and it would otherwise contaminate the sweep. In
        # this mode the seed plane is instead *transported* from the reference
        # row by the exact closed form (a1b_common.normal_at_f), so every row
        # starts from the same physical plane and only `f` differs.
        n0 = np.asarray(seed_plane["normal"], float)
        d0 = float(seed_plane["offset"])
        fx0, fy0 = float(seed_plane["fx_native"]), float(seed_plane["fy_native"])
        fx1 = fy1 = float(f_native)
        if aspect == "manifest":
            fx1, fy1 = f_native_of(manifest_intrinsics(product))

        from soil_fit import PlaneFit

        def transported(pts, threshold, **kw):
            # A plane n.X = d under the reference camera becomes
            # (S^-1 n).X' = d under this row's camera, with
            # S = diag(fx0/fx1, fy0/fy1, 1). Renormalise to a unit normal.
            n = np.array([n0[0] * fx1 / fx0, n0[1] * fy1 / fy0, n0[2]])
            k = float(np.linalg.norm(n))
            n, d = n / k, d0 / k
            mask = np.abs(pts @ n - d) < threshold
            return PlaneFit(n, d, mask, float(threshold), 0)

        FS.ransac_plane = transported

    FS.load_product = patched
    FS.HERE = outdir            # products/ and results/ land under work/<tag>/
    argv = sys.argv
    # `--out primary_raster` is what makes A2 write to `<HERE>/products` rather
    # than `<HERE>/products_<tag>` (see `fit_soil_surface.main`), and it names
    # the report `fit_report_primary_raster.json`, which `build_scene` reads.
    sys.argv = (["fit_soil_surface.py", "--product", product,
                 "--out", "primary_raster"] + (["--quick"] if quick else []))
    try:
        FS.main()
    finally:
        sys.argv = argv
        FS.load_product = orig_load
        FS.ransac_plane = orig_ransac
    return outdir


# --------------------------------------------------------------------------
# stage 2/3 — A4 and A5 against that soil surface
# --------------------------------------------------------------------------


def run_a45(tag: str, f_native: float | None, aspect: str, product: str):
    outdir = WORK / tag
    a2dir = outdir / "products"
    assert (a2dir / "A2_MANIFEST.json").exists(), f"run --stage a2 first: {a2dir}"

    for p in (A0, A1, A2, A3, A4, A5):
        if str(p) not in sys.path:
            sys.path.insert(0, str(p))

    import a2_api
    _orig_load_a2 = a2_api.load_a2

    def load_a2_patched(products=None, grid="native"):
        return _orig_load_a2(products=products or a2dir, grid=grid)

    a2_api.load_a2 = load_a2_patched

    import a4_common as C
    import a4_graph as G          # noqa: F401  (imported by run_a4)
    import run_a4 as R4
    import report as RPT
    import unresolved as U
    import fast_eval as FE
    import eval as a0eval

    C.RESULTS = str(outdir / "results")
    C.PRODUCTS = str(outdir / "products_a4")
    os.makedirs(C.RESULTS, exist_ok=True)
    os.makedirs(C.PRODUCTS, exist_ok=True)

    gt = a0eval.load_gt()
    inp = C.load_inputs(material_source="a3")
    a2m = json.loads((a2dir / "A2_MANIFEST.json").read_text())

    res = {"tag": tag, "f_native_px": f_native, "aspect": aspect,
           "a2": {k: v for k, v in a2m["key_numbers"].items()},
           "a4": {}, "a5": {}}

    built = {}
    for policy in ("split", "merge"):
        t0 = time.time()
        r = R4.build(inp, "secdiff", None, unresolved_policy=policy)
        comp_gt = C.to_gt_grid_nearest(r["comp_depth"])
        rep = a0eval.score(a0eval.Prediction(instances=comp_gt,
                                             name=f"A1b {tag} {policy}"), gt)
        v = RPT.verdicts(comp_gt, gt)
        edges, uinfo = U.find_unresolved(inp, r["frag"], r["summary"], r["conn"],
                                         r["unres"], r["comp_of"])
        res["a4"][policy] = {
            "continuity_tolerance_rdu": r["tol"],
            "tolerance_provenance": r["tol_info"],
            "n_fragments": r["n_frag"],
            "n_components": int(r["comp_depth"].max()),
            "edges": {"adjacent_pairs": int(len(r["summary"]["n"])),
                      "connected": int(r["conn"].sum()),
                      "separated": int(r["sep"].sum()),
                      "unresolved_boundary": int(r["unres"].sum())},
            "instances": {k: val for k, val in rep["instances"].items()
                          if k != "matches"},
            "verdicts": v,
            "unresolved_summary": uinfo,
            "seconds": time.time() - t0,
        }
        np.save(os.path.join(C.PRODUCTS, f"components_depth_{policy}.npy"),
                r["comp_depth"])
        built[policy] = {"comp_depth": r["comp_depth"], "comp_gt": comp_gt,
                         "edges": edges}
        log(f"  A4 {policy}: {res['a4'][policy]['n_components']} comps, "
            f"F1 {rep['instances']['f1']:.4f}, squash IoU "
            f"{v['squash_best_iou']:.3f}, grass {v['grass_absorbed_fraction']*100:.1f}%")

    # ---- A5 -----------------------------------------------------------------
    import a5_common as A5C
    import contact_points as CP
    # A4 and A5 both ship a module called `diagnostics`, and `a5_common` puts
    # A4 ahead of A5 on sys.path, so a plain import gets the wrong one. Load
    # A5's by path rather than reordering another chunk's imports.
    A5D = _load_by_path("a5_diagnostics", A5 / "diagnostics.py")

    scene = build_scene(A5C, a2dir, outdir, product, f_native, aspect)
    material = A5C.load_a3_material_depth_grid()
    for policy in ("split", "merge"):
        t0 = time.time()
        cs = CP.contact_points(scene, built[policy]["comp_depth"], material,
                               built[policy]["edges"])
        sc = CP.status_counts(cs)
        doc = CP.to_json(cs, scene, policy, {"status_counts": sc})
        gtc = A5D.gt_consistency(doc["components"], built[policy]["comp_gt"], gt,
                                 f"{tag}/{policy}")
        res["a5"][policy] = {
            "status_counts": sc,
            "n_components": len(cs),
            "with_point": sum(1 for c in doc["components"] if c["point"]),
            "with_lowest_visible_point":
                sum(1 for c in doc["components"] if c["lowest_visible_point"]),
            "arm_admissible": sum(1 for c in doc["components"]
                                  if c.get("arm_admissible")),
            "median_confidence": float(np.median(
                [c["confidence"] for c in doc["components"]
                 if c["confidence"] is not None] or [np.nan])),
            "gt_consistency": {"summary": gtc["summary"],
                               "rows": gtc["rows"],
                               "WARNING": gtc["WARNING"]},
            "seconds": time.time() - t0,
        }
        json.dump(doc, open(outdir / f"contacts_{policy}.json", "w"), indent=1)
        log(f"  A5 {policy}: {sc}")

    # the reference row has no `--f`; record the camera's own fx so every row
    # can be placed on the sweep axis
    if res["f_native_px"] is None:
        res["f_native_px"] = f_native_of(scene.intr)[0]
    res["scene"] = {
        "sigma_datum_rdu": scene.sigma_datum,
        "plane_normal": scene.plane_normal.tolist(),
        "plane_tilt_from_camera_axis_deg": float(np.degrees(np.arccos(
            min(1.0, abs(scene.plane_normal[2]))))),
        "intrinsics": scene.intr.as_dict(),
        "f_native_fx_fy": list(f_native_of(scene.intr)),
    }
    p = HERE / "results" / f"stage_{tag}.json"
    p.parent.mkdir(exist_ok=True)
    p.write_text(json.dumps(res, indent=1, default=float))
    log(f"wrote {p}")
    return res


def build_scene(A5C, a2dir, outdir, product, f_native, aspect):
    """A5's `load_scene`, with A1b's camera and this row's A2 products.

    Kept line-for-line equivalent to `a5_common.load_scene`; only the camera and
    the two paths differ. `test_a1b.py` asserts that at the reference row this
    reproduces A5's shipped scene.
    """
    from a2_api import load_a2
    from depth_to_cloud import load_depth_product

    a1m = json.loads((A1 / "products" / "MANIFEST.json").read_text())
    entry = a1m["products"][product]
    prod = load_depth_product(A1 / os.path.dirname(entry["depth"]))
    h, w = prod.depth.shape
    if aspect == "manifest":
        intr = manifest_intrinsics(product)
        if (intr.width, intr.height) != (w, h):
            intr = intr.scaled_to(width=w, height=h)
    else:
        intr = assumed_intrinsics(f_native, width=w, height=h,
                                  provenance="assumed")
    a2 = load_a2(products=a2dir)
    norm = a2.manifest["source"]["rdu_normaliser_depth_units"]
    depth_rdu = np.asarray(prod.depth, dtype=np.float64) / norm
    dirs = A5C.ray_directions(h, w, intr)
    rep = json.loads((outdir / "results" /
                      "fit_report_primary_raster.json").read_text())
    plane_normal = np.asarray(rep["ransac"]["normal"], dtype=np.float64)
    S = dirs * a2.soil_depth[..., None].astype(np.float64)
    return A5C.Scene(
        depth_rdu=depth_rdu, dirs=dirs, P=dirs * depth_rdu[..., None], S=S,
        N=A5C.local_normals(S, plane_normal), height=a2.height.astype(np.float64),
        height_sigma=a2.height_sigma.astype(np.float64), valid=a2.valid,
        coverage=a2.coverage, ground=a2.ground, sigma_datum=a2.sigma_datum,
        intr=intr, plane_normal=plane_normal, a2_manifest=a2.manifest,
        a1_manifest=a1m)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--f", type=float, default=None,
                    help="assumed focal length in px at 3000x4000")
    ap.add_argument("--aspect", default="square", choices=["square", "manifest"],
                    help="'manifest' is the reference row: A1's own anisotropic "
                         "camera, i.e. exactly what every shipped Phase A number "
                         "was computed with")
    ap.add_argument("--product", default="primary_raster")
    ap.add_argument("--stage", default="a2", choices=["a2", "a45"])
    ap.add_argument("--quick", action="store_true")
    ap.add_argument("--seed-plane-from", default=None,
                    help="path to a fit_report JSON whose RANSAC plane is "
                         "transported to this row's f instead of re-drawn; see "
                         "run_a2. Use with --tag-suffix so it does not overwrite "
                         "the shipped-pipeline row.")
    ap.add_argument("--seed-plane-fx", type=float, default=None)
    ap.add_argument("--seed-plane-fy", type=float, default=None)
    ap.add_argument("--tag-suffix", default="")
    a = ap.parse_args()
    if a.aspect == "square" and a.f is None:
        ap.error("--f is required unless --aspect manifest")
    tag = tag_for(a.f, a.aspect) + a.tag_suffix
    seed = None
    if a.seed_plane_from:
        rep = json.loads(Path(a.seed_plane_from).read_text())
        seed = {"normal": rep["ransac"]["normal"],
                "offset": rep["ransac"]["offset_rdu"],
                "fx_native": a.seed_plane_fx, "fy_native": a.seed_plane_fy}
        assert a.seed_plane_fx and a.seed_plane_fy, \
            "--seed-plane-fx/--seed-plane-fy are required with --seed-plane-from"
    log(f"=== A1b sweep row {tag} (stage {a.stage}) ===")
    if a.stage == "a2":
        run_a2(tag, a.f, a.aspect, a.product, a.quick, seed)
    else:
        run_a45(tag, a.f, a.aspect, a.product)


if __name__ == "__main__":
    main()
