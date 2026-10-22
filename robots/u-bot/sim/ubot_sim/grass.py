"""Deterministic rigid short-grass proxy: continuous bumps and local grip tiles."""
from dataclasses import replace
import xml.etree.ElementTree as ET

import numpy as np

# One shared 25 mm lattice prevents height discontinuities between materials.
# Nine tiles span [-3, 3] m; the central metre contains the flat launch pad.
GRASS_CUTS = (0, 100, 140, 240)
GRASS_GRIPS = (0.55, 0.65, 0.75)
GRASS_HEIGHT = 0.008


def add_grass(root, contact):
    """Add tiled heightfield assets/geoms; return shared-edge elevation arrays."""
    coordinates = np.linspace(-3, 3, 241)
    x, y = np.meshgrid(coordinates, coordinates)
    heights = 0.5 + 0.3 * np.sin(17 * x) * np.cos(13 * y) + 0.2 * np.sin(9 * x + 11 * y)
    heights *= np.clip((np.hypot(x, y) - 0.3) / 0.2, 0, 1)
    world = root.find("worldbody")
    world.remove(world.find("geom[@name='floor']"))
    arrays = {}
    colors = ("0.23 0.36 0.13 1", "0.29 0.43 0.16 1", "0.36 0.50 0.20 1")
    for row, (y0, y1) in enumerate(zip(GRASS_CUTS[:-1], GRASS_CUTS[1:])):
        for col, (x0, x1) in enumerate(zip(GRASS_CUTS[:-1], GRASS_CUTS[1:])):
            name = f"grass_{row}_{col}"
            values = heights[y0:y1 + 1, x0:x1 + 1].copy()
            lo, hi = coordinates[[x0, y0]], coordinates[[x1, y1]]
            center, half = (lo + hi) / 2, (hi - lo) / 2
            ET.SubElement(root.find("asset"), "hfield", name=name,
                          nrow=str(values.shape[0]), ncol=str(values.shape[1]),
                          size=f"{half[0]} {half[1]} {GRASS_HEIGHT} 0.1")
            material = (col + 2 * row) % len(GRASS_GRIPS)
            geom = ET.SubElement(world, "geom", name="floor" if (row, col) == (1, 1) else name,
                                 type="hfield", hfield=name, pos=f"{center[0]} {center[1]} 0",
                                 contype="1", conaffinity="2", rgba=colors[material])
            replace(contact, sliding_friction=GRASS_GRIPS[material]).apply(geom)
            arrays[name] = values
    return arrays
