"""Build phone_girl.xml from the CAD manifest written by phone_girl.cad.

Simulation frame: +X forward, +Y left, +Z up; m, kg, s, rad. The model is built
in the CAD's default pose, standing on its stilt tips: that is qpos0, so every
body frame is world-aligned there and sits on its joint's shaft. Each joint's
ref is its default servo angle, so qpos is the servo shaft angle. Inertials are
summed from sliced and bought parts; visual meshes carry no mass. Collision uses
cheap primitives: exact servo and phone boxes, oriented boxes for printed parts,
and a sphere for each stilt tip.

The phone's IMU site uses CoreMotion's device frame (x right and y up the
screen, z out of it), and its cameras use MuJoCo's camera frame (looking down
-z, image up +y), in portrait.
"""

from __future__ import annotations

import argparse
import json

import mujoco
import numpy as np
import trimesh

from phone_girl import ASSETS, CAD, CAD_TO_SIM, MJCF

ROOT = "torso"
# Collision groups. A geom collides with the ground and every group but its own,
# so limbs hit each other and the trunk but not themselves.
GROUND, TRUNK = 1, 2
LIMB_BITS = {"left_shoulder": 4, "right_shoulder": 8, "left_hip": 16, "right_hip": 32}
ALL_BODY_BITS = 2 | 4 | 8 | 16 | 32
FOOT_RADIUS = 0.0025  # leg()'s foot=5 rounded end
# Provisional soft travel either side of the CAD default pose, in degrees. These
# are not measured: check them against the hardware before trusting them.
TRAVEL_DEG = {"waist": 45, "shoulder_pitch": 150, "shoulder_yaw": 90, "elbow": 110, "wrist": 150,
              "hip_roll": 35, "hip_pitch": 80, "thigh_yaw": 60, "knee": 110}
# Where the IMU sits in the phone's geometry frame, mm. Not published by Apple;
# this guesses the logic board's upper middle and is randomized in training.
IMU_IN_PHONE_MM = [0.0, 40.0, 0.0]
# Cameras in the phone's geometry frame (origin at the body centre, screen +Z,
# top +Y): position mm, which way it looks, and 35 mm-equivalent focal length.
# Rear positions are the CAD module's lens centres; the TrueDepth camera is the
# right-hand end of the Dynamic Island. Focal lengths are Apple's published ones,
# except the front camera's, which is an estimate.
CAMERAS = {
    "front": ([7.33, 149.61 / 2 - 7.71, 8.25 / 2], +1, 23.0),
    "rear_main": ([71.45 / 2 - 14.17, 149.61 / 2 - 14.17, -8.25 / 2 - 2.23], -1, 24.0),
    "rear_ultrawide": ([71.45 / 2 - 14.17, 149.61 / 2 - 33.41, -8.25 / 2 - 2.23], -1, 13.0),
    "rear_tele": ([71.45 / 2 - 32.16, 149.61 / 2 - 23.79, -8.25 / 2 - 2.23], -1, 120.0),
}
CAMERA_RESOLUTION = (96, 128)  # portrait width, height; tasks choose their own


def quat(rotation: np.ndarray) -> np.ndarray:
    u, _, vt = np.linalg.svd(rotation)  # SCAD matrices are rounded; re-orthonormalize
    out = np.empty(4)
    mujoco.mju_mat2Quat(out, np.ascontiguousarray(u @ vt).reshape(-1))
    return out


def placed(part: dict) -> tuple[np.ndarray, np.ndarray]:
    """A part's geometry frame in the simulation world at the reference pose, in m."""
    transform = np.array(part["transform"])
    return CAD_TO_SIM @ transform[:3, :3], CAD_TO_SIM @ transform[:3, 3] * 1e-3


def proper(rotation: np.ndarray) -> tuple[np.ndarray, bool]:
    """Split off a mirror: a mirrored part uses an x-flipped mesh and a proper rotation."""
    if np.linalg.det(rotation) > 0:
        return rotation, False
    return rotation @ np.diag([-1.0, 1, 1]), True


def summed_inertia(items: list) -> tuple[float, np.ndarray, np.ndarray]:
    total = sum(m for m, _, _ in items)
    centre = sum(m * c for m, c, _ in items) / total
    inertia = sum(i + m * (np.eye(3) * np.dot(c - centre, c - centre) - np.outer(c - centre, c - centre))
                  for m, c, i in items)
    eigen = np.linalg.eigvalsh(inertia)
    if eigen.min() <= 0 or 2 * eigen.max() > eigen.sum() + 1e-12:
        raise ValueError("Link inertia is not physical")
    return total, centre, inertia


def collision_shapes(module: str, mesh: trimesh.Trimesh) -> list[tuple]:
    """Primitives in the part's geometry frame, in mm: (type, size, pos, rotation)."""
    if module == "xl330":
        return [("box", [10, 17, 11.5], [0, -7.5, -14.5], np.eye(3))]
    if module == "iphone_16_pro":
        return [("box", list(np.ptp(mesh.vertices, axis=0) / 2), list(mesh.bounds.mean(axis=0)), np.eye(3))]
    if module in ("inr18650", "electronics"):
        return []  # inside the backpack lid's box
    if module == "leg":
        # The stilt runs along +Y to a rounded tip. Keep every primitive inside the
        # tapering shaft, so none touches the floor before the real leg would.
        tip = mesh.vertices[np.argmax(mesh.vertices[:, 1])]
        axis_x, axis_z = tip[0], tip[2]
        upper = trimesh.PointCloud(mesh.vertices[mesh.vertices[:, 1] < 45]).bounding_box_oriented
        return [("box", list(upper.primitive.extents / 2), list(upper.primitive.transform[:3, 3]),
                 upper.primitive.transform[:3, :3]),
                ("capsule", [3.5], [[axis_x, 45, axis_z], [axis_x, 100, axis_z]], None),
                ("foot", [FOOT_RADIUS * 1e3], [axis_x, tip[1] - FOOT_RADIUS * 1e3, axis_z], None)]
    box = mesh.bounding_box_oriented.primitive
    return [("box", list(box.extents / 2), list(box.transform[:3, 3]), box.transform[:3, :3])]


def camera_frame(looks: int) -> np.ndarray:
    """Camera axes in the phone frame. MuJoCo cameras look down -z with image up +y."""
    up = np.array([0, 1.0, 0])
    back = np.array([0, 0, -1.0]) * looks  # -z of the camera points where it looks
    return np.column_stack([np.cross(up, back), up, back])


def portrait_fovy(focal_35mm: float) -> float:
    """Vertical field of view of a portrait 4:3 frame: the sensor's long side."""
    return float(np.degrees(2 * np.arctan(43.27 * 0.8 / 2 / focal_35mm)))


def build(manifest: dict) -> tuple[mujoco.MjSpec, dict]:
    joints, parts, variants = manifest["joints"], manifest["parts"], manifest["variants"]
    meshes = {k: trimesh.load(ASSETS / v["mesh"], force="mesh") for k, v in variants.items()}
    link_of = {i: ROOT if p["joint"] is None else joints[p["joint"]]["name"] for i, p in enumerate(parts)}
    origin = {ROOT: np.zeros(3)}
    for j in joints:
        origin[j["name"]] = CAD_TO_SIM @ np.array(j["pivot_mm"]) * 1e-3
    # A limb is named by its first joint: left_shoulder_pitch starts left_shoulder.
    limb_of = {ROOT: "trunk", "waist": "trunk"}
    for j in joints:
        first = j
        while first["parent"] is not None and joints[first["parent"]]["name"] != "waist":
            first = joints[first["parent"]]
        if j["name"] != "waist":
            limb_of[j["name"]] = "_".join(first["name"].split("_")[:2])

    spec = mujoco.MjSpec()
    spec.modelname = "phone_girl"
    spec.compiler.degree = False
    spec.compiler.inertiafromgeom = mujoco.mjtInertiaFromGeom.mjINERTIAFROMGEOM_FALSE
    spec.compiler.autolimits = True
    spec.meshdir = str(ASSETS)  # written as "assets", relative to the XML
    spec.stat.meansize = 0.03
    spec.stat.extent = 0.5

    bodies = {ROOT: spec.worldbody.add_body(name=ROOT)}
    bodies[ROOT].add_freejoint(name="root")
    pending = list(joints)
    while pending:  # parents before children
        for j in list(pending):
            parent = ROOT if j["parent"] is None else joints[j["parent"]]["name"]
            if parent in bodies:
                name = j["name"]
                child = "pelvis" if name == "waist" else f"{name}_link"
                body = bodies[parent].add_body(name=child, pos=origin[name] - origin[parent])
                default = j["default_rad"]
                limit = np.radians(next(v for k, v in TRAVEL_DEG.items() if name.endswith(k)))
                body.add_joint(name=name, type=mujoco.mjtJoint.mjJNT_HINGE, ref=default,
                               axis=CAD_TO_SIM @ np.array(j["axis"]), range=[default - limit, default + limit])
                bodies[name] = body
                pending.remove(j)

    def body_of(link):
        return bodies[link]

    used_meshes, inertials = set(), {}

    def mesh_asset(stem: str, mirrored: bool, **attributes) -> str:
        """An exported mesh, or its mirror image for a part placed inside an xflip()."""
        name = stem + ("_mirror" if mirrored else "")
        if name not in used_meshes:
            if mirrored:
                flipped = trimesh.load(ASSETS / f"{stem}.stl", force="mesh")
                flipped.apply_transform(np.diag([-1.0, 1, 1, 1]))
                flipped.export(ASSETS / f"{name}.stl")
            spec.add_mesh(name=name, file=f"{name}.stl", scale=[1e-3] * 3, **attributes)
            used_meshes.add(name)
        return name

    report = dict(cad_sha256=manifest["cad_sha256"], slicer=manifest["slicer"], links={}, joints=[], parts=[])
    phone = None
    for part in parts:
        link = link_of[part["index"]]
        key = part["variant"]
        props = variants[key]["mass"]
        rotation, position = placed(part)
        local = position - origin[link]
        com = rotation @ np.array(props["com_mm"]) * 1e-3 + local
        inertia = rotation @ np.array(props["inertia_g_mm2"]) @ rotation.T * 1e-9
        inertials.setdefault(link, []).append((props["mass_g"] * 1e-3, com, inertia))
        report["parts"].append(dict(index=part["index"], module=part["module"], link=link,
                                    mass_g=props["mass_g"], mass_source=props["source"]))
        if part["module"] == "iphone_16_pro":
            phone = (link, rotation, local)

        upright, mirrored = proper(rotation)
        visual = dict(type=mujoco.mjtGeom.mjGEOM_MESH, pos=local, quat=quat(upright), contype=0, conaffinity=0,
                      group=2, density=0)
        grey = part["module"] in ("xl330", "iphone_16_pro", "inr18650", "electronics", "backpack_lid")
        body_of(link).add_geom(name=f"{link}_{part['module']}_{part['index']}_visual",
                               meshname=mesh_asset(key, mirrored), **visual,
                               rgba=[0.2, 0.2, 0.22, 1] if grey else [0.42, 0.73, 0.67, 1])
        for name, decal in variants[key].get("decals", {}).items():
            # Decals are open surfaces (the face is a skin on the screen), so no volume.
            stem = decal["mesh"].removesuffix(".stl")
            body_of(link).add_geom(name=f"{link}_{part['module']}_{part['index']}_{name}",
                                   meshname=mesh_asset(stem, mirrored, inertia=mujoco.mjtMeshInertia.mjMESH_INERTIA_SHELL),
                                   **visual, rgba=[int(decal["color"][i:i + 2], 16) / 255 for i in (1, 3, 5)] + [1])

        bit = TRUNK if limb_of[link] == "trunk" else LIMB_BITS[limb_of[link]]
        for n, (kind, size, pos, frame) in enumerate(collision_shapes(part["module"], meshes[key])):
            name = f"{link}_{part['module']}_{part['index']}_{n}"
            # Priority 1: the robot's friction, not the floor's, sets the contact's.
            common = dict(contype=bit, conaffinity=GROUND | (ALL_BODY_BITS & ~bit), group=3, priority=1,
                          condim=3, friction=[0.6, 0.005, 0.0001], rgba=[0.9, 0.4, 0.2, 0.3])
            if kind == "box":
                body_of(link).add_geom(name=name, type=mujoco.mjtGeom.mjGEOM_BOX, size=np.array(size) * 1e-3,
                                       pos=rotation @ np.array(pos) * 1e-3 + local,
                                       quat=quat(proper(rotation @ frame)[0]), **common)
            elif kind == "capsule":
                ends = [rotation @ np.array(p) * 1e-3 + local for p in pos]
                body_of(link).add_geom(name=name, type=mujoco.mjtGeom.mjGEOM_CAPSULE,
                                       size=[size[0] * 1e-3, 0, 0], fromto=np.concatenate(ends), **common)
            else:
                side = link.split("_")[0]
                centre = rotation @ np.array(pos) * 1e-3 + local
                body_of(link).add_geom(name=f"{side}_foot", type=mujoco.mjtGeom.mjGEOM_SPHERE,
                                       size=[FOOT_RADIUS, 0, 0], pos=centre, **{**common, "rgba": [1, 0.8, 0.1, 1]})
                body_of(link).add_site(name=f"{side}_foot", pos=centre, size=[0.003, 0, 0])

    for link, items in inertials.items():
        mass_kg, com, inertia = summed_inertia(items)
        body = body_of(link)
        body.explicitinertial = True
        body.mass = mass_kg
        body.ipos = com
        body.fullinertia = [inertia[0, 0], inertia[1, 1], inertia[2, 2], inertia[0, 1], inertia[0, 2], inertia[1, 2]]
        report["links"][link] = dict(mass_kg=mass_kg, com_m=com.tolist(), inertia_kg_m2=inertia.tolist())

    # Phone sensors, all on the torso since the phone is held by the chest.
    link, rotation, local = phone
    phone_quat = quat(rotation)
    imu = rotation @ np.array(IMU_IN_PHONE_MM) * 1e-3 + local
    bodies[link].add_site(name="imu", pos=imu, quat=phone_quat, size=[0.004, 0, 0])
    for name, (pos, looks, focal) in CAMERAS.items():
        bodies[link].add_camera(name=name, pos=rotation @ np.array(pos) * 1e-3 + local,
                                quat=quat(rotation @ camera_frame(looks)), fovy=portrait_fovy(focal),
                                resolution=list(CAMERA_RESOLUTION))
    for name, kind in (("imu_accel", mujoco.mjtSensor.mjSENS_ACCELEROMETER),
                       ("imu_gyro", mujoco.mjtSensor.mjSENS_GYRO),
                       ("imu_quat", mujoco.mjtSensor.mjSENS_FRAMEQUAT),
                       ("imu_vel", mujoco.mjtSensor.mjSENS_VELOCIMETER)):
        spec.add_sensor(name=name, type=kind, objtype=mujoco.mjtObj.mjOBJ_SITE, objname="imu")

    # MuJoCo's depth-first joint order is the canonical servo order: actuators,
    # observations and bus slots all use it. Dynamixel ID = slot + 1.
    tree = spec.compile()
    order = [tree.joint(i).name for i in range(1, tree.njnt)]
    by_name = {j["name"]: j for j in joints}
    for slot, name in enumerate(order):
        j = by_name[name]
        actuator = spec.add_actuator(name=name, target=name, trntype=mujoco.mjtTrn.mjTRN_JOINT)
        actuator.set_to_motor()
        report["joints"].append(dict(name=name, slot=slot, dynamixel_id=slot + 1, cad_knob=j["knob"],
                                     parent=None if j["parent"] is None else joints[j["parent"]]["name"],
                                     default_rad=j["default_rad"], mirrored_servo=j["handedness"] < 0,
                                     axis_sim=(CAD_TO_SIM @ np.array(j["axis"])).tolist()))
    return spec, report


def exclusions(spec: mujoco.MjSpec) -> list[tuple[str, str]]:
    """Body pairs whose proxies already touch in the CAD pose: proxy artefacts, not contacts."""
    model = spec.compile()
    data = mujoco.MjData(model)
    mujoco.mj_forward(model, data)
    pairs = set()
    for contact in data.contact[:data.ncon]:
        a, b = (model.body(model.geom_bodyid[g]).name for g in (contact.geom1, contact.geom2))
        if contact.dist < 0 and "world" not in (a, b):
            pairs.add(tuple(sorted((a, b))))
    return sorted(pairs)


def stand(spec: mujoco.MjSpec, report: dict) -> None:
    """Raise the torso until the lower stilt tip touches the floor at qpos0."""
    model = spec.compile()
    data = mujoco.MjData(model)
    mujoco.mj_forward(model, data)
    feet = [model.geom(f"{side}_foot").id for side in ("left", "right")]
    height = FOOT_RADIUS - data.geom_xpos[feet, 2].min()
    spec.body(ROOT).pos = [0, 0, height]
    model = spec.compile()
    data = mujoco.MjData(model)
    mujoco.mj_forward(model, data)
    report["home"] = dict(root_height_m=float(height), foot_heights_m=data.geom_xpos[feet, 2].tolist(),
                          foot_positions_m=data.geom_xpos[feet].tolist(),
                          com_m=data.subtree_com[model.body(ROOT).id].tolist(),
                          total_mass_kg=float(model.body_mass.sum()))


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.parse_args()
    manifest = json.loads((ASSETS / "cad_manifest.json").read_text())
    import hashlib
    if manifest["cad_sha256"] != hashlib.sha256(CAD.read_bytes()).hexdigest():
        raise SystemExit("phone_girl.scad changed since the export; run phone-girl-export first")
    spec, report = build(manifest)
    stand(spec, report)
    pairs = exclusions(spec)
    for a, b in pairs:
        spec.add_exclude(bodyname1=a, bodyname2=b)
    report["excluded_body_pairs"] = pairs
    report["travel_deg"] = TRAVEL_DEG
    report["imu_in_phone_mm"] = IMU_IN_PHONE_MM
    report["assumptions"] = [
        "XL330-M288-T servos; 18 g each with a uniform-box case inertia.",
        "Printed parts are sliced PETG HF; bought masses come from mass.py.",
        f"The electronics box is a {manifest['variants']['electronics']['mass']['mass_g']} g guess.",
        "Wires, screws and glue are not modelled; randomize link masses to cover them.",
        "Joint travel is provisional, not measured; IMU position in the phone is a guess.",
        "Collision proxies are boxes, capsules and spheres; brackets are boxes.",
    ]
    model = spec.compile()  # validate before writing anything
    MJCF.write_text(spec.to_xml().replace(f'meshdir="{ASSETS}"', f'meshdir="{ASSETS.name}"'))
    MJCF.with_name("model_report.json").write_text(json.dumps(report, indent=1) + "\n")
    print(f"{model.nbody - 1} bodies, {model.njnt - 1} joints, {model.ngeom} geoms, "
          f"{model.body_mass.sum():.4f} kg, home height {report['home']['root_height_m']:.4f} m, "
          f"{len(pairs)} excluded pairs", flush=True)


if __name__ == "__main__":
    main()
