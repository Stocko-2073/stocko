"""Reproduce opt-in lawn-density navigation, coasting and timing checks."""
from dataclasses import asdict
import json
from pathlib import Path
from time import perf_counter
import mujoco
from ubot_sim.canopy import GrassCanopy
from ubot_sim.rolling_benchmark import coast_run
from ubot_sim.surface_evaluation import RouteMetrics
from ubot_sim.waypoints import UBotWaypointsEnv


def main():
    runs = []
    for density in (None, 4000, 20000, 36000):
        for wheel in ('smooth', 'lugs'):
            for timestep in (0.001, 0.002):
                settings = GrassCanopy(shoot_density=density)
                with UBotWaypointsEnv(surface='short_grass', grass_canopy=settings,
                                      wheel_contact=wheel, timestep=timestep, max_steps=2500) as env:
                    observation, _ = env.reset(seed=0, options={'yaw': 0})
                    metrics = RouteMetrics(env, observation)
                    start = perf_counter()
                    while not metrics.done:
                        metrics.step()
                    wall = perf_counter() - start
                    route = metrics.report()
                    coast = coast_run(env)
                    runs.append(dict(canopy=asdict(settings), wheel=wheel, timestep=timestep,
                                     route=route, coast=coast, route_wall_seconds=wall,
                                     route_realtime_factor=route['elapsed_seconds'] / wall))
                    print(density, wheel, timestep, route['is_success'], flush=True)
    report = dict(mujoco=mujoco.__version__, seed=0, render_enabled=False, runs=runs)
    Path('benchmarks/canopy-density.json').write_text(json.dumps(report, indent=2) + '\n')
    if any(not r['route']['is_success'] or r['route']['warning_count'] or
           not r['coast']['finite'] or r['coast']['warning_count'] for r in runs):
        raise RuntimeError('Density experiment failed navigation or stability checks')


if __name__ == '__main__':
    main()
