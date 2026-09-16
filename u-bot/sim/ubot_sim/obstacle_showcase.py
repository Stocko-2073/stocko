"""Record four synchronized encounters with static terrain obstacles."""
import argparse
from dataclasses import asdict
import json
from pathlib import Path
import subprocess

import mujoco
import numpy as np
from PIL import Image, ImageDraw

from ubot_sim.contact_model import TerrainObstacle
from ubot_sim.env import UBotNavigationEnv
from ubot_sim.record import font

OBSTACLES = [
    TerrainObstacle("rock", (0.5, 0.15, 0.015), (0.04, 0.04, 0.025)),
    TerrainObstacle("root", (0.5, 0, 0), (0.012, 0.25)),
    TerrainObstacle("seam", (0.5, 0, 0.005), (0.006, 0.25, 0.005)),
    TerrainObstacle("edge", (0.5, 0, 0.015), (0.1, 0.25, 0.015)),
]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("videos/obstacle-showcase.mp4"))
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    envs, renderers, samples = [], [], []
    touched = [False] * 4
    encoder = None
    title, label, small = font(30), font(22), font(18)
    camera = mujoco.MjvCamera()
    camera.lookat[:] = [0.4, 0, 0.025]
    camera.distance, camera.azimuth, camera.elevation = 1.65, 110, -38
    try:
        for obstacle in OBSTACLES:
            env = UBotNavigationEnv(obstacles=[obstacle])
            envs.append(env)
            env.reset(seed=0, options={"yaw": 0, "goal": [5, 5]})
            env.model.vis.global_.offwidth = 640
            env.model.vis.global_.offheight = 260
            renderers.append(mujoco.Renderer(env.model, height=260, width=640))

        def frame():
            canvas = Image.new("RGB", (1280, 720), "#0c151d")
            draw = ImageDraw.Draw(canvas)
            draw.text((24, 14), "U-BOT / OBSTACLE ENCOUNTERS", font=title, fill="#eef4f5")
            draw.text((24, 54), "Same drive commands / lugged wheels / rigid shape approximations / real-time playback",
                      font=small, fill="#abc0cb")
            for i, (env, renderer, obstacle) in enumerate(zip(envs, renderers, OBSTACLES)):
                x, y = (i % 2) * 640, 86 + (i // 2) * 298
                renderer.update_scene(env.data, camera=camera)
                canvas.paste(Image.fromarray(renderer.render()), (x, y + 30))
                speed = np.linalg.norm(env._state()[1][3:5])
                state = "CONTACT RECORDED" if touched[i] else "APPROACHING"
                draw.text((x + 18, y), obstacle.kind.upper(), font=label, fill="#48ddb1")
                draw.text((x + 175, y + 3), f"{state} / {speed:.2f} m/s", font=small, fill="#eef4f5")
            draw.line((640, 86, 640, 682), fill="#536774", width=2)
            phase = "DRIVE +0.35 turns/s" if envs[0].data.time < 4 else "BRAKE TO STOP"
            draw.text((24, 692), f"{envs[0].data.time:.1f} s / {phase} / Contact does not guarantee crossing",
                      font=small, fill="#abc0cb")
            return canvas

        command = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "rawvideo",
                   "-pix_fmt", "rgb24", "-s", "1280x720", "-r", "25", "-i", "-", "-an",
                   "-c:v", "libx264", "-crf", "18", "-pix_fmt", "yuv420p",
                   "-movflags", "+faststart", str(args.output)]
        encoder = subprocess.Popen(command, stdin=subprocess.PIPE)
        first = frame()
        first.save(args.output.with_suffix(".png"))
        for _ in range(25):
            encoder.stdin.write(first.tobytes())
        for step in range(250):
            action = [0.35, 0.35] if step < 200 else [0, 0]
            for i, env in enumerate(envs):
                _, _, terminated, truncated, info = env.step(action)
                if terminated or truncated:
                    raise RuntimeError(f"{OBSTACLES[i].kind} run ended early: {info}")
                obstacle_id = env.model.geom("terrain_obstacle_0").id
                touched[i] |= any(obstacle_id in (c.geom1, c.geom2) for c in env.data.contact)
            if step % 2 == 1:
                last = frame()
                encoder.stdin.write(last.tobytes())
                samples.append({"seconds": float(envs[0].data.time), "action": action,
                                "xy_metres": [e.data.xpos[e.base, :2].tolist() for e in envs],
                                "contact_recorded": touched.copy()})
            if (step + 1) % 50 == 0:
                print(f"Rendered {(step + 1) * 0.02:.0f}/5 seconds", flush=True)
        for _ in range(50):
            encoder.stdin.write(last.tobytes())
        encoder.stdin.close()
        if encoder.wait():
            raise RuntimeError("FFmpeg failed")
        last.save(args.output.with_name(args.output.stem + "-complete.png"))
        report = {"seed": 0, "terrain": "flat", "wheel_contact": "lugs", "fps": 25,
                  "video_seconds": 8, "obstacles": [asdict(o) for o in OBSTACLES],
                  "samples": samples, "contact_recorded": touched,
                  "warning_counts": [sum(int(w.number) for w in e.data.warning) for e in envs]}
        args.output.with_suffix(".json").write_text(json.dumps(report, indent=2) + "\n")
        if not all(touched):
            raise RuntimeError(f"Some obstacles were never contacted: {touched}")
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
