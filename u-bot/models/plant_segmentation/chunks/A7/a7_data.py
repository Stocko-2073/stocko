"""A7 — inputs, triage, and the ground-truth association used for scoring.

Nothing in this module calls a model. It answers three questions:

1. **Which instance IDs exist?**  The A4 `merge` components (A4's FINDINGS tells
   A7 to label these, not the 674 `split` ones).
2. **Which of them can a render carry evidence about?**  Triage, by A0's already
   registered *min reviewable region* of 25 label px.  An ID below the floor is
   **not dropped** — it is labelled `unsure` by policy, with the policy recorded
   as its rationale (brief: "an ID with no defensible label is `unsure`, not
   omitted").
3. **What is the truth for each ID?**  Two different truths, because R2 makes
   them different questions:
   * a *majority* class per component, for the discrete confusion counts;
   * the *pixel* accounting (how much GT crop / weed / grass sits inside each
     component), for the threshold-free R2 metric "what fraction of the crop
     would a tool be sent at".

There is no coordinate anywhere in what the VLM is shown or asked (R3); this
module is the only place image geometry is touched, and it is code, not prompt.
"""
from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "chunks", "A4"))

from a4_api import load_a4  # noqa: E402

# --- constants (R1; see BOOKKEEPING.md §2) ----------------------------------
# Reused unchanged from A0 / A3 / A4: below this a region cannot be judged by
# eye at the label grid, so it cannot carry render evidence either. (a)
MIN_REVIEWABLE_PX = 25

# Second triage tier — a **budget** decision, not an evidence one, and labelled
# as such so it is never mistaken for a measurement.
#
# Each per-instance call costs about $0.09, essentially all of it fixed CLI
# overhead, so the call count is the whole cost of the chunk. 129 components
# clear MIN_REVIEWABLE_PX; 73 clear this floor. The cut is made on **region
# size alone** and is blind to the ground truth — that matters, because a floor
# chosen by looking at which components are crop or weed would decide the
# experiment's own answer. The consequence is then measured rather than assumed:
# the 56 components below this floor hold **0.09 % of the ground-truth crop
# pixels and 0.00 % of the weed pixels**, and all four weed-majority components
# lie above it (see `tier_report()`).
#
# Components below it are labelled `unsure` by policy, in code, and are present
# in every output file — no ID is dropped (R2's default, applied by code).
# What the floor costs is audited directly rather than argued: `tier2_audit.py`
# asks the shipped prompt about a seeded random half of the 56 components the
# floor silences, and reports how many of them the model would have called
# `remove` — the only direction that can hurt under R2. (d) assumed — retired by
# a real budget, or by B1 deciding it from data across images.
TIER1_PX = 75
# A0's grid -> native scale. Fixed by the ground-truth contract. (a)
NATIVE_PER_LABEL_PX = 3.90625

GT_CROP_INSTANCE = 1              # A0 schema: the squash, one instance
GT_WEED_INSTANCES = range(2, 11)  # A0 schema: 9 broadleaf weeds
GT_GRASS = 255                    # A0 schema: grass, unresolved
MAT = {0: "unlabelled", 1: "squash_leaf", 2: "squash_petiole", 3: "grass",
       4: "broadleaf_weed", 5: "straw", 6: "soil", 7: "fruit", 8: "other"}


@dataclass
class Component:
    id: int
    px: int
    bbox: tuple                 # (x0, y0, x1, y1) on the 768x1024 label grid
    renderable: bool            # >= MIN_REVIEWABLE_PX: a render could carry evidence
    core: bool = False          # >= TIER1_PX: the model is actually asked about it
    # ground-truth accounting, label-grid pixels
    gt_crop_px: int = 0
    gt_weed_px: int = 0         # broadleaf weed instances 2..10
    gt_grass_px: int = 0
    gt_nonplant_px: int = 0     # straw / other / soil
    gt_unlabelled_px: int = 0
    gt_instances: dict = field(default_factory=dict)

    @property
    def gt_plant_px(self):
        return self.gt_crop_px + self.gt_weed_px + self.gt_grass_px

    @property
    def truth(self):
        """Majority truth over *plant* pixels, for the discrete confusion table.

        `crop` / `weed` / `grass` / `nonplant`.  Grass is kept as its own class
        rather than folded into `weed` because A0 declares it unresolved as an
        instance, and because the crop component holds 83 % of it — folding it
        in would hide exactly the hazard this chunk was told to probe.
        """
        if self.gt_plant_px == 0:
            return "nonplant"
        counts = {"crop": self.gt_crop_px, "weed": self.gt_weed_px,
                  "grass": self.gt_grass_px}
        return max(counts, key=counts.get)

    @property
    def contains_crop(self):
        return self.gt_crop_px > 0

    @property
    def crop_fraction(self):
        return self.gt_crop_px / self.gt_plant_px if self.gt_plant_px else 0.0


def load_components(tag: str = "merge"):
    """A4 components + the A0 ground-truth accounting for each."""
    a4 = load_a4(tag=tag)
    comp = a4.components
    gi = np.array(Image.open(os.path.join(ROOT, "groundtruth",
                                          "plants_instances.png")))
    gm = np.array(Image.open(os.path.join(ROOT, "groundtruth",
                                          "plants_material.png")))
    assert comp.shape == gi.shape == gm.shape, (comp.shape, gi.shape, gm.shape)

    out = {}
    for cid, npx in sorted(a4.sizes().items(), key=lambda kv: -kv[1]):
        m = comp == cid
        ys, xs = np.nonzero(m)
        gi_m, gm_m = gi[m], gm[m]
        inst, cnt = np.unique(gi_m, return_counts=True)
        out[cid] = Component(
            id=cid, px=int(npx),
            bbox=(int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max())),
            renderable=npx >= MIN_REVIEWABLE_PX,
            core=npx >= TIER1_PX,
            gt_crop_px=int((gi_m == GT_CROP_INSTANCE).sum()),
            gt_weed_px=int(((gi_m >= 2) & (gi_m <= 10)).sum()),
            gt_grass_px=int((gi_m == GT_GRASS).sum()),
            gt_nonplant_px=int(np.isin(gm_m, [5, 6, 8]).sum()),
            gt_unlabelled_px=int((gm_m == 0).sum()),
            gt_instances={int(i): int(c) for i, c in zip(inst, cnt)},
        )
    return a4, out


def totals(comps):
    """Scene-wide GT pixel totals, for the threshold-free R2 fractions."""
    return {
        "crop": sum(c.gt_crop_px for c in comps.values()),
        "weed": sum(c.gt_weed_px for c in comps.values()),
        "grass": sum(c.gt_grass_px for c in comps.values()),
    }


def tier_report(comps):
    """What each triage floor costs, in ground-truth mass rather than in words.

    The two floors are different kinds of claim and are reported separately:
    `MIN_REVIEWABLE_PX` is (a), a property of the label grid; `TIER1_PX` is (d),
    a budget. Both are blind to the ground truth by construction; this function
    is what checks, after the fact, what they happened to exclude.
    """
    tot = totals(comps)
    out = {"gt_pixel_totals": tot}
    for name, sel in (("below_min_reviewable", lambda c: not c.renderable),
                      ("tier2_silenced", lambda c: c.renderable and not c.core),
                      ("core_asked", lambda c: c.core)):
        g = [c for c in comps.values() if sel(c)]
        out[name] = {
            "n_components": len(g),
            "crop_px_fraction": sum(c.gt_crop_px for c in g) / tot["crop"],
            "weed_px_fraction": sum(c.gt_weed_px for c in g) / tot["weed"],
            "grass_px_fraction": sum(c.gt_grass_px for c in g) / tot["grass"],
            "truth_histogram": {t: sum(1 for c in g if c.truth == t)
                                for t in ("crop", "weed", "grass", "nonplant")},
        }
    return out


if __name__ == "__main__":
    import json
    a4, comps = load_components()
    print(json.dumps(tier_report(comps), indent=1, default=float))
    r = [c for c in comps.values() if c.renderable]
    print(f"components {len(comps)}  renderable {len(r)}  "
          f"triaged-unsure {len(comps) - len(r)}")
    print("truth histogram:", {t: sum(1 for c in r if c.truth == t)
                               for t in ("crop", "weed", "grass", "nonplant")})
    print("crop-bearing (any GT crop px):", sum(1 for c in r if c.contains_crop))
    print("totals:", totals(comps))
    for c in list(comps.values())[:6]:
        print(json.dumps({"id": c.id, "px": c.px, "truth": c.truth,
                          "crop_frac": round(c.crop_fraction, 4),
                          "inst": c.gt_instances}, default=str)[:220])
