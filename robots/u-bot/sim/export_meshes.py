"""Export visual-only meshes from the current CAD; requires OpenSCAD and BOSL2."""
import argparse
import hashlib
import json
import re
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parent
CAD = ROOT.parent / "u-bot.scad"
ASSETS = ROOT / "ubot_sim" / "assets"
PARTS = {
    "chassis": '''union() {
        body() { nop(); nop(); nop(); nop(); nop(); nop(); }
        xflip_copy() fwd($slop) left(128) leg() {
            motor(); drive_gear(); nop();
            axle_mount() { nop(); as5600_mount() { nop(); as5600_mount_cap() nop(); } nop(); }
            leg_cap() nop();
        }
        up(35+$slop) back(79) body_lid();
        back(79+$slop) down(32+$slop) back(6) body_tray();
    }''',
    # Place the origin at the tread midplane, not the gear/axle datum.
    "wheel_right": "right(20) wheel() nop();",
    "wheel_left": "xflip() right(20) wheel() nop();",
    # Caster pivot at roller axle height; initial CAD orientation is 180 degrees.
    "caster_fork": '''zrot(180) back(19) union() {
        caster_leg_bottom(caster_leg_len) { nop(); nop(); nop(); nop(); }
        caster_leg_top(caster_leg_len);
        caster_cap_right() nop(); caster_cap_left() nop();
    }''',
    # Roller origin midway through its 18.3 mm width.
    "caster_roller": "left(9.15) caster_side() nop();",
}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--openscad", default="openscad")
    args = parser.parse_args()
    ASSETS.mkdir(parents=True, exist_ok=True)
    for name, shape in PARTS.items():
        # Evaluate a temporary copy without the top-level assembly. The original
        # has preview-only globals; even ! evaluates that assembly in OpenSCAD.
        source = CAD.read_text()
        if source.count("\nrobot();") != 1:
            raise RuntimeError("Expected exactly one top-level robot(); in CAD")
        source = source.replace("\nrobot();", "\n// Assembly omitted for part export")
        source = re.sub(r"(include|use) <([^>]+)>",
                        lambda m: m[0] if m[2].startswith("BOSL2/") else
                        f"{m[1]} <{(CAD.parent / m[2]).resolve().as_posix()}>", source)
        source += f'\n!zrot(90) {{ {shape} }}\n'
        with tempfile.TemporaryDirectory(prefix="ubot-cad-") as tmp:
            wrapper = Path(tmp) / "export.scad"
            wrapper.write_text(source)
            result = subprocess.run(
                [args.openscad, "--backend=Manifold", "--export-format", "binstl",
                 "-D", "$fa=4", "-D", "$fs=1", "-o", str(ASSETS / f"{name}.stl"), str(wrapper)],
                text=True, capture_output=True,
            )
            if result.returncode or "WARNING:" in result.stderr or "ERROR:" in result.stderr:
                raise RuntimeError(f"{name}:\n{result.stderr}")
            print(f"Exported {name}", flush=True)
    inputs = [CAD, *sorted((ROOT.parent / "modules").rglob("*.scad")),
              *sorted((ROOT.parent.parent / "lib").glob("*.scad"))]
    (ASSETS / "cad_manifest.json").write_text(json.dumps({
        "units": "millimetres; MJCF mesh scale is 0.001",
        "frame": "sim (x,y,z) = CAD (-y,x,z)",
        "inputs_sha256": {str(p.relative_to(ROOT.parent.parent)): hashlib.sha256(p.read_bytes()).hexdigest() for p in inputs},
        "mesh_sha256": {f"{n}.stl": hashlib.sha256((ASSETS / f"{n}.stl").read_bytes()).hexdigest() for n in PARTS},
    }, indent=2) + "\n")


if __name__ == "__main__":
    main()
