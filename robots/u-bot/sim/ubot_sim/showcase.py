"""Record a synchronized grip comparison with identical start/stop/turn commands."""
import argparse
from dataclasses import asdict
import json
from pathlib import Path
import subprocess

import mujoco
import numpy as np
from PIL import Image, ImageDraw

from ubot_sim.contact_model import TerrainContact
from ubot_sim.env import UBotNavigationEnv, MAX_WHEEL_SPEED
from ubot_sim.record import add_geometry, font

PHASES = [(3, "ACCELERATE", [0.65, 0.65]), (5, "BRAKE", [0, 0]),
          (8, "TURN", [-0.4, 0.4]), (10, "BRAKE", [0, 0]),
          (13, "REVERSE", [-0.5, -0.5]), (16, "BRAKE", [0, 0])]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("videos/terrain-contact-showcase.mp4"))
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    surfaces = [TerrainContact(), TerrainContact(sliding_friction=0.08)]
    envs, renderers, trails, samples = [], [], [[], []], []
    encoder = None
    title, label, small = font(32), font(24), font(19)
    camera = mujoco.MjvCamera()
    camera.lookat[:] = [0.65, 0, 0]
    camera.distance, camera.azimuth, camera.elevation = 2.8, 90, -65
    try:
        for surface in surfaces:
            env = UBotNavigationEnv(terrain_contact=surface)
            envs.append(env)
            env.reset(seed=0, options={"yaw": 0, "goal": [5, 5]})
            env.model.vis.global_.offwidth = 640
            env.model.vis.global_.offheight = 480
            renderers.append(mujoco.Renderer(env.model, height=480, width=640, max_geom=2000))

        def frame(phase):
            canvas = Image.new("RGB", (1280, 720), "#0c151d")
            draw = ImageDraw.Draw(canvas)
            draw.text((32, 18), "U-BOT / TERRAIN CONTACTS", font=title, fill="#eef4f5")
            draw.text((32, 62), "Identical commands and initial state / estimated surfaces / real-time playback",
                      font=small, fill="#abc0cb")
            for i, (env, renderer) in enumerate(zip(envs, renderers)):
                renderer.update_scene(env.data, camera=camera)
                for start, end in zip(trails[i][:-1], trails[i][1:]):
                    add_geometry(renderer.scene, mujoco.mjtGeom.mjGEOM_CAPSULE,
                                 [*start, 0.015], [0.007, 0, 0], [0.2, 0.85, 0.65, 1], [*end, 0.015])
                canvas.paste(Image.fromarray(renderer.render()), (640 * i, 120))
                x = 640 * i + 24
                heading = "DEFAULT GRIP  /  0.80" if i == 0 else "LOW GRIP  /  0.08"
                draw.text((x, 90), heading, font=label, fill="#48ddb1")
                speed = np.linalg.norm(env._state()[1][3:5])
                cmd = env.command / MAX_WHEEL_SPEED
                draw.text((x, 610), f"Body speed {speed:.2f} m/s", font=label, fill="#eef4f5")
                draw.text((x, 644), f"Wheel command {cmd[0]:+.2f}, {cmd[1]:+.2f} turns/s",
                          font=small, fill="#abc0cb")
            draw.line((640, 90, 640, 674), fill="#536774", width=2)
            draw.text((24, 682), f"{envs[0].data.time:04.1f} s  /  {phase}  /  Accel 8, brake 2 turns/s²",
                      font=small, fill="#eef4f5")
            return canvas

        command = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "rawvideo",
                   "-pix_fmt", "rgb24", "-s", "1280x720", "-r", "25", "-i", "-", "-an",
                   "-c:v", "libx264", "-crf", "18", "-pix_fmt", "yuv420p",
                   "-movflags", "+faststart", str(args.output)]
        encoder = subprocess.Popen(command, stdin=subprocess.PIPE)
        first = frame("READY")
        first.save(args.output.with_suffix(".png"))
        for _ in range(25):
            encoder.stdin.write(first.tobytes())
        for step in range(800):
            _, phase, action = next(p for p in PHASES if step * 0.02 < p[0])
            for i, env in enumerate(envs):
                _, _, terminated, truncated, info = env.step(action)
                if terminated or truncated:
                    raise RuntimeError(f"Comparison ended early: {info}")
                xy = env.data.xpos[env.base, :2].copy()
                if not trails[i] or np.linalg.norm(xy - trails[i][-1]) > 0.015:
                    trails[i].append(xy)
            if step % 2 == 1:
                last = frame(phase)
                encoder.stdin.write(last.tobytes())
                samples.append({"seconds": float(envs[0].data.time), "phase": phase,
                                "xy_metres": [e.data.xpos[e.base, :2].tolist() for e in envs],
                                "body_speed_mps": [float(np.linalg.norm(e._state()[1][3:5])) for e in envs]})
            if (step + 1) % 100 == 0:
                print(f"Rendered {(step + 1) * 0.02:.0f}/16 seconds", flush=True)
        for _ in range(50):
            encoder.stdin.write(last.tobytes())
        encoder.stdin.close()
        if encoder.wait():
            raise RuntimeError("FFmpeg failed")
        last.save(args.output.with_name(args.output.stem + "-complete.png"))
        report = {"seed": 0, "terrain": "flat", "wheel_contact": "lugs", "fps": 25,
                  "video_seconds": 19, "surfaces": [asdict(s) for s in surfaces],
                  "phases": PHASES, "samples": samples,
                  "warning_counts": [sum(int(w.number) for w in e.data.warning) for e in envs]}
        args.output.with_suffix(".json").write_text(json.dumps(report, indent=2) + "\n")
        print(f"Saved {args.output}", flush=True)
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
