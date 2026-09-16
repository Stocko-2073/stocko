"""Render the evaluated five-waypoint route side by side on current presets."""
import argparse
import json
from pathlib import Path
import subprocess

import mujoco
import numpy as np
from PIL import Image, ImageDraw

from ubot_sim.record import add_geometry, font
from ubot_sim.surface_evaluation import ROUTES, RouteMetrics
from ubot_sim.waypoints import UBotWaypointsEnv

SURFACES = ("concrete", "rough_concrete")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("videos/surface-evaluation-showcase.mp4"))
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    envs, renderers, metrics = [], [], []
    trails = [[], []]
    samples = []
    encoder = None
    title, label, small = font(30), font(23), font(18)
    camera = mujoco.MjvCamera()
    camera.lookat[:] = [0.25, 0.5, 0]
    camera.distance, camera.azimuth, camera.elevation = 2.6, 105, -60
    try:
        for surface in SURFACES:
            env = UBotWaypointsEnv(surface=surface, waypoints=ROUTES["five_waypoints"], max_steps=2250)
            envs.append(env)
            obs, _ = env.reset(seed=0, options={"yaw": 0})
            metrics.append(RouteMetrics(env, obs))
            env.model.vis.global_.offwidth = 640
            env.model.vis.global_.offheight = 420
            renderers.append(mujoco.Renderer(env.model, height=420, width=640, max_geom=2000))

        def value(number, scale=1):
            return "—" if number is None else f"{number * scale:.1f}"

        def frame():
            canvas = Image.new("RGB", (1280, 720), "#0c151d")
            draw = ImageDraw.Draw(canvas)
            draw.text((24, 17), "U-BOT / SURFACE ROUTE EVALUATION", font=title, fill="#eef4f5")
            draw.text((24, 61), "Same five goals + seed 0 / baseline controller / lugged wheels / 2 ms physics / real-time playback",
                      font=small, fill="#abc0cb")
            for i, (env, renderer, measurement) in enumerate(zip(envs, renderers, metrics)):
                x = i * 640
                draw.text((x + 24, 103), SURFACES[i].replace("_", " ").upper(), font=label, fill="#48ddb1")
                renderer.update_scene(env.data, camera=camera)
                for j, point in enumerate(env.waypoints):
                    color = [0.2, 0.9, 0.65, 1] if j < env.waypoint_index else [1, 0.7, 0.25, 1]
                    add_geometry(renderer.scene, mujoco.mjtGeom.mjGEOM_CYLINDER,
                                 [*point, env.terrain_height(point) + 0.008], [0.045, 0.005, 0], color)
                for a, b in zip(trails[i][:-1], trails[i][1:]):
                    add_geometry(renderer.scene, mujoco.mjtGeom.mjGEOM_CAPSULE,
                                 [*a, env.terrain_height(a) + 0.015], [0.005, 0, 0],
                                 [0.2, 0.9, 0.65, 1], [*b, env.terrain_height(b) + 0.015])
                canvas.paste(Image.fromarray(renderer.render()), (x, 139))
                report = measurement.report()
                status = "COMPLETE / holding" if report["is_success"] else f"Target {env.waypoint_index + 1}/5"
                draw.text((x + 24, 570), f"{env.data.time:04.1f} s / {status}", font=label, fill="#eef4f5")
                draw.text((x + 24, 607), f"Tracking RMS {value(report['tracking_rms_m'], 1000)} mm   |   "
                          f"Contact slip RMS {value(report['slip_rms_mps'], 1000)} mm/s", font=small, fill="#abc0cb")
                stop = report["stops"][-1] if report["stops"] else None
                stop_text = (f"Last stop: {value(stop['travel_after_command_m'], 1000)} mm after zero target / "
                             f"goal error {value(stop['goal_error_m'], 1000)} mm" if stop else "Last stop: awaiting first arrival")
                draw.text((x + 24, 638), stop_text, font=small, fill="#abc0cb")
            draw.line((640, 96, 640, 675), fill="#536774", width=2)
            draw.text((24, 692), "Estimated presets / contact slip includes turning scrub / full report: 48 runs across routes, seeds and timesteps",
                      font=small, fill="#abc0cb")
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
        for step in range(2250):
            for i, measurement in enumerate(metrics):
                if measurement.done:
                    continue
                info = measurement.step()
                if measurement.done and not info["is_success"]:
                    raise RuntimeError(f"{SURFACES[i]} did not finish: {measurement.report()}")
                xy = envs[i].data.xpos[envs[i].base, :2].copy()
                if not trails[i] or np.linalg.norm(xy - trails[i][-1]) > 0.02:
                    trails[i].append(xy)
            done = all(m.done for m in metrics)
            if step % 2 == 1 or done:
                last = frame()
                encoder.stdin.write(last.tobytes())
                frames += 1
            if step % 10 == 9 or done:
                samples.append({"playback_seconds": (step + 1) * 0.02,
                                "panels": [{"xy": e.data.xpos[e.base, :2].tolist(),
                                            "simulation_seconds": float(e.data.time),
                                            "waypoints_reached": e.waypoint_index} for e in envs]})
            if (step + 1) % 250 == 0:
                print(f"Rendered {(step + 1) * 0.02:.0f} seconds", flush=True)
            if done:
                break
        for _ in range(50):
            encoder.stdin.write(last.tobytes())
            frames += 1
        encoder.stdin.close()
        if encoder.wait():
            raise RuntimeError("FFmpeg failed")
        last.save(args.output.with_name(args.output.stem + "-complete.png"))
        report = {"route": ROUTES["five_waypoints"], "seed": 0, "wheel_contact": "lugs",
                  "physics_timestep": 0.002, "fps": 25, "resolution": [1280, 720], "video_seconds": frames / 25,
                  "panels": {surface: m.report() for surface, m in zip(SURFACES, metrics)}, "samples": samples}
        args.output.with_suffix(".json").write_text(json.dumps(report, indent=2) + "\n")
        if not all(m.info["is_success"] for m in metrics) or any(m.report()["warning_count"] for m in metrics):
            raise RuntimeError("Showcase requires both routes complete with no solver warnings")
        print(f"Saved {args.output} ({frames / 25:.2f}s)", flush=True)
    finally:
        if encoder is not None and encoder.poll() is None:
            if not encoder.stdin.closed:
                encoder.stdin.close()
            encoder.wait()
        for renderer in renderers:
            renderer.close()
        for env in envs:
            env.close()


if __name__ == "__main__":
    main()
