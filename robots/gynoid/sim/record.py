"""Record policy rollouts to MP4 with the same renderer and dynamics as evaluation.

May also be run by absolute path from a snapshot with PYTHONPATH set to that
snapshot, to import its original sim.env and sim.train without modifying it.
"""

import argparse
import json
from pathlib import Path
import shutil
import subprocess

import mujoco
import numpy as np
from stable_baselines3 import PPO
import torch

from sim.env import GynoidBalanceEnv, MODEL_PATH
from sim.train import model_hash


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    control = parser.add_mutually_exclusive_group()
    control.add_argument("--policy", type=Path)
    control.add_argument("--controller", type=Path, help="Saved planted balance controller (.npz)")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--episodes", type=int, default=4)
    parser.add_argument("--seed", type=int, default=1000)
    parser.add_argument("--task", choices=["balance", "planted", "motion"])
    parser.add_argument("--seconds", type=float, help="Episode duration, default 10 seconds")
    parser.add_argument("--push-force", type=float, help="Override the recorded horizontal push force in N")
    parser.add_argument("--show-forces", action="store_true", help="Draw red arrows while external pushes are applied")
    parser.add_argument("--camera-height", type=float, default=0.24, help="Camera look-at height in metres")
    parser.add_argument("--camera-distance", type=float, default=0.85, help="Camera distance in metres")
    parser.add_argument("--speed", type=float, default=0.5, help="Playback speed relative to real time")
    args = parser.parse_args()
    if (args.episodes <= 0 or not np.isfinite(args.speed) or args.speed <= 0
            or (args.seconds is not None and args.seconds <= 0)
            or not np.isfinite([args.camera_height, args.camera_distance]).all() or args.camera_distance <= 0):
        parser.error("Episodes and playback speed must be positive")
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        parser.error("Video recording requires ffmpeg on PATH")
    if args.output.suffix.lower() != ".mp4" or args.output.exists():
        parser.error("Choose a new .mp4 output path")
    torch.set_num_threads(1)
    task = args.task or "balance"
    env_kwargs = {}
    controller = None
    if args.controller:
        from sim.balance_controller import PlantedBalanceController
        controller, config = PlantedBalanceController.load(args.controller)
        task = config["task"]
        if args.task is not None and args.task != task:
            parser.error("Use the controller's recorded task")
        env_kwargs.update(config["env_kwargs"])
    if args.policy:
        run_dir = args.policy.parent
        if run_dir.name in ("checkpoints", "best"):
            run_dir = run_dir.parent
        config = json.loads((run_dir / "config.json").read_text())
        task = config.get("task", "balance")
        if args.task is not None and args.task != task:
            parser.error("Use the policy's recorded task")
        fingerprint = model_hash(task) if task in ("planted", "motion") else model_hash()
        if config["model_sha256"] != fingerprint:
            parser.error("Policy and environment differ; record using the policy's original snapshot")
        env_kwargs.update(config["env_kwargs"])
    fingerprint = model_hash(task) if task in ("planted", "motion") else model_hash()
    if args.seconds is not None:
        env_kwargs["episode_seconds"] = args.seconds
    if args.push_force is not None:
        env_kwargs["push_force"] = args.push_force
    policy = PPO.load(args.policy, device="cpu") if args.policy else None
    env_class = GynoidBalanceEnv
    if task == "planted":
        from sim.planted import GynoidPlantedEnv
        env_class = GynoidPlantedEnv
    elif task == "motion":
        from sim.motion_env import GynoidMotionEnv
        env_class = GynoidMotionEnv
    env = env_class(render_mode="rgb_array", **env_kwargs)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    episodes = []
    process = None
    camera = mujoco.MjvCamera()
    camera.lookat[:] = [0, 0, args.camera_height]
    camera.distance, camera.azimuth, camera.elevation = args.camera_distance, 135, -12
    options = mujoco.MjvOption()
    options.geomgroup[3] = 0
    def render_frame():
        if env.renderer is None:
            env.renderer = mujoco.Renderer(env.model, height=720, width=960)
        env.renderer.update_scene(env.data, camera=camera, scene_option=options)
        if args.show_forces:
            scene = env.renderer.scene
            for body, force in enumerate(env.data.xfrc_applied[:, :3]):
                magnitude = np.linalg.norm(force)
                if magnitude < 1e-8:
                    continue
                end = env.data.xipos[body].copy()
                start = end - force / magnitude * 0.08
                geom = scene.geoms[scene.ngeom]
                mujoco.mjv_initGeom(geom, mujoco.mjtGeom.mjGEOM_ARROW, np.ones(3),
                                  start, np.eye(3).ravel(), np.array([1, 0.12, 0.08, 1], dtype=np.float32))
                mujoco.mjv_connector(geom, mujoco.mjtGeom.mjGEOM_ARROW, 0.004, start, end)
                scene.ngeom += 1
        return env.renderer.render()

    try:
        env.reset(seed=args.seed)
        first_frame = render_frame()
        height, width, _ = first_frame.shape
        fps = round(1 / env.dt)
        command = [ffmpeg, "-hide_banner", "-loglevel", "error", "-n",
                   "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{width}x{height}",
                   "-r", str(fps), "-i", "pipe:0", "-an", "-vf", f"setpts=PTS/{args.speed}",
                   "-r", str(fps), "-c:v", "libx264", "-preset", "fast", "-crf", "20",
                   "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(args.output)]
        with args.output.with_suffix(".ffmpeg.log").open("wb") as log:
            process = subprocess.Popen(command, stdin=subprocess.PIPE, stderr=log)
            try:
                for episode in range(args.episodes):
                    obs, _ = env.reset(seed=args.seed + episode)
                    frame = render_frame().tobytes()
                    for _ in range(round(.25 * fps)):
                        process.stdin.write(frame)
                    reward_sum = 0.0
                    samples = []
                    for _ in range(env.max_steps):
                        action = (controller.predict(env) if controller else
                                  policy.predict(obs, deterministic=True)[0] if policy else np.zeros(env.model.nu))
                        obs, reward, terminated, truncated, info = env.step(action)
                        reward_sum += reward
                        if controller and hasattr(controller, "assess"):
                            samples.append(info)
                        frame = render_frame().tobytes()
                        process.stdin.write(frame)
                        if terminated or truncated:
                            break
                    for _ in range(round(.35 * fps)):
                        process.stdin.write(frame)
                    episodes.append(dict(seed=args.seed + episode, seconds=info["elapsed_seconds"],
                                         success=info["success"], return_=reward_sum))
                    if samples:
                        episodes[-1].update(controller.assess(samples))
                        episodes[-1]["success"] &= episodes[-1]["motion_success"]
            finally:
                process.stdin.close()
                process.wait()
            if process.returncode:
                raise RuntimeError(f"FFmpeg failed; see {args.output.with_suffix('.ffmpeg.log')}")
        metadata = dict(task=task, policy=str(args.policy.resolve()) if args.policy else None,
                        controller=str(args.controller.resolve()) if args.controller else None,
                        environment_source=str(MODEL_PATH.parent.resolve()), model_sha256=fingerprint,
                        playback_speed=args.speed, fps=fps, episodes=episodes)
        metadata.update(push_force_n=env.push_force, show_forces=args.show_forces)
        metadata.update(camera_height_m=args.camera_height, camera_distance_m=args.camera_distance)
        args.output.with_suffix(".json").write_text(json.dumps(metadata, indent=2) + "\n")
        print(args.output.resolve())
    finally:
        env.close()


if __name__ == "__main__":
    main()
