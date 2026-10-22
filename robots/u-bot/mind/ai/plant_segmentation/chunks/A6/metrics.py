"""A6 — what the keep-out volume covers, and what it shields.

Two numbers matter and they pull in opposite directions.

* **Coverage.** How much of the crop is protected. Under R2 this should be
  close to 1: a piece of crop outside the keep-out is a piece a tool may be
  sent at.
* **Shielding.** How much *weed* material is inside the same volume. Every
  shielded weed is a weed the robot will refuse to remove. That is the cheap
  error under R2, but it is not free, and it must be counted rather than
  assumed small — especially here, where A4's ``merge`` component already
  absorbs 83 % of the ground-truth grass before A6 adds a single unit of
  clearance.

Shielding is therefore reported in two parts: material the keep-out inherits
because **A4 already put it in the crop component**, and material A6 sweeps in
itself through the occupancy assumption and the clearance. Only the second is
A6's to answer for.
"""
from __future__ import annotations

import numpy as np

from a6_common import (GT_CROP_INSTANCE, MAT_BROADLEAF, MAT_GRASS, MAT_SOIL,
                       MAT_STRAW, MAT_UNLABELLED, gt_rc_to_depth_rc)
from keepout import INSIDE, UNKNOWN


class GtProbe:
    """Every GT pixel's 3-D point, its distance to the crop material, and
    whether the camera could see where it is. Computed once; every clearance
    is then a threshold on the same array."""

    def __init__(self, scene, gt, vol):
        self.gt = gt
        h, w = gt.material.shape
        rr, cc = np.meshgrid(np.arange(h), np.arange(w), indexing="ij")
        dr, dc = gt_rc_to_depth_rc(rr.ravel(), cc.ravel())
        self.depth_rc = (dr.reshape(h, w), dc.reshape(h, w))
        xyz = scene.xyz[dr, dc]
        finite = np.isfinite(xyz).all(axis=1)
        d = np.full(len(xyz), np.inf)
        d[finite] = vol.distance_to_material(xyz[finite])
        self.dist = d.reshape(h, w)
        self.finite = finite.reshape(h, w)
        # UNKNOWN never fires for GT pixels: they all project inside the frame
        # by construction. Kept explicit so the asymmetry is visible.
        self.unknown = np.zeros((h, w), dtype=bool)

    def inside(self, vol, clearance: float, *, conservative: bool = True):
        t = clearance + (vol.voxel_bracket if conservative else 0.0)
        return self.finite & (self.dist <= t)


def _frac(num, den):
    return float(num) / float(den) if den else float("nan")


def coverage_and_shielding(scene, gt, vol, crop, clearances,
                           probe: GtProbe | None = None) -> dict:
    probe = probe or GtProbe(scene, gt, vol)
    mat, inst = gt.material, gt.instances

    squash = inst == GT_CROP_INSTANCE
    grass = mat == MAT_GRASS
    broadleaf = mat == MAT_BROADLEAF
    weed = grass | broadleaf
    ground = (mat == MAT_STRAW) | (mat == MAT_SOIL)
    labelled = mat != MAT_UNLABELLED

    # which GT pixels A4 had already placed in the crop component
    dr, dc = probe.depth_rc
    in_component = crop.observed[dr, dc]
    in_unseen = crop.unseen[dr, dc]

    rows = []
    for c in clearances:
        ins = probe.inside(vol, c)
        row = {
            "clearance_rdu": float(c),
            "clearance_datum_sigma": float(c / scene.a2.sigma_datum),
            "volume_rdu3": vol.volume_rdu3(c),
            "footprint_area_rdu2": float(vol.footprint(c).sum()) * vol.cell ** 2,
            "gt_squash_covered": _frac((ins & squash).sum(), squash.sum()),
            "gt_squash_uncovered_px": int((squash & ~ins).sum()),
            "gt_grass_inside": _frac((ins & grass).sum(), grass.sum()),
            "gt_broadleaf_inside": _frac((ins & broadleaf).sum(), broadleaf.sum()),
            "gt_weed_inside": _frac((ins & weed).sum(), weed.sum()),
            "gt_weed_inside_already_in_crop_component":
                _frac((ins & weed & in_component).sum(), weed.sum()),
            "gt_weed_inside_added_by_a6":
                _frac((ins & weed & ~in_component).sum(), weed.sum()),
            "gt_ground_inside": _frac((ins & ground).sum(), ground.sum()),
            "frame_labelled_inside": _frac((ins & labelled).sum(), labelled.sum()),
        }
        # per weed instance
        per = {}
        for iid in sorted(int(i) for i in np.unique(inst)
                          if i not in (0, GT_CROP_INSTANCE, 255)):
            m = inst == iid
            per[iid] = {"px": int(m.sum()),
                        "fraction_inside": _frac((ins & m).sum(), m.sum())}
        row["per_weed_instance"] = per
        rows.append(row)

    return {
        "clearances": rows,
        "gt_pixel_counts": {
            "squash": int(squash.sum()), "grass": int(grass.sum()),
            "broadleaf_weed": int(broadleaf.sum()), "ground": int(ground.sum()),
            "labelled": int(labelled.sum())},
        "a4_inheritance": {
            "note": ("what A4's component already contained, before A6 added "
                     "any occupancy or clearance"),
            "gt_squash_in_component": _frac((squash & in_component).sum(),
                                            squash.sum()),
            "gt_grass_in_component": _frac((grass & in_component).sum(),
                                           grass.sum()),
            "gt_broadleaf_in_component": _frac((broadleaf & in_component).sum(),
                                               broadleaf.sum()),
            "gt_weed_in_unseen_halo": _frac((weed & in_unseen).sum(), weed.sum()),
            "gt_squash_in_unseen_halo": _frac((squash & in_unseen).sum(),
                                              squash.sum())},
    }


def contact_point_report(scene, gt, vol, clearances) -> dict:
    """Would A8 refuse each ground-truth weed target?

    A0's contact points are all ``under_straw`` and ``estimated`` — there is not
    one ``visible`` stem in this photograph — so these are not scoring targets.
    They are still the only stem-soil points that exist, and whether they fall
    inside the crop's keep-out is exactly the question A8's gate asks.
    Each point is lifted to 3-D on the A2 straw datum along its own ray.
    """
    out = {"note": ("A0 contact points are all `under_straw` / `estimated`; "
                    "these are gate rehearsals, not accuracy scores"),
           "points": []}
    for e in gt.contacts["instances"]:
        pt = e.get("point")
        if pt is None:
            continue
        x, y = int(pt[0]), int(pt[1])
        dr, dc = gt_rc_to_depth_rc(np.array([y]), np.array([x]))
        ray = scene.xyz[dr[0], dc[0]]
        if not np.isfinite(ray).all() or ray[2] <= 0:
            continue
        xyz = ray / ray[2] * scene.a2.soil_depth[dr[0], dc[0]]
        d = float(vol.distance_to_material(xyz[None, :])[0])
        rec = {"id": int(e["id"]), "name": e.get("name"),
               "crop": bool(e.get("crop", False)),
               "gt_point_xy": [x, y],
               "status": e.get("status"),
               "localisation": e.get("localisation"),
               "distance_to_crop_material_rdu": d,
               "inside_at": {}}
        for c in clearances:
            rec["inside_at"][f"{c:g}"] = bool(d <= c + vol.voxel_bracket)
        out["points"].append(rec)
    return out


def circle_comparison(vol, scene, gt, clearance) -> dict:
    """The roadmap's claim, measured: *is a radius around the crown wrong?*

    Compares the keep-out's own footprint on the datum plane with the best a
    disk centred on the crop's crown can do.
    """
    fp = vol.footprint(clearance)
    nu, nv = fp.shape
    iu, iv = np.nonzero(fp)
    cell = vol.cell
    u = vol.origin_uvw[0] + iu * cell
    v = vol.origin_uvw[1] + iv * cell

    # crown = A0's recorded contact point for the crop instance, lifted to the
    # datum. It is `estimated`, and it is the only crown this image has.
    contacts = gt.contacts["instances"]
    crop_e = next(e for e in contacts if int(e["id"]) == 1)
    x, y = crop_e["point"]
    from a6_common import gt_rc_to_depth_rc as g2d
    dr, dc = g2d(np.array([y]), np.array([x]))
    ray = scene.xyz[dr[0], dc[0]]
    crown = vol.frame.to_uvw((ray / ray[2] * scene.a2.soil_depth[dr[0], dc[0]])[None, :])[0]

    r = np.hypot(u - crown[0], v - crown[1])
    area = fp.sum() * cell ** 2
    r_equal = float(np.sqrt(area / np.pi))
    r_cover = float(r.max())

    # rasterise both disks on the same grid
    gu = vol.origin_uvw[0] + np.arange(nu) * cell
    gv = vol.origin_uvw[1] + np.arange(nv) * cell
    RR = np.hypot(gu[:, None] - crown[0], gv[None, :] - crown[1])
    d_equal, d_cover = RR <= r_equal, RR <= r_cover
    inter = float((fp & d_equal).sum())
    return {
        "clearance_rdu": float(clearance),
        "crown_uv": crown[:2].tolist(),
        "crown_provenance": "A0 instance 1 contact point (under_straw, estimated)",
        "keepout_footprint_area_rdu2": float(area),
        "max_radius_from_crown_rdu": r_cover,
        "radius_percentiles_rdu": {p: float(np.percentile(r, p))
                                   for p in (50, 90, 99, 100)},
        "equal_area_disk": {
            "radius_rdu": r_equal,
            "iou_with_footprint": float(inter / max((fp | d_equal).sum(), 1)),
            "fraction_of_sprawl_it_covers": float(inter / max(fp.sum(), 1)),
            "fraction_of_the_disk_that_is_not_plant":
                float(1.0 - inter / max(d_equal.sum(), 1))},
        "covering_disk": {
            "radius_rdu": r_cover,
            "area_rdu2": float(d_cover.sum()) * cell ** 2,
            "area_inflation_over_footprint":
                float(d_cover.sum() / max(fp.sum(), 1)),
            "fraction_of_the_disk_that_is_not_plant":
                float(1.0 - fp.sum() / max(d_cover.sum(), 1))},
    }
