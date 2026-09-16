"""Train PPO for goal navigation, saving periodic and final checkpoints."""
import argparse
from pathlib import Path

from stable_baselines3 import PPO
from stable_baselines3.common.callbacks import CheckpointCallback, EvalCallback
from stable_baselines3.common.env_util import make_vec_env

from ubot_sim.contact_model import SURFACE_PRESETS
from ubot_sim.env import UBotNavigationEnv


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--steps", type=int, default=1_000_000)
    parser.add_argument("--envs", type=int, default=4)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--output", type=Path, default=Path("runs/navigation"))
    parser.add_argument("--randomize", action="store_true")
    parser.add_argument("--wheel-contact", choices=["smooth", "lugs"], default="lugs")
    parser.add_argument("--terrain", choices=["flat", "bumps"], default="flat")
    parser.add_argument("--surface", choices=sorted(SURFACE_PRESETS), help="Estimated material preset (flat terrain only)")
    args = parser.parse_args()
    if args.surface and args.terrain != "flat":
        parser.error("--surface requires --terrain flat")
    if args.steps <= 0 or args.envs <= 0:
        parser.error("steps and envs must be positive")
    args.output.mkdir(parents=True, exist_ok=True)
    model_options = {"wheel_contact": args.wheel_contact, "terrain": args.terrain, "surface": args.surface}
    train = make_vec_env(UBotNavigationEnv, n_envs=args.envs, seed=args.seed,
                         env_kwargs={"randomize": args.randomize, **model_options}, monitor_dir=str(args.output / "monitor"))
    evaluation = make_vec_env(UBotNavigationEnv, n_envs=1, seed=args.seed + 10000,
                              env_kwargs=model_options)
    callbacks = [
        CheckpointCallback(save_freq=max(50_000 // args.envs, 1), save_path=str(args.output / "checkpoints")),
        EvalCallback(evaluation, best_model_save_path=str(args.output / "best"),
                     log_path=str(args.output / "eval"), eval_freq=max(25_000 // args.envs, 1), n_eval_episodes=10),
    ]
    try:
        model = PPO("MlpPolicy", train, seed=args.seed, device="cpu", verbose=1,
                    n_steps=512, batch_size=128, learning_rate=3e-4,
                    policy_kwargs={"net_arch": [128, 128]})
        model.learn(total_timesteps=args.steps, callback=callbacks)
        model.save(args.output / "final")
    finally:
        train.close()
        evaluation.close()


if __name__ == "__main__":
    main()
