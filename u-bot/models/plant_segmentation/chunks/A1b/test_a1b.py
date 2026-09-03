"""A1b tests.

Most of these are assertions about a *refusal* or about an *invariance*, which
is what this chunk is made of. The load-bearing ones are:

* the algebra: changing `f` is exactly `diag(s, s, 1)` on the cloud;
* the degeneracy: planarity cannot pick `f`, and the synthetic control with a
  known `f` is where that is proved rather than argued;
* the honesty: nothing A1b writes can present an assumed camera as measured, or
  an unresolved scale as resolved.

    chunks/A1/.venv/bin/python -m pytest chunks/A1b/test_a1b.py -q
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import a1b_common as CM  # noqa: E402
from a1b_common import (CALIB, DA3_F_MAX, DA3_F_MIN, F_CHOSEN, F_INITIAL,  # noqa: E402
                        RESULTS, SWEEP_F, assumed_intrinsics, equiv_mm_from_f_px,
                        f_px_from_equiv_mm, normal_at_f)
from depth_to_cloud import (ASSUMED_SCALE, Intrinsics,  # noqa: E402
                            MissingIntrinsicsError, depth_to_cloud)
from refine_focal import patch_stats, synthetic_control  # noqa: E402


# --------------------------------------------------------------------------
# the algebra
# --------------------------------------------------------------------------


def _depth(h=40, w=30, seed=3):
    rng = np.random.default_rng(seed)
    v, u = np.mgrid[0:h, 0:w].astype(float)
    return 1.0 + 0.3 * np.sin(u / 5) * np.cos(v / 7) + 0.02 * rng.standard_normal((h, w))


def test_changing_f_is_exactly_an_axial_scaling_of_the_cloud():
    """The one fact the whole chunk rests on."""
    d = _depth()
    h, w = d.shape
    f0, f1 = 300.0, 777.0
    c0 = depth_to_cloud(d, Intrinsics.from_focal_px(
        f0, w, h, "assumed", principal_point_at_centre=True), "assumed")
    c1 = depth_to_cloud(d, Intrinsics.from_focal_px(
        f1, w, h, "assumed", principal_point_at_centre=True), "assumed")
    s = f0 / f1
    pred = c0.xyz * np.array([s, s, 1.0])
    assert np.allclose(pred, c1.xyz, rtol=0, atol=1e-12)


def test_a_plane_stays_a_plane_at_every_focal_length():
    """Linear maps take planes to planes, so planarity residual is zero at every
    f whenever it is zero at one. This is why the refinement is degenerate."""
    h, w = 60, 45
    cx, cy = (w - 1) / 2.0, (h - 1) / 2.0
    v, u = np.mgrid[0:h, 0:w].astype(float)
    f = 100.0
    n = np.array([0.3, 0.5, -1.0]) / np.linalg.norm([0.3, 0.5, -1.0])
    z = -1.0 / (n[0] * (u - cx) / f + n[1] * (v - cy) / f + n[2])
    z = z / np.median(z)
    band = np.ones((h, w), bool)
    for f_native in (500.0, 1502.0, 3005.0, 4453.0, 20000.0, 60000.0):
        rms, _, _, _ = patch_stats(z, band, f_native, win=21)
        assert float(np.sqrt(np.mean(rms ** 2))) < 1e-12, f_native


def test_the_planarity_refinement_cannot_recover_a_focal_length_it_was_given():
    """The control that settles the degeneracy without reference to DA3.

    A locally-planar rough surface is rendered through a KNOWN camera and the
    estimator is asked for `f` back. It returns the edge of the search grid, at
    every ground truth tried. If this test ever *fails* — i.e. the estimator
    starts recovering the answer — the chunk's central finding is wrong and the
    refinement should be reinstated.
    """
    grid = np.geomspace(400.0, 60000.0, 25)
    for f_true in (1502.0, 3005.0, 6009.0):
        r = synthetic_control(f_true=f_true, f_grid=grid)
        got = r["argmin_planarity_rms"]["f_native_px"]
        assert r["argmin_planarity_rms"]["at_grid_edge"], (f_true, got)
        assert abs(got - f_true) / f_true > 0.25, (f_true, got)


def test_closed_form_normal_matches_a_refit():
    """`normal_at_f` against an actual plane refit of the rescaled cloud."""
    rng = np.random.default_rng(11)
    P = rng.standard_normal((4000, 3))
    n_true = np.array([0.2, -0.5, 1.0])
    n_true /= np.linalg.norm(n_true)
    P -= np.outer(P @ n_true, n_true)          # exactly planar
    P[:, 2] += 3.0
    f0, f1 = 1000.0, 2500.0
    Q = P * np.array([f0 / f1, f0 / f1, 1.0])
    _, _, Vt = np.linalg.svd(Q - Q.mean(0), full_matrices=False)
    refit = Vt[2] / np.linalg.norm(Vt[2])
    pred = normal_at_f(n_true, f0, f1)
    assert CM.angle_deg(pred, refit) < 1e-8


# --------------------------------------------------------------------------
# the camera A1b ships
# --------------------------------------------------------------------------


def test_focal_conversion_round_trips_and_the_default_is_26mm():
    assert f_px_from_equiv_mm(26.0) == pytest.approx(3005, abs=1.0)
    assert equiv_mm_from_f_px(F_INITIAL) == pytest.approx(26.0, abs=0.05)
    # the roadmap's sanity check: f is close to the image width
    assert 0.9 < F_INITIAL / CM.NATIVE_W < 1.1


def test_assumed_intrinsics_are_grid_consistent():
    a = assumed_intrinsics(F_CHOSEN, 3000, 4000)
    b = assumed_intrinsics(F_CHOSEN, 1008, 1344)
    c = a.scaled_to(1008, 1344)
    assert b.fx == pytest.approx(c.fx, rel=1e-12)
    assert b.cx == pytest.approx(c.cx, rel=1e-9)
    assert b.cy == pytest.approx(c.cy, rel=1e-9)


def test_the_sweep_covers_da3s_own_band():
    """A1's FINDINGS: the roadmap's five values step straight over 4159-4695."""
    assert min(SWEEP_F) <= 1502 and max(SWEEP_F) >= 6009
    inside = [f for f in SWEEP_F if DA3_F_MIN <= f <= DA3_F_MAX]
    assert len(inside) >= 3, SWEEP_F
    for f in (1502.0, 2774.0, 3005.0, 3236.0, 6009.0):   # the roadmap's own set
        assert f in SWEEP_F


def test_assumed_mode_still_refuses_a_missing_or_model_estimated_camera():
    """A1's refusals must survive A1b, or the whole point is lost."""
    d = _depth()
    with pytest.raises(MissingIntrinsicsError):
        depth_to_cloud(d, None, "assumed")
    model = Intrinsics.from_focal_px(500, 30, 40, "model_estimated",
                                     principal_point_at_centre=True)
    with pytest.raises(ValueError):
        depth_to_cloud(d, model, "assumed")


def test_a1b_camera_is_flagged_assumed_scale_when_used_metrically():
    d = _depth()
    h, w = d.shape
    intr = assumed_intrinsics(F_CHOSEN, w, h, provenance="assumed+refined")
    cloud = depth_to_cloud(d, intr, "assumed")
    assert cloud.scale_confidence == ASSUMED_SCALE
    assert "ASSUMED" in cloud.units
    assert cloud.intrinsics.provenance == "assumed+refined"


# --------------------------------------------------------------------------
# the artifacts
# --------------------------------------------------------------------------

CALIB_FILE = CALIB / "plants_assumed.json"


@pytest.mark.skipif(not CALIB_FILE.exists(), reason="run make_calib.py first")
def test_calib_file_is_complete_and_honest():
    doc = json.loads(CALIB_FILE.read_text())
    assert doc["provenance"] == "assumed+refined"
    assert doc["model"]["type"] == "pinhole"
    assert doc["intrinsics"]["fx"] == doc["intrinsics"]["fy"]
    assert doc["absolute_scale"]["status"] == "UNRESOLVED"
    # the refinement curve is present and says what it found
    curve = doc["planarity_refinement_curve"]["primary_raster_res1344"]
    assert len(curve) > 20
    assert "DEGENERATE" in doc["provenance_detail"]["refinement_outcome"]
    # and the file cannot be read as a metric claim
    blob = json.dumps(doc).lower()
    for word in ("metres", "meters", " cm", "millimetre"):
        if word in blob:
            assert "unresolved" in blob


@pytest.mark.skipif(not CALIB_FILE.exists(), reason="run make_calib.py first")
def test_calib_grids_agree_with_the_constructor():
    doc = json.loads(CALIB_FILE.read_text())
    for name, g in doc["usage"]["on_other_grids"].items():
        intr = assumed_intrinsics(doc["intrinsics"]["f_px_at_3000x4000"],
                                  g["width"], g["height"])
        assert intr.fx == pytest.approx(g["fx"], rel=1e-12), name
        assert intr.cx == pytest.approx(g["cx"], rel=1e-12), name


REF = RESULTS / "focal_refinement.json"


@pytest.mark.skipif(not REF.exists(), reason="run refine_focal.py first")
def test_recorded_refinement_says_degenerate():
    d = json.loads(REF.read_text())
    for name, p in d["products"].items():
        assert p["argmin_planarity_rms"]["at_grid_edge"], name
    for k, v in d["verdict"]["synthetic_recovery"].items():
        assert not v["recovered"], k
    for row in d["control_exact_plane"]["rows"]:
        assert row["planarity_rms_rdu"] < 1e-12


SENS = RESULTS / "sensitivity.json"


@pytest.mark.skipif(not SENS.exists(), reason="run the sweep and aggregate.py")
def test_the_reference_row_reproduces_shipped_phase_A():
    """A1b's `manifest` row uses A1's own camera, so it must land on the numbers
    already in RESULTS.md. If it does not, the harness is wrong, not the sweep."""
    d = json.loads(SENS.read_text())
    for k, v in d["reference_row_reproduces_shipped_phase_A"].items():
        assert v["A1b_manifest_row"] is not None, k
        assert v["relative_difference"] is not None, k
        assert v["relative_difference"] < 0.02, (k, v)


@pytest.mark.skipif(not SENS.exists(), reason="run the sweep and aggregate.py")
def test_the_three_A4_verdicts_are_reported_at_every_f():
    d = json.loads(SENS.read_text())
    for col in ("A4 split squash one component", "A4 split clover separate",
                "A4 split grass absorbed"):
        by = d["columns"][col]["by_tag"]
        for t in d["swept_tags_in_order"]:
            assert by.get(t) is not None, (col, t)


@pytest.mark.skipif(not SENS.exists(), reason="run the sweep and aggregate.py")
def test_no_absolute_distance_escapes_without_a_flag():
    d = json.loads(SENS.read_text())
    assert "rdu" in d["scale_confidence"]
    assert "no metric claim" in d["scale_confidence"]
