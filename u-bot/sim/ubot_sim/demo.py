"""Run a baseline or trained navigation policy, with optional interactive view."""
import argparse
import json
import time

from ubot_sim.env import UBotNavigationEnv, baseline_action
from ubot_sim.waypoints import UBotWaypointsEnv


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--viewer", action="store_true")
    parser.add_argument("--policy", help="PPO checkpoint path")
    parser.add_argument("--episodes", type=int, default=5)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--waypoints", action="store_true", help="Follow one continuous five-waypoint route")
    parser.add_argument("--route", help="JSON file containing a list of [x, y] waypoints")
    parser.add_argument("--wheel-contact", choices=["smooth", "lugs"], default="lugs")
    parser.add_argument("--terrain", choices=["flat", "bumps"], default="flat")
    args = parser.parse_args()
    policy = None
    if args.policy:
        from stable_baselines3 import PPO
        policy = PPO.load(args.policy, device="cpu")
    if args.waypoints or args.route:
        route = None
        if args.route:
            with open(args.route) as file:
                route = json.load(file)
        env = UBotWaypointsEnv(waypoints=route, render_mode="human" if args.viewer else None,
                              wheel_contact=args.wheel_contact, terrain=args.terrain)
    else:
        env = UBotNavigationEnv(render_mode="human" if args.viewer else None,
                               wheel_contact=args.wheel_contact, terrain=args.terrain)
    try:
        for episode in range(1 if args.waypoints or args.route else args.episodes):
            obs, _ = env.reset(seed=args.seed + episode, options={"yaw": 0} if args.waypoints or args.route else None)
            total = 0
            for step in range(env.max_steps):
                start = time.monotonic()
                action = baseline_action(obs) if policy is None else policy.predict(obs, deterministic=True)[0]
                obs, reward, terminated, truncated, info = env.step(action)
                total += reward
                if args.viewer:
                    time.sleep(max(0, env.dt - (time.monotonic() - start)))
                    if not env._viewer.is_running():
                        return
                if terminated or truncated:
                    break
            print(json.dumps({"episode": episode, "steps": step + 1, "return": total, **info}), flush=True)
    finally:
        env.close()


if __name__ == "__main__":
    main()
