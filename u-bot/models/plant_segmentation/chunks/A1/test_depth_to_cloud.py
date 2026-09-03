"""Tests for depth_to_cloud. Run: .venv/bin/python -m pytest -q test_depth_to_cloud.py

The tests that matter most are the ones asserting the module *refuses* to work:
inventing a camera is the failure mode this chunk exists to prevent.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from depth_to_cloud import (  # noqa: E402
    ASSUMED_SCALE,
    SCALE_FREE,
    DepthProduct,
    Intrinsics,
    MissingIntrinsicsError,
    PointCloud,
    ScaleConfidenceError,
    depth_to_cloud,
    load_depth_product,
    save_cloud,
)

H, W = 40, 30
F = 100.0


def synthetic_plane(fx=F, fy=F, cx=(W - 1) / 2, cy=(H - 1) / 2, nrm=(0.2, -0.3, 1.0), d=5.0):
    """Depth raster of an exact 3-D plane n . X = d, so a planarity test on the
    recovered cloud has a known answer (residual ~ 0)."""
    n = np.asarray(nrm, dtype=np.float64)
    r, c = np.mgrid[0:H, 0:W]
    xn = (c - cx) / fx
    yn = (r - cy) / fy
    z = d / (n[0] * xn + n[1] * yn + n[2])
    return z, n, d


def hand_K() -> Intrinsics:
    return Intrinsics.from_focal_px(
        F, W, H, provenance="assumed", principal_point_at_centre=True,
        note="unit test",
    )


# ---------------------------------------------------------------- refusals


def test_assumed_without_intrinsics_raises():
    z, _, _ = synthetic_plane()
    with pytest.raises(MissingIntrinsicsError):
        depth_to_cloud(z, None, mode="assumed")


def test_assumed_rejects_model_estimated_intrinsics():
    """Model intrinsics are self-consistent with the depth, not measured.
    Laundering them through 'assumed' would overclaim."""
    z, _, _ = synthetic_plane()
    K = Intrinsics.from_focal_px(
        F, W, H, provenance="model_estimated", principal_point_at_centre=True
    )
    with pytest.raises(ValueError):
        depth_to_cloud(z, K, mode="assumed")


def test_scale_free_with_bare_array_and_no_camera_raises():
    """f changes the *shape* of the reconstruction; a similarity transform
    cannot absorb it, so scale_free cannot conjure one either."""
    z, _, _ = synthetic_plane()
    with pytest.raises(MissingIntrinsicsError):
        depth_to_cloud(z, None, mode="scale_free")


def test_no_default_focal_length_anywhere_in_the_module():
    """Grep-level guard against someone adding a convenient default later."""
    src = (Path(__file__).resolve().parent / "depth_to_cloud.py").read_text()
    for bad in ("f=1000", "fx=1000", "focal = 3005", "f = 3005", "DEFAULT_F"):
        assert bad not in src, f"a default camera crept in: {bad}"


def test_bad_mode_raises():
    z, _, _ = synthetic_plane()
    with pytest.raises(ValueError):
        depth_to_cloud(z, hand_K(), mode="metric")  # type: ignore[arg-type]


def test_intrinsics_requires_known_provenance():
    with pytest.raises(ValueError):
        Intrinsics(F, F, 1, 1, W, H, provenance="vibes")


def test_principal_point_assumption_is_explicit():
    with pytest.raises(ValueError):
        Intrinsics.from_focal_px(
            F, W, H, provenance="assumed", principal_point_at_centre=False
        )


# ---------------------------------------------------------------- geometry


def test_assumed_recovers_the_plane_exactly():
    z, n, d = synthetic_plane()
    cloud = depth_to_cloud(z, hand_K(), mode="assumed")
    assert len(cloud) == H * W
    resid = cloud.xyz @ n - d
    assert np.abs(resid).max() < 1e-9


def test_scale_free_is_the_same_shape_up_to_a_similarity():
    """The whole claim of scale_free: identical geometry, rescaled."""
    z, n, d = synthetic_plane()
    a = depth_to_cloud(z, hand_K(), mode="assumed")
    s = depth_to_cloud(z, hand_K(), mode="scale_free")
    assert s.normaliser == pytest.approx(float(np.median(z)))
    assert np.allclose(s.xyz * s.normaliser, a.xyz, atol=1e-9)
    # and the plane is still a plane, at the rescaled offset
    resid = s.xyz @ n - d / s.normaliser
    assert np.abs(resid).max() < 1e-9


def test_focal_length_changes_shape_not_just_scale():
    """The premise behind keeping f explicit. If halving f were absorbable by a
    similarity transform there would be no reason to demand intrinsics."""
    z, _, _ = synthetic_plane()
    k1 = hand_K()
    k2 = Intrinsics.from_focal_px(
        F / 2, W, H, provenance="assumed", principal_point_at_centre=True
    )
    c1 = depth_to_cloud(z, k1, mode="scale_free").xyz
    c2 = depth_to_cloud(z, k2, mode="scale_free").xyz
    # best single scale relating the two clouds, then the residual it leaves
    s = float((c1 * c2).sum() / (c1 * c1).sum())
    rel = np.linalg.norm(c2 - s * c1) / np.linalg.norm(c2)
    assert rel > 0.05, "halving f should not be absorbable by a scale factor"


def test_z_depth_not_ray_length():
    """A fronto-parallel plane must come back flat in z. If depth were ray
    length, z would fall off toward the image corners."""
    z = np.full((H, W), 3.0)
    cloud = depth_to_cloud(z, hand_K(), mode="assumed")
    assert np.allclose(cloud.xyz[:, 2], 3.0)


def test_pixel_convention_matches_da3():
    """Integer pixel centres, no +0.5 — the same grid DA3 unprojects on."""
    z = np.ones((H, W))
    k = hand_K()
    cloud = depth_to_cloud(z, k, mode="assumed")
    ras = cloud.as_raster((H, W))
    r, c = 7, 11
    assert ras[r, c, 0] == pytest.approx((c - k.cx) / k.fx)
    assert ras[r, c, 1] == pytest.approx((r - k.cy) / k.fy)


def test_intrinsics_rescaled_when_raster_size_differs():
    z, n, d = synthetic_plane()
    big = Intrinsics.from_focal_px(
        F * 4, W * 4, H * 4, provenance="assumed", principal_point_at_centre=True
    )
    cloud = depth_to_cloud(z, big, mode="assumed")
    assert cloud.intrinsics.fx == pytest.approx(F)
    assert np.abs(cloud.xyz @ n - d).max() < 1e-9


# ---------------------------------------------------------------- masking


def test_mask_and_confidence_filtering():
    z, _, _ = synthetic_plane()
    mask = np.zeros((H, W), bool)
    mask[:10, :10] = True
    assert len(depth_to_cloud(z, hand_K(), "assumed", mask=mask)) == 100

    conf = np.zeros((H, W))
    conf[:5, :] = 1.0
    assert len(depth_to_cloud(z, hand_K(), "assumed", conf=conf, conf_min=0.5)) == 5 * W


def test_nonfinite_and_nonpositive_depth_is_dropped():
    z, _, _ = synthetic_plane()
    z = z.copy()
    z[0, 0] = np.nan
    z[0, 1] = 0.0
    z[0, 2] = -1.0
    assert len(depth_to_cloud(z, hand_K(), "assumed")) == H * W - 3


def test_subsample():
    z, _, _ = synthetic_plane()
    c = depth_to_cloud(z, hand_K(), "assumed", subsample=3)
    assert len(c) == len(range(0, H, 3)) * len(range(0, W, 3))


# ---------------------------------------------------------------- flags & io


def test_scale_confidence_flags():
    z, _, _ = synthetic_plane()
    assert depth_to_cloud(z, hand_K(), "assumed").scale_confidence == ASSUMED_SCALE
    assert depth_to_cloud(z, hand_K(), "scale_free").scale_confidence == SCALE_FREE


def test_cloud_rejects_an_unknown_scale_flag():
    with pytest.raises(ScaleConfidenceError):
        PointCloud(
            xyz=np.zeros((1, 3)),
            pixel_rc=np.zeros((1, 2), np.int32),
            scale_confidence="probably_fine",
            units="m",
            mode="assumed",
            intrinsics=hand_K(),
            normaliser=None,
        )


def test_saved_artifact_carries_the_flag(tmp_path):
    z, _, _ = synthetic_plane()
    cloud = depth_to_cloud(z, hand_K(), "scale_free")
    p = save_cloud(cloud, tmp_path / "cloud")
    side = json.loads(p.with_suffix(".json").read_text())
    assert side["scale_confidence"] == SCALE_FREE
    assert "rdu" in side["units"]
    assert side["intrinsics"]["provenance"] == "assumed"
    assert np.load(p.with_suffix(".npy")).shape == (H * W, 3)


def test_depth_product_supplies_model_intrinsics_to_scale_free():
    z, _, _ = synthetic_plane()
    K = np.array([[F, 0, (W - 1) / 2], [0, F, (H - 1) / 2], [0, 0, 1.0]])
    prod = DepthProduct(
        depth=z,
        provenance={"output_semantics": {"is_metric": 0}, "model": {"hf_repo": "x"}},
        model_intrinsics=Intrinsics.from_K(K, W, H, provenance="model_estimated"),
    )
    cloud = depth_to_cloud(prod, mode="scale_free")
    assert cloud.scale_confidence == SCALE_FREE
    assert cloud.provenance["intrinsics_provenance"] == "model_estimated"
    # ...and the same product still refuses 'assumed'
    with pytest.raises(MissingIntrinsicsError):
        depth_to_cloud(prod, None, mode="assumed")


# ---------------------------------------------------------------- real data


REAL = Path(__file__).resolve().parent / "depth" / "da3-large_res1344"


@pytest.mark.skipif(not REAL.exists(), reason="run da3_infer.py first")
def test_round_trip_on_the_real_depth_product():
    prod = load_depth_product(REAL)
    cloud = depth_to_cloud(prod, mode="scale_free", subsample=8)
    assert cloud.scale_confidence == SCALE_FREE
    assert len(cloud) > 1000
    assert np.isfinite(cloud.xyz).all()
    assert cloud.intrinsics.provenance == "model_estimated"
    # camera looks into +z, everything in front of it
    assert (cloud.xyz[:, 2] > 0).all()
