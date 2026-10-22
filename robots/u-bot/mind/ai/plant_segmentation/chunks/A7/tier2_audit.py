"""A7 — what the budget floor cost, measured instead of argued.

`TIER1_PX = 75` is the one constant in this chunk that exists for money rather
than for evidence. It silences 56 of the 129 components that clear A0's minimum
reviewable region, and they are labelled `unsure` by policy without the model
ever seeing them.

Two things are already known about those 56 without spending anything: they hold
**0.09 %** of the ground-truth crop pixels and **0.00 %** of the weed pixels
(`a7_data.tier_report`). That bounds what the floor can cost the *pixel* metrics
to almost nothing. It says nothing about what it costs the *component* counts,
and 11 of the 56 are crop-majority — so under R2 the open question is whether
the model would have called any of them `remove`.

This asks. A seeded random half of the 56, one repeat, the shipped framing-A
prompt and the shipped renders, so nothing differs from the main run but which
components are in it. The sample is drawn from the id list alone, before any
ground truth is consulted, and the seed is recorded.

    python tier2_audit.py            # ~24 calls
"""
from __future__ import annotations

import json
import os
from concurrent.futures import ThreadPoolExecutor

import numpy as np

import prompts as P
import schema as S
import vlm
from a7_data import load_components, TIER1_PX
from render import Renderer

HERE = os.path.dirname(os.path.abspath(__file__))
RES = os.path.join(HERE, "results")
AUDIT_SEED = 20260901
AUDIT_FRACTION = 0.5
VARIANT = "r2"          # the shipped condition


def sample_ids(comps):
    """A seeded half of the silenced tier, drawn without looking at the truth."""
    silenced = sorted(c.id for c in comps.values()
                      if c.renderable and not c.core)
    rng = np.random.default_rng(AUDIT_SEED)
    n = int(round(len(silenced) * AUDIT_FRACTION))
    return sorted(int(i) for i in rng.choice(silenced, n, replace=False))


def main(workers=8):
    _, comps = load_components()
    ids = sample_ids(comps)
    R = Renderer()
    rdir = os.path.join(HERE, "renders", "A")

    def one(cid):
        png = os.path.join(rdir, f"region_{cid:03d}.png")
        if not os.path.exists(png):
            png = R.render_instance(cid, rdir)
        files = vlm.stage([png])
        txt, rec = vlm.call(P.prompt_A(cid, VARIANT, files),
                            f"T2_{VARIANT}_r1_c{cid:03d}")
        try:
            obj = S.validate_label(S.extract_json(txt), expect_id=cid)
        except S.R3Violation as e:
            obj = S.fallback(cid, f"R3 violation: {e}")
        except Exception as e:
            obj = S.fallback(cid, f"unparseable reply: {e}")
        obj["_cost_usd"] = rec.get("cost_usd")
        return obj

    with ThreadPoolExecutor(workers) as ex:
        labels = list(ex.map(one, ids))

    # the only number this exists to produce, under R2
    by = {l["id"]: l for l in labels}
    crop_removes = [cid for cid in ids
                    if comps[cid].truth == "crop" and by[cid]["label"] == "remove"]
    out = {
        "purpose": "what TIER1_PX silences, measured",
        "tier1_px": TIER1_PX, "seed": AUDIT_SEED, "fraction": AUDIT_FRACTION,
        "variant": VARIANT, "model": vlm.MODEL, "cli_version": vlm.cli_version(),
        "n_silenced_total": sum(1 for c in comps.values()
                                if c.renderable and not c.core),
        "n_sampled": len(ids), "sampled_ids": ids,
        "label_counts": {k: sum(1 for l in labels if l["label"] == k)
                         for k in ("keep", "remove", "unsure")},
        "truth_histogram": {t: sum(1 for cid in ids if comps[cid].truth == t)
                            for t in ("crop", "weed", "grass", "nonplant")},
        "by_truth": {t: {k: sum(1 for cid in ids
                                if comps[cid].truth == t
                                and by[cid]["label"] == k)
                         for k in ("keep", "remove", "unsure")}
                     for t in ("crop", "weed", "grass", "nonplant")},
        "crop_components_the_floor_saved_from_remove": crop_removes,
        "crop_px_in_those": sum(comps[c].gt_crop_px for c in crop_removes),
        "cost_usd": sum(l.get("_cost_usd") or 0 for l in labels),
        "labels": labels,
    }
    p = os.path.join(RES, "tier2_audit.json")
    json.dump(out, open(p, "w"), indent=1)
    print(json.dumps({k: v for k, v in out.items()
                      if k not in ("labels", "sampled_ids")}, indent=1))
    print(f"-> {p}")


if __name__ == "__main__":
    main()
