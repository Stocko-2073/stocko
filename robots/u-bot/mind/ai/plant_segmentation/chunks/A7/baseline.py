"""A7 — the no-VLM baseline the semantic layer has to beat.

There is no recorded VLM baseline to compare against: A7 is the first chunk with
a semantic model in it. The right comparison is therefore the decision the stack
could already make **without** one — A3's material classifier, voted per A4
component, which is exactly the policy A4's Open Question 2 table scored
("deciding crop-vs-weed per component by majority puts 1.65 % of the crop under
the tool"). It is recomputed here on the same 207 components so the numbers are
apples to apples, and it emits the same label schema as the VLM does.

Two further reference points, both trivial and both worth having on the page:

* `all_keep` — R2's degenerate optimum. Zero crop at risk, zero weed reached.
* `all_remove` — the opposite corner, for scale.
"""
from __future__ import annotations

import os

import numpy as np

from a7_data import ROOT, load_components

A3_MATERIAL = os.path.join(ROOT, "chunks", "A4", "work", "a3_material.npz")
# A0 / A3 class ids
WEEDY = {3, 4}                 # grass, broadleaf_weed
CROPPY = {1, 2, 7}             # squash_leaf, squash_petiole, fruit


def a3_majority_labels(comps, a4):
    m = np.load(A3_MATERIAL)["m"]
    out = []
    for c in comps.values():
        mask = a4.components == c.id
        cls, cnt = np.unique(m[mask], return_counts=True)
        top = int(cls[np.argmax(cnt)])
        if top in WEEDY:
            lab, why = "remove", f"A3 majority class {top} (weedy)"
        elif top in CROPPY:
            lab, why = "keep", f"A3 majority class {top} (crop)"
        else:
            lab, why = "keep", f"A3 majority class {top} (not a plant)"
        out.append({"id": c.id, "label": lab, "confidence": 1.0,
                    "reason": why, "mixed": False, "mixed_note": "",
                    "r3_soft": []})
    return out


def constant_labels(comps, label):
    return [{"id": c.id, "label": label, "confidence": 1.0,
             "reason": f"constant baseline: {label}", "mixed": False,
             "mixed_note": "", "r3_soft": []} for c in comps.values()]


def build():
    a4, comps = load_components()
    return {
        "a3_majority": {"framing": "baseline", "variant": "a3_majority",
                        "rep": 0, "model": "none (A3 material classifier)",
                        "labels": a3_majority_labels(comps, a4)},
        "all_keep": {"framing": "baseline", "variant": "all_keep", "rep": 0,
                     "model": "none", "labels": constant_labels(comps, "keep")},
        "all_remove": {"framing": "baseline", "variant": "all_remove", "rep": 0,
                       "model": "none",
                       "labels": constant_labels(comps, "remove")},
    }


if __name__ == "__main__":
    import json
    b = build()
    os.makedirs(os.path.join(os.path.dirname(__file__), "results"),
                exist_ok=True)
    for k, v in b.items():
        p = os.path.join(os.path.dirname(__file__), "results",
                         f"labels_baseline_{k}_r0.json")
        json.dump(v, open(p, "w"), indent=1)
        n = {"keep": 0, "remove": 0, "unsure": 0}
        for l in v["labels"]:
            n[l["label"]] += 1
        print(k, n)
