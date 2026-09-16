"""Evaluate contact rolling friction: throughput, navigation, and passive coasting."""
import argparse
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import platform
import statistics

import mujoco
import numpy as np

from ubot_sim.benchmark import physics_run, route_run
from ubot_sim.contact_model import TerrainContact
from ubot_sim.waypoints import UBotWaypointsEnv

SURFACES = {
    "dim4": TerrainContact(),
    "dim6-default": TerrainContact(condim=6),
    "dim6-0.002": TerrainContact(condim=6, rolling_friction=0.002),
    "dim6-0.01": TerrainContact(condim=6, rolling_friction=0.01),
}


def coast_run(env):
    """Drive for two seconds, then disable both motor servos for three seconds.

    Bearing damping and all contact forces remain. Entry speed is measured,
    not forced, so this is an end-to-end diagnostic rather than a coefficient fit.
    """
    env.reset(seed=0, options={"yaw": 0})
    for _ in range(100):
        env.step([0.5, 0.5])
    start = env.data.xpos[env.base, :2].copy()
    entry_speed = float(np.linalg.norm(env._state()[1][3:5]))
    gains, biases = env.model.actuator_gainprm.copy(), env.model.actuator_biasprm.copy()
    path_length, stopped_at = 0.0, None
    previous = start.copy()
    speeds = []
    try:
        env.model.actuator_gainprm[:] = 0
        env.model.actuator_biasprm[:] = 0
        env.data.ctrl[:] = 0
        for step in range(150):
            if env.canopy is None:
                mujoco.mj_step(env.model, env.data, nstep=env.frame_skip)
            else:
                for _ in range(env.frame_skip):
                    env._physics_step()
            mujoco.mj_forward(env.model, env.data)
            assert np.all(env.data.actuator_force == 0), "Coasting must not include servo braking"
            xy = env.data.xpos[env.base, :2].copy()
            path_length += float(np.linalg.norm(xy - previous))
            previous = xy
            speed = float(np.linalg.norm(env._state()[1][3:5]))
            speeds.append(speed)
            if len(speeds) >= 10 and max(speeds[-10:]) < 0.02 and stopped_at is None:
                stopped_at = (step + 1) * env.dt
        contacts = [c for c in env.data.contact if any(
            env.model.geom_bodyid[g] == 0 for g in (c.geom1, c.geom2))]
        return {"entry_speed_mps": entry_speed, "path_length_3s_m": path_length,
                "final_speed_mps": speeds[-1], "settled_below_0.02_mps_seconds": stopped_at,
                "contact_dimensions": sorted({int(c.dim) for c in contacts}),
                "contact_friction": contacts[0].friction.tolist() if contacts else None,
                "finite": bool(np.isfinite(env.data.qpos).all() and np.isfinite(env.data.qvel).all()),
                "warning_count": sum(int(w.number) for w in env.data.warning)}
    finally:
        env.model.actuator_gainprm[:] = gains
        env.model.actuator_biasprm[:] = biases


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("benchmarks/rolling.json"))
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--seeds", type=int, default=2)
    args = parser.parse_args()
    if args.repeats < 3 or args.seeds < 1:
        parser.error("Use at least three timing repeats and one route seed")
    envs, results, paths = {}, {}, {}
    try:
        for terrain in ("flat", "bumps"):
            for wheel, dt in (("smooth", 0.002), ("lugs", 0.002), ("lugs", 0.001)):
                for name, surface in SURFACES.items():
                    key = f"{wheel}/{terrain}/{dt:g}/{name}"
                    env = UBotWaypointsEnv(wheel_contact=wheel, terrain=terrain,
                                           timestep=dt, terrain_contact=surface, max_steps=2500)
                    envs[key] = env
                    env._benchmark_lugs = {i for i in range(env.model.ngeom)
                                           if "_lug_" in (env.model.geom(i).name or "")}
                    physics_run(env)
                    results[key] = {"surface": asdict(surface), "physics_seconds": [], "routes": []}
                    paths[key] = []
        print("Warmed all 24 configurations", flush=True)
        rng = np.random.default_rng(42)
        for repeat in range(args.repeats):
            for key in rng.permutation(list(envs)):
                results[key]["physics_seconds"].append(physics_run(envs[key]))
            print(f"Timing repeat {repeat + 1}/{args.repeats}", flush=True)
        for seed in range(args.seeds):
            for key in rng.permutation(list(envs)):
                route, path = route_run(envs[key], seed)
                results[key]["routes"].append(route)
                paths[key].append(path)
            print(f"Route seed {seed} finished", flush=True)
        for key, env in envs.items():
            row = results[key]
            row["physics_real_time_factor"] = 20 / statistics.median(row["physics_seconds"])
            row["coast"] = coast_run(env)
            row["diagnostics"] = physics_run(env, diagnostics=True)
            print(f"Diagnosed {key}", flush=True)
        comparisons = {}
        for terrain in ("flat", "bumps"):
            for name in SURFACES:
                differences = []
                for coarse, fine in zip(paths[f"lugs/{terrain}/0.002/{name}"],
                                        paths[f"lugs/{terrain}/0.001/{name}"]):
                    n = min(len(coarse), len(fine))
                    errors = np.linalg.norm(coarse[:n] - fine[:n], axis=1)
                    differences.append({"rms_xy_m": float(np.sqrt(np.mean(errors**2))),
                                        "max_xy_m": float(errors.max())})
                comparisons[f"{terrain}/{name}"] = differences
        files = [Path(__file__), *[Path(__file__).with_name(n) for n in
                                  ("benchmark.py", "contact_model.py", "env.py", "waypoints.py", "elevation.py")],
                 Path(__file__).parent / "assets" / "robot.xml"]
        report = {"recorded_at": datetime.now(timezone.utc).isoformat(),
                  "machine": {"platform": platform.platform(), "python": platform.python_version(),
                              "mujoco": mujoco.__version__, "numpy": np.__version__},
                  "source_sha256": {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in files},
                  "method": {"repeats": args.repeats, "route_seeds": args.seeds,
                             "route_limit_seconds": 50, "physics_seconds": 20,
                             "timing": "Warmed C-batched physics; randomized order; no concurrent task tests/rendering",
                             "coast": "2s drive at 0.5 turns/s then 3s with both servos disabled; bearing damping retained",
                             "diagnostics": "Separate untimed physics and coast runs",
                             "rolling_units": "metres; estimates, not fitted material properties"},
                  "results": results, "lug_timestep_path_differences": comparisons}
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2) + "\n")
        print(f"Saved {args.output}", flush=True)
    finally:
        for env in envs.values():
            env.close()


if __name__ == "__main__":
    main()
