# Contact rolling friction evaluation

## Findings and decision

Keep `condim=4` as the default until rolling losses are measured on the robot.
`TerrainContact(condim=6, rolling_friction=0.002)` is a useful experimental
setting: it adds substantial rolling resistance at unchanged sliding grip of
0.8 and completed all 12 route runs. It is not a calibrated grass model.
The dim4 baseline and dim6 with 0.0001 m also completed all 12 runs each.
At 0.01 m, all 12 runs timed out at 50 seconds after three waypoints;
do not adopt this value as a general preset.

All 48 routes and separate physics/coast diagnostics reported zero solver
warnings. Physics diagnostics remained finite, with worst penetration 0.563 mm
and minimum upright cosine 0.998. These checks establish fixture usability,
not physical accuracy. At 2 ms, dim6 with 0.0001 m cost 13–30% more physics
time than dim4 across wheel/terrain combinations, with little change in motion.
At 0.002 m it cost 57–147% more. Changed forces and trajectories contribute to
these costs; they are not isolated solver overhead measurements.

## Lugged wheels at 2 ms

Measured on this ARM64 Mac with MuJoCo 3.13.0. Throughput is simulated seconds
per wall-clock second. Route time is the mean of two seeds; 50 s is a timeout.
Coast travel covers three seconds with motors disabled. Entry speed is shown
because rolling resistance also slows the preceding powered run.

| Terrain | Contact setting | Physics × real time | Routes | Route time (s) | Coast entry (m/s) | Coast travel (m) |
|---|---|---:|---:|---:|---:|---:|
| flat | dim4 | 66.1 | 2/2 | 18.70 | 0.330 | 0.669 |
| flat | dim6, 0.0001 m | 50.6 | 2/2 | 18.73 | 0.329 | 0.655 |
| flat | dim6, 0.002 m | 31.6 | 2/2 | 19.24 | 0.303 | 0.132 |
| flat | dim6, 0.01 m | 31.4 | 0/2 | 50.00 | 0.152 | 0.009 |
| bumps | dim4 | 63.2 | 2/2 | 18.73 | 0.312 | 0.358 |
| bumps | dim6, 0.0001 m | 55.7 | 2/2 | 18.73 | 0.310 | 0.358 |
| bumps | dim6, 0.002 m | 40.3 | 2/2 | 19.55 | 0.277 | 0.079 |
| bumps | dim6, 0.01 m | 37.2 | 0/2 | 50.00 | 0.139 | 0.009 |

At 0.002 m, lugged wheels met the coast settling criterion after 0.98 s on flat
ground and 0.62 s on bumps; the baseline did not meet it within three seconds.
Smooth-wheel coast travel likewise fell from 0.780 to 0.141 m on flat ground
and from 0.588 to 0.092 m on bumps. All configurations are in the raw report.

## Timestep sensitivity

Halving the lug timestep preserved every route success/timeout outcome.
For 0.002 m rolling friction, same-time route XY RMS differences were
1.8–10.2 mm on flat ground and 16.5–19.9 mm on bumps, with maximum differences
22.5 and 48.4 mm. At 0.01 m the bumpy route diverged by up to 446 mm.

Passive coasting on bumps is more sensitive than waypoint completion. At
0.002 m, travel changed from 0.079 to 0.083 m and settling time from 0.62 to
0.96 s when halving the timestep. With dim4, bumpy coast travel changed from
0.358 to 0.345 m. These are not precise stopping-distance predictions;
heightfield/lug interaction and low-speed settling need finer timestep and
hardware checks.

## Method

Measurements were refreshed on 2026-09-16 against the current terrain-aware
spawn and contact code. The raw report includes source hashes, including the
elevation helper used during reset.

The sweep holds sliding grip at 0.8, torsional friction at 0.002 m, and contact
compliance fixed. It compares `condim=4` with `condim=6` at rolling coefficients
0.0001, 0.002, and 0.01 m. MuJoCo adds resistance to rotation about the two
contact tangent axes with six-dimensional contacts; the rolling coefficient is
unused at four dimensions. See [MuJoCo contact dimensions](https://mujoco.readthedocs.io/en/stable/XMLreference.html#body-geom-condim).

The 24 configurations cover flat/bumps terrain, smooth wheels at 2 ms, and lugged
wheels at 2 ms and 1 ms. All policy updates remain at 50 Hz. Navigation uses the
corrected 8 turns/s² acceleration and 2 turns/s² braking envelope. The default
five-waypoint route runs with two initial-pose seeds and a 50-second limit.

Three warmed physics repetitions run in seeded randomized order using the same
20-second direct-command sequence as the [lug benchmark](README.md). Physics
timing excludes compilation, reset, logging, rendering, and Python control.
Separate diagnostic runs collect contact counts, penetration, uprightness,
finite-state checks, and solver warnings. No tests or rendering from this task
run concurrently with timing. Results describe this CPU run, not training speed.

The coasting diagnostic drives forward at 0.5 turns/s for two seconds, then
disables both motor servos for three seconds. It verifies zero actuator force
throughout coasting. Existing bearing damping, caster dynamics, gravity, and
contact forces remain. Reported travel is accumulated planar path length over
three seconds, not necessarily distance to rest. Entry speeds are measured
rather than equalized; this is a system-response comparison, not a material fit.
A settling time requires speed below 0.02 m/s for ten consecutive control periods.

These coefficients are estimates, not calibrated concrete or grass properties.
Rolling friction affects caster rollers as well as drive wheels. The finite
coast window, initial caster alignment, and terrain can affect the outcome.
Timestep comparisons use matching control times over each route pair's common
duration; they include differences in waypoint timing and do not establish
numerical convergence.

## Reproduce

From `sim/`:

```sh
uv run python -m ubot_sim.rolling_benchmark
```

[Raw measurements, configuration, versions, and source hashes](rolling.json).
