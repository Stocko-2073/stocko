"""A5 — everything that was measured, and the honesty checks on it.

    ../A3/.venv/bin/python diagnostics.py

Writes `results/diagnostics.json` and prints the tables that go into
`RESULTS.md`. Nothing here changes a status; it only measures.

The four questions this file exists to answer
---------------------------------------------
1. **Counts by status**, with the straw-occlusion rate called out.
2. **Is `observed` circular?** A2 fitted its datum to every pixel within 3σ of
   the surface, *including plant material*. If a component's lowest pixel is
   itself one of A2's ground inliers, "this plant reaches the ground" is partly
   a restatement of A2's own inlier decision. Measured, not assumed.
3. **Consistency against A0's contact points** — a *labelled diagnostic*, never
   an accuracy. A0 found **zero** `visible` contact points in this image; all
   ten are `under_straw` with `localisation: estimated`, and A0's schema says
   explicitly that they "must not be used as a scoring target". So this compares
   an estimate to an estimate.
4. **How much the two A4 policies disagree** about where the targets are.
"""
from __future__ import annotations

import json
import os
import sys

import numpy as np
from PIL import Image
from scipy import ndimage

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from a5_common import (A2, ROOT, gt_to_depth, load_a3_material_depth_grid,  # noqa: E402
                       load_a4, load_scene)
from contact_points import contact_points, status_counts  # noqa: E402
import eval as a0eval  # noqa: E402

PRODUCTS = os.path.join(HERE, "products")
RESULTS = os.path.join(HERE, "results")
POLICIES = {"split": "default", "merge": "merge"}


def dominant(c):
    comp = c["material"]["composition"]
    return max(comp, key=comp.get) if comp else "none"


def load(policy):
    return json.load(open(os.path.join(PRODUCTS, f"contacts_{policy}.json")))


# ------------------------------------------------------- 1. counts by status
def counts(cs):
    out = {"by_status": {}, "by_status_px": {},
           "by_status_excluding_grass_components": {}}
    for st in ("observed", "extrapolated", "occluded"):
        sub = [c for c in cs if c["status"] == st]
        out["by_status"][st] = len(sub)
        out["by_status_px"][st] = sum(c["n_px"] for c in sub)
        out["by_status_excluding_grass_components"][st] = sum(
            1 for c in sub if dominant(c) != "grass")
    out["total"] = len(cs)
    out["total_excluding_grass_components"] = sum(
        1 for c in cs if dominant(c) != "grass")
    out["fabricated_points"] = sum(1 for c in cs
                                   if c["status"] == "occluded" and c["point"])
    out["with_lowest_visible_point"] = sum(1 for c in cs if c["lowest_visible_point"])
    out["with_lowest_visible_stem_point"] = sum(
        1 for c in cs if c["lowest_visible_stem_point"])
    out["arm_admissible"] = sum(1 for c in cs if c["arm_admissible"])
    reasons = {}
    for c in cs:
        if c["status"] != "occluded":
            continue
        r = c["reason"]
        for k, name in [("BELOW A2", "material_below_datum"),
                        ("tool budget", "beyond_max_extrapolation"),
                        ("needed to measure", "basal_support_too_small"),
                        ("runs along the datum", "axis_not_descending"),
                        ("reporting ceiling", "never_reaches_datum"),
                        ("trust distance", "datum_not_trusted_at_landing"),
                        ("wanders", "lateral_wander_exceeds_budget"),
                        ("leaves the frame", "axis_leaves_frame"),
                        ("no pixel of this component", "no_trusted_datum")]:
            if k in r:
                reasons[name] = reasons.get(name, 0) + 1
                break
        else:
            reasons["other"] = reasons.get("other", 0) + 1
    out["occluded_reasons"] = reasons

    # the straw question, asked of every component, not only the occluded ones
    occl = {}
    for c in cs:
        if c["status"] == "observed":
            continue
        occl[c["occluder"] or "unknown"] = occl.get(c["occluder"] or "unknown", 0) + 1
    out["occluder_of_non_observed"] = occl
    n_non = sum(occl.values())
    out["straw_occlusion_rate_of_non_observed"] = (
        occl.get("straw", 0) / n_non if n_non else None)

    surround = {}
    for c in cs:
        for k, v in (c["material"].get("basal_surround") or {}).items():
            surround[k] = surround.get(k, 0) + v
    out["basal_surround_px_all_components"] = surround
    out["components_whose_basal_surround_is_mostly_straw"] = sum(
        1 for c in cs
        if (c["material"].get("basal_surround") or {})
        and max(c["material"]["basal_surround"],
                key=c["material"]["basal_surround"].get) == "straw")

    d = [c["extrapolation_distance_sigma"] for c in cs
         if c["status"] == "extrapolated"]
    out["extrapolation_distance_sigma"] = (
        {"n": len(d),
         "pct": {str(p): float(np.percentile(d, p)) for p in (0, 25, 50, 75, 90, 100)}}
        if d else {"n": 0})
    conf = [c["confidence"] for c in cs if c["confidence"] is not None]
    out["confidence"] = ({"n": len(conf),
                          "pct": {str(p): float(np.percentile(conf, p))
                                  for p in (5, 50, 95)}} if conf else {"n": 0})
    return out


# --------------------------------------------- 2. is `observed` circular?
def circularity(cs, scene, plant_mask):
    """How much of the local datum support under an observed contact comes from
    material that is *not* plant, i.e. is independent of the plant itself.

    A2's fit scale is 147 px, so that is the window over which the datum under a
    pixel is actually determined; the number is A2's, not a new constant.
    """
    win = int(round(scene.a2_manifest["key_numbers"]["fit_scale_px"]))
    g = scene.ground.astype(np.float32)
    g_free = (scene.ground & ~plant_mask).astype(np.float32)
    tot = ndimage.uniform_filter(g, win, mode="nearest")
    free = ndimage.uniform_filter(g_free, win, mode="nearest")
    frac = np.where(tot > 0, free / np.maximum(tot, 1e-9), np.nan)

    rows, on_inlier = [], 0
    for c in cs:
        p = c["lowest_visible_point"]
        if not p:
            continue
        u, v = p["depth_grid_xy"]
        f = float(frac[int(round(v)), int(round(u))])
        rows.append(f)
        on_inlier += bool(p["on_a2_ground_inlier"])
    obs = [c for c in cs if c["status"] == "observed"]
    obs_inlier = sum(1 for c in obs if c["lowest_visible_point"]["on_a2_ground_inlier"])
    return {
        "fit_scale_px": win,
        "n_components_with_a_point": len(rows),
        "base_pixel_is_an_A2_ground_inlier": on_inlier,
        "base_pixel_is_an_A2_ground_inlier_fraction": on_inlier / max(len(rows), 1),
        "observed_status_base_is_a_ground_inlier": obs_inlier,
        "observed_status_n": len(obs),
        "observed_status_base_is_a_ground_inlier_fraction":
            obs_inlier / max(len(obs), 1),
        "non_plant_share_of_local_datum_support_pct": {
            str(p): float(np.nanpercentile(rows, p)) for p in (5, 25, 50, 75, 95)},
        "note": "A2 selected ground inliers as everything within 3σ of the "
                "fitted surface, plant material included. Where the base pixel "
                "is itself an inlier, `observed` is partly a restatement of "
                "A2's inlier decision rather than an independent observation. "
                "The support fraction says how much of the datum under that "
                "pixel is nevertheless pinned by non-plant material.",
    }


# ------------------------------------- 3. consistency against A0's GT points
def gt_consistency(cs, comps_gtgrid, gt, label):
    """Distance from A5's points to A0's estimated contact points.

    NOT an accuracy: A0's ten points are all `under_straw` / `estimated` and A0
    says they must not be scored against. This measures whether two independent
    estimates of the same unobservable thing agree.
    """
    scoreable = (gt.material != 0) & (gt.instances != 255)
    by_id = {c["component"]: c for c in cs}
    rows = []
    for e in gt.contacts["instances"]:
        gid = e["id"]
        gm = (gt.instances == gid) & scoreable
        ids, cnt = np.unique(comps_gtgrid[gm], return_counts=True)
        keep = ids > 0
        ids, cnt = ids[keep], cnt[keep]
        if not len(ids):
            rows.append({"gt": gid, "name": e["name"], "assigned": None,
                         "reason": "no predicted component overlaps this GT instance"})
            continue
        pid = int(ids[cnt.argmax()])
        c = by_id.get(pid)
        gx, gy = e["point"]

        def dist(pt):
            return (float(np.hypot(pt["gt_grid_xy"][0] - gx,
                                   pt["gt_grid_xy"][1] - gy)) if pt else None)

        pm = comps_gtgrid == pid
        yy, xx = np.nonzero(pm)
        cen = (xx.mean(), yy.mean())
        low = int(np.argmax(yy))
        rows.append({
            "gt": gid, "name": e["name"], "crop": e["crop"],
            "gt_point": [gx, gy], "gt_status": e["status"],
            "gt_localisation": e.get("localisation", "estimated"),
            "assigned": pid,
            "assigned_px_of_gt_instance": int(cnt.max()),
            "assigned_coverage_of_gt_instance": float(cnt.max() / max(gm.sum(), 1)),
            "a5_status": c["status"],
            "a5_confidence": c["confidence"],
            "err_contact_px": dist(c["point"]),
            "err_lowest_visible_px": dist(c["lowest_visible_point"]),
            "err_lowest_visible_stem_px": dist(c["lowest_visible_stem_point"]),
            "baseline_err_component_centroid_px":
                float(np.hypot(cen[0] - gx, cen[1] - gy)),
            "baseline_err_bottom_most_pixel_px":
                float(np.hypot(xx[low] - gx, yy[low] - gy)),
        })

    def agg(key):
        v = [r[key] for r in rows if r.get(key) is not None]
        return ({"n": len(v), "median_px": float(np.median(v)),
                 "mean_px": float(np.mean(v)), "max_px": float(np.max(v))}
                if v else {"n": 0})

    return {
        "label": label,
        "WARNING": "consistency, NOT accuracy. All ten A0 points are "
                   "`under_straw` with localisation `estimated`; A0's SCHEMA.md "
                   "says they must not be used as a scoring target. The "
                   "roadmap's done-criterion (error over `visible` GT points) "
                   "is EMPTY for this image.",
        "n_visible_gt_points": sum(1 for e in gt.contacts["instances"]
                                   if e["status"] == "visible"),
        "rows": rows,
        "summary": {k: agg(k) for k in
                    ("err_contact_px", "err_lowest_visible_px",
                     "err_lowest_visible_stem_px",
                     "baseline_err_component_centroid_px",
                     "baseline_err_bottom_most_pixel_px")},
    }


# ------------------------------------------------ 4. policy disagreement
def policy_disagreement(split, merge, comps_split, comps_merge):
    """For every merge component, which split components sit inside it and how
    far apart their contact points are."""
    bys = {c["component"]: c for c in split}
    rows = []
    for c in merge:
        pm = comps_merge == c["component"]
        ids, cnt = np.unique(comps_split[pm], return_counts=True)
        keep = ids > 0
        ids, cnt = ids[keep], cnt[keep]
        inner = [bys[int(i)] for i in ids if int(i) in bys]
        pts = [x["point"]["gt_grid_xy"] for x in inner if x["point"]]
        mp = c["point"]["gt_grid_xy"] if c["point"] else None
        d = ([float(np.hypot(p[0] - mp[0], p[1] - mp[1])) for p in pts]
             if mp else [])
        rows.append({
            "merge_component": c["component"], "n_px": c["n_px"],
            "merge_status": c["status"],
            "n_split_components_inside": len(inner),
            "n_split_points_inside": len(pts),
            "split_status": {s: sum(1 for x in inner if x["status"] == s)
                             for s in ("observed", "extrapolated", "occluded")},
            "dist_split_points_to_merge_point_px":
                {"median": float(np.median(d)), "max": float(np.max(d))} if d else None,
        })
    n_pts_split = sum(1 for c in split if c["point"])
    n_pts_merge = sum(1 for c in merge if c["point"])
    return {
        "n_components": {"split": len(split), "merge": len(merge),
                         "ratio": len(split) / max(len(merge), 1)},
        "n_actionable_points": {"split": n_pts_split, "merge": n_pts_merge,
                                "ratio": n_pts_split / max(n_pts_merge, 1)},
        "largest_merge_components": sorted(rows, key=lambda r: -r["n_px"])[:10],
        "merge_components_holding_more_than_one_split_point":
            sum(1 for r in rows if r["n_split_points_inside"] > 1),
    }


def main():
    os.makedirs(RESULTS, exist_ok=True)
    scene = load_scene()
    gt = a0eval.load_gt()
    material = load_a3_material_depth_grid()
    plant_mask = np.isin(material, (1, 2, 3, 4, 7))

    out = {"chunk": "A5", "scale_confidence": "scale_free",
           "DATUM": scene.a2_manifest["DATUM"]}

    docs, comps = {}, {}
    for policy, tag in POLICIES.items():
        docs[policy] = load(policy)["components"]
        comps[policy] = load_a4(tag=tag).components
    docs["gt_instances"] = load("gt_instances")["components"]
    inst = np.array(Image.open(os.path.join(ROOT, "groundtruth",
                                            "plants_instances.png")))
    comps["gt_instances"] = np.where(inst == 255, 0, inst).astype(np.int32)

    for k, cs in docs.items():
        out.setdefault("counts", {})[k] = counts(cs)
        out.setdefault("circularity", {})[k] = circularity(cs, scene, plant_mask)
        out.setdefault("gt_consistency", {})[k] = gt_consistency(
            cs, comps[k], gt, k)

    out["policy_disagreement"] = policy_disagreement(
        docs["split"], docs["merge"], comps["split"], comps["merge"])

    # A0's own scorer, fed A5's points, so the empty `visible` bucket is printed
    # by the contract's own code rather than asserted here.
    for k in ("split", "merge"):
        cmap = {}
        for r in out["gt_consistency"][k]["rows"]:
            if r.get("assigned") and r.get("err_contact_px") is not None:
                c = next(x for x in docs[k] if x["component"] == r["assigned"])
                cmap[r["gt"]] = c["point"]["gt_grid_xy"]
        pred = a0eval.load_prediction(instances=comps[k], contacts=cmap,
                                      name=f"A5 {k}", gt=gt)
        r = a0eval.score(pred, gt)
        out.setdefault("a0_eval_contacts", {})[k] = r["contacts"]["per_status"]
        out["a0_eval_contacts"][k + "_scoreable_n"] = r["contacts"]["scoreable"].get("n", 0)

    json.dump(out, open(os.path.join(RESULTS, "diagnostics.json"), "w"), indent=1)

    # ----------------------------------------------------------- printout
    print("\n=== counts by status ===")
    for k, c in out["counts"].items():
        print(f"{k:14s} obs {c['by_status']['observed']:4d}  "
              f"extrap {c['by_status']['extrapolated']:4d}  "
              f"occl {c['by_status']['occluded']:4d}  "
              f"| total {c['total']:4d}  fabricated {c['fabricated_points']}  "
              f"arm-admissible {c['arm_admissible']}")
        print(f"{'':14s} occluded reasons: {c['occluded_reasons']}")
        print(f"{'':14s} occluder of non-observed: {c['occluder_of_non_observed']}"
              f"  straw rate {c['straw_occlusion_rate_of_non_observed']}")
        print(f"{'':14s} basal surround (px): {c['basal_surround_px_all_components']}")
        print(f"{'':14s} extrapolation σ: {c['extrapolation_distance_sigma']}")
    print("\n=== is `observed` circular? ===")
    for k, c in out["circularity"].items():
        print(f"{k:14s} base pixel is an A2 ground inlier: "
              f"{c['observed_status_base_is_a_ground_inlier']}/"
              f"{c['observed_status_n']} of `observed` "
              f"({100*c['observed_status_base_is_a_ground_inlier_fraction']:.1f} %)"
              f"   non-plant share of local datum support "
              f"p50 {c['non_plant_share_of_local_datum_support_pct']['50']:.2f}")
    print("\n=== consistency vs A0's estimated points (NOT accuracy) ===")
    for k, c in out["gt_consistency"].items():
        s = c["summary"]
        print(f"{k:14s} contact n={s['err_contact_px']['n']} "
              f"median {s['err_contact_px'].get('median_px', float('nan')):.1f} px | "
              f"lowest-visible n={s['err_lowest_visible_px']['n']} "
              f"median {s['err_lowest_visible_px'].get('median_px', float('nan')):.1f} px | "
              f"centroid baseline {s['baseline_err_component_centroid_px'].get('median_px', float('nan')):.1f} | "
              f"bottom-pixel baseline {s['baseline_err_bottom_most_pixel_px'].get('median_px', float('nan')):.1f}")
    print("\n=== policy disagreement ===")
    print(json.dumps({k: v for k, v in out["policy_disagreement"].items()
                      if k != "largest_merge_components"}, indent=1))
    print("\n=== A0 eval.py on A5's contacts ===")
    print(json.dumps(out["a0_eval_contacts"], indent=1))


if __name__ == "__main__":
    main()
