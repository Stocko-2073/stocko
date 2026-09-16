# U-bot in MuJoCo

Planned terrain work: [terrain TODO](TODO.md).

A working MuJoCo model of `../u-bot.scad` and a Gymnasium **navigation-to-a-goal**
environment. The included visual meshes are exported from the current CAD.
Two driven wheels, two free caster swivels, and four independent caster rollers
move dynamically on a free chassis. OpenSCAD is only needed to rebuild meshes.

![MuJoCo preview](preview.png)

## Run

From this directory:

```sh
uv sync --python 3.12 --extra train --extra dev
uv run python -m ubot_sim.demo
```

Watch the baseline navigate:

```sh
uv run python -m ubot_sim.viewer
```

The launcher works across platforms. On macOS it invokes `mjpython` and
resolves the Python shared-library path for `uv`-managed Python installations.
Headless simulation and training need no graphics context; rendering requires
working graphics drivers. Linux servers can use `MUJOCO_GL=egl` for offscreen
rendering when an EGL driver is installed.

Train PPO (CPU; four sequential environments by default):

```sh
uv run python -m ubot_sim.train --steps 1000000 --randomize
uv run python -m ubot_sim.viewer --policy runs/navigation/best/best_model.zip
```

Checkpoints, evaluation results, and episode logs go under `runs/navigation/`.
The final policy is `runs/navigation/final.zip`. `--steps` is a minimum;
PPO completes its current rollout. One million steps is a starting budget,
not a demonstrated convergence guarantee. The included baseline is a geometric
controller; no trained, successful policy is shipped.

## Environment API

```python
import gymnasium as gym
import ubot_sim  # registers the environment

env = gym.make("UBotNavigation-v0", randomize=True)
obs, info = env.reset(seed=42)
# Or choose a world-frame goal (metres) and initial heading (radians):
obs, info = env.reset(seed=42, options={"goal": [1.5, 0.5], "yaw": 0.0})
obs, reward, terminated, truncated, info = env.step([0.3, 0.3])
env.close()
```

- Frame: **X forward, Y left, Z up**; SI units. CAD millimetres transform to
  `(-CAD_Y, CAD_X, CAD_Z) / 1000`. The open end of the U is forward.
- Actions: `[left, right]` wheel velocity targets in `[-1, 1]`, scaled to
  ±2π rad/s (one output turn/s). Both positive means forward. Targets ramp
  at 8 output turns/s² when speeding up and 2 turns/s² when slowing down,
  matching the firmware's default velocity-mode envelope. Reversals brake
  through zero before accelerating in the new direction. A zero target snaps
  commands below 205/4096 turns/s (about 0.05) to standstill. The ramp runs at
  the physics timestep; actual wheel motion still depends on servo torque and
  contact forces.
- Physics: 500 Hz; policy: 50 Hz. Torque-limited wheel velocity servos represent
  the existing wheel controller, with the 40:12 transmission absorbed into
  output-side dynamics. Individual stepper steps and gear contacts are omitted.
- Goals: 0.75–2.5 m from the initial origin; randomized heading and caster
  angles. Success requires distance <0.12 m, planar speed <0.08 m/s, and yaw
  speed <0.2 rad/s for 0.3 s. Episodes end on success, tipping, or leaving a
  6 m radius; the 30 s time limit is a truncation.
- Reward per policy step: `10 × distance progress − 0.01 − 0.001 × sum(action²)`,
  plus 20 for success or minus 10 for failure.
- `info`: `distance`, `is_success`, and (after stepping) `failed`.

The 22 float32 observations, in order:

| Indices | Values |
|---|---|
| 0–1 | Goal displacement in robot frame, m |
| 2–3 | Robot-frame planar velocity, m/s |
| 4–6 | Robot-frame angular velocity, rad/s |
| 7–9 | World up expressed in robot frame |
| 10–11 | Left/right wheel velocity divided by 2π |
| 12–13 | Sine of left/right caster swivel angles |
| 14–15 | Cosine of left/right caster swivel angles |
| 16–17 | Caster swivel rates, rad/s |
| 18–19 | Ramped wheel commands divided by 2π |
| 20 | Elapsed episode fraction |
| 21 | Goal dwell fraction |

Goal pose, velocity, and attitude currently use simulator ground truth. Wheel
and caster encoder channels plus an ideal IMU are also exposed in MJCF. A real
robot needs a localization/velocity estimate and matching observation pipeline;
this environment does not implement firmware deployment or sensor noise.

## Geometry and dynamics

`build_model.py` is the source for the base template `ubot_sim/assets/robot.xml`.
`ubot_sim/contact_model.py` applies the selected wheel contacts and terrain
when loading it; the default runtime model uses lugs. The template itself
retains smooth contacts for comparison.

| Parameter | Value / provenance |
|---|---|
| Drive rolling radius | 107.5 mm, CAD tread and mechanism notes |
| Drive tread-center track | 302.7 mm = 2 × (128 + 3.35 + 20) |
| Caster swivel centers | X = −161.25 mm, Y = ±104.75 mm |
| Caster axle below drive axle | 77.5 mm |
| Caster trail / roller radius | 19 mm / 30 mm |
| Base mass | **Allocated** 3.263 kg: measured total minus estimated moving parts |
| Each drive wheel / caster fork / roller | **Estimated** 0.25 / 0.08 / 0.03 kg |
| Total mass | **Measured support-load sum** 4.043 kg ≈ 8.91 lb, postage scale (2026-09-15) |
| Whole-robot horizontal COM | **Inferred** 65.2 mm behind drive axle datum, 4.1 mm left of center, with casters rearward |
| Wheel torque limit / velocity gain | **Estimated** 0.8 N·m / 0.35 N·m·s/rad |
| Sliding friction | **Estimated** 0.8 |

The firmware's nominal 263 mm track is close to the wheel module/axle datum
spacing (262.7 mm). CAD treads sit another 20 mm outward on each side. This
model uses **302.7 mm** at the tread centers; measure the assembled robot before
reusing either value for hardware odometry.

### Static weighing calibration

The user weighed each support on a postage scale with the other three supports
on equal-height boxes: right caster 756 g, left caster 709 g, right drive
1218 g, left drive 1360 g. Their sum is 4043 g; 63.8% is on the drive wheels
and 36.2% on the casters. These are supported loads, not wheel component masses.
This supersedes the earlier bathroom-scale reading of 8.4 lb (3810 g), a
233 g difference. Neither scale's accuracy nor repeatability has been verified;
the extra displayed digits do not establish measurement precision. Sequential
readings assume consistent support heights, caster positions, and robot setup.

Horizontal COM is computed as `sum(load * contact_position) / sum(load)`.
The user confirmed caster wheels behind their stems during weighing, placing
their roller axles at X = -180.25 mm. Each twin-roller pair's resultant contact
is approximated by its midpoint. Contact-patch distribution and measurement
error add uncertainty; the inferred 4.1 mm left offset is a small asymmetry,
not a precision measurement.
The base body's COM is adjusted after subtracting estimated wheel/fork/roller
mass moments, so the whole robot matches this estimate with both swivel joints
at pi radians (rearward casters). The default CAD pose points the casters
forward; their moving mass naturally shifts the whole-robot COM in that pose.
Individual support loads are not forced to match: compliance and contact pose
also determine the load split on a four-support rigid chassis.

Individual part masses, COM height, and rotational inertias remain estimates.
The base inertia was scaled with its revised mass; its value about the revised
COM is still an approximation. The control board is pending;
reweigh with the board and final operating battery/payload configuration before
treating this as the operating mass. Scale accuracy has not been established.

COM height, inertias, bearing drag, friction, and servo parameters
remain initial estimates, not identified physical properties. `--randomize`
scales sliding friction by 0.7–1.3 and base mass/inertia by 0.8–1.2 per episode.
It does not establish transfer to hardware.

Visuals use exported CAD chassis, wheel, fork, and roller meshes. Small hardware,
encoders, and the rotating pinions/axles are simplified or omitted. Contact uses
box-shaped lugs on cylindrical wheel cores, ellipsoids for rounded caster rollers, and three
chassis boxes that preserve the U opening. Visual meshes have no contact or
mass contribution; explicit inertias avoid treating the hollow printed chassis
as solid plastic. Robot self-contact is disabled. Viewer geom group 3 contains
the transparent collision proxies; group 2 contains CAD meshes.

The initial caster pose follows the CAD's 180° assembly orientation; reset
randomizes swivel angles so the policy must handle alignment transients.
The default world is flat, obstacle-free ground; an optional uneven heightfield
and static obstacle proxies are available. Calibrated grass/soil, tool payloads, and
obstacle sensing are future extensions.

## Rebuild and verify

```sh
# Requires OpenSCAD with the Manifold backend, BOSL2, and ../lib CAD dependencies.
uv run python export_meshes.py
uv run python build_model.py
uv run pytest

# A short pipeline check, not sufficient training:
uv run python -m ubot_sim.train --steps 1024 --envs 2 --output runs/smoke
```

Export uses temporary copies of the CAD to omit its top-level assembly without
modifying `u-bot.scad`. The exporter records CAD input and mesh hashes in
`ubot_sim/assets/cad_manifest.json`. BOSL2 is an external installation and is
not vendored or version-locked. Re-export after CAD changes; update dimensions
in `build_model.py`, lug dimensions in `ubot_sim/contact_model.py`, and the
radius/track constants in `ubot_sim/env.py` if the
mechanism changes. Geometry dimensions are explicitly transcribed, not parsed
automatically from OpenSCAD.

Validated here with Python 3.12, MuJoCo 3.13.0, Gymnasium 1.3.0 and SB3 2.9.0:
59 tests pass, including Gymnasium API/seeding, drive direction, stable contact,
action ramp/time limits, randomized goal-reaching, waypoint continuity, and
lug contacts on flat and uneven terrain. A 1,024-step
PPO run saved a reloadable checkpoint. RGB rendering was checked on macOS.

References: [MuJoCo model format](https://mujoco.readthedocs.io/en/latest/XMLreference.html),
[MuJoCo Python viewer](https://mujoco.readthedocs.io/en/latest/python.html),
[Gymnasium custom environments](https://gymnasium.farama.org/introduction/create_custom_env/).

## Continuous waypoints and video

Run the five-waypoint route without resetting between goals:

```sh
uv run python -m ubot_sim.viewer --waypoints
# Headless:
uv run python -m ubot_sim.demo --waypoints
```

The robot stops briefly at each waypoint and continues with its physical state,
controls, caster angles, simulation time, and route time budget intact. Only
completion of the entire route terminates successfully. The default route is
`[[0.8, 0], [1, 0.8], [0.2, 1], [-0.5, 0.5], [0, 0]]`, in metres.
Pass `--route path/to/route.json` to use your own JSON list of `[x, y]` positions.
The environment is also available as `gym.make("UBotWaypoints-v0")`.

Record a shareable video (requires FFmpeg on PATH and working graphics):

```sh
uv sync --extra video --extra train --extra dev
uv run python -m ubot_sim.record --output videos/u-bot-waypoints.mp4
```

Recording uses the geometric baseline controller, not a trained policy. Output
is silent 1920×1080 H.264 MP4, 25 fps, real-time playback, with a one-second
opening hold and two-second closing hold. A fixed camera shows the route,
actual trajectory, active target, and completed-waypoint count. Adjacent PNGs
provide opening/closing stills; a JSON report records waypoint arrival times,
route coordinates, and completion status. Use `--preview-only` to check framing,
`--width 1280 --height 720` for a smaller render, or `--route` for a custom route.
The video is created locally for posting; recording does not publish it.
The included `videos/u-bot-waypoints.mp4` predates the default change and used
smooth wheel contacts. New recordings use lugs unless `--wheel-contact smooth`
is supplied.

Waypoint tests additionally verify continuous time across all five goals,
completion, reset behavior, and route input validation.

## Wheel contacts and performance benchmark

Simplified physical lugs are the default for environments, demos, training, and
recording. Run the default or select smooth cylinders explicitly:

```sh
uv run python -m ubot_sim.viewer --waypoints
uv run python -m ubot_sim.viewer --waypoints --wheel-contact smooth
uv run python -m ubot_sim.viewer --waypoints --wheel-contact lugs --terrain bumps
uv run python -m ubot_sim.train --wheel-contact lugs
```

`--wheel-contact` and `--terrain` also work with `demo` and `record`. Python
constructors accept `wheel_contact="lugs"`, `terrain="bumps"`, and optionally
`timestep=0.001` (policy control remains 50 Hz).

Lug mode replaces each 107.5 mm-radius smooth contact cylinder with a
102.5 mm-radius, 14 mm-wide core and 40 rigidly attached boxes. Box dimensions
and placement follow the two staggered CAD rows: 17 × 7 × 12/11 mm, a 9° row
phase offset, and 20 lugs per row. The boxes omit the CAD's chamfers; the core
also omits its edge chamfers. These are conservative bounding approximations,
not exact contact meshes. The 80 extra geoms add no bodies, joints, mass, or
inertia. CAD visual meshes are unchanged. No rolling-friction or motor tuning
changes are bundled with this comparison.

`bumps` is a deterministic benchmark fixture, not a calibrated surface preset:
a 129×129 heightfield across 6×6 m with smooth undulations up to 12 mm and a
flat launch pad. It exercises uneven contacts without simulating soil or grass.

### Concrete surface preset

Use `surface="concrete"` with either environment or `gym.make`, or select it
from the demo, viewer, recorder, or training CLI:

```sh
uv run python -m ubot_sim.viewer --waypoints --surface concrete
uv run python -m ubot_sim.record --surface concrete --width 1280 --height 720 --output videos/concrete-showcase.mp4
uv run python -m ubot_sim.train --surface concrete
```

The preset uses a flat plane for relatively smooth concrete, sliding grip 0.8,
torsional friction 0.002 m, and low rolling friction 0.0001 m. It selects
`condim=6` so rolling resistance is active, with contact time constant 0.01 s
and damping ratio 1.0 for firm contact. These are initial estimates, not
measurements of concrete or a calibrated robot/material pair. The plane has
no seams or roughness. Rolling resistance here comes from contact friction;
it does not model motor or bearing losses.

Both smooth and lugged wheels are supported. `randomize=True` scales grip by
0.7–1.3 as usual. Combining the preset with `terrain="bumps"` or a
`terrain_contact` override raises an error; use explicit terrain/contact
settings for custom experiments. Omitting `surface` retains existing defaults.
Training and evaluation receive the same selected preset.

[Watch the concrete showcase](videos/concrete-showcase.mp4): a continuous
five-waypoint run using lugged wheels and the baseline controller, rendered
at 1280×720 and 25 fps. The adjacent JSON records the chosen surface settings,
arrival times, completion, and solver warning count. Tests verify actual
six-dimensional contacts, route completion with both wheel models, seeded
grip randomization, and rejection of conflicting settings.

### Rough concrete surface preset

Select `surface="rough_concrete"` in either environment or `gym.make`, or use
`--surface rough_concrete` with the demo, viewer, recorder, or training CLI:

```sh
uv run python -m ubot_sim.viewer --waypoints --surface rough_concrete
uv run python -m ubot_sim.record --surface rough_concrete --width 1280 --height 720 --output videos/rough-concrete-showcase.mp4
uv run python -m ubot_sim.train --surface rough_concrete
```

The preset combines a deterministic 257×257 heightfield across 6×6 m with
0–4 mm bumps, two raised seam boxes, and one low step block. The heightfield
uses approximately 14–21 cm wavelengths and a flat 0.3 m launch radius,
blending to full roughness by 0.5 m. It is separate from the taller `bumps`
benchmark fixture. The default five-waypoint route crosses all three boxes.

| Feature | Centre XY (m) | Full footprint (m) | Top above Z=0 |
|---|---|---|---|
| Seam | (0.45, 0) | 0.016 × 0.6 | 4 mm |
| Step block | (1.0, 0.4) | 0.4 × 0.12 | 8 mm |
| Seam, yaw 45° | (-0.2, 0.75) | 0.016 × 0.5 | 4 mm |

The boxes extend from Z=0 to their tops, so their local protrusion depends on
the underlying bump height. Geometry provides the roughness; contact grip,
rolling friction, and compliance match `concrete` (grip 0.8, rolling 0.0001 m,
`condim=6`, time constant 0.01 s, damping ratio 1). These are estimated rigid
proxies, not scanned or hardware-calibrated concrete. During development,
6 mm seams stalled smooth wheels at 1 ms; this gentle fixture uses 4 mm seams.

The preset selects its own terrain geometry: leave `terrain`/`--terrain` at
its default and do not supply `terrain_contact`. Flat-ground `TerrainPatch`
rectangles are rejected. You can add extra `TerrainObstacle` objects; they
retain their `terrain_obstacle_*` names, while built-in features use
`surface_obstacle_*`. `randomize=True` changes seeded grip and robot mass as
usual, preserving the fixed heightfield and feature layout.

[Watch the rough-concrete showcase](videos/rough-concrete-showcase.mp4): the
baseline controller completes all five waypoints and contacts all three
features. The video reports contact progress; its JSON records the effective
terrain, feature geometry, first-contact times, route arrivals, and solver
warnings. Tests verify route completion and actual drive-wheel encounters with
both wheel models at 1 ms and 2 ms using seed 0, plus inherited contact settings,
unchanged robot dynamics, deterministic geometry, and conflicting options.

### Terrain contact settings

Python constructors accept a `TerrainContact` for either terrain and wheel model:

```python
from ubot_sim.contact_model import TerrainContact
from ubot_sim.env import UBotNavigationEnv

surface = TerrainContact(sliding_friction=0.2, time_constant=0.02)
env = UBotNavigationEnv(terrain="bumps", terrain_contact=surface)
```

These settings also work with `UBotWaypointsEnv` and `gym.make`. They apply to
the entire ground surface, including drive-wheel, caster, and chassis contacts.
Flat ground also supports local sliding-grip patches (below). Calibrated
preset values remain pending hardware measurements.

| Setting | Default | Meaning |
|---|---|---|
| `sliding_friction` | 0.8 | Dimensionless sliding grip |
| `torsional_friction` | 0.002 m | Resistance to spinning about the contact normal |
| `rolling_friction` | 0.0001 m | Contact rolling resistance; active only with `condim=6` |
| `condim` | 4 | 3: sliding; 4: adds torsion; 6: adds rolling |
| `time_constant` | 0.01 s | Positive-format contact `solref` time constant |
| `damping_ratio` | 1.0 | Positive-format contact `solref` damping ratio |

Ground geoms use priority 1 and robot geoms use priority 0. This makes the
surface select contact friction, dimension, and compliance; equal-priority
friction mixing would otherwise retain the higher wheel coefficient on slippery
ground. See [MuJoCo contact parameters](https://mujoco.readthedocs.io/en/latest/modeling.html#contact-parameters).
The contact impedance is explicitly fixed at `solimp="0.9 0.95 0.001 0.5 2"`.
MuJoCo's default reference-safety setting limits the effective time constant to
at least twice the physics timestep. These are solver settings and estimates,
not measured soil properties; soft contact does not model ground deformation.

Defaults retain the existing contact values. `randomize=True` still scales
sliding friction by 0.7–1.3 from the selected surface on each reset, reproducibly
for a given seed. Other contact settings stay fixed. Selecting `condim=6` enables
experimentation; its rolling behavior and performance still need evaluation.

### Local slippery patches

Add `TerrainPatch` rectangles to either environment or `gym.make`. This example
puts the left drive wheel on low grip and the right on dry ground when spawned
at the origin facing +X (`reset(options={"yaw": 0})`):

```python
from ubot_sim.contact_model import TerrainPatch
from ubot_sim.env import UBotNavigationEnv

patch = TerrainPatch(center=(0, 0.5), half_size=(2, 0.5), sliding_friction=0.08)
env = UBotNavigationEnv(surface="concrete", patches=[patch])
env.reset(seed=0, options={"yaw": 0})
```

Coordinates and half-sizes are metres in world XY; rectangles are axis-aligned.
Only sliding friction changes inside a patch. Contact dimension, rolling and
torsional friction, and compliance come from the selected ground settings.
The default patch grip is 0.08, an estimated slippery-surface approximation;
this does not model water or predict measured wet-concrete traction. Obstacles
keep their own explicit or inherited ground contact settings.

Patches require flat terrain and support both smooth and lugged wheels. The
colliding ground is replaced with disjoint boxes covering [-8, 8] m on each
axis, beyond the environment's 6 m failure radius. Every top face is at Z=0:
there is no raised patch and no underlying dry plane contributing duplicate
friction. At a boundary, a wheel can contact both adjacent materials. Patch
interiors must not overlap and must lie strictly inside the ground boundary;
touching edges are allowed. With no patches, the original floor is retained.

`randomize=True` applies the same seeded grip multiplier to ground and patches,
preserving their ratio without compounding on reset. Geometry is fixed. Tests
inspect actual wheel and caster contacts on opposite surfaces, complete a
continuous out-and-back route, and cross dry–slippery–dry ground using both
wheel models at 1 ms and 2 ms physics timesteps.

[Watch the 13-second split-grip showcase](videos/slippery-patch-showcase.mp4):
synchronized drive, brake, and reverse commands on identical ground geometry.
The right panel changes only one rectangle's grip from 0.8 to 0.08. Overlays
show actual left/right contact coefficients, speed, and lateral position;
trails show the drift during reversal. The JSON contains commands, contact
coefficients, paths, surface settings, and solver warning counts. Reproduce with:

```sh
uv run python -m ubot_sim.patch_showcase
```

Requires the video extra, FFmpeg, and working graphics. The output is silent
1280×720 H.264 at 25 fps, with one second of opening hold and two seconds of
closing hold; simulation playback is real time.

### Rocks, roots, seams, and edges

Add static collision proxies using `obstacles` in either environment constructor
or `gym.make`. They work on flat or bumpy ground with either wheel contact model:

```python
from ubot_sim.contact_model import TerrainObstacle

obstacles = [
    TerrainObstacle("rock", position=(0.7, 0.15, 0.02), size=(0.04, 0.03, 0.03)),
    TerrainObstacle("root", position=(1.0, 0, 0.01), size=(0.015, 0.25)),
    TerrainObstacle("seam", position=(1.4, 0, 0.005), size=(0.008, 0.3, 0.005)),
    TerrainObstacle("edge", position=(1.8, 0, 0.01), size=(0.1, 0.3, 0.01)),
]
env = UBotNavigationEnv(obstacles=obstacles)
```

All lengths are metres. `position` is the absolute world centre; `yaw` defaults
to zero and is in radians. Rock sizes are ellipsoid radii. Root sizes are capsule
radius and half the cylindrical segment length; its axis is local Y, with a
hemispherical cap at either end. Seam/edge sizes are box half-extents. Seams
represent raised joints, and edges represent finite step blocks. These are
simple rigid proxies, not scanned rocks or deformable roots.

Place Z explicitly to account for terrain height or embed part of an obstacle.
Reset automatically lifts the robot above terrain and obstacles across its
collision footprint, then lets it settle. Obstacles inherit the selected `TerrainContact` unless given
their own `contact=TerrainContact(...)`; episode friction randomization also
applies to them. They add no robot mass or joints. Collision tests verify drive
wheel encounters, finite simulation state, and the chosen contact parameters;
crossing is not guaranteed, and low-grip obstacles can leave the robot stuck.

[Watch the obstacle showcase](videos/obstacle-showcase.mp4): four synchronized
panels show a rock, root, raised seam, and step block under the same drive and
brake commands. Each panel reports contact detection and body speed. Reproduce
the 8-second, 1280×720 video with `uv run python -m ubot_sim.obstacle_showcase`
(video extra, FFmpeg, and graphics required). The adjacent JSON records obstacle
geometry, sampled positions, contact detection, and solver warnings.

### Reproduce the benchmark

```sh
uv run python -m ubot_sim.benchmark --output benchmarks/lugs.json
```

The benchmark compares smooth/2 ms, lugs/2 ms, and lugs/1 ms on both surfaces.
It times seven repetitions of the same 20-second command sequence, with
configuration order interleaved randomly. Compilation, reset, rendering, and
contact diagnostics are excluded from physics timings. Separate runs collect
contact counts, penetration, orientation, finite-state checks, and warnings.
Five seeded waypoint runs per configuration also measure Python environment
and controller throughput. Timing excludes PPO policy inference/optimization;
it is not an end-to-end training benchmark. The two lug timesteps additionally
compare XY trajectories at matching control times over their common duration.

Results: [benchmark report](benchmarks/README.md), [raw measurements](benchmarks/lugs.json).
Tests also check actual lug-ground contact, unchanged mass/inertia/joints,
route completion on both terrains, and the 50 Hz control rate at a 1 ms
physics timestep. Ramp tests cover acceleration, braking, reversals, and
standstill snapping at both 1 ms and 2 ms. Surface tests inspect actual contact
friction, dimension, and compliance for both wheel models and terrains, plus
seeded randomization and invalid settings. Obstacle tests cover all four kinds,
both terrains and wheel models, placement, and preserved robot dynamics
(59 tests total).

### Terrain contact showcase

[Watch the 19-second grip comparison](videos/terrain-contact-showcase.mp4).
Both panels use the same seeded initial pose and start, brake, turn, and reverse
commands. Only sliding friction changes (0.8 versus 0.08). The overlays show
body speed and ramped wheel commands; trails expose the resulting path difference.
Both runs use the corrected firmware braking envelope. These are estimated
contact values on flat ground, not calibrated dry/wet surface predictions.

```sh
uv run python -m ubot_sim.showcase
```

Requires the video extra, FFmpeg, and working graphics. Output is a 1280×720,
25 fps H.264 MP4 with opening/closing PNGs and a JSON report containing surface
settings, commands, sampled paths/speeds, and solver warning counts.


### Terrain-aware elevation

Spawn height, goal markers, and low-clearance failure checks use the actual
static collision geometry, including heightfields, patches, and obstacles.
`reset(options={"position": [x, y], "yaw": angle})` selects a world XY spawn
in metres; the default remains the origin. The robot starts upright with 1 mm
clearance above conservative collision bounds and settles for 0.3 seconds.
Heightfield bounds include all vertices of overlapping cells; obstacle bounds
include thin seams and roots. This avoids initial penetration but does not
guarantee that a precarious placement will settle stably.

The goal cylinder sits 5 mm above the surface at its centre and updates at
every waypoint. Recorder route markers and trails also follow elevation.
The existing 5 cm minimum body-height check is now relative to terrain beneath
the base; tilt and 6 m radial limits remain in effect. Leaving finite terrain
coverage fails the episode. Spawn/goal centres outside coverage raise
`ValueError`. XY goals, observations, and arrival distances retain their
existing meaning. Queries ignore robot visuals and the goal marker itself.
These controls cover the current horizontal planes, axis-aligned heightfields,
and static obstacle proxies; they do not add slope presets or spawn orientation
alignment.

[Watch the elevation showcase](videos/elevation-showcase.mp4): identical
out-and-back routes at ground level and on a 30 cm platform. Live overlays show
body height, terrain-relative clearance, goal height, and completed stops.
Both runs use seed 0, lugged wheels, the baseline controller, and 2 ms physics.
The adjacent JSON records route arrivals, heights, completion, and warnings.
Reproduce with the video extra, FFmpeg, and graphics access:

```sh
uv run python -m ubot_sim.elevation_showcase
```

Regression tests cover elevated route completion with both wheel models at
1 ms and 2 ms, off-origin heightfield spawns, thin obstacles, waypoint marker
height changes, terrain below world zero, and terrain-relative failure checks.


### Continuous surface transitions

`TerrainRegion` adds a complete contact material inside a flat, axis-aligned
rectangle. Unlike `TerrainPatch`, which changes only grip, a region sets its
own sliding, torsional, and rolling friction, contact dimension, and compliance.
Use regions with either environment or `gym.make`:

```python
from ubot_sim.contact_model import TerrainContact, TerrainRegion
from ubot_sim.waypoints import UBotWaypointsEnv

resistant = TerrainContact(sliding_friction=0.8, rolling_friction=0.002,
                           condim=6, time_constant=0.02, damping_ratio=1.2)
slippery = TerrainContact(sliding_friction=0.12, condim=4)
env = UBotWaypointsEnv(
    surface="concrete",
    regions=[TerrainRegion((0.7, 0), (0.2, 0.7), resistant),
             TerrainRegion((1.4, 0), (0.2, 0.7), slippery)],
    waypoints=[[2, 0], [0, 0]],
)
```

Centres and half-sizes are world XY metres. The selected base surface fills
all remaining ground; regions use their explicit `TerrainContact` without
inheriting its fields. Materials take effect in individual solver contacts,
so drive wheels and casters can touch different materials simultaneously.
At boundaries a wheel can contact both neighbouring tiles. No episode reset,
teleport, or global material switch occurs during a crossing.

Regions and grip-only patches share one partition of the flat ground, covering
[-8, 8] m on both axes with flush, disjoint boxes and no underlying plane.
Their interiors must not overlap; shared edges are allowed. Both must fit
strictly inside that boundary. Regions have `terrain_region_*` geometry names;
existing patch names are preserved. Obstacles retain their independently
specified or base-inherited contacts. Heightfields and rough-concrete terrain
cannot be combined with these flat regions. This feature changes contact
materials, not terrain geometry or elevation between presets.

`randomize=True` applies one seeded multiplier to all sliding-grip values,
preserving their ratios; rolling friction, compliance, and layout remain fixed.
Reset restores the original coefficients before applying randomization.
The example's values are estimates: the resistant material keeps concrete's
0.8 grip while increasing rolling friction 20-fold and changing compliance.
It is not a calibrated soil or grass model. The slippery region uses dim4,
which disables rolling friction.

[Watch the 18-second surface-transition showcase](videos/surface-transitions-showcase.mp4).
The baseline controller crosses concrete, the resistant region, and the slippery
region, then returns through all three in one episode. Coloured cards highlight
actual drive-wheel contacts. The adjacent JSON includes contact coefficients,
material transitions, 5 Hz position/speed samples, arrival times, and solver
warnings. Reproduce with the video extra, FFmpeg, and graphics access:

```sh
uv run python -m ubot_sim.region_showcase
```

Tests complete the route with smooth and lugged wheels at 1 ms and 2 ms,
inspect actual contact parameters on both legs and split wheel/caster contacts,
and verify partition coverage, unchanged robot dynamics, seeded randomization,
shared edges, and rejection of conflicting geometry.
