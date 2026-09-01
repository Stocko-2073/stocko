"""A1b — the assumed camera, the candidate set, and the one piece of algebra
that explains every result in this chunk.

The algebra
-----------
`depth_to_cloud` forms, for a fixed depth raster ``z(u,v)``::

    x = (u - cx) * z / fx      y = (v - cy) * z / fy      z = z

Changing the focal length from ``f0`` to ``f1`` while holding the depth raster,
the principal point and the pixel grid fixed therefore maps every point of the
cloud by

    P  ->  S P,    S = diag(s, s, 1),    s = f0 / f1

`S` is a **linear, invertible** map. Two consequences run through this whole
chunk:

1. **Planes map to planes.** A set of points that is exactly planar under `f0`
   is exactly planar under `f1`, for every `f1`. So planarity residual is zero
   at every focal length whenever it is zero at one, and "choose `f` to minimise
   the planarity residual of a locally planar surface" has no interior optimum.
   This is why the refinement in `refine_focal.py` is degenerate, and it is a
   stronger statement than the roadmap's caveat: the degeneracy does not depend
   on DA3 having assumed an FOV, it is a property of the parametrisation.
2. **What survives and what does not.** Anything invariant under an axial
   scaling — incidence, connectivity, collinearity, ratios of lengths measured
   along the *same* direction, and any quantity divided by another quantity that
   scales the same way — is exactly focal-invariant. Angles, plane normals,
   and ratios between an in-plane length and a depth length are not.

Plane normals, exactly
----------------------
For a plane ``n . X = D`` under `f0`, the same points satisfy
``(S^-1 n) . (S X) = D``, so under `f1` the normal direction is

    n(f) ∝ (n_x * f / f0,  n_y * f / f0,  n_z)

which lets the focal dependence of any fitted normal be written down in closed
form rather than only sampled. `normal_reconciliation.py` uses both the closed
form and a full refit, and checks they agree.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
A1 = ROOT / "chunks" / "A1"
A2 = ROOT / "chunks" / "A2"
A3 = ROOT / "chunks" / "A3"
A4 = ROOT / "chunks" / "A4"
A5 = ROOT / "chunks" / "A5"
A0 = ROOT / "chunks" / "A0"
WORK = HERE / "work"
RESULTS = HERE / "results"
FIGS = HERE / "figs"
CALIB = ROOT / "calib"

for _p in (A1, A2):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from depth_to_cloud import Intrinsics  # noqa: E402

# --------------------------------------------------------------------------
# The photograph. Everything is quoted at this sampling so a focal length is
# one number, whatever grid it is used on.
# --------------------------------------------------------------------------
NATIVE_W, NATIVE_H = 3000, 4000
NATIVE_DIAG_PX = float(np.hypot(NATIVE_W, NATIVE_H))
FF_DIAG_MM = 43.266615305567875  # 36x24 mm full-frame diagonal


def f_px_from_equiv_mm(f_eq_mm: float) -> float:
    """35 mm-equivalent focal length -> pixels at 3000x4000."""
    return f_eq_mm * NATIVE_DIAG_PX / FF_DIAG_MM


def equiv_mm_from_f_px(f_px: float) -> float:
    return f_px * FF_DIAG_MM / NATIVE_DIAG_PX


# --------------------------------------------------------------------------
# The sweep set.
#
# The roadmap's five: {1502, 2774, 3005, 3236, 6009} px = 13/24/26/28/52 mm-eq.
# A1's finding: DA3's own camera head reports 4159-4695 px (mean 4489) in the
# band where it is physically consistent, which falls in the roadmap's gap
# between 3236 and 6009 — the planned sweep steps straight over the value the
# depth was actually produced under. A1's FINDINGS ask for that band to be
# added, and this is the widening it asked for. 4453 is DA3's res-504 estimate
# specifically, i.e. the camera every shipped Phase A product was built on, and
# is the value A1b adopts.
# --------------------------------------------------------------------------
ROADMAP_F = (1502.0, 2774.0, 3005.0, 3236.0, 6009.0)
DA3_BAND_F = (4159.0, 4453.0, 4489.0, 4695.0)
SWEEP_F = tuple(sorted(set(ROADMAP_F + DA3_BAND_F)))

#: A1b's initial pinhole value: 26 mm-equivalent phone main camera.
F_INITIAL = 3005.0

#: A1's registered observation *about the model*, at 3000x4000.
DA3_F_MEAN = 4488.7250423829755
DA3_F_MIN, DA3_F_MAX = 4159.074571397569, 4695.178727458294
#: DA3's res-504 nested-giant estimate — the camera in A1's MANIFEST.
DA3_F_RES504_FX = 4453.214615110367

#: What A1b chooses. See FINDINGS: the refinement is degenerate, so the choice
#: is argued rather than measured, and this is the value that makes the geometry
#: self-consistent with the depth field it is applied to.
F_CHOSEN = DA3_F_RES504_FX

CHOSEN_NOTE = (
    "A1b assumed pinhole camera. Zero distortion, principal point at the image "
    "centre, square pixels. f adopted from Depth Anything 3's own camera head at "
    "process_res=504 (the band A1 found physically consistent), because the "
    "planarity refinement the roadmap specified is degenerate in f (changing f "
    "is a linear map of the cloud, so planes stay planes) and the scene cannot "
    "adjudicate between this and the 26 mm-equivalent prior of 3005 px. This "
    "remains a category (d) ASSUMPTION, bounded by the A1b sweep, not a "
    "measurement. Absolute scale is UNRESOLVED and is not implied by this file."
)


# --------------------------------------------------------------------------
# Cameras
# --------------------------------------------------------------------------


def assumed_intrinsics(f_native: float, width: int, height: int,
                       provenance: str = "assumed",
                       note: str = "") -> Intrinsics:
    """A1b's pinhole camera at `f_native` px (quoted at 3000x4000), expressed on
    a `width` x `height` sampling of the same view.

    Square pixels, principal point at the centre of *this* grid, no distortion.
    All three are category (d) assumptions and all three are registered.
    """
    f = float(f_native) * width / NATIVE_W
    return Intrinsics.from_focal_px(
        f, width=width, height=height, provenance=provenance,
        principal_point_at_centre=True,
        note=note or f"A1b assumed pinhole, f={f_native:.1f} px at "
                     f"{NATIVE_W}x{NATIVE_H} "
                     f"({equiv_mm_from_f_px(f_native):.1f} mm-equivalent)",
    )


def manifest_intrinsics(product: str = "primary_raster") -> Intrinsics:
    """The camera A1's MANIFEST ships for a product — DA3's own, anisotropic.

    Included in the sweep as the reference row: it is what every shipped Phase A
    number was actually computed with, so it is the only row whose results must
    reproduce `RESULTS.md` exactly.
    """
    m = json.loads((A1 / "products" / "MANIFEST.json").read_text())
    c = m["products"][product]["camera"]
    return Intrinsics(fx=c["fx"], fy=c["fy"], cx=c["cx"], cy=c["cy"],
                      width=c["width"], height=c["height"],
                      provenance=c["provenance"], note=c["note"])


def f_native_of(intr: Intrinsics) -> tuple[float, float]:
    """(fx, fy) of an Intrinsics expressed at 3000x4000."""
    return (intr.fx * NATIVE_W / intr.width, intr.fy * NATIVE_H / intr.height)


# --------------------------------------------------------------------------
# The sweep's row identifiers. Strings, so filenames and JSON keys agree.
# --------------------------------------------------------------------------


def tag_for(f_native: float | None, aspect: str = "square") -> str:
    if aspect == "manifest":
        return "manifest"
    return f"f{int(round(f_native))}"


def a2_products_dir(tag: str) -> Path:
    return WORK / tag / "products"


def depth_product_dir(product: str) -> Path:
    m = json.loads((A1 / "products" / "MANIFEST.json").read_text())
    return A1 / os.path.dirname(m["products"][product]["depth"])


def rdu_normaliser(product: str = "primary_raster") -> float:
    """1 rdu, in the depth raster's own units. A scene statistic; f-invariant."""
    d = np.load(depth_product_dir(product) / "depth.npy").astype(np.float64)
    v = d[np.isfinite(d) & (d > 0)]
    return float(np.median(v))


# --------------------------------------------------------------------------
# The closed form of the focal dependence of a plane normal (see module docstring)
# --------------------------------------------------------------------------


def normal_at_f(normal: np.ndarray, f_from: float, f_to: float) -> np.ndarray:
    """A plane normal fitted under `f_from`, re-expressed under `f_to`."""
    n = np.asarray(normal, dtype=np.float64)
    r = float(f_to) / float(f_from)
    out = np.array([n[0] * r, n[1] * r, n[2]], dtype=np.float64)
    return out / np.linalg.norm(out)


def angle_deg(a: np.ndarray, b: np.ndarray) -> float:
    a = np.asarray(a, float) / np.linalg.norm(a)
    b = np.asarray(b, float) / np.linalg.norm(b)
    return float(np.degrees(np.arccos(np.clip(abs(a @ b), -1.0, 1.0))))
