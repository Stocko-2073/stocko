# Initial motor voltage comparison

2026-09-22. Generated with `python -m ubot_sim.motor_benchmark`.
[Raw results, configurations and source hashes](motors.json).
[Model assumptions and parameter provenance](../MOTOR_MODEL.md).

These are predictions from an uncalibrated averaged stepper model, not measured
motor performance. Both profiles use the same 1.1601 A RMS run current, ideal
fixed voltage and identical robot mechanics. Battery sag, thermal effects and
replacement pack mass are excluded. The 2208 carrier's current calibration
and loss parameters remain provisional.

## Synchronous electrical bench

The bench prescribes actual rotor speed and a 90-degree electrical command
lead. It reports average torque at that operating point, not a pull-out curve
or guaranteed sustainable load. Gear torque conversion is ideal. Static
measurements keep run current enabled; normal idle operation reduces current.

| Wheel turns/s | Motor RPM | 12.8 V / TMC2209 wheel torque | 25.6 V / TMC2208 wheel torque |
|---|---|---|---|
| 0 | 0 | 1.160 N m | 1.160 N m |
| 0.3 | 60 | 1.160 N m | 1.160 N m |
| 1.0 | 200 | 1.160 N m | 1.160 N m |
| 2.0 | 400 | 0.749 N m | 1.160 N m |
| 3.0 | 600 | 0.261 N m | 1.113 N m |

Values above use 25 microsecond integration. The current firmware maximum is
one wheel turn/s: the final two rows are experiments beyond that envelope.
The model predicts little voltage benefit inside the current envelope at
this current setting; higher voltage preserves torque when the low-voltage
driver can no longer track the current target at higher speed.

To separate supply voltage from chip losses, the report also compares the
same TMC2208 profile at exactly 12 and 24 V. At two wheel turns/s it predicts
0.650 versus 1.160 N m per wheel; at three, 0.190 versus 1.060 N m.

## Coupled robot starts

Seed 0, flat ground, smooth wheel contacts, unchanged robot mass:

- Gentle target ramp: increase by 0.01 wheel turns/s per 20 ms up to 0.3.
  Both profiles travel approximately 0.3462 m in two seconds without faults.
- Default firmware-envelope acceleration: request 0.4 wheel turns/s with
  the existing 8 turns/s² command ramp. Both profiles lose synchronism and
  terminate on encoder slip at the 0.18 s policy boundary, after about 6 mm.
- No MuJoCo warnings or non-finite states in these runs.

The aggressive-start result persists with finer integration, but it is not
evidence that the hardware must stall. It depends on uncalibrated torque,
inertia, drivetrain losses, ideal current regulation and the existing contact
model. It identifies a useful hardware start/encoder recording to obtain.

Subsequent owner observation (2026-09-22): the app-driven 12 V/TMC2209 robot
drove well on concrete including slight driveway hills, but stalled on
slight hills and small sticks in grass. This is a qualitative calibration
constraint, not validation of this synthetic startup test. Actual app command
trajectories and obstacle/slope measurements are missing. See
[field observations and calibration order](../MOTOR_MODEL.md#field-observations-2026-09-22).

## Numerical checks

The benchmark repeats electrics and coupled starts at 12.5 microseconds.
Electrical torque changes by less than 0.03% through two wheel turns/s.
At three turns/s, the 12.8 V profile changes by about 3%; the other profiles
change by less than 0.1%. Treat that high-speed row as less numerically resolved.
Gentle-start travel differs by about 1.3 micrometres. Aggressive-start travel
differs by less than 0.4 mm; fault reporting remains at 0.18 s.

An initial 100 microsecond integration showed substantial error at three
wheel turns/s under 12 V, motivating the smaller default. This optional
model runs physics at 40 kHz (or finer), with policy updates still at 50 Hz;
it is substantially more expensive than the default velocity-servo model.

Automated checks cover RMS/peak convention, current limiting, winding/bridge
energy balance, voltage saturation, reverse symmetry, high-speed voltage
advantage, timestep refinement, run/hold reduction, fault latching, freewheel,
deterministic reset, Gym API behavior and gentle robot motion on both profiles.
