"""Evaluate a policy or zero-target baseline, optionally with the MuJoCo viewer."""

from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import time

import mujoco.viewer
import numpy as np
from stable_baselines3 import PPO
import torch

from sim.env import GynoidBalanceEnv
from sim.train import model_hash, environment_class


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    control = parser.add_mutually_exclusive_group()
    control.add_argument("--policy", type=Path)
    control.add_argument("--controller", type=Path, help="Saved planted balance controller (.npz)")
    parser.add_argument("--episodes", type=int, default=10)
    parser.add_argument("--seed", type=int, default=1000)
    parser.add_argument("--task", choices=["balance", "planted", "motion"])
    parser.add_argument("--reset-noise", type=float)
    parser.add_argument("--seconds", type=float, help="Episode duration, default 10 seconds")
    parser.add_argument("--viewer", action="store_true", help="On macOS run with .venv/bin/mjpython")
    parser.add_argument("--push-force", type=float)
    parser.add_argument("--stance", choices=["cad", "centered"], help="Stance for an untrained fixed-target evaluation")
    parser.add_argument("--output", type=Path, help="Write evaluation JSON")
    args = parser.parse_args()
    if args.episodes <= 0 or (args.seconds is not None and args.seconds <= 0):
        parser.error("episodes and seconds must be positive")
    torch.set_num_threads(1)
    env_kwargs = {}
    task = args.task or "balance"
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
        if config["model_sha256"] != model_hash(task):
            parser.error("Policy was trained against a different simulation model; use its archived snapshot if available")
        env_kwargs.update(config["env_kwargs"])
        if args.stance is not None and args.stance != env_kwargs.get("stance", "centered"):
            parser.error("Use the policy's recorded stance")
    if args.stance is not None:
        if task in ("planted", "motion"):
            parser.error("Planted task uses its optimized pose")
        env_kwargs["stance"] = args.stance
    if args.reset_noise is not None:
        env_kwargs["reset_noise"] = args.reset_noise
    if args.push_force is not None:
        env_kwargs["push_force"] = args.push_force
    if args.seconds is not None:
        env_kwargs["episode_seconds"] = args.seconds
    policy = PPO.load(args.policy, device="cpu") if args.policy else None
    env = environment_class(task)(**env_kwargs)
    viewer = None
    episodes = []
    try:
        if args.viewer:
            viewer = mujoco.viewer.launch_passive(env.model, env.data)
            viewer.cam.lookat[:] = [0, 0, 0.24]
            viewer.cam.distance = 0.85
            viewer.cam.azimuth = 135
            viewer.cam.elevation = -12
            viewer.opt.geomgroup[3] = 0
        for episode in range(args.episodes):
            obs, _ = env.reset(seed=args.seed + episode)
            reward_sum = 0.0
            peak_drift = peak_lift = peak_tilt = total_loss = 0.0
            minimum_height = float("inf")
            motion_metrics = []
            for _ in range(env.max_steps):
                start = time.perf_counter()
                action = (controller.predict(env) if controller else
                          policy.predict(obs, deterministic=True)[0] if policy else np.zeros(env.model.nu))
                obs, reward, terminated, truncated, info = env.step(action)
                reward_sum += reward
                if task in ("planted", "motion"):
                    peak_drift = max(peak_drift, info["foot_drift_m"])
                    peak_lift = max(peak_lift, info["foot_lift_m"])
                    peak_tilt = max(peak_tilt, float(np.rad2deg(np.arccos(np.clip(info["upright"], -1, 1)))))
                    total_loss += info["copper_loss_w"]
                    minimum_height = min(minimum_height, info["height"])
                if task == "motion":
                    motion_metrics.append({key: info[key] for key in
                                           ("elapsed_seconds", "right_shoulder_offset_rad", "right_hand_forward_m",
                                            "com_lateral_m", "left_load_fraction", "right_hand_above_head_m",
                                            "right_hand_lowest_above_head_m")})
                if viewer:
                    if not viewer.is_running():
                        break
                    viewer.sync()
                    time.sleep(max(0.0, env.dt - (time.perf_counter() - start)))
                if terminated or truncated:
                    break
            episodes.append(dict(seed=args.seed + episode, return_=reward_sum,
                                 seconds=info["elapsed_seconds"], success=info["success"],
                                 termination_reasons=info["termination_reasons"]))
            if task in ("planted", "motion"):
                episodes[-1].update(final_foot_drift_m=info["foot_drift_m"],
                                    final_foot_lift_m=info["foot_lift_m"],
                                    max_foot_drift_m=peak_drift, max_foot_lift_m=peak_lift,
                                    max_torso_tilt_deg=peak_tilt, min_height_m=minimum_height,
                                    mean_copper_loss_w=total_loss / env.steps,
                                    simulator_warnings=int(env.data.warning.number.sum()))
            if motion_metrics:
                episodes[-1].update({key: info[key] for key in
                                     ("peak_current_a", "peak_voltage_v", "peak_torque_nm",
                                      "saturated_actuator_updates")})
                episodes[-1]["motion_ranges"] = {
                    key: [min(row[key] for row in motion_metrics), max(row[key] for row in motion_metrics)]
                    for key in motion_metrics[0]}
                episodes[-1]["final_motion"] = motion_metrics[-1]
                if controller:
                    episodes[-1]["standing_success"] = episodes[-1]["success"]
                    episodes[-1].update(controller.assess(motion_metrics))
                    episodes[-1]["success"] &= episodes[-1]["motion_success"]
            if viewer and not viewer.is_running():
                break
        result = dict(task=task, policy=str(args.policy or args.controller or "fixed-target baseline"),
                      controller_type=controller.controller_name if controller else "ppo" if policy else "fixed_target",
                      success_rate=float(np.mean([e["success"] for e in episodes])),
                      mean_seconds=float(np.mean([e["seconds"] for e in episodes])),
                      termination_counts=dict(Counter(reason for e in episodes for reason in e["termination_reasons"])),
                      motion_failure_counts=dict(Counter(reason for e in episodes for reason in e.get("motion_failures", []))),
                      environment=env.configuration(), episodes=episodes)
        print(json.dumps(result, indent=2))
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(json.dumps(result, indent=2) + "\n")
    finally:
        if viewer:
            viewer.close()
        env.close()


if __name__ == "__main__":
    main()
