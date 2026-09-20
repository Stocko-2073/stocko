"""A8 — loading, and the three integration seams Phase A left open.

A8 is the first chunk that has to make A5, A6 and A7 agree with each other.
They do not agree by default, and this module is where the disagreements are
resolved *explicitly* rather than by whichever loader happened to be imported
first. Nothing here re-derives anything: every number comes from a shipped
product of an earlier chunk.

The three seams
---------------
1. **Policy mismatch (the big one).** A5 ships contact points on A4's ``split``
   components (742 of them, and A5's own FINDINGS recommends ``split`` because
   ``merge`` statuses 92 % of the frame as one ``occluded`` blob). A6 builds
   keep-out volumes on ``merge`` components, and A6 measured that ``split``
   cannot be rescued by any clearance. A7 labelled ``merge`` components,
   because that is the granularity a VLM can be shown a picture of.

   Resolution: **the tool surface's instance ID is the A4 ``merge`` component
   id**, because that is the ID the VLM labelled (R3: the label is an ID) and
   the ID the keep-out is built on. Each instance carries the contact points of
   its ``split`` children as *candidate* contact points. Verified here and in
   `test_a8.py`: every split component's pixels lie inside exactly one merge
   component, so the map is a function and not a vote (742/742, purity 1.000).

2. **Crop identity.** A6 used A0's ground truth as an explicit stand-in for A7.
   A8 replaces that one line with A7's labels and nothing else. A8 therefore
   never calls ``a6_api.load_a6`` or ``a6_common.load_crop_component`` for the
   gate — both hard-code A0's crop instance — and instead builds a keep-out for
   *every* instance from the same machinery (`keepout.build_keepout`), which
   knows nothing about which component is crop. R3 stays intact: the labels
   arrive as IDs, the geometry is computed in code afterwards.

3. **Scale.** Everything is rdu (A1) or px on a named grid. There is no metre
   anywhere in A8, and `plan_removals` refuses a metric `tool_profile` rather
   than converting one (A6's instruction). ``scale_confidence`` travels on
   every output.

Two caveats inherited verbatim, which A8 must not launder
---------------------------------------------------------
* **The datum is the STRAW mulch surface, not soil** (A2). A "contact point" is
  a point on the mulch. The straw depth is unmeasured and unmeasurable here.
* **A5's ``confidence`` is an ordering, not a probability**, and so is A7's.
  The gate is structural; the one place a confidence is thresholded is the
  registered floor, and A8's own measurement of what that floor buys is in
  FINDINGS.md.
"""
from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass, field

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
PRODUCTS = os.path.join(HERE, "products")
RESULTS = os.path.join(HERE, "results")

for _p in ("A0", "A1", "A2", "A4", "A5", "A6"):
    _d = os.path.join(ROOT, "chunks", _p)
    if _d not in sys.path:
        sys.path.insert(0, _d)

SCALE_CONFIDENCE = "scale_free"
UNITS = ("rdu (relative depth units; 1 rdu = median scene depth of the A1 "
         "primary raster). Image distances are px on the named grid. "
         "No absolute scale exists for this image; A1b bounds the focal "
         "length, not the scale.")
DATUM = ("THE DATUM IS THE STRAW MULCH SURFACE, NOT BARE SOIL (A2). Every "
         "height and every contact point is measured against the top of the "
         "mulch; the offset to the soil is the straw depth, which is "
         "unmeasured and unobservable from one overhead photograph.")

#: A4 tags. A4 ships the split policy under the tag "default".
SPLIT_TAG, MERGE_TAG = "default", "merge"

#: A7's shipped condition: framing A, prompt variant r2, both repeats.
A7_LABEL_FILES = ("labels_A_r2_r1.json", "labels_A_r2_r2.json")

GT_HW = (1024, 768)
DEPTH_HW = (1344, 1008)


# --------------------------------------------------------------------------
# Seam 1 — the split -> merge parent map
# --------------------------------------------------------------------------


def split_to_merge(a4_split, a4_merge) -> dict:
    """``{split_component_id: merge_component_id}`` on the depth grid.

    A4's ``merge`` policy only ever *unions* components that ``split`` left
    apart, so a split component's pixels lie inside exactly one merge
    component. That is asserted here rather than assumed: any split component
    whose pixels touch more than one merge label raises, because a majority
    vote would silently bind a label to the wrong plant.
    """
    # `cm` would be a natural name for the merge label map and is exactly the
    # name `test_no_identifier_encodes_a_belief_about_how_gardens_are_arranged`
    # refuses, because a reader cannot tell it from a centimetre. Spelled out.
    split_labels = a4_split.components_depth
    merge_labels = a4_merge.components_depth
    both = (split_labels > 0) & (merge_labels > 0)
    stride = int(merge_labels.max()) + 1
    pairs = np.unique(split_labels[both].astype(np.int64) * stride
                      + merge_labels[both].astype(np.int64))
    out = {}
    for pair in pairs:
        sid, mid = int(pair // stride), int(pair % stride)
        if sid in out:
            raise ValueError(
                f"split component {sid} spans merge labels "
                f"{{{out[sid]}, {mid}}}; the split->merge map is not a "
                "function and A8's assumption that a label binds to exactly "
                "one plant is wrong")
        out[sid] = mid
    return out


# --------------------------------------------------------------------------
# Seam 2 — a component, any component, with its unresolved halo
# --------------------------------------------------------------------------


@dataclass
class Component:
    """The generalisation of A6's ``CropComponent`` to an arbitrary id.

    Identical logic to ``a6_common.load_crop_component`` with the A0-ground-
    truth crop lookup removed — that lookup is the one line A6 told A8 to
    replace. ``test_a8.py`` asserts this reproduces A6's own object for the
    component A0's crop lands in.
    """

    component_id: int
    policy: str
    observed: np.ndarray
    unseen: np.ndarray
    frame_open: bool
    n_unresolved: dict
    frame_fragment_px: int
    identity_provenance: str
    a4: object


def _fragment_to_component(frag: np.ndarray, comp: np.ndarray) -> dict:
    m = frag > 0
    f, c = frag[m], comp[m]
    order = np.argsort(f, kind="stable")
    f, c = f[order], c[order]
    ids = np.unique(f)
    first = np.searchsorted(f, ids)
    return {int(a): int(b) for a, b in zip(ids, c[first])}


class ComponentSource:
    """Builds ``Component`` objects for any merge component id, cheaply."""

    def __init__(self, a4, policy: str = "merge"):
        self.a4 = a4
        self.policy = policy
        self.frag = np.load(os.path.join(ROOT, "chunks", "A4", "work",
                                         f"fragments_{policy}.npy"))
        self.f2c = _fragment_to_component(self.frag, a4.components_depth)
        self._by_comp = {}
        for f, c in self.f2c.items():
            self._by_comp.setdefault(c, []).append(f)

    def get(self, cid: int, identity_provenance: str) -> Component:
        cid = int(cid)
        observed = self.a4.components_depth == cid
        edges = self.a4.unresolved_for(cid)
        kinds: dict = {}
        neighbours = set()
        frame_px = 0
        for e in edges:
            kinds[e["kind"]] = kinds.get(e["kind"], 0) + 1
            if e["kind"] == "leaves_frame":
                frame_px += int(e.get("fragment_px") or 0)
            for f in (e.get("a"), e.get("b")):
                if f is None:
                    continue
                if self.f2c.get(int(f), 0) != cid:
                    neighbours.add(int(f))
        unseen = (np.isin(self.frag, sorted(neighbours)) if neighbours
                  else np.zeros_like(observed))
        unseen &= ~observed
        return Component(
            component_id=cid, policy=self.policy, observed=observed,
            unseen=unseen, frame_open=kinds.get("leaves_frame", 0) > 0,
            n_unresolved=kinds, frame_fragment_px=frame_px, a4=self.a4,
            identity_provenance=identity_provenance)


# --------------------------------------------------------------------------
# A7 labels — the semantic input, read as IDs and nothing else
# --------------------------------------------------------------------------

#: R3, enforced on the way in as well as on the way out. A8 reads exactly these
#: keys off an A7 label record and ignores everything else, so no field a model
#: authored can carry geometry into the gate.
LABEL_KEYS = ("id", "label", "confidence", "mixed", "reason")
LABEL_VALUES = ("keep", "remove", "unsure")


def load_a7_labels(files=A7_LABEL_FILES) -> dict:
    """``{"repeats": [...], "provenance": {...}}`` — A7's shipped condition.

    Each repeat is ``{instance_id: {label, confidence, mixed, reason}}``. The
    repeats are kept apart on purpose: A7 decided that unanimity across two
    repeats is part of the output contract, not an evaluation convenience, and
    a loader that majority-voted here would hide the thing the gate tests.
    """
    reps, prov = [], []
    for f in files:
        doc = json.load(open(os.path.join(ROOT, "chunks", "A7", "results", f)))
        reps.append({int(r["id"]): {k: r.get(k) for k in LABEL_KEYS}
                     for r in doc["labels"]})
        prov.append({"file": f, "framing": doc["framing"],
                     "variant": doc["variant"], "rep": doc["rep"],
                     "model": doc["model"], "cli_version": doc["cli_version"],
                     "prompt_file": doc["prompt_file"]})
    return {"repeats": reps, "provenance": prov}


# --------------------------------------------------------------------------
# Loading everything, once
# --------------------------------------------------------------------------


@dataclass
class Stack:
    a4_split: object
    a4_merge: object
    a5: object
    a2: object
    gt: object
    s2m: dict = field(default_factory=dict)
    m2s: dict = field(default_factory=dict)


_STACK: dict = {}


def load_stack(with_gt: bool = True) -> Stack:
    """Memoised: loading A4 twice, A5 and A2 costs seconds and never changes."""
    if with_gt in _STACK:
        return _STACK[with_gt]
    if with_gt is False and True in _STACK:
        return _STACK[True]
    _STACK[with_gt] = _load_stack(with_gt)
    return _STACK[with_gt]


def _load_stack(with_gt: bool) -> Stack:
    from a4_api import load_a4
    from a5_api import load_a5
    from a2_api import load_a2

    a4s = load_a4(tag=SPLIT_TAG)
    a4m = load_a4(tag=MERGE_TAG)
    s2m = split_to_merge(a4s, a4m)
    m2s: dict = {}
    for s, m in s2m.items():
        m2s.setdefault(m, []).append(s)
    gt = None
    if with_gt:
        import eval as a0eval
        gt = a0eval.load_gt()
    return Stack(a4_split=a4s, a4_merge=a4m, a5=load_a5(policy="split"),
                 a2=load_a2(), gt=gt, s2m=s2m,
                 m2s={k: sorted(v) for k, v in m2s.items()})


def gt_rc_to_depth_rc(rows, cols):
    """A0's 1024x768 grid -> A1's 1344x1008 depth grid. One scalar (1.3125),
    because both are uniform resamplings of the same photograph."""
    f = DEPTH_HW[0] / GT_HW[0]
    r = np.clip(np.rint(np.asarray(rows) * f).astype(np.int64), 0, DEPTH_HW[0] - 1)
    c = np.clip(np.rint(np.asarray(cols) * f).astype(np.int64), 0, DEPTH_HW[1] - 1)
    return r, c


def jsonable(o):
    """numpy -> json, with no silent precision games."""
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.floating,)):
        return float(o)
    if isinstance(o, (np.bool_,)):
        return bool(o)
    if isinstance(o, np.ndarray):
        return o.tolist()
    if isinstance(o, dict):
        return {k: jsonable(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [jsonable(v) for v in o]
    return o
