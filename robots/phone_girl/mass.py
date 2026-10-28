#!/usr/bin/env python3
"""Mass and center of mass of the assembled phone_girl, as it will print.

Each printed part is sliced with tools/print_mass.py, so walls, infill and
print orientation count. Bought parts use the masses in BOUGHT. Where each
part sits comes from BOSL2's $transform, echoed from a temporary copy of
phone_girl.scad; the CAD itself isn't changed.

A printed part's orientation comes from its `// print` line in
phone_girl.scad, or from ORIENTATION when it doesn't have one yet. Options
this script doesn't know (--infill 20%, --walls 3, ...) go on to print_mass.py.

Units are g and mm, in the assembly's frame: +Z up, +Y back.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile

HERE = Path(__file__).resolve().parent
CAD = HERE / "phone_girl.scad"
PRINT_MASS = HERE.parent.parent / "tools/print_mass.py"
# Printed modules and the parameters that change their shape.
PRINTED = {
    "chest": [], "abdomen": [], "shoulder": ["l"], "pole": ["l"], "u_bracket": ["w"],
    "wedge": ["a", "w", "l"], "hip": [], "leg": [], "hand": [], "backpack_lid": [],
}
# Largest flat face down, for parts without a print line.
ORIENTATION = {
    "chest": "xrot(90)", "abdomen": "yrot(90)", "leg": "",
    "hand": "xrot(90)",  # on its side; standing on the horn disk, the fingers overhang
    "backpack_lid": "xrot(-90)",
}
# Bought parts: grams, and the CoM in the module's geometry frame.
BOUGHT = {
    "xl330": (18, [0, -7.5, -14.5]),  # ROBOTIS spec mass, CoM taken at the case centre
    "iphone_16_pro": (199, [4.725, 0.195, 0]),  # measured, see iphone_16_pro()
    "inr18650": (48, [0, 0, 32.5]),
}
ELECTRONICS_BOX = [0, 9, -10]  # centre of the placeholder box in electronics()
FOOT_TIP = [0, 14.2 + 2.4 + 100, -29.2 / 2 + 5]  # end of leg()'s foot: back(reach+wall+l) down(span/2-5)


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


def instrument(source: str) -> str:
    """Echo each part's name, shape parameters and geometry frame. The echo
    prefixes attachable()'s geometry child, so $transform includes the anchor."""
    edits = []
    for name in [*PRINTED, *BOUGHT, "electronics"]:
        match = re.search(r"\bmodule\s+" + name + r"\s*\(", source)
        if match is None:
            raise ValueError(f"CAD module {name} is missing")
        attach = source.index("attachable(", match.end())
        opening = source.index("{", closing(source, source.index("(", attach), "(", ")"))
        values = "[" + ",".join(PRINTED.get(name, [])) + "]"
        edits.append((opening + 1, f'\necho(MASS=["{name}",{values},$transform,'
                                   f'is_undef($mass_variant)?"":$mass_variant])'))
    for at, text in sorted(edits, reverse=True):
        source = source[:at] + text + source[at:]
    return source


def echoes(source: str) -> list:
    """Run OpenSCAD on source, beside the CAD so its includes resolve."""
    path = HERE / ".mass-frames.scad"
    with tempfile.TemporaryDirectory() as temporary:
        out = Path(temporary) / "frames.echo"
        try:
            path.write_text(source)
            result = subprocess.run(["openscad", "-o", str(out), str(path)], capture_output=True, text=True)
        finally:
            path.unlink(missing_ok=True)
        if result.returncode or "ERROR:" in result.stderr:
            raise RuntimeError(result.stderr)
        lines = out.read_text().splitlines()
    return [json.loads(line.removeprefix("ECHO: MASS = ")) for line in lines
            if line.startswith("ECHO: MASS = ")]


def orientation(source: str, name: str) -> str:
    for line in source.splitlines():
        match = re.match(r"\s*//\s*[!*%#\s]*(.*?)\b" + name + r"\s*\(.*//\s*print\b", line)
        if match:
            return match.group(1).strip()
    return ORIENTATION[name]


def call(name: str, params: dict) -> str:
    return name + "(" + ",".join(f"{k}={json.dumps(v)}" for k, v in params.items()) + ")"


def apply(m: list, p: list) -> list:
    return [sum(m[i][k] * p[k] for k in range(3)) + m[i][3] for i in range(3)]


def inverse(m: list) -> list:
    """Inverse of an affine 4x4."""
    a = [row[:3] for row in m[:3]]
    det = (a[0][0] * (a[1][1] * a[2][2] - a[1][2] * a[2][1]) - a[0][1] * (a[1][0] * a[2][2] - a[1][2] * a[2][0])
           + a[0][2] * (a[1][0] * a[2][1] - a[1][1] * a[2][0]))
    ai = [[(a[(j + 1) % 3][(i + 1) % 3] * a[(j + 2) % 3][(i + 2) % 3]
            - a[(j + 1) % 3][(i + 2) % 3] * a[(j + 2) % 3][(i + 1) % 3]) / det for j in range(3)]
          for i in range(3)]
    b = [-sum(ai[i][k] * m[k][3] for k in range(3)) for i in range(3)]
    return [ai[i] + [b[i]] for i in range(3)] + [[0, 0, 0, 1]]


def centre(items: list) -> tuple[float, list]:
    mass = sum(g for _, g, _ in items)
    return mass, [sum(g * c[i] for _, g, c in items) / mass for i in range(3)]


def vec(v: list) -> str:
    return "[" + ", ".join(f"{x:7.2f}" for x in v) + "]"


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--electronics", type=float, metavar="G",
                        help="mass of the electronics() placeholder box, left out by default")
    args, extra = parser.parse_known_args()
    source = CAD.read_text()
    instrumented = instrument(source)

    # BOSL2's diff() and tags can evaluate a part more than once, in the same place.
    frames, seen = [], set()
    for name, values, transform, _ in echoes(instrumented):
        key = json.dumps([name, values, transform])
        if key not in seen:
            seen.add(key)
            frames.append(dict(name=name, params=dict(zip(PRINTED.get(name, []), values)), transform=transform))
    variants = {}
    for frame in frames:
        if frame["name"] in PRINTED:
            frame["variant"] = frame["name"] + "".join(f"_{k}_{v}" for k, v in frame["params"].items())
            variants[frame["variant"]] = frame
    print(f"{len(frames)} parts, {len(variants)} printed variants to slice", file=sys.stderr)

    # print_mass reports in the frame the part is called in, which a default
    # anchor can move from the geometry frame the assembly echoes.
    calls = "\n".join(f'let($mass_variant="{key}") {call(f["name"], f["params"])};' for key, f in variants.items())
    called = {variant: transform for _, _, transform, variant in echoes(instrumented + "\n" + calls) if variant}

    wrapper = HERE / ".mass-parts.scad"
    lines = ["include <phone_girl.scad>"]
    lines += [f"// !{orientation(source, f['name'])} {call(f['name'], f['params'])}; // print {key}"
              for key, f in variants.items()]
    try:
        wrapper.write_text("\n".join(lines) + "\n")
        result = subprocess.run([sys.executable, str(PRINT_MASS), str(wrapper), "--json", *extra],
                                capture_output=True, text=True)
    finally:
        wrapper.unlink(missing_ok=True)
    if result.returncode:
        sys.exit(result.stdout + result.stderr)
    # print_mass fails rather than leave a part out, so results line up with variants.
    sliced = dict(zip(variants, json.loads(result.stdout)))

    rows, items, feet, box = {}, [], [], None
    for frame in frames:
        name, transform = frame["name"], frame["transform"]
        if name in BOUGHT:
            key, (grams, com) = name, BOUGHT[name]
        elif name in PRINTED:
            key = frame["variant"]
            grams = sliced[key]["mass_g"]
            com = apply(inverse(called[key]), sliced[key]["com_mm"])
            if name == "leg":
                feet.append(apply(transform, FOOT_TIP))
        else:
            box = apply(transform, ELECTRONICS_BOX)
            continue
        items.append((key, grams, apply(transform, com)))
        rows.setdefault(key, []).append(grams)
    if args.electronics:
        items.append(("electronics", args.electronics, box))
        rows["electronics"] = [args.electronics]

    print(json.loads(result.stdout)[0]["settings"] + "\n")
    print(f"{'part':34s} {'count':>5s} {'each g':>8s} {'total g':>8s}")
    for key, grams in rows.items():
        printed = f"   printed as {orientation(source, variants[key]['name'])}" if key in variants else ""
        print(f"{key:34s} {len(grams):5d} {grams[0]:8.2f} {sum(grams):8.2f}{printed}")
    mass, com = centre(items)
    printed_g = sum(g for key, g, _ in items if key in variants)
    print(f"{'total':34s} {'':5s} {'':8s} {mass:8.2f}   ({printed_g:.2f} g printed)\n")
    print(f"CoM               {vec(com)} mm in the CAD frame")
    if len(feet) == 2:
        mid = [(feet[0][i] + feet[1][i]) / 2 for i in range(3)]
        print(f"foot tips         {vec(feet[0])} and {vec(feet[1])}")
        print(f"CoM from between  {vec([com[i] - mid[i] for i in range(3)])} mm; z is height above the tips")
    if not args.electronics:
        shift = [10 * (box[i] - com[i]) / (mass + 10) for i in range(3)]
        print(f"\nThe electronics() box isn't counted; give its mass with --electronics G.\n"
              f"Its centre is {vec(box)} and each 10 g there moves the CoM by {vec(shift)}.")


if __name__ == "__main__":
    main()
