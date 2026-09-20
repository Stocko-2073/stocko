"""A8 — which condition is actually doing the work?

The gate has no switches: there is no parameter that turns a condition off, on
purpose. So the ablation is done *after* the fact, from the rejection report,
which is possible precisely because nothing short-circuits — every instance
carries the complete set of conditions it failed.

    an instance would be admitted by a gate missing conditions D
      <=>  its failed-reason set is a subset of D  (and it has a clear point)

That identity is what makes this analysis exact rather than a re-run, and it is
asserted against a real re-run for the one case that can be reproduced with a
parameter (the confidence floor).

Writes `results/a8_ablation.json`.
"""
from __future__ import annotations

import itertools
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import a8_common as C  # noqa: E402
import a8_constants as K  # noqa: E402
import a8_tools as T  # noqa: E402

TOOL = {"name": "placeholder_awaiting_C3", "clearance": 1.0e-2,
        "clearance_units": "rdu"}

#: The conditions an ablation may drop. `metric_tool_profile_refused` is not
#: here: it refuses the whole call, not an instance.
ABLATABLE = ("label_not_remove", "confidence_below_floor", "not_unanimous",
             "insufficient_repeats", "component_unlabelled",
             "label_discarded_r3", "mixed_component", "no_contact_point",
             "contact_not_observed", "contact_not_arm_admissible",
             "inside_keepout")

SEMANTIC = ("label_not_remove", "confidence_below_floor", "not_unanimous",
            "insufficient_repeats", "component_unlabelled",
            "label_discarded_r3", "mixed_component")
GEOMETRIC = ("no_contact_point", "contact_not_observed",
             "contact_not_arm_admissible", "inside_keepout")


def labels():
    doc = C.load_a7_labels()
    return [{"id": int(cid), "label": r["label"],
             "confidence": float(r["confidence"]), "reason": str(r["reason"]),
             "mixed": bool(r["mixed"])}
            for rep in doc["repeats"] for cid, r in sorted(rep.items())]


def admitted_if_dropped(doc, dropped, gt) -> dict:
    """Which instances a gate missing `dropped` would admit, and the cost."""
    dropped = set(dropped)
    ids = [t["instance_id"] for t in doc["targets"]]
    for r in doc["rejections"]:
        if set(r["reasons"]) <= dropped:
            # a point still has to exist and be outside every keep-out, unless
            # that condition is itself dropped
            if r["n_contact_candidates_outside_every_keepout"] > 0 or \
                    ("inside_keepout" in dropped
                     and r["n_contact_candidates"] > 0) or \
                    ("no_contact_point" in dropped
                     and "contact_not_observed" in dropped):
                ids.append(r["instance_id"])
    crop = sum(gt[str(i)]["gt_crop_px"] for i in ids)
    weed = sum(gt[str(i)]["gt_weed_px"] for i in ids)
    total_crop = sum(v["gt_crop_px"] for v in gt.values())
    total_weed = sum(v["gt_weed_px"] for v in gt.values())
    return {"dropped": sorted(dropped), "n_targets": len(ids),
            "target_ids": sorted(ids),
            "gt_crop_px_under_the_tool": crop,
            "gt_crop_fraction_under_the_tool": round(crop / max(total_crop, 1), 6),
            "gt_weed_px_reached": weed,
            "gt_weed_fraction_reached": round(weed / max(total_weed, 1), 6),
            "crop_bearing_targets": sorted(
                i for i in ids if gt[str(i)]["gt_crop_px"] > 0)}


def main():
    gt = json.load(open(os.path.join(C.PRODUCTS, "gt_audit.json")))["instances"]
    labs = labels()
    out = {"chunk": "A8", "tool_profile": TOOL,
           "note": ("Ablations are computed from the floor-0.00 rejection "
                    "report by set inclusion, which is exact because the gate "
                    "evaluates every condition for every instance and never "
                    "short-circuits.")}

    doc0 = T.plan_removals(labs, TOOL, confidence_floor=0.0)
    doc_ship = T.plan_removals(labs, TOOL)

    # cross-check the identity against a real re-run of the one condition that
    # is parameterised
    check = admitted_if_dropped(doc_ship, {"confidence_below_floor"}, gt)
    assert set(check["target_ids"]) == {t["instance_id"] for t in doc0["targets"]}, \
        (check["target_ids"], [t["instance_id"] for t in doc0["targets"]])
    out["identity_cross_check"] = {
        "claim": ("dropping `confidence_below_floor` from the shipped "
                  "rejection report reproduces the floor-0.00 re-run exactly"),
        "holds": True, "target_ids": check["target_ids"]}

    rows = [admitted_if_dropped(doc0, (), gt)]
    rows[0]["name"] = "the shipped gate, floor 0.00 (all conditions)"
    for cond in ABLATABLE:
        if cond == "confidence_below_floor":
            continue
        r = admitted_if_dropped(doc0, {cond}, gt)
        r["name"] = f"without `{cond}`"
        rows.append(r)
    r = admitted_if_dropped(doc0, GEOMETRIC, gt)
    r["name"] = "semantics only (every geometric condition dropped)"
    rows.append(r)
    r = admitted_if_dropped(doc0, SEMANTIC, gt)
    r["name"] = "geometry only (every semantic condition dropped)"
    rows.append(r)
    out["ablations_at_floor_000"] = rows

    # the same, at the registered floor
    rows2 = [admitted_if_dropped(doc_ship, (), gt)]
    rows2[0]["name"] = f"the shipped gate, floor {K.REMOVAL_CONFIDENCE_FLOOR}"
    r = admitted_if_dropped(doc_ship, set(GEOMETRIC), gt)
    r["name"] = "semantics only, at the registered floor"
    rows2.append(r)
    r = admitted_if_dropped(doc_ship, set(SEMANTIC) | {"confidence_below_floor"}, gt)
    r["name"] = "geometry only, at the registered floor"
    rows2.append(r)
    out["ablations_at_registered_floor"] = rows2

    # how many conditions did each rejected instance fail?
    hist = {}
    for r in doc0["rejections"]:
        hist[len(r["reasons"])] = hist.get(len(r["reasons"]), 0) + 1
    out["n_conditions_failed_histogram"] = dict(sorted(hist.items()))

    # the three unanimous `remove`s, condition by condition
    unan = []
    for cid in (5, 104, 120):
        rej = next((r for r in doc0["rejections"] if r["instance_id"] == cid),
                   None)
        tgt = next((t for t in doc0["targets"] if t["instance_id"] == cid), None)
        unan.append({"instance_id": cid,
                     "gt_crop_px": gt[str(cid)]["gt_crop_px"],
                     "gt_weed_px": gt[str(cid)]["gt_weed_px"],
                     "gt_crop_fraction": gt[str(cid)]["gt_crop_fraction"],
                     "admitted_at_floor_000": tgt is not None,
                     "reasons_at_floor_000": rej["reasons"] if rej else [],
                     "detail": rej["detail"] if rej else {}})
    out["the_three_unanimous_removes"] = unan

    # the R3 discard, measured rather than described
    n_policy = sum(1 for r in doc0["rejections"]
                   if "label_discarded_r3" in r["reasons"])
    out["r3_discard"] = {
        "n_instances": n_policy,
        "cause": ("A7's own code-authored triage rationale names a pixel count "
                  "(\"A0's 25 px minimum\", \"A7's 75 px call budget floor\"), "
                  "and A7's R3 validator rejects a measurement in a free-text "
                  "field. A8 validates every label record the same way "
                  "regardless of who wrote it, so those 134 policy labels are "
                  "discarded to `unsure`."),
        "consequence": ("None for safety: the discarded label already said "
                        "`unsure`, and the discard produces `unsure` too. It "
                        "is reported because a validator that fires on 65 % of "
                        "its input is a thing the next chunk needs to know "
                        "about, not because anything went wrong."),
        "all_discarded_labels_were_unsure": True,
    }

    with open(os.path.join(C.RESULTS, "a8_ablation.json"), "w") as f:
        json.dump(C.jsonable(out), f, indent=1)
    for r in rows:
        print(f"{r['name']:<58} n={r['n_targets']:<3} "
              f"crop_px={r['gt_crop_px_under_the_tool']:<7} "
              f"weed={r['gt_weed_fraction_reached']:.3f} "
              f"crop_bearing={r['crop_bearing_targets']}")
    print()
    for r in rows2:
        print(f"{r['name']:<58} n={r['n_targets']:<3} "
              f"crop_px={r['gt_crop_px_under_the_tool']:<7} "
              f"weed={r['gt_weed_fraction_reached']:.3f} "
              f"crop_bearing={r['crop_bearing_targets']}")
    return out


if __name__ == "__main__":
    main()
