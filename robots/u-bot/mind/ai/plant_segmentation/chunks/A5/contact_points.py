"""A5 — where a plant's material meets the datum, with an honest status.

The output the arm needs, and the honesty rules that go with it
---------------------------------------------------------------
For every component handed in (A4's, under either policy), A5 emits:

* `lowest_visible_point` — the lowest point of the component's own observed
  material. **Always present**, because it is an observation.
* `lowest_visible_stem_point` — the same, restricted to material A3 calls
  `squash_petiole`. `null` where the component has no stem material; A0's and
  A3's label space has exactly one stem class, so for a weed this is
  legitimately absent and is reported absent rather than substituted.
* `contact` — the point where the plant meets the datum, with
  `status ∈ {observed, extrapolated, occluded}`:

  | status | meaning |
  |---|---|
  | `observed` | material is visible down into the datum's own 3σ ground band |
  | `extrapolated` | the basal material's 3-D axis was continued to the datum across a gap; `extrapolation_distance_rdu` and a confidence derived from it are reported |
  | `occluded` | no defensible estimate — the point is `null` |

  **An `occluded` component gets `"point": null`.** Nothing is filled in. R4.

**The datum is the STRAW** (A2), so every contact point here is a point on the
mulch, offset from the soil by the unmeasured straw depth. See FINDINGS.md for
the "enters soil vs. lowest visible stem" decision this chunk had to take.

Constants
---------
Every constant is a module-level name with its R1 category in the comment, and
`test_a5.py` fails if one appears that is not in the registered allow-list.
There is exactly one (b) placeholder — `MAX_EXTRAPOLATION_SIGMA` — and the
extrapolation distance is measured to a generous ceiling regardless of it, so
the sweep over it is exact rather than a re-run.
"""
from __future__ import annotations

import json
import math
import warnings
from dataclasses import asdict, dataclass, field

import numpy as np
from scipy import ndimage

from a5_common import (FOLIAGE_CLASSES, MATERIAL, STEM_CLASS, Scene,
                       depth_xy_to_gt_xy)

# ----------------------------------------------------------------- constants
# (c) convention, inherited unchanged from A2's registered "ground band
# multiplier" (2-5σ swept there). Material within k·σ of the datum is *at* the
# datum: that is what A2 means by ground.
GROUND_BAND_K = 3.0

# (c) convention. Two heights that differ by less than one combined datum σ are
# not distinguishable, so the "lowest material" is a band, not a pixel.
BASAL_BAND_K = 1.0

# (a) instrument. Smallest odd window; a boundary pixel of a component mixes
# material depth with background depth, so heights are read as the median over
# the 3×3 neighbourhood *inside the component*. MIN_MEDIAN_SUPPORT = 3 is what
# a one-pixel-wide stem supplies, so thin structure is not eroded away.
MEDIAN_WINDOW = 3
MIN_MEDIAN_SUPPORT = 3

# (a) instrument. 3×3 = 9 points is the smallest support that overdetermines a
# 3-D line; below it a direction is not measured, it is chosen.
MIN_AXIS_POINTS = 9

# (b) TOOL GEOMETRY — PLACEHOLDER, AWAITING PHASE C (C3 picks the tool and
# measures its precision budget). Expressed in datum roughnesses because Phase A
# is scale-free and σ_datum is the only length this scene supplies. It caps both
# how far a stem may be continued and how much lateral wander that continuation
# may accumulate. The measured extrapolation distances are published as a full
# CDF so C3 can read its own value off the curve instead of inheriting this one.
MAX_EXTRAPOLATION_SIGMA = 20.0

# Reporting ceiling, not a threshold: the march stops here so a runaway ray
# terminates. 1 rdu is the median scene depth — no extrapolation the length of
# the whole scene is ever going to be accepted by any tool.
MARCH_CEILING_RDU = 1.0


@dataclass
class Contact:
    component: int
    n_px: int
    # ---- the observation, always present
    lowest_visible_point: dict | None = None
    lowest_visible_stem_point: dict | None = None
    # ---- the estimate, honestly statused
    status: str = "occluded"
    reason: str = ""
    point: dict | None = None
    extrapolation_distance_rdu: float | None = None
    extrapolation_distance_sigma: float | None = None
    extrapolation_px_gt: float | None = None
    lateral_uncertainty_rdu: float | None = None
    axis_half_angle_deg: float | None = None
    confidence: float | None = None
    confidence_terms: dict = field(default_factory=dict)
    # ---- what the estimate rests on
    datum_coverage: str | None = None
    datum_sigma_rdu: float | None = None
    height_at_base_rdu: float | None = None
    height_at_base_sigma: float | None = None
    occluder: str | None = None
    occluder_profile: dict = field(default_factory=dict)
    material: dict = field(default_factory=dict)
    # ---- R4 / R2 extent flags
    unresolved_edges: dict = field(default_factory=dict)
    extent_uncertain: bool = False
    leaves_frame: bool = False
    arm_admissible: bool = False


def _pt(scene: Scene, iv: int, iu: int, xyz=None) -> dict:
    """A point, reported on every grid a downstream chunk might want."""
    if xyz is None:
        xyz = scene.P[iv, iu]
        u, v = float(iu), float(iv)
    else:
        uu, vv = scene.project(np.asarray(xyz)[None, :])
        u, v = float(uu[0]), float(vv[0])
    gx, gy = depth_xy_to_gt_xy(u, v)
    h = float(scene.signed_height(np.asarray(xyz, float)[None, :])[0])
    return {"xyz_rdu": [float(c) for c in xyz],
            "depth_grid_xy": [u, v],
            "gt_grid_xy": [float(gx), float(gy)],
            "height_above_datum_rdu": h,
            "height_above_datum_sigma": h / scene.sigma_datum}


def component_height_median(labels: np.ndarray, height: np.ndarray,
                            valid: np.ndarray, window: int = MEDIAN_WINDOW,
                            min_support: int = MIN_MEDIAN_SUPPORT
                            ) -> tuple[np.ndarray, np.ndarray]:
    """Per-pixel height, read as the median over the MEDIAN_WINDOW neighbourhood
    restricted to the pixel's own component. Returns (median, support count).

    A component's boundary pixels straddle material and background, so their raw
    depth is a mixture. Averaging inside the component only is what removes that
    without eroding a one-pixel-wide stem away.
    """
    r = window // 2
    min_support = min(min_support, window * window)   # window=1 means no filter
    H, W = labels.shape
    stack, cnt = [], np.zeros((H, W), np.int16)
    for dy in range(-r, r + 1):
        for dx in range(-r, r + 1):
            sl = np.full((H, W), np.nan, np.float32)
            sc = np.roll(np.roll(labels, dy, 0), dx, 1)
            sh = np.roll(np.roll(height, dy, 0), dx, 1)
            sv = np.roll(np.roll(valid, dy, 0), dx, 1)
            if dy > 0:
                sc[:dy] = 0
            elif dy < 0:
                sc[dy:] = 0
            if dx > 0:
                sc[:, :dx] = 0
            elif dx < 0:
                sc[:, dx:] = 0
            ok = (sc == labels) & (labels > 0) & sv
            sl[ok] = sh[ok]
            stack.append(sl)
            cnt += ok
    with np.errstate(all="ignore"), warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        med = np.nanmedian(np.stack(stack), axis=0)
    med[cnt < min_support] = np.nan
    return med, cnt


def _largest_group_containing(mask: np.ndarray, seed: tuple[int, int]):
    """8-connected group of `mask` that contains `seed`, as a boolean array."""
    lab, _ = ndimage.label(mask, structure=np.ones((3, 3), int))
    k = lab[seed]
    return lab == k if k else mask


def _basal_band(sub: np.ndarray, hmed: np.ndarray, sig: np.ndarray,
                k: float = BASAL_BAND_K):
    """The lowest distinguishable stretch of material in `sub`.

    All arrays are the component's bounding-box crop. Returns (band_mask, seed)
    or (None, None) when nothing in `sub` is usable.
    """
    cand = sub & np.isfinite(hmed)
    if not cand.any():
        return None, None
    hh = np.where(cand, hmed, np.inf)
    seed = np.unravel_index(np.argmin(hh), hh.shape)
    band = cand & (hmed <= hmed[seed] + k * sig[seed])
    return _largest_group_containing(band, seed), seed


def _representative(P: np.ndarray, band: np.ndarray):
    """The band pixel nearest the band's 3-D centroid. A real material pixel —
    never the centroid itself, which would be a point on nothing."""
    iv, iu = np.nonzero(band)
    pts = P[iv, iu]
    c = pts.mean(0)
    j = int(np.argmin(((pts - c) ** 2).sum(1)))
    return int(iv[j]), int(iu[j])


def _axis(pts: np.ndarray):
    """Principal 3-D direction of a point set, with the half-angle of its own
    scatter cone. `theta` is arctan(σ2/σ1): a stem's cone is narrow, a leaf
    blob's is ~45°, and no constant is needed to tell them apart."""
    c = pts.mean(0)
    cov = np.cov((pts - c).T)
    w, V = np.linalg.eigh(cov)
    order = np.argsort(w)[::-1]
    w, V = w[order], V[:, order]
    s1 = math.sqrt(max(w[0], 0.0))
    s2 = math.sqrt(max(w[1], 0.0))
    theta = math.atan2(s2, s1) if s1 > 0 else math.pi / 4
    # sampling error of the direction, added in quadrature
    n = len(pts)
    if s1 > s2 and n > 2:
        theta = math.hypot(theta, math.sqrt(w[1] / (n * max(w[0] - w[1], 1e-30))))
    return V[:, 0] / (np.linalg.norm(V[:, 0]) + 1e-300), min(theta, math.pi / 2), c


def _march(scene: Scene, p0: np.ndarray, d: np.ndarray, step: float):
    """Continue from p0 along d until the signed height crosses zero.

    Returns (t, point) or (None, None) if the datum is never reached inside
    MARCH_CEILING_RDU or the ray leaves the frame first.
    """
    h0 = scene.signed_height(p0[None, :])[0]
    if not np.isfinite(h0):
        return None, None
    t, hprev, tprev = step, h0, 0.0
    while t <= MARCH_CEILING_RDU:
        h = scene.signed_height((p0 + t * d)[None, :])[0]
        if not np.isfinite(h):
            return None, None
        if h <= 0.0:
            lo, hi = tprev, t
            for _ in range(40):          # bisection to well under 1e-3 σ
                mid = 0.5 * (lo + hi)
                hm = scene.signed_height((p0 + mid * d)[None, :])[0]
                if not np.isfinite(hm):
                    return None, None
                if hm > 0:
                    lo = mid
                else:
                    hi = mid
            tt = 0.5 * (lo + hi)
            return tt, p0 + tt * d
        hprev, tprev = h, t
        t += step
    return None, None


def _profile(scene: Scene, material: np.ndarray, a: tuple, b: tuple) -> dict:
    """What A3 says lies along the image-space segment from a to b."""
    (v0, u0), (v1, u1) = a, b
    n = max(2, int(math.hypot(v1 - v0, u1 - u0)) + 1)
    vv = np.clip(np.rint(np.linspace(v0, v1, n)).astype(int), 0, scene.shape[0] - 1)
    uu = np.clip(np.rint(np.linspace(u0, u1, n)).astype(int), 0, scene.shape[1] - 1)
    cls, cnt = np.unique(material[vv, uu], return_counts=True)
    return {MATERIAL.get(int(c), str(int(c))): int(k) for c, k in zip(cls, cnt)}


def _occluder(profile: dict, own: set[str]) -> str:
    """Name the thing standing between the base and the datum."""
    if not profile:
        return "unknown"
    other = {k: v for k, v in profile.items() if k not in own and k != "unlabelled"}
    if not other:
        return "none"
    top = max(other, key=other.get)
    if top == "straw":
        return "straw"
    if top in {MATERIAL[c] for c in FOLIAGE_CLASSES}:
        return "foliage"
    return top


def contact_points(scene: Scene, labels: np.ndarray, material: np.ndarray,
                   unresolved: list | None = None,
                   max_extrapolation_sigma: float = MAX_EXTRAPOLATION_SIGMA,
                   ground_band_k: float = GROUND_BAND_K,
                   basal_band_k: float = BASAL_BAND_K,
                   min_axis_points: int = MIN_AXIS_POINTS,
                   median_window: int = MEDIAN_WINDOW) -> list[Contact]:
    """Contact points for every component in `labels` (depth grid, 0 = none)."""
    d_max = max_extrapolation_sigma * scene.sigma_datum
    sig = scene.sigma_combined()
    sig_min = float(np.nanmin(sig[scene.valid])) if scene.valid.any() else scene.sigma_datum
    hmed, _ = component_height_median(labels, scene.height.astype(np.float32),
                                      scene.valid, median_window)
    ground = scene.ground

    edges_by_comp: dict[int, dict] = {}
    frame_comps: set[int] = set()
    for e in (unresolved or []):
        if e.get("already_connected"):
            continue
        for c in (e.get("components") or []):
            if c is None:
                continue
            edges_by_comp.setdefault(int(c), {})
            k = e.get("kind", "?")
            edges_by_comp[int(c)][k] = edges_by_comp[int(c)].get(k, 0) + 1
            if k == "leaves_frame":
                frame_comps.add(int(c))

    # A2 invalidates a pixel by refusing to trust the datum under it, so an
    # invalid pixel carries no height at all.
    hmed = np.where(scene.valid, hmed, np.nan)

    ids = [int(i) for i in np.unique(labels) if i > 0]
    objs = ndimage.find_objects(labels.astype(np.int32))
    out = []
    for cid in ids:
        sl = objs[cid - 1]
        # padded by one pixel so the ring of material just outside the
        # component's basal band can be read without a second pass
        box = (slice(max(0, sl[0].start - 1), min(scene.shape[0], sl[0].stop + 1)),
               slice(max(0, sl[1].start - 1), min(scene.shape[1], sl[1].stop + 1)))
        ctx = _Box(box, labels[box] == cid, hmed[box], sig[box], material[box],
                   scene.P[box], scene.coverage[box], scene.valid[box],
                   ground[box])
        c = Contact(component=cid, n_px=int(ctx.sub.sum()))
        c.unresolved_edges = edges_by_comp.get(cid, {})
        c.leaves_frame = cid in frame_comps
        c.extent_uncertain = bool(c.unresolved_edges)
        out.append(c)
        _one(scene, c, ctx, sig_min, d_max, ground_band_k, material, sig,
             basal_band_k, min_axis_points)
    return out


@dataclass
class _Box:
    """A component's bounding-box crop of every raster the decision needs."""
    box: tuple
    sub: np.ndarray
    hmed: np.ndarray
    sig: np.ndarray
    material: np.ndarray
    P: np.ndarray
    coverage: np.ndarray
    valid: np.ndarray
    ground: np.ndarray

    def g(self, v, u):
        return int(v) + self.box[0].start, int(u) + self.box[1].start


def _one(scene, c, ctx, sig_min, d_max, ground_band_k, material_full,
         sig_full, basal_band_k=BASAL_BAND_K, min_axis_points=MIN_AXIS_POINTS):
    material, hmed, sig = ctx.material, ctx.hmed, ctx.sig
    cls, cnt = np.unique(material[ctx.sub], return_counts=True)
    c.material["composition"] = {MATERIAL.get(int(k), str(int(k))): int(v)
                                 for k, v in zip(cls, cnt)}
    band, seed = _basal_band(ctx.sub, hmed, sig, basal_band_k)
    if band is None:
        c.status, c.reason = "occluded", (
            "no pixel of this component has an A2 datum inside its measured "
            "trust distance — nothing here can be levelled against the ground")
        return
    lbv, lbu = _representative(ctx.P, band)
    bv, bu = ctx.g(lbv, lbu)
    c.lowest_visible_point = _pt(scene, bv, bu)
    c.lowest_visible_point["n_band_px"] = int(band.sum())
    c.lowest_visible_point["material"] = MATERIAL.get(int(material[lbv, lbu]), "?")
    c.lowest_visible_point["datum_coverage"] = ["observed", "interpolated",
                                                "extrapolated"][int(ctx.coverage[lbv, lbu])]
    # R1 honesty check: was this very pixel one A2 fitted the datum *to*? If so,
    # "the plant reaches the ground" is partly circular, and the count of such
    # cases is reported rather than buried.
    c.lowest_visible_point["on_a2_ground_inlier"] = bool(ctx.ground[lbv, lbu])
    ring = ndimage.binary_dilation(band, np.ones((3, 3), bool)) & ~ctx.sub
    if ring.any():
        rk, rn = np.unique(material[ring], return_counts=True)
        c.material["basal_surround"] = {MATERIAL.get(int(k), str(int(k))): int(v)
                                        for k, v in zip(rk, rn)}

    stem = ctx.sub & (material == STEM_CLASS)
    if stem.sum() >= min_axis_points:
        sband, _ = _basal_band(stem, hmed, sig, basal_band_k)
        if sband is not None:
            sv, su = ctx.g(*_representative(ctx.P, sband))
            c.lowest_visible_stem_point = _pt(scene, sv, su)
            c.lowest_visible_stem_point["n_band_px"] = int(sband.sum())
    if c.lowest_visible_stem_point is None:
        c.material["stem_note"] = ("no `squash_petiole` material in this "
                                   "component; A0/A3 have no other stem class")
    h_b = float(hmed[lbv, lbu])
    sg = float(sig[lbv, lbu])
    c.height_at_base_rdu = h_b
    c.height_at_base_sigma = h_b / scene.sigma_datum
    c.datum_sigma_rdu = sg
    cov_at_base = ["observed", "interpolated",
                   "extrapolated"][int(ctx.coverage[lbv, lbu])]
    # "What stands between this plant and the ground" is asked about the
    # material the base itself is made of. Using every class in the component
    # would let one grass blade inside a squash component hide a straw occluder.
    own = {MATERIAL.get(int(material[lbv, lbu]), "?")}

    # ---- material below the datum: a disagreement, not a contact
    # Nothing in a scene lies under the ground (A2's own argument for its
    # one-sided roughness estimator). Material that sits more than the ground
    # band *below* the fitted surface means the surface under this component is
    # wrong — almost always because it was interpolated across a canopy hole, or
    # because the component runs off the frame. R4: report it, do not resolve it.
    if h_b < -ground_band_k * sg:
        c.status = "occluded"
        c.reason = (f"the component's lowest material sits {abs(h_b)/sg:.1f}·σ "
                    "BELOW A2's fitted datum. Nothing lies under the ground, so "
                    "this is the surface disagreeing with the material, not a "
                    "contact — the datum here is "
                    f"{c.lowest_visible_point['datum_coverage']}")
        c.datum_coverage = cov_at_base
        c.occluder = _occluder(c.material.get("basal_surround", {}), own)
        return

    # ---- observed: the material is already inside the datum's own ground band
    if abs(h_b) <= ground_band_k * sg:
        c.status, c.reason = "observed", (
            f"material reaches within {abs(h_b)/sg:.2f}·σ of the datum "
            f"(band is {ground_band_k}·σ)")
        c.point = dict(c.lowest_visible_point)
        c.datum_coverage = cov_at_base
        c.extrapolation_distance_rdu = 0.0
        c.extrapolation_distance_sigma = 0.0
        c.extrapolation_px_gt = 0.0
        rho_band = float(np.clip(1.0 - abs(h_b) / (ground_band_k * sg), 0.0, 1.0))
        kappa = float(sig_min / sg)
        c.confidence_terms = {"kappa_datum": kappa, "lambda_axis": 1.0,
                              "rho_reach": 1.0, "rho_band": rho_band}
        c.confidence = kappa * rho_band
        c.occluder = "none"
        c.arm_admissible = (cov_at_base == "observed") and not c.leaves_frame
        return

    # ---- otherwise: continue the basal material's own axis to the datum
    axis_win = (ctx.sub & np.isfinite(hmed)
                & (hmed <= h_b + max(abs(h_b), sg)))
    axis_win = _largest_group_containing(axis_win, (lbv, lbu))
    npts = int(axis_win.sum())
    c.occluder = _occluder(c.material.get("basal_surround", {}), own)
    if npts < min_axis_points:
        c.status = "occluded"
        c.reason = (f"basal material is {npts} px, below the {min_axis_points} px "
                    "needed to measure a 3-D direction")
        return
    iv, iu = np.nonzero(axis_win)
    d, theta, _ = _axis(ctx.P[iv, iu])
    p0 = scene.P[bv, bu]
    step = scene.sigma_datum
    hs = [scene.signed_height((p0 + s * step * d)[None, :])[0] for s in (1, -1)]
    if not np.isfinite(hs[0]) and not np.isfinite(hs[1]):
        c.status, c.reason = "occluded", "the basal axis leaves the frame immediately"
        return
    lo = np.nanargmin([hs[0] if np.isfinite(hs[0]) else np.inf,
                       hs[1] if np.isfinite(hs[1]) else np.inf])
    if not (hs[lo] < h_b):
        c.status, c.reason = "occluded", (
            "the basal material's axis runs along the datum, not toward it — "
            "continuing it never reaches the surface")
        return
    d = d if lo == 0 else -d
    t, land = _march(scene, p0, d, step)
    if t is None:
        c.status, c.reason = "occluded", (
            f"the axis does not reach the datum inside the {MARCH_CEILING_RDU} rdu "
            "reporting ceiling, or leaves the frame first")
        c.axis_half_angle_deg = math.degrees(theta)
        return

    lat = t * math.tan(theta)
    lu, lv = scene.project(land[None, :])
    liv = int(np.clip(round(float(lv[0])), 0, scene.shape[0] - 1))
    liu = int(np.clip(round(float(lu[0])), 0, scene.shape[1] - 1))
    cov = ["observed", "interpolated", "extrapolated"][int(scene.coverage[liv, liu])]
    prof = _profile(scene, material_full, (bv, bu), (liv, liu))
    c.occluder_profile = prof
    c.occluder = _occluder({**c.material.get("basal_surround", {}), **prof}, own)
    c.axis_half_angle_deg = math.degrees(theta)
    c.extrapolation_distance_rdu = float(t)
    c.extrapolation_distance_sigma = float(t / scene.sigma_datum)
    gx0, gy0 = depth_xy_to_gt_xy(bu, bv)
    gx1, gy1 = depth_xy_to_gt_xy(float(lu[0]), float(lv[0]))
    c.extrapolation_px_gt = float(math.hypot(gx1 - gx0, gy1 - gy0))
    c.lateral_uncertainty_rdu = float(lat)
    c.datum_coverage = cov

    if not scene.valid[liv, liu]:
        c.status, c.reason = "occluded", (
            "the axis lands where A2's datum is beyond its measured trust "
            "distance — the surface there is a continuation, not an observation")
        return
    if t > d_max:
        c.status, c.reason = "occluded", (
            f"extrapolation {t/scene.sigma_datum:.1f}·σ exceeds the tool budget "
            f"of {d_max/scene.sigma_datum:.0f}·σ (b, placeholder, awaiting C3)")
        return
    if lat >= d_max:
        c.status, c.reason = "occluded", (
            f"the basal material's axis is a {math.degrees(theta):.0f}° cone; "
            f"continued {t/scene.sigma_datum:.1f}·σ it wanders "
            f"{lat/scene.sigma_datum:.1f}·σ sideways, at or beyond the whole budget")
        return

    kappa = float(sig_min / sig_full[liv, liu])
    lam = float(max(0.0, 1.0 - lat / d_max))
    rho = float(max(0.0, 1.0 - t / d_max))
    c.confidence_terms = {"kappa_datum": kappa, "lambda_axis": lam,
                          "rho_reach": rho, "rho_band": 1.0}
    c.confidence = kappa * lam * rho
    c.status = "extrapolated"
    c.reason = (f"basal axis continued {t/scene.sigma_datum:.1f}·σ to the datum "
                f"across material A3 reads as {c.occluder}")
    c.point = _pt(scene, liv, liu, xyz=land)
    c.arm_admissible = False      # R2: only `observed` may admit a removal
    return


def to_json(cs: list[Contact], scene: Scene, policy: str, extra: dict | None = None):
    return {
        "chunk": "A5",
        "policy": policy,
        "scale_confidence": "scale_free",
        "units": "3-D distances in rdu (1 rdu = median scene depth); image "
                 "distances in px on the named grid. No metric claim.",
        "DATUM": scene.a2_manifest["DATUM"],
        "product_target": "lowest visible stem / datum contact — NOT the "
                          "stem-soil intersection, which is unobservable in "
                          "this image. See chunks/A5/FINDINGS.md.",
        "constants": {
            "GROUND_BAND_K": GROUND_BAND_K,
            "BASAL_BAND_K": BASAL_BAND_K,
            "MEDIAN_WINDOW": MEDIAN_WINDOW,
            "MIN_MEDIAN_SUPPORT": MIN_MEDIAN_SUPPORT,
            "MIN_AXIS_POINTS": MIN_AXIS_POINTS,
            "MAX_EXTRAPOLATION_SIGMA": MAX_EXTRAPOLATION_SIGMA,
            "MARCH_CEILING_RDU": MARCH_CEILING_RDU,
            "sigma_datum_rdu": scene.sigma_datum,
        },
        "provenance": {
            "a1_product": "primary_raster",
            "a2_manifest": "chunks/A2/products/A2_MANIFEST.json",
            "a4_policy": policy,
            "material": "chunks/A3 segment_material(), lifted to the depth grid",
        },
        "components": [asdict(c) for c in cs],
        **(extra or {}),
    }


def status_counts(cs: list[Contact]) -> dict:
    d = {"observed": 0, "extrapolated": 0, "occluded": 0}
    for c in cs:
        d[c.status] += 1
    d["total"] = len(cs)
    d["arm_admissible"] = sum(1 for c in cs if c.arm_admissible)
    d["with_lowest_visible_point"] = sum(1 for c in cs
                                         if c.lowest_visible_point is not None)
    d["with_lowest_visible_stem_point"] = sum(
        1 for c in cs if c.lowest_visible_stem_point is not None)
    d["fabricated_points"] = sum(1 for c in cs
                                 if c.status == "occluded" and c.point is not None)
    return d
