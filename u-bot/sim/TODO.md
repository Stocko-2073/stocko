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
- [x] Evaluate `condim=6` to activate contact rolling friction; the current
  `condim=4` does not use the configured rolling-friction coefficient.
  [Rolling evaluation](benchmarks/rolling.md): 24 configurations, navigation,
  passive coasting, timing, and timestep checks. Keep dim4 as the default;
  dim6 with 0.002 m rolling friction is an experimental option, not a preset.
- [ ] Compare contact rolling friction with a ground-dependent resistance model.
  Grass should be able to resist rolling without necessarily having low grip.
- [x] Make effective wheel–terrain contact parameters explicit so each patch
  actually produces its intended friction and compliance.
  `TerrainContact` defines friction, contact dimension, and compliance for the
  current flat/bumps surfaces. Terrain priority overrides wheel mixing; tests
  inspect actual drive-wheel and caster contacts. `TerrainPatch` now provides
  local sliding-grip overrides on flat ground.
- [x] Add separate collision shapes for rocks, roots, seams, and small edges.
  `TerrainObstacle` supplies static ellipsoids, capsules, and boxes with world
  placement, yaw, and optional contact overrides. Tests exercise actual wheel
  encounters on flat/bumps terrain with smooth and lugged wheels.
- [x] Adapt spawn height, goal markers, and failure checks to terrain elevation.
  Static collision geometry now sets footprint-aware spawn clearance, goal
  marker height, and terrain-relative failure checks. Resets accept XY spawn
  positions; tests cover heightfields, elevated routes, and missing ground.
  [Elevation video](videos/elevation-showcase.mp4).

## Surface presets

- [x] Concrete: firm, relatively smooth, low rolling resistance.
  `surface="concrete"` selects flat ground with explicit estimated contact
  settings and active low rolling friction (dim6). Both wheel models complete
  the five-waypoint route. [Video](videos/concrete-showcase.mp4).
- [x] Rough concrete: small bumps, seams, and occasional edges.
  `surface="rough_concrete"` combines a 0–4 mm heightfield, two 4 mm seams,
  and an 8 mm step. Both wheel models complete the five-waypoint route and
  contact every feature at 1 ms and 2 ms.
  [Video](videos/rough-concrete-showcase.mp4).
- [x] Short grass approximation: uneven ground, increased rolling resistance,
  and variable grip. `surface="short_grass"` combines continuous 0–8 mm
  heightfield bumps, nine tiles with grip 0.55/0.65/0.75, and active 0.002 m
  rolling friction. Both wheels complete the route at 1 ms and 2 ms.
  A separate 5 cm canopy adds estimated wheel/caster drag and illustrative
  blade bending/recovery. [Canopy video](videos/grass-canopy-showcase.mp4).
- [ ] Experiment with a 5 cm canopy representative of average lawn density.
  Source or measure a typical density range, distinguishing shoots/tillers
  from individual blades. Use it to inform both visual coverage and physical
  resistance, and compare against the current sparse illustration (about
  178 blades/m², with density-independent drag). Check travel, stopping,
  runtime, and timestep sensitivity; document assumptions and calibration gaps.
- [x] Wet/slippery patches: local grip changes, including one drive wheel on
  each of two different surfaces. `TerrainPatch` adds flush rectangles with
  independent sliding grip and inherited rolling/compliance settings. Tests
  cover actual split wheel/caster contacts, dry–patch–dry crossings at two
  timesteps, seeded grip, and a continuous route.
  [Split-grip video](videos/slippery-patch-showcase.mp4).
- [ ] Sloped lawn: combine grass settings with uphill, downhill, and cross-slope
  routes.
- [x] Support transitions between surface types within one continuous route.
  `TerrainRegion` assigns complete contact materials to flush flat rectangles,
  including grip, rolling resistance, contact dimension, and compliance.
  Tests cross all materials in both directions without resetting, with both
  wheel models at 1 ms and 2 ms. [Video](videos/surface-transitions-showcase.mp4).

Treat initial preset values as estimates until measured on the robot.

## Validation and training

- [x] Run the same waypoint routes across all presets and compare completion,
  travel time, tracking error, wheel slip, and stopping behavior.
  [Surface evaluation](benchmarks/surfaces.md): 72/72 completed across all three
  current presets, two routes, both wheels, 1/2 ms, and three seeds. Metrics
  include actual contact-point slip and per-waypoint stopping measurements.
  [Comparison video](videos/surface-evaluation-showcase.mp4).
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
