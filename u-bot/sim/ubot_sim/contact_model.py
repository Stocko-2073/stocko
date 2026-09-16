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


def load_model(path: Path, wheel_contact="lugs", terrain="flat", timestep=0.002,
               terrain_contact=None):
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
