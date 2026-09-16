"""Compare soil-only grass with a five-centimetre canopy under identical commands."""
import argparse
from dataclasses import asdict
import json
from pathlib import Path
import subprocess

import mujoco
import numpy as np
from PIL import Image, ImageDraw

from ubot_sim.env import UBotNavigationEnv
from ubot_sim.record import font, add_geometry

PHASES = [(3, "DRIVE", [0.45, 0.45]), (5, "BRAKE / RECOVER", [0, 0]),
          (8, "REVERSE", [-0.45, -0.45]), (11, "STOP / RECOVER", [0, 0])]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("videos/grass-canopy-showcase.mp4"))
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    envs, renderers, samples = [], [], []
    encoder = None
    title, label, small = font(30), font(23), font(18)
    camera = mujoco.MjvCamera()
    camera.lookat[:] = [0.35, 0, 0.02]
    camera.distance, camera.azimuth, camera.elevation = 1.65, 100, -30
    try:
        for canopy in (False, None):
            env = UBotNavigationEnv(surface="short_grass", grass_canopy=canopy)
            envs.append(env)
            env.reset(seed=0, options={"yaw": 0, "goal": [2.5, 2.5]})
            env.model.vis.global_.offwidth = 640
            env.model.vis.global_.offheight = 440
            renderers.append(mujoco.Renderer(env.model, height=440, width=640, max_geom=5000))

        def frame(phase):
            canvas = Image.new("RGB", (1280, 720), "#0c151d")
            draw = ImageDraw.Draw(canvas)
            draw.text((24, 17), "U-BOT / A 5 cm GRASS CANOPY", font=title, fill="#eef4f5")
            draw.text((24, 60), "Identical soil, grip, rolling friction and commands / experimental resistance / real-time playback",
                      font=small, fill="#abc0cb")
            for i, (env, renderer) in enumerate(zip(envs, renderers)):
                x = i * 640
                draw.text((x + 24, 100), "SOIL CONTACT ONLY" if i == 0 else "5 cm CANOPY + DRAG", font=label, fill="#48ddb1")
                renderer.update_scene(env.data, camera=camera)
                if env.canopy:
                    env.draw_canopy(renderer.scene, camera.lookat)
                    # A true 5 cm reference beside the robot's path.
                    a = np.array([0.25, -0.28, env.terrain_height([0.25, -0.28])])
                    b = a + [0, 0, 0.05]
                    add_geometry(renderer.scene, mujoco.mjtGeom.mjGEOM_CAPSULE, a,
                                 [0.002, 0, 0], [1, 0.8, 0.2, 1], b)
                    for point in (a, b):
                        add_geometry(renderer.scene, mujoco.mjtGeom.mjGEOM_CAPSULE, point - [0.015, 0, 0],
                                     [0.0015, 0, 0], [1, 0.8, 0.2, 1], point + [0.015, 0, 0])
                canvas.paste(Image.fromarray(renderer.render()), (x, 140))
                speed = np.linalg.norm(env._state()[1][3:5])
                draw.text((x + 24, 591), f"Speed {speed:.3f} m/s / X {env.data.xpos[env.base, 0]:+.3f} m",
                          font=label, fill="#eef4f5")
                detail = (f"Canopy drag {env.canopy.force_norm:.2f} N / power {env.canopy.power:.3f} W"
                          if env.canopy else "Original 0–8 mm soil bumps / canopy disabled")
                draw.text((x + 24, 628), detail, font=small, fill="#abc0cb")
            draw.line((640, 96, 640, 670), fill="#536774", width=2)
            draw.text((24, 690), f"{envs[0].data.time:04.1f} s / {phase} / Yellow ruler = 5 cm / Blade bending is illustrative",
                      font=small, fill="#abc0cb")
            return canvas

        encoder = subprocess.Popen(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "rawvideo",
                                    "-pix_fmt", "rgb24", "-s", "1280x720", "-r", "25", "-i", "-", "-an",
                                    "-c:v", "libx264", "-crf", "18", "-pix_fmt", "yuv420p", "-movflags",
                                    "+faststart", str(args.output)], stdin=subprocess.PIPE)
        first = frame("READY")
        first.save(args.output.with_suffix(".png"))
        for _ in range(25):
            encoder.stdin.write(first.tobytes())
        for step in range(550):
            _, phase, action = next(p for p in PHASES if step * 0.02 < p[0])
            for env in envs:
                _, _, terminated, truncated, info = env.step(action)
                if terminated or truncated:
                    raise RuntimeError(f"Comparison ended early: {info}")
            if step % 2 == 1:
                last = frame(phase)
                encoder.stdin.write(last.tobytes())
            if step % 10 == 9:
                samples.append({"seconds": float(envs[0].data.time), "phase": phase,
                                "xy_metres": [e.data.xpos[e.base, :2].tolist() for e in envs],
                                "speeds_mps": [float(np.linalg.norm(e._state()[1][3:5])) for e in envs],
                                "canopy_drag_n": envs[1].canopy.force_norm,
                                "canopy_power_w": envs[1].canopy.power,
                                "max_blade_bend_m": float(np.max(np.linalg.norm(envs[1].canopy.visual.bend, axis=1)))})
            if (step + 1) % 100 == 0:
                print(f"Rendered {(step + 1) * 0.02:.0f}/11 seconds", flush=True)
        for _ in range(50):
            encoder.stdin.write(last.tobytes())
        encoder.stdin.close()
        if encoder.wait():
            raise RuntimeError("FFmpeg failed")
        last.save(args.output.with_name(args.output.stem + "-complete.png"))
        report = {"surface": "short_grass", "seed": 0, "wheel_contact": "lugs", "physics_timestep": 0.002,
                  "canopy": asdict(envs[1].canopy.settings), "fps": 25, "resolution": [1280, 720],
                  "video_seconds": 14, "phases": PHASES, "samples": samples,
                  "warning_counts": [sum(int(w.number) for w in e.data.warning) for e in envs]}
        args.output.with_suffix(".json").write_text(json.dumps(report, indent=2) + "\n")
        if any(report["warning_counts"]) or any(s["canopy_power_w"] > 1e-10 for s in samples):
            raise RuntimeError("Comparison requires no solver warnings or energy-injecting canopy forces")
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
