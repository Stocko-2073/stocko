"""A7 — tests.

These assert the properties that make the rest of the chunk trustworthy:

* **R3 is enforced by code, not by the prompt.** The validator rejects a
  coordinate however it is smuggled in — as a key, as a pair in the rationale,
  as a measurement with units.
* **No ID is ever dropped.** Every shipped label file covers all 207 A4 `merge`
  components, and every triaged or failed ID is present as `unsure`.
* **The default is `keep`/`unsure`, never `remove`.** No code path can turn a
  failure into a removal.
* **The experiment was isolated.** No `CLAUDE.md` is reachable from the arena
  the model ran in, so the repository's own statement of the crop, the weeds and
  the design rules could not leak into the answer.
* **The two prompt variants differ in exactly one paragraph**, so the ablation
  measures the asymmetry claim and not the wording.

Run: `chunks/A3/.venv/bin/python -m pytest chunks/A7/test_a7.py -q`
"""
from __future__ import annotations

import glob
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import prompts as P          # noqa: E402
import schema as S           # noqa: E402
import vlm                   # noqa: E402
from a7_data import (load_components, tier_report, MIN_REVIEWABLE_PX,  # noqa: E402
                     TIER1_PX)

HERE = os.path.dirname(os.path.abspath(__file__))
RES = os.path.join(HERE, "results")


# ---------------------------------------------------------------- R3, in code
@pytest.mark.parametrize("obj,why", [
    ({"id": 1, "label": "remove", "confidence": 0.9, "reason": "weed",
      "x": 10}, "geometric key"),
    ({"id": 1, "label": "remove", "confidence": 0.9, "reason": "weed",
      "bbox": [1, 2, 3, 4]}, "geometric key"),
    ({"id": 1, "label": "remove", "confidence": 0.9, "reason": "centroid"},
     "centroid in prose"),
    ({"id": 1, "label": "remove", "confidence": 0.9,
      "reason": "weed at (412, 903)"}, "coordinate pair"),
    ({"id": 1, "label": "remove", "confidence": 0.9,
      "reason": "weed near 412,903"}, "bare coordinate pair"),
    ({"id": 1, "label": "remove", "confidence": 0.9,
      "reason": "about 40 mm across"}, "measurement"),
    ({"id": 1, "label": "remove", "confidence": 0.9, "reason": "x=51 here"},
     "x= form"),
    ({"id": 1, "label": "keep", "confidence": 0.9, "reason": "ok",
      "mixed": True, "mixed_note": "grass at (10, 20)"}, "coord in mixed_note"),
])
def test_r3_violations_are_rejected(obj, why):
    with pytest.raises(S.R3Violation):
        S.validate_label(obj)


def test_clean_label_passes_and_is_normalised():
    o = S.validate_label({"id": "7", "label": "keep", "confidence": "0.8",
                          "reason": "squash leaf, lobed and hairy"})
    assert o["id"] == 7 and o["confidence"] == 0.8 and o["mixed"] is False
    assert o["r3_soft"] == []


def test_frame_relative_prose_is_recorded_not_rejected():
    o = S.validate_label({"id": 7, "label": "keep", "confidence": 0.8,
                          "reason": "leaf in the lower left of the frame"})
    assert o["r3_soft"], "frame-relative prose should be recorded"


@pytest.mark.parametrize("obj", [
    {"id": 1, "label": "kill", "confidence": 0.9, "reason": "x"},
    {"id": 1, "label": "remove", "confidence": 1.4, "reason": "x"},
    {"id": 1, "label": "remove", "confidence": "high", "reason": "x"},
    {"id": 1, "label": "remove", "reason": "x"},
])
def test_malformed_labels_are_rejected(obj):
    with pytest.raises(ValueError):
        S.validate_label(obj)


def test_id_mismatch_is_rejected():
    with pytest.raises(ValueError):
        S.validate_label({"id": 9, "label": "keep", "confidence": 0.5,
                          "reason": "x"}, expect_id=8)


def test_fallback_is_never_a_removal():
    f = S.fallback(3, "anything at all")
    assert f["label"] == "unsure" and f["confidence"] == 0.0


def test_no_label_object_can_be_built_with_a_coordinate_field():
    """The schema is closed: only the six permitted keys exist."""
    assert S.ALLOWED_KEYS == {"id", "label", "confidence", "reason", "mixed",
                              "mixed_note"}
    assert not any(S.BANNED_KEY.match(k) for k in S.ALLOWED_KEYS)


def test_extract_json_survives_fences_and_chatter():
    assert S.extract_json('```json\n{"a": 1}\n```')["a"] == 1
    assert S.extract_json('Sure!\n{"a": 2}\nHope that helps')["a"] == 2
    with pytest.raises(ValueError):
        S.extract_json("no json here")


# ------------------------------------------------------------ prompt contract
def test_variants_differ_in_exactly_one_paragraph():
    a = P.prompt_A(5, "neutral", ["/f.png"]).split("\n\n")
    b = P.prompt_A(5, "r2", ["/f.png"]).split("\n\n")
    diff = [i for i, (x, y) in enumerate(zip(a, b)) if x != y]
    assert len(a) == len(b) and len(diff) == 1, (len(a), len(b), diff)


def test_r2_paragraph_states_the_asymmetry_and_neutral_denies_it():
    assert "catastrophic" in P.COST_R2 and "defaults to `keep`" in P.COST_R2
    assert "equally costly" in P.COST_NEUTRAL
    assert abs(len(P.COST_R2) - len(P.COST_NEUTRAL)) < 60


def test_prompt_forbids_coordinates_and_offers_unsure():
    p = P.prompt_A(5, "r2", ["/f.png"])
    assert "must not output coordinates" in p
    assert "unsure" in p


def test_prompt_never_names_the_crop_or_the_weeds():
    """The prompt must not hand the model the answer A0 holds."""
    joined = (P.TASK_CORE + P.COST_R2 + P.COST_NEUTRAL + P.SCHEMA_COMMON
              + P.A_BODY + P.B_SCENE_BODY + P.B_BIND_BODY).lower()
    for word in ("squash", "kabocha", "pumpkin", "clover", "purslane",
                 "mallow", "grass", "straw", "broadleaf"):
        assert word not in joined, f"prompt leaks {word!r}"


# ------------------------------------------------------------------ isolation
def test_arena_is_isolated():
    p = os.path.abspath(vlm.ARENA)
    assert os.path.isdir(p), "arena missing — run the experiment first"
    while p != "/":
        assert not os.path.exists(os.path.join(p, "CLAUDE.md")), \
            f"CLAUDE.md reachable at {p}: the run was not isolated"
        p = os.path.dirname(p)
    for root, _, files in os.walk(vlm.ARENA):
        assert "CLAUDE.md" not in files


def test_arena_holds_only_images():
    bad = [f for f in os.listdir(vlm.ARENA) if not f.endswith(".png")]
    assert not bad, f"non-image files in the arena: {bad}"


# ------------------------------------------------------- outputs, if they exist
def _label_files():
    return sorted(glob.glob(os.path.join(RES, "labels_*.json")))


@pytest.mark.skipif(not _label_files(), reason="no runs yet")
def test_every_run_covers_every_component_exactly_once():
    _, comps = load_components()
    want = set(comps)
    for f in _label_files():
        got = [l["id"] for l in json.load(open(f))["labels"]]
        assert len(got) == len(set(got)), f"{f}: duplicate ids"
        assert set(got) == want, f"{f}: missing {sorted(want - set(got))}"


@pytest.mark.skipif(not _label_files(), reason="no runs yet")
def test_no_shipped_label_carries_a_coordinate():
    """R3, on the shipped artifacts — over *model-authored* text.

    Code-authored fallback rationales are exempt and are checked separately by
    `test_fallback_rationales_are_code_authored`. They must be: a fallback
    reason legitimately cites A0's "25 px minimum reviewable region", which the
    measurement pattern reads as a length — correctly, since it is one. The
    distinction that matters for R3 is not whether a number appears anywhere in
    the file, it is whether the *model* emitted geometry.
    """
    for f in _label_files():
        for l in json.load(open(f))["labels"]:
            if l.get("fallback"):
                continue
            assert not S.scan_text(l.get("reason", ""), "hard"), (f, l)
            assert not S.scan_text(l.get("mixed_note", ""), "hard"), (f, l)
            assert set(l) - S.ALLOWED_KEYS <= {
                "r3_soft", "r3_violation", "fallback", "triaged",
                "omitted_by_model", "_cost_usd", "_wall_s", "condition",
                "rep", "raw"}


@pytest.mark.skipif(not _label_files(), reason="no runs yet")
def test_triaged_components_are_present_and_unsure():
    """Both triage tiers land on `unsure`, never on a label, in every run."""
    _, comps = load_components()
    small = {c.id for c in comps.values() if not c.core}
    for f in _label_files():
        if "baseline" in f:
            continue
        by = {l["id"]: l for l in json.load(open(f))["labels"]}
        for cid in small:
            assert by[cid]["label"] == "unsure", (f, cid)
            assert by[cid]["confidence"] == 0.0, (f, cid)


def test_the_budget_floor_is_blind_to_the_ground_truth():
    """TIER1_PX is a size cut, and size is not a label.

    A floor chosen by looking at which components are crop or weed would decide
    the experiment's own answer. This asserts the partition is a pure function
    of `px`, so no ground-truth field can have entered it.
    """
    _, comps = load_components()
    for c in comps.values():
        assert c.core == (c.px >= TIER1_PX)
        assert c.renderable == (c.px >= MIN_REVIEWABLE_PX)
    # and the tiers are nested: nothing is `core` without being `renderable`
    assert all(c.renderable for c in comps.values() if c.core)


def test_the_budget_floor_keeps_the_ground_truth_mass_it_claims_to():
    """The floor's cost, asserted rather than asserted-in-prose.

    If a future change to A4's components moves crop or weed mass below the
    floor, this fails and the FINDINGS number stops being a claim nobody checks.
    """
    _, comps = load_components()
    t = tier_report(comps)
    assert t["core_asked"]["crop_px_fraction"] > 0.99
    assert t["core_asked"]["weed_px_fraction"] > 0.99
    # every weed-majority component survives the floor
    assert t["tier2_silenced"]["truth_histogram"]["weed"] == 0


@pytest.mark.skipif(not _label_files(), reason="no runs yet")
def test_fallback_rationales_are_code_authored():
    """Every exempted rationale is one this repository wrote, not the model."""
    for f in _label_files():
        for l in json.load(open(f))["labels"]:
            if l.get("fallback"):
                assert l["reason"].startswith("[code fallback]"), (f, l)


@pytest.mark.skipif(not _label_files(), reason="no runs yet")
def test_no_shipped_run_holds_a_transport_failure():
    """The corruption that killed the first attempt cannot be in an output.

    A usage-limit notice was once cached as a model reply and scored as
    `unsure`. `vlm.is_transport_failure` is the guard; this asserts no shipped
    label carries the fingerprint of one.
    """
    for f in _label_files():
        for l in json.load(open(f))["labels"]:
            blob = f"{l.get('reason', '')} {l.get('mixed_note', '')}".lower()
            for m in vlm.TRANSPORT_MARKERS:
                assert m.lower() not in blob, (f, l["id"], m)


@pytest.mark.skipif(not _label_files(), reason="no runs yet")
def test_every_fallback_is_unsure():
    for f in _label_files():
        for l in json.load(open(f))["labels"]:
            if l.get("fallback"):
                assert l["label"] == "unsure", (f, l["id"])
