# Gynoid simulation and balance training

This is a runnable MuJoCo and Gymnasium standing task for the Gynoid CAD,
with local CPU PPO training and BAM XL330 M6 actuators. The current `planted`
task actuates all 21 servos, starts from a CoM/holding-torque optimized pose,
and rewards balancing with the rounded leg tips at their original locations.
The saved `motion-v2` controllers stand, recover from small pushes, reach with
one arm, and transfer weight between the feet using the full BAM friction model.
The newer `overhead-v1` reaches above the head using a wider provisional right
shoulder travel range, with the same motor electrical limits.
The earlier `balance` task retains nine active waist/leg joints with a fixed
upper body. There is no walking reward or trained walking policy yet.

Run commands from the `gynoid` directory. The local `.venv` is already installed.
For another checkout with Python 3.12 and `uv`:

```sh
uv venv --python 3.12 .venv
uv pip install --python .venv/bin/python -r sim/requirements.txt
```

Watch the overhead reach, or inspect the initial standing pose:

```sh
.venv/bin/python -m sim.preview --task planted --com --output sim/runs/planted-rest-com.png
.venv/bin/mjpython -m sim.evaluate --controller sim/runs/overhead-v1/controller.npz --viewer
```

Yellow marks show the total CoM and its vertical projection; green marks show
the two foot centers. On macOS, the interactive
viewer requires `mjpython`; headless training uses regular Python.
See [MuJoCo's viewer documentation](https://mujoco.readthedocs.io/en/stable/python.html#passive-viewer).

Start an optional PPO training run (the successful controller above uses LQR):

```sh
.venv/bin/python -m sim.train --task planted --steps 1000000 --envs 4 --output sim/runs/planted-v2
.venv/bin/python -m sim.evaluate --policy sim/runs/planted-v2/policy.zip --episodes 100
.venv/bin/mjpython -m sim.evaluate --policy sim/runs/planted-v2/policy.zip --viewer
```

The output directory must be new or empty. Runs save the final policy, periodic
checkpoints, the best evaluated policy, monitor CSVs, evaluation results and
configuration. `Ctrl-C` saves the current policy. Resume into a new directory:

```sh
.venv/bin/python -m sim.train --resume sim/runs/planted-v2/policy.zip \
  --steps 1000000 --envs 4 --output sim/runs/planted-v2-continued
```

`--steps` counts additional environment transitions when resuming and rounds
up to complete PPO rollouts. A model fingerprint covers MJCF, mesh assets and
the controller/task/stance source, BAM parameter file, installed BAM source and
physics package versions; incompatible resumes and evaluations are rejected.
The configuration records voltage, firmware gain, nominal joint angles and
environment arguments. Evaluation restores those arguments; resume retains
them and rejects changes to the actuator settings or stance.
Resuming restores the policy and optimizer, but starts fresh simulator episodes
and evaluation/checkpoint schedules. Run outputs are ignored by Git.

## Overhead reach

In `overhead-v1`, the right arm raises 2.6 rad (149°) from its starting
shoulder angle, holds for three seconds, and returns. Twenty held-out trials (seeds 21000–21019) all completed the motion
and returned to standing. During the measured hold, the hand center averaged
49.2 mm above the head, with the entire hand at least 24.2 mm above it. Maximum
foot drift was 0.292 mm and maximum torso tilt was 1.63°.

The earlier reach was intentionally small. A geometric search within the old
provisional ±0.8 rad shoulder and other arm limits left the highest fingertip
about 49 mm below the top of the head. This experiment raises **only the right
first shoulder's upper travel limit to 3.0 rad**; its commanded peak angle is
about 2.68 rad. This is an explicit simulation assumption, not measured hardware
travel. Motor torque/current/voltage limits, masses and ground contacts remain
unchanged. Wiring and physical joint travel still need hardware validation.

Current, torque and voltage peaks are measured on every 2 ms actuator update.
Across all trials, peaks were 0.455 A, 0.167 N·m and 1.491 V; no actuator update
reached the 1.75 A or 5 V limits. Mean motor copper loss was 0.265 W. Thus this
slow overhead motion is not limited by actuator saturation in the model.

The planner adds forearm/hip-bracket clearance after exact CAD mesh intersections
revealed a small rub missed by the simple collision proxies. The final 105-pose
path has no new mesh intersections; two unchanged neck/chest overlaps of about
0.031 mm³ each are present in the source assembly. The recorded motion was also
checked every 0.2 seconds: an existing 0.297 mm³ forearm/bracket intersection
in the initial standing pose clears before the first sample, with no arm
intersections in subsequent samples. Detailed results and geometry
checks are in `runs/overhead-v1`; its snapshot preserves source and dependencies.
All 40 simulation tests pass, including an overhead hold-and-return regression.

```sh
.venv/bin/python -m sim.evaluate --controller sim/runs/overhead-v1/controller.npz --episodes 20
.venv/bin/python -m sim.motion_control --motion overhead --output sim/runs/my-overhead/controller.npz
.venv/bin/python -m sim.record --controller sim/runs/overhead-v1/controller.npz \
  --output sim/runs/my-overhead.mp4 --episodes 1 --speed 1 --camera-height 0.28 --camera-distance 0.96
```

## Push recovery and deliberate motion

The `motion-v2` controllers handle 0.1 N push recovery, a right-arm reach, and
left/right weight transfers followed by a return to the starting stance.

`motion_control.py` plans collision-free equilibria with a vertical torso and
the feet at their original positions. It interpolates local feedback gains
along the motion, adds gravity and back-EMF feedforward, and sends ordinary
position targets to all 21 BAM servos. The motion task allows residual commands
of ±0.24 rad for the legs and ±0.40 rad elsewhere, with an 8 rad/s target slew
limit. Voltage (5 V), firmware gain (200), current limit (1.75 A), physical joint
stops, masses, contacts and friction are unchanged. Neither foot is welded.

Held-out evaluation starts use the usual ±0.002 initial root-velocity noise:

| Motion | Trials | Maximum foot drift | Maximum torso tilt | Mean copper loss |
| --- | --- | --- | --- | --- |
| Quiet standing, 60 s | 20/20 | 0.103 mm | 1.47° | 79.5 mW |
| Push recovery, 10 s | 100/100 | 0.349 mm | 14.44° | 178.3 mW |
| Push recovery, 60 s | 20/20 | 0.685 mm | 14.91° | 220.1 mW |
| Reach and return, 20 s | 20/20 | 0.147 mm | 1.46° | 95.1 mW |
| Weight shift and return, 32 s | 20/20 | 0.229 mm | 1.39° | 120.0 mW |

Pushes last 100 ms, occur every two seconds, and change horizontal direction
by the golden angle. The arm holds approximately 14.3° of shoulder motion and
moves the hand forward 41.5 mm. Weight transfer moves the CoM about 9.9 mm left
and 9.7 mm right, with measured loads of approximately 70/30 and 30/70. Every
motion test requires both the requested movement and the return to standing;
surviving the episode alone does not count. These runs had no simulator warnings.
The [result summary](runs/motion-v2/results-summary.json) and individual
evaluation files are saved in the run directory. Its original 37 simulation tests passed.
Its `snapshot` directory preserves the source, model assets and package lock.
Replay this older controller set from that snapshot, since the current source
adds overhead travel and actuator telemetry:

```sh
cd sim/runs/motion-v2/snapshot
../../../../.venv/bin/python -m sim.evaluate --controller ../recovery.npz \
  --episodes 20 --seconds 60 --push-force 0.1
../../../../.venv/bin/mjpython -m sim.evaluate --controller ../reach.npz --viewer
../../../../.venv/bin/mjpython -m sim.evaluate --controller ../weight_shift.npz --viewer
```

These are model-based feedback controllers using simulator state. Foot lift,
landing and stepping remain experimental; no walking result is claimed.

## Earlier successful planted standing controller

`balance_controller.py` designs whole-body LQR feedback around the unrestricted
optimized pose. It uses the full mass matrix, including BAM rotor inertia,
linearizes gravity and contact/linkage reactions, and discretizes the servo
dynamics for 50 Hz target updates. Free axial rod spin is omitted from the
controller's state cost because it is nearly uncontrollable and irrelevant to
standing. Predicted joint velocity selects a bounded friction-compensation
offset. All corrections go through the existing 21 servo position commands,
unchanged residual ranges and 1.5 rad/s slew limit.

Rigid contacts and smooth friction are approximations used to calculate gains
only. Evaluation retains the original unwelded floor contacts, corrected parallel
neck linkage, complete BAM M6 friction and electrical limits. The controller
uses simulator state, including velocities and friction budgets; deploying it
on hardware will require state estimation and actuator calibration. It is a
feedback controller, not a newly trained PPO policy.

The saved controller is `runs/planted-lqr-v1/controller.npz`. Its metadata checks
both simulation and controller-source fingerprints. Rebuild into a new file and
evaluate with:

```sh
.venv/bin/python -m sim.balance_controller --output sim/runs/my-controller/controller.npz
.venv/bin/python -m sim.evaluate --controller sim/runs/my-controller/controller.npz --episodes 100
.venv/bin/python -m sim.evaluate --controller sim/runs/my-controller/controller.npz --episodes 20 --seconds 60
```

Validation uses the standard initial velocity perturbations of ±0.002 m/s and
rad/s, with independent seeds held out from tuning:

| Evaluation | Success | Maximum foot drift | Maximum torso tilt | Mean motor copper loss |
| --- | --- | --- | --- | --- |
| 100 × 10 s, seeds 2000–2099 | 100/100 | 0.122 mm | 5.54° | 93.0 mW |
| 20 × 60 s, seeds 3000–3019 | 20/20 | 0.308 mm | 6.65° | 96.6 mW |

Neither set had foot lift or simulator warnings. The lowest pelvis position was
344.36 mm, only 0.69 mm below its initial position. This exceeds the standing
milestone of at least 95/100 ten-second successes. It has **not** achieved push
recovery: ten separate trials with 0.1 N horizontal pulses lasting 0.1 seconds
all exceeded the torso-tilt limit, averaging 2.594 seconds of standing. The first
pulse begins at 2 seconds. These results use the same physical model and limits.
Motor copper loss is an I²R estimate, not total battery consumption.

Detailed JSON results are in `runs/planted-lqr-v1`. Its original 28 simulation tests passed, including
two seeded ten-second balance regressions and serialization/fingerprint checks.
The run's `snapshot` directory preserves source, assets and a package lock.
Controller source has since changed; replay this older artifact from its snapshot:

```sh
cd sim/runs/planted-lqr-v1/snapshot
../../../../.venv/bin/mjpython -m sim.evaluate --controller ../controller.npz --viewer --seconds 60
```

## Planted feet and whole-body rest pose

`gynoid_full.xml` contains all 54 original parts, 25 moving links and 21 actuators,
with the same 0.6324 kg mass and neutral CoM as the nine-joint model. Both arms,
wrists, thumbs and neck motors are articulated. Two passive head axes, two rod
ball joints and two endpoint constraints implement the parallel neck linkage.
The head retains the CAD solver's **fixed-roll assumption**; independent head
roll is not modeled. The hand stays on the thumb servo's case while the thumb
follows its horn. Joint movements are checked against reposed OpenSCAD assemblies.

The neck rod endpoints use near-rigid equality impedance
(`solimp="0.9999 0.9999 0.001"`). The initial `planted-v1` model used the default
softer impedance, which allowed about 1 mm of endpoint separation and several
degrees of unintended head motion even with both neck targets held constant.
The corrected constraints retain the two powered neck joints and passive linkage
axes; they do not lock the head. Elastic rod bending and hardware joint clearance
are not modeled. Regression checks cover both holding still and commanded motion.

`rest_pose.py` uses the existing slicer-derived masses and inertias. Its constrained
optimization holds both original foot centers at ground contact height, centers
the CoM between them, keeps the torso vertical, and keeps the pelvis within 1 mm
of its original height or higher. The objective minimizes squared holding torque,
prefers a 5 mm higher pelvis, and mildly penalizes large joint changes. Inverse
statics includes the internal neck-rod forces and equal vertical foot loads.
The result is a local optimum within assumed joint ranges, not a proof of the
lowest-energy pose available on hardware. Two thigh-yaw and two shoulder joints
reach those assumed ranges; their actual clearance and travel need validation.

The saved pose in `rest_pose.json` has pelvis height 345.05 mm, a vertical torso,
CoM height 323.48 mm and less than 0.001 mm calculated foot/CoM constraint error.
Peak holding torque is 0.0232 Nm. The motor winding-loss proxy falls from 68.9 mW
for the balanced pose with the original upper-body posture to 23.9 mW with the
whole body optimized (about 65% lower). This is **I²R at static holding torque**,
not total battery power: it omits electronics losses and the contribution of
stiction. The original unbalanced CAD pose is also reported but is not the
balanced comparison used for that reduction.

The policy starts from this complete pose, with small root-velocity perturbations
(default ±0.002 m/s and rad/s), rather than perturbing joints and breaking foot
placement or neck closure. Static holding torques are converted into BAM servo
target offsets. The learned actions add residual offsets: ±0.12 rad at the leg
joints and ±0.20 rad elsewhere, slewed at 1.5 rad/s. All 21 actions remain available.
The 110 observations extend the balance state with each foot's position error
and velocity. Reward favors upright posture, high hips, centered CoM and planted
feet, with penalties for motion, winding loss and abrupt commands. Episodes stop
at 8 mm horizontal foot drift, 4 mm lift after the first 0.2 seconds, 25 mm pelvis
drop, excessive tilt, or other body-ground contact. A successful episode lasts
10 seconds. Feet use ordinary frictional contacts; there are no ground welds.

Before the neck correction, even with optimized pose and gravity holding offsets,
the fixed-target controller averaged only 1.4226 seconds across seeds 1000–1099
(0/100 successes). Centering the
CoM establishes a static equilibrium; it does not stabilize the inverted pendulum
formed by these narrow rounded tips. The active policy must provide that feedback.

The first PPO run on this task, `planted-v1`, used the pre-correction neck
model. Over 1,000,448 transitions it learned no more balance than the
fixed-target controller: across seeds 1000–1099 the final policy averaged
1.4282 seconds, with 0/100 successful 10-second episodes, all ending at the
pelvis-height threshold. Its feet stayed planted, within 1.001 mm of horizontal
drift and with no lift. The run's files have since been removed.

The unrestricted pose remains the default. The simulation checks include all
servo axes against OpenSCAD and the neck holding/motion regression. The
unrestricted rest-pose coordinates and static holding torques are identical
after the correction. The successful LQR controller described above uses the
corrected physics; the `planted-v2` commands above start a fresh PPO run on it.

Compare the original CAD pose, the centered pose with original arms, and the
unrestricted whole-body pose from matched side and front cameras:

```sh
.venv/bin/python -m sim.compare_poses --output sim/runs/pose-comparison-front-side.png
```

Recompute the full model and pose after rebuilding CAD assets:

```sh
.venv/bin/python -m sim.build_model --full
.venv/bin/python -m sim.rest_pose
```

## Earlier nine-joint balance experiments

The original PD environment on this M1 Max with 32 GB RAM was checked with 1, 4 and 8 environments. Headless
rollout throughput was approximately 1,770, 4,610 and 7,970 transitions/s,
respectively, over short warmed-up measurements. Training also spends time on
policy inference and optimization. Four workers is the default; eight is an
option when the machine can devote more CPU to training. The small MLP uses
CPU, following [Stable-Baselines3's PPO guidance](https://stable-baselines3.readthedocs.io/en/master/modules/ppo.html).

```sh
.venv/bin/python -m sim.benchmark
.venv/bin/python -m pytest sim/tests -q
```

With fixed targets, the BAM environment averages 0.93 seconds in the CAD pose and 1.18 seconds in the centered pose
over reset seeds 1000–1019. A successful episode lasts 10 seconds. The next
milestone is at least 95 successful episodes across 100 reset seeds, then
small pushes with `--push-force 0.1`, increased gradually.
Walking will need velocity commands/rewards and revised termination conditions;
the current task deliberately ends when the robot travels more than 0.3 m.

The policy receives 50 values: projected gravity, local base velocity, joint
positions/velocities, previous action, servo target state, base height, COM
offset from the midpoint of the tips and ground contact indicators. These use
simulator state, appropriate for simulation-only training. Nine actions in
`[-1, 1]` request position offsets from the centered pose. The `baseline` action
range is ±0.25 rad at the waist and ±0.35 rad at each leg joint. The `wide` range
is ±0.45 rad at the waist and ±1 rad at each leg joint. This allows larger
servo position errors to generate corrective torque with BAM's firmware gain;
joint travel limits and actuator electrical limits stay fixed. Some targets
can therefore lie beyond the modeled mechanical joint stops. The pose penalty
retains its original normalization in both profiles. Targets slew at 4 rad/s. BAM control runs at 500 Hz
and policy actions at 50 Hz. Reward favors upright posture, height and centering,
with penalties for motion, effort and abrupt action changes. These reward weights,
action ranges, slew rate and PPO settings are retained from the PD baseline
for the first BAM experiment; only target range changes in the second BAM run.
Falls terminate;
the 10-second time limit truncates.

The generated model includes 54 part instances, 21 servos, 10 rigid bodies and
9 actuators. Its total mass is about 0.6324 kg. `model_report.json` lists each
link's mass, center of mass and full inertia, part-to-link assignments, joint
order and assumptions. Simulation coordinates are meters, kilograms, seconds
and radians, with +X forward, +Y left and +Z up. Joint zero is the existing CAD
pose; the centered reset adds approximately 1.10° right hip pitch, 0.99° left
hip pitch and opposite 0.018° hip roll adjustments. A deterministic kinematic
solve centers the COM over the tip midpoint and levels the tips. This removes
the CAD pose's 4.56 mm forward COM offset; it does not establish dynamic balance.
Use `--stance cad` with training, preview or fixed-target evaluation to compare
the original pose. Joint signs follow each servo's shaft axis. Anatomical left/right uses assembled
position; the original CAD's `leg_l` and `leg_r` anchors have opposite labels.

| Model input | Source or assumption |
| --- | --- |
| Part frames and joint pivots | BOSL2 assembled transforms from `gynoid.scad` |
| Printed masses and inertias | `../tools/print_mass.py`, including print orientation |
| Slicer configuration | X1 Carbon 0.4 mm, 0.20 mm Standard, PETG HF, 15% grid, 2 walls, 5 top and 3 bottom layers |
| Servo mass | 18 g each; case COM and uniform box inertia are approximations |
| Motor variant | XL330-M288 at 5 V assumed; the CAD only specifies XL330 |
| Motor model | BAM 1.0.2, identified XL330 M6 parameters; PWM voltage control, back-EMF, winding resistance and firmware current limiting |
| Controller | 5 V supply, firmware Kp 200, 1.75 A current limit; `--voltage` and `--kp` configure new runs |
| Inertia and friction | BAM armature 0.001807743 kg·m²; Coulomb, Stribeck, viscous and directional/load-dependent M6 friction |
| Other control assumptions | Target slew, action ranges, joint travel and contact friction remain provisional |
| Contacts | CAD convex legs; simple case/torso/hand proxies; small brackets have no collision geometry |
| Extra hardware | Battery, controller, wiring and separate fasteners absent from the assembly are omitted |

The servo's [ROBOTIS specification](https://emanual.robotis.com/docs/en/dxl/x/xl330-m288/)
provides the case mass. The BAM model's own voltage/current equations determine
motor torque; the previous hard 0.52 Nm clipping is removed. That value remains
only as the effort reward's normalization, to retain the baseline reward scale.
The 1.75 A setting is the bundled BAM actuator's firmware limit, not a measured
Gynoid setting. Thermal behavior, backlash, supply sag, command delay and domain
randomization are not included in this first experiment.
The neck rods are currently treated as PETG prints. The linked settings and
assumptions make this a simulation baseline, not a calibrated physical robot.

`actuators.py` calls BAM's motor and M6 friction calculations directly and writes
the friction budget to MuJoCo's constraint solver. BAM 1.0.2's standard CPU wrapper
uses joint IDs when subtracting its previous dry-friction forces; MuJoCo's
`mjCNSTR_FRICTION_DOF` constraints are indexed by DOF ID. Those differ after a
free root joint, so this adapter explicitly uses DOF IDs. Tests compare fixed-base
trajectories against BAM's wrapper and separately verify floating-base friction,
current/voltage saturation, electrical braking and deterministic episode resets.
See [BAM CPU integration](https://bam.readthedocs.io/en/stable/usage/mujoco_cpu.html).

The identified numbers are copied unchanged from BAM 1.0.2 into
`assets/xl330_m6.json`, matching Microduck's pinned XL330 M6 parameters.
They are identified servo parameters, not a calibration of this particular robot.

Three 1,000,448-step PPO runs on this task each scored 0/100 successful
10-second episodes over the same 100 seeds, all ending at the height threshold.
The final policies averaged 1.281 seconds with the original PD actuators,
1.1472 seconds with BAM and the baseline target range, and 1.1684 seconds with
BAM and the wide range. Their files have since been removed.

Record an MP4 using the same physics and renderer (requires `ffmpeg`):

```sh
.venv/bin/python -m sim.record --policy sim/runs/planted-v2/policy.zip \
  --output sim/runs/planted-v2/preview.mp4 --episodes 4 --speed 0.5
```

The recorder verifies the policy's model fingerprint, adds short pauses around
each episode, and saves playback/seed metadata beside the video. The output
path must be new. macOS needs access to its graphics session for rendering.

To regenerate after a CAD edit:

```sh
.venv/bin/python -m sim.export_cad
.venv/bin/python -m sim.build_model
.venv/bin/python -m sim.build_model --full
.venv/bin/python -m sim.rest_pose
.venv/bin/python -m pytest sim/tests -q
```

Export needs the repository's OpenSCAD build with BOSL2 and Bambu Studio.
It captures the actual assembled transforms using temporary instrumentation,
exports individual STL meshes, and slices each printed variant through the
repository tool. The original `gynoid.scad` remains unchanged.
`mass_parts.scad` records the generated print orientations. The manifests retain
the CAD hash, slicer settings and mass-tool hash. Changed CAD cannot reuse stale
mass properties; `--skip-mass` is only for mesh regeneration of unchanged CAD.
The generated assets are included so ordinary training needs neither CAD nor
slicer software. Kinematic tests compare all part origins and orientations
against independently reposed OpenSCAD assemblies across all 21 actuated axes,
including mirrored arms, fixed-case hand attachments and parallel neck closure.
