# phone_girl simulation

A MuJoCo Warp model of phone_girl for reinforcement learning with
[mjlab](https://github.com/mujocolab/mjlab), built so that a trained policy
runs on the robot unchanged. The phone, the radio link, the MCU and the servos
are modelled the way the hardware will see them:

- **Model.** It comes straight from `phone_girl.scad`, with printed masses from
  the slicer.
- **Servos.** BAM's identified XL330 model, fed by a battery that sags.
- **Phone sensors.** CoreMotion's gravity and rotation rate at 100 Hz, and the
  phone's cameras with their real fields of view.
- **Timing.** The BLE control loop in
  [`../protocol/PROTOCOL.md`](../protocol/PROTOCOL.md).

Everything the robot can't know is randomized. Every exported policy carries the
contract the phone app needs to run it.

## On the RTX 5080 machine

Training needs Linux and an NVIDIA driver of **580 or newer**: the locked torch
is built for CUDA 13, which includes Blackwell. On Ubuntu 24.04 install the
`nvidia-driver-580-open` package or newer, then reboot. Blackwell needs the
open kernel modules.

The meshes are in Git LFS, as the repository's `.gitattributes` asks. Install it
before cloning, or MuJoCo will find pointer files where the meshes should be.

```sh
sudo apt install git-lfs && git lfs install
curl -LsSf https://astral.sh/uv/install.sh | sh
cd stocko/robots/phone_girl/sim
uv sync                      # uv's own Python 3.12 and the locked dependencies
uv run python -c "import torch; print(torch.cuda.get_device_name())"
uv run pytest -q             # 35 tests; the CAD comparison skips without OpenSCAD
uv run phone-girl-bench      # throughput at 1k-8k worlds: pick num-envs from this
```

The project uses uv's own Python builds (`python-preference` in
`pyproject.toml`). On a GPU the servo and IMU code is compiled with
`torch.compile`, and its Triton kernels need `Python.h`, which Ubuntu's Python
lacks without `python3.12-dev`. On the RTX 5080, 8k worlds is 0.75 s per PPO
iteration.

Then train, watch and export:

```sh
uv run train PhoneGirl-Stand --env.scene.num-envs 4096
uv run train PhoneGirl-Walk --env.scene.num-envs 4096
uv run tensorboard --logdir logs/rsl_rl
uv run play PhoneGirl-Stand --viewer viser \
  --checkpoint-file logs/rsl_rl/phone_girl_stand/<run>/model_3000.pt
```

`play` opens a web viewer; forward its port to view it from another machine.
Every checkpoint is saved with an ONNX policy beside it
(`<run>/<run>_<iteration>.onnx`). It includes observation normalization and a
`phone_girl` metadata entry with the robot contract; see
[Deployment](#deployment). Add `--agent.logger wandb` to log to Weights & Biases.

On this Mac everything runs on the CPU, slowly: model building, tests, the
viewer, and short training runs for debugging.

## Looking at it

There are two web viewers, and both work on the Mac:

```sh
uv run phone-girl-view                    # http://localhost:8081: pose the model by hand
uv run play PhoneGirl-Stand --agent zero  # http://localhost:8080: the simulator as training sees it
```

- **`phone-girl-view`** holds the torso on a stand 5 cm above the floor. Each
  joint has a slider under Controls → Actuation that sets its target as an
  offset from home, across its full travel. The servos are ideal position
  servos, not BAM.
  - Use it to check joint axes and directions, travel, and collision shapes.
  - Collision geoms are group 3, under Groups. Contact points are under
    Visualization.
  - To drop the robot, tick Equality under Physics → Disable Flags.
- **`play`** runs the whole environment: BAM servos, link delays, domain
  randomization and terminations.
  - `--agent zero` holds home, and the robot topples in about a second.
  - Other options: `--agent random` for random targets, `--num-envs 4` for
    several randomized robots, and `--no-terminations` to let a fallen robot
    lie.
  - `PhoneGirl-Walk` adds a joystick under Commands.
  - The Mac runs it at 0.3–0.4× real time.
  - On Linux with a display, `play` opens MuJoCo's native viewer instead;
    `--viewer viser` keeps the web one.

## How it fits together

```
policy (phone) --command--> BLE link --> MCU --> servo goals ---> BAM XL330 servos --> MuJoCo Warp
     ^                     15 ms tick,         ticks from home    P loop, current limit,      |
     |                     late packets,                          back-EMF, M6 friction,      |
     |                     stalls                                 shared sagging battery      |
     +-- CoreMotion gravity, rotation rate (100 Hz, latency, bias, mount tilt) <--------------+
     +-- servo registers: position, velocity, PWM, voltage (quantized, read before the tick) -+
```

| File | What it does |
| --- | --- |
| `cad.py` | Echoes every part's BOSL2 frame from a temporary copy of the CAD. Turns each pose knob to find the joint tree, axes and directions. Exports meshes and slices printed parts. |
| `mjcf.py` | Builds `phone_girl.xml`: inertials, collision primitives, IMU site, cameras. |
| `robot.py` | The mjlab entity, joint order, home pose and mirror map. |
| `xl330.py` | BAM XL330 servos on MuJoCo Warp, the battery, and the servo telemetry. |
| `phone.py` | CoreMotion IMU model, phone cameras, and camera frame rate and latency. |
| `link.py` | BLE and bus timing, late packets and stalls. |
| `randomization.py` | Every randomized parameter, and a curriculum that widens them. |
| `observations.py` | The actor's inputs (the contract) and the critic's privileged inputs. |
| `tasks/env.py` | The shared environment, and the stand and walk tasks. |
| `deploy.py` | The ONNX export with the robot contract attached. |
| `protocol.py` | BLE frames: the reference for the firmware and the app. |
| `bench.py` | Throughput, solver and contact statistics. |

### Where it runs

On a GPU, the whole training loop runs there, batched over every world:

- physics: MuJoCo Warp, one CUDA graph per physics step;
- the servos and battery;
- link latency, lost packets and stalls;
- the IMU and camera models;
- rewards, resets, randomization and PPO.

Python on the CPU only launches the kernels and runs mjlab's managers; nothing
loops over environments. Each world carries its own latency, stall, battery and
randomized parameters, so all of them still step together.

The BLE codec (`protocol.py`) never runs in training. The GPU code reproduces its
tick quantization, register units and timing, and `test_protocol.py` checks they
agree. Expect the codec in tools that talk to the real robot.

mjlab waits for the GPU a few times per control step, for example to find the
worlds that need a reset. The phone_girl code adds no waits of its own:
constants and index tensors are built once.

What keeps the step fast on the GPU:
- the servo and IMU code is compiled with `torch.compile` on CUDA;
- body randomization is in closed form;
- MuJoCo Warp's `set_const` replays from a CUDA graph;
- falls are read from the contact list.

The tools:
- `uv run phone-girl-bench --profile` splits a control step into its parts.
- `uv run phone-girl-bench --sync-debug` reports every CPU–GPU sync in one step.
- TODO.md has the measurements.

## The model, from the CAD

```sh
uv run phone-girl-export     # OpenSCAD + Bambu Studio: frames, meshes, sliced masses
uv run phone-girl-build      # phone_girl.xml and model_report.json
uv run pytest tests/test_model.py
```

Run both after any CAD change. The generated files are checked in, so training
needs neither OpenSCAD nor the slicer. The build refuses a stale export, and a
test fails if `phone_girl.scad` changed since the export.

- **Joints.** These come from the CAD, not from reading it. The exporter turns each
  of `default_pose`'s 17 knobs by 5° and records which parts move, about which
  shaft, and which way. Every joint angle is the servo's own shaft angle,
  counterclockwise viewed from the horn as Dynamixel counts it. Servos inside the
  left arm's `xflip()` turn against their `drive`, so their angle is −drive.
- **Model pose.** The model is built standing in `default_pose`, which is qpos0,
  with each joint's `ref` set to its default angle.
- **Tests.** One independent OpenSCAD run at random knobs must agree with the
  model's kinematics for all 44 parts, within 2 µm.
- **Mass, 0.758 kg.**
  - The phone is 199 g (Apple's figure, with the CoM measured on a pin), the two 18650s 96 g,
    and the 17 servos 306 g.
  - Sliced PETG parts add 140 g.
  - The electronics box is a **20 g guess**.
  - Link inertias sum the parts' sliced or box inertias.
- **Looks.** Printed parts are teal and bought parts dark grey. The face on the
  phone's screen is split off the phone mesh by its CAD colour (`cad.DECALS`)
  and drawn on its own, visual only.
- **Collision.** The servo and phone boxes are exact; printed parts are oriented
  boxes, except the top of each stilt, which is its convex hull: the stilts are
  4.6 mm apart at home, and boxes left 1.1 mm. Each stilt ends in a 2.5 mm
  sphere, which is the foot. Limbs collide with
  each other and with the trunk, but not with themselves. Robot geoms have
  priority, so the foot's randomized friction is the contact's.
- **Home.** The CoM is 0.274 m up and within a millimetre of the stilt tips fore
  and aft. The tips are 25 mm apart, so standing is active balancing on two
  points.

### Joints

Slot order is MuJoCo's depth-first order. It is used everywhere: actions,
observations, the bus, and the Dynamixel IDs (slot + 1).

| Slot | Joint | Slot | Joint |
| --- | --- | --- | --- |
| 0 | waist (pitch) | 9 | right_shoulder_pitch |
| 1–4 | right hip_roll, hip_pitch, thigh_yaw, knee | 10–12 | right shoulder_yaw, elbow, wrist |
| 5–8 | left hip_roll, hip_pitch, thigh_yaw, knee | 13–16 | left shoulder_pitch, shoulder_yaw, elbow, wrist |

The CAD's `leg_l` is the robot's right leg; sides here go by assembled position.
The "knee" swings the stilt. Home rests on knees locked 7° backward past
straight; they stop at 10° and fold 167° the other way, to kneel. Hip roll stops
at about 2° inward on the other stilt and 5.5° outward on the hand hanging
beside it, on the printed parts as in the model. **Other joint travel is
provisional.** It is ±35° to ±150° about home by joint type (`mjcf.TRAVEL_DEG`)
and is not measured. Find the real stops before trusting it, and set the same
values as the MCU's soft limits.

## Servos

`xl330.py` runs BAM's identified XL330-M288-T model
([Duclusaud et al., ICRA 2025](https://arxiv.org/abs/2410.08650)) on every 2.5 ms
physics step, vectorized over all worlds.

- **Firmware control.** The firmware's P controller works in whole encoder
  ticks: duty = Kp × error × 4096/2π / (256 × 885), with Kp = 400. The current
  limiter narrows the duty, and the bus voltage times the duty drives a DC motor
  with back-EMF.
- **Friction.** BAM's M6 budget is Coulomb, Stribeck, load-dependent,
  directional and quadratic. It is written each step into MuJoCo's per-DOF
  `frictionloss` and `damping`, so the solver resolves stiction, as BAM's own
  integration does. MuJoCo Warp has no noslip solver, so the friction constraint
  is stiffened, as BAM does on the GPU. That costs about 1 mrad of static droop
  compared with CPU MuJoCo's default.
- **Validation** (`tests/test_xl330.py`):
  - The motor law and the friction budget match BAM's CPU code to 1e-12.
  - A loaded single-servo arm on MuJoCo Warp tracks BAM's `MujocoController` on
    CPU MuJoCo within 0.5 mrad.
- **Battery.** All 17 servos draw from one battery: open-circuit voltage behind
  a resistance. The duty-weighted motor current plus the electronics' idle draw
  sag the voltage every servo sees. The pack is two 18650s in series, 6.6–8.4 V:
  above the XL330's 6 V rating, as in BAM's identification (7.5 V). Torque and
  stiffness scale with the voltage, so a nearly flat pack gives about 20% less
  than a full one.
- **Registers.** Telemetry is reported as the registers read it: position in
  ticks from home, velocity in 0.229 rpm, current in mA, PWM in 0.113%, voltage
  in 0.1 V.
- **Present Current.** The XL330 measures current at its power input
  (ROBOTIS: "unlike other DYNAMIXEL-X series"). So Present Current is modelled as
  duty × motor current. Its real sign convention is unknown: check it on the bench.

### Force feedback

The actor gets a torque estimate per joint, computed from the servo's own
registers:

  τ̂ = kt/R · (PWM · V_bus − kt · ω)

This is BAM's motor equation with nominal kt and R; the phone app computes the
same thing from the state frame. It needs no current sensor, which matters
because the XL330's current sensor sits at its power input. The torque includes
what the gearbox friction eats, so external load is the difference the policy
learns from history. The critic sees the true motor torque and Present Current.

## Phone sensors

- **IMU.** The model's `imu` site carries CoreMotion's device frame: x right, y
  up the screen, z out of the screen.
  - At home the screen faces forward, so x is the robot's left, y is up, and z is
    forward.
  - The app reads `CMDeviceMotion.gravity` (g) and `rotationRate` (rad/s) at
    CoreMotion's 100 Hz maximum.
  - The model gives the newest sample 5–25 ms late, with a random sample phase.
    Errors are drawn per episode: gyro bias, a 1° fusion tilt, and up to 2° of
    phone tilt in its pocket. Noise is per sample.
  - The noise is a few times Bosch's BMI323 datasheet values. The real IMU is an
    unidentified Bosch part.
  - Raw acceleration is modelled too, as CoreMotion signs it: (0, 0, −1) face up,
    which is the negative of MuJoCo's accelerometer, in g.
  - Where the IMU sits in the phone is a guess, 40 mm above centre.
- **Cameras.** Four MJCF cameras sit at the real lens positions, in portrait:
  `front` (TrueDepth, about 23 mm equivalent), and `rear_main` (24 mm),
  `rear_ultrawide` (13 mm) and `rear_tele` (120 mm), which look backwards.
  - `phone.with_camera(cfg, "front", kind="depth")` adds one as a separate
    `camera` observation group for a CNN.
  - Frames arrive at the camera's rate (30 fps default) and 30–50 ms late, so a
    frame is held for a few control steps. RGB and depth render through MuJoCo
    Warp's batch ray tracer.
  - The registered tasks are blind; vision is ready for teacher–student
    distillation.

## Timing

`link.LinkCfg` mirrors [PROTOCOL.md](../protocol/PROTOCOL.md).

| Parameter | Value |
| --- | --- |
| Control period | 15 ms, one BLE connection interval: 6 physics steps of 2.5 ms |
| Telemetry age | Servos read 0.5–4 ms before the state frame leaves |
| Command latency | Goals land one interval plus 0.5–3 ms after the read, about 17 ms |
| Lost packets | 3% of commands come one interval later |
| Stalls | 0.05/s on average, 50–250 ms each: the MCU holds the last goals, as iOS stalls do |

These are design targets, not measurements. The state frame reports every
command's real latency: fit these numbers to it.

## Domain randomization

Everything is drawn per episode, and per servo where it applies.
`Randomization.scale` shrinks every span toward nominal; training widens it from
0.3 to 1 over the first 1,500 iterations. Measure a parameter and you can narrow
its span.

| Parameter | Span | Why it is unknown |
| --- | --- | --- |
| Floor friction at the stilt tips | 0.25–1.2 | PETG tips on wood, tile, carpet |
| Friction of other contacts | 0.3–1.0 | falls |
| Battery open-circuit voltage | 6.6–8.4 V | 2S Li-ion charge state |
| Battery and wiring resistance | 0.05–0.3 Ω | cells, connectors, wire gauge |
| Electronics idle current | 0.25–0.6 A | MCU, radio, servo electronics |
| Servo torque constant kt | ×0.92–1.08 | unit-to-unit |
| Winding resistance | ×0.9–1.3 | unit spread, and winding temperature |
| Gearbox friction and damping | ×0.7–1.5, ×0.6–1.6 | wear, temperature, lubrication |
| Firmware gain scaling | ×0.9–1.1 | BAM measured /256; the manual says /128 |
| Current limit | ×0.9–1.1 | |
| Armature (reflected rotor inertia) | ×0.85–1.15 | |
| Encoder offset | ±0.02 rad | horn spline, calibration |
| Link mass and inertia | ×0.9–1.1 | print variation, screws, wires; via pseudo-inertia, so it stays physical |
| Torso mass and inertia | ×0.97–1.12 | unweighed wiring and electronics |
| Torso CoM | ±6 mm | the same, plus the phone's seat |
| Command latency, lost packets, stalls | see Timing | radio and app |
| IMU latency, sample phase, bias, noise, fusion tilt, mount tilt | in `PhoneImuCfg` | the phone |
| Pushes | Stand: up to 0.25 N on the torso for 50–150 ms, every 1–3 s; Walk: 0.1 m/s, every 3–8 s | robustness |

### Worth adding as they matter

- **Floor slope and compliance.** Use mjlab's terrain generator for slopes and
  steps, and randomize contact `solref` for carpet.
- **Backlash.** XL330 backlash isn't published; estimates run 0.5–1.5°. BAM
  doesn't model it. If the bench shows it matters, add a dead-band joint.
- **Winding heating.** Over long episodes, R rises 0.4%/°C. This needs a thermal
  state from I²R.
- **Joint stops.** Randomize them once real ones are measured.
- **Camera exposure, white balance, lighting and textures** for vision policies.
  mjlab has `dr.mat_*`, `dr.light_*` and `dr.cam_*`.
- **A screen touch.** Taps push the head.

## Tasks, and policies that can be combined

| Task | Goal |
| --- | --- |
| `PhoneGirl-Stand` | Balance on planted stilt tips with the waist and the hips' roll and pitch, through shoves on the torso. The knees, thigh yaws and arms hold home: their actions are scaled to zero. Rewards: upright, CoM over the line between the tips, posture, stillness, both tips on the floor, no slipping, low copper loss. |
| `PhoneGirl-Walk` | Track a twist command (−0.15 to 0.25 m/s forward, ±0.1 m/s sideways, ±0.6 rad/s turning) with steps. |
| `PhoneGirl-Stand-Ideal` | Stand on the nominal robot over a perfect link: no randomization, latency or stalls. A diagnostic, not for deployment: is balancing on the tips possible at all? |

Every task shares the actor's inputs, the 17 joint targets and the twist-command
slot; stand holds the command at zero. So policies are interchangeable on the
phone, and can be distilled into one: rsl_rl 5.5 has a student–teacher
`Distillation` algorithm. Give a new skill a new command or task embedding by
extending that slot, never by reordering. The critic sees privileged state: true
velocities, contacts, friction, supply and torques.

PPO uses an asymmetric actor–critic with ELU MLPs (actor 256-256-128) and a
history of three observations. Episodes are 20 s; falls end them, as does any
body part other than a stilt touching the floor. Mirror pairs and signs are in
`robot.MIRROR`, ready for rsl_rl's symmetry augmentation.

## Deployment

The phone app has to do exactly what the simulator does. Every exported ONNX
file carries it in its `phone_girl` metadata (`deploy.read(path)`):

- **Inputs, in order.** Gravity (3), gyro (3), joint position − home (17), joint
  velocity (17), torque estimate (17), bus voltage − 7.4 V (1), last action (17)
  and twist command (3), repeated for 3 steps. Each term's history runs oldest to
  newest, term after term. All values are in SI units; the network normalizes
  them.
- **Output.** The 17 actions. Each target is home + 0.4 × action, clipped to the
  soft limits and sent as round(target − home)/tick goals.
- **Encoding.** Calibrate every servo so the home pose reads 2048, using control
  opcode 4. Then joint position − home = (Present Position − 2048) × 2π/4096.

`tests/test_deploy.py` checks the ONNX output against the trained actor. ONNX
Runtime's iOS package runs the file as is. For Core ML, convert the PyTorch
checkpoint with coremltools, which no longer reads ONNX. A 3-layer MLP is also
small enough to hand-write with Accelerate.

## Measure before trusting

These items are assumptions in this model. Measure them on the robot, roughly in
this order:

1. **Servo variant.** XL330-**M288**-T is assumed; the M077 is geared
   differently. Use the capture opcode to record step responses on the robot's
   own servos and refit BAM (`bam.fit`).
2. **Supply.** Two 18650s in series drive the servos directly. Measure the pack
   plus wiring resistance by stepping a load, and the electronics' idle current.
3. **Joint travel.** Find the real stops, then set `mjcf.TRAVEL_DEG` and the
   MCU's soft limits.
4. **Electronics mass.** Weigh the electronics box and the wiring: pass
   `--electronics-g` to `phone-girl-export`, then rebuild.
5. **Link timing.** Plot `command_latency` from real state frames and count
   `seq` gaps (stalls), then fit `LinkCfg`.
6. **IMU.** Log CoreMotion standing still and rocking. Fit noise, bias and
   latency (`systemUptime − timestamp`).
7. **Present Current sign** under load in both directions.
8. **Tip friction** on the floors you'll use, from the slip angle of a stilt
   held against a tilted board.

## Tests

```sh
uv run pytest -q
```

| File | Checks |
| --- | --- |
| `test_model.py` | The MJCF against an independent OpenSCAD run; mass and inertia; standing on the tips; the knees' locked rest and travel; the stilts' collision gap; the IMU frame and camera directions; `phone-girl-view`'s stand holding home. |
| `test_xl330.py` | The motor law and M6 friction against BAM; a closed loop against BAM's CPU controller. |
| `test_env.py` | Clean resets; Stand moving only the waist and hips; commands landing after exactly the modelled latency; stalls holding; randomization spans; the web viewer's command controls; the closed-form body randomization against pseudo-inertia; the fall check against per-body contact sensors; the slip penalty pairing each foot with its own contact; on CUDA, the graph-captured `set_const` and the compiled servo and IMU code against the uncompiled ones. |
| `test_phone.py` | CoreMotion gravity at rest; the 100 Hz sample-and-hold; camera frames held and late. |
| `test_protocol.py` | Frame round trips; sizes within one notification; the C header byte-identical to Python; the app-side encoding equal to the simulator's. |
| `test_deploy.py` | The ONNX output equals the actor's; the attached contract matches the environment, with each joint's action scale. |

Versions are pinned in `uv.lock`: mjlab at commit `8bb2bc9e` on main, MuJoCo
and MuJoCo Warp 3.16, warp-lang 1.18, torch 2.14.1 (CUDA 13) and BAM 1.0.2.
mjlab main is ahead of its 1.6.0 release with fixes this project needs: delay
buffers that start with the right lag, IMU-style bias noise that no longer
random-walks, and per-world Gaussian draws.
