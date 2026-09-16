# Terrain simulation TODO

## Current baseline

- [x] Use simplified wheel lug contacts by default, with smooth wheels selectable.
- [x] Add a deterministic bumpy heightfield for comparison with flat ground.
- [x] Benchmark both wheel models for speed, contacts, stability, and waypoint completion.

The existing `bumps` terrain is a benchmark fixture, not a calibrated grass or
soil model. See [benchmark results](benchmarks/README.md).

## First terrain controls

- [ ] Separate terrain settings into independent controls:
  - Grip: sliding friction and local slippery patches.
  - Rolling resistance: effort needed to roll, separately from grip.
  - Slope: uphill, downhill, and cross-slope travel.
  - Roughness: bump height, spacing, and ruts using heightfields.
  - Compliance: approximate yielding/cushioning through contact settings.
- [ ] Evaluate `condim=6` to activate contact rolling friction; the current
  `condim=4` does not use the configured rolling-friction coefficient.
- [ ] Compare contact rolling friction with a ground-dependent resistance model.
  Grass should be able to resist rolling without necessarily having low grip.
- [ ] Make effective wheel–terrain contact parameters explicit so each patch
  actually produces its intended friction and compliance.
- [ ] Add separate collision shapes for rocks, roots, seams, and small edges.
- [ ] Adapt spawn height, goal markers, and failure checks to terrain elevation.

## Surface presets

- [ ] Concrete: firm, relatively smooth, low rolling resistance.
- [ ] Rough concrete: small bumps, seams, and occasional edges.
- [ ] Short grass approximation: uneven ground, increased rolling resistance,
  and variable grip.
- [ ] Wet/slippery patches: local grip changes, including one drive wheel on
  each of two different surfaces.
- [ ] Sloped lawn: combine grass settings with uphill, downhill, and cross-slope
  routes.
- [ ] Support transitions between surface types within one continuous route.

Treat initial preset values as estimates until measured on the robot.

## Validation and training

- [ ] Run the same waypoint routes across all presets and compare completion,
  travel time, tracking error, wheel slip, and stopping behavior.
- [ ] Exercise caster alignment and reversals, caster hang-ups, uneven wheel
  loading, chassis clearance, and getting stuck at obstacles.
- [ ] Repeat performance and timestep-sensitivity checks as terrain complexity
  increases; compare lugged and smooth contacts where useful.
- [x] Correct the command ramp's braking behavior to match firmware defaults:
  acceleration 8 turns/s², braking 2 turns/s², before evaluating stopping.
  Includes reversal handling and the firmware's near-zero stop snap; regression
  tests cover both 1 ms and 2 ms physics timesteps.
- [ ] Randomize terrain properties and layouts reproducibly during training;
  use separate seeds/layouts for evaluation.
- [ ] Once the control board works, record starts, stops, straight runs, arcs,
  and reversals on concrete and grass. Combine wheel encoder logs with an
  independent measurement of robot motion to distinguish travel from slip.
- [ ] Fit terrain and drive-response parameters to those recordings, validate
  on separate runs, and set randomization ranges from observed variation.
- [ ] Revisit center-of-mass height, rotational inertia, and motor response
  before trusting predictions about slopes, tipping, or traction limits.

## Later: ground deformation and detailed tread interaction

- [ ] Evaluate whether navigation failures justify modeling soil displacement,
  wheel sinkage, persistent ruts, mud, or grass bending around the tread.
- [ ] Investigate custom ground-force/deformation models or a specialized
  terrain simulator if those effects become important.
- [ ] Refine the lug/core collision geometry, including omitted chamfers, if
  obstacle-crossing or traction measurements show the box approximation matters.

Soft contact alone does not model displaced soil or persistent ruts. Physical
lugs improve geometric interaction with uneven ground, but realistic grass/soil
traction also requires an appropriate ground model and calibration.
