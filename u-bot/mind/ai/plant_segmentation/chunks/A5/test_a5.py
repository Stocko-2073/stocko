"""A5 — tests for the honest-status logic.

    ../A3/.venv/bin/python -m pytest test_a5.py -q

Most of these run against a *synthetic* scene with known geometry, because the
property under test is "does this code refuse to guess", and the only way to
test a refusal is to build the case that should trigger it. The last group runs
against the shipped products so a regression in the real numbers is caught too.
"""
from __future__ import annotations

import ast
import json
import math
import os
import sys

import numpy as np
import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import contact_points as cp  # noqa: E402
from a5_api import load_a5  # noqa: E402
from a5_common import Scene, local_normals, ray_directions  # noqa: E402
from depth_to_cloud import Intrinsics  # noqa: E402

SIGMA = 5.469617460760942e-03          # A2's datum roughness, this scene


# --------------------------------------------------------------- synthetic
def synthetic(height_field, valid=None, coverage=None, ground=None,
              sigma_datum=SIGMA, h=120, w=120, datum_depth=1.0,
              height_sigma=7.0e-3):
    """A flat datum at `datum_depth` with `height_field` of material above it.

    The material's depth is set so that its height above the datum, measured the
    way A2 measures it, is exactly `height_field`. Working backwards through the
    same geometry the real Scene uses is what makes the test meaningful.
    """
    intr = Intrinsics(fx=1000.0, fy=1000.0, cx=w / 2, cy=h / 2, width=w, height=h,
                      provenance="assumed", note="synthetic test camera")
    dirs = ray_directions(h, w, intr)
    soil = np.full((h, w), datum_depth, np.float64)
    S = dirs * soil[..., None]
    n = np.array([0.0, 0.0, -1.0])
    N = local_normals(S, n)
    # A2 measures height as (P - S)·N with P on the pixel's own ray, so the
    # depth that puts a pixel exactly `height_field` above the datum is
    # soil + height/(dirs·N). Solving it exactly here is what makes the tilt
    # test a real test rather than a small-angle approximation.
    depth = soil + height_field / np.einsum("hwc,hwc->hw", dirs, N)
    P = dirs * depth[..., None]
    height = np.einsum("hwc,hwc->hw", P - S, N)
    return Scene(depth_rdu=depth, dirs=dirs, P=P, S=S, N=N, height=height,
                 height_sigma=np.full((h, w), height_sigma, np.float64),
                 valid=np.ones((h, w), bool) if valid is None else valid,
                 coverage=(np.zeros((h, w), np.uint8) if coverage is None
                           else coverage),
                 ground=(np.zeros((h, w), bool) if ground is None else ground),
                 sigma_datum=sigma_datum, intr=intr, plane_normal=n,
                 a2_manifest={"DATUM": "synthetic flat datum",
                              "key_numbers": {"fit_scale_px": 40}},
                 a1_manifest={})


def vertical_stem(h=120, w=120, x=60, y0=40, y1=90, top=0.20, bottom=0.0,
                  width=3):
    """A stem descending from `top` to `bottom` rdu above the datum."""
    hf = np.zeros((h, w))
    labels = np.zeros((h, w), np.int32)
    for i, y in enumerate(range(y0, y1)):
        z = top + (bottom - top) * i / max(y1 - y0 - 1, 1)
        hf[y, x - width // 2:x + width // 2 + 1] = z
        labels[y, x - width // 2:x + width // 2 + 1] = 1
    return hf, labels


def run(scene, labels, material=None, **kw):
    material = (np.full(labels.shape, cp.STEM_CLASS, np.uint8)
                if material is None else material)
    return cp.contact_points(scene, labels, material, None, **kw)


# ------------------------------------------------------------------- tests
def test_material_reaching_the_datum_is_observed():
    hf, labels = vertical_stem(bottom=0.0)
    c = run(synthetic(hf), labels)[0]
    assert c.status == "observed"
    assert c.point is not None
    assert c.extrapolation_distance_rdu == 0.0
    assert abs(c.height_at_base_rdu) <= 3 * math.hypot(SIGMA, 7.0e-3)


def test_a_stem_stopping_above_the_datum_is_extrapolated_with_its_distance():
    gap = 8 * SIGMA
    hf, labels = vertical_stem(top=0.20, bottom=gap)
    c = run(synthetic(hf), labels)[0]
    assert c.status == "extrapolated"
    assert c.point is not None
    # the stem is not vertical in 3-D (it leans across the image), so the
    # distance along its own axis is at least the height gap it had to cross
    assert c.extrapolation_distance_rdu >= gap * 0.99
    assert c.extrapolation_distance_sigma == pytest.approx(
        c.extrapolation_distance_rdu / SIGMA)
    assert 0.0 < c.confidence <= 1.0


def test_a_stem_stopping_too_far_above_the_datum_is_occluded_and_gets_no_point():
    hf, labels = vertical_stem(top=0.9, bottom=0.5)      # ~91 sigma up
    c = run(synthetic(hf), labels)[0]
    assert c.status == "occluded"
    assert c.point is None, "R4: an occluded component must not receive a point"
    assert "tool budget" in c.reason
    # the observation is still emitted, because it *is* an observation
    assert c.lowest_visible_point is not None


def test_confidence_falls_as_the_extrapolation_grows():
    conf, dist = [], []
    for gap in (6 * SIGMA, 10 * SIGMA, 14 * SIGMA, 18 * SIGMA):
        hf, labels = vertical_stem(top=0.25, bottom=gap)
        c = run(synthetic(hf), labels)[0]
        assert c.status == "extrapolated"
        conf.append(c.confidence)
        dist.append(c.extrapolation_distance_rdu)
    assert dist == sorted(dist)
    assert conf == sorted(conf, reverse=True), conf


def test_raising_the_tool_budget_never_creates_an_observed_point():
    """The one (b) placeholder must not be able to manufacture the status that
    R2 lets a removal through on."""
    hf, labels = vertical_stem(top=0.30, bottom=0.15)
    seen = set()
    for b in (2, 20, 200, 2000):
        c = run(synthetic(hf), labels, max_extrapolation_sigma=b)[0]
        seen.add(c.status)
    assert "observed" not in seen
    assert seen <= {"extrapolated", "occluded"}


def test_a_blob_has_no_axis_and_is_refused():
    """An isotropic patch has no direction to continue. It must not get one."""
    h = w = 120
    hf = np.zeros((h, w))
    labels = np.zeros((h, w), np.int32)
    yy, xx = np.mgrid[0:h, 0:w]
    blob = (yy - 60) ** 2 + (xx - 60) ** 2 < 15 ** 2
    hf[blob] = 0.06                      # 11 sigma up, flat
    labels[blob] = 1
    c = run(synthetic(hf), labels)[0]
    assert c.point is None
    assert c.status == "occluded"
    assert c.axis_half_angle_deg is None or c.axis_half_angle_deg > 30


def test_material_below_the_datum_is_refused_not_reported_as_contact():
    """Nothing lies under the ground. Material well below the fitted surface is
    the surface being wrong, and A5 must say so rather than snapping a point."""
    hf, labels = vertical_stem(top=0.0, bottom=-0.10)
    c = run(synthetic(hf), labels)[0]
    assert c.status == "occluded"
    assert c.point is None
    assert "BELOW" in c.reason


def test_a_component_over_an_untrusted_datum_gets_no_point():
    hf, labels = vertical_stem(bottom=0.0)
    scene = synthetic(hf, valid=np.zeros((120, 120), bool))
    c = run(scene, labels)[0]
    assert c.status == "occluded"
    assert c.point is None
    assert c.lowest_visible_point is None


def test_an_interpolated_datum_is_never_arm_admissible():
    hf, labels = vertical_stem(bottom=0.0)
    scene = synthetic(hf, coverage=np.ones((120, 120), np.uint8))
    c = run(scene, labels)[0]
    assert c.status == "observed"
    assert c.datum_coverage == "interpolated"
    assert not c.arm_admissible, "R2: an interpolated datum is not an observation"


def test_a_component_that_leaves_the_frame_is_never_arm_admissible():
    hf, labels = vertical_stem(bottom=0.0)
    edges = [{"kind": "leaves_frame", "components": [1, None],
              "already_connected": False}]
    material = np.full(labels.shape, cp.STEM_CLASS, np.uint8)
    c = cp.contact_points(synthetic(hf), labels, material, edges)[0]
    assert c.status == "observed"
    assert c.leaves_frame and c.extent_uncertain
    assert not c.arm_admissible


def test_lowest_visible_point_is_a_real_material_pixel():
    hf, labels = vertical_stem(top=0.30, bottom=0.20)
    scene = synthetic(hf)
    c = run(scene, labels)[0]
    u, v = c.lowest_visible_point["depth_grid_xy"]
    assert labels[int(round(v)), int(round(u))] == 1


def test_the_stem_point_is_absent_rather_than_substituted():
    """A component with no stem material must report `null`, not the nearest
    non-stem point relabelled."""
    hf, labels = vertical_stem(bottom=0.0)
    material = np.full(labels.shape, 4, np.uint8)      # broadleaf_weed
    c = run(synthetic(hf), labels, material=material)[0]
    assert c.lowest_visible_stem_point is None
    assert "no `squash_petiole`" in c.material["stem_note"]
    assert c.lowest_visible_point is not None


def test_two_components_are_decided_independently():
    hf1, l1 = vertical_stem(x=30, bottom=0.0)
    hf2, l2 = vertical_stem(x=90, top=0.9, bottom=0.5)
    hf = hf1 + hf2
    labels = l1 + 2 * l2
    cs = {c.component: c for c in run(synthetic(hf), labels)}
    assert cs[1].status == "observed"
    assert cs[2].status == "occluded"


def test_a_steeply_banked_bed_is_handled_the_same_way_as_a_level_one():
    """A5 must not know which way is down. A2's surface is oriented toward the
    camera, never toward gravity, and A5 only ever asks "how far is this
    material from *that* surface". Tilting the ground by ~60° must not change a
    status, and must not make the march fail.

    The extrapolation *distance* is not expected to be invariant, and that is
    the point: a steeply banked ground really is further along the stem's own
    axis. What must not happen is a different verdict, or a silent fall-back to
    a vertical drop.
    """
    hf, labels = vertical_stem(top=0.25, bottom=8 * SIGMA)
    base = run(synthetic(hf), labels)[0]
    tilt = np.linspace(-0.12, 0.12, 120)[None, :] + np.zeros((120, 1))
    tilted = run(synthetic(hf, datum_depth=1.0 + tilt), labels)[0]
    assert base.status == tilted.status == "extrapolated"
    assert base.height_at_base_sigma == pytest.approx(
        tilted.height_at_base_sigma, rel=1e-6)
    assert tilted.extrapolation_distance_rdu > 0
    assert tilted.point is not None


def test_scale_invariance_of_the_status():
    """Everything is scale-free: scaling depth and the datum together is a
    similarity transform and must not move a decision."""
    hf, labels = vertical_stem(top=0.25, bottom=8 * SIGMA)
    a = run(synthetic(hf), labels)[0]
    b = run(synthetic(hf * 2, datum_depth=2.0, sigma_datum=SIGMA * 2,
                      height_sigma=1.4e-2), labels)[0]
    assert a.status == b.status
    assert b.extrapolation_distance_sigma == pytest.approx(
        a.extrapolation_distance_sigma, rel=0.05)


# ------------------------------------------------------- constants and R1
ALLOWED_CONSTANTS = {
    "GROUND_BAND_K": "(c) convention, inherited from A2",
    "BASAL_BAND_K": "(c) convention, one combined datum sigma",
    "MEDIAN_WINDOW": "(a) instrument, smallest odd window",
    "MIN_MEDIAN_SUPPORT": "(a) instrument, a 1-px-wide stem's own support",
    "MIN_AXIS_POINTS": "(a) instrument, 3x3 = smallest support for a 3-D line",
    "MAX_EXTRAPOLATION_SIGMA": "(b) tool geometry, placeholder awaiting C3",
    "MARCH_CEILING_RDU": "reporting ceiling, not a threshold",
    "STEM_CLASS": "A0 class id, not a measurement",
    "GT_W": "A0 grid", "GT_H": "A0 grid",
}


def test_every_module_level_constant_is_registered():
    for mod in ("contact_points.py", "a5_common.py"):
        tree = ast.parse(open(os.path.join(HERE, mod)).read())
        for node in tree.body:
            if not isinstance(node, ast.Assign):
                continue
            for t in node.targets:
                if not isinstance(t, ast.Name) or not t.id.isupper():
                    continue
                if isinstance(node.value, (ast.Constant,)) and isinstance(
                        node.value.value, (int, float)) and not isinstance(
                        node.value.value, bool):
                    assert t.id in ALLOWED_CONSTANTS, (
                        f"{mod}: {t.id} is a numeric constant with no R1 "
                        "category. Register it in CONSTANTS.md and add it here.")


def test_there_is_no_spacing_or_agronomic_constant_in_the_code_path():
    """R1: no constant may encode a belief about how gardens are arranged."""
    banned = ("eps", "radius", "max_gap", "search_radius", "spacing",
              "plant_spacing", "_cm", "centimet", "millimet", "metre", "meter")
    for mod in ("contact_points.py", "a5_common.py", "a5_api.py"):
        src = open(os.path.join(HERE, mod)).read()
        tree = ast.parse(src)
        for node in ast.walk(tree):          # strip docstrings and comments
            if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant) \
                    and isinstance(node.value.value, str):
                node.value.value = ""
        code = ast.unparse(tree).lower()
        for b in banned:
            assert b not in code, f"{mod} contains `{b}` in executable code"


# ------------------------------------------------------ shipped products
@pytest.mark.parametrize("policy", ["split", "merge", "gt_instances"])
def test_no_shipped_component_silently_receives_a_fabricated_point(policy):
    a5 = load_a5(policy=policy)
    for c in a5.components:
        if c.raw["status"] == "occluded":
            assert c.raw["point"] is None, c.raw["component"]
        else:
            assert c.raw["point"] is not None, c.raw["component"]
            assert c.raw["reason"]


@pytest.mark.parametrize("policy", ["split", "merge"])
def test_every_shipped_record_carries_the_datum_caveat_and_the_scale_flag(policy):
    a5 = load_a5(policy=policy)
    assert a5.scale_confidence == "scale_free"
    assert "STRAW" in a5.datum
    assert "NOT" in a5.product_target or "not" in a5.product_target


def test_admissible_is_a_strict_subset_of_observed():
    for policy in ("split", "merge"):
        a5 = load_a5(policy=policy)
        adm = a5.admissible()
        assert all(c.raw["status"] == "observed" for c in adm)
        assert all(c.raw["lowest_visible_point"]["datum_coverage"] == "observed"
                   for c in adm)
        assert all(not c.raw["leaves_frame"] for c in adm)


def test_no_extrapolated_point_is_arm_admissible():
    """The gate A8 has to prove: a high-confidence extrapolation is still not a
    licence to cut."""
    for policy in ("split", "merge"):
        for c in load_a5(policy=policy).components:
            if c.raw["status"] == "extrapolated":
                assert not c.raw["arm_admissible"]


def test_the_roadmaps_visible_contact_metric_is_empty_for_this_image():
    gt = json.load(open(os.path.join(HERE, "..", "..", "groundtruth",
                                     "plants_contacts.json")))
    assert sum(1 for e in gt["instances"] if e["status"] == "visible") == 0
    d = json.load(open(os.path.join(HERE, "results", "diagnostics.json")))
    for k in ("split", "merge"):
        assert d["a0_eval_contacts"][k]["visible"]["n"] == 0
        assert d["gt_consistency"][k]["n_visible_gt_points"] == 0
