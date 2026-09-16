"""Render a continuous waypoint run to an H.264 MP4 using MuJoCo and FFmpeg."""
import argparse
from dataclasses import asdict
import json
from pathlib import Path
import shutil
import subprocess

import mujoco
import numpy as np
from PIL import Image, ImageDraw, ImageFont

from ubot_sim.contact_model import SURFACE_PRESETS, SURFACE_TERRAINS, SURFACE_OBSTACLES
from ubot_sim.env import baseline_action
from ubot_sim.waypoints import UBotWaypointsEnv


def font(size):
    for path in ("/System/Library/Fonts/Supplemental/Arial.ttf",
                 "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
                 "C:/Windows/Fonts/arial.ttf"):
        if Path(path).exists():
            return ImageFont.truetype(path, size)
    return ImageFont.load_default(size=size)


def add_geometry(scene, kind, position, size, color, end=None):
    if scene.ngeom >= scene.maxgeom:
        return
    geom = scene.geoms[scene.ngeom]
    mujoco.mjv_initGeom(geom, kind, np.array(size), np.array(position), np.eye(3).ravel(), np.array(color))
    if end is not None:
        mujoco.mjv_connector(geom, kind, size[0], np.array(position), np.array(end))
    scene.ngeom += 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("videos/u-bot-waypoints.mp4"))
    parser.add_argument("--route", type=Path, help="JSON list of [x, y] waypoint coordinates in metres")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--width", type=int, default=1920)
    parser.add_argument("--height", type=int, default=1080)
    parser.add_argument("--preview-only", action="store_true")
    parser.add_argument("--wheel-contact", choices=["smooth", "lugs"], default="lugs")
    parser.add_argument("--terrain", choices=["flat", "bumps"], default="flat")
    parser.add_argument("--surface", choices=sorted(SURFACE_PRESETS), help="Estimated surface preset (selects its own terrain geometry)")
    args = parser.parse_args()
    if args.surface and args.terrain != "flat":
        parser.error("--surface selects terrain geometry; omit --terrain or leave it at flat")
    if args.width < 640 or args.height < 360 or args.width % 2 or args.height % 2:
        parser.error("Use even dimensions, at least 640 x 360")
    if not shutil.which("ffmpeg") and not args.preview_only:
        parser.error("FFmpeg must be installed and on PATH")
    route = json.loads(args.route.read_text()) if args.route else None
    args.output.parent.mkdir(parents=True, exist_ok=True)
    env = UBotWaypointsEnv(waypoints=route, wheel_contact=args.wheel_contact, terrain=args.terrain, surface=args.surface)
    renderer = None
    encoder = None
    fps = 25  # exactly two 50 Hz policy steps per video frame, real-time playback
    try:
        obs, _ = env.reset(seed=args.seed, options={"yaw": 0})
        env.model.vis.global_.offwidth = args.width
        env.model.vis.global_.offheight = args.height
        # A neutral presentation floor; this changes appearance only.
        floor = env.model.geom("floor").id
        env.model.geom_matid[floor] = -1
        env.model.geom_rgba[floor] = [0.18, 0.23, 0.27, 1]
        goal_geom = env.model.body_geomadr[env.model.body("goal").id]
        env.model.geom_rgba[goal_geom] = [1, 0.65, 0.2, 0.22]
        renderer = mujoco.Renderer(env.model, height=args.height, width=args.width, max_geom=4000)
        camera = mujoco.MjvCamera()
        bounds = np.vstack(([0, 0], env.waypoints))
        center = (bounds.min(axis=0) + bounds.max(axis=0)) / 2
        camera.lookat[:] = [*center, -0.12]
        camera.distance = max(2.6, np.ptp(bounds, axis=0).max() * 2.0)
        camera.azimuth = 135
        camera.elevation = -52
        trail = [env.data.xpos[env.base, :2].copy()]
        scale = args.width / 1920
        title_font, text_font, small_font = (font(round(s * scale)) for s in (54, 28, 24))
        reached_times = []
        surface_obstacles = SURFACE_OBSTACLES.get(args.surface, ())
        obstacle_ids = {env.model.geom(f"surface_obstacle_{i}").id: i
                        for i in range(len(surface_obstacles))}
        obstacle_times = {}
        surface_title = args.surface.replace("_", " ").upper() if args.surface else None
        subtitle = "MuJoCo simulation  •  Baseline controller  •  Continuous run"
        if args.surface:
            contact = SURFACE_PRESETS[args.surface]
            subtitle = (f"Estimated surface • Grip {contact.sliding_friction:g} • "
                        f"Rolling {contact.rolling_friction:g} m (dim{contact.condim}) • Baseline controller")
        if args.surface == "rough_concrete":
            subtitle = "Estimated geometry • 0–4 mm bumps • 4 mm seams • 8 mm step • Baseline controller"

        def frame():
            renderer.update_scene(env.data, camera=camera)
            scene = renderer.scene
            points = np.vstack(([0, 0], env.waypoints))
            for start, end in zip(points[:-1], points[1:]):
                samples = np.linspace(start, end, max(2, int(np.linalg.norm(end - start) / 0.025) + 1))
                for a, b in zip(samples[:-1], samples[1:]):
                    za, zb = env.terrain_height(a), env.terrain_height(b)
                    if za is not None and zb is not None:
                        add_geometry(scene, mujoco.mjtGeom.mjGEOM_CAPSULE, [*a, za + 0.006],
                                     [0.004, 0, 0], [0.45, 0.55, 0.6, 1], [*b, zb + 0.006])
            for i, point in enumerate(env.waypoints):
                height = env.terrain_height(point)
                if height is None:
                    continue
                color = [0.2, 0.85, 0.65, 1] if i < env.waypoint_index else [0.55, 0.62, 0.66, 1]
                if i == env.waypoint_index:
                    color = [1, 0.65, 0.2, 1]
                add_geometry(scene, mujoco.mjtGeom.mjGEOM_CYLINDER, [*point, height + 0.009],
                             [0.045, 0.006, 0], color)
            for start, end in zip(trail[:-1], trail[1:]):
                za, zb = env.terrain_height(start), env.terrain_height(end)
                if za is None or zb is None:
                    continue
                add_geometry(scene, mujoco.mjtGeom.mjGEOM_CAPSULE, [*start, za + 0.014],
                             [0.006, 0, 0], [0.2, 0.85, 0.65, 1], [*end, zb + 0.014])
            image = Image.fromarray(renderer.render()).convert("RGBA")
            overlay = Image.new("RGBA", image.size)
            draw = ImageDraw.Draw(overlay)
            def rect(box, fill):
                draw.rectangle(tuple(round(x * scale) for x in box), fill=fill)
            def text(x, y, value, selected_font, fill="#eef4f5"):
                draw.text((round(x * scale), round(y * scale)), value, font=selected_font, fill=fill)
            h = args.height / scale
            rect((0, 0, 1920, 150), (12, 21, 29, 235))
            text(56, 28, "U-BOT  /  " + (f"{surface_title} SURFACE" if args.surface else "WAYPOINT NAVIGATION"), title_font)
            text(58, 98, subtitle, text_font, "#abc0cb")
            rect((0, h - 118, 1920, h), (12, 21, 29, 240))
            done = env.waypoint_index == len(env.waypoints)
            status = "ROUTE COMPLETE" if done else f"TARGET {env.waypoint_index + 1:02d} / {len(env.waypoints):02d}"
            text(56, h - 93, status, text_font, "#48ddb1")
            detail = (f"Features contacted {len(obstacle_times)}/{len(surface_obstacles)}"
                      if surface_obstacles else "4.043 kg model")
            text(56, h - 51, f"{env.data.time:05.1f} s   •   Real-time playback   •   {detail}", small_font, "#abc0cb")
            for i in range(len(env.waypoints)):
                x = 1130 + i * min(130, 680 / max(1, len(env.waypoints) - 1))
                y = h - 62
                color = "#48ddb1" if i < env.waypoint_index else "#536774"
                draw.ellipse(tuple(round(v * scale) for v in (x-19, y-19, x+19, y+19)), fill=color)
                text(x-7, y-14, str(i+1), small_font, "#10202a" if i < env.waypoint_index else "#ffffff")
            return Image.alpha_composite(image, overlay).convert("RGB")

        first = frame()
        first.save(args.output.with_suffix(".png"))
        if args.preview_only:
            return
        command = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "rawvideo",
                   "-pix_fmt", "rgb24", "-s", f"{args.width}x{args.height}", "-r", str(fps),
                   "-i", "-", "-an", "-c:v", "libx264", "-preset", "medium", "-crf", "18",
                   "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(args.output)]
        encoder = subprocess.Popen(command, stdin=subprocess.PIPE)
        frames = 0
        # Brief title hold, then continuous real-time simulation, then end hold.
        for _ in range(fps):
            encoder.stdin.write(first.tobytes())
            frames += 1
        info = {}
        for step in range(env.max_steps):
            obs, _, terminated, truncated, info = env.step(baseline_action(obs))
            for contact in env.data.contact:
                for geom_id in (contact.geom1, contact.geom2):
                    if geom_id in obstacle_ids:
                        obstacle_times.setdefault(obstacle_ids[geom_id], float(env.data.time))
            xy = env.data.xpos[env.base, :2].copy()
            if np.linalg.norm(xy - trail[-1]) > 0.025:
                trail.append(xy)
            if info["waypoint_reached"]:
                reached_times.append(float(env.data.time))
                print(f"Waypoint {env.waypoint_index}/{len(env.waypoints)} reached at {env.data.time:.2f}s", flush=True)
            if step % 2 == 1 or terminated or truncated:
                last = frame()
                encoder.stdin.write(last.tobytes())
                frames += 1
            if terminated or truncated:
                break
        for _ in range(2 * fps):
            encoder.stdin.write(last.tobytes())
            frames += 1
        encoder.stdin.close()
        result = encoder.wait()
        if result:
            raise RuntimeError(f"FFmpeg failed with exit code {result}")
        report = {"controller": "geometric baseline (not a trained policy)", "seed": args.seed,
                  "wheel_contact": args.wheel_contact, "terrain": SURFACE_TERRAINS.get(args.surface, args.terrain),
                  "surface_obstacles": [asdict(o) for o in surface_obstacles],
                  "obstacle_first_contact_seconds": obstacle_times,
                  "surface": args.surface,
                  "surface_contact": asdict(SURFACE_PRESETS[args.surface]) if args.surface else None,
                  "warning_count": sum(int(w.number) for w in env.data.warning),
                  "route_metres": env.waypoints.tolist(), "waypoint_times_seconds": reached_times,
                  "simulation_seconds": float(env.data.time), "video_seconds": frames / fps,
                  "fps": fps, "resolution": [args.width, args.height], **info}
        args.output.with_suffix(".json").write_text(json.dumps(report, indent=2) + "\n")
        last.save(args.output.with_name(args.output.stem + "-complete.png"))
        if not info.get("is_success"):
            raise RuntimeError(f"Route did not complete; diagnostic video saved: {info}")
        print(f"Saved {args.output} ({frames / fps:.2f}s)", flush=True)
    finally:
        if encoder is not None and encoder.poll() is None:
            if encoder.stdin and not encoder.stdin.closed:
                encoder.stdin.close()
            encoder.wait()
        if renderer is not None:
            renderer.close()
        env.close()


if __name__ == "__main__":
    main()
