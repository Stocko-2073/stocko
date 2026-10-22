"""Optional collision-only wheel lugs and deterministic benchmark terrain."""
from pathlib import Path
from dataclasses import dataclass, replace
import xml.etree.ElementTree as ET

import mujoco
import numpy as np


@dataclass(frozen=True)
class TerrainContact:
    """Estimated surface contact settings; rolling friction requires condim=6.

    Sliding friction is dimensionless; torsional and rolling friction have
    units of metres. Compliance uses MuJoCo's positive-format solref.
    """

    sliding_friction: float = 0.8
    torsional_friction: float = 0.002
    rolling_friction: float = 0.0001
    condim: int = 4
    time_constant: float = 0.01
    damping_ratio: float = 1.0

    def __post_init__(self):
        friction = (self.sliding_friction, self.torsional_friction, self.rolling_friction)
        if not np.isfinite(friction).all() or min(friction) < 0:
            raise ValueError("terrain friction coefficients must be finite and nonnegative")
        if self.condim not in (3, 4, 6):
            raise ValueError("terrain condim must be 3, 4, or 6")
        compliance = (self.time_constant, self.damping_ratio)
        if not np.isfinite(compliance).all() or min(compliance) <= 0:
            raise ValueError("terrain time_constant and damping_ratio must be finite and positive")

    def apply(self, geom):
        # Robot collision geoms have priority 0. Surface priority prevents
        # max-friction mixing from erasing slippery terrain, and selects the
        # surface's condim and compliance instead of averaging with the wheel.
        geom.set("priority", "1")
        geom.set("friction", f"{self.sliding_friction} {self.torsional_friction} {self.rolling_friction}")
        geom.set("condim", str(int(self.condim)))
        geom.set("solref", f"{self.time_constant} {self.damping_ratio}")
        geom.set("solimp", "0.9 0.95 0.001 0.5 2")


@dataclass(frozen=True)
class TerrainObstacle:
    """Static collision proxy at a world-frame centre (metres), with yaw in radians.

    rock: ellipsoid radii (x, y, z); root: (radius, half cylinder length),
    along local Y; seam/edge: box half-sizes (x, y, z). Positions are absolute,
    so set Z to account for terrain elevation and any intended embedding.
    """

    kind: str
    position: tuple[float, float, float]
    size: tuple[float, ...]
    yaw: float = 0.0
    contact: TerrainContact | None = None

    def __post_init__(self):
        if self.kind not in ("rock", "root", "seam", "edge"):
            raise ValueError("obstacle kind must be rock, root, seam, or edge")
        if np.shape(self.position) != (3,) or not np.isfinite(self.position).all():
            raise ValueError("obstacle position must contain three finite coordinates")
        count = 2 if self.kind == "root" else 3
        if np.shape(self.size) != (count,) or not np.isfinite(self.size).all() or min(self.size) <= 0:
            raise ValueError(f"{self.kind} size must contain {count} finite positive dimensions")
        if not np.isfinite(self.yaw):
            raise ValueError("obstacle yaw must be finite")
        if self.contact is not None and not isinstance(self.contact, TerrainContact):
            raise TypeError("obstacle contact must be a TerrainContact instance")

    def add_to(self, world, name, default_contact):
        shape = {"rock": "ellipsoid", "root": "capsule", "seam": "box", "edge": "box"}[self.kind]
        colors = {"rock": "0.45 0.43 0.4 1", "root": "0.35 0.22 0.12 1",
                  "seam": "0.6 0.58 0.52 1", "edge": "0.5 0.5 0.48 1"}
        geom = ET.SubElement(world, "geom", name=name, type=shape, contype="1",
                             conaffinity="2", group="0", rgba=colors[self.kind])
        if self.kind == "root":
            offset = self.size[1] * np.array([-np.sin(self.yaw), np.cos(self.yaw), 0])
            endpoints = np.r_[np.asarray(self.position) - offset, np.asarray(self.position) + offset]
            geom.set("fromto", " ".join(map(str, endpoints)))
            geom.set("size", str(self.size[0]))
        else:
            geom.set("pos", " ".join(map(str, self.position)))
            geom.set("size", " ".join(map(str, self.size)))
            geom.set("euler", f"0 0 {self.yaw}")
        (self.contact or default_contact).apply(geom)


# Initial estimates, not hardware-calibrated material models.
SURFACE_PRESETS = {
    "short_grass": TerrainContact(sliding_friction=0.65, rolling_friction=0.002,
                                  condim=6, time_constant=0.02, damping_ratio=1.0),
    "concrete": TerrainContact(sliding_friction=0.8, torsional_friction=0.002,
                               rolling_friction=0.0001, condim=6,
                               time_constant=0.01, damping_ratio=1.0),
    "rough_concrete": TerrainContact(sliding_friction=0.8, torsional_friction=0.002,
                                     rolling_friction=0.0001, condim=6,
                                     time_constant=0.01, damping_ratio=1.0),
}
SURFACE_TERRAINS = {"concrete": "flat", "rough_concrete": "rough_concrete",
                    "short_grass": "short_grass"}
SURFACE_OBSTACLES = {
    "rough_concrete": (
        TerrainObstacle("seam", (0.45, 0, 0.002), (0.008, 0.3, 0.002)),
        TerrainObstacle("edge", (1.0, 0.4, 0.004), (0.2, 0.06, 0.004)),
        TerrainObstacle("seam", (-0.2, 0.75, 0.002), (0.008, 0.25, 0.002), yaw=np.pi / 4),
    ),
}


PATCH_EXTENT = 8.0  # Beyond the environment's 6 m failure radius.


@dataclass(frozen=True)
class TerrainPatch:
    """Axis-aligned, flush rectangle; centre and half-sizes in world XY metres.

    Only sliding grip changes. All other settings come from the ground.
    Patches must fit inside +/-8 m, have disjoint interiors, and use flat terrain.
    """

    center: tuple[float, float]
    half_size: tuple[float, float]
    sliding_friction: float = 0.08

    def __post_init__(self):
        if np.shape(self.center) != (2,) or not np.isfinite(self.center).all():
            raise ValueError("patch center must contain two finite coordinates")
        if (np.shape(self.half_size) != (2,) or not np.isfinite(self.half_size).all()
                or min(self.half_size) <= 0):
            raise ValueError("patch half_size must contain two finite positive dimensions")
        if not np.isfinite(self.sliding_friction) or self.sliding_friction < 0:
            raise ValueError("patch sliding_friction must be finite and nonnegative")
        if np.any(np.abs(self.center) + np.asarray(self.half_size) >= PATCH_EXTENT):
            raise ValueError("patch must lie strictly inside the +/-8 m ground boundary")

    @property
    def bounds(self):
        x, y = self.center
        hx, hy = self.half_size
        return x - hx, x + hx, y - hy, y + hy


@dataclass(frozen=True)
class TerrainRegion:
    """Flush, axis-aligned rectangle with a complete contact material.

    Centre and half-sizes are world XY metres. Regions and grip-only patches
    may share edges but cannot overlap. Only flat terrain is supported.
    """

    center: tuple[float, float]
    half_size: tuple[float, float]
    contact: TerrainContact

    def __post_init__(self):
        # Use the same footprint validation as grip-only patches.
        TerrainPatch(self.center, self.half_size)
        if not isinstance(self.contact, TerrainContact):
            raise TypeError("region contact must be a TerrainContact instance")

    @property
    def bounds(self):
        x, y = self.center
        hx, hy = self.half_size
        return x - hx, x + hx, y - hy, y + hy


def _partition_ground(root, patches, contact, regions):
    # Tile the ground with disjoint boxes whose top faces are exactly z=0.
    # Keeping an infinite colliding plane beneath a patch would also apply dry
    # friction there; raising patches to hide the plane would create steps.
    for patch in patches:
        if not isinstance(patch, TerrainPatch):
            raise TypeError("patches must contain TerrainPatch instances")
    for region in regions:
        if not isinstance(region, TerrainRegion):
            raise TypeError("regions must contain TerrainRegion instances")
    rectangles = patches + regions
    dry = [(-PATCH_EXTENT, PATCH_EXTENT, -PATCH_EXTENT, PATCH_EXTENT)]
    for i, patch in enumerate(rectangles):
        x0, x1, y0, y1 = patch.bounds
        for previous in rectangles[:i]:
            a, b, c, d = previous.bounds
            if max(a, x0) < min(b, x1) and max(c, y0) < min(d, y1):
                raise ValueError("patch and region interiors must not overlap")
        remaining = []
        for a, b, c, d in dry:
            lo, hi, bottom, top = max(a, x0), min(b, x1), max(c, y0), min(d, y1)
            if lo >= hi or bottom >= top:
                remaining.append((a, b, c, d))
                continue
            remaining.extend(rect for rect in (
                (a, lo, c, d), (hi, b, c, d),
                (lo, hi, c, bottom), (lo, hi, top, d),
            ) if rect[0] < rect[1] and rect[2] < rect[3])
        dry = remaining
    world = root.find("worldbody")
    floor = world.find("geom[@name='floor']")
    template = dict(floor.attrib)
    world.remove(floor)
    tiles = [("floor" if i == 0 else f"terrain_ground_{i}", rect, contact, False)
               for i, rect in enumerate(dry)]
    tiles += [(f"terrain_patch_{i}", patch.bounds,
                 replace(contact, sliding_friction=patch.sliding_friction), True)
                for i, patch in enumerate(patches)]
    tiles += [(f"terrain_region_{i}", region.bounds, region.contact, True)
              for i, region in enumerate(regions)]
    for name, (x0, x1, y0, y1), settings, is_patch in tiles:
        geom = ET.SubElement(world, "geom", template)
        geom.set("name", name)
        geom.set("type", "box")
        geom.set("pos", f"{(x0 + x1) / 2} {(y0 + y1) / 2} -0.1")
        geom.set("size", f"{(x1 - x0) / 2} {(y1 - y0) / 2} 0.1")
        if is_patch:
            geom.attrib.pop("material", None)
            geom.set("rgba", "0.48 0.37 0.22 1" if name.startswith("terrain_region_")
                     else "0.12 0.4 0.58 1")
        settings.apply(geom)


def load_model(path: Path, wheel_contact="lugs", terrain="flat", timestep=0.002,
               terrain_contact=None, obstacles=(), surface=None, patches=(), regions=()):
    patches = tuple(patches)
    regions = tuple(regions)
    if surface is not None:
        if surface not in SURFACE_PRESETS:
            raise ValueError(f"unknown surface preset: {surface!r}")
        if terrain != "flat" or terrain_contact is not None:
            raise ValueError("surface presets require terrain='flat' and no terrain_contact override")
        terrain_contact = SURFACE_PRESETS[surface]
    if wheel_contact not in ("smooth", "lugs"):
        raise ValueError("wheel_contact must be smooth or lugs")
    if terrain not in ("flat", "bumps"):
        raise ValueError("terrain must be flat or bumps")
    if surface is not None:
        terrain = SURFACE_TERRAINS[surface]
    if (patches or regions) and terrain != "flat":
        raise ValueError("local grip patches and material regions require flat terrain")
    if (not np.isfinite(timestep) or not 0 < timestep <= 0.02
            or not np.isclose(0.02 / timestep, round(0.02 / timestep))):
        raise ValueError("timestep must be positive and divide the 20 ms control period")
    root = ET.parse(path).getroot()
    root.find("compiler").set("meshdir", str(path.parent.resolve()))
    root.find("option").set("timestep", str(timestep))
    contact = TerrainContact() if terrain_contact is None else terrain_contact
    if not isinstance(contact, TerrainContact):
        raise TypeError("terrain_contact must be a TerrainContact instance")
    contact.apply(root.find(".//geom[@name='floor']"))
    if patches or regions:
        _partition_ground(root, patches, contact, regions)
    for index, obstacle in enumerate(SURFACE_OBSTACLES.get(surface, ())):
        obstacle.add_to(root.find("worldbody"), f"surface_obstacle_{index}", contact)
    for index, obstacle in enumerate(obstacles):
        if not isinstance(obstacle, TerrainObstacle):
            raise TypeError("obstacles must contain TerrainObstacle instances")
        obstacle.add_to(root.find("worldbody"), f"terrain_obstacle_{index}", contact)
    if wheel_contact == "lugs":
        for side in ("left", "right"):
            wheel = root.find(f".//body[@name='{side}_wheel']")
            tire = wheel.find(f"geom[@name='{side}_tire']")
            # CAD hub tread: radius 102.5 mm, width 14 mm. Keep the original
            # wheel mass/inertia; added collision geoms contribute no mass.
            tire.set("size", "0.1025 0.007")
            mirror = -1 if side == "left" else 1
            for row, (axial, height, phase) in enumerate(((-0.0065, 0.012, np.pi / 20),
                                                       (0.0065, 0.011, 0))):
                for index in range(20):
                    angle = phase + index * np.pi / 10
                    radius = 0.1075 - height / 2
                    pos = [radius * np.sin(angle), mirror * axial, radius * np.cos(angle)]
                    # Local axes: tangential, axial, radial. Unchamfered bounding
                    # boxes of the CAD's 17 x 7 x 12/11 mm staggered lugs.
                    quat = [np.cos(angle / 2), 0, np.sin(angle / 2), 0]
                    ET.SubElement(wheel, "geom", name=f"{side}_lug_{row}_{index}",
                                  type="box", size=f"0.0035 0.0085 {height / 2}",
                                  pos=" ".join(map(str, pos)), quat=" ".join(map(str, quat)),
                                  mass="0", group="3", rgba="0.9 0.45 0.15 0")
    if terrain in ("bumps", "rough_concrete"):
        resolution = 257 if terrain == "rough_concrete" else 129
        amplitude = 0.004 if terrain == "rough_concrete" else 0.012
        ET.SubElement(root.find("asset"), "hfield", name=terrain,
                      nrow=str(resolution), ncol=str(resolution), size=f"3 3 {amplitude} 0.1")
        floor = root.find(".//geom[@name='floor']")
        floor.set("type", "hfield")
        floor.set("hfield", terrain)
        floor.attrib.pop("size")
    grass_arrays = {}
    if terrain == "short_grass":
        from ubot_sim.grass import add_grass
        grass_arrays = add_grass(root, contact)
    model = mujoco.MjModel.from_xml_string(ET.tostring(root, encoding="unicode"))
    for name, values in grass_arrays.items():
        offset = model.hfield_adr[model.hfield(name).id]
        model.hfield_data[offset:offset + values.size] = values.ravel()
    if terrain in ("bumps", "rough_concrete"):
        x, y = np.meshgrid(np.linspace(-3, 3, resolution), np.linspace(-3, 3, resolution))
        if terrain == "rough_concrete":
            # About 14-21 cm wavelengths sampled at 23 mm; fixed layout for
            # repeatable runs. Geometry supplies roughness, not extra drag.
            heights = (0.5 + 0.3 * np.sin(45 * x) * np.cos(38 * y)
                       + 0.2 * np.sin(30 * x + 25 * y))
        else:
            heights = (0.5 + 0.3 * np.sin(18 * x) * np.cos(15 * y)
                       + 0.2 * np.sin(9 * x + 13 * y))
        # Flat launch pad avoids an initial terrain penetration for either model.
        heights *= np.clip((np.hypot(x, y) - 0.3) / 0.2, 0, 1)
        model.hfield_data[:] = heights.ravel()
    return model
