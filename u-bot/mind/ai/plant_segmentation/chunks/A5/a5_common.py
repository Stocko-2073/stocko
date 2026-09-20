"""A5 — shared loading and geometry.

Everything here is `scale_free`. Distances in 3-D are in **rdu**
(1 rdu = the median scene depth of A1's `primary_raster`); distances in the
image plane are in pixels of whichever grid is named. There is no metre in this
chunk and A1b has not landed.

**The datum is the STRAW mulch surface, not bare soil** (A2). Every "contact
point" produced by A5 is a point on the mulch. It is offset from the true
stem-soil intersection by the straw depth, which is unmeasured and, from one
overhead photograph, unmeasurable.

Grids
-----
* **depth grid** — 1344 x 1008. A1's `primary_raster` and every A2 raster live
  here. All of A5's geometry is computed here, with the depth never resampled.
* **GT grid** — 1024 x 768 (h, w). A0's labels, A3's material map and A4's
  `components` live here. A5 reports every point on this grid too, so `eval.py`
  can read it.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
A1 = os.path.join(ROOT, "chunks", "A1")
A2 = os.path.join(ROOT, "chunks", "A2")
A3 = os.path.join(ROOT, "chunks", "A3")
A4 = os.path.join(ROOT, "chunks", "A4")

import sys  # noqa: E402

for _p in (A1, A2, A4, os.path.join(ROOT, "chunks", "A0")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from depth_to_cloud import Intrinsics, load_depth_product  # noqa: E402
from a2_api import EXTRAPOLATED, INTERPOLATED, OBSERVED, load_a2  # noqa: E402
from a4_api import load_a4  # noqa: E402

# A0 material class ids, reused unchanged (A0 SCHEMA.md).
MATERIAL = {0: "unlabelled", 1: "squash_leaf", 2: "squash_petiole", 3: "grass",
            4: "broadleaf_weed", 5: "straw", 6: "soil", 7: "fruit", 8: "other"}
STEM_CLASS = 2          # `squash_petiole` — the only stem class A0/A3 have
DRY_CLASSES = (5,)      # straw
FOLIAGE_CLASSES = (1, 3, 4, 7)


# ------------------------------------------------------------------ geometry
# The two helpers below are A2's, kept identical so A5's height field is the
# same field A2 published (verified numerically in test_a5.py).

def ray_directions(h: int, w: int, intr: Intrinsics) -> np.ndarray:
    v, u = np.mgrid[0:h, 0:w].astype(np.float64)
    return np.stack(
        [(u - intr.cx) / intr.fx, (v - intr.cy) / intr.fy, np.ones_like(u)], axis=-1
    )


def local_normals(P: np.ndarray, normal: np.ndarray) -> np.ndarray:
    """Unit normals of a 3-D surface raster, oriented to the same side as the
    global plane normal (A2 orients that toward the camera, never toward
    gravity)."""
    du = np.gradient(P, axis=1)
    dv = np.gradient(P, axis=0)
    n = np.cross(du, dv)
    n /= np.linalg.norm(n, axis=-1, keepdims=True) + 1e-300
    flip = np.sign(n @ normal)[..., None]
    flip[flip == 0] = 1.0
    return n * flip


@dataclass
class Scene:
    """Everything A5's geometry needs, all on the 1344x1008 depth grid."""
    depth_rdu: np.ndarray        # (H, W) float64, z-depth in rdu
    dirs: np.ndarray             # (H, W, 3) unit-z ray directions
    P: np.ndarray                # (H, W, 3) material points, rdu
    S: np.ndarray                # (H, W, 3) datum points along the same rays
    N: np.ndarray                # (H, W, 3) local datum normals, camera-facing
    height: np.ndarray           # (H, W) A2's height above the datum, rdu
    height_sigma: np.ndarray     # (H, W) A2's datum 1-sigma, rdu
    valid: np.ndarray            # (H, W) bool
    coverage: np.ndarray         # (H, W) 0 observed / 1 interpolated / 2 extrap
    ground: np.ndarray           # (H, W) bool, pixels A2 fitted the datum TO
    sigma_datum: float           # rdu
    intr: Intrinsics
    plane_normal: np.ndarray
    a2_manifest: dict
    a1_manifest: dict

    @property
    def shape(self):
        return self.height.shape

    def sigma_combined(self) -> np.ndarray:
        """Datum roughness and the local datum uncertainty, added in quadrature.
        A2's `confident_above` uses exactly this."""
        return np.sqrt(self.sigma_datum ** 2
                       + np.nan_to_num(self.height_sigma) ** 2)

    def signed_height(self, pts: np.ndarray) -> np.ndarray:
        """Height of arbitrary 3-D points above the fitted datum, measured the
        way A2 measures it: along the local surface normal at the pixel the
        point projects into. Points that project outside the frame get NaN."""
        pts = np.atleast_2d(np.asarray(pts, dtype=np.float64))
        u, v = self.project(pts)
        H, W = self.shape
        ok = (u >= 0) & (u <= W - 1) & (v >= 0) & (v <= H - 1)
        out = np.full(len(pts), np.nan)
        if not ok.any():
            return out
        iu = np.clip(np.rint(u[ok]).astype(int), 0, W - 1)
        iv = np.clip(np.rint(v[ok]).astype(int), 0, H - 1)
        s = self.S[iv, iu]
        n = self.N[iv, iu]
        out[ok] = np.einsum("ij,ij->i", pts[ok] - s, n)
        return out

    def project(self, pts: np.ndarray):
        """Camera-space points -> (u, v) pixel coordinates on the depth grid."""
        pts = np.atleast_2d(np.asarray(pts, dtype=np.float64))
        z = np.where(np.abs(pts[:, 2]) < 1e-12, np.nan, pts[:, 2])
        return (pts[:, 0] / z * self.intr.fx + self.intr.cx,
                pts[:, 1] / z * self.intr.fy + self.intr.cy)


def load_scene(product: str = "primary_raster") -> Scene:
    a1m = json.load(open(os.path.join(A1, "products", "MANIFEST.json")))
    entry = a1m["products"][product]
    prod = load_depth_product(os.path.join(A1, os.path.dirname(entry["depth"])))
    cam = entry["camera"]
    intr = Intrinsics(fx=cam["fx"], fy=cam["fy"], cx=cam["cx"], cy=cam["cy"],
                      width=cam["width"], height=cam["height"],
                      provenance=cam["provenance"], note=cam["note"])
    a2 = load_a2()
    norm = a2.manifest["source"]["rdu_normaliser_depth_units"]
    depth_rdu = np.asarray(prod.depth, dtype=np.float64) / norm
    h, w = depth_rdu.shape
    dirs = ray_directions(h, w, intr)
    plane_normal = np.asarray(
        json.load(open(os.path.join(A2, "results",
                                    f"fit_report_{product}.json")))["ransac"]["normal"],
        dtype=np.float64)
    S = dirs * a2.soil_depth[..., None].astype(np.float64)
    return Scene(
        depth_rdu=depth_rdu, dirs=dirs, P=dirs * depth_rdu[..., None], S=S,
        N=local_normals(S, plane_normal), height=a2.height.astype(np.float64),
        height_sigma=a2.height_sigma.astype(np.float64), valid=a2.valid,
        coverage=a2.coverage, ground=a2.ground, sigma_datum=a2.sigma_datum,
        intr=intr,
        plane_normal=plane_normal, a2_manifest=a2.manifest, a1_manifest=a1m)


# ------------------------------------------------------------------- rasters
def gt_to_depth(a: np.ndarray, shape=(1344, 1008)) -> np.ndarray:
    """Nearest-neighbour lift of a GT-grid label map onto the depth grid — the
    same direction and the same interpolation A4 used. Label maps are never
    interpolated."""
    from PIL import Image
    im = Image.fromarray(a.astype(np.int32), mode="I")
    return np.array(im.resize((shape[1], shape[0]), Image.NEAREST)).astype(a.dtype)


def depth_xy_to_gt_xy(u, v, depth_shape=(1344, 1008), gt_shape=(1024, 768)):
    """A point on the depth grid, expressed on A0's label grid. Both grids cover
    the same 3000x4000 photograph, so this is a pure scale."""
    return (np.asarray(u) * gt_shape[1] / depth_shape[1],
            np.asarray(v) * gt_shape[0] / depth_shape[0])


def load_a3_material_depth_grid() -> np.ndarray:
    """A3's shipped material map, lifted to the depth grid exactly as A4 does."""
    p = os.path.join(A4, "work", "a3_material.npz")
    if os.path.exists(p):
        m = np.load(p, allow_pickle=True)["m"]
    else:  # pragma: no cover - only when A4's cache has been cleaned
        sys.path.insert(0, A3)
        from a3_api import segment_material
        m = segment_material().material
    return gt_to_depth(m)


def load_gt_material_depth_grid() -> np.ndarray:
    from PIL import Image
    m = np.array(Image.open(os.path.join(ROOT, "groundtruth",
                                         "plants_material.png")))
    return gt_to_depth(m)


def load_rgb(shape=(1344, 1008)) -> np.ndarray:
    from PIL import Image
    im = Image.open(os.path.join(ROOT, "plants.jpeg")).convert("RGB")
    return np.asarray(im.resize((shape[1], shape[0]), Image.LANCZOS))
