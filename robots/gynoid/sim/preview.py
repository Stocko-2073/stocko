"""Render the initial simulation pose to a PNG without extra image dependencies."""

import argparse
from pathlib import Path
import struct
import zlib

import mujoco
import numpy as np

from sim.env import GynoidBalanceEnv


def write_png(path, pixels):
    def chunk(kind, data):
        return (struct.pack("!I", len(data)) + kind + data
                + struct.pack("!I", zlib.crc32(kind + data) & 0xFFFFFFFF))
    height, width, _ = pixels.shape
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack("!2I5B", width, height, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(b"".join(b"\x00" + row.tobytes() for row in pixels)))
        + chunk(b"IEND", b""))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("sim/runs/preview.png"))
    parser.add_argument("--stance", choices=["cad", "centered"], default="centered")
    parser.add_argument("--task", choices=["balance", "planted"], default="balance")
    parser.add_argument("--com", action="store_true", help="Show total CoM and its ground projection in yellow")
    args = parser.parse_args()
    if args.task == "planted":
        from sim.planted import GynoidPlantedEnv
        env = GynoidPlantedEnv(render_mode="rgb_array", reset_noise=0)
    else:
        env = GynoidBalanceEnv(render_mode="rgb_array", reset_noise=0, stance=args.stance)
    try:
        env.reset(seed=0)
        pixels = env.render()
        if args.com:
            scene = env.renderer.scene
            center = env.data.subtree_com[env.pelvis].copy()
            projection = np.r_[center[:2], 0.001]
            def marker(position, radius, color):
                geom = scene.geoms[scene.ngeom]
                mujoco.mjv_initGeom(geom, mujoco.mjtGeom.mjGEOM_SPHERE, np.full(3, radius),
                                  position, np.eye(3).ravel(), np.array(color, dtype=np.float32))
                scene.ngeom += 1
                return geom
            marker(center, 0.006, [1, 0.85, 0.05, 1])
            marker(projection, 0.004, [1, 0.85, 0.05, 1])
            line = marker(center, 0.001, [1, 0.85, 0.05, 0.8])
            mujoco.mjv_connector(line, mujoco.mjtGeom.mjGEOM_LINE, 2, center, projection)
            for foot in env.feet:
                marker(env.data.site_xpos[foot], 0.0035, [0.2, 0.9, 0.4, 1])
            pixels = env.renderer.render()
        write_png(args.output, pixels)
        print(args.output)
    finally:
        env.close()


if __name__ == "__main__":
    main()
