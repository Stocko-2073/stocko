# Wheel lug benchmark

These recorded results predate the velocity-ramp braking correction from
8 to 2 turns/s². Waypoint timings and trajectories describe the old ramp;
rerun the benchmark before using them to assess current stopping behavior.
The direct-command physics measurements bypass the ramp and are unaffected
by that correction.

## Conclusion

Simplified lug contacts are practical in the tested scenes. Keep the 2 ms timestep for initial navigation experiments; lug contacts are now the default, with smooth contacts available explicitly. These results establish computational usability, not physical accuracy on grass or soil.

## Measured performance

Headless CPU simulation on this ARM64 Mac, MuJoCo 3.13.0. Exact CPU model was unavailable inside the sandbox. A real-time factor of 60 means 60 simulated seconds per wall-clock second.

| Contacts / terrain / timestep | Physics × real time | Controller + environment × real time | Policy steps/s | Route successes |
|---|---:|---:|---:|---:|
| smooth/flat/0.002 | 81.5 | 57.4 | 2872 | 5/5 |
| lugs/flat/0.002 | 65.7 | 47.8 | 2388 | 5/5 |
| lugs/flat/0.001 | 36.8 | 28.6 | 1432 | 5/5 |
| smooth/bumps/0.002 | 67.1 | 46.7 | 2333 | 5/5 |
| lugs/bumps/0.002 | 63.1 | 45.1 | 2254 | 5/5 |
| lugs/bumps/0.001 | 33.7 | 25.7 | 1287 | 5/5 |

## Cost of lugs at 2 ms

- **flat:** 24.0% more physics time per simulated second; 20.3% more controller/environment time per policy step.
- **bumps:** 6.4% more physics time per simulated second; 3.5% more controller/environment time per policy step.

These percentages describe increased execution time, not percentage loss of throughput. The uneven-ground case has a smaller relative overhead because smooth-cylinder heightfield collision is already more expensive, and the two wheel models produce different contact histories. This explanation is an interpretation of the measurements.

## Stability and timestep sensitivity

| Configuration | Mean / peak contacts | Peak lug contacts | Maximum contact penetration, mm | Solver warnings |
|---|---:|---:|---:|---:|
| smooth/flat/0.002 | 7.69 / 8 | 0 | 0.127 | 0 |
| lugs/flat/0.002 | 8.10 / 12 | 8 | 0.145 | 0 |
| lugs/flat/0.001 | 8.10 / 12 | 8 | 0.142 | 0 |
| smooth/bumps/0.002 | 4.89 / 17 | 0 | 0.380 | 0 |
| lugs/bumps/0.002 | 4.93 / 17 | 12 | 0.422 | 0 |
| lugs/bumps/0.001 | 5.01 / 17 | 12 | 0.450 | 0 |

All diagnostic runs remained finite and upright, and all 30 seeded waypoint runs completed. Only a fraction of the 80 added lug shapes touch the ground at once. The diagnostic command sequence includes forward driving, arcs, pivots, reversing, and stopping.

Reducing the lug timestep from 2 ms to 1 ms also completed every route, but does not produce identical trajectories:
- flat: per-run XY RMS differences 4.0–11.9 mm; worst same-time XY difference 29.7 mm.
- bumps: per-run XY RMS differences 1.0–14.5 mm; worst same-time XY difference 37.9 mm.

These compare matching 50 Hz control times over each pair of runs’ common duration, including accumulated differences in waypoint timing. Both variants settle for 0.3 simulated seconds. This is a sensitivity check, not proof of timestep convergence. The 2 ms model is useful for these 120 mm-tolerance goals; precise impact or traction studies need further checks.

## Method and limits

- Seven warmed repetitions of identical 20-second control sequences, randomized interleaving of configurations; median timings reported.
- C-batched physics excludes compilation, reset, rendering, Python diagnostic loops, and PPO. Route timings include Python environment stepping, baseline control, and path capture, but exclude reset, rendering, and neural-network computation.
- Diagnostics run separately so contact logging does not distort physics timing. Physics timings were collected without concurrent tests or training from this task.
- Five route seeds per configuration; identical 50 Hz policy rate, friction, solver settings, mass and inertia. Smaller timestep is tested only for the lug model.
- Flat plane versus a deterministic 129×129 heightfield spanning 6×6 m, up to 12 mm high, with a flat launch pad. No deformable soil or discrete rocks.
- Lugs are unchamfered CAD bounding boxes, with a smaller core cylinder; exact tread faces and core chamfers are omitted. No extra bodies or joints.
- Results are specific to these trajectories, terrain resolution, CPU backend, and current contact settings. They do not predict GPU-batched training or full PPO throughput.

## Reproduce

From `sim/`:

```sh
uv run python -m ubot_sim.benchmark --output benchmarks/lugs.json
uv run python -m ubot_sim.viewer --waypoints --wheel-contact lugs --terrain bumps
```

[Raw timings, stability metrics, source hashes, and route results](lugs.json).
