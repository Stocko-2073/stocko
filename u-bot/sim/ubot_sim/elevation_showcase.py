"""Record the same continuous route at ground level and on a 30 cm platform."""
import argparse
import json
from pathlib import Path
import subprocess

import mujoco
import numpy as np
from PIL import Image, ImageDraw

from ubot_sim.contact_model import TerrainObstacle
from ubot_sim.env import baseline_action
from ubot_sim.record import font
from ubot_sim.waypoints import UBotWaypointsEnv


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("videos/elevation-showcase.mp4"))
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    envs, renderers, observations, samples = [], [], [], []
    encoder = None
    title, label, small = font(30), font(24), font(19)
    done = [False, False]
    arrivals = [[], []]
    camera = mujoco.MjvCamera()
    camera.lookat[:] = [0.15, 0, 0.08]
    camera.distance, camera.azimuth, camera.elevation = 2.4, 115, -27
    try:
        for height in (0, 0.3):
            obstacles = [TerrainObstacle("edge", (0, 0, height / 2), (1.1, 0.7, height / 2))] if height else []
            env = UBotWaypointsEnv(waypoints=[[0.5, 0], [0, 0]], obstacles=obstacles)
            envs.append(env)
            obs, _ = env.reset(seed=0, options={"yaw": 0})
            observations.append(obs)
            env.model.vis.global_.offwidth = 640
            env.model.vis.global_.offheight = 460
            renderers.append(mujoco.Renderer(env.model, height=460, width=640))

        def frame():
            canvas = Image.new("RGB", (1280, 720), "#0c151d")
            draw = ImageDraw.Draw(canvas)
            draw.text((26, 20), "U-BOT / TERRAIN-AWARE ELEVATION", font=title, fill="#eef4f5")
            draw.text((26, 66), "Automatic spawn height  /  goals on the surface  /  clearance relative to local terrain",
                      font=small, fill="#abc0cb")
            for i, (env, renderer) in enumerate(zip(envs, renderers)):
                x = i * 640
                draw.text((x + 24, 114), "GROUND LEVEL" if i == 0 else "RAISED PLATFORM  +30 cm", font=label, fill="#48ddb1")
                renderer.update_scene(env.data, camera=camera)
                canvas.paste(Image.fromarray(renderer.render()), (x, 151))
                z = env.data.xpos[env.base, 2]
                ground = env.terrain_height(env.data.xpos[env.base, :2])
                draw.text((x + 24, 620), f"Body Z {z:.3f} m  |  clearance {z - ground:.3f} m", font=small, fill="#eef4f5")
                draw.text((x + 24, 651), f"Goal Z {env.data.mocap_pos[0, 2]:.3f} m  |  stops {env.waypoint_index}/2",
                          font=small, fill="#abc0cb")
            draw.line((640, 108, 640, 684), fill="#536774", width=2)
            status = "BOTH ROUTES COMPLETE" if all(done) else "Same route, seed and controller / real-time playback"
            draw.text((26, 690), status, font=small, fill="#48ddb1")
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
        for step in range(1500):
            for i, env in enumerate(envs):
                if done[i]:
                    continue
                observations[i], _, terminated, truncated, info = env.step(baseline_action(observations[i]))
                if info["waypoint_reached"]:
                    arrivals[i].append(float(env.data.time))
                if info["failed"] or truncated:
                    raise RuntimeError(f"Route {i} failed: {info}")
                done[i] = terminated
            if step % 2 == 1 or all(done):
                last = frame()
                encoder.stdin.write(last.tobytes())
                frames += 1
                samples.append({"seconds": (step + 1) * 0.02,
                                "body_z": [float(e.data.xpos[e.base, 2]) for e in envs],
                                "goal_z": [float(e.data.mocap_pos[0, 2]) for e in envs]})
            if (step + 1) % 250 == 0:
                print(f"Rendered {(step + 1) * 0.02:.0f} seconds", flush=True)
            if all(done):
                break
        if not all(done):
            raise RuntimeError("Routes did not finish")
        for _ in range(50):
            encoder.stdin.write(last.tobytes())
            frames += 1
        encoder.stdin.close()
        if encoder.wait():
            raise RuntimeError("FFmpeg failed")
        last.save(args.output.with_name(args.output.stem + "-complete.png"))
        report = {"seed": 0, "route": [[0.5, 0], [0, 0]], "platform_height_metres": 0.3,
                  "wheel_contact": "lugs", "physics_timestep": 0.002,
                  "fps": 25, "resolution": [1280, 720], "video_seconds": frames / 25,
                  "completed": done, "arrivals_seconds": arrivals, "samples": samples,
                  "warning_counts": [sum(int(w.number) for w in e.data.warning) for e in envs]}
        args.output.with_suffix(".json").write_text(json.dumps(report, indent=2) + "\n")
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
