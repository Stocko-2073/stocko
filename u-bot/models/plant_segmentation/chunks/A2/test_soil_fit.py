"""
A2 tests.

    chunks/A1/.venv/bin/python -m pytest chunks/A2/test_soil_fit.py -q

The load-bearing ones are the last two: a synthetic garden where the ground is
curved, most of the frame is covered by canopy, and the answer is known — and a
check that the pipeline does not quietly assume level ground.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest
import scipy.sparse as sp

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "A1"))

from soil_fit import (  # noqa: E402
    PSpline2D,
    _row_kron,
    block_cv_folds,
    disk_fold_masks,
    local_plane_residuals,
    ransac_plane,
    variogram_range,
)
from fit_soil_surface import (  # noqa: E402
    below_surface_sigma,
    local_normals,
    ray_directions,
    surface_points,
)
from depth_to_cloud import Intrinsics  # noqa: E402


# ------------------------------------------------------------------ algebra


def test_row_kron_matches_dense():
    rng = np.random.default_rng(0)
    A = sp.csr_matrix(rng.random((7, 4)))
    B = sp.csr_matrix(rng.random((7, 3)))
    got = _row_kron(A, B).toarray()
    want = np.stack([np.kron(A.toarray()[i], B.toarray()[i]) for i in range(7)])
    assert np.allclose(got, want)


def test_row_kron_fast_path_is_the_spline_case():
    """B-spline design matrices have a constant nonzero count per row, which is
    what the vectorised path keys on. If that ever stops being true the slow
    path must still give the same answer."""
    s = PSpline2D((0, 100), (0, 100), 8, 8)
    u = np.linspace(0.5, 99.5, 50)
    B = s.design(u, u[::-1])
    assert np.all(np.diff(B.indptr) == 16)
    assert np.allclose(B.sum(axis=1), 1.0)  # partition of unity


# ------------------------------------------------------------------ P-spline


def test_pspline_recovers_a_smooth_surface():
    rng = np.random.default_rng(1)
    n = 20000
    u = rng.uniform(0, 200, n)
    v = rng.uniform(0, 300, n)
    f = lambda u, v: 0.01 * np.sin(u / 60) + 0.02 * np.cos(v / 90)
    z = f(u, v) + rng.normal(0, 1e-4, n)
    s = PSpline2D((0, 200), (0, 300), 12, 16).fit(u, v, z, lam=1.0)
    gu, gv = np.linspace(10, 190, 30), np.linspace(10, 290, 30)
    got = s.eval_grid(gu, gv)
    want = f(gu[None, :], gv[:, None])
    assert np.abs(got - want).max() < 5e-4


def test_pspline_lam_controls_smoothness():
    rng = np.random.default_rng(2)
    u = rng.uniform(0, 100, 5000)
    v = rng.uniform(0, 100, 5000)
    z = rng.normal(0, 1.0, 5000)
    rough = PSpline2D((0, 100), (0, 100), 10, 10).fit(u, v, z, lam=1e-6)
    smooth = PSpline2D((0, 100), (0, 100), 10, 10).fit(u, v, z, lam=1e6)
    assert np.std(rough.eval_points(u, v)) > 5 * np.std(smooth.eval_points(u, v))


def test_pspline_robust_ignores_a_one_sided_outlier_population():
    """The canopy case in miniature: a third of the data sits far above the
    surface. A least-squares fit is dragged up; the bisquare fit is not."""
    rng = np.random.default_rng(3)
    n = 9000
    u = rng.uniform(0, 100, n)
    v = rng.uniform(0, 100, n)
    z = rng.normal(0, 0.01, n)
    z[: n // 3] += 5.0
    ls = PSpline2D((0, 100), (0, 100), 8, 8).fit(u, v, z, lam=10.0)
    rb, _, _ = PSpline2D((0, 100), (0, 100), 8, 8).fit_robust(u, v, z, lam=10.0)
    assert abs(np.median(rb.eval_points(u, v))) < 0.05
    assert np.median(ls.eval_points(u, v)) > 1.0


# -------------------------------------------------------------------- RANSAC


def test_ransac_recovers_a_plane_under_heavy_outliers():
    rng = np.random.default_rng(4)
    n_ok, n_bad = 6000, 6000
    nrm = np.array([0.3, 0.5, -0.81])
    nrm /= np.linalg.norm(nrm)
    basis = np.linalg.svd(nrm[None, :])[2][1:]
    coords = rng.uniform(-1, 1, (n_ok, 2))
    on = coords @ basis + 3.0 * (-nrm) + rng.normal(0, 1e-3, (n_ok, 1)) * nrm
    off = rng.uniform(-1, 1, (n_bad, 2)) @ basis + 3.0 * (-nrm) + \
        rng.uniform(0.1, 1.0, (n_bad, 1)) * (-nrm)
    pts = np.vstack([on, off])
    fit = ransac_plane(pts, threshold=5e-3, iters=2000)
    assert abs(abs(fit.normal @ nrm) - 1) < 1e-3
    assert fit.inliers[:n_ok].mean() > 0.95
    assert fit.inliers[n_ok:].mean() < 0.05


def test_ransac_normal_points_at_the_camera_not_at_gravity():
    """Orientation is fixed by where the camera is, so a wall or a steeply
    banked bed is handled the same as a level bed. Nothing here knows which way
    is down."""
    rng = np.random.default_rng(5)
    for nrm in (np.array([0.0, 0.0, -1.0]), np.array([0.9, 0.1, -0.42])):
        nrm = nrm / np.linalg.norm(nrm)
        basis = np.linalg.svd(nrm[None, :])[2][1:]
        pts = rng.uniform(-1, 1, (4000, 2)) @ basis + 4.0 * (-nrm)
        fit = ransac_plane(pts, threshold=1e-3, iters=500)
        assert fit.normal @ (-pts.mean(0)) > 0


def test_ransac_is_deterministic():
    rng = np.random.default_rng(6)
    pts = rng.normal(size=(3000, 3))
    a = ransac_plane(pts, 0.1, iters=300)
    b = ransac_plane(pts, 0.1, iters=300)
    assert np.allclose(a.normal, b.normal) and a.offset == b.offset


# ----------------------------------------------------------------- estimators


def test_below_surface_sigma_is_the_two_sided_sigma_when_nothing_is_above():
    rng = np.random.default_rng(7)
    r = rng.normal(0, 0.004, 200000)
    assert below_surface_sigma(r) == pytest.approx(0.004, rel=0.03)


def test_below_surface_sigma_ignores_the_canopy():
    """Half the residuals are plants, arbitrarily far above. The estimate must
    not move — that is the whole reason it only looks below the surface."""
    rng = np.random.default_rng(8)
    r = rng.normal(0, 0.004, 100000)
    canopy = np.abs(rng.normal(0, 0.4, 100000)) + 0.02
    both = np.concatenate([r, canopy])
    assert below_surface_sigma(both) == pytest.approx(0.004, rel=0.05)


def test_variogram_finds_a_known_correlation_length():
    rng = np.random.default_rng(9)
    import scipy.ndimage as ndi

    field = ndi.gaussian_filter(rng.normal(size=(400, 400)), 6.0)
    v = variogram_range(field, np.ones_like(field, bool), np.arange(1, 120, 2.0))
    # a Gaussian-smoothed field decorrelates over a few filter widths
    assert 5 < v["practical_range_px"] < 60


def test_disk_folds_cover_what_they_claim():
    masks = disk_fold_masks((200, 300), [10.0, 25.0], k=3, coverage=0.2, seed=1)
    assert len(masks) == 3
    for m in masks:
        assert 0.19 < m.mean() < 0.45


def test_block_cv_folds_are_spatial_not_pointwise():
    u = np.repeat(np.arange(100), 100).astype(float)
    v = np.tile(np.arange(100), 100).astype(float)
    f = block_cv_folds(u, v, block_px=25.0, k=5)
    # every point in a block shares a fold
    for bu in range(4):
        for bv in range(4):
            m = (u // 25 == bu) & (v // 25 == bv)
            assert len(np.unique(f[m])) == 1


# ------------------------------------------------------------------ geometry


def test_heights_on_a_synthetic_tilted_plane_are_exact():
    """Camera, plane and a set of points at known perpendicular heights above
    it. Nothing is level and the camera height is unknown to the code."""
    intr = Intrinsics.from_focal_px(800, 200, 160, "assumed",
                                   principal_point_at_centre=True)
    h, w = 160, 200
    dirs = ray_directions(h, w, intr)
    nrm = np.array([0.25, 0.45, -0.86])
    nrm /= np.linalg.norm(nrm)
    offset = -3.0
    S = np.zeros((h, w))
    P = surface_points(dirs, nrm, offset, S)
    assert np.allclose(P @ nrm, offset)
    n_loc = local_normals(P, nrm)
    assert np.allclose(n_loc, nrm[None, None, :], atol=1e-9)
    # lift every ray's point 0.02 along the normal and read the height back
    lifted = P + 0.02 * nrm
    got = np.einsum("ijk,ijk->ij", lifted - P, n_loc)
    assert np.allclose(got, 0.02)


def test_local_normals_follow_a_curved_surface():
    intr = Intrinsics.from_focal_px(600, 120, 100, "assumed",
                                   principal_point_at_centre=True)
    dirs = ray_directions(100, 120, intr)
    nrm = np.array([0.0, 0.0, -1.0])
    u = np.arange(120)[None, :] * np.ones((100, 1))
    S = 0.002 * (u - 60)  # a linear ramp off the plane
    P = surface_points(dirs, nrm, -2.0, S)
    n_loc = local_normals(P, nrm)
    tilt = np.degrees(np.arccos(np.clip(n_loc @ nrm, -1, 1)))
    # a flat surface has no tilt at all ...
    flat = local_normals(surface_points(dirs, nrm, -2.0, np.zeros_like(S)), nrm)
    assert np.degrees(np.arccos(np.clip(flat @ nrm, -1, 1))).max() < 1e-6
    # ... and the ramp tilts everywhere, growing across the frame the way
    # perspective requires (the same offset ramp is a steeper slope where the
    # ground is further away).
    assert tilt[10:-10, 10:-10].min() > 10.0
    row = tilt[50, 10:-10]
    assert np.all(np.diff(row) > 0)


# ----------------------------------------------------- the end-to-end check


def _synthetic_scene(seed=11):
    """A curved 'garden': an oblique, gently domed ground surface with straw-like
    roughness, plus three plant blobs of known height covering most of the
    frame, seen by a camera at an unknown height."""
    rng = np.random.default_rng(seed)
    h, w = 300, 220
    intr = Intrinsics.from_focal_px(500, w, h, "assumed",
                                    principal_point_at_centre=True)
    dirs = ray_directions(h, w, intr)
    nrm = np.array([0.22, 0.62, -0.75])
    nrm /= np.linalg.norm(nrm)
    offset = -2.0
    v, u = np.mgrid[0:h, 0:w]
    dome = 0.08 * np.sin(np.pi * u / w) * np.sin(np.pi * v / h)   # not flat
    roughness = 0.004 * rng.normal(size=(h, w))
    S_true = dome + roughness
    P_ground = surface_points(dirs, nrm, offset, S_true)

    lift = np.zeros((h, w))
    for cy, cx, r, ht in ((80, 60, 45, 0.30), (200, 150, 60, 0.18), (250, 40, 35, 0.05)):
        lift[(v - cy) ** 2 + (u - cx) ** 2 < r * r] = ht
    P = surface_points(dirs, nrm, offset, S_true + lift)
    depth = P[..., 2]
    return depth, intr, nrm, offset, dome, lift, S_true


def test_end_to_end_recovers_known_heights_on_a_curved_ground():
    from fit_soil_surface import below_surface_sigma  # noqa: F401

    depth, intr, nrm_true, offset, dome, lift, S_true = _synthetic_scene()
    h, w = depth.shape
    dirs = ray_directions(h, w, intr)
    xyz = dirs * depth[..., None]
    pts = xyz.reshape(-1, 3)

    plane = ransac_plane(pts, threshold=0.004, iters=3000)
    assert abs(abs(plane.normal @ nrm_true) - 1) < 5e-3

    d_plane = plane.signed_distance(pts)
    v_f, u_f = (np.mgrid[0:h, 0:w]).reshape(2, -1).astype(float)
    s_field = np.zeros(h * w)
    for _ in range(6):
        sig = below_surface_sigma(d_plane - s_field)
        cand = np.abs(d_plane - s_field) < 3 * sig
        spl, _, _ = PSpline2D((0, w - 1), (0, h - 1), 12, 16).fit_robust(
            u_f[cand], v_f[cand], d_plane[cand], lam=30.0
        )
        s_field = spl.eval_grid(np.arange(w, dtype=float),
                                np.arange(h, dtype=float)).ravel()

    P_soil = surface_points(dirs, plane.normal, plane.offset, s_field.reshape(h, w))
    n_loc = local_normals(P_soil, plane.normal)
    height = np.einsum("ijk,ijk->ij", xyz - P_soil, n_loc)

    # the recovered datum roughness is the roughness that was put in
    assert sig == pytest.approx(0.004, rel=0.35)
    # heights on bare ground sit at zero
    bare = lift == 0
    assert abs(np.median(height[bare])) < 0.01
    # and each plant comes back at its own height
    for ht in (0.30, 0.18, 0.05):
        m = lift == ht
        assert np.median(height[m]) == pytest.approx(ht, abs=0.02)


def test_a_level_ground_assumption_would_have_failed_this_scene():
    """Guard against a regression into 'the ground is a plane'. On the same
    synthetic scene a single global plane leaves a residual as large as the dome
    it ignored, while the fitted field does not."""
    depth, intr, nrm_true, offset, dome, lift, S_true = _synthetic_scene()
    h, w = depth.shape
    dirs = ray_directions(h, w, intr)
    pts = (dirs * depth[..., None]).reshape(-1, 3)
    plane = ransac_plane(pts, threshold=0.004, iters=3000)
    bare = (lift == 0).ravel()
    plane_resid = plane.signed_distance(pts)[bare]
    assert np.sqrt((plane_resid**2).mean()) > 5 * 0.004


def test_local_planarity_curve_grows_with_window():
    rng = np.random.default_rng(12)
    v, u = np.mgrid[0:200, 0:200]
    z = 3.0 + 0.001 * (u**1.5) / 100 + rng.normal(0, 1e-4, u.shape)
    xyz = np.stack([u * 0.01, v * 0.01, z], -1)
    p = [np.percentile(local_plane_residuals(xyz, win=k), 10) for k in (5, 17, 33)]
    assert p[0] < p[1] < p[2]
