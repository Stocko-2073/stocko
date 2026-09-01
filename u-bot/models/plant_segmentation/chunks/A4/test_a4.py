"""A4 — the tests that make the numbers mean what they say.

    ../A3/.venv/bin/python -m pytest test_a4.py -q

The load-bearing ones:

* **`test_no_spacing_constant_in_the_code_path`** — the chunk's whole premise.
  Every module-level numeric constant in every A4 module must appear in an
  explicit allow-list with its R1 category, and the source must contain no
  spacing vocabulary (`eps`, radius, max_gap, "cm", "apart", ...). If someone
  adds a distance-between-plants constant at 2am, this fails.
* **`test_synthetic_*`** — a scene built by hand where the right answer is known:
  two surfaces that touch in the image but step in depth must not be one
  component; two surfaces joined by a continuous ridge must be.
* **`test_tilt_invariance`** — adding an arbitrary plane to the whole scene
  changes no edge decision. That is what "subtract the soil surface first" is
  for, and it means a sloping bed cannot split a plant.
* **`test_fast_eval_matches_a0_eval`** — the sweeps' scorer and the contract's
  scorer agree exactly, including on degenerate maps.
"""
from __future__ import annotations

import os
import re
import sys

import numpy as np
import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import a4_common as C      # noqa: E402
import a4_graph as G       # noqa: E402
import fast_eval as FE     # noqa: E402
import run_a4 as R         # noqa: E402
import unresolved as U     # noqa: E402
import eval as a0eval      # noqa: E402

A4_MODULES = ["a4_common.py", "a4_graph.py", "run_a4.py", "unresolved.py",
              "fast_eval.py", "a4_api.py", "report.py", "sweeps.py"]

# Every module-level numeric constant A4 defines, with the R1 category that
# justifies it. A constant not on this list is a defect by construction.
ALLOWED_CONSTANTS = {
    "LOCAL_PLANARITY_P10_RDU": "(a) A1 instrument, verbatim",
    "CONTINUITY_WINDOW": "(a) window index into the above",
    "CONTINUITY_TOL_RDU": "(a) A1 instrument, read at CONTINUITY_WINDOW",
    "FIT_WINDOW": "(a) plane-fit support, 5x5",
    "DEPTH_RESOLUTION_FLOOR_RDU": "(a) A1 instrument; used only as a refusal",
    "CONNECTIVITY": "(a) 8-connected, the roadmap's registered adjacency",
    "MIN_FRAGMENT_PX": "(a) the fit support, = A0/A3 min region",
    "LINK_QUANTILE_LO": "(c) convention, swept",
    "LINK_QUANTILE_HI": "(c) convention, swept",
    "GT_H": "(a) A0 label grid", "GT_W": "(a) A0 label grid",
    "DEPTH_H": "(a) A1 raster grid", "DEPTH_W": "(a) A1 raster grid",
    "WITHIN_FRAGMENT_QUANTILE": "(c) convention, swept 50..99",
    # not thresholds: label-id lookups, the 8-neighbourhood itself, and the
    # sweep grids whose whole purpose is to move a value across decades
    "PLANT_IDS": "(a) A0 class ids, looked up by name",
    "CROP_IDS": "(a) A0 class ids, looked up by name",
    "WEED_IDS": "(a) A0 class ids, looked up by name",
    "DIRECTIONS": "(a) the four unordered directions of an 8-neighbourhood",
    "TOLS": "sweep grid, not a value used by the pipeline",
    "QUANTILES": "sweep grid, not a value used by the pipeline",
}

FORBIDDEN = re.compile(
    r"\b(eps|epsilon|dbscan|max_gap|max_distance|search_radius|neighbourhood_radius|"
    r"spacing|plant_spacing|row_spacing|cm\b|centimet|inches)\b", re.I)


def _executable_lines(path):
    """Source lines with comments and docstrings removed. The prose in this
    chunk necessarily *names* `eps` in order to say it is absent; the scan must
    look at code, not at the argument."""
    import ast
    src = open(path).read()
    lines = src.splitlines()
    skip = set()
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant) \
                and isinstance(node.value.value, str):
            skip.update(range(node.lineno, (node.end_lineno or node.lineno) + 1))
    for i, line in enumerate(lines, 1):
        if i in skip:
            continue
        yield i, line.split("#", 1)[0]


def test_no_spacing_constant_in_the_code_path():
    """R1: no constant may encode a belief about how gardens are arranged."""
    offenders = []
    for name in A4_MODULES:
        p = os.path.join(HERE, name)
        if not os.path.exists(p):
            continue
        for i, code in _executable_lines(p):
            m = FORBIDDEN.search(code)
            if m:
                offenders.append(f"{name}:{i}: {m.group(0)} :: {code.strip()}")
    assert not offenders, "spacing vocabulary in the A4 code path:\n" + \
        "\n".join(offenders)


def test_every_module_level_constant_is_registered():
    pat = re.compile(r"^([A-Z][A-Z0-9_]*)\s*=")
    unknown = []
    for name in A4_MODULES:
        p = os.path.join(HERE, name)
        if not os.path.exists(p):
            continue
        for _, line in _executable_lines(p):
            m = pat.match(line)
            if not m:
                continue
            rhs = line.split("=", 1)[1]
            if not re.search(r"[0-9]", rhs):
                continue                       # not numeric: paths, strings, ids
            if m.group(1) not in ALLOWED_CONSTANTS:
                unknown.append(f"{name}: {line.strip()}")
    assert not unknown, ("numeric constants with no R1 category:\n"
                         + "\n".join(unknown))


def test_tolerance_is_above_the_instrument_floor():
    assert C.CONTINUITY_TOL_RDU > C.DEPTH_RESOLUTION_FLOOR_RDU
    assert C.CONTINUITY_TOL_RDU == C.LOCAL_PLANARITY_P10_RDU[C.CONTINUITY_WINDOW]


# ------------------------------------------------------------- synthetic ----
def _synthetic(kind: str, H=160, W=160):
    """A scene with a known answer. Two square patches of material with a gap
    of background between them, and (optionally) a continuous ridge joining
    them — the synthetic petiole."""
    depth = np.full((H, W), 1.0, np.float32)
    plant = np.zeros((H, W), bool)
    yy, xx = np.mgrid[0:H, 0:W]
    a = (yy > 30) & (yy < 70) & (xx > 20) & (xx < 140)
    b = (yy > 90) & (yy < 130) & (xx > 20) & (xx < 140)
    plant |= a | b
    depth[a] = 0.80
    depth[b] = 0.60 if kind == "touching_step" else 0.80
    if kind == "ridge":
        ridge = (yy >= 70) & (yy <= 90) & (xx > 70) & (xx < 80)
        plant |= ridge
        depth[ridge] = 0.80          # continuous with both patches
    if kind == "touching_step":
        # the two patches meet with no gap, but at different depths
        mid = (yy >= 70) & (yy <= 90) & (xx > 20) & (xx < 140)
        plant |= mid
        depth[mid] = 0.60
    # three bands, standing in for what SAM supplies on the real image: the
    # test is of the *edge* decision, so the nodes are given, not discovered.
    regions = np.ones((H, W), np.int32)
    regions[yy >= 70] = 2
    regions[yy > 90] = 3
    material = np.where(plant, a0aleaf(), 0).astype(np.uint8)
    soil = np.full((H, W), 1.0, np.float32)
    return C.Inputs(
        relief=(soil - depth).astype(np.float32), depth_rdu=depth,
        soil_depth=soil, height_sigma=np.zeros((H, W), np.float32),
        a2_valid=np.ones((H, W), bool), coverage=np.zeros((H, W), np.uint8),
        material=material, material_gt=material,
        confidence_gt=np.ones((H, W), np.float32), regions=regions, plant=plant,
        provenance={"synthetic": kind})


def a0aleaf():
    return a0eval.CID["squash_leaf"]


def _components_of(inp, tol):
    frag, _ = G.build_fragments(inp, use_class=True)
    n = int(frag.max())
    s = G.summarise_boundaries(
        G.boundary_residuals(inp, frag, intra=False, statistic="secdiff"), n)
    conn, sep, unres = G.classify_edges(s, tol)
    comp = G.components(n, s["pairs"], conn)
    return comp[frag], frag, s, (conn, sep, unres)


def test_synthetic_touching_surfaces_at_different_depths_do_not_merge():
    inp = _synthetic("touching_step")
    lab, *_ = _components_of(inp, 1e-3)
    ids = np.unique(lab[lab > 0])
    assert len(ids) >= 2, "a step in depth must cut the component"
    top = lab[35, 80]
    bot = lab[125, 80]
    assert top != bot


def test_synthetic_ridge_joins_two_patches():
    """The petiole case: two surfaces that touch nothing else, joined by a
    continuous bridge of material at the same height, must be one component."""
    inp = _synthetic("ridge")
    lab, *_ = _components_of(inp, 1e-3)
    assert lab[35, 80] != 0 and lab[125, 80] != 0
    assert lab[35, 80] == lab[125, 80], "a continuous ridge must connect"


def test_synthetic_disconnected_patches_stay_apart_at_any_tolerance():
    """No spacing parameter exists, so no tolerance can bridge a gap. This is
    the property `eps` did not have: raising the threshold cannot reach across
    empty space, only across material."""
    inp = _synthetic("same_height")
    for tol in (1e-6, 1e-3, 1.0, 1e6):
        lab, *_ = _components_of(inp, tol)
        assert lab[35, 80] != lab[125, 80], f"bridged a gap at tol={tol}"


def test_tilt_invariance():
    """Adding an arbitrary plane to the *scene* and to the *datum* together
    changes no edge decision — which is what subtracting `soil_surface_depth`
    buys, and why a sloping bed cannot split a plant."""
    inp = _synthetic("ridge")
    _, _, s0, v0 = _components_of(inp, 1e-3)
    yy, xx = np.mgrid[0:inp.relief.shape[0], 0:inp.relief.shape[1]]
    plane = (0.004 * yy - 0.003 * xx).astype(np.float32)
    tilted = C.Inputs(**{**inp.__dict__,
                         "depth_rdu": inp.depth_rdu + plane,
                         "soil_depth": inp.soil_depth + plane})
    tilted.relief = (tilted.soil_depth - tilted.depth_rdu).astype(np.float32)
    _, _, s1, v1 = _components_of(tilted, 1e-3)
    assert np.array_equal(s0["pairs"], s1["pairs"])
    assert np.allclose(s0["p50"], s1["p50"], atol=1e-6)
    for a, b in zip(v0, v1):
        assert np.array_equal(a, b)


def test_depth_offset_invariance():
    inp = _synthetic("ridge")
    _, _, _, v0 = _components_of(inp, 1e-3)
    shifted = C.Inputs(**{**inp.__dict__,
                          "depth_rdu": inp.depth_rdu + 0.37,
                          "soil_depth": inp.soil_depth + 0.37})
    _, _, _, v1 = _components_of(shifted, 1e-3)
    for a, b in zip(v0, v1):
        assert np.array_equal(a, b)


def test_edges_are_classified_exactly_once():
    inp = _synthetic("touching_step")
    _, _, s, (conn, sep, unres) = _components_of(inp, 1e-3)
    assert np.array_equal(conn.astype(int) + sep.astype(int) + unres.astype(int),
                          np.ones(len(conn), int))


def test_fragments_partition_the_plant_mask():
    inp = _synthetic("ridge")
    frag, info = G.build_fragments(inp, use_class=True)
    assert np.array_equal(frag > 0, inp.plant)
    assert int(frag.max()) == len(np.unique(frag)) - 1     # compact ids


def test_components_union_find():
    pairs = np.array([[1, 2], [3, 4], [4, 5], [6, 7]])
    conn = np.array([True, True, True, False])
    comp = G.components(7, pairs, conn)
    assert comp[1] == comp[2]
    assert comp[3] == comp[4] == comp[5]
    assert comp[6] != comp[7]
    assert comp[0] == 0


def test_build_refuses_a_tolerance_below_the_resolution_floor():
    inp = _synthetic("ridge")
    with pytest.raises(ValueError, match="resolution floor"):
        R.build(inp, tol=1e-9)


def test_to_gt_grid_invents_no_labels():
    a = np.random.default_rng(0).integers(0, 50, (C.DEPTH_H, C.DEPTH_W)).astype(np.int32)
    b = C.to_gt_grid_nearest(a)
    assert b.shape == (C.GT_H, C.GT_W)
    assert set(np.unique(b)).issubset(set(np.unique(a)))


# ------------------------------------------------------------ scorers -------
@pytest.fixture(scope="module")
def gt():
    return a0eval.load_gt()


def _maps(gt):
    rng = np.random.default_rng(1)
    yield "gt itself", np.where(gt.instances == 255, 0, gt.instances).astype(np.int32)
    yield "all one", (np.isin(gt.material, C.PLANT_IDS)).astype(np.int32)
    yield "shattered", (rng.integers(1, 400, gt.instances.shape)
                        * (gt.instances > 0)).astype(np.int32)
    yield "empty", np.zeros_like(gt.instances, np.int32)
    p = os.path.join(C.PRODUCTS, "components_gt_grid_default.npy")
    if os.path.exists(p):
        yield "A4 default", np.load(p)


def test_fast_eval_matches_a0_eval(gt):
    for name, m in _maps(gt):
        want = a0eval.instance_scores(m, gt)
        got = FE.instance_scores(m, gt)
        for k in ("n_gt", "n_pred", "tp", "fp", "fn", "precision", "recall", "f1"):
            assert np.isclose(want[k], got[k]), f"{name}: {k}"
        assert {m["gt"] for m in want["matches"]} == {m["gt"] for m in got["matches"]}
        for g, v in want["best_iou_per_gt"].items():
            assert np.isclose(v["iou"], got["best_iou_per_gt"][int(g)]["iou"]), name
        assert (a0eval.fragmentation(m, gt)["n_pred_parts"]
                == FE.fragmentation(m, gt)["n_pred_parts"]), name


def test_the_recorded_baseline_still_scores_zero(gt):
    """Guards the comparison itself: if this moves, RESULTS.md is stale."""
    z = a0eval.load_zps_baseline(gt)
    s = a0eval.instance_scores(z.instances, gt)
    assert s["f1"] == 0.0 and s["tp"] == 0
    assert np.isclose(s["best_iou_per_gt"][1]["iou"], 0.425, atol=5e-3)
    assert np.isclose(
        a0eval.grass_absorption(z.instances, gt)["absorbed_fraction"], 0.530,
        atol=2e-3)


# ------------------------------------------------------- unresolved edges ---
def test_unresolved_edges_are_recorded_not_decided():
    inp = _synthetic("touching_step")
    frag, _ = G.build_fragments(inp, use_class=True)
    n = int(frag.max())
    s = G.summarise_boundaries(
        G.boundary_residuals(inp, frag, intra=False, statistic="secdiff"), n)
    conn, sep, unres = G.classify_edges(s, 1e-3)
    comp = G.components(n, s["pairs"], conn)
    edges, info = U.find_unresolved(inp, frag, s, conn, unres, comp)
    kinds = {e["kind"] for e in edges}
    assert kinds <= {"ambiguous_boundary", "occluded_by", "leaves_frame"}
    assert info["n_unresolved_edges"] == len(edges)
    # every ambiguous edge in the list is one the graph did not link
    for e in edges:
        if e["kind"] == "ambiguous_boundary":
            i = np.nonzero((s["pairs"][:, 0] == e["a"])
                           & (s["pairs"][:, 1] == e["b"]))[0]
            assert not conn[i].any()
