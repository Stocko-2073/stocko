"""A4 — the loader A5 / A6 / A7 should import. Do not re-derive the graph.

    import sys; sys.path.insert(0, "chunks/A4")
    from a4_api import load_a4
    a4 = load_a4()
    a4.components          # (1024, 768) int32 on A0's label grid, 0 = not plant
    a4.components_depth    # (1344, 1008) int32 on the A1 depth grid
    a4.unresolved          # the edges the graph refused to decide
    a4.component_ids()     # ids present, largest first

Three things that travel with every component and must not be dropped
---------------------------------------------------------------------
1. **`scale_confidence = "scale_free"`.** Every distance is in rdu. There is no
   metre in this product and A1b has not landed.
2. **The datum is the STRAW**, not soil (A2). A5's contact point is a point on
   the mulch, offset from the soil by an unmeasured straw depth.
3. **A component is a connected piece of observed material, not a proof of a
   plant.** `unresolved_for(component)` returns the links that would have
   changed its extent had a second viewpoint been available. Under R2 and R4, a
   component carrying unresolved edges is not evidence that the plant ends
   there. A6 in particular must treat an unresolved edge on the crop component
   as keep-out volume it cannot see, not as empty space.

What it scores (see RESULTS / FINDINGS; A0 `eval.py` is the scorer)
-------------------------------------------------------------------
Shipped configuration (`unresolved -> split`): instance F1 **0.0088** against a
recorded ZeroPlantSeg baseline of **0.0000**; squash best IoU **0.462** against
0.425; **11.8 %** of ground-truth grass absorbed into the crop component against
**53.0 %**. The squash does **not** come out as one component. The `merge`
variant (`load_a4(policy="merge")`) does — squash IoU 0.885 — and absorbs 83 %
of the grass. Both are shipped, because R2 and R4 point in opposite directions
here and this chunk could not settle it from one image.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
PRODUCTS = os.path.join(HERE, "products")


@dataclass
class A4Product:
    components: np.ndarray          # (1024, 768) int32, A0 grid
    components_depth: np.ndarray    # (1344, 1008) int32, A1 depth grid
    unresolved: list
    scores: dict
    scale_confidence: str
    datum: str
    policy: str

    def component_ids(self):
        ids, cnt = np.unique(self.components[self.components > 0],
                             return_counts=True)
        return [int(i) for i in ids[np.argsort(-cnt)]]

    def sizes(self):
        ids, cnt = np.unique(self.components[self.components > 0],
                             return_counts=True)
        return {int(i): int(c) for i, c in zip(ids, cnt)}

    def unresolved_for(self, component_id: int):
        """Every recorded link that touches this component and was not decided."""
        return [e for e in self.unresolved
                if component_id in (e.get("components") or [])
                and not e.get("already_connected")]

    def is_uncertain(self, component_id: int) -> bool:
        """R4: does this component have an undecided boundary anywhere?"""
        return bool(self.unresolved_for(component_id))


def load_a4(products: str | None = None, tag: str = "default") -> A4Product:
    p = products or PRODUCTS
    scores = json.load(open(os.path.join(p, "..", "results",
                                         f"a4_scores_{tag}.json")))
    edges = json.load(open(os.path.join(p, f"unresolved_edges_{tag}.json")))
    return A4Product(
        components=np.load(os.path.join(p, f"components_gt_grid_{tag}.npy")),
        components_depth=np.load(os.path.join(p, f"components_depth_grid_{tag}.npy")),
        unresolved=edges["edges"],
        scores=scores,
        scale_confidence=scores["scale_confidence"],
        datum=scores["provenance"]["a2"]["datum"],
        policy=scores.get("unresolved_policy", "split"))
