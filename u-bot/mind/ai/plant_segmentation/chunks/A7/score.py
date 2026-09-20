"""A7 — scoring against the A0 ground truth.

Three families of number, and the order matters.

**1. The R2-critical confusion, first.** A3's forwarded warning is that
rewriting prompt prose moved one specific confusion 5x while the aggregate
stayed flat. So the headline is never accuracy. It is:

* `crop_mislabels` — components whose majority ground truth is the crop and
  which the model said `remove`. Catastrophic, and the number A8's gate exists
  to drive to zero.
* `crop_px_at_risk` — the same failure counted in ground-truth crop *pixels*
  rather than components, because components are wildly unequal in size and one
  component holds 98 % of the crop. Threshold-free: no size cut-off is applied
  anywhere in it.
* `weed_keeps` — weed or grass components said `keep`. Cheap under R2, and
  reported so the safety number cannot be bought by saying `keep` to everything.
* `unsure_rate` — the third option's actual usage.

**2. Aggregate accuracy, second and clearly labelled as secondary.**

**3. Stability.** Every condition is run twice with a byte-identical prompt.
`flip_rate` is the fraction of components that did not get the same label both
times; the per-metric spread across repeats is reported as min-max. Two repeats
detect instability but cannot estimate its rate precisely, and a two-way
"majority" vote is really "unanimous, else `unsure`" — which is R2's default,
so the tie-break is at least on the safe side. Both limits are stated in
FINDINGS rather than smoothed over.

The confidence floor sweep exists for A8: `plan_removals` admits a target only
at high confidence, and this is the curve that tells it where high is.
"""
from __future__ import annotations

import json
import os
from collections import Counter, defaultdict

from a7_data import load_components, tier_report, totals

HERE = os.path.dirname(os.path.abspath(__file__))
RES = os.path.join(HERE, "results")
FLOORS = (0.0, 0.5, 0.7, 0.8, 0.9, 0.95)


def load_run(path):
    return json.load(open(path))


def score_run(run, comps, tot, floor=0.0, core_only=True):
    """Score one repeat of one condition.

    Scored over the `core` components — the ones the model was actually asked
    about. The triaged tiers are `unsure` by policy in every condition and every
    baseline alike, so including them would add the same constant to every row
    and depress every unsure rate by the same amount. What they cost is reported
    once, by `a7_data.tier_report()`, in ground-truth pixels.
    """
    lab = {l["id"]: l for l in run["labels"]}
    ids = [c.id for c in comps.values() if (c.core or not core_only)]

    def eff(cid):
        """The label after the confidence floor — R2's default applied in code."""
        l = lab.get(cid)
        if l is None:
            return "unsure"
        if l["label"] == "remove" and l["confidence"] < floor:
            return "unsure"
        return l["label"]

    by_truth = defaultdict(Counter)
    for cid in ids:
        by_truth[comps[cid].truth][eff(cid)] += 1

    px = Counter()
    for c in comps.values():
        if core_only and not c.core:
            # a triaged component is `unsure`; it targets nothing
            continue
        if eff(c.id) == "remove":
            px["crop"] += c.gt_crop_px
            px["weed"] += c.gt_weed_px
            px["grass"] += c.gt_grass_px

    n = len(ids)
    lc = Counter(eff(c) for c in ids)
    correct = (by_truth["crop"]["keep"] + by_truth["weed"]["remove"]
               + by_truth["grass"]["remove"] + by_truth["nonplant"]["keep"])
    return {
        "n_components": n,
        "confidence_floor": floor,
        # --- 1. the confusion that matters -------------------------------
        "crop_mislabels": by_truth["crop"]["remove"],
        "crop_components": sum(by_truth["crop"].values()),
        "crop_px_at_risk": px["crop"] / tot["crop"],
        "crop_px_at_risk_n": px["crop"],
        "weed_keeps": by_truth["weed"]["keep"] + by_truth["grass"]["keep"],
        "weed_components": sum(by_truth["weed"].values()),
        "grass_components": sum(by_truth["grass"].values()),
        "weed_px_reached": px["weed"] / tot["weed"],
        "grass_px_reached": px["grass"] / tot["grass"],
        "unsure_rate": lc["unsure"] / n,
        "unsure_on_crop": by_truth["crop"]["unsure"],
        "unsure_on_weed": by_truth["weed"]["unsure"] + by_truth["grass"]["unsure"],
        # --- 2. secondary -------------------------------------------------
        "accuracy_keep_remove": correct / n,
        "label_counts": dict(lc),
        "by_truth": {k: dict(v) for k, v in by_truth.items()},
        # --- confabulation: straw-only components called remove ----------
        "nonplant_removes": by_truth["nonplant"]["remove"],
        "nonplant_components": sum(by_truth["nonplant"].values()),
        "mean_confidence": (sum(lab[c]["confidence"] for c in ids
                                if c in lab) / n),
        "mean_confidence_remove": _mean(
            [lab[c]["confidence"] for c in ids
             if c in lab and lab[c]["label"] == "remove"]),
        "mean_confidence_keep": _mean(
            [lab[c]["confidence"] for c in ids
             if c in lab and lab[c]["label"] == "keep"]),
    }


def _mean(xs):
    return sum(xs) / len(xs) if xs else None


def stability(runs, comps):
    """Agreement across repeats of the same condition."""
    ids = [c.id for c in comps.values() if c.core]
    per = {cid: [next(l["label"] for l in r["labels"] if l["id"] == cid)
                 for r in runs] for cid in ids}
    flips = [cid for cid, v in per.items() if len(set(v)) > 1]
    conf = {cid: [next(l["confidence"] for l in r["labels"] if l["id"] == cid)
                  for r in runs] for cid in ids}
    spread = _mean([max(v) - min(v) for v in conf.values()])
    maj = {}
    for cid, v in per.items():
        c = Counter(v)
        top, k = c.most_common(1)[0]
        maj[cid] = top if k > len(runs) / 2 else "unsure"
    # A "flip rate" over one repeat is 0.0 by arithmetic and says nothing about
    # the model. It is reported as null rather than as a zero, so a
    # single-repeat condition cannot be read as a perfectly stable one.
    single = len(runs) < 2
    return {"n_repeats": len(runs), "n_components": len(ids),
            "flip_rate": None if single else len(flips) / len(ids),
            "flipped_ids": sorted(flips),
            "mean_confidence_spread": None if single else spread,
            "majority_vote": maj,
            "unanimous_rate": None if single else 1 - len(flips) / len(ids)}


def majority_run(runs, comps):
    """A synthetic run holding the per-component majority vote of `runs`."""
    st = stability(runs, comps)
    labels = []
    for cid, lab in st["majority_vote"].items():
        confs = [next(l["confidence"] for l in r["labels"] if l["id"] == cid)
                 for r in runs]
        labels.append({"id": cid, "label": lab,
                       "confidence": sum(confs) / len(confs),
                       "reason": "majority vote of repeats", "mixed": False,
                       "mixed_note": "", "r3_soft": []})
    seen = {l["id"] for l in labels}
    for c in comps.values():
        if c.id not in seen:
            labels.append({"id": c.id, "label": "unsure", "confidence": 0.0,
                           "reason": "triaged", "mixed": False,
                           "mixed_note": "", "r3_soft": []})
    return {"framing": runs[0]["framing"], "variant": runs[0]["variant"],
            "rep": "majority", "labels": labels}


def r3_report(runs):
    hard = soft = 0
    soft_examples = []
    for r in runs:
        for l in r["labels"]:
            if l.get("r3_violation"):
                hard += 1
            for s in l.get("r3_soft", []) or []:
                soft += 1
                if len(soft_examples) < 8:
                    soft_examples.append({"id": l["id"], "hit": s})
    return {"hard_violations": hard, "soft_frame_relative": soft,
            "examples": soft_examples}


def mixed_report(runs, comps):
    """Did the model notice the mixed components?  Component 1 above all."""
    out = {}
    for cid in [c.id for c in comps.values() if c.core]:
        vals = []
        for r in runs:
            l = next((x for x in r["labels"] if x["id"] == cid), None)
            if l:
                vals.append(bool(l.get("mixed")))
        out[cid] = sum(vals)
    flagged = {k: v for k, v in out.items() if v}
    return {"n_repeats": len(runs), "flagged_any": len(flagged),
            "component_1_flagged_in": out.get(1, 0),
            "flagged": dict(sorted(flagged.items(), key=lambda kv: -kv[1]))}


def condition_report(runs, comps, tot):
    per_rep = [score_run(r, comps, tot) for r in runs]
    sweep = {f"{f:.2f}": score_run(majority_run(runs, comps), comps, tot,
                                   floor=f) for f in FLOORS}
    keys = ("crop_mislabels", "crop_px_at_risk", "weed_keeps",
            "weed_px_reached", "grass_px_reached", "unsure_rate",
            "accuracy_keep_remove", "nonplant_removes")
    spread = {k: [min(s[k] for s in per_rep), max(s[k] for s in per_rep)]
              for k in keys}
    return {
        "framing": runs[0]["framing"], "variant": runs[0]["variant"],
        "model": runs[0].get("model"), "n_runs": len(runs),
        "per_repeat": per_rep,
        "across_repeats_minmax": spread,
        "majority_vote_score": score_run(majority_run(runs, comps), comps, tot),
        "confidence_floor_sweep": sweep,
        "stability": {k: v for k, v in stability(runs, comps).items()
                      if k != "majority_vote"},
        "r3": r3_report(runs),
        "mixed": mixed_report(runs, comps),
        "framing_b_binding": {
            "n_asked": runs[0].get("n_asked"),
            "returned_per_rep": [r.get("n_returned") for r in runs],
            "omitted_per_rep": [len(r.get("omitted") or []) for r in runs],
            "hallucinated_ids_per_rep": [r.get("hallucinated_ids") for r in runs],
            "rejects_per_rep": [len(r.get("rejects") or []) for r in runs],
        } if runs[0]["framing"] == "B" else None,
    }


def main():
    _, comps = load_components()
    tot = totals(comps)
    groups = defaultdict(list)
    for f in sorted(os.listdir(RES)):
        if f.startswith("labels_") and f.endswith(".json"):
            r = load_run(os.path.join(RES, f))
            groups[(r["framing"], r["variant"])].append(r)
    report = {"ground_truth": "groundtruth/ (A0)",
              "components": "chunks/A4 merge, a4_api.load_a4(tag='merge')",
              "n_components_total": len(comps),
              "n_renderable": sum(1 for c in comps.values() if c.renderable),
              "n_core_asked": sum(1 for c in comps.values() if c.core),
              "n_triaged_unsure": sum(1 for c in comps.values()
                                      if not c.core),
              "gt_pixel_totals": tot,
              "tiers": tier_report(comps),
              "truth_histogram": dict(Counter(
                  c.truth for c in comps.values() if c.core)),
              "conditions": {}}
    # Baselines are single deterministic runs, not conditions with repeats, so
    # they get scored on their own rather than pushed through `condition_report`
    # — a "stability" or a min-max over one run would be a fabricated number.
    report["baselines"] = {}
    for f in sorted(os.listdir(RES)):
        if f.startswith("labels_baseline_") and f.endswith(".json"):
            r = load_run(os.path.join(RES, f))
            groups.pop((r["framing"], r["variant"]), None)
            report["baselines"][f] = score_run(r, comps, tot)
            report["baselines"][f]["model"] = r.get("model")

    for (f, v), runs in sorted(groups.items()):
        runs.sort(key=lambda r: str(r["rep"]))
        report["conditions"][f"{f}/{v}"] = condition_report(runs, comps, tot)
    p = os.path.join(RES, "a7_scores.json")
    json.dump(report, open(p, "w"), indent=1, default=str)
    print(f"wrote {p}\n")
    hdr = f"{'condition':22} {'crop_mislab':>11} {'crop_px_risk':>12} " \
          f"{'weed_keep':>9} {'weed_px':>8} {'grass_px':>8} {'unsure':>7} " \
          f"{'acc':>6} {'flip':>6}"
    print(hdr); print("-" * len(hdr))
    for k, s in report["baselines"].items():
        n = k[len("labels_baseline_"):-len("_r0.json")]
        print(f"{'baseline ' + n:22} {s['crop_mislabels']:>4}/"
              f"{s['crop_components']:<6} {s['crop_px_at_risk']:>11.4%} "
              f"{s['weed_keeps']:>4}/{s['weed_components']+s['grass_components']:<4} "
              f"{s['weed_px_reached']:>7.1%} {s['grass_px_reached']:>7.1%} "
              f"{s['unsure_rate']:>6.1%} {s['accuracy_keep_remove']:>5.3f} "
              f"{'—':>5}")
    print()
    for k, c in report["conditions"].items():
        s = c["majority_vote_score"]
        print(f"{k:22} {s['crop_mislabels']:>4}/{s['crop_components']:<6} "
              f"{s['crop_px_at_risk']:>11.4%} "
              f"{s['weed_keeps']:>4}/{s['weed_components']+s['grass_components']:<4} "
              f"{s['weed_px_reached']:>7.1%} {s['grass_px_reached']:>7.1%} "
              f"{s['unsure_rate']:>6.1%} {s['accuracy_keep_remove']:>5.3f} "
              + (f"{c['stability']['flip_rate']:>5.1%}"
                 if c['stability']['flip_rate'] is not None else f"{'n/a':>5}"))


if __name__ == "__main__":
    main()
