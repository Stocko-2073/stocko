"""Optional collision-only wheel lugs and deterministic benchmark terrain."""
from pathlib import Path
import xml.etree.ElementTree as ET

import mujoco
import numpy as np


def load_model(path: Path, wheel_contact="lugs", terrain="flat", timestep=0.002):
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
