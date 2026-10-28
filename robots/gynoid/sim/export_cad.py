"""Export assembled BOSL2 frames, part meshes and slicer-derived mass properties.

The CAD source is never rewritten. Temporary instrumentation uses BOSL2's
$transform to capture each part after its attachment has been applied.
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

HERE = Path(__file__).resolve().parent
CAD = HERE.parent / "gynoid.scad"
ASSETS = HERE / "assets"
PARAMS = {
    "xl330": ["idler_disk", "drive"],
    "u_bracket": ["w"], "hip": [], "wedge": ["a", "w", "l"],
    "pole": ["l"], "shoulder": ["l"], "head": [], "hand": [],
    "thumb": [], "chest": [], "abdomen": [], "leg": [],
    "neck_link_1": [], "neck_link_2": [],
}
# Print orientation is part of the mass model, not just a presentation choice.
PRINT_ORIENTATION = {
    "u_bracket": "xrot(-90)", "head": "yrot(180)",
    "leg": "xrot(90)", "chest": "yrot(90)",
    "abdomen": "xrot(90)", "hand": "xrot(90)",
}


def closing(text: str, start: int, left="{", right="}") -> int:
    """Match brackets while ignoring strings and comments."""
    token = re.compile(r'"(?:\\.|[^"\\])*"|//[^\n]*|/\*[\s\S]*?\*/|['
                       + re.escape(left + right) + r']')
    depth = 0
    for match in token.finditer(text, start):
        if match.group() == left:
            depth += 1
        elif match.group() == right:
            depth -= 1
            if depth == 0:
                return match.start()
    raise ValueError("Unclosed CAD block")


def run(command: list[str]) -> subprocess.CompletedProcess:
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode or "ERROR:" in result.stderr or "WARNING:" in result.stderr:
        raise RuntimeError(f"{' '.join(command)}\n{result.stdout}\n{result.stderr}")
    return result


def extract_frames(source: str) -> list[dict]:
    edits = []
    for name, params in PARAMS.items():
        match = re.search(r"module\s+" + name + r"\s*\(", source)
        if match is None:
            raise ValueError(f"CAD module {name} is missing")
        start = source.index("{", closing(source, source.index("(", match.start()), "(", ")"))
        end = closing(source, start)
        body = source[start + 1:end]
        values = "[" + ",".join(params) + "]"
        # The incoming frame distinguishes repeated instances. The anchored
        # frame in the echo below is the frame used for mesh and mass placement.
        scope = (f'\n$sim_path=concat(is_undef($sim_path)?[]:$sim_path,'
                 f'[str("{name}@",$transform,{values})]);\n')
        if name == "hand":
            body = f'echo(SIM=["{name}",{values},$transform,$sim_path]) {{\n{body}\n}}'
        else:
            attach = body.index("attachable(")
            opening = body.index("{", closing(body, body.index("(", attach), "(", ")"))
            # echo is a prefix to the geometry child, preserving attachable's
            # exactly-two-children contract and all descendant transforms.
            body = (body[:opening + 1]
                    + f'\necho(SIM=["{name}",{values},$transform,$sim_path])\n'
                    + body[opening + 1:])
        edits.append((start + 1, end, scope + body))
    for start, end, value in sorted(edits, reverse=True):
        source = source[:start] + value + source[end:]
    with tempfile.TemporaryDirectory(prefix=".sim-", dir=CAD.parent) as temporary:
        path = Path(temporary) / "frames.scad"
        # Relative includes in the original file are relative to its directory.
        source = source.replace("<../lib/globals.scad>", "<../../lib/globals.scad>")
        path.write_text(source)
        out = Path(temporary) / "frames.echo"
        run(["openscad", "-o", str(out), str(path)])
        frames = []
        seen = set()
        for line in out.read_text().splitlines():
            if not line.startswith("ECHO: SIM = "):
                continue
            name, values, transform, ancestry = json.loads(line.removeprefix("ECHO: SIM = "))
            # BOSL2 diff/tag evaluation can visit the same geometry repeatedly.
            identity = json.dumps([ancestry, transform])
            if identity in seen:
                continue
            seen.add(identity)
            frames.append(dict(module=name, parameters=dict(zip(PARAMS[name], values)),
                               transform_mm=transform, ancestry=ancestry))
    if sum(frame["module"] == "xl330" for frame in frames) != 21:
        raise ValueError("Expected 21 servo instances; review topology for changed CAD")
    return frames


def scad_value(value):
    return json.dumps(value)


def variants(frames):
    result = {}
    for frame in frames:
        name = frame["module"]
        params = frame["parameters"]
        if name == "xl330":
            params = {"idler_disk": params["idler_disk"]}
        key = name + "".join(f"_{key}_{value}" for key, value in params.items())
        frame["asset"] = key
        result[key] = dict(module=name, parameters=params)
    return result


def part_call(part):
    return part["module"] + "(" + ",".join(
        f"{key}={scad_value(value)}" for key, value in part["parameters"].items()) + ");"


def export_mesh(item):
    key, part = item
    with tempfile.TemporaryDirectory(prefix=".mesh-", dir=HERE) as temporary:
        path = Path(temporary) / "part.scad"
        path.write_text(f"include <../../gynoid.scad>\n!{part_call(part)}\n")
        run(["openscad", "--export-format", "binstl", "-o", str(ASSETS / f"{key}.stl"), str(path)])
    print(f"Mesh: {key}", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--frames-only", action="store_true")
    parser.add_argument("--skip-mass", action="store_true", help="Reuse existing slicer results")
    args = parser.parse_args()
    ASSETS.mkdir(exist_ok=True)
    source = CAD.read_text()
    source_hash = hashlib.sha256(source.encode()).hexdigest()
    if args.skip_mass and not args.frames_only:
        prior_mass = json.loads((ASSETS / "print_mass.json").read_text())
        if prior_mass["cad_sha256"] != source_hash:
            raise ValueError("CAD changed; cannot reuse old mass properties. Omit --skip-mass.")
    frames = extract_frames(source)
    parts = variants(frames)
    manifest = dict(cad_sha256=source_hash,
                    frames=frames, parts=parts)
    (ASSETS / "cad_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(f"Extracted {len(frames)} part instances, {len(parts)} unique meshes", flush=True)
    if args.frames_only:
        return
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(export_mesh, parts.items()))
    if not args.skip_mass:
        printed = [(key, part) for key, part in parts.items() if part["module"] != "xl330"]
        wrapper = HERE / "mass_parts.scad"
        lines = ["// Generated by export_cad.py; orientations also define the mass model.",
                 "include <../gynoid.scad>"]
        for key, part in printed:
            orientation = PRINT_ORIENTATION.get(part["module"], "")
            # Labels disambiguate parameter variants in print_mass output.
            lines.append(f"// !{orientation} {part_call(part)} // print {key}")
        wrapper.write_text("\n".join(lines) + "\n")
        command = [sys.executable, str(CAD.parent.parent / "tools/print_mass.py"),
                   str(wrapper), "--json", "--jobs", "4"]
        result = subprocess.run(command, capture_output=True, text=True)
        if result.returncode:
            raise RuntimeError(result.stdout + result.stderr)
        masses = json.loads(result.stdout)
        for (key, _), mass in zip(printed, masses, strict=True):
            mass["asset"] = key
            mass["source"] = mass["source"].replace(str(HERE) + "/", "")
        provenance = dict(cad_sha256=source_hash, print_orientations=PRINT_ORIENTATION,
                          print_tool_sha256=hashlib.sha256(Path(command[1]).read_bytes()).hexdigest(),
                          parts=masses)
        (ASSETS / "print_mass.json").write_text(json.dumps(provenance, indent=2) + "\n")
        print(result.stderr, file=sys.stderr)
        print(f"Sliced {len(masses)} part variants", flush=True)


if __name__ == "__main__":
    main()
