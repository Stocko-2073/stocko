"""
A2 — the loader A3 / A4 / A5 should use.

    import sys; sys.path.insert(0, "chunks/A2")
    from a2_api import load_a2
    a2 = load_a2()                      # native 1344x1008 depth grid
    a2_full = load_a2(grid="image")     # resampled to plants.jpeg, 4000x3000

Every field carries the scale-confidence flag and the datum caveat, because the
single most dangerous way to use this product is to read `height_above_soil` as
a height above *soil*. It is a height above the *straw*.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent

OBSERVED, INTERPOLATED, EXTRAPOLATED = 0, 1, 2


@dataclass
class A2Product:
    height: np.ndarray            # (H, W) float32, rdu above the straw datum
    height_sigma: np.ndarray      # (H, W) float32, 1-sigma of the datum, rdu
    valid: np.ndarray             # (H, W) bool
    coverage: np.ndarray          # (H, W) uint8, see OBSERVED/INTERPOLATED/...
    support_px: np.ndarray        # (H, W) float32
    ground: np.ndarray            # (H, W) bool, pixels the surface was fitted to
    soil_depth: np.ndarray        # (H, W) float32, rdu z-depth of the datum
    manifest: dict
    scale_confidence: str
    datum: str

    @property
    def sigma_datum(self) -> float:
        """Roughness of the datum itself, in rdu. The natural unit for any
        'is this above the ground' question."""
        return float(self.manifest["key_numbers"]["datum_roughness_sigma_rdu"])

    def height_in_sigma(self) -> np.ndarray:
        """Height expressed in datum roughnesses — the scale-free, threshold-free
        way to ask how far above the ground something is."""
        return self.height / self.sigma_datum

    def confident_above(self, k: float = 3.0) -> np.ndarray:
        """Pixels whose height exceeds `k` sigma of the *combined* datum
        roughness and local surface uncertainty. Defaults to keep: a pixel with
        an uncertain datum under it does not qualify."""
        s = np.sqrt(self.sigma_datum**2 + np.nan_to_num(self.height_sigma) ** 2)
        return self.valid & (self.height > k * s)


def load_a2(products: str | Path | None = None, grid: str = "native") -> A2Product:
    pdir = Path(products) if products else HERE / "products"
    m = json.loads((pdir / "A2_MANIFEST.json").read_text())

    def g(name):
        return np.load(pdir / name)

    p = A2Product(
        height=g("height_above_soil.npy"),
        height_sigma=g("height_sigma.npy"),
        valid=g("validity_mask.npy"),
        coverage=g("coverage_class.npy"),
        support_px=g("support_distance_px.npy"),
        ground=g("ground_inliers.npy"),
        soil_depth=g("soil_surface_depth.npy"),
        manifest=m,
        scale_confidence=m["scale_confidence"],
        datum=m["DATUM"],
    )
    if grid == "native":
        return p
    if grid != "image":
        raise ValueError("grid must be 'native' or 'image'")

    from PIL import Image

    W, H = Image.open(ROOT / "plants.jpeg").size

    def up(a, nearest=False):
        im = Image.fromarray(a.astype(np.float32) if not nearest else a.astype(np.uint8))
        return np.asarray(
            im.resize((W, H), Image.NEAREST if nearest else Image.BILINEAR)
        )

    return A2Product(
        height=up(p.height), height_sigma=up(p.height_sigma),
        valid=up(p.valid, True).astype(bool), coverage=up(p.coverage, True),
        support_px=up(p.support_px), ground=up(p.ground, True).astype(bool),
        soil_depth=up(p.soil_depth), manifest=m,
        scale_confidence=p.scale_confidence, datum=p.datum,
    )
