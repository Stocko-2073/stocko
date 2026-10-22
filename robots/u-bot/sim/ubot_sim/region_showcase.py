"""Record continuous transitions between three flat contact materials."""
import argparse
from dataclasses import asdict
import json
from pathlib import Path
import subprocess

import mujoco
import numpy as np
from PIL import Image, ImageDraw

from ubot_sim.contact_model import TerrainContact, TerrainRegion, SURFACE_PRESETS
from ubot_sim.env import baseline_action
from ubot_sim.record import add_geometry, font
from ubot_sim.waypoints import UBotWaypointsEnv

REGIONS = [
    TerrainRegion((0.7, 0), (0.2, 0.7), TerrainContact(
        sliding_friction=0.8, rolling_friction=0.002, condim=6,
        time_constant=0.02, damping_ratio=1.2)),
    TerrainRegion((1.4, 0), (0.2, 0.7), TerrainContact(
        sliding_friction=0.12, rolling_friction=0.0001, condim=4)),
]
NAMES = ["CONCRETE", "MORE ROLLING RESISTANCE", "SLIPPERY"]
COLORS = ["#889aa8", "#d7a65a", "#59b4de"]


def drive_materials(env):
    """Read material and effective settings from actual drive-wheel contacts."""
    contacts = {}
    for c in env.data.contact:
        for ground, wheel in [(c.geom1, c.geom2), (c.geom2, c.geom1)]:
            name = env.model.geom(wheel).name
            if env.model.geom_bodyid[ground] != 0 or not name.startswith(
                    ("left_tire", "right_tire", "left_lug", "right_lug")):
                continue
            surface = env.model.geom(ground).name
            material = int(surface.rsplit("_", 1)[1]) + 1 if surface.startswith("terrain_region_") else 0
            side = name.split("_", 1)[0]
            contacts[(side, material)] = {
                "side": side, "material": material, "dim": int(c.dim),
                "friction": c.friction.tolist(), "solref": c.solref.tolist(),
            }
    return [contacts[key] for key in sorted(contacts)]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("videos/surface-transitions-showcase.mp4"))
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    env = UBotWaypointsEnv(surface="concrete", regions=REGIONS,
                           waypoints=[[2, 0], [0, 0]], max_steps=1800)
    renderer = encoder = None
    title, label, small = font(30), font(21), font(18)
    camera = mujoco.MjvCamera()
    camera.lookat[:] = [0.95, 0, 0]
    camera.distance, camera.azimuth, camera.elevation = 2.0, 90, -58
    trail, samples, arrivals, transitions = [], [], [], []
    seen = [set(), set()]
    previous_materials = None
    try:
        obs, _ = env.reset(seed=0, options={"yaw": 0})
        for g in range(env.model.ngeom):
            if env.model.geom_bodyid[g] == 0:
                name = env.model.geom(g).name
                material = int(name.rsplit("_", 1)[1]) + 1 if name.startswith("terrain_region_") else 0
                env.model.geom_matid[g] = -1
                env.model.geom_rgba[g] = ([0.24, 0.29, 0.32, 1], [0.55, 0.38, 0.16, 1],
                                          [0.1, 0.36, 0.5, 1])[material]
        env.model.vis.global_.offwidth = 1280
        env.model.vis.global_.offheight = 440
        renderer = mujoco.Renderer(env.model, height=440, width=1280, max_geom=2000)

        def frame():
            canvas = Image.new("RGB", (1280, 720), "#0c151d")
            draw = ImageDraw.Draw(canvas)
            draw.text((26, 17), "U-BOT / CONTINUOUS SURFACE TRANSITIONS", font=title, fill="#eef4f5")
            draw.text((26, 61), "One episode, out and back / flat material regions / estimated contacts / real-time playback",
                      font=small, fill="#abc0cb")
            renderer.update_scene(env.data, camera=camera)
            for a, b in zip(trail[:-1], trail[1:]):
                add_geometry(renderer.scene, mujoco.mjtGeom.mjGEOM_CAPSULE,
                             [*a, 0.014], [0.005, 0, 0], [0.25, 0.95, 0.72, 1], [*b, 0.014])
            for point in env.waypoints:
                add_geometry(renderer.scene, mujoco.mjtGeom.mjGEOM_CYLINDER,
                             [*point, 0.006], [0.055, 0.004, 0], [0.25, 0.95, 0.72, 1])
            canvas.paste(Image.fromarray(renderer.render()), (0, 91))
            active = {c["material"] for c in drive_materials(env)}
            settings = [SURFACE_PRESETS["concrete"], *(r.contact for r in REGIONS)]
            for i, contact in enumerate(settings):
                x = 18 + i * 422
                draw.rectangle((x, 542, x + 402, 671), fill="#162833", outline=COLORS[i], width=3 if i in active else 1)
                draw.text((x + 14, 552), NAMES[i], font=label, fill=COLORS[i])
                draw.text((x + 14, 582), f"Grip {contact.sliding_friction:g} / " + (
                    f"rolling {contact.rolling_friction:g} m" if contact.condim == 6 else "rolling inactive (dim4)"),
                          font=small, fill="#eef4f5")
                draw.text((x + 14, 609), f"Contact time {contact.time_constant:g} s / damping {contact.damping_ratio:g}",
                          font=small, fill="#abc0cb")
                draw.text((x + 14, 638), "WHEEL CONTACT NOW" if i in active else "", font=small, fill="#48ddb1")
            status = "ROUTE COMPLETE" if env.waypoint_index == 2 else ("OUTBOUND" if env.waypoint_index == 0 else "RETURN")
            speed = np.linalg.norm(env._state()[1][3:5])
            draw.text((26, 691), f"{env.data.time:04.1f} s / {status} / stops {env.waypoint_index}/2 / speed {speed:.2f} m/s",
                      font=small, fill="#48ddb1")
            return canvas

        encoder = subprocess.Popen(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "rawvideo",
                                    "-pix_fmt", "rgb24", "-s", "1280x720", "-r", "25", "-i", "-", "-an",
                                    "-c:v", "libx264", "-crf", "18", "-pix_fmt", "yuv420p", "-movflags",
                                    "+faststart", str(args.output)], stdin=subprocess.PIPE)
        first = frame()
        first.save(args.output.with_suffix(".png"))
        frames = 0
        for _ in range(25):
            encoder.stdin.write(first.tobytes())
            frames += 1
        for step in range(env.max_steps):
            leg = env.waypoint_index
            obs, _, terminated, truncated, info = env.step(baseline_action(obs))
            if info["failed"] or truncated:
                raise RuntimeError(f"Route failed: {info}")
            contacts = drive_materials(env)
            active = sorted({c["material"] for c in contacts})
            seen[leg].update(active)
            if active != previous_materials:
                transitions.append({"seconds": float(env.data.time), "leg": leg, "materials": active})
                previous_materials = active
            xy = env.data.xpos[env.base, :2].copy()
            if not trail or np.linalg.norm(xy - trail[-1]) > 0.02:
                trail.append(xy)
            if info["waypoint_reached"]:
                arrivals.append(float(env.data.time))
            if step % 2 == 1 or terminated:
                last = frame()
                encoder.stdin.write(last.tobytes())
                frames += 1
            if step % 10 == 9 or terminated:
                samples.append({"seconds": float(env.data.time), "xy_metres": xy.tolist(),
                                "contacts": contacts, "speed_mps": float(np.linalg.norm(env._state()[1][3:5]))})
            if (step + 1) % 250 == 0:
                print(f"Rendered {(step + 1) * 0.02:.0f} seconds", flush=True)
            if terminated:
                break
        for _ in range(50):
            encoder.stdin.write(last.tobytes())
            frames += 1
        encoder.stdin.close()
        if encoder.wait():
            raise RuntimeError("FFmpeg failed")
        last.save(args.output.with_name(args.output.stem + "-complete.png"))
        report = {"seed": 0, "route": env.waypoints.tolist(), "regions": [asdict(r) for r in REGIONS],
                  "base_contact": asdict(SURFACE_PRESETS["concrete"]), "wheel_contact": "lugs",
                  "physics_timestep": 0.002, "fps": 25, "resolution": [1280, 720],
                  "video_seconds": frames / 25, "completed": info["is_success"],
                  "arrivals_seconds": arrivals, "materials_seen_by_leg": [sorted(s) for s in seen],
                  "transitions": transitions, "samples": samples,
                  "warning_count": sum(int(w.number) for w in env.data.warning)}
        args.output.with_suffix(".json").write_text(json.dumps(report, indent=2) + "\n")
        if not info["is_success"] or seen != [{0, 1, 2}, {0, 1, 2}] or report["warning_count"]:
            raise RuntimeError("Showcase requires a completed route, all materials on both legs, and no warnings")
        print(f"Saved {args.output} ({frames / 25:.2f}s)", flush=True)
    finally:
        if encoder is not None and encoder.poll() is None:
            if not encoder.stdin.closed:
                encoder.stdin.close()
            encoder.wait()
        if renderer is not None:
            renderer.close()
        env.close()


if __name__ == "__main__":
    main()
