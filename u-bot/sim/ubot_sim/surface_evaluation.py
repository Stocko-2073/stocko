"""Compare navigation, tracking, contact slip, and stops across every preset."""
import argparse
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import platform

import mujoco
import numpy as np

from ubot_sim.contact_model import SURFACE_PRESETS
from ubot_sim.env import baseline_action
from ubot_sim.waypoints import DEFAULT_ROUTE, UBotWaypointsEnv

ROUTES = {"five_waypoints": DEFAULT_ROUTE, "out_and_back": [[1.8, 0], [0, 0]]}


def segment_distance(point, start, end):
    """Distance to the finite nominal XY leg, including its endpoints."""
    delta = np.asarray(end) - start
    length2 = float(delta @ delta)
    fraction = np.clip((np.asarray(point) - start) @ delta / length2, 0, 1) if length2 else 0
    return float(np.linalg.norm(point - (np.asarray(start) + fraction * delta)))


def tangential_speed(model, data, contact, body, jacobian):
    """Speed of a robot material point along its stationary contact surface."""
    mujoco.mj_jac(model, data, jacobian, None, contact.pos, body)
    local_velocity = contact.frame.reshape(3, 3) @ (jacobian @ data.qvel)
    return float(np.linalg.norm(local_velocity[1:]))


class RouteMetrics:
    """A 50 Hz baseline rollout with shared metrics for the report and video."""
    def __init__(self, env, observation):
        self.env, self.observation = env, observation
        self.start = env.data.xpos[env.base, :2].copy()
        self.previous = self.start.copy()
        self.path_length = 0.0
        self.tracking = []
        self.slip = []
        self.slip_steps = 0
        self.stops = []
        self.brake = None
        self.done = False
        self.info = {"is_success": False, "failed": False, "waypoints_reached": 0}
        self.truncated = False
        self.jacobian = np.zeros((3, env.model.nv))
        self.force = np.zeros(6)
        self.drive_geoms = {g for g in range(env.model.ngeom)
                            if env.model.geom(g).name.startswith(
                                ("left_tire", "right_tire", "left_lug", "right_lug"))}

    def step(self):
        if self.done:
            raise RuntimeError("cannot advance a completed evaluation")
        env = self.env
        leg = env.waypoint_index
        action = baseline_action(self.observation)
        if self.brake is None and not np.any(action):
            self.brake = {"command_seconds": float(env.data.time),
                          "entry_speed_mps": float(np.linalg.norm(env._state()[1][3:5])),
                          "path_at_command_m": self.path_length}
        self.observation, _, terminated, self.truncated, self.info = env.step(action)
        xy = env.data.xpos[env.base, :2].copy()
        self.path_length += float(np.linalg.norm(xy - self.previous))
        self.previous = xy
        start = self.start if leg == 0 else env.waypoints[leg - 1]
        self.tracking.append(segment_distance(xy, start, env.waypoints[leg]))
        count = 0
        for i, contact in enumerate(env.data.contact):
            pair = (int(contact.geom1), int(contact.geom2))
            wheel = next((g for g in pair if g in self.drive_geoms), None)
            if wheel is None:
                continue
            ground = pair[1] if wheel == pair[0] else pair[0]
            if env.model.geom_bodyid[ground] != 0 or contact.efc_address < 0:
                continue
            mujoco.mj_contactForce(env.model, env.data, i, self.force)
            if self.force[0] <= 1e-6:
                continue
            self.slip.append(tangential_speed(env.model, env.data, contact,
                                             env.model.geom_bodyid[wheel], self.jacobian))
            count += 1
        self.slip_steps += bool(count)
        if self.info["waypoint_reached"]:
            stop = {"waypoint": leg + 1, "arrival_seconds": float(env.data.time),
                    "goal_error_m": float(np.linalg.norm(xy - env.waypoints[leg])),
                    "arrival_speed_mps": float(np.linalg.norm(env._state()[1][3:5]))}
            stop.update(self.brake or {"command_seconds": None, "entry_speed_mps": None})
            stop["travel_after_command_m"] = (self.path_length - stop.pop("path_at_command_m")
                                                if self.brake else None)
            stop["settle_seconds"] = (float(env.data.time) - self.brake["command_seconds"]
                                      if self.brake else None)
            self.stops.append(stop)
            self.brake = None
        self.done = bool(terminated or self.truncated)
        return self.info

    def report(self):
        def rms(values):
            return float(np.sqrt(np.mean(np.square(values)))) if values else None
        return {"is_success": bool(self.info["is_success"]), "failed": bool(self.info["failed"]),
                "truncated": bool(self.truncated), "waypoints_reached": self.info["waypoints_reached"],
                "elapsed_seconds": float(self.env.data.time),
                "completion_seconds": float(self.env.data.time) if self.info["is_success"] else None,
                "path_length_m": self.path_length, "tracking_rms_m": rms(self.tracking),
                "tracking_max_m": max(self.tracking, default=None), "slip_rms_mps": rms(self.slip),
                "slip_p95_mps": float(np.percentile(self.slip, 95)) if self.slip else None,
                "slip_contact_samples": len(self.slip), "slip_control_steps": self.slip_steps,
                "control_steps": len(self.tracking), "stops": self.stops,
                "warning_count": sum(int(w.number) for w in self.env.data.warning)}


def markdown_report(report):
    rows = report["runs"]
    lines = ["# Surface route evaluation", "",
             f"{sum(r['is_success'] for r in rows)}/{len(rows)} routes completed; "
             f"{sum(r['warning_count'] for r in rows)} solver warnings. "
             "All current presets use the same baseline controller, routes and seeds.", "",
             "Each row aggregates seeds for one route, wheel model and timestep. "
             "Time is the mean of successful runs only; errors and slip include all runs. "
             "Stop travel averages completed waypoint stops with a recorded zero command.", "",
             "| Surface | Route | Wheels | dt (ms) | Complete | Time (s) | Tracking RMS (mm) | Slip RMS (mm/s) | Stop travel (mm) |",
             "|---|---|---|---:|---:|---:|---:|---:|---:|"]
    def mean(values, scale=1):
        values = [v for v in values if v is not None]
        return f"{np.mean(values) * scale:.2f}" if values else "—"
    keys = sorted({(r['surface'], r['route'], r['wheel_contact'], r['timestep']) for r in rows})
    for surface, route, wheel, dt in keys:
        group = [r for r in rows if (r['surface'], r['route'], r['wheel_contact'], r['timestep'])
                 == (surface, route, wheel, dt)]
        lines.append(f"| {surface} | {route} | {wheel} | {dt * 1000:g} | "
                     f"{sum(r['is_success'] for r in group)}/{len(group)} | "
                     f"{mean([r['completion_seconds'] for r in group])} | "
                     f"{mean([r['tracking_rms_m'] for r in group], 1000)} | "
                     f"{mean([r['slip_rms_mps'] for r in group], 1000)} | "
                     f"{mean([s['travel_after_command_m'] for r in group for s in r['stops']], 1000)} |")
    lines += ["", "## Method and limits", ""]
    lines += [f"- **{key}**: {value}" for key, value in report['method'].items()]
    lines += ["", "The raw JSON includes every run, stop, seed, contact sample count, solver warning count, "
              "software versions, and source hashes. These estimated presets are not calibrated "
              "material measurements. This evaluates the existing baseline controller; it does not "
              "establish hardware accuracy or timestep convergence.", ""]
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("benchmarks/surfaces.json"))
    parser.add_argument("--seeds", type=int, default=3)
    args = parser.parse_args()
    if args.seeds < 1:
        parser.error("--seeds must be positive")
    runs = []
    for surface in sorted(SURFACE_PRESETS):
        for route, points in ROUTES.items():
            for wheel in ("smooth", "lugs"):
                for dt in (0.001, 0.002):
                    with UBotWaypointsEnv(surface=surface, wheel_contact=wheel, timestep=dt,
                                         waypoints=points, max_steps=2250) as env:
                        for seed in range(args.seeds):
                            obs, _ = env.reset(seed=seed, options={"yaw": 0})
                            metrics = RouteMetrics(env, obs)
                            while not metrics.done:
                                metrics.step()
                            runs.append({"surface": surface, "route": route, "wheel_contact": wheel,
                                         "timestep": dt, "seed": seed, **metrics.report()})
                    print(f"Evaluated {surface}/{route}/{wheel}/{dt:g}", flush=True)
    files = [Path(__file__), *[Path(__file__).with_name(n) for n in
             ("contact_model.py", "env.py", "waypoints.py", "elevation.py")],
             Path(__file__).parent / "assets" / "robot.xml"]
    report = {"presets": {name: asdict(value) for name, value in SURFACE_PRESETS.items()},
              "routes": ROUTES, "seeds": list(range(args.seeds)), "runs": runs,
              "versions": {"python": platform.python_version(), "mujoco": mujoco.__version__, "numpy": np.__version__},
              "source_sha256": {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in files},
              "method": {
                  "Sampling": "50 Hz after physics/forward; 45 s episode limit; fixed layout, no domain randomization; reset excluded.",
                  "Completion": "Stop at every waypoint using the existing 12 cm / 0.08 m/s / 0.2 rad/s, 15-control-step arrival test.",
                  "Travel time": "Simulated elapsed time through the final arrival, including turns and required stop dwell; failures have null completion time.",
                  "Tracking": "RMS and maximum XY distance to the active finite nominal route segment, sampled uniformly in time; not distance to the goal.",
                  "Slip": "Tangential speed at loaded drive-wheel contact points against static terrain, from point Jacobians and qvel. Normal force must exceed 1e-6 N. RMS/P95 pool unweighted contacts across 50 Hz samples; no-contact steps are omitted and counted separately. Includes longitudinal and lateral scrubbing, not a slip ratio or a force-weighted measure.",
                  "Stopping": "For each waypoint: first zero wheel-speed target to arrival, entry speed, XY travel during that interval, final goal error and speed. Includes any remaining success dwell and later controller correction; not a passive coast test or guaranteed monotonic deceleration.",
                  "Aggregation": "Table values average per-run RMS metrics across seeds, and completed stop travel across stops; raw values remain in JSON.",
              }}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    args.output.with_suffix(".md").write_text(markdown_report(report))
    print(f"Saved {args.output}: {sum(r['is_success'] for r in runs)}/{len(runs)} complete", flush=True)


if __name__ == "__main__":
    main()
