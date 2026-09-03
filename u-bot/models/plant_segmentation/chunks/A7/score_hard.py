"""A7 — scoring the hard cases and the confabulation probe.

Two questions the main table cannot answer.

**1. Was the label read off the material, or off the context?**  `plants.jpeg`
contains no squash seedling, so the brief's failure mode — a crop volunteer and
a weed that look nearly identical — is reached the only honest way one image
allows: by taking the surround away. A small squash leaf fragment with its vine
cropped out *is* visually a broadleaf seedling. So the same regions are rendered
at `pad_fraction` 0.00, at the shipped 0.75, and at 3.00, with nothing else
changed, and the labels are compared.

  * A label that holds across all three was read off the leaf.
  * A label that flips was read off the vine, and the model would have been
    wrong about a real seedling.

The direction matters more than the rate, under R2: a crop fragment that becomes
`remove` when its context is removed is the catastrophic direction, and it is
counted separately from the harmless one.

**2. Will it invent a plant that is not there?**  Six regions drawn over
material A0 labels as *pure straw*, where A4 found no plant at all, rendered and
prompted identically to real regions. There is nothing to label. `unsure` or
`keep` is the correct behaviour; a confident `remove` is a confabulation, and
this counts them instead of anecdote.

Run:  ../A3/.venv/bin/python score_hard.py
"""
from __future__ import annotations

import json
import os
from collections import Counter, defaultdict

from a7_data import load_components

HERE = os.path.dirname(os.path.abspath(__file__))
RES = os.path.join(HERE, "results")
SHIPPED_PAD = "shipped(0.75)"


def shipped_labels(variant="r2"):
    """The shipped-pad labels for the same regions, from the main run."""
    out = defaultdict(list)
    for rep in (1, 2):
        p = os.path.join(RES, f"labels_A_{variant}_r{rep}.json")
        if not os.path.exists(p):
            continue
        for l in json.load(open(p))["labels"]:
            if not l.get("fallback"):
                out[l["id"]].append(l)
    return out


def main(variant="r2"):
    hp = os.path.join(RES, f"hard_{variant}.json")
    if not os.path.exists(hp):
        raise SystemExit(f"no {hp} — run hard.py first")
    hard = json.load(open(hp))
    _, comps = load_components()
    ship = shipped_labels(variant)

    by_cond = defaultdict(lambda: defaultdict(list))
    for l in hard["labels"]:
        by_cond[l["condition"]][l["id"]].append(l)
    for cid, ls in ship.items():
        by_cond[SHIPPED_PAD][cid] = ls

    hs = hard["hard_set"]
    ids = sorted(set(sum(hs.values(), [])))

    def modal(ls):
        """Unanimous label, else `unsure` — R2's default as the tie-break."""
        if not ls:
            return None
        c = Counter(l["label"] for l in ls)
        top, k = c.most_common(1)[0]
        return top if k > len(ls) / 2 else "unsure"

    # ---- 1. context ablation ------------------------------------------------
    conds = ["p000", SHIPPED_PAD, "p300"]
    rows, flips, dangerous, safe = [], [], [], []
    for cid in ids:
        got = {c: modal(by_cond[c].get(cid, [])) for c in conds}
        t = comps[cid].truth
        rows.append({"id": cid, "truth": t, "px": comps[cid].px,
                     "crop_fraction": round(comps[cid].crop_fraction, 3),
                     **{c: got[c] for c in conds}})
        vals = [v for v in got.values() if v]
        if len(set(vals)) > 1:
            flips.append(cid)
            # the direction that matters: losing the surround makes it a target
            if got[SHIPPED_PAD] != "remove" and got["p000"] == "remove" \
                    and t == "crop":
                dangerous.append(cid)
            elif got[SHIPPED_PAD] == "remove" and got["p000"] != "remove":
                safe.append(cid)

    per_cond = {}
    for c in conds:
        lc = Counter()
        by_truth = defaultdict(Counter)
        for cid in ids:
            m = modal(by_cond[c].get(cid, []))
            if m:
                lc[m] += 1
                by_truth[comps[cid].truth][m] += 1
        per_cond[c] = {
            "label_counts": dict(lc),
            "crop_called_remove": by_truth["crop"]["remove"],
            "crop_components": sum(by_truth["crop"].values()),
            "weed_called_remove": by_truth["weed"]["remove"],
            "weed_components": sum(by_truth["weed"].values()),
            "by_truth": {k: dict(v) for k, v in by_truth.items()},
        }

    # ---- 2. null regions ----------------------------------------------------
    nulls = [l for l in hard["labels"] if l["condition"] == "null"]
    nc = Counter(l["label"] for l in nulls)
    confident_removes = [l for l in nulls
                         if l["label"] == "remove" and l["confidence"] >= 0.7]
    per_null = {}
    for l in nulls:
        per_null.setdefault(l["id"], []).append(
            {"rep": l["rep"], "label": l["label"],
             "confidence": l["confidence"], "reason": l["reason"]})

    out = {
        "variant": variant, "model": hard["model"],
        "cli_version": hard["cli_version"],
        "hard_set_rule": "crop-majority components other than the crop itself; "
                         "weed-majority components; grass-majority components "
                         "holding >= 10 % crop. Stated before scoring.",
        "hard_set_sizes": {k: len(v) for k, v in hs.items()},
        "n_hard": len(ids),
        "pads": {"p000": 0.0, SHIPPED_PAD: 0.75, "p300": 3.0},
        "context_ablation": {
            "per_condition": per_cond,
            "n_flipped": len(flips), "flipped_ids": flips,
            "flip_rate": len(flips) / len(ids) if ids else None,
            "flips_toward_remove_on_crop": dangerous,
            "flips_away_from_remove": safe,
            "reading": "a label that survives losing its surround was read off "
                       "the material; one that flips was read off the context, "
                       "and would have been wrong about a real seedling.",
            "rows": rows,
        },
        "null_regions": {
            "n_regions": len(set(l["id"] for l in nulls)),
            "n_judgements": len(nulls),
            "label_counts": dict(nc),
            "confabulation_rate": len(confident_removes) / len(nulls) if nulls else None,
            "confabulation_definition": "`remove` at confidence >= 0.70 over a "
                                        "region that is pure straw in A0 and "
                                        "holds no A4 plant material at all",
            "confident_removes": [{"id": l["id"], "confidence": l["confidence"],
                                   "reason": l["reason"]}
                                  for l in confident_removes],
            "mean_confidence": (sum(l["confidence"] for l in nulls) / len(nulls)
                                if nulls else None),
            "per_region": per_null,
        },
    }
    p = os.path.join(RES, f"hard_scores_{variant}.json")
    json.dump(out, open(p, "w"), indent=1)
    print(f"wrote {p}\n")

    print(f"context ablation over {len(ids)} hard regions "
          f"({hard['hard_set_sizes'] if 'hard_set_sizes' in hard else ''})")
    h = f"{'pad':16} {'keep':>5} {'remove':>7} {'unsure':>7} {'crop→remove':>12}"
    print(h); print("-" * len(h))
    for c in conds:
        d = per_cond[c]["label_counts"]
        print(f"{c:16} {d.get('keep', 0):>5} {d.get('remove', 0):>7} "
              f"{d.get('unsure', 0):>7} "
              f"{per_cond[c]['crop_called_remove']:>7}/"
              f"{per_cond[c]['crop_components']:<4}")
    print(f"\nflipped across the three pads: {len(flips)}/{len(ids)} "
          f"({len(flips) / len(ids):.1%})" if ids else "")
    print(f"  flips that make a CROP fragment a target when context is removed: "
          f"{len(dangerous)}  {dangerous}")
    print(f"  flips that make a target harmless when context is removed: "
          f"{len(safe)}  {safe}")
    print(f"\nnull regions: {out['null_regions']['n_judgements']} judgements "
          f"over {out['null_regions']['n_regions']} straw-only regions")
    print(f"  {out['null_regions']['label_counts']}")
    print(f"  confabulation (confident remove): "
          f"{out['null_regions']['confabulation_rate']:.1%}")


if __name__ == "__main__":
    main()
