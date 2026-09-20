"""A8 — the two tools, their schemas, and nothing else.

`segment_garden` and `plan_removals` are deliberately split at the R3 line:

    segment_garden(image, depth, intrinsics)  ->  geometry, no semantics
    plan_removals(labels, tool_profile)       ->  semantics meets geometry,
                                                  in code, after the fact

`segment_garden` returns no crop flag it decided itself. It cannot: nothing in
A1-A6 knows which plant is the crop, and the roadmap's own architecture puts
that decision in a VLM that sees the instance *ids* this tool emits. So the
`crop` field is present and `null`, with `crop_source` saying who fills it in.
That is a deviation from the roadmap's wording ("a list of instances, each with
ID, crop, ...") and it is recorded as one in FINDINGS.md, because the
alternative is a tool that launders A0's ground truth into a runtime answer.

Both tools are pure functions of products on disk. Neither runs a model,
neither touches the network, and neither can move anything: `plan_removals`
ends at a target list, as the roadmap requires.
"""
from __future__ import annotations

import json
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import a8_common as C  # noqa: E402
import a8_constants as K  # noqa: E402
import a8_gate as G  # noqa: E402

DEFAULT_IMAGE = os.path.join(C.ROOT, "plants.jpeg")
DEFAULT_DEPTH = os.path.join(C.ROOT, "chunks", "A1", "depth",
                             "da3nested-giant-large_res1344")

# --------------------------------------------------------------------------
# Schemas (JSON Schema draft 2020-12 subset; what MCP `inputSchema` accepts)
# --------------------------------------------------------------------------

SEGMENT_GARDEN_INPUT = {
    "type": "object",
    "properties": {
        "image": {
            "type": "string",
            "description":
                "Path to the RGB photograph. Phase A has products for exactly "
                "one image (plants.jpeg); any other path is refused rather "
                "than answered from the wrong products (R4)."},
        "depth": {
            "type": "string",
            "description":
                "Path to the A1 float depth product directory. Optional; "
                "defaults to the A1 primary raster that A2, A4, A5 and A6 all "
                "used. A different raster is refused, not resampled."},
        "intrinsics": {
            "type": ["object", "null"],
            "description":
                "Camera intrinsics {fx, fy, cx, cy, width, height}. Optional. "
                "This image has no EXIF and its camera is not available, so "
                "the shipped geometry uses A1's model-estimated camera and "
                "every output is flagged scale_free. Supplying intrinsics that "
                "differ from A1's is refused: honouring them would mean "
                "rebuilding A2-A6, and silently ignoring them would be worse.",
            "properties": {
                "fx": {"type": "number"}, "fy": {"type": "number"},
                "cx": {"type": "number"}, "cy": {"type": "number"},
                "width": {"type": "integer"}, "height": {"type": "integer"}},
            "additionalProperties": False},
        "include_contact_candidates": {
            "type": "boolean",
            "description":
                "Include every split-component contact candidate per instance "
                "(530 in total). Default true. False returns only the "
                "designated contact point per instance and a much smaller "
                "document.",
            "default": True},
    },
    "required": ["image"],
    "additionalProperties": False,
}

PLAN_REMOVALS_INPUT = {
    "type": "object",
    "properties": {
        "labels": {
            "type": "array",
            "description":
                "Per-instance VLM labels. One record per (instance, look): "
                "supply the SAME id more than once to give the gate more than "
                "one independent look, which is what R4 asks for and what the "
                "unanimity condition tests. Records are validated with A7's R3 "
                "validator; a record carrying a coordinate, a bounding box or "
                "a measurement is discarded to `unsure`, never repaired.",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "integer",
                           "description": "An instance_id from segment_garden."},
                    "label": {"type": "string",
                              "enum": ["keep", "remove", "unsure"]},
                    "confidence": {"type": "number",
                                   "minimum": 0.0, "maximum": 1.0},
                    "reason": {"type": "string"},
                    "mixed": {"type": "boolean",
                              "description":
                                  "True if this instance holds more than one "
                                  "kind of plant. A `remove` on a mixed "
                                  "instance is refused outright."},
                },
                "required": ["id", "label", "confidence", "reason"],
                "additionalProperties": False}},
        "tool_profile": {
            "type": "object",
            "description":
                "The weeding tool. Every length is in rdu. A metric clearance "
                "is REFUSED, not converted: there is no absolute scale for "
                "this image and inventing one would resize the keep-out "
                "volume by an unknown factor.",
            "properties": {
                "name": {"type": "string"},
                "clearance": {"type": "number", "minimum": 0.0},
                "clearance_units": {"type": "string", "default": "rdu"},
                "positioning_repeatability": {"type": ["number", "null"]},
                "note": {"type": "string"}},
            "required": ["clearance"],
            "additionalProperties": False},
        "confidence_floor": {
            "type": "number", "minimum": 0.0, "maximum": 1.0,
            "description":
                "Override the registered removal floor "
                f"({K.REMOVAL_CONFIDENCE_FLOOR}). Raising it can only close "
                "the gate further; lowering it is a diagnostic and every "
                "output records the floor it was produced at."},
        "min_label_repeats": {
            "type": "integer", "minimum": 1,
            "description":
                f"Independent looks required before a `remove` is considered "
                f"(default {K.MIN_LABEL_REPEATS}, R4)."},
        "keep_plant_policy": {
            "type": "string",
            "enum": sorted(G.KEEP_PLANT_POLICIES),
            "description":
                "How keep-plants are derived from the labels. "
                + " | ".join(f"{k}: {v}" for k, v in
                             sorted(G.KEEP_PLANT_POLICIES.items()))},
        "include_rejections": {
            "type": "boolean", "default": True,
            "description":
                "Return the full rejection report (one record per rejected "
                "instance with every reason that applied). Default true; the "
                "roadmap requires it and turning it off hides the gate's "
                "dominant behaviour."},
    },
    "required": ["labels", "tool_profile"],
    "additionalProperties": False,
}


# --------------------------------------------------------------------------
# Loading the precomputed products
# --------------------------------------------------------------------------

_CACHE: dict = {}


def load_products(products_dir: str | None = None):
    d = products_dir or C.PRODUCTS
    if d not in _CACHE:
        with open(os.path.join(d, "segment_garden_plants.json")) as f:
            doc = json.load(f)
        dist = dict(np.load(os.path.join(d, "keepout_distances.npz")))
        _CACHE[d] = (doc, dist)
    return _CACHE[d]


class ToolRefusal(ValueError):
    """A refusal the caller must see. Never converted into a plausible answer."""


# --------------------------------------------------------------------------
# Tool 1 — segment_garden
# --------------------------------------------------------------------------


def segment_garden(image: str, depth: str | None = None,
                   intrinsics: dict | None = None,
                   include_contact_candidates: bool = True,
                   products_dir: str | None = None) -> dict:
    doc, _ = load_products(products_dir)
    if os.path.abspath(image) != os.path.abspath(DEFAULT_IMAGE):
        raise ToolRefusal(
            f"A8 has products for exactly one image ({DEFAULT_IMAGE}). "
            f"{image!r} is refused rather than answered from another image's "
            "geometry. Generalisation beyond one image is chunk B1 and it is "
            "blocked on a capture protocol, not on this tool.")
    if depth is not None and os.path.abspath(depth) != os.path.abspath(DEFAULT_DEPTH):
        raise ToolRefusal(
            f"the shipped geometry is built on the A1 primary raster "
            f"({DEFAULT_DEPTH}), unresampled, and A2/A4/A5/A6 all used it. "
            f"{depth!r} would need the whole stack rebuilt; A8 refuses rather "
            "than mixing rasters.")
    cam = doc["soil_surface"]["camera"]
    if intrinsics:
        for k in ("fx", "fy", "cx", "cy"):
            if k in intrinsics and abs(float(intrinsics[k]) - float(cam[k])) > 1e-6:
                raise ToolRefusal(
                    f"intrinsics.{k}={intrinsics[k]} differs from the camera "
                    f"the shipped geometry was built with ({cam[k]}, "
                    f"provenance {cam.get('provenance')!r}). This image has no "
                    "EXIF and its camera is unavailable, so the focal length "
                    "is an assumption and A1b is what bounds it. A8 refuses to "
                    "relabel existing geometry with a different camera.")

    out = {k: doc[k] for k in ("chunk", "tool", "scale_confidence", "units",
                               "DATUM", "product_target", "instance_id_space",
                               "soil_surface", "provenance")}
    out["image"] = os.path.abspath(image)
    out["n_instances"] = len(doc["instances"])
    keys = ("instance_id", "crop", "crop_source", "material_class",
            "material_composition_fraction", "height_above_datum",
            "n_px_gt_grid", "n_px_depth_grid", "n_split_children",
            "contact_point", "contact_status", "n_contact_candidates",
            "n_contact_candidates_arm_admissible", "keep_out",
            "unresolved_edges", "split_children_without_a_point")
    inst = []
    for i in doc["instances"]:
        r = {k: i[k] for k in keys}
        cp = r.get("contact_point")
        r["extrapolation_distance_rdu"] = (
            cp["extrapolation_distance_rdu"] if cp else None)
        r["geometry_confidence"] = cp["geometry_confidence"] if cp else None
        r["geometry_confidence_note"] = (
            "An ordering, not a probability (A5). Nothing in this image could "
            "calibrate it. The safety field is `contact_status`.")
        if include_contact_candidates:
            r["contact_candidates"] = i["contact_candidates"]
        inst.append(r)
    out["instances"] = inst
    out["caveats"] = [
        "The datum is the straw mulch surface. `observed` means the material "
        "reaches the STRAW, not the soil. A0 found zero `visible` stem-soil "
        "contacts in this photograph and A5 could not invent one, so any "
        "contact-point error quoted for this image without the "
        "`estimated`/`under_straw` caveat is wrong.",
        "`contact_status` is the safety field. `geometry_confidence` is an "
        "ordering and must not be used as a licence to remove anything.",
        "Every length is in rdu. There is no metre in this product.",
        "An instance is a connected piece of observed material, not a proof of "
        "a plant. `unresolved_edges` counts the links A4 refused to decide.",
        "A6 measured that 86.9 % of A5's `observed` contacts stand on a pixel "
        "A2 fitted its datum to, so `observed` is partly circular; the honest "
        "reading is 'the lowest material is indistinguishable from the mulch'.",
    ]
    return out


# --------------------------------------------------------------------------
# Tool 2 — plan_removals
# --------------------------------------------------------------------------


def plan_removals(labels, tool_profile, confidence_floor: float | None = None,
                  min_label_repeats: int | None = None,
                  keep_plant_policy: str = "r2_default_keep",
                  include_rejections: bool = True,
                  conservative_keepout: bool = True,
                  unknown_is_inside: bool = True,
                  products_dir: str | None = None) -> dict:
    doc, dist = load_products(products_dir)
    cfg = G.GateConfig(
        confidence_floor=(K.REMOVAL_CONFIDENCE_FLOOR if confidence_floor is None
                          else float(confidence_floor)),
        min_repeats=(K.MIN_LABEL_REPEATS if min_label_repeats is None
                     else int(min_label_repeats)),
        keep_plant_policy=keep_plant_policy,
        conservative_keepout=conservative_keepout,
        unknown_is_inside=unknown_is_inside)
    targets, rejections, summary = G.run_gate(doc, dist, labels, tool_profile,
                                              cfg)
    out = {
        "chunk": "A8",
        "tool": "plan_removals",
        "scale_confidence": doc["scale_confidence"],
        "units": doc["units"],
        "DATUM": doc["DATUM"],
        "product_target": doc["product_target"],
        "ends_at": ("a target list. No motion is planned, ordered or commanded "
                    "here, and nothing in this module can move anything."),
        "summary": summary,
        "targets": targets,
        "rejection_reason_vocabulary": G.REASONS,
    }
    if include_rejections:
        out["rejections"] = rejections
    if cfg.confidence_floor != K.REMOVAL_CONFIDENCE_FLOOR:
        out["floor_override"] = {
            "registered_floor": K.REMOVAL_CONFIDENCE_FLOOR,
            "floor_used": cfg.confidence_floor,
            "warning": ("This run did not use the registered removal floor. "
                        "It is a diagnostic, not a shippable target list.")}
    return out


TOOLS = {
    "segment_garden": {
        "description":
            "Segment one garden photograph into plant instances against a "
            "measured soil (straw) surface, and return, per instance: id, "
            "material class, height statistics above the datum, a contact "
            "point with an honest status (observed / extrapolated / occluded), "
            "extrapolation distance, geometry confidence and a keep-out "
            "volume descriptor. Emits NO crop/weed judgement and no semantic "
            "opinion of any kind — that is the caller's job, and the caller "
            "gets instance ids to label, never coordinates (R3). Every length "
            "is in relative depth units; this image has no absolute scale.",
        "inputSchema": SEGMENT_GARDEN_INPUT,
        "fn": segment_garden,
    },
    "plan_removals": {
        "description":
            "Given per-instance keep/remove/unsure labels and a tool profile, "
            "return an ordered target list plus a rejection report. A target "
            "is admitted ONLY when the label is unanimously `remove` across "
            "the required number of independent looks, at or above the "
            "registered confidence floor, on an instance not flagged `mixed`, "
            "with a contact point A5 statused `observed` and marked "
            "arm-admissible, lying outside the keep-out volume of every "
            "keep-plant. Every one of those conditions is evaluated in code "
            "for every instance and every failure is returned with its "
            "specific reason. Ends at a target list: no motion is planned.",
        "inputSchema": PLAN_REMOVALS_INPUT,
        "fn": plan_removals,
    },
}


def call_tool(name: str, arguments: dict) -> dict:
    if name not in TOOLS:
        raise ToolRefusal(f"unknown tool {name!r}; "
                          f"this server exposes {sorted(TOOLS)}")
    return TOOLS[name]["fn"](**(arguments or {}))
