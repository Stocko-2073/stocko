"""Export phone_girl.scad as a joint tree, part meshes and printed mass properties.

The CAD is never edited. A temporary copy beside it echoes every part's BOSL2
$transform. Turning one pose knob at a time shows which parts that servo moves
and about which axis, so the tree, axes and directions come from the assembled
CAD rather than from reading its anchors. Printed parts are sliced with
tools/print_mass.py, so walls, infill and print orientation count.

Joint angles are servo shaft angles: right-handed about the shaft, pointing out
of the horn, and zero at the CAD's drive=0. A servo inside an xflip() turns
against `drive`, so its angle is -drive. Frames are those of the CAD's
default_pose. The manifest is in the CAD frame (+Z up, +Y back), mm and g.
"""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import uuid

import numpy as np
import trimesh

from phone_girl import ASSETS, CAD, CAD_TO_SIM, ROBOT_DIR

sys.path.insert(0, str(ROBOT_DIR))
import mass  # noqa: E402  the robot's own mass tool: print orientations and bought parts

# Echoed modules and the parameters that change their shape. A servo's drive
# is echoed too, to see which servo each pose knob turns.
PARTS = {"xl330": ["idler_disk", "drive"], "iphone_16_pro": [], "inr18650": [], "electronics": [],
         **mass.PRINTED}
NUDGE = 5.0  # degrees per knob when finding joints
# Boxes and the cell used for bought parts' inertia; masses and CoMs are mass.py's.
BOX = {"xl330": [20, 34, 23], "electronics": [67, 18, 16]}
CELL = dict(d=18, l=65)
ELECTRONICS_G = 20.0


def run_scad(source: str, suffix: str, *args: str) -> bytes:
    """Run OpenSCAD on source beside the CAD so its relative includes resolve."""
    path = ROBOT_DIR / f".sim-{uuid.uuid4().hex[:8]}.scad"
    with tempfile.TemporaryDirectory() as temporary:
        out = Path(temporary) / f"out{suffix}"
        try:
            path.write_text(source)
            result = subprocess.run(["openscad", *args, "-o", str(out), str(path)],
                                    capture_output=True, text=True)
        finally:
            path.unlink(missing_ok=True)
        if result.returncode or "ERROR:" in result.stderr:
            raise RuntimeError(result.stderr)
        return out.read_bytes()


def instrument(source: str) -> str:
    """Echo each part's name, parameters and geometry frame. The echo prefixes
    attachable()'s geometry child, so $transform includes the anchor."""
    edits = []
    for name, params in PARTS.items():
        match = re.search(r"\bmodule\s+" + name + r"\s*\(", source)
        if match is None:
            raise ValueError(f"CAD module {name} is missing")
        attach = source.index("attachable(", match.end())
        opening = source.index("{", mass.closing(source, source.index("(", attach), "(", ")"))
        edits.append((opening + 1, f'\necho(SIM=["{name}",[{",".join(params)}],$transform,'
                                   f'is_undef($sim_variant)?"":$sim_variant])'))
    for at, text in sorted(edits, reverse=True):
        source = source[:at] + text + source[at:]
    return source + "\necho(SIM_POSE=default_pose);\n"


def echoes(source: str, pose: list[float] | None = None) -> tuple[list, list]:
    args = ["-D", "pose=" + json.dumps(pose)] if pose is not None else []
    text = run_scad(source, ".echo", *args).decode()
    rows, default = [], None
    for line in text.splitlines():
        if line.startswith("ECHO: SIM = "):
            name, params, transform, variant = json.loads(line.removeprefix("ECHO: SIM = "))
            rows.append(dict(module=name, params=dict(zip(PARTS[name], params)),
                             transform=np.array(transform, dtype=float), variant=variant))
        elif line.startswith("ECHO: SIM_POSE = "):
            default = json.loads(line.removeprefix("ECHO: SIM_POSE = "))
    return rows, default


def rotation_vector(rotation: np.ndarray) -> np.ndarray:
    angle = np.arccos(np.clip((np.trace(rotation) - 1) / 2, -1, 1))
    if angle < 1e-9:
        return np.zeros(3)
    skew = np.array([rotation[2, 1] - rotation[1, 2], rotation[0, 2] - rotation[2, 0],
                     rotation[1, 0] - rotation[0, 1]])
    return skew / (2 * np.sin(angle)) * angle


def discover(source: str) -> dict:
    """Nudge each pose knob and record the servo it turns and the parts it moves."""
    base, default = echoes(source)
    with ThreadPoolExecutor(8) as pool:
        nudged = list(pool.map(lambda k: echoes(source, [v + NUDGE * (i == k) for i, v in
                                                         enumerate(default)])[0], range(len(default))))
    joints = []
    for knob, rows in enumerate(nudged):
        if [r["module"] for r in rows] != [r["module"] for r in base]:
            raise ValueError("A pose knob changed the CAD's structure")
        turned = [i for i, (a, b) in enumerate(zip(base, rows))
                  if a["module"] == "xl330" and a["params"]["drive"] != b["params"]["drive"]]
        if len(turned) != 1:
            raise ValueError(f"Pose knob {knob} turns {len(turned)} servos")
        servo = turned[0]
        step = rows[servo]["params"]["drive"] - base[servo]["params"]["drive"]
        moved = [i for i, (a, b) in enumerate(zip(base, rows))
                 if not np.allclose(a["transform"], b["transform"], atol=1e-4)]
        frame = base[servo]["transform"]
        shaft, pivot = frame[:3, 2] / np.linalg.norm(frame[:3, 2]), frame[:3, 3]
        handed = float(np.sign(np.linalg.det(frame[:3, :3])))
        # Every moved part must turn rigidly about the servo shaft.
        per_drive = []
        for i in moved:
            a, b = base[i]["transform"], rows[i]["transform"]
            turn = b[:3, :3] @ np.linalg.inv(a[:3, :3])
            vector = rotation_vector(turn)
            per_drive.append(vector @ shaft / np.radians(step))
            off_axis = np.linalg.norm(vector - (vector @ shaft) * shaft)
            residual = np.linalg.norm(turn @ (a[:3, 3] - pivot) + pivot - b[:3, 3])
            if off_axis > 1e-3 or residual > 5e-3:
                raise ValueError(f"Knob {knob} moves part {i} off servo {servo}'s shaft")
        child_turn = float(np.round(np.mean(per_drive)))
        if abs(child_turn) != 1 or np.ptp(per_drive) > 1e-3:
            raise ValueError(f"Knob {knob}: moved parts don't follow servo {servo}")
        drive = base[servo]["params"]["drive"]
        joints.append(dict(knob=knob, servo_part=servo, knob_to_drive=step / NUDGE, handedness=handed,
                           horn_side=child_turn == handed, moved=moved,
                           # The child turns about this axis by +angle.
                           axis=(shaft * child_turn * handed).tolist(), pivot_mm=pivot.tolist(),
                           default_drive_deg=drive, default_deg=handed * drive))
    return dict(base=base, default_pose=default, joints=joints)


def build_tree(parts: list, joints: list) -> None:
    """Give each part its link: the deepest joint that moves it, or the torso."""
    sets = [set(j["moved"]) for j in joints]
    for a in sets:
        for b in sets:
            if not (a <= b or b <= a or not a & b):
                raise ValueError("Moved sets overlap without nesting; not a tree")
    for k, joint in enumerate(joints):
        parents = [j for j, s in enumerate(sets) if s > sets[k]]
        joint["parent"] = min(parents, key=lambda j: len(sets[j])) if parents else None
    for i, part in enumerate(parts):
        owners = [k for k, s in enumerate(sets) if i in s]
        part["joint"] = min(owners, key=lambda k: len(sets[k])) if owners else None


def name_joints(parts: list, joints: list, cad_to_sim: np.ndarray) -> None:
    """Name limbs by assembled side (+Y_sim is the robot's left) and position in the chain."""
    labels = {"arm": ["shoulder_pitch", "shoulder_yaw", "elbow", "wrist"],
              "leg": ["hip_roll", "hip_pitch", "thigh_yaw", "knee"]}
    roots = [k for k, j in enumerate(joints) if j["parent"] is None]
    waist = [k for k in roots if any(joints[c]["parent"] == k for c in range(len(joints)))
             and len(joints[k]["moved"]) == max(len(joints[r]["moved"]) for r in roots)]
    if len(waist) != 1:
        raise ValueError("Could not identify the waist joint")
    joints[waist[0]]["name"] = "waist"
    starts = [k for k in range(len(joints)) if k not in waist
              and joints[k]["parent"] in (None, waist[0])]
    for start in starts:
        kind = "leg" if joints[start]["parent"] == waist[0] else "arm"
        side = "left" if (cad_to_sim @ joints[start]["pivot_mm"])[1] > 0 else "right"
        chain, k = [start], start
        while children := [c for c in range(len(joints)) if joints[c]["parent"] == k]:
            if len(children) != 1:
                raise ValueError(f"Joint {k} branches; limbs must be chains")
            k = children[0]
            chain.append(k)
        if len(chain) != len(labels[kind]):
            raise ValueError(f"Expected {len(labels[kind])} joints in a {kind}, got {len(chain)}")
        for k, label in zip(chain, labels[kind]):
            joints[k]["name"] = f"{side}_{label}"


def variant_key(part: dict) -> str:
    params = {k: v for k, v in part["params"].items() if k != "drive"}
    return part["module"] + "".join(f"_{k}_{v}" for k, v in params.items())


def call(module: str, params: dict) -> str:
    return mass.call(module, {k: v for k, v in params.items() if k != "drive"})


def frame_of_calls(source: str, variants: dict) -> dict:
    """Each variant's geometry frame when called bare, as print_mass and the mesh export do."""
    calls = "\n".join(f'let($sim_variant="{key}") {call(v["module"], v["params"])};'
                      for key, v in variants.items())
    rows, _ = echoes(source + "\n" + calls)
    return {r["variant"]: r["transform"] for r in rows
            if r["variant"] and r["module"] == variants[r["variant"]]["module"]}


def export_mesh(key: str, variant: dict, called: np.ndarray) -> None:
    wrapper = f"include <{CAD.name}>\n!{call(variant['module'], variant['params'])};\n"
    # Coarser facets: these meshes are for viewing and fitting collision shapes.
    data = run_scad(wrapper, ".stl", "--export-format", "binstl", "-D", "$fa=6", "-D", "$fs=1")
    with tempfile.NamedTemporaryFile(suffix=".stl") as handle:
        handle.write(data)
        handle.flush()
        mesh = trimesh.load(handle.name, force="mesh")
    mesh.apply_transform(np.linalg.inv(called))  # call frame -> geometry frame
    mesh.export(ASSETS / f"{key}.stl")
    print(f"mesh {key}: {len(mesh.faces)} faces", flush=True)


def box_inertia(grams: float, size) -> list:
    size = np.asarray(size, dtype=float)
    return np.diag(grams / 12 * (size @ size - size * size)).tolist()


def bought(module: str, electronics_g: float, phone_size: list) -> dict:
    if module == "inr18650":
        grams, com = mass.BOUGHT[module]
        r, l = CELL["d"] / 2, CELL["l"]
        side = grams * (3 * r * r + l * l) / 12
        return dict(mass_g=grams, com_mm=com, inertia_g_mm2=np.diag([side, side, grams * r * r / 2]).tolist(),
                    source="Molicel INR-18650-M35A, 48 g; solid cylinder")
    if module == "electronics":
        return dict(mass_g=electronics_g, com_mm=mass.ELECTRONICS_BOX,
                    inertia_g_mm2=box_inertia(electronics_g, BOX[module]),
                    source="placeholder box; mass is a guess, randomized in training")
    grams, com = mass.BOUGHT[module]
    size = phone_size if module == "iphone_16_pro" else BOX[module]
    return dict(mass_g=grams, com_mm=com, inertia_g_mm2=box_inertia(grams, size),
                source=f"{grams} g from mass.py; uniform box inertia")


def slice_printed(source: str, variants: dict, called: dict, jobs: int) -> tuple[dict, str]:
    printed = {k: v for k, v in variants.items() if v["module"] in mass.PRINTED}
    wrapper = ROBOT_DIR / f".sim-mass-{uuid.uuid4().hex[:8]}.scad"
    lines = [f"include <{CAD.name}>"]
    lines += [f"// !{mass.orientation(source, v['module'])} {call(v['module'], v['params'])}; // print {k}"
              for k, v in printed.items()]
    try:
        wrapper.write_text("\n".join(lines) + "\n")
        result = subprocess.run([sys.executable, str(mass.PRINT_MASS), str(wrapper), "--json",
                                 "--jobs", str(jobs)], capture_output=True, text=True)
    finally:
        wrapper.unlink(missing_ok=True)
    if result.returncode:
        raise RuntimeError(result.stdout + result.stderr)
    sliced = json.loads(result.stdout)
    out = {}
    for (key, variant), part in zip(printed.items(), sliced, strict=True):
        # print_mass reports in the bare call's frame; move it to the geometry frame.
        inverse = np.linalg.inv(called[key])
        rotation = inverse[:3, :3]
        out[key] = dict(mass_g=part["mass_g"], com_mm=(inverse @ [*part["com_mm"], 1])[:3].tolist(),
                        inertia_g_mm2=(rotation @ np.array(part["inertia_g_mm2"]) @ rotation.T).tolist(),
                        source=f"sliced, printed as {mass.orientation(source, variant['module'])}")
    return out, sliced[0]["settings"]


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--skip-mass", action="store_true", help="reuse sliced masses; the CAD must be unchanged")
    parser.add_argument("--electronics-g", type=float, default=ELECTRONICS_G,
                        help="mass of the electronics() placeholder box, default %(default)s g")
    parser.add_argument("--jobs", type=int, default=6)
    args = parser.parse_args()

    ASSETS.mkdir(exist_ok=True)
    text = CAD.read_text()
    phone_size = json.loads(re.search(r"^iphone_size=(\[[^\]]+\]);", text, re.M).group(1))
    digest = hashlib.sha256(text.encode()).hexdigest()
    previous = ASSETS / "cad_manifest.json"
    if args.skip_mass and json.loads(previous.read_text())["cad_sha256"] != digest:
        parser.error("The CAD changed since the last export; slice again without --skip-mass")
    source = instrument(text)
    found = discover(source)
    joints, default = found["joints"], found["default_pose"]
    parts = [dict(index=i, module=r["module"], params=r["params"], variant=variant_key(r))
             for i, r in enumerate(found["base"])]
    build_tree(parts, joints)
    name_joints(parts, joints, CAD_TO_SIM)
    if len({j["name"] for j in joints}) != len(joints):
        raise ValueError("Joint names collide")

    for part, row in zip(parts, found["base"]):
        part["transform"] = row["transform"].tolist()

    variants = {}
    for part in parts:
        variants.setdefault(part["variant"], dict(module=part["module"],
                                                  params={k: v for k, v in part["params"].items() if k != "drive"}))
    called = frame_of_calls(source, variants)
    with ThreadPoolExecutor(6) as pool:
        list(pool.map(lambda kv: export_mesh(kv[0], kv[1], called[kv[0]]), variants.items()))

    if args.skip_mass:
        old = json.loads(previous.read_text())
        properties, settings = {k: v["mass"] for k, v in old["variants"].items()
                                if v["module"] in mass.PRINTED}, old["slicer"]
    else:
        properties, settings = slice_printed(text, variants, called, args.jobs)
    for key, variant in variants.items():
        variant["mass"] = properties[key] if variant["module"] in mass.PRINTED else \
            bought(variant["module"], args.electronics_g, phone_size)
        variant["mesh"] = f"{key}.stl"

    for joint in joints:
        joint["default_rad"] = float(np.radians(joint["default_deg"]))
    manifest = dict(
        cad_sha256=digest, print_tool_sha256=hashlib.sha256(Path(mass.PRINT_MASS).read_bytes()).hexdigest(),
        slicer=settings, units="mm, g, CAD frame (+Z up, +Y back); joint angles in rad",
        default_pose=default, nudge_deg=NUDGE, phone_size_mm=phone_size,
        joints=[{k: v for k, v in j.items() if k != "moved"} | dict(moved_parts=j["moved"]) for j in joints],
        parts=parts, variants=variants)
    previous.write_text(json.dumps(manifest, indent=1) + "\n")
    total = sum(variants[p["variant"]]["mass"]["mass_g"] for p in parts)
    print(f"{len(parts)} parts, {len(joints)} joints, {len(variants)} meshes, {total:.1f} g", flush=True)


if __name__ == "__main__":
    main()
