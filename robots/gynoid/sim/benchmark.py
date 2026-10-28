"""Measure headless rollout throughput on this machine (no training)."""

import argparse
import json
import time

import numpy as np
from stable_baselines3.common.env_util import make_vec_env
from stable_baselines3.common.vec_env import DummyVecEnv, SubprocVecEnv
import torch

from sim.env import GynoidBalanceEnv


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--steps", type=int, default=2000, help="Vector steps per configuration")
    args = parser.parse_args()
    if args.steps <= 0:
        parser.error("steps must be positive")
    torch.set_num_threads(1)
    results = []
    for count in (1, 4, 8):
        env = make_vec_env(GynoidBalanceEnv, n_envs=count, seed=0,
                           vec_env_cls=DummyVecEnv if count == 1 else SubprocVecEnv,
                           vec_env_kwargs={} if count == 1 else {"start_method": "spawn"})
        try:
            env.reset()
            action = np.zeros((count, 9), dtype=np.float32)
            for _ in range(50):
                env.step(action)
            started = time.perf_counter()
            for _ in range(args.steps):
                env.step(action)
            elapsed = time.perf_counter() - started
            result = dict(envs=count, environment_steps_per_second=args.steps * count / elapsed,
                          elapsed_seconds=elapsed)
            results.append(result)
            print(json.dumps(result), flush=True)
        finally:
            env.close()
    print("Each environment step advances 20 ms of simulation; training includes additional policy/optimizer work.")


if __name__ == "__main__":
    main()
