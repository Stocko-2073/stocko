"""A5 — the loader A8 should import. Do not re-derive the points.

    import sys; sys.path.insert(0, "chunks/A5")
    from a5_api import load_a5
    a5 = load_a5()                      # policy="split" (A4's default)
    a5 = load_a5(policy="merge")
    a5.by_component[37].status          # observed | extrapolated | occluded
    a5.by_component[37].point           # None when the status is `occluded`
    a5.by_component[37].lowest_visible_point        # always present
    a5.admissible()                     # the only components R2 may remove

Five things that travel with every point and must not be dropped
----------------------------------------------------------------
1. **`scale_confidence = "scale_free"`.** 3-D distances are in rdu, image
   distances in px on the named grid. There is no metre here.
2. **The datum is the STRAW** (A2), so a contact point is a point on the mulch.
   Height above *soil* is offset from it by the straw depth, which is unmeasured
   and unmeasurable from this photograph.
3. **`status` is the safety field, not `confidence`.** Under R2 a removal needs
   `observed`; `extrapolated` is a guess with its distance attached, and
   `occluded` has no point at all. `admissible()` applies that rule in code.
4. **`confidence` is an ordering, not a probability.** It is the product of
   three measured factors (datum support, axis wander, extrapolated distance).
   It is not calibrated against anything, because nothing in this image could
   calibrate it.
5. **`observed` here means "the material reaches the STRAW".** On `plants.jpeg`
   no stem is seen meeting the soil — A0 found zero `visible` contact points —
   and A5 cannot invent one. See FINDINGS.md § "enters soil vs lowest visible".

What it measured (RESULTS / FINDINGS; A0's `eval.py` is the scorer)
-------------------------------------------------------------------
`split` (742 components): 472 observed / 59 extrapolated / 211 occluded, zero
fabricated points. `merge` (207): 164 / 11 / 32. The roadmap's done-criterion
"contact-point error over `visible` GT points" is **empty** for this image.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass

HERE = os.path.dirname(os.path.abspath(__file__))
PRODUCTS = os.path.join(HERE, "products")
POLICY_FILE = {"split": "contacts_split.json", "merge": "contacts_merge.json",
               "gt_instances": "contacts_gt_instances.json"}


@dataclass
class ContactRecord:
    raw: dict

    def __getattr__(self, k):
        try:
            return self.raw[k]
        except KeyError as e:                       # pragma: no cover
            raise AttributeError(k) from e


@dataclass
class A5Product:
    policy: str
    components: list
    by_component: dict
    status_counts: dict
    constants: dict
    scale_confidence: str
    datum: str
    product_target: str

    def admissible(self):
        """R2's geometric precondition for a removal, enforced in code: the
        contact was **observed**, the datum under it was itself **observed**
        rather than interpolated, and the component has no `leaves_frame`
        unresolved edge (A4) that could mean the plant continues off-frame.

        Being admissible is necessary, never sufficient — A8 still needs the
        VLM's label and the keep-out test from A6.
        """
        return [c for c in self.components if c.raw["arm_admissible"]]

    def points_for_eval(self):
        """`{component_id: (x, y)}` on A0's 768x1024 grid, for `eval.py`.
        Components with no defensible point are absent, not zero-filled."""
        return {c.raw["component"]: tuple(c.raw["point"]["gt_grid_xy"])
                for c in self.components if c.raw["point"]}


def load_a5(policy: str = "split", products: str | None = None) -> A5Product:
    p = products or PRODUCTS
    doc = json.load(open(os.path.join(p, POLICY_FILE[policy])))
    cs = [ContactRecord(c) for c in doc["components"]]
    return A5Product(
        policy=doc["policy"], components=cs,
        by_component={c.raw["component"]: c for c in cs},
        status_counts=doc.get("status_counts", {}), constants=doc["constants"],
        scale_confidence=doc["scale_confidence"], datum=doc["DATUM"],
        product_target=doc["product_target"])
