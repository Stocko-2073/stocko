"""
A1 — what is the depth resolution of the float output, really?

Three different things get called "depth quantisation" and only one of them is
the number A2 and A4 should consume:

1. **Representation step.** The smallest gap between distinct values in the
   stored raster. Tells you whether the container is throwing information away.
   For a float32 `.npy` it is ~1e-7 relative and irrelevant; for the 8-bit
   preview it is 1/255 of the range and dominates everything.

2. **Effective depth resolution (the noise floor).** How flat a genuinely flat
   surface comes out. This is what a RANSAC inlier threshold or a
   depth-continuity tolerance has to clear, and it is the honest category (a)
   instrument constant. Measured here as the residual of a local plane fit in
   small windows, taking a low percentile over windows so leaf edges and canopy
   structure do not contaminate the estimate.

3. Model *disagreement* (between DA3 variants or resolutions). Much larger, and
   a different quantity — model uncertainty, not instrument resolution. Reported
   separately so it never gets mistaken for (2).

Everything is reported in relative depth units (rdu, 1 rdu = median scene
depth), because Phase A is scale-free.

Run: .venv/bin/python measure_quantisation.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from depth_to_cloud import depth_to_cloud, load_depth_product  # noqa: E402

RNG = np.random.default_rng(20260901)


# ---------------------------------------------------------------- 1. storage


def representation_step(depth: np.ndarray) -> dict:
    v = np.unique(depth[np.isfinite(depth)].astype(np.float64))
    gaps = np.diff(v)
    span = float(v[-1] - v[0])
    return {
        "n_pixels": int(depth.size),
        "n_distinct_values": int(v.size),
        "distinct_fraction": float(v.size / depth.size),
        "range": [float(v[0]), float(v[-1])],
        "min_gap": float(gaps.min()) if gaps.size else 0.0,
        "median_gap": float(np.median(gaps)) if gaps.size else 0.0,
        "min_gap_over_range": float(gaps.min() / span) if gaps.size else 0.0,
        "effective_bits": float(np.log2(v.size)),
    }


# -------------------------------------------------- 2. local planarity floor


def local_plane_residuals(
    xyz_raster: np.ndarray, win: int = 9, stride: int = 4, min_pts: int | None = None
) -> np.ndarray:
    """RMS residual of a least-squares plane fit inside each win x win window.

    Works on a 3-D point raster (H, W, 3) so the fit is in real geometry, not in
    the depth image. Windows with any invalid pixel are skipped.
    """
    h, w, _ = xyz_raster.shape
    if min_pts is None:
        min_pts = win * win
    out = []
    for r0 in range(0, h - win + 1, stride):
        for c0 in range(0, w - win + 1, stride):
            blk = xyz_raster[r0 : r0 + win, c0 : c0 + win].reshape(-1, 3)
            if not np.isfinite(blk).all() or blk.shape[0] < min_pts:
                continue
            centred = blk - blk.mean(0)
            # smallest singular value / sqrt(n) is exactly the RMS orthogonal
            # distance to the best-fit plane
            s = np.linalg.svd(centred, compute_uv=False)
            out.append(s[-1] / np.sqrt(blk.shape[0]))
    return np.asarray(out)


def immerkaer_sigma(z: np.ndarray) -> float:
    """High-frequency noise in the depth raster from a robust second-difference
    estimator. The 3x3 kernel [[1,-2,1],[-2,4,-2],[1,-2,1]] annihilates any
    locally-linear surface, so what is left is noise plus edges; the MAD (not
    the mean) keeps leaf edges from inflating it.
    """
    from numpy.lib.stride_tricks import sliding_window_view

    k = np.array([[1.0, -2, 1], [-2, 4, -2], [1, -2, 1]])
    v = sliding_window_view(z, (3, 3))
    lap = np.einsum("ijkl,kl->ij", v, k)
    lap = lap[np.isfinite(lap)]
    mad = float(np.median(np.abs(lap - np.median(lap))))
    # MAD -> sigma for a Gaussian, then divide by the kernel norm ||k|| = 6
    return 1.4826 * mad / 6.0


def noise_floor(resid: np.ndarray) -> dict:
    """The low percentiles are the flattest windows in the scene — straw, soil,
    the inside of a big leaf. Their residual is the instrument floor. Higher
    percentiles are scene structure, not noise."""
    q = {f"p{p:02d}": float(np.percentile(resid, p)) for p in (1, 5, 10, 25, 50, 90)}
    return {
        "n_windows": int(resid.size),
        **q,
        "recommended_sigma_rdu": q["p10"],
        "rationale": (
            "10th-percentile window residual: flat enough to be surface, common "
            "enough not to be a lucky window"
        ),
    }


# ------------------------------------------------------------------ RANSAC


def ransac_plane(
    pts: np.ndarray, thresh: float, iters: int = 2000, rng=RNG
) -> tuple[np.ndarray, float, np.ndarray]:
    """Plain 3-point RANSAC plane fit. Returns (normal, offset, inlier mask).

    `thresh` is an orthogonal distance in the same units as `pts`.
    """
    n = pts.shape[0]
    best_mask = np.zeros(n, bool)
    best_count = -1
    for _ in range(iters):
        idx = rng.choice(n, 3, replace=False)
        p0, p1, p2 = pts[idx]
        nrm = np.cross(p1 - p0, p2 - p0)
        norm = np.linalg.norm(nrm)
        if norm < 1e-12:
            continue
        nrm = nrm / norm
        d = float(nrm @ p0)
        mask = np.abs(pts @ nrm - d) < thresh
        c = int(mask.sum())
        if c > best_count:
            best_count, best_mask = c, mask
    # refit on inliers
    inl = pts[best_mask]
    centred = inl - inl.mean(0)
    _, _, vt = np.linalg.svd(centred, full_matrices=False)
    nrm = vt[-1]
    d = float(nrm @ inl.mean(0))
    mask = np.abs(pts @ nrm - d) < thresh
    return nrm, d, mask


def soil_fit_report(pts: np.ndarray, thresh: float, label: str) -> dict:
    nrm, d, mask = ransac_plane(pts, thresh)
    resid = pts @ nrm - d
    inl = resid[mask]
    return {
        "label": label,
        "threshold_rdu": thresh,
        "inlier_fraction": float(mask.mean()),
        "n_inliers": int(mask.sum()),
        "inlier_residual_rms_rdu": float(np.sqrt((inl**2).mean())),
        "inlier_residual_mad_rdu": float(np.median(np.abs(inl - np.median(inl)))),
        "all_point_residual_rms_rdu": float(np.sqrt((resid**2).mean())),
        "plane_normal": nrm.tolist(),
        "plane_offset_rdu": float(d),
        # angle between the fitted surface normal and the camera axis: a sanity
        # check that we found a ground-like plane and not a leaf
        "tilt_from_camera_axis_deg": float(
            np.degrees(np.arccos(min(1.0, abs(nrm[2]))))
        ),
    }


# --------------------------------------------------------------------- main


def main() -> None:
    results: dict = {}
    depth_dir = HERE / "depth"
    runs = sorted(p.name for p in depth_dir.iterdir() if (p / "depth.npy").exists())
    print("runs:", runs)

    # The raster A2/A4 will actually consume: flagship model, finest resolution
    # whose depth still looks like the scene. Its *camera* is not usable — see
    # camera_report.py — but the noise floor is a property of the depth field.
    primary = "da3nested-giant-large_res1344"
    # The multi-window noise-floor analysis is slow, so it runs only on the
    # resolutions later chunks might plausibly use.
    deep = {
        "da3-large_res504",
        "da3-large_res1344",
        "da3nested-giant-large_res504",
        "da3nested-giant-large_res1344",
    }
    per_run = {}

    for run in runs:
        prod = load_depth_product(depth_dir / run)
        depth = prod.depth.astype(np.float64)
        rep = representation_step(depth)

        entry = {"representation": rep}

        if prod.model_intrinsics is not None and run in deep:
            cloud = depth_to_cloud(prod, mode="scale_free")
            ras = cloud.as_raster(prod.shape)
            entry["immerkaer_sigma_rdu"] = immerkaer_sigma(ras[..., 2])
            # The local-plane residual is a function of window size: a 3x3
            # window sees only pixel-scale noise, a 33x33 window also sees the
            # surface's own low-frequency error. A4 (adjacent continuity) wants
            # the small end; A2 (a soil surface fit) wants the large end.
            by_win = {}
            for win in (3, 5, 9, 17, 33):
                r = local_plane_residuals(ras, win=win, stride=win)
                by_win[f"win{win}"] = noise_floor(r)
                if win == 9:
                    entry["noise_floor_rdu"] = by_win[f"win{win}"]
            entry["noise_floor_by_window_rdu"] = by_win
            entry["normaliser_depth_units_per_rdu"] = cloud.normaliser
            entry["intrinsics"] = cloud.intrinsics.as_dict()
        else:
            entry["noise_floor_rdu"] = None
            entry["note"] = (
                "no Euclidean cloud for this run: either the preset has no camera "
                "head, or it is outside the shortlist the deep analysis runs on"
            )
        per_run[run] = entry
        print(
            f"  {run}: distinct={rep['n_distinct_values']} "
            f"({rep['effective_bits']:.1f} bits), min_gap/range={rep['min_gap_over_range']:.2e}"
            + (
                f", noise floor p10={entry['noise_floor_rdu']['p10']:.2e} rdu"
                if entry.get("noise_floor_rdu")
                else ""
            )
        )

    results["per_run"] = per_run

    # ---- 3. cross-model disagreement, on the common 1344 grid --------------
    common = [r for r in runs if r.endswith("_res1344")]
    if len(common) > 1:
        ds = {}
        for r in common:
            d = np.load(depth_dir / r / "depth.npy").astype(np.float64)
            ds[r] = d / np.median(d)
        pairs = {}
        keys = sorted(ds)
        for i, a in enumerate(keys):
            for b in keys[i + 1 :]:
                # align b to a with the best least-squares affine map, then look
                # at what is left: that is genuine shape disagreement
                A = np.stack([ds[b].ravel(), np.ones(ds[b].size)], 1)
                coef, *_ = np.linalg.lstsq(A, ds[a].ravel(), rcond=None)
                res = ds[a].ravel() - A @ coef
                pairs[f"{a} vs {b}"] = {
                    "affine_gain": float(coef[0]),
                    "affine_offset": float(coef[1]),
                    "residual_rms_rdu": float(np.sqrt((res**2).mean())),
                    "residual_p95_abs_rdu": float(np.percentile(np.abs(res), 95)),
                }
        results["cross_model_disagreement"] = pairs
        print("\ncross-model disagreement (after best affine alignment):")
        for k, v in pairs.items():
            print(f"  {k}: rms={v['residual_rms_rdu']:.4f} rdu")

    # ---- soil-surface fit on the primary run, sensitivity-swept ------------
    if (depth_dir / primary).exists():
        prod = load_depth_product(depth_dir / primary)
        cloud = depth_to_cloud(prod, mode="scale_free", subsample=3)
        sigma = per_run[primary]["noise_floor_rdu"]["recommended_sigma_rdu"]
        sweep = {}
        print("\nsoil-plane RANSAC threshold sweep (primary run, scale-free):")
        for k in (1, 3, 10, 30, 100, 300, 1000):
            key = f"{k}sigma"
            sweep[key] = soil_fit_report(cloud.xyz, k * sigma, key)
            print(
                f"  @ {k:>4d} sigma = {k * sigma:.5f} rdu -> "
                f"inliers {sweep[key]['inlier_fraction']:.3f}, "
                f"rms {sweep[key]['inlier_residual_rms_rdu']:.5f} rdu, "
                f"tilt {sweep[key]['tilt_from_camera_axis_deg']:.1f} deg"
            )
        results["soil_fit_sensitivity"] = {
            "primary_run": primary,
            "sigma_rdu": sigma,
            "sweep": sweep,
        }

    out = HERE / "results" / "quantisation.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(results, indent=2))
    print(f"\n-> {out}")


if __name__ == "__main__":
    main()
