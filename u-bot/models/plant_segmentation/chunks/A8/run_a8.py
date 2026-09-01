"""A8 — the end-to-end run on `plants.jpeg`, through the MCP server.

Everything below goes over the wire. `client.StdioClient` starts `server.py` in
a subprocess and talks JSON-RPC to it over pipes; this script never imports
`a8_tools`. "Callable as an MCP tool" is therefore a thing that was done, not a
thing that was claimed.

Produces
--------
* `products/target_list.json`      — the shipped run, at the registered floor.
* `products/rejection_report.json` — every rejected instance, every reason.
* `products/target_list_floor000_diagnostic.json` — the same gate with the
  confidence floor removed, so the geometric half is visible. Clearly labelled;
  not a shippable target list.
* `results/a8_scores.json`         — the sweeps and the A0 audit.

Run:  chunks/A3/.venv/bin/python chunks/A8/run_a8.py
"""
from __future__ import annotations

import json
import os
import sys
import time

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import a8_common as C  # noqa: E402
import a8_constants as K  # noqa: E402
from client import StdioClient  # noqa: E402

IMAGE = os.path.join(C.ROOT, "plants.jpeg")

#: The tool profile the shipped run uses. Both numbers are A6's, in rdu, and
#: both are placeholders awaiting C3 — A8 introduces no tool constant of its
#: own. `positioning_repeatability` is left null because no actuator exists to
#: measure one, and inventing a second (b) placeholder would be worse than
#: carrying one honestly.
TOOL_PROFILE = {
    "name": "placeholder_awaiting_C3",
    "clearance": 1.0e-2,
    "clearance_units": "rdu",
    "positioning_repeatability": None,
    "note": ("A6's DEFAULT_CLEARANCE_RDU (1.83 A2 datum-sigma), category (b) "
             "tool geometry, PLACEHOLDER awaiting C3. A6 swept it over two "
             "decades: crop coverage moves 0.56 points, weed shielding moves "
             "14. The number decides how much of the bed the robot may touch, "
             "not whether the crop is protected."),
}

CLEARANCE_SWEEP = (0.0, 1.0e-3, 2.0e-3, 5.0e-3, 1.0e-2, 2.0e-2, 5.0e-2)


def a7_labels_as_tool_input():
    """A7's two shipped repeats, flattened into `plan_removals`' label list.

    Both repeats are passed, one record each, with the same id — which is how
    the caller gives the gate two independent looks. Nothing is voted here;
    unanimity is the gate's job and testing it is the point.
    """
    doc = C.load_a7_labels()
    recs = []
    for rep in doc["repeats"]:
        for cid, r in sorted(rep.items()):
            recs.append({"id": int(cid), "label": r["label"],
                         "confidence": float(r["confidence"]),
                         "reason": str(r["reason"]),
                         "mixed": bool(r["mixed"])})
    return recs, doc["provenance"]


# --------------------------------------------------------------------------
# A0 audit — the only place ground truth is allowed to appear
# --------------------------------------------------------------------------


def audit(plan: dict, gt_audit: dict, gt) -> dict:
    """Score the gate's output against A0. R2's question, asked directly:
    did any admitted target put ground-truth crop under the tool?"""
    a = gt_audit["instances"]
    crop_admitted, detail = [], []
    for t in plan["targets"]:
        cid = str(t["instance_id"])
        g = a.get(cid, {})
        x, y = t["target"]["point_gt_grid_xy"]
        gi = int(gt.instances[int(round(y)), int(round(x))])
        gm = int(gt.material[int(round(y)), int(round(x))])
        row = {"instance_id": t["instance_id"],
               "gt_crop_px_in_instance": g.get("gt_crop_px", 0),
               "gt_weed_px_in_instance": g.get("gt_weed_px", 0),
               "gt_crop_fraction": g.get("gt_crop_fraction", 0.0),
               "crop_majority": g.get("crop_majority", False),
               "gt_instance_at_contact_point": gi,
               "gt_material_at_contact_point": gm,
               "gt_instance_names": g.get("gt_instance_px", {})}
        detail.append(row)
        if row["gt_crop_px_in_instance"] > 0 or gi == 1:
            crop_admitted.append(row)
    total_crop = sum(v["gt_crop_px"] for v in a.values())
    at_risk = sum(a.get(str(t["instance_id"]), {}).get("gt_crop_px", 0)
                  for t in plan["targets"])
    total_weed = sum(v["gt_weed_px"] for v in a.values())
    reached = sum(a.get(str(t["instance_id"]), {}).get("gt_weed_px", 0)
                  for t in plan["targets"])
    return {
        "n_targets": len(plan["targets"]),
        "n_targets_touching_gt_crop": len(crop_admitted),
        "no_gt_crop_point_admitted": len(crop_admitted) == 0,
        "gt_crop_px_under_the_tool": at_risk,
        "gt_crop_px_total": total_crop,
        "gt_crop_fraction_under_the_tool": round(at_risk / max(total_crop, 1), 6),
        "gt_weed_px_reached": reached,
        "gt_weed_px_total": total_weed,
        "gt_weed_fraction_reached": round(reached / max(total_weed, 1), 6),
        "per_target": detail,
        "note": ("'crop px under the tool' counts every ground-truth crop "
                 "pixel inside an admitted instance, which is A7's own "
                 "threshold-free metric. It is an upper bound on the damage: "
                 "a target is one point, not the whole instance."),
    }


def gt_weed_rollcall(plan: dict, gt, merge_components) -> list:
    """A6 §6's gate rehearsal, now run for real.

    A6 predicted the gate would refuse 6 of the 9 ground-truth weeds at the
    placeholder clearance and 4 of 9 at zero clearance, and asked A8 to report
    that as *rejections with reasons* rather than as a bug. This is that table:
    one row per ground-truth weed, the instance the gate actually decided about,
    and what it decided.
    """
    admitted = {t["instance_id"] for t in plan["targets"]}
    rej = {r["instance_id"]: r for r in plan.get("rejections", [])}
    rows = []
    for inst in gt.contacts["instances"]:
        if inst.get("crop"):
            continue
        gid = int(inst["id"])
        mask = gt.instances == gid
        vals, cnt = np.unique(merge_components[mask], return_counts=True)
        keep = vals > 0
        cid = int(vals[keep][np.argmax(cnt[keep])]) if keep.any() else 0
        x, y = inst["point"]
        at_pt = int(merge_components[int(y), int(x)])
        rows.append({
            "gt_instance": gid, "name": inst["name"],
            "gt_contact_status": inst["status"],
            "gt_localisation": inst["localisation"],
            "merge_instance_by_overlap": cid,
            "merge_instance_at_gt_contact_point": at_pt,
            "admitted": cid in admitted,
            "reasons": rej.get(cid, {}).get("reasons", []),
            "detail": rej.get(cid, {}).get("detail", {}),
        })
    return rows


def main():
    t0 = time.time()
    os.makedirs(C.RESULTS, exist_ok=True)
    labels, label_prov = a7_labels_as_tool_input()
    gt_audit = json.load(open(os.path.join(C.PRODUCTS, "gt_audit.json")))
    import eval as a0eval
    gt = a0eval.load_gt()

    out = {"chunk": "A8", "date": "2026-09-01",
           "label_provenance": label_prov,
           "tool_profile": TOOL_PROFILE,
           "registered_floor": K.REMOVAL_CONFIDENCE_FLOOR,
           "min_label_repeats": K.MIN_LABEL_REPEATS}

    with StdioClient() as cli:
        out["server_info"] = cli.server_info
        tools = cli.list_tools()
        out["tools"] = [{"name": t["name"],
                         "n_schema_properties":
                             len(t["inputSchema"]["properties"]),
                         "required": t["inputSchema"].get("required", [])}
                        for t in tools]
        print("tools/list ->", [t["name"] for t in tools])

        # ---------------- segment_garden -----------------------------------
        seg = cli.call_ok("segment_garden", {"image": IMAGE})
        print(f"segment_garden -> {seg['n_instances']} instances")
        out["segment_garden"] = {
            "n_instances": seg["n_instances"],
            "scale_confidence": seg["scale_confidence"],
            "soil_surface": seg["soil_surface"],
            "contact_status_counts": _counts(
                i["contact_status"] for i in seg["instances"]),
            "n_instances_with_an_admissible_contact": sum(
                1 for i in seg["instances"]
                if i["n_contact_candidates_arm_admissible"] > 0),
            "n_contact_candidates_total": sum(
                i["n_contact_candidates"] for i in seg["instances"]),
            "crop_flags_emitted": _counts(str(i["crop"]) for i in seg["instances"]),
        }
        # refusals are part of the contract, so they are exercised here
        out["refusals"] = {}
        for name, args in (
                ("other_image", {"image": os.path.join(C.ROOT, "nope.jpeg")}),
                ("other_intrinsics", {"image": IMAGE,
                                      "intrinsics": {"fx": 3005.0}})):
            _, is_err, text = cli.call("segment_garden", args)
            out["refusals"][name] = {"isError": is_err, "text": text[:200]}
            assert is_err, name

        # ---------------- plan_removals, shipped ---------------------------
        plan = cli.call_ok("plan_removals", {
            "labels": labels, "tool_profile": TOOL_PROFILE})
        _write("target_list.json", {
            k: v for k, v in plan.items() if k != "rejections"})
        _write("rejection_report.json", {
            "chunk": "A8", "tool": "plan_removals",
            "summary": plan["summary"],
            "rejection_reason_vocabulary": plan["rejection_reason_vocabulary"],
            "rejections": plan["rejections"]})
        merge_components = np.load(os.path.join(
            C.ROOT, "chunks", "A4", "products",
            "components_gt_grid_merge.npy"))
        out["shipped"] = {"summary": plan["summary"],
                          "targets": plan["targets"],
                          "audit_vs_A0": audit(plan, gt_audit, gt),
                          "gt_weed_rollcall": gt_weed_rollcall(
                              plan, gt, merge_components)}
        print("shipped:", plan["summary"]["n_targets_admitted"], "targets;",
              plan["summary"]["rejections_by_reason"])

        # ---------------- diagnostic: the floor removed --------------------
        diag = cli.call_ok("plan_removals", {
            "labels": labels, "tool_profile": TOOL_PROFILE,
            "confidence_floor": 0.0})
        _write("target_list_floor000_diagnostic.json",
               {k: v for k, v in diag.items() if k != "rejections"})
        out["diagnostic_floor_000"] = {
            "summary": diag["summary"], "targets": diag["targets"],
            "audit_vs_A0": audit(diag, gt_audit, gt),
            "gt_weed_rollcall": gt_weed_rollcall(diag, gt, merge_components)}
        print("floor 0.00:", diag["summary"]["n_targets_admitted"], "targets")

        # ---------------- sweeps -------------------------------------------
        out["sweep_confidence_floor"] = []
        for f in K.CONFIDENCE_FLOOR_SWEEP:
            p = cli.call_ok("plan_removals", {
                "labels": labels, "tool_profile": TOOL_PROFILE,
                "confidence_floor": f, "include_rejections": False})
            au = audit(p, gt_audit, gt)
            out["sweep_confidence_floor"].append({
                "floor": f, "n_targets": len(p["targets"]),
                "target_ids": [t["instance_id"] for t in p["targets"]],
                "gt_crop_px_under_the_tool": au["gt_crop_px_under_the_tool"],
                "gt_crop_fraction_under_the_tool":
                    au["gt_crop_fraction_under_the_tool"],
                "gt_weed_fraction_reached": au["gt_weed_fraction_reached"],
                "no_gt_crop_point_admitted": au["no_gt_crop_point_admitted"]})

        out["sweep_clearance"] = []
        for c in CLEARANCE_SWEEP:
            tp = dict(TOOL_PROFILE, clearance=c)
            for floor, tag in ((K.REMOVAL_CONFIDENCE_FLOOR, "registered"),
                               (0.0, "floor_000_diagnostic")):
                p = cli.call_ok("plan_removals", {
                    "labels": labels, "tool_profile": tp,
                    "confidence_floor": floor, "include_rejections": False})
                au = audit(p, gt_audit, gt)
                out["sweep_clearance"].append({
                    "clearance_rdu": c, "floor": tag,
                    "n_targets": len(p["targets"]),
                    "target_ids": [t["instance_id"] for t in p["targets"]],
                    "gt_crop_px_under_the_tool": au["gt_crop_px_under_the_tool"],
                    "gt_weed_fraction_reached": au["gt_weed_fraction_reached"],
                    "no_gt_crop_point_admitted":
                        au["no_gt_crop_point_admitted"]})

        out["sweep_keep_plant_policy"] = []
        for pol in ("r2_default_keep", "labelled_keep_only"):
            for floor, tag in ((K.REMOVAL_CONFIDENCE_FLOOR, "registered"),
                               (0.0, "floor_000_diagnostic")):
                p = cli.call_ok("plan_removals", {
                    "labels": labels, "tool_profile": TOOL_PROFILE,
                    "keep_plant_policy": pol, "confidence_floor": floor,
                    "include_rejections": False})
                au = audit(p, gt_audit, gt)
                out["sweep_keep_plant_policy"].append({
                    "policy": pol, "floor": tag,
                    "n_keep_plants": p["summary"]["n_keep_plants"],
                    "n_targets": len(p["targets"]),
                    "target_ids": [t["instance_id"] for t in p["targets"]],
                    "gt_crop_px_under_the_tool": au["gt_crop_px_under_the_tool"],
                    "gt_weed_fraction_reached": au["gt_weed_fraction_reached"],
                    "no_gt_crop_point_admitted":
                        au["no_gt_crop_point_admitted"]})

        # ---------------- single-look ablation (R4) ------------------------
        one_look = [r for r in labels[:len(labels) // 2]]
        p = cli.call_ok("plan_removals", {
            "labels": one_look, "tool_profile": TOOL_PROFILE,
            "confidence_floor": 0.0, "include_rejections": False})
        out["ablation_one_look"] = {
            "n_label_records": len(one_look),
            "n_targets": len(p["targets"]),
            "rejections_insufficient_repeats":
                p["summary"]["rejections_by_reason"].get("insufficient_repeats"),
            "note": ("Repeat 1 only. Every instance is refused for "
                     "`insufficient_repeats`: R4 is structural, so one look "
                     "cannot open the gate no matter what it says.")}

        # ---------------- metric tool profile ------------------------------
        p = cli.call_ok("plan_removals", {
            "labels": labels,
            "tool_profile": {"name": "tine", "clearance": 15.0,
                             "clearance_units": "mm"},
            "confidence_floor": 0.0, "include_rejections": False})
        out["metric_tool_profile"] = {
            "n_targets": len(p["targets"]),
            "refusal": p["summary"]["refusal"]}

    out["seconds"] = round(time.time() - t0, 1)
    with open(os.path.join(C.RESULTS, "a8_scores.json"), "w") as f:
        json.dump(C.jsonable(out), f, indent=1)
    print("wrote results/a8_scores.json in", out["seconds"], "s")
    return out


def _counts(it):
    d = {}
    for x in it:
        d[x] = d.get(x, 0) + 1
    return dict(sorted(d.items(), key=lambda kv: -kv[1]))


def _write(name, doc):
    with open(os.path.join(C.PRODUCTS, name), "w") as f:
        json.dump(C.jsonable(doc), f, indent=1)


if __name__ == "__main__":
    main()
