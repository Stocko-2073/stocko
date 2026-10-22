"""A6 — shared loading and the datum-aligned frame.

Everything A6 does happens in one rigid frame, built once here, so that a
distance in the keep-out volume is a distance in the reconstruction and nothing
is silently rescaled.

Three facts travel with every number this module returns and must not be
dropped (they are A1's, A2's and A4's, not A6's):

1. ``scale_confidence = "scale_free"``. Every length is in **rdu**
   (1 rdu = median scene depth of the A1 primary raster). There is no metre
   anywhere in A6 and A1b has not landed.
2. **The datum is the STRAW mulch surface**, not soil. The floor of the
   keep-out volume is the top of the mulch, offset from the soil by an
   unmeasured straw depth.
3. **A component is a connected piece of observed material, not a proof of a
   plant.** A6 reads ``unresolved_for(component)`` and treats the material on
   the far side of an undecided link as *unseen volume*, never as empty space.
"""
from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))

for _p in (os.path.join(ROOT, "chunks", "A0"),
           os.path.join(ROOT, "chunks", "A1"),
           os.path.join(ROOT, "chunks", "A2"),
           os.path.join(ROOT, "chunks", "A4")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from a2_api import load_a2                                    # noqa: E402
from a4_api import load_a4                                    # noqa: E402
from depth_to_cloud import (Intrinsics, depth_to_cloud,       # noqa: E402
                            load_depth_product)

SCALE_CONFIDENCE = "scale_free"
UNITS = "rdu (relative depth units; 1 rdu = median scene depth)"

#: The A1 product A2 and A4 both used. A6 uses the same one, unresampled.
A1_PRODUCT = "primary_raster"
A1_DEPTH_DIR = os.path.join(ROOT, "chunks", "A1", "depth",
                            "da3nested-giant-large_res1344")

#: A0's ground-truth label grid, and the depth grid. Both are uniform
#: resamplings of the native 3000x4000 photograph by the *same* factor in x and
#: y, so one maps to the other by a single scalar (1.3125). (a) grid property.
GT_HW = (1024, 768)
DEPTH_HW = (1344, 1008)

#: A0 material ids (groundtruth/SCHEMA.md).
MAT_UNLABELLED, MAT_SQUASH_LEAF, MAT_SQUASH_PETIOLE = 0, 1, 2
MAT_GRASS, MAT_BROADLEAF, MAT_STRAW, MAT_SOIL, MAT_FRUIT, MAT_OTHER = 3, 4, 5, 6, 7, 8
GT_CROP_INSTANCE = 1          # A0: the squash, crop=true. Stand-in for A7.
GT_GRASS_UNRESOLVED = 255


# --------------------------------------------------------------------------
# Scene: depth, camera, cloud, datum
# --------------------------------------------------------------------------


@dataclass
class Scene:
    """The one reconstruction A6 works in. Nothing here is A6's own."""

    xyz: np.ndarray          # (H, W, 3) float64, camera frame, rdu. NaN where invalid
    intrinsics: Intrinsics
    normaliser: float        # depth units per rdu (A1's rdu normaliser)
    a2: object               # A2Product on the native depth grid
    plane_n: np.ndarray      # (3,) unit normal of A2's RANSAC plane
    plane_offset: float      # plane is {X : n.X = offset}
    height_plane_normal: np.ndarray   # (H, W) rdu, A2's height along plane_n
    manifest: dict

    @property
    def shape(self):
        return self.xyz.shape[:2]

    def height_above_plane(self, xyz: np.ndarray) -> np.ndarray:
        """Signed height of a point above A2's RANSAC plane, camera side positive."""
        return xyz @ self.plane_n - self.plane_offset

    def project(self, xyz: np.ndarray) -> np.ndarray:
        """Camera-frame points -> (col, row) float pixel coordinates."""
        z = xyz[..., 2]
        with np.errstate(divide="ignore", invalid="ignore"):
            u = xyz[..., 0] * self.intrinsics.fx / z + self.intrinsics.cx
            v = xyz[..., 1] * self.intrinsics.fy / z + self.intrinsics.cy
        return np.stack([u, v], axis=-1)

    def datum_points(self) -> np.ndarray:
        """(H, W, 3) — where each ray meets the fitted straw datum."""
        z = self.xyz[..., 2]
        with np.errstate(divide="ignore", invalid="ignore"):
            scale = self.a2.soil_depth / z
        return self.xyz * scale[..., None]


def load_scene() -> Scene:
    """Rebuild the A1/A2 geometry exactly as A2 and A4 did. No resampling."""
    manifest = json.load(open(os.path.join(ROOT, "chunks", "A1", "products",
                                           "MANIFEST.json")))
    cam = manifest["products"][A1_PRODUCT]["camera"]
    intr = Intrinsics(fx=cam["fx"], fy=cam["fy"], cx=cam["cx"], cy=cam["cy"],
                      width=cam["width"], height=cam["height"],
                      provenance="model_estimated", note=cam["note"])

    product = load_depth_product(A1_DEPTH_DIR)
    # NOTE: the intrinsics stored beside this raster are the run's own estimate,
    # which A1 rejected (fx/fy = 0.543, impossible for square pixels). The camera
    # above is A1's res-504 estimate rescaled, exactly what A2 and A4 used.
    cloud = depth_to_cloud(product.depth, intr, mode="scale_free")
    xyz = cloud.as_raster(product.depth.shape)

    a2 = load_a2()
    fit = json.load(open(os.path.join(ROOT, "chunks", "A2", "results",
                                      "fit_report_primary_raster.json")))
    plane_n = np.asarray(fit["ransac"]["normal"], dtype=np.float64)
    plane_n = plane_n / np.linalg.norm(plane_n)
    plane_offset = float(fit["ransac"]["offset_rdu"])

    hpn = np.load(os.path.join(ROOT, "chunks", "A2", "products",
                               "height_above_soil_plane_normal.npy"))

    return Scene(xyz=xyz, intrinsics=intr, normaliser=float(cloud.normaliser),
                 a2=a2, plane_n=plane_n, plane_offset=plane_offset,
                 height_plane_normal=hpn.astype(np.float64), manifest=manifest)


# --------------------------------------------------------------------------
# The datum-aligned frame
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class DatumFrame:
    """A rigid rotation of the camera frame whose third axis is 'up'.

    ``w`` is height above A2's RANSAC plane (camera side positive); ``u``, ``v``
    span the plane. The map is a rotation plus a translation along one axis, so
    **every Euclidean distance is preserved** — the keep-out volume is measured
    in the same rdu as the reconstruction it came from.
    """

    e1: np.ndarray
    e2: np.ndarray
    n: np.ndarray
    offset: float

    @classmethod
    def from_scene(cls, scene: Scene) -> "DatumFrame":
        n = scene.plane_n
        seed = np.array([1.0, 0.0, 0.0])
        if abs(seed @ n) > 0.9:
            seed = np.array([0.0, 1.0, 0.0])
        e1 = seed - n * (seed @ n)
        e1 /= np.linalg.norm(e1)
        e2 = np.cross(n, e1)
        return cls(e1=e1, e2=e2, n=n, offset=scene.plane_offset)

    @property
    def R(self) -> np.ndarray:
        return np.stack([self.e1, self.e2, self.n], axis=0)

    def to_uvw(self, xyz: np.ndarray) -> np.ndarray:
        out = xyz @ self.R.T
        out[..., 2] -= self.offset
        return out

    def to_xyz(self, uvw: np.ndarray) -> np.ndarray:
        q = uvw.copy()
        q[..., 2] += self.offset
        return q @ self.R


# --------------------------------------------------------------------------
# Ground truth on the depth grid
# --------------------------------------------------------------------------

GT_TO_DEPTH = DEPTH_HW[0] / GT_HW[0]      # 1.3125, identical in x and y


def gt_rc_to_depth_rc(rows: np.ndarray, cols: np.ndarray):
    """A0 grid -> depth grid, nearest. One scalar, because both grids are
    uniform resamplings of the same photograph by the same factor in x and y."""
    r = np.clip(np.rint(np.asarray(rows) * GT_TO_DEPTH).astype(np.int64),
                0, DEPTH_HW[0] - 1)
    c = np.clip(np.rint(np.asarray(cols) * GT_TO_DEPTH).astype(np.int64),
                0, DEPTH_HW[1] - 1)
    return r, c


def load_gt():
    import eval as a0eval
    return a0eval.load_gt()


# --------------------------------------------------------------------------
# The crop component and its unresolved edges
# --------------------------------------------------------------------------


@dataclass
class CropComponent:
    """The A4 component A6 protects, plus everything A4 refused to decide."""

    component_id: int
    policy: str
    observed: np.ndarray       # (H, W) bool on the depth grid — the component
    unseen: np.ndarray         # (H, W) bool — material behind an undecided link
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


def load_crop_component(policy: str = "merge",
                        gt=None) -> CropComponent:
    """Load the A4 component that carries the crop, and its unseen halo.

    **Crop identity is taken from A0 ground truth (instance 1, `crop: true`),
    as an explicit stand-in for A7's VLM labels, which run in parallel and are
    not available.** A8 wires the real path; nothing else in A6 depends on how
    the identity arrived.
    """
    a4 = load_a4(tag=policy)
    if gt is None:
        gt = load_gt()

    squash = gt.instances == GT_CROP_INSTANCE
    rows, cols = np.nonzero(squash)
    dr, dc = gt_rc_to_depth_rc(rows, cols)
    lab = a4.components_depth[dr, dc]
    lab = lab[lab > 0]
    ids, counts = np.unique(lab, return_counts=True)
    cid = int(ids[int(np.argmax(counts))])

    observed = a4.components_depth == cid

    frag = np.load(os.path.join(ROOT, "chunks", "A4", "work",
                                f"fragments_{policy}.npy"))
    f2c = _fragment_to_component(frag, a4.components_depth)

    edges = a4.unresolved_for(cid)
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
            if f2c.get(int(f), 0) != cid:
                neighbours.add(int(f))
    unseen = (np.isin(frag, sorted(neighbours)) if neighbours
              else np.zeros_like(observed))
    unseen &= ~observed

    return CropComponent(
        component_id=cid, policy=policy, observed=observed, unseen=unseen,
        frame_open=kinds.get("leaves_frame", 0) > 0, n_unresolved=kinds,
        frame_fragment_px=frame_px, a4=a4,
        identity_provenance=(
            "A0 ground truth instance 1 (crop=true), matched to the A4 "
            f"'{policy}' component with the largest overlap. STAND-IN for A7's "
            "VLM labels (R3: the label is an ID, never a coordinate); A8 wires "
            "the real path."))
