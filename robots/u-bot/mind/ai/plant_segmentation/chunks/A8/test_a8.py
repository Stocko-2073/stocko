"""A8 — the gate, proved rather than described.

Run:  chunks/A3/.venv/bin/python -m pytest chunks/A8/test_a8.py -q

The two tests the roadmap asks for by name are
`test_a_high_confidence_remove_with_an_extrapolated_contact_is_rejected` and
`test_a_point_inside_the_squash_keep_out_is_rejected`. Both feed the gate a
label that is as favourable to removal as the schema permits — `remove` at
confidence 1.0, unanimous across the required repeats, not mixed — and both
assert that the geometry refuses it anyway. That is what "the gate is enforced
in code, not by instructing the model" means, stated as an experiment: the
model is made to say the most dangerous thing it can say, and nothing moves.
"""
from __future__ import annotations

import ast
import json
import os
import re
import subprocess
import sys

import numpy as np
import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import a8_common as C  # noqa: E402
import a8_constants as K  # noqa: E402
import a8_gate as G  # noqa: E402
import a8_tools as T  # noqa: E402
from client import StdioClient  # noqa: E402

TOOL = {"name": "test", "clearance": 1.0e-2, "clearance_units": "rdu"}


# --------------------------------------------------------------------------
# fixtures
# --------------------------------------------------------------------------


@pytest.fixture(scope="module")
def product():
    return T.load_products()[0]


@pytest.fixture(scope="module")
def dist():
    return T.load_products()[1]


@pytest.fixture(scope="module")
def a7_labels():
    doc = C.load_a7_labels()
    return [{"id": int(cid), "label": r["label"],
             "confidence": float(r["confidence"]), "reason": str(r["reason"]),
             "mixed": bool(r["mixed"])}
            for rep in doc["repeats"] for cid, r in sorted(rep.items())]


def forced_remove(cid, confidence=1.0, n=K.MIN_LABEL_REPEATS, mixed=False):
    """The most dangerous thing a labeller can say about an instance."""
    return [{"id": int(cid), "label": "remove", "confidence": confidence,
             "reason": "forced by the test", "mixed": mixed}
            for _ in range(n)]


def plan(labels, **kw):
    kw.setdefault("confidence_floor", 0.0)
    return T.plan_removals(labels, TOOL, **kw)


def verdict(doc, cid):
    for t in doc["targets"]:
        if t["instance_id"] == cid:
            return True, []
    for r in doc["rejections"]:
        if r["instance_id"] == cid:
            return False, r["reasons"]
    raise AssertionError(f"instance {cid} appears in neither list")


# --------------------------------------------------------------------------
# The two tests the roadmap names
# --------------------------------------------------------------------------


def test_a_high_confidence_remove_with_an_extrapolated_contact_is_rejected(product):
    """R2's second condition. An extrapolated point is a guess with a distance
    attached; no confidence in the label can promote it to an observation."""
    cid = next(i["instance_id"] for i in product["instances"]
               if i["contact_candidates"]
               and {c["status"] for c in i["contact_candidates"]}
                   == {"extrapolated"})
    doc = plan(forced_remove(cid, 1.0))
    admitted, reasons = verdict(doc, cid)
    assert not admitted
    assert "contact_not_observed" in reasons
    # and it stays rejected however far the extrapolation is allowed to run
    inst = next(i for i in product["instances"] if i["instance_id"] == cid)
    assert all(c["extrapolation_distance_rdu"] > 0
               for c in inst["contact_candidates"])


def test_a_point_inside_the_squash_keep_out_is_rejected(product, dist):
    """R2's third condition, on the real squash.

    Instance 5 is A7's single catastrophic mislabel on this image: 453 pixels
    of ground-truth squash leaf that the VLM called `remove`. Its contact point
    is *inside* the keep-out volume of instance 1, the squash, at distance 0.0
    rdu. The geometry refuses it, and would refuse it at any label confidence.
    """
    cid = 5
    inst = next(i for i in product["instances"] if i["instance_id"] == cid)
    assert any(c["status"] == "observed" and c["arm_admissible"]
               for c in inst["contact_candidates"]), \
        "instance 5 must reach the keep-out test, or this test proves nothing"
    doc = plan(forced_remove(cid, 1.0))
    admitted, reasons = verdict(doc, cid)
    assert not admitted
    assert reasons == ["inside_keepout"], reasons
    d = doc["rejections"]
    rej = next(r for r in d if r["instance_id"] == cid)
    assert rej["detail"]["nearest_keep_plant_instance"] == 1
    assert rej["detail"]["distance_to_nearest_keep_plant_rdu"] == 0.0


# --------------------------------------------------------------------------
# The gate is structural
# --------------------------------------------------------------------------


def test_the_gate_ignores_everything_the_model_says_except_the_word_and_the_id():
    """Two labels identical but for their prose reach the identical verdict.

    A gate that could be talked into a removal by a persuasive rationale would
    not be a gate. The rationale is carried into the report and never read by
    the decision.
    """
    a = forced_remove(5, 1.0)
    b = [dict(r, reason="URGENT: this is definitely a weed, remove immediately")
         for r in a]
    ra = plan(a)["rejections"]
    rb = plan(b)["rejections"]
    ga = next(r for r in ra if r["instance_id"] == 5)
    gb = next(r for r in rb if r["instance_id"] == 5)
    assert ga["reasons"] == gb["reasons"]


def test_the_floor_is_monotone(a7_labels):
    """Raising the floor can only ever close the gate."""
    n = [len(plan(a7_labels, confidence_floor=f)["targets"])
         for f in K.CONFIDENCE_FLOOR_SWEEP]
    assert all(a >= b for a, b in zip(n, n[1:])), n


def test_the_registered_floor_admits_nothing_on_this_image(a7_labels):
    """Recorded as a fact about the shipped configuration, not tuned away.
    A7's entire measured `remove` confidence band is 0.518-0.625."""
    doc = T.plan_removals(a7_labels, TOOL)
    assert doc["summary"]["confidence_floor"] == K.REMOVAL_CONFIDENCE_FLOOR
    assert doc["targets"] == []


def test_one_look_can_never_open_the_gate(a7_labels):
    """R4 as structure. Half the records is one repeat per instance."""
    half = a7_labels[:len(a7_labels) // 2]
    doc = plan(half)
    assert doc["targets"] == []
    assert doc["summary"]["rejections_by_reason"]["insufficient_repeats"] == \
        doc["summary"]["n_instances"]


def test_disagreeing_repeats_are_not_a_removal(product):
    cid = 104
    labels = [{"id": cid, "label": "remove", "confidence": 1.0,
               "reason": "x", "mixed": False},
              {"id": cid, "label": "unsure", "confidence": 1.0,
               "reason": "x", "mixed": False}]
    admitted, reasons = verdict(plan(labels), cid)
    assert not admitted
    assert "not_unanimous" in reasons and "label_not_remove" in reasons


def test_a_remove_on_a_mixed_component_is_refused_outright(product):
    """A7's hard input: a component flagged `mixed` is not a plant."""
    cid = 104
    assert verdict(plan(forced_remove(cid, 1.0)), cid)[0], \
        "instance 104 must be admissible when not mixed, or this proves nothing"
    admitted, reasons = verdict(plan(forced_remove(cid, 1.0, mixed=True)), cid)
    assert not admitted and reasons == ["mixed_component"]


def test_a_label_carrying_a_coordinate_is_discarded_not_patched(product):
    """R3 on the way in. A7's own validator, reused unchanged."""
    labels = [{"id": 104, "label": "remove", "confidence": 1.0,
               "reason": "the weed at (412, 806), bbox 40x40", "mixed": False}
              for _ in range(K.MIN_LABEL_REPEATS)]
    admitted, reasons = verdict(plan(labels), 104)
    assert not admitted
    assert "label_discarded_r3" in reasons
    assert "component_unlabelled" in reasons


def test_a_geometric_key_in_a_label_is_discarded(product):
    labels = [{"id": 104, "label": "remove", "confidence": 1.0,
               "reason": "ok", "mixed": False, "centroid": [1, 2]}
              for _ in range(K.MIN_LABEL_REPEATS)]
    # unknown keys are dropped before validation, so the record survives as a
    # label -- but it cannot smuggle geometry in, which is the property R3 wants
    doc = plan(labels)
    admitted, _ = verdict(doc, 104)
    assert admitted
    t = next(t for t in doc["targets"] if t["instance_id"] == 104)
    assert "centroid" not in json.dumps(t)


def test_a_metric_tool_profile_is_refused_not_converted(a7_labels):
    doc = T.plan_removals(a7_labels, {"name": "tine", "clearance": 15.0,
                                      "clearance_units": "mm"},
                          confidence_floor=0.0)
    assert doc["targets"] == []
    assert doc["summary"]["refusal"]["reason"] == "metric_tool_profile_refused"
    assert all("metric_tool_profile_refused" in r["reasons"]
               for r in doc["rejections"])


def test_positioning_repeatability_widens_the_protected_region():
    a = G.ToolProfile.parse({"clearance": 1e-2})
    b = G.ToolProfile.parse({"clearance": 1e-2,
                             "positioning_repeatability": 5e-3})
    assert b.effective_clearance() > a.effective_clearance()


def test_keep_plants_do_not_depend_on_the_confidence_floor(a7_labels):
    n = {f: T.plan_removals(a7_labels, TOOL, confidence_floor=f
                            )["summary"]["n_keep_plants"]
         for f in (0.0, 0.6, 0.9)}
    assert len(set(n.values())) == 1, n


# --------------------------------------------------------------------------
# The seams
# --------------------------------------------------------------------------


def test_the_split_to_merge_map_is_a_function():
    """Seam 1. A split component's pixels lie inside exactly one merge
    component; `split_to_merge` raises rather than voting if they do not."""
    st = C.load_stack(with_gt=False)
    split_labels = st.a4_split.components_depth
    merge_labels = st.a4_merge.components_depth
    present = set(np.unique(split_labels[split_labels > 0]).tolist())
    assert len(st.s2m) == len(present) == 742
    # checked independently of `split_to_merge`'s own arithmetic: for a sample
    # of ids, and for the two that matter most, the merge label is unique.
    rng = np.random.default_rng(0)
    sample = list(rng.choice(sorted(present), 60, replace=False)) + [37, 441]
    for sid in sample:
        labels = set(np.unique(merge_labels[split_labels == int(sid)]).tolist())
        assert labels == {st.s2m[int(sid)]}, (sid, labels)


def test_the_rebuilt_keep_out_reproduces_A6s_shipped_volume(dist):
    """Seam 2. A8 rebuilds a volume for every instance, from the same
    machinery, with A0's crop lookup removed. For the component A0's crop lands
    in, it must be A6's own volume."""
    sys.path.insert(0, os.path.join(C.ROOT, "chunks", "A6"))
    from a6_api import load_a6
    vol = load_a6()
    assert vol.provenance["a4"]["component_id"] == 1
    j = [int(x) for x in dist["instance_ids"]].index(1)
    d6 = vol.distance_to_material(dist["point_xyz_rdu"])
    assert np.abs(d6 - dist["distance_rdu"][:, j]).max() < 1e-6


def test_the_distance_table_reproduces_A6s_is_inside_exactly(dist):
    """The gate reads a table instead of calling `classify`; the table must be
    the same answer. Includes A6's conservative bracket and its UNKNOWN rule."""
    sys.path.insert(0, os.path.join(C.ROOT, "chunks", "A6"))
    from a6_api import load_a6
    vol = load_a6()
    j = [int(x) for x in dist["instance_ids"]].index(1)
    pts = dist["point_xyz_rdu"]
    mine = ((dist["distance_rdu"][:, j] <= vol.clearance_rdu + vol.voxel_bracket)
            | (dist["frame_open"][j] & dist["point_off_frame"]))
    assert np.array_equal(mine, vol.is_inside(pts))


def test_contact_admissibility_is_A5s_own(product):
    """Seam 3. A8 does not re-derive `arm_admissible`; it carries A5's."""
    st = C.load_stack(with_gt=False)
    a5adm = {c.raw["component"] for c in st.a5.admissible()}
    mine = {c["split_component"] for i in product["instances"]
            for c in i["contact_candidates"] if c["arm_admissible"]}
    # A5's admissible set includes components with no point at all? it must not
    assert mine <= a5adm
    with_point = {c.raw["component"] for c in st.a5.admissible() if c.raw["point"]}
    assert mine == with_point


def test_no_extrapolated_contact_is_ever_arm_admissible(product):
    """A5 asserts this on its own products; A8 asserts it survives the seam."""
    for i in product["instances"]:
        for c in i["contact_candidates"]:
            if c["arm_admissible"]:
                assert c["status"] == "observed"


# --------------------------------------------------------------------------
# Discipline: the R1 rules A4, A5 and A6 established
# --------------------------------------------------------------------------

A8_MODULES = ("a8_common.py", "a8_constants.py", "a8_gate.py", "a8_tools.py",
              "server.py", "client.py", "build_products.py", "run_a8.py")

BANNED_IDENTIFIER = re.compile(
    r"^(eps|epsilon|radius|spacing|max_gap|gap|cm|mm|metres?|meters?|inches?|"
    r"plant_spacing|row_spacing|crop_size|typical_.*|expected_.*)$", re.I)


def test_no_identifier_encodes_a_belief_about_how_gardens_are_arranged():
    for m in A8_MODULES:
        tree = ast.parse(open(os.path.join(HERE, m)).read())
        for node in ast.walk(tree):
            for name in ([node.id] if isinstance(node, ast.Name) else
                         [a.arg for a in node.args.args]
                         if isinstance(node, ast.FunctionDef) else []):
                assert not BANNED_IDENTIFIER.match(name), f"{m}: {name}"


def test_every_numeric_constant_in_the_gate_is_registered():
    """Every module-level number in the decision path is either in
    `a8_constants` with an R1 category, or is a structural 0/1."""
    allowed = {0, 1, 2, 0.0, 1.0, 1e-6, 1e-12, 1e9}
    registered = {v for k, v in vars(K).items()
                  if isinstance(v, (int, float)) and not k.startswith("_")}
    registered |= set(K.CONFIDENCE_FLOOR_SWEEP)
    for m in ("a8_gate.py",):
        tree = ast.parse(open(os.path.join(HERE, m)).read())
        for node in tree.body:
            if not isinstance(node, (ast.Assign, ast.AnnAssign)):
                continue
            for sub in ast.walk(node):
                if isinstance(sub, ast.Constant) and isinstance(
                        sub.value, (int, float)) and not isinstance(
                        sub.value, bool):
                    assert sub.value in allowed | registered, \
                        f"{m}: unregistered module-level constant {sub.value}"


def test_no_output_carries_a_metre(a7_labels):
    """A6's instruction: A8 must not print a metre."""
    doc = T.plan_removals(a7_labels, TOOL, confidence_floor=0.0)
    s = json.dumps(doc)
    for unit in (r"\d\s*mm\b", r"\d\s*cm\b", r"\d+(\.\d+)?\s*m\b",
                 r"\d\s*metres?\b", r"\d\s*inch"):
        assert re.search(unit, s) is None, unit
    assert doc["scale_confidence"] == "scale_free"


def test_every_rejection_reason_is_in_the_closed_vocabulary(a7_labels):
    doc = T.plan_removals(a7_labels, TOOL, confidence_floor=0.0)
    for r in doc["rejections"]:
        assert r["reasons"], f"instance {r['instance_id']} rejected with no reason"
        for reason in r["reasons"]:
            assert reason in G.REASONS
    assert set(G.REASON_ORDER) == set(G.REASONS)


def test_an_admitted_target_carries_no_rejection_reason(a7_labels):
    doc = T.plan_removals(a7_labels, TOOL, confidence_floor=0.0)
    ids = {t["instance_id"] for t in doc["targets"]}
    assert not ids & {r["instance_id"] for r in doc["rejections"]}
    assert len(ids) + len(doc["rejections"]) == doc["summary"]["n_instances"]


def test_segment_garden_emits_no_crop_judgement(product):
    """R3 in the tool surface: the geometry tool has no opinion to leak.

    Note what this does NOT assert. A3's material vocabulary is A0's, and A0's
    class names include `squash_leaf` and `squash_petiole` — so `material_class`
    does name the crop species, and `segment_garden` is not species-blind. It
    was never meant to be: the roadmap asks it for a material class. What R3
    forbids is a *crop-vs-weed decision* and a coordinate coming from the
    labeller, and neither is here.
    """
    out = T.segment_garden(T.DEFAULT_IMAGE, include_contact_candidates=False)
    assert all(i["crop"] is None for i in out["instances"])
    assert all(i["crop_source"].startswith("unassigned") for i in out["instances"])
    banned = {"is_crop", "weed", "is_weed", "label", "verdict", "remove",
              "keep", "target", "confidence_floor"}
    for i in out["instances"]:
        assert not (set(i) & banned), sorted(set(i) & banned)


def test_segment_garden_refuses_another_image():
    with pytest.raises(T.ToolRefusal):
        T.segment_garden(os.path.join(C.ROOT, "somewhere_else.jpeg"))


def test_segment_garden_refuses_intrinsics_it_did_not_build_with():
    with pytest.raises(T.ToolRefusal):
        T.segment_garden(T.DEFAULT_IMAGE, intrinsics={"fx": 3005.0})


def test_no_target_lands_on_ground_truth_crop(a7_labels):
    """The R2 question, asked of A0 directly, at every floor in the sweep."""
    gtd = json.load(open(os.path.join(C.PRODUCTS, "gt_audit.json")))["instances"]
    for f in K.CONFIDENCE_FLOOR_SWEEP:
        doc = T.plan_removals(a7_labels, TOOL, confidence_floor=f)
        for t in doc["targets"]:
            assert gtd[str(t["instance_id"])]["gt_crop_px"] == 0, (f, t)


# --------------------------------------------------------------------------
# The server, over the wire
# --------------------------------------------------------------------------


def test_the_server_speaks_mcp_over_stdio(a7_labels):
    with StdioClient() as cli:
        assert cli.server_info["name"] == "weeding-perception"
        names = {t["name"] for t in cli.list_tools()}
        assert names == {"segment_garden", "plan_removals"}
        for t in cli.list_tools():
            assert t["inputSchema"]["type"] == "object"
            assert t["inputSchema"]["properties"]
        seg = cli.call_ok("segment_garden", {"image": T.DEFAULT_IMAGE,
                                             "include_contact_candidates": False})
        assert seg["n_instances"] == 207
        plan_doc = cli.call_ok("plan_removals",
                               {"labels": a7_labels, "tool_profile": TOOL})
        assert plan_doc["targets"] == []
        assert plan_doc["summary"]["n_instances"] == 207


def test_a_refusal_comes_back_as_an_error_not_as_an_empty_answer():
    """A7's lesson: a transport or refusal path that returns a safe-looking
    result is worse than one that fails loudly."""
    with StdioClient() as cli:
        _, is_err, text = cli.call("segment_garden", {"image": "/nope.jpeg"})
        assert is_err and "REFUSED" in text
        _, is_err, _ = cli.call("no_such_tool", {})
        assert is_err


def test_the_server_reports_an_unknown_method():
    with StdioClient() as cli:
        with pytest.raises(Exception):
            cli.request("resources/list")


def test_nothing_in_the_tool_surface_can_move_anything():
    """`plan_removals` ends at a target list. Asserted by parsing, because the
    roadmap makes it a hard boundary."""
    banned = ("subprocess", "socket", "serial", "requests", "urllib", "http",
              "asyncio")
    for m in ("a8_gate.py", "a8_tools.py"):
        tree = ast.parse(open(os.path.join(HERE, m)).read())
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for a in node.names:
                    assert a.name.split(".")[0] not in banned, (m, a.name)
            if isinstance(node, ast.ImportFrom):
                assert (node.module or "").split(".")[0] not in banned, m
