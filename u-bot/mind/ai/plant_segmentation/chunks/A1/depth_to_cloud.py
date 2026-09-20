"""
A1 — back-projection from a depth raster to a 3D point cloud, with the scale
story kept honest.

The one rule this module exists to enforce: **it never invents a camera.**
There is no default focal length anywhere in this file. If the geometry cannot
be formed from something the caller actually has, the call raises.

Two modes, as required by the roadmap:

``mode="assumed"``
    Intrinsics are supplied by hand (A1b's `f` sweep lives here). Coordinates
    come out looking metric, and are flagged ``scale_confidence="assumed_scale"``
    so no downstream artifact can quietly present them as measured.
    **Raises `MissingIntrinsicsError` if intrinsics is None.**

``mode="scale_free"``
    Geometry up to an unknown similarity transform. All coordinates are divided
    by a normaliser derived from the scene itself (the median valid depth), so
    distances are in *relative depth units* (rdu), 1 rdu = the median scene
    depth. Ratios, planarity residuals and connectivity survive; absolute size
    is not claimed. Flagged ``scale_confidence="scale_free"``.

A note on why ``scale_free`` still needs intrinsics
---------------------------------------------------
"Up to a similarity transform" permits an unknown scale, rotation and
translation. It does *not* permit an unknown focal length: `f` changes the
*shape* of the reconstruction, not just its size (roadmap, Known gaps #4).
So a Euclidean cloud is impossible without some `f`, in either mode.

What ``scale_free`` avoids is *inventing* one. Depth Anything 3 regresses its
own field of view internally (`CameraDec.fc_fov`) and the depth it emits is
already conditioned on that guess, so using DA3's own K makes the reconstruction
*self-consistent with the depth being fed in* — which is the strongest claim
available for this image. Those intrinsics ride along in the depth product and
are labelled ``model_estimated``. If a caller has neither hand intrinsics nor a
depth product carrying model intrinsics, ``scale_free`` raises too. There is no
third path.

Usage
-----
    from depth_to_cloud import load_depth_product, depth_to_cloud, Intrinsics

    prod = load_depth_product("depth/da3-large_res1344")
    cloud = depth_to_cloud(prod, mode="scale_free")           # relative units
    cloud = depth_to_cloud(prod, Intrinsics(...), "assumed")  # flagged metric
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Literal

import numpy as np

Mode = Literal["assumed", "scale_free"]

#: The flag every downstream artifact must carry. Ordered weakest claim first.
SCALE_FREE = "scale_free"
ASSUMED_SCALE = "assumed_scale"
MEASURED_SCALE = "measured_scale"  # not reachable in Phase A; here so C0 has a slot.

VALID_SCALE_CONFIDENCE = (SCALE_FREE, ASSUMED_SCALE, MEASURED_SCALE)


class MissingIntrinsicsError(ValueError):
    """Raised instead of guessing a camera."""


class ScaleConfidenceError(ValueError):
    """Raised when an artifact would be written without a scale-confidence flag."""


# --------------------------------------------------------------------------
# Camera
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Intrinsics:
    """A pinhole camera. No distortion model — DA3 assumes none either.

    ``provenance`` is mandatory and free-text-but-checked: it must say where the
    numbers came from, because R1 makes that the difference between a constant
    and a defect.
    """

    fx: float
    fy: float
    cx: float
    cy: float
    width: int
    height: int
    provenance: str  # one of PROVENANCE, below
    note: str = ""

    PROVENANCE = ("assumed", "assumed+refined", "model_estimated", "calibrated")

    def __post_init__(self) -> None:
        if self.provenance not in self.PROVENANCE:
            raise ValueError(
                f"intrinsics provenance must be one of {self.PROVENANCE}, "
                f"got {self.provenance!r} — R1: a constant with no traceable "
                f"origin is a defect"
            )
        for name in ("fx", "fy"):
            if not np.isfinite(getattr(self, name)) or getattr(self, name) <= 0:
                raise ValueError(f"{name} must be finite and positive")

    @classmethod
    def from_focal_px(
        cls,
        f: float,
        width: int,
        height: int,
        provenance: str,
        *,
        principal_point_at_centre: bool,
        note: str = "",
    ) -> "Intrinsics":
        """Square-pixel camera. ``principal_point_at_centre`` is deliberately a
        required keyword: pinning the principal point to the image centre is an
        assumption (A1b registers it as category (d)), not a formality."""
        if not principal_point_at_centre:
            raise ValueError(
                "from_focal_px only builds centre-principal-point cameras; "
                "construct Intrinsics(...) directly to place it elsewhere"
            )
        return cls(
            fx=float(f),
            fy=float(f),
            cx=(width - 1) / 2.0,
            cy=(height - 1) / 2.0,
            width=int(width),
            height=int(height),
            provenance=provenance,
            note=note,
        )

    @classmethod
    def from_K(
        cls, K: np.ndarray, width: int, height: int, provenance: str, note: str = ""
    ) -> "Intrinsics":
        K = np.asarray(K, dtype=np.float64)
        if K.shape != (3, 3):
            raise ValueError(f"K must be 3x3, got {K.shape}")
        if abs(K[0, 1]) > 1e-9:
            raise ValueError("non-zero skew is not supported")
        return cls(
            fx=float(K[0, 0]),
            fy=float(K[1, 1]),
            cx=float(K[0, 2]),
            cy=float(K[1, 2]),
            width=int(width),
            height=int(height),
            provenance=provenance,
            note=note,
        )

    def scaled_to(self, width: int, height: int) -> "Intrinsics":
        """Rescale to a different sampling of the same view.

        The principal point uses the half-pixel-corrected mapping
        ``c' = (c + 0.5) s - 0.5``, which is the correct one when pixel centres
        sit at integer indices. (DA3's own ``InputProcessor._resize_ixt`` uses
        the naive ``c' = c s``; the difference is under half a pixel and only
        bites for supplied intrinsics, never for the model's own, whose
        principal point is pinned to the centre either way.)
        """
        sx, sy = width / self.width, height / self.height
        return Intrinsics(
            fx=self.fx * sx,
            fy=self.fy * sy,
            cx=(self.cx + 0.5) * sx - 0.5,
            cy=(self.cy + 0.5) * sy - 0.5,
            width=int(width),
            height=int(height),
            provenance=self.provenance,
            note=(self.note + f" [rescaled from {self.width}x{self.height}]").strip(),
        )

    @property
    def fov_deg(self) -> tuple[float, float]:
        """(horizontal, vertical) field of view in degrees."""
        return (
            float(np.degrees(2 * np.arctan(self.width / (2 * self.fx)))),
            float(np.degrees(2 * np.arctan(self.height / (2 * self.fy)))),
        )

    def as_dict(self) -> dict:
        d = asdict(self)
        d["fov_horizontal_deg"], d["fov_vertical_deg"] = self.fov_deg
        return d


# --------------------------------------------------------------------------
# Depth product (what da3_infer.py wrote)
# --------------------------------------------------------------------------


@dataclass
class DepthProduct:
    """A float depth raster plus everything known about where it came from."""

    depth: np.ndarray  # (H, W) float32/float64, z along the optical axis
    provenance: dict[str, Any]
    conf: np.ndarray | None = None
    model_intrinsics: Intrinsics | None = None
    path: str | None = None

    @property
    def shape(self) -> tuple[int, int]:
        return self.depth.shape[0], self.depth.shape[1]

    @property
    def is_metric_claim(self) -> bool:
        return bool(self.provenance.get("output_semantics", {}).get("is_metric", 0))


def load_depth_product(directory: str | Path) -> DepthProduct:
    d = Path(directory)
    depth = np.load(d / "depth.npy")
    prov = json.loads((d / "provenance.json").read_text())
    conf = np.load(d / "conf.npy") if (d / "conf.npy").exists() else None

    K_path = d / "intrinsics.npy"
    intr = None
    if K_path.exists():
        h, w = depth.shape[:2]
        intr = Intrinsics.from_K(
            np.load(K_path),
            width=w,
            height=h,
            provenance="model_estimated",
            note=(
                "regressed by Depth Anything 3's CameraDec.fc_fov; the depth in "
                "this product is conditioned on it, so it is self-consistent, "
                "not measured"
            ),
        )
    return DepthProduct(
        depth=depth, provenance=prov, conf=conf, model_intrinsics=intr, path=str(d)
    )


# --------------------------------------------------------------------------
# Point cloud
# --------------------------------------------------------------------------


@dataclass
class PointCloud:
    """Nx3 cloud in camera space, with the scale claim attached.

    ``scale_confidence`` is not optional and not decorative. Anything written to
    disk from this object carries it (see :func:`save_cloud`).
    """

    xyz: np.ndarray  # (N, 3) float64
    pixel_rc: np.ndarray  # (N, 2) int32, (row, col) into the source raster
    scale_confidence: str
    units: str
    mode: str
    intrinsics: Intrinsics
    normaliser: float | None  # depth divided by this, if any (scale_free)
    provenance: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.scale_confidence not in VALID_SCALE_CONFIDENCE:
            raise ScaleConfidenceError(
                f"scale_confidence must be one of {VALID_SCALE_CONFIDENCE}"
            )

    def __len__(self) -> int:
        return int(self.xyz.shape[0])

    def as_raster(self, shape: tuple[int, int]) -> np.ndarray:
        """Scatter back to an (H, W, 3) raster; unfilled pixels are NaN."""
        out = np.full((shape[0], shape[1], 3), np.nan, dtype=np.float64)
        out[self.pixel_rc[:, 0], self.pixel_rc[:, 1]] = self.xyz
        return out

    def sidecar(self) -> dict:
        return {
            "n_points": len(self),
            "scale_confidence": self.scale_confidence,
            "units": self.units,
            "mode": self.mode,
            "normaliser_depth_units_per_rdu": self.normaliser,
            "intrinsics": self.intrinsics.as_dict(),
            "provenance": self.provenance,
        }


def depth_to_cloud(
    depth: np.ndarray | DepthProduct,
    intrinsics: Intrinsics | None = None,
    mode: Mode = "scale_free",
    *,
    mask: np.ndarray | None = None,
    conf: np.ndarray | None = None,
    conf_min: float | None = None,
    subsample: int = 1,
) -> PointCloud:
    """Back-project a depth raster into an Nx3 camera-space point cloud.

    Parameters
    ----------
    depth
        (H, W) float array of z-depth (distance along the optical axis, *not*
        ray length), or a :class:`DepthProduct`.
    intrinsics
        Pinhole camera. Required for ``mode="assumed"``. For ``mode="scale_free"``
        it may be omitted **only** when ``depth`` is a DepthProduct that carries
        model-estimated intrinsics.
    mode
        ``"assumed"`` or ``"scale_free"``. See the module docstring.
    mask
        Optional (H, W) boolean; True keeps the pixel.
    conf, conf_min
        Optional confidence raster and threshold. If ``depth`` is a DepthProduct
        its ``conf`` is used unless ``conf`` is passed explicitly.
    subsample
        Take every n-th pixel in each axis. 1 = all pixels.

    Raises
    ------
    MissingIntrinsicsError
        When ``mode="assumed"`` and no intrinsics were supplied, or when
        ``mode="scale_free"`` and no intrinsics are available from any source.
        The module never falls back to a default camera.
    """
    if mode not in ("assumed", "scale_free"):
        raise ValueError(f"mode must be 'assumed' or 'scale_free', got {mode!r}")

    product: DepthProduct | None = None
    if isinstance(depth, DepthProduct):
        product = depth
        if conf is None:
            conf = product.conf
        depth_arr = np.asarray(product.depth, dtype=np.float64)
    else:
        depth_arr = np.asarray(depth, dtype=np.float64)

    if depth_arr.ndim != 2:
        raise ValueError(f"depth must be 2-D (H, W), got shape {depth_arr.shape}")
    h, w = depth_arr.shape

    # ---- resolve the camera, or refuse ------------------------------------
    if mode == "assumed":
        if intrinsics is None:
            raise MissingIntrinsicsError(
                "mode='assumed' requires intrinsics. This image has no EXIF and "
                "the camera is unavailable, so there is nothing to fall back to "
                "and guessing one here would hide the assumption. Supply an "
                "Intrinsics with provenance='assumed' (see chunk A1b), or use "
                "mode='scale_free'."
            )
        if intrinsics.provenance == "model_estimated":
            raise ValueError(
                "mode='assumed' is for hand-supplied intrinsics. Model-estimated "
                "intrinsics belong to mode='scale_free' — they are self-consistent "
                "with the depth, not an independent measurement, and treating them "
                "as metric would overclaim."
            )
    else:  # scale_free
        if intrinsics is None:
            if product is not None and product.model_intrinsics is not None:
                intrinsics = product.model_intrinsics
            else:
                raise MissingIntrinsicsError(
                    "mode='scale_free' still needs a focal length: f sets the "
                    "*shape* of the reconstruction, and a similarity transform "
                    "cannot absorb it. No intrinsics were passed and the depth "
                    "product carries none. Pass Intrinsics explicitly, or use a "
                    "depth product from a model that reports its own camera."
                )

    if (intrinsics.width, intrinsics.height) != (w, h):
        intrinsics = intrinsics.scaled_to(width=w, height=h)

    # ---- select pixels -----------------------------------------------------
    valid = np.isfinite(depth_arr) & (depth_arr > 0)
    if mask is not None:
        if mask.shape != depth_arr.shape:
            raise ValueError("mask shape must match depth shape")
        valid &= mask.astype(bool)
    if conf is not None and conf_min is not None:
        conf = np.asarray(conf)
        if conf.shape != depth_arr.shape:
            raise ValueError("conf shape must match depth shape")
        valid &= conf >= conf_min
    if subsample > 1:
        keep = np.zeros_like(valid)
        keep[::subsample, ::subsample] = True
        valid &= keep

    rows, cols = np.nonzero(valid)
    z = depth_arr[rows, cols]

    # ---- normalise, or don't ----------------------------------------------
    normaliser: float | None = None
    if mode == "scale_free":
        # A scene statistic, not a constant: category (c). Recorded so the
        # transform is reversible.
        normaliser = float(np.median(z))
        if not np.isfinite(normaliser) or normaliser <= 0:
            raise ValueError("cannot normalise: median valid depth is not positive")
        z = z / normaliser
        units = "rdu (relative depth units; 1 rdu = median scene depth)"
        scale_confidence = SCALE_FREE
    else:
        units = (
            "same units as the input depth raster — ASSUMED, not measured; "
            "see scale_confidence"
        )
        scale_confidence = ASSUMED_SCALE

    # ---- back-project ------------------------------------------------------
    # Pixel centres are integer indices, matching DA3's own unprojection
    # (torch.meshgrid over arange, no +0.5 offset). Keeping the same convention
    # means our cloud and DA3's differ by nothing.
    x = (cols.astype(np.float64) - intrinsics.cx) * z / intrinsics.fx
    y = (rows.astype(np.float64) - intrinsics.cy) * z / intrinsics.fy
    xyz = np.stack([x, y, z], axis=1)

    prov: dict[str, Any] = {
        "source_depth_shape": [h, w],
        "n_valid": int(valid.sum()),
        "n_total": int(h * w),
        "subsample": subsample,
        "conf_min": conf_min,
        "camera_convention": (
            "+x right, +y down, +z into the scene; camera at the origin; "
            "z-depth (not ray length); pixel centres at integer indices"
        ),
        "intrinsics_provenance": intrinsics.provenance,
    }
    if product is not None:
        ps = product.provenance
        prov["depth_provenance"] = {
            "model": ps.get("model", {}).get("hf_repo"),
            "revision": ps.get("model", {}).get("hf_revision"),
            "process_res": ps.get("preprocessing", {}).get("process_res"),
            "is_metric_claim": ps.get("output_semantics", {}).get("is_metric"),
            "path": product.path,
        }
        if mode == "assumed" and product.is_metric_claim:
            prov["warning"] = (
                "the depth product already claims metric units AND hand intrinsics "
                "were supplied; the two scales are independent guesses and are not "
                "reconciled here"
            )

    return PointCloud(
        xyz=xyz,
        pixel_rc=np.stack([rows, cols], axis=1).astype(np.int32),
        scale_confidence=scale_confidence,
        units=units,
        mode=mode,
        intrinsics=intrinsics,
        normaliser=normaliser,
        provenance=prov,
    )


def save_cloud(cloud: PointCloud, path: str | Path) -> Path:
    """Write ``<path>.npy`` + ``<path>.json``. The sidecar always carries the
    scale-confidence flag — that is the whole reason this helper exists rather
    than a bare ``np.save``."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    np.save(p.with_suffix(".npy"), cloud.xyz.astype(np.float32))
    side = cloud.sidecar()
    if side.get("scale_confidence") not in VALID_SCALE_CONFIDENCE:
        raise ScaleConfidenceError("refusing to write a cloud with no scale flag")
    p.with_suffix(".json").write_text(json.dumps(side, indent=2))
    return p
