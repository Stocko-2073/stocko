"""Optional collision-only wheel lugs and deterministic benchmark terrain."""
from pathlib import Path
from dataclasses import dataclass
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


# Initial estimates, not a hardware-calibrated material model. A flat plane
# represents relatively smooth concrete; dim6 makes low rolling drag active.
SURFACE_PRESETS = {
    "concrete": TerrainContact(sliding_friction=0.8, torsional_friction=0.002,
                               rolling_friction=0.0001, condim=6,
                               time_constant=0.01, damping_ratio=1.0),
}


def load_model(path: Path, wheel_contact="lugs", terrain="flat", timestep=0.002,
               terrain_contact=None, obstacles=(), surface=None):
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
    if terrain == "bumps":
        ET.SubElement(root.find("asset"), "hfield", name="bumps", nrow="129", ncol="129",
                      size="3 3 0.012 0.1")
        floor = root.find(".//geom[@name='floor']")
        floor.set("type", "hfield")
        floor.set("hfield", "bumps")
        floor.attrib.pop("size")
    model = mujoco.MjModel.from_xml_string(ET.tostring(root, encoding="unicode"))
    if terrain == "bumps":
        x, y = np.meshgrid(np.linspace(-3, 3, 129), np.linspace(-3, 3, 129))
        heights = (0.5 + 0.3 * np.sin(18 * x) * np.cos(15 * y)
                   + 0.2 * np.sin(9 * x + 13 * y))
        # Flat launch pad avoids an initial terrain penetration for either model.
        heights *= np.clip((np.hypot(x, y) - 0.3) / 0.2, 0, 1)
        model.hfield_data[:] = heights.ravel()
    return model
