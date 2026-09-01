"""A4 — shared substrate: grids, inputs, and the registered constants.

Nothing here decides anything. It loads the three upstream products A4 is built
on and states, in one place, every numeric constant the code path uses.

The grids
---------
Three grids are in play and they are kept explicit, because silently resampling
depth is exactly the mistake A1 measured the cost of.

* **native**  3000 x 4000 — the photograph. Nothing in A4 runs here.
* **depth**   1008 x 1344 (W x H) — A1 `primary_raster`. **The graph is built
  here**, on the float depth as produced, with no resampling of the depth at
  all. A2's rasters are already on this grid.
* **GT**      768 x 1024 — A0's label grid. The A3 material map and the A3 SAM
  partition live here and are lifted to the depth grid by nearest neighbour
  (they are label maps; they may never be interpolated). The finished component
  map is brought *back* to this grid, nearest, for scoring.

The depth grid is 1.3125x the GT grid in both axes, exactly.

Constants
---------
Every number below is registered in `CONSTANTS.md`. **There is no spacing,
radius, `eps`, or distance-between-plants constant in this file or anywhere else
in A4** — that absence is the point of the chunk, and `test_a4.py` asserts it by
grepping the code path.
"""
from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
WORK = os.path.join(HERE, "work")
RESULTS = os.path.join(HERE, "results")
FIGS = os.path.join(HERE, "figs")
PRODUCTS = os.path.join(HERE, "products")

sys.path.insert(0, os.path.join(ROOT, "chunks", "A0"))
sys.path.insert(0, os.path.join(ROOT, "chunks", "A2"))
sys.path.insert(0, os.path.join(ROOT, "chunks", "A3"))

import eval as a0eval  # noqa: E402

GT_H, GT_W = 1024, 768
DEPTH_H, DEPTH_W = 1344, 1008

# --- registered constants ----------------------------------------------------
#
# (a) instrument — A1's local-planarity p10, read at the window the link
#     stencil actually spans. The stencil is a 5x5 plane fit centred on one
#     pixel plus a one-pixel step to its neighbour: 7 px across. win9 is the
#     smallest registered window that contains it. Fixed a priori, before any
#     score was computed; swept over 0.25x..100x in `sweeps.py`.
LOCAL_PLANARITY_P10_RDU = {3: 2.9462945118460555e-05,
                           5: 6.670238333267323e-05,
                           9: 0.00012895677396270323,
                           17: 0.00027119812111501353,
                           33: 0.0005673600187500496}
CONTINUITY_WINDOW = 9
CONTINUITY_TOL_RDU = LOCAL_PLANARITY_P10_RDU[CONTINUITY_WINDOW]

# (a) instrument — the plane fit's support. 5x5 is the smallest odd window that
#     gives a least-squares plane (3 parameters) a usable overdetermination.
FIT_WINDOW = 5

# (a) instrument — A1's registered depth resolution floor. Used only as a
#     refusal: a tolerance below this would be meaningless.
DEPTH_RESOLUTION_FLOOR_RDU = 4.145862809411695e-05

# (a) instrument — pixel adjacency, as the roadmap specifies.
CONNECTIVITY = 8

# (a) instrument / stencil — a fragment smaller than the plane fit's own support
#     (5x5 = 25 px) carries no surface to test continuity against, so it is
#     merged into the neighbour it shares the longest boundary with rather than
#     being given a fabricated one. Numerically identical to A0's registered
#     "min reviewable region" and A3's `MIN_REGION`, and reused deliberately.
MIN_FRAGMENT_PX = 25

# (c) convention, documented and swappable, swept in `sweeps.py` — a shared
#     boundary is judged by its quartiles, not its mean, so a handful of leaking
#     pixels cannot merge two plants and a handful of noisy ones cannot split
#     one. p75 <= tol => connected; p25 > tol => separated; anything else is
#     recorded as an unresolved edge rather than decided.
LINK_QUANTILE_LO, LINK_QUANTILE_HI = 25.0, 75.0

PLANT_CLASSES = ["squash_leaf", "squash_petiole", "grass", "broadleaf_weed", "fruit"]
PLANT_IDS = np.array(sorted(a0eval.CID[c] for c in PLANT_CLASSES))


@dataclass
class Inputs:
    """Everything A4 reads, all on the depth grid unless the name says GT."""
    relief: np.ndarray        # (H, W) float32 rdu, datum depth - scene depth
    depth_rdu: np.ndarray     # (H, W) float32 rdu, z-depth as A1 produced it
    soil_depth: np.ndarray    # (H, W) float32 rdu, A2 datum along each ray
    height_sigma: np.ndarray  # (H, W) float32 rdu, A2 datum uncertainty
    a2_valid: np.ndarray      # (H, W) bool
    coverage: np.ndarray      # (H, W) uint8 0=observed 1=interp 2=extrap
    material: np.ndarray      # (H, W) uint8, A3 class ids on the depth grid
    material_gt: np.ndarray   # (GT_H, GT_W) uint8, A3 as shipped
    confidence_gt: np.ndarray  # (GT_H, GT_W) float32, A3 probe prob (never gates)
    regions: np.ndarray       # (H, W) int32, A3's independent SAM partition
    plant: np.ndarray         # (H, W) bool, material in PLANT_IDS and depth valid
    provenance: dict


def _nearest_to_depth_grid(a: np.ndarray) -> np.ndarray:
    """Lift a GT-grid label map to the depth grid. Nearest only, never bilinear."""
    yy = np.minimum(np.arange(DEPTH_H) * GT_H // DEPTH_H, GT_H - 1)
    xx = np.minimum(np.arange(DEPTH_W) * GT_W // DEPTH_W, GT_W - 1)
    return a[yy[:, None], xx[None, :]]


def to_gt_grid_nearest(a: np.ndarray) -> np.ndarray:
    """Bring a depth-grid label map down to A0's 768x1024 grid. Nearest only."""
    yy = np.minimum(np.arange(GT_H) * DEPTH_H // GT_H, DEPTH_H - 1)
    xx = np.minimum(np.arange(GT_W) * DEPTH_W // GT_W, DEPTH_W - 1)
    return a[yy[:, None], xx[None, :]]


def load_inputs(material_source: str = "a3", use_cache: bool = True) -> Inputs:
    """Load A1 depth, A2 datum and A3 material onto the depth grid.

    `material_source`:
      * ``"a3"``  — `chunks/A3/a3_api.segment_material()`, the shipped default.
      * ``"gt"``  — A0's ground-truth material map. **Diagnostic only.** It
        answers "how much of A4's error is A3's material map", and every number
        computed from it is labelled `oracle_material` and never reported as an
        A4 score.
    """
    a1man = json.load(open(os.path.join(ROOT, "chunks/A1/products/MANIFEST.json")))
    prod = a1man["products"]["primary_raster"]
    depth_raw = np.load(os.path.join(ROOT, "chunks/A1", prod["depth"]))
    a2man = json.load(open(os.path.join(ROOT, "chunks/A2/products/A2_MANIFEST.json")))
    normaliser = float(a2man["source"]["rdu_normaliser_depth_units"])
    depth_rdu = (depth_raw / normaliser).astype(np.float32)

    from a2_api import load_a2
    a2 = load_a2()
    assert a2.soil_depth.shape == depth_rdu.shape, "A2 is not on the A1 depth grid"

    if material_source == "a3":
        cache = os.path.join(WORK, "a3_material.npz")
        if use_cache and os.path.exists(cache):
            z = np.load(cache)
            mat_gt, conf_gt, a3prov = z["m"], z["c"], json.loads(str(z["p"]))
        else:
            from a3_api import segment_material
            out = segment_material()
            mat_gt, conf_gt, a3prov = out.material, out.confidence, out.provenance
            os.makedirs(WORK, exist_ok=True)
            np.savez(cache, m=mat_gt, c=conf_gt, p=json.dumps(a3prov, default=str))
    elif material_source == "gt":
        gt = a0eval.load_gt()
        mat_gt = gt.material.copy()
        conf_gt = np.ones(mat_gt.shape, np.float32)
        a3prov = {"oracle_material": True,
                  "note": "A0 ground-truth material — diagnostic only"}
    else:
        raise ValueError(material_source)

    regions_gt = np.load(os.path.join(ROOT, "chunks/A3/work/regions_a3f.npy"))
    material = _nearest_to_depth_grid(mat_gt)
    regions = _nearest_to_depth_grid(regions_gt).astype(np.int32)

    depth_ok = np.isfinite(depth_rdu) & (depth_rdu > 0)
    plant = np.isin(material, PLANT_IDS) & depth_ok

    relief = (a2.soil_depth - depth_rdu).astype(np.float32)

    return Inputs(
        relief=relief, depth_rdu=depth_rdu, soil_depth=a2.soil_depth,
        height_sigma=a2.height_sigma, a2_valid=a2.valid, coverage=a2.coverage,
        material=material, material_gt=mat_gt, confidence_gt=conf_gt,
        regions=regions, plant=plant,
        provenance={
            "chunk": "A4",
            "scale_confidence": "scale_free",
            "units": "rdu (relative depth units; 1 rdu = median scene depth)",
            "DATUM": a2.datum,
            "grid": {"graph_built_on": [DEPTH_H, DEPTH_W],
                     "scored_on": [GT_H, GT_W],
                     "depth_resampled": False,
                     "material_and_regions_lifted": "nearest, GT -> depth grid"},
            "a1": {"product": "primary_raster",
                   "model": a1man["model"],
                   "rdu_normaliser_depth_units": normaliser},
            "a2": {"datum": a2.datum,
                   "sigma_datum_rdu": a2.sigma_datum,
                   "soil_surface_depth_subtracted": True},
            "a3": {"material_source": material_source, "provenance": a3prov},
            "partition": {"source": "chunks/A3/work/regions_a3f.npy",
                          "n_regions": int(regions_gt.max()),
                          "why": "A3's independent SAM partition (pps 64, oracle "
                                 "ceiling 0.9246). A0's own partition has a "
                                 "ceiling of exactly 1.0 and is not used."},
        })


def gt_grid_scale() -> float:
    """Depth-grid px per GT-grid px. Exactly 1.3125."""
    return DEPTH_H / GT_H
