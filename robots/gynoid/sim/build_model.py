"""Build the balance MJCF from exported CAD frames and printed mass properties."""

from __future__ import annotations

import hashlib
import argparse
import json
from pathlib import Path
import xml.etree.ElementTree as ET

import mujoco
import numpy as np
import trimesh

HERE = Path(__file__).resolve().parent
ASSETS = HERE / "assets"
# CAD: +Y back. Simulation: +X forward, +Y left, +Z up.
CAD_TO_SIM = np.array([[0., -1, 0], [1, 0, 0], [0, 0, 1]])
SERVO_MASS = 0.018


def fmt(value):
    return " ".join(f"{x:.10g}" for x in np.asarray(value).reshape(-1))


def quaternion(rotation):
    # Exported SCAD matrices are rounded to six decimal places.
    u, _, vt = np.linalg.svd(rotation)
    result = np.empty(4)
    mujoco.mju_mat2Quat(result, np.ascontiguousarray(u @ vt).reshape(-1))
    return fmt(result)


def mass_properties(frame, masses):
    if frame["module"] == "xl330":
        size = np.array([20, 34, 23]) * 1e-3
        inertia = np.diag(SERVO_MASS / 12 * (sum(size * size) - size * size))
        return SERVO_MASS, np.array([0, -7.5, -14.5]) * 1e-3, inertia
    part = masses[frame["asset"]]
    return (part["mass_g"] * 1e-3, np.array(part["com_mm"]) * 1e-3,
            np.array(part["inertia_g_mm2"]) * 1e-9)


def aggregate_mass(items):
    mass = sum(item[0] for item in items)
    center = sum(m * c for m, c, _ in items) / mass
    inertia = sum(I + m * (np.eye(3) * np.dot(c - center, c - center)
                          - np.outer(c - center, c - center)) for m, c, I in items)
    eigenvalues = np.linalg.eigvalsh(inertia)
    if eigenvalues.min() <= 0 or 2 * eigenvalues.max() > eigenvalues.sum() + 1e-12:
        raise ValueError("Invalid aggregate inertia")
    return mass, center, inertia


def main(full=False):
    manifest = json.loads((ASSETS / "cad_manifest.json").read_text())
    source_hash = hashlib.sha256((HERE.parent / "gynoid.scad").read_bytes()).hexdigest()
    if manifest["cad_sha256"] != source_hash:
        raise ValueError("CAD changed. Run python -m sim.export_cad first.")
    frames = manifest["frames"]
    mass_document = json.loads((ASSETS / "print_mass.json").read_text())
    if mass_document["cad_sha256"] != source_hash:
        raise ValueError("Sliced masses are stale. Run python -m sim.export_cad without --skip-mass.")
    masses = {p["asset"]: p for p in mass_document["parts"]}
    meshes = {key: trimesh.load(ASSETS / f"{key}.stl", force="mesh") for key in manifest["parts"]}
    for i, frame in enumerate(frames):
        frame["index"] = i
        transform = np.array(frame["transform_mm"])
        frame["rotation"] = CAD_TO_SIM @ transform[:3, :3]
        frame["origin"] = CAD_TO_SIM @ transform[:3, 3] * 1e-3

    leg_servos = [f for f in frames if f["module"] == "xl330"
                  and any(p.startswith("abdomen@") for p in f["ancestry"])]
    if len(leg_servos) != 8:
        raise ValueError("Expected four joints per leg")
    waist = frames[0]
    joints = [("waist", waist, "pelvis", (-0.45, 0.45))]
    for branch in (leg_servos[:4], leg_servos[4:]):
        side = "left" if branch[0]["origin"][1] > 0 else "right"
        parent = "pelvis"
        for suffix, frame, limits in zip(
            ("hip_roll", "hip_pitch", "thigh_yaw", "knee"), branch,
            ((-0.45, 0.45), (-0.7, 0.7), (-0.45, 0.45), (-0.9, 0.9)), strict=True
        ):
            name = f"{side}_{suffix}"
            joints.append((name, frame, parent, limits))
            parent = name
    if full:
        for side, indices in (("right", [9, 11, 13, 16, 18]), ("left", [21, 23, 25, 28, 30])):
            parent = "waist"
            for suffix, index, limit in zip(
                ("shoulder_1", "shoulder_2", "elbow", "wrist", "thumb"), indices,
                (0.8, 0.8, 1.0, 0.8, 0.6), strict=True
            ):
                name = f"{side}_{suffix}"
                joints.append((name, frames[index], parent, (-limit, limit)))
                parent = name
        joints += [("right_neck", frames[3], "head", (-0.45, 0.45)),
                   ("left_neck", frames[5], "head", (-0.45, 0.45))]
    active = {frame["ancestry"][-1]: name for name, frame, _, _ in joints[1:]}
    origins = {"pelvis": waist["origin"], **{name: f["origin"] for name, f, _, _ in joints}}
    if full:
        origins.update(head=frames[2]["origin"], right_rod=frames[7]["origin"],
                       left_rod=frames[8]["origin"])
    groups = {name: [] for name in origins}
    for frame in frames:
        if any(p.startswith("chest@") for p in frame["ancestry"]):
            link = "waist"
        else:
            link = "pelvis"
        if full or link == "pelvis":
            # A motor case belongs to its upstream link, its horn attachments
            # belong to its downstream link. Abdomen attaches to the waist case.
            for ancestor in frame["ancestry"][:-1]:
                if ancestor in active:
                    link = active[ancestor]
        if full:
            overrides = {2: "head", 3: "head", 5: "head", 7: "right_rod", 8: "left_rod",
                         19: "right_wrist", 31: "left_wrist"}
            link = overrides.get(frame["index"], link)
        frame["link"] = link
        groups[link].append(frame)

    # Set both CAD tips just above the floor; retain the tiny CAD asymmetry.
    bottom = min((mesh.vertices @ f["rotation"].T * 1e-3 + f["origin"])[:, 2].min()
                 for f in frames if f["module"] == "leg" for mesh in [meshes[f["asset"]]])
    floor_offset = -bottom + 0.0003
    root = ET.Element("mujoco", model="gynoid_full" if full else "gynoid_balance")
    ET.SubElement(root, "compiler", angle="radian", meshdir="assets", inertiafromgeom="false")
    ET.SubElement(root, "option", timestep="0.002", gravity="0 0 -9.81",
                  integrator="implicitfast", cone="elliptic", iterations="50", jacobian="dense")
    visual = ET.SubElement(root, "visual")
    ET.SubElement(visual, "global", offwidth="960", offheight="720")
    ET.SubElement(visual, "headlight", diffuse="0.8 0.8 0.8", ambient="0.3 0.3 0.3")
    default = ET.SubElement(root, "default")
    # BAM initializes armature, viscous damping and dry friction at runtime.
    ET.SubElement(default, "joint", damping="0", armature="0", limited="true")
    ET.SubElement(default, "geom", friction="0.8 0.003 0.0001", condim="3",
                  solref="0.006 1", solimp="0.9 0.95 0.001")
    asset = ET.SubElement(root, "asset")
    ET.SubElement(asset, "texture", name="floor", type="2d", builtin="checker",
                  rgb1="0.15 0.18 0.22", rgb2="0.22 0.26 0.30", width="512", height="512")
    ET.SubElement(asset, "material", name="floor", texture="floor", texrepeat="12 12")
    used_meshes = set()
    world = ET.SubElement(root, "worldbody")
    ET.SubElement(world, "light", pos="0 -1 2", dir="0 0 -1", directional="true")
    ET.SubElement(world, "geom", name="floor", type="plane", size="3 3 0.1", material="floor")
    bodies = {"pelvis": ET.SubElement(world, "body", name="pelvis",
                                     pos=fmt(origins["pelvis"] + [0, 0, floor_offset]))}
    ET.SubElement(bodies["pelvis"], "freejoint", name="root")
    for name, frame, parent, limits in joints:
        if parent == "head" and "head" not in bodies:
            bodies["head"] = ET.SubElement(bodies["waist"], "body", name="head",
                                          pos=fmt(origins["head"] - origins["waist"]))
            for suffix, column in (("yaw", 2), ("pitch", 0)):
                ET.SubElement(bodies["head"], "joint", name=f"head_{suffix}",
                              axis=fmt(frames[2]["rotation"][:, column]), range="-0.6 0.6",
                              damping="0.00001")
        bodies[name] = ET.SubElement(bodies[parent], "body", name=name,
                                    pos=fmt(origins[name] - origins[parent]))
        axis = np.linalg.det(frame["rotation"]) * frame["rotation"][:, 2]
        axis /= np.linalg.norm(axis)
        ET.SubElement(bodies[name], "joint", name=name, axis=fmt(axis), range=fmt(limits))
    if full:
        equality = ET.SubElement(root, "equality")
        for side, index in (("right", 7), ("left", 8)):
            link = f"{side}_rod"
            bodies[link] = ET.SubElement(bodies[f"{side}_neck"], "body", name=link,
                                        pos=fmt(origins[link] - origins[f"{side}_neck"]))
            ET.SubElement(bodies[link], "joint", name=link, type="ball", limited="false",
                          damping="0.000001")
            end = frames[index]["rotation"] @ [-0.04325, 0, 0]
            ET.SubElement(bodies[link], "site", name=f"{side}_rod_end", pos=fmt(end), size="0.001")
            ET.SubElement(bodies["waist"], "site", name=f"{side}_stem", size="0.001",
                          pos=fmt(origins[link] + end - origins["waist"]))
            # Rigid rod connections need tighter closure than ordinary contacts.
            # Default impedance allowed about 1 mm of unintended neck play.
            ET.SubElement(equality, "connect", name=f"{side}_neck_closure",
                          site1=f"{side}_rod_end", site2=f"{side}_stem", solref="0.004 1",
                          solimp="0.9999 0.9999 0.001")
    report = dict(cad_sha256=source_hash, units="m, kg, s, rad", floor_offset_m=floor_offset,
                  servo_count=21, actuated_joints=[], links={}, parts=[])
    for link, instances in groups.items():
        properties = []
        for frame in instances:
            mass, center, inertia = mass_properties(frame, masses)
            rotation = frame["rotation"]
            position = frame["origin"] - origins[link]
            properties.append((mass, rotation @ center + position, rotation @ inertia @ rotation.T))
            key = frame["asset"]
            mesh = meshes[key]
            display_rotation = rotation.copy()
            if np.linalg.det(rotation) < 0:
                key += "_mirror"
                display_rotation = rotation @ np.diag([-1., 1, 1])
                if key not in used_meshes:
                    reflected = mesh.copy()
                    reflected.apply_transform(np.diag([-1., 1, 1, 1]))
                    reflected.export(ASSETS / f"{key}.stl")
            if key not in used_meshes:
                ET.SubElement(asset, "mesh", name=key, file=f"{key}.stl", scale="0.001 0.001 0.001")
                used_meshes.add(key)
            color = ("0.18 0.18 0.20 1" if frame["module"] == "xl330" else
                     "0.8 0.8 0.82 1" if frame["module"] in ("head", "hand", "thumb") else
                     "0.95 0.42 0.18 1")
            geom_name = f"part_{frame['index']}_{frame['module']}"
            ET.SubElement(bodies[link], "geom", name=geom_name, type="mesh", mesh=key,
                          pos=fmt(position), quat=quaternion(display_rotation), rgba=color,
                          contype="0", conaffinity="0", group="1")
            # Simple, inexpensive contacts. Bracket cavities are deliberately
            # not replaced by convex hulls that would collide with their servos.
            collision = dict(name=geom_name + "_collision", group="3", rgba="0.2 0.7 0.9 0.25")
            module = frame["module"]
            if module == "xl330":
                ET.SubElement(bodies[link], "geom", type="box", size="0.010 0.017 0.0115",
                              pos=fmt(position + rotation @ np.array([0, -0.0075, -0.0145])),
                              quat=quaternion(display_rotation), **collision)
            elif module == "leg":
                # Actual convex tapered leg, including the 5 mm rounded tip.
                ET.SubElement(bodies[link], "geom", type="mesh", mesh=key,
                              pos=fmt(position), quat=quaternion(display_rotation), **collision)
                ET.SubElement(bodies[link], "site", name=link.split("_")[0] + "_foot",
                              pos=fmt(position + rotation @ [0, 0, -0.1675]), size="0.0025")
            elif module in ("head", "chest", "abdomen", "hand", "thumb"):
                center = mesh.bounds.mean(axis=0) * 1e-3
                size = (mesh.bounds[1] - mesh.bounds[0]) * 0.5e-3
                ET.SubElement(bodies[link], "geom", type="ellipsoid" if module == "head" else "box",
                              size=fmt(size), pos=fmt(position + rotation @ center),
                              quat=quaternion(display_rotation), **collision)
            report["parts"].append(dict(index=frame["index"], module=module, asset=frame["asset"],
                                        link=link, mass_kg=mass, origin_m=frame["origin"].tolist()))
        mass, center, inertia = aggregate_mass(properties)
        ET.SubElement(bodies[link], "inertial", mass=fmt([mass]), pos=fmt(center),
                      fullinertia=fmt([*inertia.diagonal(), inertia[0, 1], inertia[0, 2], inertia[1, 2]]))
        report["links"][link] = dict(mass_kg=mass, com_m=center.tolist(), inertia_kg_m2=inertia.tolist())
    actuator = ET.SubElement(root, "actuator")
    for name, frame, parent, limits in joints:
        ET.SubElement(actuator, "motor", name=name, joint=name, gear="1")
        report["actuated_joints"].append(dict(name=name, parent=parent, cad_part_index=frame["index"],
                                                cad_drive_deg=frame["parameters"]["drive"],
                                                range_rad=list(limits)))
    report["total_mass_kg"] = sum(item["mass_kg"] for item in report["links"].values())
    report["assumptions"] = [
        ("All 21 servos active; two-axis head follows the CAD fixed-roll neck assumption."
         if full else "Arms, thumbs and parallel neck linkage fixed in CAD pose; nine actuated joints."),
        "XL330-M288 at 5 V assumed; 18 g and uniform case inertia per servo.",
        "BAM XL330 M6 supplies motor electrical dynamics, armature and friction at runtime.",
        "Default 5 V, firmware Kp 200 and 1.75 A current limiter; no thermal or gearbox backlash model.",
        "Joint travel and ground contact friction remain simulation assumptions.",
        "Printed mass/inertia from Bambu PETG HF and saved slicer settings, including neck rods.",
        "No battery/electronics/wiring/extra fastener mass: these are absent from the CAD assembly.",
        "Collision proxies for cases/torso/hands, convex CAD legs; small brackets are visual only.",
    ]
    if full:
        report["assumptions"].append(
            "Neck rods use near-rigid endpoint constraints; elastic bending and joint clearance are not modeled.")
    ET.indent(root, space="  ")
    filename = "gynoid_full.xml" if full else "gynoid.xml"
    ET.ElementTree(root).write(HERE / filename, encoding="unicode", xml_declaration=True)
    # Compilation validates MJCF, inertias and mesh assets before publishing report.
    model = mujoco.MjModel.from_xml_path(str(HERE / filename))
    if model.nu != (21 if full else 9) or model.nq != (38 if full else 16):
        raise ValueError("Unexpected generalized coordinates")
    (HERE / ("full_model_report.json" if full else "model_report.json")).write_text(json.dumps(report, indent=2) + "\n")
    print(f"Built {model.nu} actuators, {model.nbody - 1} links, {report['total_mass_kg']:.4f} kg")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--full", action="store_true", help="Articulate arms, thumbs and parallel neck")
    main(parser.parse_args().full)
