"""Compare smooth/lug wheel physics and full waypoint throughput without rendering."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import platform
import statistics
import subprocess
import time

import mujoco
import numpy as np

from ubot_sim.env import baseline_action
from ubot_sim.waypoints import UBotWaypointsEnv

# Identical velocity commands across variants: straight, arcs, pivot, reverse.
COMMANDS = [[2, 2], [3, 3], [1, 3], [-2, 2], [-2, -2],
            [-3, -1], [2, -2], [2, 2], [1, 1], [0, 0]]


def physics_run(env, diagnostics=False):
    env.reset(seed=17, options={"yaw": 0})
    contacts, lug_contacts, penetration = [], [], 0.0
    upright = 1.0
    finite = True
    step_count = round(2 / env.model.opt.timestep)
    start = time.perf_counter()
    for command in COMMANDS:
        env.data.ctrl[:] = command
        if env.motor is not None:
            env.command[:] = command
        if not diagnostics:
            # Batch pure contact models in C; canopy forces require per-tick
            # Python updates. Diagnostics are excluded in either case.
            if env.canopy is None and env.motor is None:
                mujoco.mj_step(env.model, env.data, nstep=step_count)
            else:
                for _ in range(step_count):
                    env._physics_step()
        else:
            for _ in range(step_count):
                env._physics_step()
                contacts.append(int(env.data.ncon))
                lug_count = 0
                for c in env.data.contact:
                    penetration = max(penetration, -float(c.dist))
                    lug_count += int(c.geom1 in env._benchmark_lugs or c.geom2 in env._benchmark_lugs)
                lug_contacts.append(lug_count)
                upright = min(upright, float(env.data.xmat[env.base, 8]))
                finite &= bool(np.isfinite(env.data.qpos).all() and np.isfinite(env.data.qvel).all())
    elapsed = time.perf_counter() - start
    if not diagnostics:
        return elapsed
    return {"mean_contacts": float(np.mean(contacts)), "max_contacts": max(contacts),
            "mean_lug_contacts": float(np.mean(lug_contacts)), "max_lug_contacts": max(lug_contacts),
            "max_penetration_mm": 1000 * penetration, "min_upright_cosine": upright,
            "finite": finite, "warning_count": sum(int(w.number) for w in env.data.warning),
            "final_xy_m": env.data.xpos[env.base, :2].tolist()}


def route_run(env, seed):
    obs, _ = env.reset(seed=seed, options={"yaw": 0})
    start = time.perf_counter()
    path = []
    for step in range(env.max_steps):
        obs, _, terminated, truncated, info = env.step(baseline_action(obs))
        path.append(env.data.xpos[env.base, :2].tolist())
        if terminated or truncated:
            break
    elapsed = time.perf_counter() - start
    return {"seed": seed, "seconds": elapsed, "steps": step + 1,
            "simulated_seconds": float(env.data.time),
            "real_time_factor": float(env.data.time) / elapsed,
            "policy_steps_per_second": (step + 1) / elapsed,
            "is_success": info["is_success"], "reached": info["waypoints_reached"],
            "warning_count": sum(int(w.number) for w in env.data.warning)}, np.array(path)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("benchmarks/lugs.json"))
    parser.add_argument("--repeats", type=int, default=7)
    parser.add_argument("--seeds", type=int, default=5)
    args = parser.parse_args()
    if args.repeats < 3 or args.seeds < 1:
        parser.error("Use at least three repeats and one seed")
    configurations = [(wheel, terrain, dt) for terrain in ("flat", "bumps")
                      for wheel, dt in (("smooth", 0.002), ("lugs", 0.002), ("lugs", 0.001))]
    envs, timings, routes, paths = {}, {}, {}, {}
    try:
        for wheel, terrain, dt in configurations:
            key = f"{wheel}/{terrain}/{dt:g}"
            env = UBotWaypointsEnv(wheel_contact=wheel, terrain=terrain, timestep=dt)
            envs[key] = env
            env._benchmark_lugs = {i for i in range(env.model.ngeom)
                                   if "_lug_" in (mujoco.mj_id2name(env.model, mujoco.mjtObj.mjOBJ_GEOM, i) or "")}
            physics_run(env)  # compile/load/reset and warmup excluded from timings
            timings[key], routes[key], paths[key] = [], [], []
        rng = np.random.default_rng(42)
        for _ in range(args.repeats):
            for key in rng.permutation(list(envs)):
                timings[key].append(physics_run(envs[key]))
        for seed in range(args.seeds):
            for key in rng.permutation(list(envs)):
                route, path = route_run(envs[key], seed)
                routes[key].append(route)
                paths[key].append(path)
        results = {}
        for key, env in envs.items():
            print(f"Checking {key}", flush=True)
            diagnostics = physics_run(env, diagnostics=True)
            median = statistics.median(timings[key])
            results[key] = {"physics_seconds_samples": timings[key], "physics_seconds_median": median,
                            "physics_real_time_factor": 20 / median,
                            "physics_steps_per_second": 20 / env.model.opt.timestep / median,
                            "route_real_time_factor_median": statistics.median(r["real_time_factor"] for r in routes[key]),
                            "policy_steps_per_second_median": statistics.median(r["policy_steps_per_second"] for r in routes[key]),
                            "ngeom": env.model.ngeom, "nbody": env.model.nbody, "nv": env.model.nv,
                            "diagnostics": diagnostics, "routes": routes[key]}
        comparisons = {}
        for terrain in ("flat", "bumps"):
            smooth = results[f"smooth/{terrain}/0.002"]
            lugs = results[f"lugs/{terrain}/0.002"]
            differences = []
            for coarse, fine in zip(paths[f"lugs/{terrain}/0.002"], paths[f"lugs/{terrain}/0.001"]):
                n = min(len(coarse), len(fine))
                errors = np.linalg.norm(coarse[:n] - fine[:n], axis=1)
                differences.append({"rms_xy_difference_m": float(np.sqrt(np.mean(errors**2))),
                                    "max_xy_difference_m": float(errors.max())})
            comparisons[terrain] = {
                "physics_lug_slowdown": lugs["physics_seconds_median"] / smooth["physics_seconds_median"],
                "route_lug_slowdown": smooth["policy_steps_per_second_median"] / lugs["policy_steps_per_second_median"],
                "lug_2ms_vs_1ms_same_time_path_differences": differences}
        cpu = platform.processor()
        if platform.system() == "Darwin":
            probe = subprocess.run(["sysctl", "-n", "machdep.cpu.brand_string"], text=True, capture_output=True)
            if probe.returncode == 0:
                cpu = probe.stdout.strip()
            else:
                cpu = f"{platform.machine()} (CPU model unavailable in sandbox)"
        source_files = [Path(__file__), Path(__file__).with_name("contact_model.py"),
                        Path(__file__).with_name("env.py"), Path(__file__).with_name("waypoints.py"),
                        Path(__file__).parent / "assets" / "robot.xml"]
        report = {"recorded_at": datetime.now(timezone.utc).isoformat(),
                  "source_sha256": {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in source_files},
                  "machine": {"cpu": cpu, "platform": platform.platform(), "python": platform.python_version(),
                              "mujoco": mujoco.__version__, "numpy": np.__version__},
                  "method": {"physics_duration_s": 20, "repeats": args.repeats, "route_seeds": args.seeds,
                             "rendering": False, "physics_timing": "C-batched mj_step, no logging, compile/reset excluded",
                             "order": "seeded randomized interleaving of configurations",
                             "commands_rad_s": COMMANDS, "command_duration_s": 2,
                             "terrain": "129x129 heightfield over 6x6m, up to 12mm undulations, flat launch pad",
                             "route_timing": "Python environment + baseline controller + path capture; excludes rendering, reset and PPO"},
                  "results": results, "comparisons": comparisons}
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2) + "\n")
        print(json.dumps(comparisons, indent=2), flush=True)
        print(f"Saved {args.output}", flush=True)
    finally:
        for env in envs.values():
            env.close()


if __name__ == "__main__":
    main()
