"""A6 — the keep-out volume and its ``is_inside`` test.

What the volume is
------------------
The protected region is the crop's **own observed 3-D material**, made solid by
one stated occupancy assumption, then dilated by a single named parameter,
``clearance_rdu``. It is not a radius, not a disk, and not a bounding box: a
squash sprawls, so a circle around the crown is wrong in both directions at
once, and the whole point of this chunk is that the shape comes from the plant.

    keep_out(c) = { q : dist(q, M) <= c }

where ``M`` is the crop's material solid and ``c`` is the tool clearance.
``M`` is built in A2's datum-aligned frame (a rigid rotation of the camera
frame, so distances are unchanged) as a *height field with a floor*:

* **ceiling** — the highest observed crop material over each ground cell;
* **floor** — the A2 straw datum under that cell;
* **occupied** — everything between them.

The occupancy assumption, and why (R2 / R4)
-------------------------------------------
The depth is one view. What lies *behind* an observed leaf is unobserved, and
under **R4** an unobserved region must not be reported as a measured one. Two
readings of "unobserved" are available and only one of them is safe:

* *empty* — a tool may pass under the canopy. This is a fabricated claim about
  space the camera never saw, and it is unsafe in the catastrophic direction.
* *occupied* — the column between a leaf and the ground beneath it belongs to
  the plant. This over-covers, and **R2** says over-covering the crop is the
  cheap error.

A6 takes the second (``occupancy="column"``, shipped). The first is available
as ``occupancy="shell"`` purely as a diagnostic, so the cost of the assumption
can be measured rather than asserted. Note the column is extruded **vertically,
along the datum normal** — never along the camera ray. Ray extrusion would
build the plant's *occlusion shadow*, which in this 41-degree-oblique view is
several times the plant and is not the plant.

Unresolved edges are volume, not empty space
--------------------------------------------
A4 records the links its graph refused to decide. Material on the far side of
one of those links *may* be part of the crop; one view cannot say. A6 includes
it as a second tier, ``TIER_UNSEEN``, and reports the volume with and without
it. ``leaves_frame`` edges cannot be turned into volume at all — the material
is outside the photograph — so the volume is flagged ``frame_open`` and
``classify()`` returns ``UNKNOWN`` for query points that project off the image,
which ``is_inside`` resolves to *inside* by R2 default.

Resolution, and why the test is conservative
--------------------------------------------
``M`` is held as a voxel grid of edge ``cell``. Any point of the true solid is
within ``voxel_bracket = cell * sqrt(3) / 2`` of an occupied voxel centre, so
the exact distance to the solid is bracketed by ``d - voxel_bracket <=
dist(q, M) <= d``, where
``d`` is the distance to the nearest occupied *boundary* voxel centre. The
shipped test uses the lower bracket (``d - voxel_bracket <= c``), which can only
over-cover. ``conservative=False`` uses ``d`` instead, and the gap between the
two is reported at every clearance.

Every length in this module is in **rdu**. There is no metre here.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Literal

import numpy as np
from scipy import ndimage
from scipy.spatial import cKDTree

from a6_common import (DatumFrame, Intrinsics, Scene, SCALE_CONFIDENCE, UNITS,
                       load_crop_component, load_scene)

# --- occupancy tiers ---------------------------------------------------------
TIER_EMPTY, TIER_OBSERVED, TIER_UNSEEN = 0, 1, 2

# --- classify() outcomes -----------------------------------------------------
OUTSIDE, INSIDE, UNKNOWN = 0, 1, 2

Occupancy = Literal["column", "shell"]

# --- the one constant this chunk introduces ---------------------------------
#: **Tool clearance.** Category (b), tool geometry — and the tool does not
#: exist yet, so this is an explicit PLACEHOLDER awaiting C3 (actuator
#: selection and precision budget). It is the *only* parameter of the keep-out
#: volume. It is in rdu because Phase A is scale-free: converting it to
#: millimetres needs an absolute scale this image cannot supply (roadmap, Known
#: gaps #2). The value below is a round number in the middle of the swept
#: decade and nothing is tuned to it; `sweeps.json` records what the volume,
#: the crop coverage and the weed shielding do across the whole range, which is
#: what bounds the eventual real number.
DEFAULT_CLEARANCE_RDU = 1.0e-2

#: The clearances every A6 report is computed at. rdu; the second column of
#: every table gives the same value in A2 datum-sigma (5.4696e-3 rdu).
CLEARANCE_SWEEP_RDU = (0.0, 1.0e-3, 2.0e-3, 5.0e-3, 1.0e-2, 2.0e-2, 5.0e-2)

#: Voxel edge. A **resolution ceiling and compute budget, not a threshold** —
#: the same category as A2's spline basis size. It bounds the reported volume
#: and the is_inside test by +/- `voxel_bracket` and decides nothing else; swept in
#: `sweeps.json`.
DEFAULT_CELL_RDU = 3.5e-3


@dataclass
class KeepOutVolume:
    """A crop plant's protected region, plus a fast ``is_inside``."""

    # --- geometry -----------------------------------------------------------
    frame: DatumFrame
    cell: float
    origin_uvw: np.ndarray          # (3,) uvw of voxel (0, 0, 0) *centre*
    tier: np.ndarray                # (nu, nv, nw) uint8, see TIER_*
    dist: np.ndarray                # (nu, nv, nw) float, rdu to nearest occupied
    # --- the parameter ------------------------------------------------------
    clearance_rdu: float
    max_clearance_rdu: float        # the grid is padded for this; beyond it, refuse
    occupancy: str
    include_unseen: bool
    # --- honesty ------------------------------------------------------------
    frame_open: bool
    scale_confidence: str = SCALE_CONFIDENCE
    units: str = UNITS
    datum: str = "straw mulch surface (A2), not soil"
    provenance: dict = field(default_factory=dict)
    # --- lazily built -------------------------------------------------------
    _tree: object = field(default=None, repr=False)
    _boundary_uvw: np.ndarray | None = field(default=None, repr=False)
    _intrinsics: object = field(default=None, repr=False)
    _image_hw: tuple = field(default=None, repr=False)

    # ---------------------------------------------------------------- basics
    @property
    def voxel_bracket(self) -> float:
        """Half the voxel diagonal: the resolution bracket on every distance."""
        return float(self.cell * np.sqrt(3.0) / 2.0)

    @property
    def shape(self) -> tuple:
        return tuple(self.tier.shape)

    @property
    def sigma_datum(self) -> float:
        return float(self.provenance.get("a2", {}).get("datum_roughness_sigma_rdu",
                                                       np.nan))

    def clearance_in_sigma(self, c: float | None = None) -> float:
        return float((self.clearance_rdu if c is None else c) / self.sigma_datum)

    # ------------------------------------------------------------ occupancy
    @property
    def occupied(self) -> np.ndarray:
        return self.tier > TIER_EMPTY

    def material_volume_rdu3(self, tier: int | None = None) -> float:
        m = self.occupied if tier is None else (self.tier == tier)
        return float(m.sum()) * self.cell ** 3

    def volume_rdu3(self, clearance: float | None = None) -> float:
        """Volume of the dilated keep-out region, rdu^3."""
        c = self.clearance_rdu if clearance is None else float(clearance)
        self._check_clearance(c)
        return float((self.dist <= c).sum()) * self.cell ** 3

    def _check_clearance(self, c: float) -> None:
        if c < 0:
            raise ValueError("clearance must be >= 0")
        if c > self.max_clearance_rdu + 1e-12:
            raise ValueError(
                f"clearance {c} rdu exceeds the padding this volume was built "
                f"with ({self.max_clearance_rdu} rdu). Rebuild with a larger "
                f"max_clearance rather than reading a clipped answer.")

    # -------------------------------------------------------------- indexing
    def _voxel_index(self, uvw: np.ndarray) -> np.ndarray:
        return np.rint((uvw - self.origin_uvw) / self.cell).astype(np.int64)

    def _in_grid(self, idx: np.ndarray) -> np.ndarray:
        return np.all((idx >= 0) & (idx < np.array(self.shape)), axis=-1)

    # ------------------------------------------------------------------ tree
    def _ensure_tree(self):
        if self._tree is not None:
            return
        occ = self.occupied
        # A boundary voxel is occupied and has at least one empty 6-neighbour
        # (grid edges count as empty). The nearest point of the solid to any
        # exterior query lies in one of these.
        interior = ndimage.binary_erosion(
            occ, structure=ndimage.generate_binary_structure(3, 1),
            border_value=0)
        bidx = np.argwhere(occ & ~interior)
        self._boundary_uvw = (self.origin_uvw
                              + bidx.astype(np.float64) * self.cell)
        self._tree = cKDTree(self._boundary_uvw)

    # ------------------------------------------------------------- the tests
    def distance_to_material(self, xyz: np.ndarray) -> np.ndarray:
        """Exact distance in rdu from camera-frame points to the voxelised
        material set (0 inside it). Bracket to the true solid:
        ``[d - voxel_bracket, d]``."""
        xyz = np.atleast_2d(np.asarray(xyz, dtype=np.float64))
        uvw = self.frame.to_uvw(xyz)
        idx = self._voxel_index(uvw)
        d = np.empty(len(uvw), dtype=np.float64)
        ing = self._in_grid(idx)
        inside_solid = np.zeros(len(uvw), dtype=bool)
        if ing.any():
            ii = idx[ing]
            inside_solid[ing] = self.occupied[ii[:, 0], ii[:, 1], ii[:, 2]]
        d[inside_solid] = 0.0
        rest = ~inside_solid
        if rest.any():
            self._ensure_tree()
            d[rest], _ = self._tree.query(uvw[rest], workers=-1)
        return d

    def classify(self, xyz: np.ndarray, clearance: float | None = None,
                 *, conservative: bool = True) -> np.ndarray:
        """INSIDE / OUTSIDE / UNKNOWN per point.

        UNKNOWN is returned only when the volume is ``frame_open`` and the point
        projects off the photograph — the one place where "not in the keep-out"
        would be a claim about material the camera never saw (R4).
        """
        c = self.clearance_rdu if clearance is None else float(clearance)
        self._check_clearance(c)
        xyz = np.atleast_2d(np.asarray(xyz, dtype=np.float64))
        d = self.distance_to_material(xyz)
        thresh = c + self.voxel_bracket if conservative else c
        out = np.where(d <= thresh, INSIDE, OUTSIDE).astype(np.uint8)

        if self.frame_open and self._intrinsics is not None:
            z = xyz[:, 2]
            with np.errstate(divide="ignore", invalid="ignore"):
                u = xyz[:, 0] * self._intrinsics.fx / z + self._intrinsics.cx
                v = xyz[:, 1] * self._intrinsics.fy / z + self._intrinsics.cy
            h, w = self._image_hw
            off = ~np.isfinite(u) | ~np.isfinite(v) | (u < 0) | (u > w - 1) \
                | (v < 0) | (v > h - 1) | (z <= 0)
            out[off & (out == OUTSIDE)] = UNKNOWN
        return out

    def is_inside(self, xyz: np.ndarray, clearance: float | None = None, *,
                  conservative: bool = True,
                  unknown_is_inside: bool = True) -> np.ndarray:
        """Is a point inside the keep-out volume?

        ``xyz`` is (3,) or (N, 3) in the A1 camera frame, in rdu.

        Defaults are R2's: the resolution bracket resolves toward *inside*, and
        a point the camera could not see (``UNKNOWN``) counts as *inside*.
        Both are switchable so the cost of each can be measured.
        """
        single = np.asarray(xyz).ndim == 1
        k = self.classify(xyz, clearance, conservative=conservative)
        out = (k == INSIDE) | (unknown_is_inside & (k == UNKNOWN))
        return bool(out[0]) if single else out

    # ------------------------------------------------------- image-space view
    def silhouette(self, scene: Scene, clearance: float | None = None) -> np.ndarray:
        """(H, W) bool on the depth grid: pixels whose ray meets the keep-out.

        This is what the volume looks like from where the photograph was taken,
        and it is the right picture to check the shape by eye against the RGB.
        It is *not* a claim about what a tool approaching from elsewhere sees.

        Rendered by marching each ray through the voxel grid, **not** by
        projecting voxel centres: at this camera one voxel subtends 3-10 px, so
        a scatter leaves a lattice of holes that reads as gaps in the volume
        when there are none. Step is one voxel along the ray, so nothing
        thicker than a voxel can be stepped over.
        """
        c = self.clearance_rdu if clearance is None else float(clearance)
        self._check_clearance(c)
        h, w = scene.shape
        keep = self.dist <= c

        rr, cc = np.meshgrid(np.arange(h), np.arange(w), indexing="ij")
        d = np.stack([(cc.ravel() - scene.intrinsics.cx) / scene.intrinsics.fx,
                      (rr.ravel() - scene.intrinsics.cy) / scene.intrinsics.fy,
                      np.ones(h * w)], axis=1)
        D = d @ self.frame.R.T                      # uvw direction per unit z
        D[:, 2] -= 0.0
        base = np.array([0.0, 0.0, -self.frame.offset])

        # the z range that can possibly intersect the grid
        corners = np.array(np.meshgrid([0, self.shape[0] - 1],
                                       [0, self.shape[1] - 1],
                                       [0, self.shape[2] - 1])).reshape(3, -1).T
        cx = self.frame.to_xyz(self.origin_uvw + corners * self.cell)
        z0, z1 = max(float(cx[:, 2].min()), 1e-6), float(cx[:, 2].max())
        step = self.cell / float(np.abs(d).sum(axis=1).max())

        out = np.zeros(h * w, dtype=bool)
        origin = self.origin_uvw
        shape = np.array(self.shape)
        for z in np.arange(z0, z1 + step, step):
            idx = np.rint((D * z + base - origin) / self.cell).astype(np.int32)
            ok = np.all((idx >= 0) & (idx < shape), axis=1) & ~out
            if not ok.any():
                continue
            ii = idx[ok]
            hit = keep[ii[:, 0], ii[:, 1], ii[:, 2]]
            sel = np.nonzero(ok)[0]
            out[sel[hit]] = True
        return out.reshape(h, w)

    def footprint(self, clearance: float | None = None) -> np.ndarray:
        """(nu, nv) bool — the keep-out's shadow on the datum plane.

        The 2-D shape the "is a radius good enough?" question is really about.
        """
        c = self.clearance_rdu if clearance is None else float(clearance)
        self._check_clearance(c)
        return (self.dist <= c).any(axis=2)

    # ------------------------------------------------------------- i/o
    def save(self, path: str) -> str:
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        np.savez_compressed(
            path,
            e1=self.frame.e1, e2=self.frame.e2, n=self.frame.n,
            plane_offset=np.float64(self.frame.offset),
            cell=np.float64(self.cell), origin_uvw=self.origin_uvw,
            tier=self.tier,
            dist=np.minimum(self.dist,
                            self.max_clearance_rdu * 2).astype(np.float16),
            clearance_rdu=np.float64(self.clearance_rdu),
            max_clearance_rdu=np.float64(self.max_clearance_rdu),
            frame_open=np.bool_(self.frame_open),
            meta=np.frombuffer(json.dumps({
                "occupancy": self.occupancy,
                "include_unseen": bool(self.include_unseen),
                "scale_confidence": self.scale_confidence,
                "units": self.units,
                "datum": self.datum,
                "provenance": self.provenance,
                "dist_note": ("stored float16 and clipped at 2x "
                              "max_clearance_rdu; distances beyond the "
                              "padding were never valid anyway"),
            }).encode("utf-8"), dtype=np.uint8))
        return path


# --------------------------------------------------------------------------
# Building
# --------------------------------------------------------------------------


def build_keepout(scene: Scene, crop, *,
                  cell: float = DEFAULT_CELL_RDU,
                  clearance: float = DEFAULT_CLEARANCE_RDU,
                  max_clearance: float = max(CLEARANCE_SWEEP_RDU),
                  occupancy: Occupancy = "column",
                  include_unseen: bool = True,
                  frame: DatumFrame | None = None,
                  compute_dist: bool = True) -> KeepOutVolume:
    """Build the keep-out volume for one A4 component.

    No length in this function is a spacing parameter. ``cell`` is a reporting
    resolution, ``clearance`` is the tool parameter, and nothing else in here
    has a unit of length at all.
    """
    if occupancy not in ("column", "shell"):
        raise ValueError("occupancy must be 'column' or 'shell'")
    frame = frame or DatumFrame.from_scene(scene)

    masks = [(crop.observed, TIER_OBSERVED)]
    if include_unseen:
        masks.append((crop.unseen, TIER_UNSEEN))

    valid = scene.a2.valid & np.isfinite(scene.height_plane_normal)
    finite = np.isfinite(scene.xyz).all(axis=2)

    # --- gather every column, in datum coordinates --------------------------
    cols = []
    for mask, tier in masks:
        m = mask & finite
        if not m.any():
            continue
        rows, colsi = np.nonzero(m)
        uvw = frame.to_uvw(scene.xyz[rows, colsi])
        top = uvw[:, 2]
        if occupancy == "column":
            h = np.where(valid[rows, colsi],
                         np.maximum(scene.height_plane_normal[rows, colsi], 0.0),
                         np.nan)
        else:
            h = np.zeros_like(top)
        cols.append((uvw[:, 0], uvw[:, 1], top, h, tier,
                     int((~valid[rows, colsi]).sum()) if occupancy == "column" else 0))

    u_all = np.concatenate([c[0] for c in cols])
    v_all = np.concatenate([c[1] for c in cols])
    top_all = np.concatenate([c[2] for c in cols])
    h_all = np.concatenate([c[3] for c in cols])
    bot_all = top_all - np.nan_to_num(h_all, nan=0.0)

    pad = int(np.ceil(max_clearance / cell)) + 2
    u0 = u_all.min() - pad * cell
    v0 = v_all.min() - pad * cell
    w0 = np.nanmin(bot_all) - pad * cell
    nu = int(np.ceil((u_all.max() - u0) / cell)) + pad + 1
    nv = int(np.ceil((v_all.max() - v0) / cell)) + pad + 1
    nw = int(np.ceil((top_all.max() - w0) / cell)) + pad + 1
    n_vox = nu * nv * nw
    if n_vox > 120_000_000:
        raise MemoryError(
            f"grid would be {nu}x{nv}x{nw} = {n_vox/1e6:.0f} M voxels; raise "
            f"`cell` or lower `max_clearance` rather than swapping to disk")
    origin = np.array([u0, v0, w0])

    # --- per-cell floor and ceiling, per tier -------------------------------
    tier_grid = np.zeros((nu, nv, nw), dtype=np.uint8)
    karr = np.arange(nw)
    n_no_datum = 0
    for u, v, top, h, tier, n_nd in cols:
        n_no_datum += n_nd
        iu = np.rint((u - u0) / cell).astype(np.int64)
        iv = np.rint((v - v0) / cell).astype(np.int64)
        flat = iu * nv + iv
        ktop = np.rint((top - w0) / cell).astype(np.int64)
        kbot_f = np.full(nu * nv, np.iinfo(np.int32).max, dtype=np.int64)
        ktop_f = np.full(nu * nv, -1, dtype=np.int64)
        np.maximum.at(ktop_f, flat, ktop)
        good = np.isfinite(h)
        if good.any():
            kb = np.rint((top[good] - h[good] - w0) / cell).astype(np.int64)
            np.minimum.at(kbot_f, flat[good], kb)
        # cells with material but no observed datum under them: the surface
        # voxel only. Counted and reported, never silently extrapolated (R4).
        has = ktop_f >= 0
        kbot_f = np.where(kbot_f > ktop_f, ktop_f, kbot_f)
        sel = np.nonzero(has)[0]
        kb = kbot_f[sel][:, None]
        kt = ktop_f[sel][:, None]
        block = (karr[None, :] >= kb) & (karr[None, :] <= kt)
        su, sv = np.divmod(sel, nv)
        sub = tier_grid[su, sv]
        sub[block & (sub == TIER_EMPTY)] = tier
        tier_grid[su, sv] = sub

    dist = None
    if compute_dist:
        dist = ndimage.distance_transform_edt(
            tier_grid == TIER_EMPTY, sampling=(cell, cell, cell))
        dist = np.minimum(dist, max_clearance * 2.0).astype(np.float32)

    vol = KeepOutVolume(
        frame=frame, cell=float(cell), origin_uvw=origin, tier=tier_grid,
        dist=dist, clearance_rdu=float(clearance),
        max_clearance_rdu=float(max_clearance), occupancy=occupancy,
        include_unseen=bool(include_unseen), frame_open=bool(crop.frame_open),
        provenance={
            "chunk": "A6",
            "a1_product": "primary_raster (1344x1008, never resampled)",
            "a2": {"datum": scene.a2.datum,
                   "datum_roughness_sigma_rdu": scene.a2.sigma_datum},
            "a4": {"policy": crop.policy, "component_id": crop.component_id,
                   "unresolved_edges_on_component": crop.n_unresolved,
                   "frame_open": bool(crop.frame_open)},
            "crop_identity": crop.identity_provenance,
            "camera": scene.intrinsics.as_dict(),
            "grid": {"shape": [nu, nv, nw], "cell_rdu": float(cell),
                     "origin_uvw": origin.tolist(),
                     "pad_cells": pad},
            "columns_without_an_observed_datum_px": int(n_no_datum),
            "occupancy_assumption": (
                "column: material implies the vertical column beneath it down "
                "to the A2 straw datum is not free space. R2/R4: the alternative "
                "is a fabricated claim that unobserved space is empty."
                if occupancy == "column" else
                "shell: only the observed surface voxels. DIAGNOSTIC ONLY - it "
                "asserts that space behind a leaf is empty, which one view "
                "cannot support."),
        })
    vol._intrinsics = scene.intrinsics
    vol._image_hw = scene.shape
    return vol


def load_keepout(path: str) -> KeepOutVolume:
    z = np.load(path, allow_pickle=False)
    meta = json.loads(bytes(z["meta"]).decode("utf-8"))
    frame = DatumFrame(e1=z["e1"], e2=z["e2"], n=z["n"],
                       offset=float(z["plane_offset"]))
    vol = KeepOutVolume(
        frame=frame, cell=float(z["cell"]), origin_uvw=z["origin_uvw"],
        tier=z["tier"], dist=z["dist"].astype(np.float32),
        clearance_rdu=float(z["clearance_rdu"]),
        max_clearance_rdu=float(z["max_clearance_rdu"]),
        occupancy=meta["occupancy"], include_unseen=meta["include_unseen"],
        frame_open=bool(z["frame_open"]),
        scale_confidence=meta["scale_confidence"], units=meta["units"],
        datum=meta["datum"], provenance=meta["provenance"])
    # restore the camera, so `classify` can still say UNKNOWN off-frame
    cam = meta["provenance"].get("camera")
    if cam:
        vol._intrinsics = Intrinsics(
            fx=cam["fx"], fy=cam["fy"], cx=cam["cx"], cy=cam["cy"],
            width=cam["width"], height=cam["height"],
            provenance=cam["provenance"], note=cam.get("note", ""))
        vol._image_hw = (cam["height"], cam["width"])
    return vol
