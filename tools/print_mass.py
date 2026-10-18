#!/usr/bin/env python3
"""Mass, center of mass and inertia of a part as it will print, from its G-code.

Infill percentage says little about a printed part's mass. Walls and top and
bottom layers are solid, so a small part at 15% infill can weigh 40% of the
solid model, and its center of mass moves toward the thin, mostly solid
features. So this slices the part with Bambu Studio's CLI and adds up the
plastic in every extrusion move, which covers walls, skins, infill, bridges and
whatever else the slicer does.

Inputs:
- A .scad file. Each print line (`// !xrot(180) wheel(); // print`, see
  CAD_STYLE_GUIDE.md) is uncommented in a hidden copy next to the file, so
  relative includes still resolve, then rendered and sliced. Results are in
  the part's own frame: the print line's transforms are undone. A file without
  print lines is sliced as it renders.
- An .stl, taken as already in print orientation. Results are in its frame.
- A .gcode, or a sliced .3mf saved from the GUI. Results are in plate
  coordinates.

Presets default to the ones selected in the GUI here: Bambu Lab X1 Carbon 0.4
nozzle, 0.20mm Standard @BBL X1C and Bambu PETG HF @BBL X1C. Other names are
looked up in Bambu Studio's system profiles, then in the user presets.

Units are g, mm and g*mm^2 (1 g*mm^2 = 1e-9 kg*m^2). Inertia is about the
center of mass, with axes in the same frame as the center of mass.

Mass is the filament the G-code pushes, the filament preset's flow ratio
included (PETG HF's 0.95 makes a 100% part 95% of the solid model), at the
preset's diameter and density. Weigh a print and correct it with
--set filament_density=... if they differ.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import glob
import io
import json
import math
import os
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import zipfile

BAMBU_APP = os.environ.get("BAMBU_STUDIO", "/Applications/BambuStudio.app")
USER_PRESETS = os.path.expanduser("~/Library/Application Support/BambuStudio/user")
MACHINE = "Bambu Lab X1 Carbon 0.4 nozzle"
PROCESS = "0.20mm Standard @BBL X1C"
FILAMENT = "Bambu PETG HF @BBL X1C"
# The CLI checks the filament against a plate type, which the GUI keeps per project.
PLATE = "Textured PEI Plate"

# Extrusions under these features, and before the first feature label (the
# start G-code's purge line), aren't part of the part.
NOT_PART = ("skirt", "brim", "support", "prime tower", "wipe tower", "custom")
# Transforms a print line can put in front of the part, mapped to the BOSL2
# functions that return their matrices. NO_MOVE calls are skipped, and the
# first call in neither set is the part.
MATRIX = {n: n for n in ("up", "down", "left", "right", "fwd", "back", "move", "xrot", "yrot",
                         "zrot", "rot", "xflip", "yflip", "zflip", "mirror", "xscale", "yscale",
                         "zscale", "scale")}
MATRIX.update(translate="move", rotate="rot")
NO_MOVE = {"render", "color", "recolor", "color_this", "hide", "show_only", "show_all"}
IDENT = [[1.0, 0.0, 0.0, 0.0], [0.0, 1.0, 0.0, 0.0], [0.0, 0.0, 1.0, 0.0], [0.0, 0.0, 0.0, 1.0]]

PRINT_LINE = re.compile(r"^(\s*)//\s*(\S.*;)\s*//\s*print\b[ \t]*(.*?)\s*$")
CALL = re.compile(r"\s*([A-Za-z_$][\w$]*)\s*\(")
FEATURE = re.compile(r";\s*(?:FEATURE|TYPE):\s*(.*?)\s*$")
HEIGHT = re.compile(r";\s*(?:LAYER_)?HEIGHT:\s*([\d.]+)")
CONFIG = re.compile(r";\s*([a-z][a-z0-9_]*)\s*=\s*(.*?)\s*$")
WEIGHT = re.compile(r";\s*total filament (?:weight|used) \[g\]\s*[:=]\s*([\d.]+)")


class Failure(Exception):
    pass


def warn(msg: str) -> None:
    print(f"warning: {msg}", file=sys.stderr)


# --- print lines -------------------------------------------------------------

def calls(stmt: str) -> list[tuple[str, str]]:
    """`!yrot(90) leg(a=f(1)) nop();` -> [("yrot", "90"), ("leg", "a=f(1)"), ("nop", "")]"""
    s, i, out = stmt.lstrip("!*%# "), 0, []
    while True:
        m = CALL.match(s, i)
        if not m:
            return out
        j, depth, quoted = m.end(), 1, False
        while j < len(s) and depth:
            c = s[j]
            if quoted:
                quoted = c != '"' or s[j - 1] == "\\"
            elif c == '"':
                quoted = True
            elif c in "()":
                depth += 1 if c == "(" else -1
            j += 1
        out.append((m.group(1), s[m.end():j - 1].strip()))
        i = j


def print_lines(scad: str) -> list[dict]:
    """The file's print lines, each with the part it prints and an OpenSCAD
    expression for the matrix of the transforms in front of that part."""
    parts = []
    for n, line in enumerate(open(scad).read().split("\n"), 1):
        m = PRINT_LINE.match(line)
        if not m:
            continue
        terms = []
        for name, args in calls(m.group(2)):
            if name in MATRIX:
                terms.append(f"{MATRIX[name]}({args})")
            elif name not in NO_MOVE:
                parts.append(dict(line=n, stmt=m.group(2), name=" ".join(filter(None, [name, m.group(3)])),
                                  transform="*".join(terms)))
                break
    return parts


def openscad(cmd: list[str]) -> tuple[int, str]:
    r = subprocess.run(["openscad"] + cmd, capture_output=True, text=True)
    return r.returncode, r.stdout + r.stderr


def failed(out: str) -> Failure:
    return Failure("openscad failed:\n  " + "\n  ".join(out.strip().splitlines()[-6:]))


def render(scad: str, part: dict | None, defines: list[str], stl: str) -> list | None:
    """Export the part in print orientation. Returns the print transform (part
    frame to print frame, 4x4), or None if OpenSCAD couldn't evaluate it."""
    cmd = ["--export-format", "binstl", "-o", stl]
    for d in defines:
        cmd += ["-D", d]
    if part is None:
        code, out = openscad(cmd + [scad])
        if code:
            raise failed(out)
        return IDENT
    lines = open(scad).read().split("\n")
    n = part["line"]
    indent = re.match(r"\s*", lines[n - 1]).group(0)
    # The echo sits in the print line's scope, so it also proves the line ran.
    lines[n - 1] = (f'{indent}!{part["stmt"].lstrip("!*%# ")} '
                    f'echo(PRINT_MASS={part["transform"] or IDENT});')
    tmp = os.path.join(os.path.dirname(os.path.abspath(scad)), f".{os.path.basename(scad)}.{n}.print_mass.scad")
    try:
        with open(tmp, "w") as f:
            f.write("\n".join(lines))
        code, out = openscad(cmd + [tmp])
    finally:
        os.remove(tmp)
    # A `!` on an unknown module is dropped: OpenSCAD renders nothing, or the whole file.
    unknown = re.search(rf"unknown (module|function) '(\w+)' in file {re.escape(os.path.basename(tmp))}, "
                        rf"line {n}\b", out)
    if unknown:
        raise Failure(f"line {n} calls {unknown.group(2)}(), which isn't a {unknown.group(1)} here")
    if code:
        raise failed(out)
    echoes = re.findall(r"ECHO: PRINT_MASS = (.*)", out)
    if not echoes:
        raise Failure(f"line {n} never ran; is it under a * or inside a module nothing calls?")
    if len(set(echoes)) > 1:
        warn(f"line {n} runs {len(echoes)} times with different transforms; using the first")
    try:
        return json.loads(echoes[0])
    except ValueError:
        return None


# --- meshes ------------------------------------------------------------------

def read_stl(path: str) -> list[tuple]:
    data = open(path, "rb").read()
    if len(data) >= 84 and len(data) == 84 + 50 * struct.unpack_from("<I", data, 80)[0]:
        n = struct.unpack_from("<I", data, 80)[0]
        return [tuple(struct.unpack_from("<3f", data, 96 + 50 * i + 12 * k) for k in range(3))
                for i in range(n)]
    v = [tuple(map(float, l.split()[1:4])) for l in data.decode(errors="replace").splitlines()
         if l.strip().startswith("vertex")]
    return [tuple(v[i:i + 3]) for i in range(0, len(v) - 2, 3)]


def write_stl(path: str, tris: list[tuple]) -> None:
    with open(path, "wb") as f:
        f.write(b"\0" * 80 + struct.pack("<I", len(tris)))
        for t in tris:
            f.write(struct.pack("<12fH", 0, 0, 0, *t[0], *t[1], *t[2], 0))


def solid(tris: list[tuple]) -> tuple[float, list[float], list[float], list[float]]:
    """Volume, centroid and bounding box of a closed mesh."""
    vol, c = 0.0, [0.0, 0.0, 0.0]
    lo, hi = [math.inf] * 3, [-math.inf] * 3
    for a, b, d in tris:
        v = (a[0] * (b[1] * d[2] - b[2] * d[1]) + a[1] * (b[2] * d[0] - b[0] * d[2])
             + a[2] * (b[0] * d[1] - b[1] * d[0])) / 6
        vol += v
        for i in range(3):
            c[i] += v * (a[i] + b[i] + d[i]) / 4
            lo[i] = min(lo[i], a[i], b[i], d[i])
            hi[i] = max(hi[i], a[i], b[i], d[i])
    if vol <= 0:
        raise Failure("the part has no volume")
    return vol, [k / vol for k in c], lo, hi


# --- presets and slicing -----------------------------------------------------

def find_preset(kind: str, ref: str) -> dict:
    if ref.endswith(".json") and os.path.exists(ref):
        return json.load(open(ref))
    dirs = [os.path.join(BAMBU_APP, "Contents/Resources/profiles/BBL", kind)]
    dirs += sorted(glob.glob(os.path.join(USER_PRESETS, "*", kind)))
    for d in dirs:
        if os.path.exists(os.path.join(d, ref + ".json")):
            return json.load(open(os.path.join(d, ref + ".json")))
    for d in dirs:
        for p in glob.glob(os.path.join(d, "**", "*.json"), recursive=True):
            try:
                if json.load(open(p)).get("name") == ref:
                    return json.load(open(p))
            except ValueError:
                pass
    raise Failure(f"no {kind} preset named {ref!r}")


def load_preset(kind: str, ref: str) -> dict:
    """A preset with its `inherits` chain merged in; the CLI wants it whole.
    It's marked as a system preset, a whole one with no parent: the CLI only
    checks a user preset's printer through the parent."""
    chain = [find_preset(kind, ref)]
    while chain[-1].get("inherits"):
        chain.append(find_preset(kind, chain[-1]["inherits"]))
    cfg = {"type": kind}  # user presets can leave it out
    for d in reversed(chain):
        cfg.update(d)
    cfg.pop("inherits", None)
    cfg["from"] = "system"
    return cfg


def presets_for(args) -> dict:
    presets = {k: load_preset(k, getattr(args, k)) for k in ("process", "filament")}
    # Without --machine, use the default printer, or the one a process is made for.
    fits = presets["process"].get("compatible_printers") or [MACHINE]
    args.machine = args.machine or (MACHINE if MACHINE in fits else fits[0])
    presets["machine"] = load_preset("machine", args.machine)
    presets["machine"]["printer_settings_id"] = args.machine
    presets["process"]["print_settings_id"] = args.process
    presets["filament"]["filament_settings_id"] = [args.filament]
    presets["process"]["curr_bed_type"] = PLATE
    overrides = [("sparse_infill_density", args.infill), ("sparse_infill_pattern", args.pattern),
                 ("wall_loops", args.walls), ("top_shell_layers", args.top),
                 ("bottom_shell_layers", args.bottom)]
    overrides += [tuple(s.split("=", 1)) for s in args.set]
    for key, value in overrides:
        if value is None:
            continue
        cfg = next((presets[k] for k in ("process", "filament", "machine") if key in presets[k]),
                   presets["process"])
        old = cfg.get(key)
        cfg[key] = [str(value)] * len(old) if isinstance(old, list) else str(value)
    # Like the GUI, switch to rectilinear for solid infill if the pattern can't do it.
    process = presets["process"]
    if process.get("sparse_infill_density") == "100%" and not args.pattern and process.get(
            "sparse_infill_pattern") not in ("zig-zag", "line", "concentric", "alignedrectilinear"):
        process["sparse_infill_pattern"] = "zig-zag"
    return presets


def slice_stl(stl: str, presets: dict, workdir: str) -> str:
    paths = {}
    for kind, cfg in presets.items():
        paths[kind] = os.path.join(workdir, kind + ".json")
        with open(paths[kind], "w") as f:
            json.dump(cfg, f)
    out = os.path.join(workdir, "sliced")
    # Run in workdir: the CLI drops a result.json in its working directory.
    r = subprocess.run([os.path.join(BAMBU_APP, "Contents/MacOS/BambuStudio"),
                        "--orient", "0", "--arrange", "0", "--slice", "0",
                        "--load-settings", f'{paths["machine"]};{paths["process"]}',
                        "--load-filaments", paths["filament"], "--outputdir", out, stl],
                       capture_output=True, text=True, cwd=workdir)
    gcode = os.path.join(out, "plate_1.gcode")
    if not os.path.exists(gcode):
        # Its messages are the untimestamped lines and the [error] log lines.
        log = (r.stdout + r.stderr).splitlines()
        errors = [re.sub(r"^\[.*?\] \[.*?\] \[error\]\s*", "", l) for l in log
                  if (l.strip() and not l.startswith("[")) or ("] [error]" in l and "parent path" not in l)]
        raise Failure("Bambu Studio didn't slice it:\n  " + "\n  ".join(errors[-6:] or log[-3:]))
    return gcode


# --- G-code ------------------------------------------------------------------

def is_part(feature: str | None) -> bool:
    return feature is not None and not any(w in feature.lower() for w in NOT_PART)


def open_gcode(path: str):
    if zipfile.is_zipfile(path):
        z = zipfile.ZipFile(path)
        plates = sorted(n for n in z.namelist() if re.fullmatch(r"Metadata/plate_\d+\.gcode", n))
        if not plates:
            raise Failure(f"{path} has no G-code in it; slice the plate in the GUI and export that")
        if len(plates) > 1:
            warn(f"{path} has {len(plates)} sliced plates; using {plates[0]}")
        return io.TextIOWrapper(z.open(plates[0]), errors="replace")
    return open(path, errors="replace")


def integrate(path: str) -> dict:
    """Filament (mm) laid per feature with its first and second moments, plus
    the slicer's config comments and the part's extrusion bounding box.

    Each move's filament lies along its segment at the bead's mid-height (G-code
    Z is the top of the layer). Arcs are split into chords. Retracts and their
    restores don't move in XY and are skipped, so they cancel. Extrusion is
    relative or absolute only by M82/M83, as Bambu Studio and PrusaSlicer write
    it; G90/G91 only change XYZ."""
    feats, cfg = {}, {}
    lo, hi = [math.inf] * 3, [-math.inf] * 3
    x = y = z = e = 0.0
    abs_xyz = abs_e = True
    feature, height, reported = None, 0.0, None

    def lay(p0, p1, de):
        acc = feats.setdefault(feature, [0.0, [0.0] * 3, [[0.0] * 3 for _ in range(3)]])
        c = [(p0[0] + p1[0]) / 2, (p0[1] + p1[1]) / 2, (p0[2] + p1[2]) / 2 - height / 2]
        d = [p1[0] - p0[0], p1[1] - p0[1], p1[2] - p0[2]]
        acc[0] += de
        for i in range(3):
            acc[1][i] += de * c[i]
            for j in range(3):
                acc[2][i][j] += de * (c[i] * c[j] + d[i] * d[j] / 12)  # + the segment's own spread
        if is_part(feature):
            for i in range(3):
                lo[i] = min(lo[i], p0[i], p1[i])
                hi[i] = max(hi[i], p0[i], p1[i])

    with open_gcode(path) as f:
        for line in f:
            if line.startswith(";"):
                m = FEATURE.match(line) or HEIGHT.match(line)
                if m and m.re is FEATURE:
                    feature = m.group(1)
                elif m:
                    height = float(m.group(1))
                elif CONFIG.match(line):
                    cfg.setdefault(*CONFIG.match(line).groups())
                elif WEIGHT.match(line):
                    reported = float(WEIGHT.match(line).group(1))
                continue
            words = line.split(";", 1)[0].split()
            if not words:
                continue
            cmd, args = words[0], {}
            for w in words[1:]:
                try:
                    args[w[0]] = float(w[1:])
                except ValueError:
                    pass
            if cmd in ("M82", "M83"):
                abs_e = cmd == "M82"
            elif cmd in ("G90", "G91"):
                abs_xyz = cmd == "G90"
            elif cmd == "G92":
                x, y, z, e = (args.get(k, v) for k, v in zip("XYZE", (x, y, z, e)))
            elif cmd in ("G0", "G1", "G2", "G3"):
                nx, ny, nz = (args.get(k, v) if abs_xyz else v + args.get(k, 0.0)
                              for k, v in zip("XYZ", (x, y, z)))
                de = 0.0
                if "E" in args:
                    de = args["E"] - e if abs_e else args["E"]
                    e = args["E"] if abs_e else e + args["E"]
                if de > 0 and (nx, ny) != (x, y):
                    if cmd in ("G0", "G1"):
                        lay((x, y, z), (nx, ny, nz), de)
                    else:
                        cx, cy = x + args.get("I", 0.0), y + args.get("J", 0.0)
                        r = math.hypot(x - cx, y - cy)
                        a0 = math.atan2(y - cy, x - cx)
                        sweep = math.atan2(ny - cy, nx - cx) - a0
                        if cmd == "G2" and sweep >= 0:
                            sweep -= 2 * math.pi
                        elif cmd == "G3" and sweep <= 0:
                            sweep += 2 * math.pi
                        n = max(1, math.ceil(abs(sweep) / math.radians(10)), math.ceil(abs(sweep) * r))
                        p = (x, y, z)
                        for k in range(1, n + 1):
                            a = a0 + sweep * k / n
                            q = (cx + r * math.cos(a), cy + r * math.sin(a), z + (nz - z) * k / n)
                            lay(p, q, de / n)
                            p = q
                x, y, z = nx, ny, nz
    if not any(is_part(k) for k in feats):
        raise Failure(f"{path} has no part extrusions in it")
    return dict(features=feats, config=cfg, bbox=(lo, hi), reported_g=reported)


# --- mass properties ---------------------------------------------------------

def first(cfg: dict, *keys: str, default: str = "") -> str:
    """A config value, the first extruder's if it lists several."""
    for k in keys:
        v = re.split(r"[,;]", cfg.get(k, ""))[0].strip().strip('"')
        if v:
            return v
    return default


def properties(sliced: dict) -> dict:
    cfg = sliced["config"]
    d = float(first(cfg, "filament_diameter", default="1.75"))
    rho = float(first(cfg, "filament_density", default="0"))
    if not rho:
        raise Failure("the G-code doesn't give a filament density; set one with --set filament_density=1.27")
    g_per_mm = math.pi * d * d / 4 * rho / 1000
    E, S1, S2 = 0.0, [0.0] * 3, [[0.0] * 3 for _ in range(3)]
    for name, (de, s1, s2) in sliced["features"].items():
        if is_part(name):
            E += de
            for i in range(3):
                S1[i] += s1[i]
                for j in range(3):
                    S2[i][j] += s2[i][j]
    com = [s / E for s in S1]
    C = [[g_per_mm * (S2[i][j] - E * com[i] * com[j]) for j in range(3)] for i in range(3)]
    tr = C[0][0] + C[1][1] + C[2][2]
    return dict(mass_g=E * g_per_mm, com_mm=com, density=rho,
                inertia_g_mm2=[[(tr if i == j else 0.0) - C[i][j] for j in range(3)] for i in range(3)],
                features_g={k: v[0] * g_per_mm for k, v in sorted(sliced["features"].items(),
                                                                   key=lambda kv: -kv[1][0])},
                total_g=sum(v[0] for v in sliced["features"].values()) * g_per_mm)


def inverse3(a: list) -> tuple[list, float]:
    """Inverse and determinant of a 3x3 matrix."""
    det =(a[0][0] * (a[1][1] * a[2][2] - a[1][2] * a[2][1]) - a[0][1] * (a[1][0] * a[2][2] - a[1][2] * a[2][0])
           + a[0][2] * (a[1][0] * a[2][1] - a[1][1] * a[2][0]))
    return [[(a[(j + 1) % 3][(i + 1) % 3] * a[(j + 2) % 3][(i + 2) % 3]
              - a[(j + 1) % 3][(i + 2) % 3] * a[(j + 2) % 3][(i + 1) % 3]) / det for j in range(3)]
            for i in range(3)], det


def to_part_frame(props: dict, solid_c: list | None, shift: list, transform: list) -> dict:
    """Move results to the part frame: G-code coordinates lose the plate
    placement (`shift`), then print coordinates lose the print transform (part
    to print, affine)."""
    A = [row[:3] for row in transform[:3]]
    b = [row[3] for row in transform[:3]]
    Ai, det = inverse3(A)

    def point(p):
        q = [p[i] - b[i] for i in range(3)]
        return [sum(Ai[i][k] * q[k] for k in range(3)) for i in range(3)]

    out = dict(props, com_mm=point([props["com_mm"][i] - shift[i] for i in range(3)]), mirrored=det < 0)
    if solid_c is not None:
        out["solid_centroid_mm"] = point(solid_c)
    if all(abs(sum(A[k][i] * A[k][j] for k in range(3)) - (i == j)) < 1e-6 for i in range(3) for j in range(3)):
        I = props["inertia_g_mm2"]
        out["inertia_g_mm2"] = [[sum(Ai[i][k] * I[k][l] * Ai[j][l] for k in range(3) for l in range(3))
                                 for j in range(3)] for i in range(3)]
    else:
        del out["inertia_g_mm2"]
        warn("the print transform scales the part, so its inertia isn't reported")
    return out


# --- driver ------------------------------------------------------------------

def label(source: str, part: dict | None) -> str:
    return f"{source}:{part['line']} {part['name']}" if part else source


def measure(args, presets: dict | None, source: str, part: dict | None) -> dict:
    """Render (for .scad), place, slice and integrate one part."""
    workdir = tempfile.mkdtemp(prefix="print_mass-")
    try:
        transform, frame, solid_c, vol, shift = IDENT, "plate", None, None, [0.0, 0.0, 0.0]
        if source.lower().endswith((".scad", ".stl")):
            stl = os.path.join(workdir, "print.stl")
            frame = "STL"
            if source.lower().endswith(".scad"):
                transform, frame = render(source, part, args.D, stl), "part" if part else "model"
                if transform is None:
                    warn(f"{label(source, part)}: couldn't evaluate the print transform; "
                         "results are in print orientation")
                    transform, frame = IDENT, "print"
            tris = read_stl(stl if source.lower().endswith(".scad") else source)
            vol, solid_c, lo, hi = solid(tris)
            area = [[float(v) for v in p.split("x")] for p in presets["machine"]["printable_area"]]
            centre = [(min(p[i] for p in area) + max(p[i] for p in area)) / 2 for i in range(2)]
            shift = [centre[0] - (lo[0] + hi[0]) / 2, centre[1] - (lo[1] + hi[1]) / 2, -lo[2]]
            write_stl(stl, [tuple(tuple(v[i] + shift[i] for i in range(3)) for v in t) for t in tris])
            gcode = slice_stl(stl, presets, workdir)
        else:
            gcode = source
        sliced = integrate(gcode)
        props = properties(sliced)
        # Bambu writes G-code in nozzle coordinates, which sit this far from the plate's.
        offset = [float(v) for v in first(sliced["config"], "extruder_offset", default="0x0").split("x")]
        shift = [shift[0] - offset[0], shift[1] - offset[1], shift[2]]
        if vol is not None:
            glo, ghi = sliced["bbox"]
            miss = [(lo[i] + hi[i]) / 2 - ((glo[i] + ghi[i]) / 2 - shift[i]) for i in range(2)]
            if math.hypot(*miss) > 0.5:
                warn(f"{label(source, part)}: the sliced part sits {math.hypot(*miss):.1f} mm from where it "
                     "was placed; going by its bounding box instead")
                shift = [shift[0] - miss[0], shift[1] - miss[1], shift[2]]
            props["solid_mass_g"] = vol * props["density"] / 1000
        if sliced["reported_g"] and abs(sliced["reported_g"] - props["total_g"]) > 0.01 * sliced["reported_g"] + 0.02:
            warn(f"{label(source, part)}: the G-code says {sliced['reported_g']:.2f} g in all, but its moves "
                 f"add up to {props['total_g']:.2f} g")
        result = to_part_frame(props, solid_c, shift, transform)
        result.update(source=label(source, part), frame=frame, settings=settings(sliced["config"]),
                      print_transform=part["transform"] if part else "")
        if args.keep:
            keep = os.path.join(args.keep, re.sub(r"\W+", "_", f"{part['line']} {part['name']}") if part
                                else os.path.splitext(os.path.basename(source))[0])
            os.makedirs(keep, exist_ok=True)
            for f in glob.glob(os.path.join(workdir, "*.*")) + glob.glob(os.path.join(workdir, "sliced", "*")):
                shutil.move(f, os.path.join(keep, os.path.basename(f)))
        return result
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


def settings(cfg: dict) -> str:
    infill = first(cfg, "sparse_infill_density", "fill_density")
    pattern = first(cfg, "sparse_infill_pattern", "fill_pattern")
    walls = first(cfg, "wall_loops", "perimeters")
    top = first(cfg, "top_shell_layers", "top_solid_layers")
    bottom = first(cfg, "bottom_shell_layers", "bottom_solid_layers")
    return (f"{first(cfg, 'printer_settings_id', default='?')} / {first(cfg, 'print_settings_id', default='?')} "
            f"({infill} {pattern}, {walls} walls, {top} top / {bottom} bottom layers) / "
            f"{first(cfg, 'filament_settings_id', default='?')} ({first(cfg, 'filament_density')} g/cm3)")


def vec(v: list) -> str:
    return "[" + ", ".join(f"{x:7.2f}" for x in v) + "]"


def show(r: dict, verbose: bool) -> None:
    print(r["source"] + (f"   printed as {r['print_transform']}" if r["print_transform"] else ""))
    solid = (f"   solid model {r['solid_mass_g']:.2f} g, so {100 * r['mass_g'] / r['solid_mass_g']:.0f}% of it"
             if "solid_mass_g" in r else "")
    print(f"  mass     {r['mass_g']:8.2f} g{solid}")
    centroid = f"   solid centroid {vec(r['solid_centroid_mm'])}" if "solid_centroid_mm" in r else ""
    mirrored = ", mirrored back" if r["mirrored"] else ""
    print(f"  CoM      {vec(r['com_mm'])} mm in the {r['frame']} frame{mirrored}{centroid}")
    if "inertia_g_mm2" in r:
        I = r["inertia_g_mm2"]
        print(f"  inertia  Ixx {I[0][0]:.1f}  Iyy {I[1][1]:.1f}  Izz {I[2][2]:.1f}  "
              f"Ixy {I[0][1]:.1f}  Ixz {I[0][2]:.1f}  Iyz {I[1][2]:.1f} g*mm2 about the CoM")
    if verbose:
        for k, v in r["features_g"].items():
            print(f"    {v:8.3f} g  {k if k is not None else '(before the first feature)'}"
                  f"{'' if is_part(k) else '  (not counted)'}")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("input", help=".scad, .stl, .gcode or sliced .3mf")
    p.add_argument("--part", action="append", default=[],
                   help="print line to do, by part name (substring) or line number; repeatable")
    p.add_argument("--list", action="store_true", help="list the .scad file's print lines and stop")
    p.add_argument("-D", action="append", default=[], metavar="VAR=VAL", help="passed to openscad")
    p.add_argument("--infill", help="sparse infill density, e.g. 20%%")
    p.add_argument("--pattern", help="sparse infill pattern, e.g. gyroid")
    p.add_argument("--walls", type=int, help="wall loops")
    p.add_argument("--top", type=int, help="top shell layers")
    p.add_argument("--bottom", type=int, help="bottom shell layers")
    p.add_argument("--set", action="append", default=[], metavar="KEY=VALUE",
                   help="any other preset option, e.g. filament_density=1.25; repeatable")
    p.add_argument("--machine", help=f"default: {MACHINE}, or the printer --process is made for")
    p.add_argument("--process", default=PROCESS, help=f"default: {PROCESS}")
    p.add_argument("--filament", default=FILAMENT, help=f"default: {FILAMENT}")
    p.add_argument("--keep", metavar="DIR", help="keep each part's STL, presets and G-code here")
    p.add_argument("--jobs", type=int, default=4, help="parts done at once (default 4)")
    p.add_argument("--json", action="store_true", help="print the results as JSON")
    p.add_argument("-v", "--verbose", action="store_true", help="also list mass by feature")
    args = p.parse_args()

    try:
        source = args.input
        if not os.path.isfile(source):
            raise Failure(f"no file {source}")
        parts = [None]
        if source.lower().endswith(".scad"):
            found = print_lines(source)
            if args.list:
                for pl in found:
                    print(f"{pl['line']:5d}  {pl['name']:30s} {pl['transform']}")
                return
            if found:
                parts = [pl for pl in found if not args.part or any(
                    str(pl["line"]) == s or s.lower() in pl["name"].lower() for s in args.part)]
                if not parts:
                    raise Failure("no print line matches --part " + " ".join(args.part))
        presets = presets_for(args) if source.lower().endswith((".scad", ".stl")) else None
    except Failure as err:
        sys.exit(f"error: {err}")
    results = []
    with concurrent.futures.ThreadPoolExecutor(max(1, args.jobs)) as pool:
        for pl, job in [(pl, pool.submit(measure, args, presets, source, pl)) for pl in parts]:
            try:
                results.append(job.result())
            except Failure as err:
                print(f"{label(source, pl)}: {err}", file=sys.stderr)
    if args.json:
        print(json.dumps(results, indent=1))
    else:
        if results:
            print(results[0]["settings"] + "\n")
        for r in results:
            show(r, args.verbose)
    if len(results) < len(parts):
        sys.exit(1)


if __name__ == "__main__":
    main()
