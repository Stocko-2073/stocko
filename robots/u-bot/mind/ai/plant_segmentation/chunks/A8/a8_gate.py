"""A8 — the safety gate. R2 as a data structure, not a sentence in a prompt.

    A removal requires *all* of:
      * the VLM classifies the instance as a weed with high confidence, **and**
      * the soil contact point was *observed*, not extrapolated, **and**
      * the point lies outside the keep-out volume of every keep-plant.
                                                     — RESEARCH_ROADMAP.md, R2

This module is that sentence compiled. Three properties are deliberate:

**Nothing short-circuits.** Every condition is evaluated for every instance,
even when an earlier one has already refused it, and every failure is returned.
A gate that stopped at the first failure would report `label_not_remove` for a
target that was *also* inside the crop's keep-out, and the rejection report
would then understate how many independent things had to go wrong at once. It
also means the keep-out column of the report is populated even when the
confidence floor has already refused everything, which is exactly the case on
`plants.jpeg`.

**The gate cannot be opened from outside.** `admit` is computed as the AND of
booleans that live in this module; there is no parameter that turns a condition
off, no `force` flag, and no path where a model-authored string is evaluated as
code or as a coordinate. The only tunable is the confidence floor, and raising
it can only ever *close* the gate (`test_the_floor_is_monotone`).

**A model-authored field never reaches geometry.** Labels are validated with
A7's own `schema.validate_label` on the way in — the same validator that
enforced R3 across 584 model-authored labels — and a label that fails is
discarded to `unsure` rather than patched. R3 in the direction that matters:
the semantic layer contributes an ID and a word, and nothing else.

The reason vocabulary is closed. `REASONS` is the whole of it, every rejection
carries a subset of it, and `test_every_rejection_reason_is_in_the_vocabulary`
asserts nothing else is ever emitted.
"""
from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.abspath(os.path.join(HERE, "..", "A7")))

import a8_constants as K  # noqa: E402
import schema as a7schema  # noqa: E402  (A7's R3 validator, reused unchanged)

# --------------------------------------------------------------------------
# The closed rejection vocabulary
# --------------------------------------------------------------------------

REASONS = {
    # --- the call itself -------------------------------------------------
    "metric_tool_profile_refused":
        "The tool profile carries a length in metric units. Every length in "
        "this stack is in rdu and no absolute scale exists for this image "
        "(roadmap, Known gaps #2). A8 refuses rather than converting: a "
        "fabricated scale factor would silently resize the keep-out volume.",
    # --- the semantic half (A7) ------------------------------------------
    "component_unlabelled":
        "No label was supplied for this instance id. R2 defaults to keep.",
    "label_discarded_r3":
        "The label failed A7's R3 validator (a geometric key, a coordinate or "
        "a measurement in a free-text field) and was discarded to `unsure` "
        "rather than patched.",
    "insufficient_repeats":
        "Fewer independent looks than R4 requires. A single look is not "
        "evidence: A7 measured a 20.5 % flip rate between two repeats of the "
        "shipped condition.",
    "not_unanimous":
        "The repeats disagreed about this instance. Unanimity-else-`unsure` "
        "is R4 applied to the semantic layer; A7 measured that it removes a "
        "third of the catastrophic errors for the price of one extra call.",
    "label_not_remove":
        "The unanimous label is not `remove`. Note a `keep` may mean 'this is "
        "crop' OR 'there is nothing here to cut' — A7's label vocabulary does "
        "not distinguish them and A8 must not read one as the other.",
    "confidence_below_floor":
        "The lowest confidence across the repeats is below the registered "
        "removal floor (a8_constants.REMOVAL_CONFIDENCE_FLOOR).",
    "mixed_component":
        "The instance was flagged `mixed` — it is not one plant. A `remove` "
        "inside a mixed component is a claim about a component that contains "
        "material the labeller itself said was of more than one kind, so "
        "under R2 it is refused outright.",
    # --- the geometric half (A5) -----------------------------------------
    "no_contact_point":
        "A5 emitted no defensible contact point for any part of this instance "
        "(status `occluded`). R4: no point is reported rather than one "
        "invented.",
    "contact_not_observed":
        "No contact candidate has status `observed`. An `extrapolated` point "
        "is a guess with a distance attached and R2 does not admit one.",
    "contact_not_arm_admissible":
        "A contact is `observed` but fails A5's `admissible()`: either the "
        "datum beneath it was interpolated rather than observed, or the "
        "component carries a `leaves_frame` unresolved edge and may continue "
        "outside the photograph.",
    # --- the geometric half (A6) -----------------------------------------
    "inside_keepout":
        "The point lies inside the keep-out volume of at least one keep-plant. "
        "A6's `is_inside` is conservative by default and resolves UNKNOWN "
        "(a point the camera never saw) to inside; A8 does not flip either.",
}

#: The order rejection reasons are reported in. Semantics first, geometry
#: second, because that is the order R2 states them and because it makes the
#: report readable — not because the gate evaluates them in that order. It does
#: not evaluate them in any order; it evaluates all of them.
REASON_ORDER = ("metric_tool_profile_refused", "component_unlabelled",
                "label_discarded_r3", "insufficient_repeats", "not_unanimous",
                "label_not_remove", "confidence_below_floor",
                "mixed_component", "no_contact_point", "contact_not_observed",
                "contact_not_arm_admissible", "inside_keepout")

#: How the set of keep-plants is derived from the labels.
KEEP_PLANT_POLICIES = {
    "r2_default_keep": (
        "SHIPPED. Every instance that is not unanimously `remove` is a "
        "keep-plant. This is R2 read literally: an instance the labeller was "
        "unsure about is kept, and an instance that is kept is protected. It "
        "is deliberately NOT a function of the confidence floor, so raising "
        "the floor cannot enlarge or shrink the protected region."),
    "labelled_keep_only": (
        "DIAGNOSTIC. Only instances unanimously labelled `keep` protect "
        "anything; `unsure` instances protect nothing. Reported as a "
        "sensitivity in RESULTS.md, never shipped: it makes the protected "
        "region a function of the labeller's willingness to commit."),
}


class MetricToolProfile(ValueError):
    """A tool profile that carries a length in metric units."""


METRIC_UNIT_WORDS = ("mm", "millimetre", "millimeter", "cm", "centimetre",
                     "centimeter", "m", "metre", "meter", "in", "inch",
                     "inches", "ft", "feet", "um", "micron")


@dataclass
class ToolProfile:
    """What the arm can do, in the only units this stack has.

    A6's instruction, followed literally: *"A `tool_profile` carrying a
    millimetre clearance cannot be used against this volume until C0 lands; A8
    should raise rather than convert."*
    """

    name: str
    clearance: float
    clearance_units: str = "rdu"
    positioning_repeatability: float | None = None
    note: str = ""

    @classmethod
    def parse(cls, obj: dict | None) -> "ToolProfile":
        obj = dict(obj or {})
        units = str(obj.get("clearance_units", "rdu")).strip().lower()
        if units not in ("rdu", "relative_depth_unit", "relative_depth_units"):
            raise MetricToolProfile(
                f"clearance_units={units!r}. Phase A is scale-free: every "
                "length is in rdu and there is no absolute scale for this "
                "image. Converting would require a scale factor that does not "
                "exist, so the call is refused (roadmap A1b: 'absolute scale "
                "is unresolved and stays that way').")
        for k, v in obj.items():
            if isinstance(v, str) and any(
                    v.strip().lower().endswith(u) for u in METRIC_UNIT_WORDS):
                raise MetricToolProfile(
                    f"tool_profile.{k}={v!r} carries a metric unit.")
        c = obj.get("clearance", None)
        if c is None:
            raise ValueError("tool_profile.clearance is required, in rdu")
        c = float(c)
        if not np.isfinite(c) or c < 0:
            raise ValueError("tool_profile.clearance must be finite and >= 0")
        rep = obj.get("positioning_repeatability")
        return cls(name=str(obj.get("name", "unnamed")), clearance=c,
                   clearance_units="rdu",
                   positioning_repeatability=(None if rep is None
                                              else float(rep)),
                   note=str(obj.get("note", "")))

    def effective_clearance(self) -> float:
        """Clearance plus positioning repeatability, if one was supplied.

        Both are (b) tool-geometry quantities and both widen the protected
        region; adding them is the conservative composition and is the only
        arithmetic A8 does with a tool number.
        """
        return self.clearance + (self.positioning_repeatability or 0.0)


@dataclass
class LabelVerdict:
    """What the repeats jointly say about one instance."""

    instance_id: int
    n_repeats: int = 0
    labels: list = field(default_factory=list)
    confidences: list = field(default_factory=list)
    mixed: bool = False
    unanimous: bool = False
    label: str | None = None
    min_confidence: float = 0.0
    r3_discarded: list = field(default_factory=list)
    reasons: list = field(default_factory=list)


def read_labels(records, instance_ids) -> dict:
    """Group caller-supplied label records by instance id, validating each.

    `records` is a flat list; several records may share an id, and each such
    record is one independent look (R4). A record that fails A7's R3 validator
    is *discarded*, not repaired — so it cannot contribute to unanimity and
    cannot open the gate.
    """
    known = set(int(i) for i in instance_ids)
    out = {i: LabelVerdict(instance_id=i) for i in sorted(known)}
    unknown = []
    for rec in records or []:
        try:
            rid = int(rec.get("id"))
        except (TypeError, ValueError, AttributeError):
            unknown.append(rec)
            continue
        if rid not in known:
            unknown.append(rec)
            continue
        v = out[rid]
        clean = {k: rec[k] for k in a7schema.ALLOWED_KEYS if k in rec}
        try:
            ok = a7schema.validate_label(clean, expect_id=rid)
        except Exception as e:                      # R3Violation or ValueError
            v.r3_discarded.append(f"{type(e).__name__}: {e}")
            continue
        v.n_repeats += 1
        v.labels.append(ok["label"])
        v.confidences.append(float(ok["confidence"]))
        v.mixed = v.mixed or bool(ok.get("mixed"))
    for v in out.values():
        v.unanimous = bool(v.labels) and len(set(v.labels)) == 1
        v.label = v.labels[0] if v.unanimous else None
        v.min_confidence = min(v.confidences) if v.confidences else 0.0
    return out, unknown


# --------------------------------------------------------------------------
# The gate
# --------------------------------------------------------------------------


@dataclass
class GateConfig:
    confidence_floor: float = K.REMOVAL_CONFIDENCE_FLOOR
    min_repeats: int = K.MIN_LABEL_REPEATS
    keep_plant_policy: str = "r2_default_keep"
    conservative_keepout: bool = True
    unknown_is_inside: bool = True


def keep_plants(verdicts: dict, policy: str) -> set:
    """The instances whose geometry protects the garden.

    Note what this is *not* a function of: the confidence floor. A keep-plant
    is decided by the label alone, so turning the floor up cannot shrink the
    protected region as a side effect.
    """
    if policy == "r2_default_keep":
        return {i for i, v in verdicts.items()
                if not (v.unanimous and v.label == "remove")}
    if policy == "labelled_keep_only":
        return {i for i, v in verdicts.items()
                if v.unanimous and v.label == "keep"}
    raise ValueError(f"unknown keep-plant policy {policy!r}; "
                     f"known: {sorted(KEEP_PLANT_POLICIES)}")


def run_gate(product: dict, dist, labels, tool_profile, cfg: GateConfig):
    """Evaluate every instance. Returns (targets, rejections, summary).

    `dist` is the loaded `keepout_distances.npz`. `labels` is the caller's flat
    list of label records. `tool_profile` is a dict or None.
    """
    instances = {int(i["instance_id"]): i for i in product["instances"]}
    ids = sorted(instances)
    verdicts, unknown_labels = read_labels(labels, ids)

    # ---- the tool profile, first, because it can refuse the whole call -----
    refusal = None
    try:
        tp = ToolProfile.parse(tool_profile)
        clearance = tp.effective_clearance()
    except MetricToolProfile as e:
        refusal = {"reason": "metric_tool_profile_refused", "detail": str(e)}
        tp, clearance = None, None

    D = dist["distance_rdu"]
    dist_ids = [int(x) for x in dist["instance_ids"]]
    col = {c: j for j, c in enumerate(dist_ids)}
    frame_open = {c: bool(dist["frame_open"][j]) for c, j in col.items()}
    off_frame = dist["point_off_frame"]
    bracket = float(dist["voxel_bracket_rdu"])

    kp = keep_plants(verdicts, cfg.keep_plant_policy) if refusal is None else set()

    targets, rejections = [], []
    for cid in ids:
        inst = instances[cid]
        v = verdicts[cid]
        reasons, detail = set(), {}

        # ------------------------------------------------ the semantic half
        if refusal is not None:
            reasons.add("metric_tool_profile_refused")
            detail["tool_profile"] = refusal["detail"]
        if v.n_repeats == 0:
            reasons.add("component_unlabelled")
        if v.r3_discarded:
            reasons.add("label_discarded_r3")
            detail["r3_discarded"] = v.r3_discarded
        if v.n_repeats < cfg.min_repeats:
            reasons.add("insufficient_repeats")
            detail["n_repeats"] = v.n_repeats
            detail["min_repeats"] = cfg.min_repeats
        if v.n_repeats and not v.unanimous:
            reasons.add("not_unanimous")
            detail["labels_across_repeats"] = list(v.labels)
        if not (v.unanimous and v.label == "remove"):
            reasons.add("label_not_remove")
            detail["label"] = v.label if v.unanimous else "(disagreement)"
        if v.confidences and v.min_confidence < cfg.confidence_floor:
            reasons.add("confidence_below_floor")
            detail["min_confidence"] = round(v.min_confidence, 4)
            detail["floor"] = cfg.confidence_floor
        if v.mixed:
            reasons.add("mixed_component")

        # ------------------------------------------------ the geometric half
        cands = inst["contact_candidates"]
        if not cands:
            reasons.add("no_contact_point")
            detail["a5_status"] = inst["contact_status"]
        observed = [c for c in cands if c["status"] == "observed"]
        if cands and not observed:
            reasons.add("contact_not_observed")
            detail["statuses"] = sorted({c["status"] for c in cands})
        admissible = [c for c in observed if c["arm_admissible"]]
        if observed and not admissible:
            reasons.add("contact_not_arm_admissible")

        others = sorted(kp - {cid}) if refusal is None else []
        cols = [col[o] for o in others if o in col]
        evaluated = []
        clear = []
        # A refused tool profile means there is no clearance to test against.
        # The geometry is not evaluated at all rather than evaluated at a made-up
        # number: `clearance` is None here and every candidate stays unadmitted.
        for c in (admissible if refusal is None else ()):
            row = c["row_in_distance_table"]
            if cols:
                d = D[row, cols]
                k = int(np.argmin(d))
                dmin, nearest = float(d[k]), others[k]
            else:
                dmin, nearest = float("inf"), None
            thresh = clearance + (bracket if cfg.conservative_keepout else 0.0)
            inside = dmin <= thresh
            unknown = bool(off_frame[row]) and any(
                frame_open[o] for o in others if o in frame_open)
            if unknown and cfg.unknown_is_inside:
                inside = True
            rec = {
                "contact_id": c["contact_id"],
                "split_component": c["split_component"],
                "point_xyz_rdu": c["point_xyz_rdu"],
                "point_gt_grid_xy": c["point_gt_grid_xy"],
                "status": c["status"],
                "extrapolation_distance_rdu": c["extrapolation_distance_rdu"],
                "geometry_confidence": c["geometry_confidence"],
                "material_at_point": c["material_at_point"],
                "distance_to_nearest_keep_plant_rdu":
                    None if nearest is None else round(dmin, 6),
                "nearest_keep_plant_instance": nearest,
                "inside_keepout": bool(inside),
                "point_projects_off_frame": bool(off_frame[row]),
            }
            evaluated.append(rec)
            if not inside:
                clear.append(rec)
        if admissible and not clear:
            reasons.add("inside_keepout")
            if evaluated:
                nearest = min(evaluated,
                              key=lambda r: (r["distance_to_nearest_keep_plant_rdu"]
                                             if r["distance_to_nearest_keep_plant_rdu"]
                                             is not None else 1e9))
                detail["nearest_keep_plant_instance"] = \
                    nearest["nearest_keep_plant_instance"]
                detail["distance_to_nearest_keep_plant_rdu"] = \
                    nearest["distance_to_nearest_keep_plant_rdu"]
                detail["clearance_rdu"] = clearance
                detail["voxel_bracket_rdu"] = bracket

        # -------------------------------------------------------- the verdict
        admit = not reasons and bool(clear)
        if admit:
            best = max(clear, key=lambda r: (r["geometry_confidence"] or 0.0,
                                             -r["split_component"]))
            targets.append({
                "instance_id": cid,
                "label": v.label,
                "label_confidence_min_across_repeats": round(v.min_confidence, 4),
                "n_label_repeats": v.n_repeats,
                "material_class": inst["material_class"],
                "n_px_gt_grid": inst["n_px_gt_grid"],
                "target": best,
                "alternate_points": [r for r in clear
                                     if r["contact_id"] != best["contact_id"]],
                "rejected_points_inside_keepout":
                    [r for r in evaluated if r["inside_keepout"]],
                "keep_out_clearance_rdu": clearance,
                "scale_confidence": product["scale_confidence"],
                "datum": "straw mulch surface, not soil",
                "product_target": product["product_target"],
            })
        else:
            rejections.append({
                "instance_id": cid,
                "reasons": [r for r in REASON_ORDER if r in reasons],
                "detail": detail,
                "material_class": inst["material_class"],
                "n_px_gt_grid": inst["n_px_gt_grid"],
                "n_contact_candidates": len(cands),
                "n_contact_candidates_observed": len(observed),
                "n_contact_candidates_arm_admissible": len(admissible),
                "n_contact_candidates_outside_every_keepout": len(clear),
                "best_contact": (evaluated[0] if evaluated else
                                 (cands[0] if cands else None)),
            })

    # ordering: geometric confidence, descending. Not a priority claim about
    # which weed matters most — nothing in this stack can rank that.
    targets.sort(key=lambda t: (-(t["target"]["geometry_confidence"] or 0.0),
                                t["instance_id"]))
    for r, t in enumerate(targets, 1):
        t["order"] = r

    by_reason = {}
    for rej in rejections:
        for r in rej["reasons"]:
            by_reason[r] = by_reason.get(r, 0) + 1
    summary = {
        "n_instances": len(ids),
        "n_targets_admitted": len(targets),
        "n_rejected": len(rejections),
        "rejections_by_reason": {r: by_reason[r] for r in REASON_ORDER
                                 if r in by_reason},
        "rejections_by_reason_note": (
            "Reasons are not exclusive. Every condition is evaluated for every "
            "instance and every failure is reported, so these counts sum to "
            "more than the number of rejections. That is the point: it shows "
            "how many independent conditions had to fail together."),
        "n_keep_plants": len(kp),
        "keep_plant_policy": cfg.keep_plant_policy,
        "keep_plant_policy_note": KEEP_PLANT_POLICIES[cfg.keep_plant_policy],
        "confidence_floor": cfg.confidence_floor,
        "min_label_repeats": cfg.min_repeats,
        "clearance_rdu": clearance,
        "unlabelled_ids_supplied_by_caller": len(unknown_labels),
        "refusal": refusal,
    }
    return targets, rejections, summary
