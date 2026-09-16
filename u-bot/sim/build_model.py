"""Build MJCF from documented CAD dimensions and explicit dynamics estimates."""
from pathlib import Path
import xml.etree.ElementTree as ET

ASSETS = Path(__file__).resolve().parent / "ubot_sim" / "assets"
# User measurements, 2026-09-15: postage scale, other three wheels supported
# at the same height. These are support loads, NOT individual wheel masses.
SUPPORT_LOADS_KG = {"right_caster": 0.756, "left_caster": 0.709,
                    "right_drive": 1.218, "left_drive": 1.360}
MEASURED_TOTAL_KG = sum(SUPPORT_LOADS_KG.values())
BASE_MASS_KG = MEASURED_TOTAL_KG - (2 * 0.25 + 2 * 0.08 + 4 * 0.03)
# User confirmed caster wheels behind the stems while weighing (swivel pi).
# Use each twin-roller pair's midpoint as its resultant support location.
SUPPORT_POSITIONS_XY = {"right_caster": (-0.16125 - 0.019, -0.10475),
                        "left_caster": (-0.16125 - 0.019, 0.10475),
                        "right_drive": (0.0002, -0.15135),
                        "left_drive": (0.0002, 0.15135)}
ROBOT_COM_XY = tuple(sum(SUPPORT_LOADS_KG[k] * xy[i]
                         for k, xy in SUPPORT_POSITIONS_XY.items()) / MEASURED_TOTAL_KG
                     for i in range(2))
# Subtract estimated moving-part moments in the measured, rearward-caster pose so the
# whole robot, rather than just the base body, matches the inferred COM.
MOVING_PART_MOMENT_XY = (2 * 0.25 * 0.0002 + 2 * 0.08 * (-0.16125 - 0.012)
                         + 4 * 0.03 * (-0.16125 - 0.019), 0.0)
BASE_COM_XY = tuple((MEASURED_TOTAL_KG * ROBOT_COM_XY[i] - MOVING_PART_MOMENT_XY[i])
                   / BASE_MASS_KG for i in range(2))


def add(parent, tag, **attrs):
    return ET.SubElement(parent, tag, {k: str(v) for k, v in attrs.items()})


def main():
    root = ET.Element("mujoco", model="U-bot")
    add(root, "compiler", angle="radian", meshdir=".")
    add(root, "option", timestep="0.002", integrator="implicitfast", cone="elliptic", iterations="50")
    default = add(root, "default")
    add(default, "joint", damping="0.002", armature="0.00005")
    add(default, "geom", contype="2", conaffinity="1", friction="0.8 0.002 0.0001", condim="4", solref="0.01 1")
    visual = add(default, "default", **{"class": "visual"})
    add(visual, "geom", type="mesh", contype="0", conaffinity="0", group="2", density="0")
    asset = add(root, "asset")
    for name in ("chassis", "wheel_left", "wheel_right", "caster_fork", "caster_roller"):
        add(asset, "mesh", name=name, file=f"{name}.stl", scale="0.001 0.001 0.001")
    add(asset, "texture", name="grid", type="2d", builtin="checker", rgb1="0.22 0.28 0.22", rgb2="0.3 0.36 0.3", width="512", height="512")
    add(asset, "material", name="ground", texture="grid", texrepeat="12 12", reflectance="0.05")
    world = add(root, "worldbody")
    add(world, "light", pos="0 -2 4", dir="0 0 -1", directional="true")
    add(world, "geom", name="floor", type="plane", size="0 0 0.1", material="ground", contype="1", conaffinity="2")
    goal = add(world, "body", name="goal", mocap="true", pos="1 0 0.005")
    add(goal, "geom", type="cylinder", size="0.12 0.004", rgba="0.2 0.9 0.3 0.5", contype="0", conaffinity="0")
    robot = add(world, "body", name="base", pos="0 0 0.1085")
    add(robot, "freejoint", name="root")
    # Keep moving-part estimates; assign the measured total's remainder to the
    # base. Inertia about the revised COM remains an estimate; static support
    # loads identify neither COM height nor rotational inertia.
    base_inertia = " ".join(f"{i * BASE_MASS_KG / 4.4:.10g}" for i in (0.035, 0.045, 0.07))
    add(robot, "inertial", pos=f"{BASE_COM_XY[0]} {BASE_COM_XY[1]} 0", mass=BASE_MASS_KG, diaginertia=base_inertia)
    add(robot, "geom", mesh="chassis", rgba="0.78 0.8 0.82 1", **{"class": "visual"})
    for name, pos, size in [
        ("rear", "-0.149 0 0", "0.07 0.125 0.035"),
        ("left_housing", "-0.002 0.1005 0", "0.077 0.0275 0.035"),
        ("right_housing", "-0.002 -0.1005 0", "0.077 0.0275 0.035"),
    ]:
        add(robot, "geom", name=name, type="box", pos=pos, size=size, group="3", rgba="0.5 0.5 0.5 0")
    add(robot, "geom", name="battery", type="box", pos="-0.1322 0 -0.0005", size="0.047 0.075 0.0325", rgba="0.15 0.15 0.15 1", contype="0", conaffinity="0", mass="0")
    add(robot, "site", name="imu", size="0.004", pos="0 0 0.03")
    add(robot, "camera", name="follow", mode="trackcom", pos="0.8 -1 0.65", xyaxes="0.78 0.62 0 -0.3 0.38 0.87")
    wheel_quat = "0.707106781 -0.707106781 0 0"
    for side, sign in (("left", 1), ("right", -1)):
        wheel = add(robot, "body", name=f"{side}_wheel", pos=f"0.0002 {sign * 0.15135} 0")
        add(wheel, "joint", name=f"{side}_drive", axis="0 1 0")
        add(wheel, "inertial", pos="0 0 0", mass="0.25", diaginertia="0.00074 0.00144 0.00074")
        add(wheel, "geom", mesh=f"wheel_{side}", rgba="0.18 0.19 0.2 1", **{"class": "visual"})
        add(wheel, "geom", name=f"{side}_tire", type="cylinder", size="0.1075 0.012", quat=wheel_quat, group="3", rgba="0.2 0.2 0.2 0")
        caster = add(robot, "body", name=f"{side}_caster", pos=f"-0.16125 {sign * 0.10475} -0.0775")
        add(caster, "joint", name=f"{side}_swivel", axis="0 0 1", damping="0.001")
        add(caster, "inertial", pos="0.012 0 0.03", mass="0.08", diaginertia="0.00006 0.00007 0.00002")
        add(caster, "geom", mesh="caster_fork", rgba="0.5 0.5 0.52 1", **{"class": "visual"})
        for roller, offset in (("a", -0.01585), ("b", 0.01585)):
            body = add(caster, "body", name=f"{side}_roller_{roller}", pos=f"0.019 {offset} 0")
            add(body, "joint", name=f"{side}_roll_{roller}", axis="0 1 0", damping="0.0001")
            add(body, "inertial", pos="0 0 0", mass="0.03", diaginertia="0.000008 0.0000135 0.000008")
            add(body, "geom", mesh="caster_roller", quat="1 0 0 0" if offset > 0 else "0 0 0 1", rgba="0.23 0.23 0.24 1", **{"class": "visual"})
            add(body, "geom", name=f"{side}_contact_{roller}", type="ellipsoid", size="0.03 0.00915 0.03", group="3", rgba="0.2 0.2 0.2 0")
    actuator = add(root, "actuator")
    for side in ("left", "right"):
        add(actuator, "velocity", name=f"{side}_motor", joint=f"{side}_drive", kv="0.35", ctrlrange="-6.283185307 6.283185307", forcerange="-0.8 0.8")
    sensor = add(root, "sensor")
    for joint in ("left_drive", "right_drive", "left_swivel", "right_swivel"):
        add(sensor, "jointpos", name=f"{joint}_angle", joint=joint)
        add(sensor, "jointvel", name=f"{joint}_speed", joint=joint)
    add(sensor, "gyro", name="gyro", site="imu")
    add(sensor, "accelerometer", name="accelerometer", site="imu")
    ET.indent(root)
    ET.ElementTree(root).write(ASSETS / "robot.xml", encoding="unicode", xml_declaration=True)


if __name__ == "__main__":
    main()
