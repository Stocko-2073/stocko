"""A6 — the loader A8 should import. Do not re-derive the volume.

    import sys; sys.path.insert(0, "chunks/A6")
    from a6_api import load_a6
    a6 = load_a6()                       # the shipped squash keep-out
    a6.is_inside(xyz)                    # (3,) or (N, 3) camera-frame rdu -> bool
    a6.classify(xyz)                     # OUTSIDE / INSIDE / UNKNOWN
    a6.clearance_rdu                     # the one constant, a PLACEHOLDER

Four things travel with this product and must not be dropped
------------------------------------------------------------
1. **`scale_confidence = "scale_free"`.** Every length is in rdu. The clearance
   is in rdu. When C3 finally measures a tool clearance it will arrive in
   millimetres and **cannot be compared to this number** until C0 supplies an
   absolute scale. A8 must not print a metre.
2. **The datum is the STRAW**, not soil (A2). The floor of the volume is the top
   of the mulch, offset from the soil by an unmeasured straw depth.
3. **The clearance is a placeholder** (category (b), tool geometry, awaiting
   C3). `results/sweeps.json` is what bounds it. Nothing in A6 is tuned to the
   shipped value.
4. **Crop identity came from A0 ground truth, not from A7.** `provenance`
   ["crop_identity"] says so in full. A8 replaces that one line and nothing
   else: R3 keeps the label (an ID) and the geometry (this volume) in separate
   places on purpose.

What it is honest about
-----------------------
* ``frame_open`` is True: 83 of the crop component's fragments run off the edge
  of the photograph. `classify()` returns **UNKNOWN**, not OUTSIDE, for a query
  that projects off-frame, and `is_inside` resolves UNKNOWN to *inside* by R2
  default.
* The volume already contains the material A4 could not decide about
  (``TIER_UNSEEN``) — 36 058 px behind 1 204 `occluded_by` links.
* The occupancy assumption ("everything between the canopy and the datum") is
  recorded in ``provenance["occupancy_assumption"]`` and is measurable: the
  ``shell`` variant in `results/sweeps.json` is the same volume without it.
"""
from __future__ import annotations

import os

from a6_common import DatumFrame, load_crop_component, load_gt, load_scene
from keepout import (CLEARANCE_SWEEP_RDU, DEFAULT_CELL_RDU,  # noqa: F401
                     DEFAULT_CLEARANCE_RDU, INSIDE, OUTSIDE, UNKNOWN,
                     KeepOutVolume, build_keepout, load_keepout)

HERE = os.path.dirname(os.path.abspath(__file__))
SHIPPED = os.path.join(HERE, "products", "keepout_squash_merge.npz")


def load_a6(path: str | None = None) -> KeepOutVolume:
    """The shipped keep-out volume for the squash, from disk. ~1 s."""
    return load_keepout(path or SHIPPED)


def keepout_for(component_id: int | None = None, *,
                policy: str = "merge",
                clearance: float = DEFAULT_CLEARANCE_RDU,
                cell: float = DEFAULT_CELL_RDU,
                scene=None, gt=None) -> KeepOutVolume:
    """Rebuild a keep-out volume for one A4 component. ~5 s, ~3.5 GB peak.

    ``component_id=None`` uses the component carrying A0's crop instance — the
    stand-in for A7. A8 passes the id A7's label attaches to instead.
    """
    scene = scene or load_scene()
    gt = gt or load_gt()
    crop = load_crop_component(policy, gt=gt)
    if component_id is not None and int(component_id) != crop.component_id:
        raise NotImplementedError(
            "A6 ships one built volume, for the component carrying A0's crop "
            "instance. Building for an arbitrary component id is A8's job once "
            "A7's labels exist; the machinery is `a6_common.load_crop_component` "
            "plus `keepout.build_keepout`, which take a component mask and know "
            "nothing about which component is crop.")
    return build_keepout(scene, crop, cell=cell, clearance=clearance,
                         frame=DatumFrame.from_scene(scene))
