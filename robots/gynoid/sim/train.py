"""Local CPU PPO training. Run from gynoid: python -m sim.train."""

from __future__ import annotations

import argparse
from datetime import datetime
import hashlib
from importlib.metadata import version
import json
from pathlib import Path
import platform
import time
import xml.etree.ElementTree as ET

import mujoco
import stable_baselines3
from stable_baselines3 import PPO
from stable_baselines3.common.callbacks import CheckpointCallback, EvalCallback
from stable_baselines3.common.env_util import make_vec_env
from stable_baselines3.common.vec_env import DummyVecEnv, SubprocVecEnv
import torch
import bam

from sim.env import GynoidBalanceEnv, MODEL_PATH
from sim.actuators import PARAMETERS


def environment_class(task):
    if task == "motion":
        from sim.motion_env import GynoidMotionEnv
        return GynoidMotionEnv
    if task == "planted":
        from sim.planted import GynoidPlantedEnv
        return GynoidPlantedEnv
    if task == "balance":
        return GynoidBalanceEnv
    raise ValueError(f"Unknown task: {task}")


def model_hash(task="balance"):
    """Fingerprint dynamics, contact/visual assets and controller/task code."""
    digest = hashlib.sha256()
    model_path = MODEL_PATH.with_name("gynoid_full.xml") if task in ("planted", "motion") else MODEL_PATH
    xml = ET.parse(model_path).getroot()
    paths = [model_path, PARAMETERS, MODEL_PATH.with_name("env.py"),
             MODEL_PATH.with_name("actuators.py"), MODEL_PATH.with_name("stance.py")]
    if task in ("planted", "motion"):
        paths += [MODEL_PATH.with_name(name) for name in ("planted.py", "rest_pose.py", "rest_pose.json")]
    if task == "motion":
        paths += [MODEL_PATH.with_name("motion_env.py")]
    paths += sorted({MODEL_PATH.parent / "assets" / mesh.attrib["file"]
                     for mesh in xml.findall("./asset/mesh")})
    for path in paths:
        digest.update(path.name.encode())
        digest.update(path.read_bytes())
    # Pin executable BAM behavior as well as parameters, including local fixes
    # or edits to an installed package that would not change its version string.
    bam_root = Path(bam.__file__).parent
    for path in sorted(bam_root.rglob("*.py")):
        digest.update(str(path.relative_to(bam_root)).encode())
        digest.update(path.read_bytes())
    for package in ("mujoco", "numpy", "better-actuator-models", "gymnasium"):
        digest.update(f"{package}=={version(package)}".encode())
    return digest.hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--steps", type=int, default=1_000_000, help="Additional environment steps")
    parser.add_argument("--envs", type=int, default=4)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--task", choices=["balance", "planted"])
    parser.add_argument("--reset-noise", type=float)
    parser.add_argument("--push-force", type=float, help="Horizontal push in N, after standing works")
    parser.add_argument("--stance", choices=["cad", "centered"])
    parser.add_argument("--voltage", type=float, help="BAM supply voltage, default 5 V")
    parser.add_argument("--kp", type=float, help="BAM firmware proportional gain, default 200")
    parser.add_argument("--action-range", choices=["baseline", "wide"], help="Position target range, default baseline")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--resume", type=Path, help="Policy ZIP from an existing run")
    args = parser.parse_args()
    if args.steps <= 0 or args.envs <= 0 or (args.push_force is not None and args.push_force < 0):
        parser.error("steps/envs must be positive and push-force nonnegative")
    torch.set_num_threads(1)
    output = args.output or MODEL_PATH.parent / "runs" / datetime.now().strftime("%Y%m%d-%H%M%S")
    if output.exists() and any(output.iterdir()):
        parser.error("Output directory is not empty; choose a new run directory (also when resuming)")
    task = args.task or "balance"
    config = None
    if args.resume:
        previous = args.resume.parent
        if previous.name in ("checkpoints", "best"):
            previous = previous.parent
        config = json.loads((previous / "config.json").read_text())
        task = config.get("task", "balance")
        if args.task is not None and args.task != task:
            parser.error("Cannot resume with a different task")
        if config["model_sha256"] != model_hash(task):
            parser.error("Cannot resume: the simulation model changed")
    env_kwargs = dict(push_force=0.0, voltage=5.0, kp=200.0,
                      reset_noise=0.002 if task == "planted" else 0.01)
    if task == "balance":
        env_kwargs.update(stance="centered", action_range="baseline")
    elif args.stance is not None or args.action_range is not None:
        parser.error("Planted task uses its optimized pose and residual action range")
    if config:
        env_kwargs.update(config["env_kwargs"])
    for key in env_kwargs:
        value = getattr(args, key)
        if value is not None:
            if args.resume and key != "push_force" and value != env_kwargs[key]:
                parser.error(f"Cannot resume with a different {key}")
            env_kwargs[key] = value
    output.mkdir(parents=True, exist_ok=True)
    env = make_vec_env(environment_class(task), n_envs=args.envs, seed=args.seed,
                       env_kwargs=env_kwargs, monitor_dir=str(output / "monitor"),
                       vec_env_cls=SubprocVecEnv if args.envs > 1 else DummyVecEnv,
                       vec_env_kwargs={"start_method": "spawn"} if args.envs > 1 else {})
    evaluation = make_vec_env(environment_class(task), n_envs=1, seed=args.seed + 10_000,
                              env_kwargs=env_kwargs)
    try:
        config = dict(task=task, model_sha256=model_hash(task), env_kwargs=env_kwargs,
                      seed=args.seed, envs=args.envs, requested_steps=args.steps,
                      resume=str(args.resume) if args.resume else None,
                      python=platform.python_version(), machine=platform.machine(),
                      mujoco=mujoco.__version__, torch=torch.__version__,
                      stable_baselines3=stable_baselines3.__version__)
        config["environment"] = evaluation.env_method("configuration")[0]
        (output / "config.json").write_text(json.dumps(config, indent=2) + "\n")
        if args.resume:
            policy = PPO.load(args.resume, env=env, device="cpu")
            policy.set_random_seed(args.seed)
        else:
            policy = PPO("MlpPolicy", env, device="cpu", seed=args.seed, verbose=1,
                         learning_rate=3e-4, n_steps=256, batch_size=256, n_epochs=5,
                         gamma=0.99, gae_lambda=0.95, clip_range=0.2, ent_coef=0.0,
                         policy_kwargs=dict(net_arch=dict(pi=[128, 128], vf=[128, 128]),
                                            log_std_init=-1.5 if task == "planted" else 0.0))
        callbacks = [
            CheckpointCallback(save_freq=max(100_000 // args.envs, 1),
                               save_path=str(output / "checkpoints"), name_prefix="balance"),
            EvalCallback(evaluation, best_model_save_path=str(output / "best"),
                         log_path=str(output), eval_freq=max(25_000 // args.envs, 1),
                         n_eval_episodes=5, deterministic=True),
        ]
        started = time.perf_counter()
        initial_steps = policy.num_timesteps
        interrupted = False
        try:
            policy.learn(total_timesteps=args.steps, callback=callbacks,
                         reset_num_timesteps=not bool(args.resume))
        except KeyboardInterrupt:
            interrupted = True
        finally:
            policy.save(output / "policy")
            summary = dict(total_steps=policy.num_timesteps,
                           additional_steps=policy.num_timesteps - initial_steps,
                           elapsed_seconds=time.perf_counter() - started, interrupted=interrupted)
            (output / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
            print(f"Saved {output / 'policy.zip'}", flush=True)
    finally:
        evaluation.close()
        env.close()


if __name__ == "__main__":
    main()
