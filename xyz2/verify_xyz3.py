#!/usr/bin/env python3
"""Mesh and primary frame-clearance checks; not a full hardware collision audit."""
import itertools
from pathlib import Path
import subprocess
import tempfile
from verify import inspect_mesh
from verify_xyz2 import assert_clear

SOURCE = Path(__file__).with_name('xyz3.scad').resolve()

def render(path, *defs):
    args = ['openscad', '--hardwarnings', '--export-format', 'binstl', '-o', str(path)]
    for d in defs:
        args += ['-D', d]
    p = subprocess.run(args + [str(SOURCE)], capture_output=True, text=True)
    log = p.stdout + p.stderr
    assert 'WARNING:' not in log and 'ERROR:' not in log, log
    return p.returncode, log

with tempfile.TemporaryDirectory(prefix='xyz3-') as tmp:
    tmp = Path(tmp)
    for part in ['base', 'cross_carriage', 'arm', 'belt_clamp']:
        path = tmp / (part + '.stl')
        status, log = render(path, f'part="{part}"')
        assert status == 0, log
        print(part, inspect_mesh(path), flush=True)
    for x,y in [(0,0)] + list(itertools.product([-35,35],[-45,45])):
        path = tmp / 'collision.stl'
        status, log = render(path, 'part="collision_check"', f'tool_x={x}', f'tool_y={y}')
        assert_clear(path, status, log)
        print('Frame clearance:', x, y, flush=True)
    # Evaluate full assemblies at travel corners, including both lift endpoints.
    for x,y,z in itertools.product([-35,35],[-45,45],[0,5]):
        status, log = render(tmp/'pose.csg', f'tool_x={x}', f'tool_y={y}', f'pen_lift={z}')
        assert status == 0, log
    print('Eight travel/lift corner assemblies compile without warnings.')
