#!/usr/bin/env python3
"""Geometric checks for xyz2.scad; does not simulate scribing or spring forces."""
import itertools
import math
from pathlib import Path
import struct
import subprocess
import tempfile

from verify import inspect_mesh

SOURCE = Path(__file__).resolve().with_name("xyz2.scad")
PARTS = ("base", "bridge", "saddle", "cartridge", "plunger", "lift_arm",
         "tool_blank", "belt_cap", "idler_spacer", "board_clip", "backing")


def render(path, *definitions):
    command = ["openscad", "--hardwarnings", "--backend", "Manifold",
               "--export-format", "binstl", "-o", str(path)]
    for definition in definitions:
        command.extend(("-D", definition))
    result = subprocess.run(command + [str(SOURCE)], capture_output=True, text=True)
    log = result.stdout + result.stderr
    assert "WARNING:" not in log and "ERROR:" not in log, log
    return result.returncode, log


def assert_clear(path, status, log):
    # Manifold sometimes exports coincident mounting faces as zero-volume STL
    # sheets. Accept exact contact, but reject any positive-volume penetration.
    if status == 1 and "Current top level object is empty" in log:
        return
    assert status == 0, log
    data = path.read_bytes()
    count = struct.unpack_from("<I", data, 80)[0]
    assert len(data) == 84 + 50 * count, "Expected binary collision STL"
    terms = []
    for i in range(count):
        values = struct.unpack_from("<12fH", data, 84 + 50 * i)
        a, b, c = values[3:6], values[6:9], values[9:12]
        terms.append(sum(a[j] * (b[(j+1)%3] * c[(j+2)%3]
                                - b[(j+2)%3] * c[(j+1)%3]) for j in range(3)) / 6)
    volume = abs(math.fsum(terms))
    assert volume < 1e-5, f"Collision volume {volume:.6f} mm³:\n{log}"


def main():
    with tempfile.TemporaryDirectory(prefix="xyz2-scriber-") as directory:
        target = Path(directory)
        for name in PARTS:
            path = target / f"{name}.stl"
            status, log = render(path, f'part="{name}"')
            assert status == 0, log
            size = inspect_mesh(path)
            print(f"PASS {name}: connected, closed, on bed; {size} mm", flush=True)
        # Corners and intermediate lift positions exercise the rotary lift linkage.
        poses = [(0, 0, z) for z in (0, 1, 2.5, 4, 5)]
        poses += list(itertools.product((-35, 35), (-45, 45), (0, 5)))
        for x, y, z in poses:
            status, log = render(target / "collision.stl", 'part="collision_check"',
                                 f"tool_x={x}", f"tool_y={y}", f"pen_lift={z}")
            assert_clear(target / "collision.stl", status, log)
            print(f"PASS clearance ({x}, {y}, lift={z})", flush=True)
        for preload in (0.5, 4):
            for lift in (0, 5):
                status, log = render(target / "preload.stl", 'part="collision_check"',
                                     f"spring_preload={preload}", f"pen_lift={lift}")
                assert_clear(target / "preload.stl", status, log)
                print(f"PASS preload={preload}, lift={lift}", flush=True)
        status, log = render(target / "access.stl", 'part="assembly_access_check"')
        assert_clear(target / "access.stl", status, log)
        print("PASS cartridge/collar/servo-arm insertion samples and saddle driver access", flush=True)
        # Hardware must clear its own print as well as neighbouring parts. Check
        # intermediate poses at both preload limits, where the old suite only
        # checked endpoints. This also checks head-to-head screw interference.
        for preload, lift in itertools.product((0.5, 4), (1, 2, 3, 4)):
            status, log = render(target / "head.stl", 'part="head_assembly_check"',
                                 f"spring_preload={preload}", f"pen_lift={lift}")
            assert_clear(target / "head.stl", status, log)
            print(f"PASS head fasteners/access preload={preload}, lift={lift}", flush=True)
        for definition in ("tool_x=36", "tool_y=46", "pen_lift=6", "pen_d=12"):
            result = subprocess.run(["openscad", "--hardwarnings", "-o", str(target / "invalid.csg"),
                                     "-D", definition, str(SOURCE)], capture_output=True, text=True)
            assert "ERROR: Assertion" in result.stderr, f"Accepted invalid setting: {definition}"
        print("PASS invalid configurations rejected", flush=True)


if __name__ == "__main__":
    main()
