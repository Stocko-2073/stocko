"""A6 — tests.

    cd chunks/A6 && ../A3/.venv/bin/python -m pytest test_a6.py -q

Three groups:

* **unit** — the geometry of ``is_inside``, on a hand-built volume where the
  right answer is known exactly. No data, no I/O, milliseconds.
* **scene** — the real squash keep-out, including the point the roadmap asks
  for specifically: *points near the vines rather than only near the crown*.
* **discipline** — the properties that make the chunk auditable: one named
  length constant, no spacing parameter, every module-level number registered.
"""
from __future__ import annotations

import ast
import os
import sys

import numpy as np
import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from a6_common import (DatumFrame, gt_rc_to_depth_rc, load_crop_component,  # noqa: E402
                       load_gt, load_scene)
from keepout import (CLEARANCE_SWEEP_RDU, DEFAULT_CLEARANCE_RDU, INSIDE,  # noqa: E402
                     OUTSIDE, TIER_EMPTY, TIER_OBSERVED, TIER_UNSEEN, UNKNOWN,
                     KeepOutVolume, build_keepout, load_keepout)

#: Coarse enough that the whole suite fits in memory and runs in ~30 s. Every
#: test that depends on a *number* rather than a *property* uses the shipped
#: product from disk instead.
TEST_CELL = 7.0e-3


# ---------------------------------------------------------------------------
# unit — a hand-built volume, exact answers
# ---------------------------------------------------------------------------


def _toy(cell=0.1, n=9):
    """A single occupied voxel at the centre of an otherwise empty grid, in a
    frame that is the identity. Distances are then trivially checkable."""
    from scipy import ndimage
    tier = np.zeros((n, n, n), np.uint8)
    tier[n // 2, n // 2, n // 2] = TIER_OBSERVED
    dist = ndimage.distance_transform_edt(tier == TIER_EMPTY,
                                          sampling=(cell,) * 3)
    frame = DatumFrame(e1=np.array([1.0, 0, 0]), e2=np.array([0, 1.0, 0]),
                       n=np.array([0, 0, 1.0]), offset=0.0)
    return KeepOutVolume(
        frame=frame, cell=cell, origin_uvw=np.zeros(3), tier=tier, dist=dist,
        clearance_rdu=0.0, max_clearance_rdu=cell * 3, occupancy="column",
        include_unseen=True, frame_open=False,
        provenance={"a2": {"datum_roughness_sigma_rdu": 1.0}})


def test_the_material_itself_is_always_inside():
    v = _toy()
    centre = np.array([4, 4, 4]) * v.cell
    assert v.is_inside(centre, clearance=0.0)


def test_distance_is_the_real_euclidean_distance():
    v = _toy()
    centre = np.array([4, 4, 4]) * v.cell
    for offset, expect in [((2, 0, 0), 0.2), ((0, 3, 0), 0.3), ((1, 1, 0), 0.1 * 2 ** 0.5)]:
        q = centre + np.array(offset) * v.cell
        assert v.distance_to_material(q[None, :])[0] == pytest.approx(expect, rel=1e-9)


def test_is_inside_is_monotone_in_clearance():
    v = _toy()
    q = np.random.default_rng(0).uniform(0, 0.8, size=(400, 3))
    prev = np.zeros(len(q), bool)
    for c in (0.0, 0.05, 0.1, 0.2, 0.3):
        now = v.is_inside(q, clearance=c)
        assert np.all(now | ~prev), "growing the clearance un-protected a point"
        prev = now


def test_conservative_is_a_superset_of_exact():
    v = _toy()
    q = np.random.default_rng(1).uniform(0, 0.8, size=(400, 3))
    a = v.is_inside(q, clearance=0.15, conservative=True)
    b = v.is_inside(q, clearance=0.15, conservative=False)
    assert np.all(a | ~b)
    assert a.sum() > b.sum(), "the R2 bracket should protect strictly more"


def test_scalar_and_vector_calls_agree():
    v = _toy()
    q = np.random.default_rng(2).uniform(0, 0.8, size=(50, 3))
    batch = v.is_inside(q, clearance=0.15)
    one = np.array([v.is_inside(p, clearance=0.15) for p in q])
    assert np.array_equal(batch, one)
    assert isinstance(v.is_inside(q[0], clearance=0.15), bool)


def test_a_clearance_beyond_the_padding_is_refused_not_clipped():
    v = _toy()
    with pytest.raises(ValueError, match="exceeds the padding"):
        v.is_inside(np.zeros(3), clearance=v.max_clearance_rdu * 2)


def test_far_away_points_are_outside():
    v = _toy()
    assert not v.is_inside(np.array([-50.0, -50.0, -50.0]),
                           clearance=v.max_clearance_rdu)


# ---------------------------------------------------------------------------
# scene — the real squash
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def scene():
    return load_scene()


@pytest.fixture(scope="module")
def gt():
    return load_gt()


@pytest.fixture(scope="module")
def crop(gt):
    return load_crop_component("merge", gt=gt)


@pytest.fixture(scope="module")
def vol(scene, crop):
    return build_keepout(scene, crop, cell=TEST_CELL,
                         clearance=DEFAULT_CLEARANCE_RDU,
                         frame=DatumFrame.from_scene(scene))


def _gt_points(scene, gt, mask, n, seed=0):
    rows, cols = np.nonzero(mask)
    rng = np.random.default_rng(seed)
    pick = rng.choice(len(rows), size=min(n, len(rows)), replace=False)
    dr, dc = gt_rc_to_depth_rc(rows[pick], cols[pick])
    xyz = scene.xyz[dr, dc]
    return xyz[np.isfinite(xyz).all(axis=1)]


def test_crown_is_inside(scene, gt, vol):
    """A0's recorded contact point for the crop, lifted to the straw datum."""
    e = next(x for x in gt.contacts["instances"] if x["id"] == 1)
    x, y = e["point"]
    dr, dc = gt_rc_to_depth_rc(np.array([y]), np.array([x]))
    ray = scene.xyz[dr[0], dc[0]]
    p = ray / ray[2] * scene.a2.soil_depth[dr[0], dc[0]]
    assert vol.is_inside(p, clearance=DEFAULT_CLEARANCE_RDU)


def test_vines_and_petioles_are_inside_not_just_the_crown(scene, gt, vol):
    """The roadmap's specific ask. `squash_petiole` is A0's class for petioles,
    vines, peduncles and tendrils — the thin sprawling structure a crown-centred
    radius is worst at."""
    pts = _gt_points(scene, gt, gt.material == 2, 3000)
    ins = vol.is_inside(pts, clearance=DEFAULT_CLEARANCE_RDU)
    assert ins.mean() > 0.99, f"only {ins.mean():.3f} of vine material protected"


def test_the_far_vines_are_inside_where_an_equal_area_disk_misses_them(
        scene, gt, vol):
    """A radius around the crown is wrong *in both directions*, and this is the
    direction that destroys a crop: material far from the crown, protected here,
    dropped by any equal-area disk."""
    frame = vol.frame
    e = next(x for x in gt.contacts["instances"] if x["id"] == 1)
    x, y = e["point"]
    dr, dc = gt_rc_to_depth_rc(np.array([y]), np.array([x]))
    ray = scene.xyz[dr[0], dc[0]]
    crown = frame.to_uvw((ray / ray[2] * scene.a2.soil_depth[dr[0], dc[0]])[None, :])[0]

    pts = _gt_points(scene, gt, (gt.material == 1) | (gt.material == 2), 8000, seed=3)
    uvw = frame.to_uvw(pts)
    r = np.hypot(uvw[:, 0] - crown[0], uvw[:, 1] - crown[1])
    area = vol.footprint(DEFAULT_CLEARANCE_RDU).sum() * vol.cell ** 2
    r_equal = np.sqrt(area / np.pi)

    far = r > r_equal
    assert far.sum() > 100, "expected real material outside the equal-area disk"
    assert vol.is_inside(pts[far], clearance=DEFAULT_CLEARANCE_RDU).mean() > 0.99


def _probe_points(vol, n=20000, seed=11):
    """Points spread over one volume's own grid, in camera coordinates. Two
    volumes may sit on different grids, so containment is compared by querying
    the same *points*, never by comparing the two rasters element-wise."""
    rng = np.random.default_rng(seed)
    idx = rng.uniform(0, 1, size=(n, 3)) * (np.array(vol.shape) - 1)
    return vol.frame.to_xyz(vol.origin_uvw + idx * vol.cell)


def test_unresolved_edges_only_ever_add_volume(scene, crop):
    """R2/R4: material behind a link A4 refused to decide is unseen volume, not
    empty space. Including it can only grow the protected region."""
    f = DatumFrame.from_scene(scene)
    a = build_keepout(scene, crop, cell=TEST_CELL, include_unseen=False, frame=f)
    b = build_keepout(scene, crop, cell=TEST_CELL, include_unseen=True, frame=f)
    q = _probe_points(a)
    ia = a.is_inside(q, clearance=DEFAULT_CLEARANCE_RDU, unknown_is_inside=False)
    ib = b.is_inside(q, clearance=DEFAULT_CLEARANCE_RDU, unknown_is_inside=False)
    assert np.all(ib | ~ia), "including unseen material un-protected a point"
    assert ib.sum() > ia.sum()
    assert b.material_volume_rdu3() > a.material_volume_rdu3()
    assert b.material_volume_rdu3(TIER_UNSEEN) > 0
    assert a.material_volume_rdu3(TIER_UNSEEN) == 0


def test_the_column_assumption_only_ever_adds_volume(scene, crop):
    f = DatumFrame.from_scene(scene)
    shell = build_keepout(scene, crop, cell=TEST_CELL, occupancy="shell", frame=f)
    col = build_keepout(scene, crop, cell=TEST_CELL, occupancy="column", frame=f)
    q = _probe_points(shell)
    a = shell.is_inside(q, clearance=DEFAULT_CLEARANCE_RDU, unknown_is_inside=False)
    b = col.is_inside(q, clearance=DEFAULT_CLEARANCE_RDU, unknown_is_inside=False)
    assert np.all(b | ~a), "the column assumption un-protected a point"
    assert col.material_volume_rdu3() > shell.material_volume_rdu3()


def test_the_volume_is_open_at_the_frame_and_says_so(vol, crop):
    """83 of the crop's fragments touch the image border. A point off-frame is
    UNKNOWN, never a confident OUTSIDE (R4), and R2 resolves it to inside."""
    assert crop.n_unresolved.get("leaves_frame", 0) > 0
    assert vol.frame_open
    far_left = np.array([-3.0, 0.0, 1.0])       # projects well off the image
    assert vol.classify(far_left[None, :], DEFAULT_CLEARANCE_RDU)[0] == UNKNOWN
    assert vol.is_inside(far_left, clearance=DEFAULT_CLEARANCE_RDU)
    assert not vol.is_inside(far_left, clearance=DEFAULT_CLEARANCE_RDU,
                             unknown_is_inside=False)


def test_growing_the_clearance_never_unprotects_real_crop(scene, gt, vol):
    pts = _gt_points(scene, gt, gt.instances == 1, 4000, seed=5)
    prev = np.zeros(len(pts), bool)
    for c in CLEARANCE_SWEEP_RDU:
        now = vol.is_inside(pts, clearance=c)
        assert np.all(now | ~prev)
        prev = now


def test_the_shipped_product_round_trips(tmp_path, vol):
    p = vol.save(str(tmp_path / "k.npz"))
    b = load_keepout(p)
    assert b.cell == vol.cell and b.frame_open == vol.frame_open
    assert np.array_equal(b.tier, vol.tier)
    assert b.scale_confidence == "scale_free"
    q = np.random.default_rng(7).uniform(-0.4, 0.4, size=(300, 3)) + np.array([0, 0, 1.0])
    assert np.array_equal(vol.is_inside(q, clearance=DEFAULT_CLEARANCE_RDU),
                          b.is_inside(q, clearance=DEFAULT_CLEARANCE_RDU))


def test_the_shipped_product_on_disk_carries_its_caveats():
    from a6_api import SHIPPED
    if not os.path.exists(SHIPPED):
        pytest.skip("run run_a6.py first")
    v = load_keepout(SHIPPED)
    assert v.scale_confidence == "scale_free"
    assert "STRAW" in v.datum.upper()
    assert "A7" in v.provenance["crop_identity"]
    assert "R2" in v.provenance["occupancy_assumption"] or \
           "R4" in v.provenance["occupancy_assumption"]
    assert v.provenance["a4"]["policy"] == "merge"


# ---------------------------------------------------------------------------
# discipline
# ---------------------------------------------------------------------------

A6_MODULES = ["a6_common.py", "keepout.py", "metrics.py", "run_a6.py",
              "a6_api.py", "figures.py"]

#: Every module-level numeric constant in A6, with the R1 category that
#: justifies it. The machine-readable twin of the rows in BOOKKEEPING.md.
ALLOWED_CONSTANTS = {
    "DEFAULT_CLEARANCE_RDU": "(b) tool geometry — PLACEHOLDER, retired by C3",
    "CLEARANCE_SWEEP_RDU": "(b) the sweep that bounds the placeholder",
    "DEFAULT_CELL_RDU": "(a) resolution ceiling / compute budget, not a threshold",
    "TEST_CELL": "(a) same, coarsened so the suite fits in memory",
    "GT_HW": "(a) A0's registered label grid",
    "DEPTH_HW": "(a) A1's registered depth grid",
    "GT_TO_DEPTH": "(a) the ratio of the two, identical in x and y",
    "GT_CROP_INSTANCE": "id, not a length",
    "GT_GRASS_UNRESOLVED": "id, not a length",
    "TIER_EMPTY": "enum", "TIER_OBSERVED": "enum", "TIER_UNSEEN": "enum",
    "OUTSIDE": "enum", "INSIDE": "enum", "UNKNOWN": "enum",
    "MAT_UNLABELLED": "A0 class id", "MAT_SQUASH_LEAF": "A0 class id",
    "MAT_SQUASH_PETIOLE": "A0 class id", "MAT_GRASS": "A0 class id",
    "MAT_BROADLEAF": "A0 class id", "MAT_STRAW": "A0 class id",
    "MAT_SOIL": "A0 class id", "MAT_FRUIT": "A0 class id",
    "MAT_OTHER": "A0 class id",
}

#: Identifiers that would mean A6 had reintroduced the thing A4 removed: a
#: length that encodes how far apart plants are, or how big a plant gets.
#: Matched as whole identifiers, not substrings, so `bbox_inches` and the word
#: "millimetres" inside an honesty message do not trip it.
FORBIDDEN = {"eps", "epsilon", "max_gap", "gap", "search_radius", "spacing",
             "radius", "plant_radius", "crown_radius", "neighbour_dist",
             "neighbor_dist", "min_dist", "dist_threshold", "cm", "mm",
             "metres", "meters", "inches", "proximity", "nearby"}


def _identifiers(path):
    """Every identifier in the module: names, attributes, arguments, keywords,
    and the names things are defined as. Docstrings and comments are not code
    and cannot hide anything, so they are simply not looked at."""
    tree = ast.parse(open(path).read())
    out = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.Name):
            out.add(n.id)
        elif isinstance(n, ast.Attribute):
            out.add(n.attr)
        elif isinstance(n, ast.arg):
            out.add(n.arg)
        elif isinstance(n, ast.keyword) and n.arg:
            out.add(n.arg)
        elif isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            out.add(n.name)
        elif isinstance(n, ast.alias):
            out.add(n.asname or n.name.split(".")[-1])
    return {o.lower() for o in out}


def test_no_spacing_constant_anywhere_in_the_code_path():
    bad = []
    for m in A6_MODULES:
        for ident in sorted(_identifiers(os.path.join(HERE, m)) & FORBIDDEN):
            bad.append(f"{m}: {ident!r}")
    assert not bad, ("A6 must contain no spacing constant. The only length it "
                     f"is allowed is the tool clearance. Found: {bad}")


def test_the_only_length_the_shape_depends_on_is_the_clearance():
    """`build_keepout` takes exactly two lengths: the clearance (the parameter)
    and the cell (a reporting resolution). Anything else with a unit of length
    in its signature would be an unregistered constant."""
    import inspect

    import keepout as ko
    params = inspect.signature(ko.build_keepout).parameters
    lengths = {n for n, p in params.items()
               if isinstance(p.default, float) and p.default != 0}
    assert lengths == {"cell", "clearance", "max_clearance"}, lengths


def test_every_module_level_constant_is_registered():
    unregistered = []
    for m in A6_MODULES:
        tree = ast.parse(open(os.path.join(HERE, m)).read())
        for node in tree.body:
            if not isinstance(node, (ast.Assign, ast.AnnAssign)):
                continue
            targets = (node.targets if isinstance(node, ast.Assign)
                       else [node.target])
            names = [t.id for t in targets if isinstance(t, ast.Name)]
            if not names:
                continue
            has_number = any(isinstance(n, ast.Constant)
                             and isinstance(n.value, (int, float))
                             and not isinstance(n.value, bool)
                             for n in ast.walk(node.value)) if node.value else False
            for name in names:
                if has_number and name.isupper() and name not in ALLOWED_CONSTANTS:
                    unregistered.append(f"{m}:{name}")
    assert not unregistered, (
        "R1: every numeric constant needs a category in ALLOWED_CONSTANTS and a "
        f"row in BOOKKEEPING.md. Unregistered: {unregistered}")


def test_the_clearance_is_the_only_parameter_of_the_shape():
    """Changing nothing but the clearance must change nothing but the size."""
    v = _toy()
    a = v.footprint(0.0)
    b = v.footprint(0.25)
    assert b.sum() > a.sum()
    assert np.all(b | ~a)


def test_the_default_clearance_is_documented_as_a_placeholder():
    src = open(os.path.join(HERE, "keepout.py")).read()
    i = src.index("DEFAULT_CLEARANCE_RDU =")
    head = src[max(0, i - 1200):i]
    assert "PLACEHOLDER" in head and "C3" in head and "(b)" in head
