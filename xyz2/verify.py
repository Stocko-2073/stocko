#!/usr/bin/env python3
"""Render printable meshes and test structural clearances using local OpenSCAD."""
import itertools
from pathlib import Path
import shutil
import struct
import subprocess
import tempfile

SOURCE = Path(__file__).resolve().with_name("xyz.scad")
PARTS = ("base", "y_frame", "tray", "column", "z_carriage", "tool_plate",
         "pen_adapter", "belt_clamp", "idler_spacer", "board_clip")


def run(output, *definitions):
    command = ["openscad", "--hardwarnings", "--backend", "Manifold",
               "--export-format", "binstl", "-o", str(output)]
    for definition in definitions:
        command.extend(("-D", definition))
    result = subprocess.run(command + [str(SOURCE)], capture_output=True, text=True)
    log = result.stdout + result.stderr
    if "WARNING:" in log or "ERROR:" in log:
        raise AssertionError(log)
    return result.returncode, log


def inspect_mesh(path):
    data = path.read_bytes()
    count = struct.unpack_from("<I", data, 80)[0]
    assert len(data) == 84 + 50 * count, "Not a binary STL"
    edges = {}
    adjacency = {}
    vertices = set()
    for index in range(count):
        triangle = struct.unpack_from("<12fH", data, 84 + index * 50)
        points = [tuple(round(v, 4) for v in triangle[start:start + 3])
                  for start in (3, 6, 9)]
        vertices.update(points)
        for a, b in zip(points, points[1:] + points[:1]):
            edge = tuple(sorted((a, b)))
            edges[edge] = edges.get(edge, 0) + 1
            adjacency.setdefault(a, set()).add(b)
            adjacency.setdefault(b, set()).add(a)
    assert vertices, "Empty printable part"
    assert all(count == 2 for count in edges.values()), "Mesh has open or non-manifold edges"
    todo = [next(iter(vertices))]
    reached = set()
    while todo:
        point = todo.pop()
        if point not in reached:
            reached.add(point)
            todo.extend(adjacency[point] - reached)
    assert reached == vertices, "Printable part has disconnected bodies"
    low = [min(v[axis] for v in vertices) for axis in range(3)]
    high = [max(v[axis] for v in vertices) for axis in range(3)]
    assert abs(low[2]) < 0.03, f"Part does not sit on print bed: z_min={low[2]}"
    return " × ".join(f"{b-a:.1f}" for a, b in zip(low, high))


def main():
    assert shutil.which("openscad"), "OpenSCAD CLI required"
    with tempfile.TemporaryDirectory(prefix="xyz2-verify-") as directory:
        target = Path(directory)
        for part in PARTS:
            output = target / f"{part}.stl"
            status, log = run(output, f'part="{part}"')
            assert status == 0, log
            print(f"PASS {part}: connected, closed, on bed; {inspect_mesh(output)} mm", flush=True)
        positions = [(0, 0, 15)] + list(itertools.product((-35, 35), (-45, 45), (0, 40)))
        for x, y, z in positions:
            status, log = run(target / "collision.stl", 'part="collision_check"',
                              f"tool_x={x}", f"tool_y={y}", f"tool_z={z}")
            assert status == 1 and "Current top level object is empty" in log, (
                f"Structural collision at ({x}, {y}, {z}):\n{log}")
            print(f"PASS structural clearance at ({x}, {y}, {z})", flush=True)
        for definition in ("tool_x=36", "tool_y=46", "tool_z=41", "y_travel=120"):
            command = ["openscad", "--hardwarnings", "-o", str(target / "invalid.csg"),
                       "-D", definition, str(SOURCE)]
            result = subprocess.run(command, capture_output=True, text=True)
            assert "ERROR: Assertion" in result.stderr, f"Invalid configuration accepted: {definition}"
        print("PASS out-of-range configurations rejected", flush=True)


if __name__ == "__main__":
    main()
