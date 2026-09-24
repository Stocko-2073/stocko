# Motor voltage model inputs

Status: initial averaged stepper model implemented, 2026-09-22. The default
remains the original velocity servo. The electrical profiles are opt-in,
datasheet-based estimates and have not been calibrated against hardware.

## Running the model

```sh
python -m ubot_sim.demo --drive eiiev_12v --episodes 1
python -m ubot_sim.demo --drive talentcell_24v --episodes 1
python -m ubot_sim.demo --drive talentcell_24v --supply-voltage 24 --episodes 1
python -m ubot_sim.motor_benchmark
```

The baseline navigation controller can trip the new model's slip protection;
successful navigation under the old servo does not establish stepper feasibility.
The benchmark includes a gentle start and a firmware-envelope start, and writes
`benchmarks/motors.json`. See [results and interpretation](benchmarks/motors.md).

```python
from dataclasses import replace
from ubot_sim.env import UBotNavigationEnv
from ubot_sim.motor import DRIVE_PROFILES

config = replace(DRIVE_PROFILES["talentcell_24v"], supply_voltage=24.0)
with UBotNavigationEnv(drive=config) as env:
    obs, info = env.reset(seed=0)
    obs, reward, terminated, truncated, info = env.step([0.01, 0.01])
    print(info["motor"])
```

`info["motor"]` reports phase currents, wheel torque, ideal-source current
and power, winding copper loss, net energy, encoder/command mismatch and slip
faults. Values other than energy are from the last integration step, not a
policy-period average. Negative source power represents energy returned to
an ideal absorbing supply, not a calibrated battery regeneration model.

## Implemented physics and provenance

For each motor, two phase currents evolve under `L di/dt = v - R i - e`.
The averaged current regulator selects a voltage bounded by the ideal supply.
The RL solution is integrated analytically for each step with midpoint rotor
position and back EMF. Commanded phase follows integrated commanded speed;
it does not follow actual rotor position. This permits loss of synchronism.

For rotor electrical angle `theta`, torque is
`Kt * (-iA sin(theta) + iB cos(theta))`. The back-EMF vector is
`Kt * motor_speed * [-sin(theta), cos(theta)]`, preserving electromagnetic
power reciprocity. Rigid ideal gears multiply torque by 40/12 and reflect
rotor inertia by `(40/12)^2`. Existing estimated joint damping remains.

| Parameter | Initial value | Provenance / qualification |
|---|---|---|
| Phase R / L | 2.3 ohm / 4.4 mH | Motor datasheet; tolerances ±10% / ±20% |
| Full step / electrical pole pairs | 1.8 degrees / 50 | Datasheet / calculated |
| Rotor inertia | 5.4e-6 kg m² | Datasheet 54 g cm²; replaces prior drive armature estimate |
| Kt and matching mechanical-speed Ke | 0.2121 N m/A and V s/rad | Derived sinusoidal approximation: 0.45/(sqrt(2)*1.5), assuming two energized phases at rated current |
| Run / hold current | 1.1601 / 0.5524 A RMS | Current firmware conversion for R110 and CS=20/9; provisional same target for 2208 |
| Winding-current target amplitude | sqrt(2) × RMS setting | Sinusoidal microstepping convention |
| 2209 / 2208 bridge resistance | 0.34 / 0.57 ohm | Typical chip high-side plus low-side resistance at 25 C |
| Sense resistance | 0.11 ohm | Current R110; assumed for unselected 2208 carrier |
| Hold delay / reduction duration | 0.5 / 2 s | Smooth approximation; not register-exact |
| Encoder / slip monitoring | 4096 counts/rev; 200 Hz; 200 microsteps; 1 s reference leak | Existing StepperServo defaults; ideal encoder |
| Integration step | At most 25 microseconds by default | Both mechanics and electrics; convergence checked at 12.5 microseconds |

Sources: [motor datasheet](https://omc-stepperonline.com/download/17HS15-1504S-X1.pdf),
[TMC2209 datasheet](https://www.analog.com/media/en/technical-documentation/data-sheets/TMC2209_datasheet_rev1.09.pdf),
[TMC2208 specifications](https://www.analog.com/en/products/TMC2208.html),
[phase-current and torque background](https://www.analog.com/media/en/technical-documentation/application-notes/17900133an323.pdf),
[firmware current conversion](../firmware/base/components/drive/MotorCurrent.h),
[firmware slip protection](../firmware/base/components/drive/StepperServo.h).

The command ramp retains the existing simulation's acceleration/deceleration
envelope, evaluated at the physics timestep; it is not an exact 200 Hz replay
of the firmware's command updates. The slip monitor runs at 200 Hz. Either
wheel's slip fault freezes both commanded positions, retains energized hold,
and terminates a navigation episode as failed. Reset clears electrical state,
energy and faults after settling the unpowered robot. `env.motor.enabled=False`
models ideal freewheeling with immediate current removal.

This model does not reproduce individual chopper transitions, microstep
quantization, detent torque, saturation, position-dependent inductance, gear
backlash or efficiency, thermal evolution, UART delays, sensor noise, BMS
behavior or battery sag. Motor torque constants and loss terms need calibration.
The same physical robot mass is used in both profiles; pack capacity and mass
below are provenance, not an implemented runtime or replacement-mass model.

## Batteries

The owner identified the current and planned replacement packs. Values below
are seller specifications, not measurements of the installed batteries.

| Parameter | Current: Eiiev B0F7X6WDYY | Planned: Talentcell LF8011 B0CNLKKL9C |
|---|---|---|
| Chemistry | LiFePO4 | LiFePO4 |
| Marketed voltage | 12 V | 24 V |
| Nominal voltage | 12.8 V | 25.6 V |
| Capacity | 8 Ah | 6 Ah |
| Nominal energy | 102.4 Wh (calculated) | 153.6 Wh (listed and calculated) |
| Output current specification | 5 A BMS rating | 10 A maximum output |
| Output voltage range | Not verified | 18–29.2 V; seller says mostly 24–26 V |
| Listed mass | 2.2 lb (about 1.0 kg) | 1.4 kg |
| Driver | Existing TMC2209 | TMC2208 (owner decision, 2026-09-22) |

Sources checked 2026-09-22:

- [Eiiev seller listing](https://www.amazon.com/Eiiev-Lithium-Phosphate-Rechargeable-Batteries/dp/B0F7X6WDYY)
- [Talentcell seller listing](https://www.amazon.com/Talentcell-LF8011-Rechargeable-Phosphate-Batteries/dp/B0CNLKKL9C)

The current ratings do not establish exact BMS trip thresholds, delays or
recovery behavior. Battery current is not motor phase current. Neither
listing establishes internal resistance or a usable voltage-versus-charge
curve. Do not infer either from Ah capacity or BMS current rating.

## Comparison scope

1. Compare ideal fixed supplies at 12 V and 24 V to isolate voltage effects.
2. Compare pack nominal supplies at 12.8 V and 25.6 V with identical motor
   current, commands, mass and terrain. Explicitly label zero source
   resistance as an ideal-supply assumption, not a measured battery property.
3. Next: add measured driver-terminal voltage/current and effective source
   resistance for each pack. Sweep uncertain values before calibration.
4. Evaluate the actual replacement separately: use a TMC2208 driver profile
   for the 24 V setup and TMC2209 for the current 12 V setup. Update driver
   losses and current calibration for the selected carrier; do not assume
   identical current settings or thermal limits. Update battery mass, robot
   center of mass and inertia using measured pack masses and placement.
   Listed masses suggest roughly 0.4 kg added, but are not calibration data.

The benchmark implements comparisons 1 and 2 with the same robot mechanics.
Complete replacement-mass and measured-source modeling remain follow-up work.

## Selected 24 V driver

The owner selected TMC2208 drivers for the 24 V setup on 2026-09-22.
The [TMC2208 specifications](https://www.analog.com/en/products/TMC2208.html)
give a 36 V upper operating supply limit, above the LF8011's listed 29.2 V
maximum output. This resolves the previous chip operating-voltage mismatch.
Exact carrier current-sense resistors, current settings, cooling and board
voltage rating remain inputs to confirm for the replacement profile.

The existing 12 V setup retains TMC2209 drivers. The
[TMC2209 datasheet](https://www.analog.com/media/en/technical-documentation/data-sheets/TMC2209_datasheet_rev1.09.pdf)
specifies a 29 V upper operating supply limit; it is not the selected driver
for the new pack.

[Driver investigation](TMC_DRIVER_OPTIONS.md) records higher-voltage module
options, verified spare XIAO pins, and UART/motion-control compatibility.

## Measurements still needed

- Driver-terminal voltage and battery current at several loads, for supply
  sag and effective battery-plus-wiring resistance.
- Wheel torque versus speed at known supply voltage/current settings, plus
  command and encoder traces through acceleration and stall/recovery.
- Actual replacement pack mass and placement for complete robot comparisons.
- Temperature-versus-time data only when adding calibrated thermal behavior.

Detailed BMS thresholds, discharge curves and thermal parameters can come
from manufacturer documentation if obtained; otherwise they remain unknown.
Short fixed-supply voltage comparisons do not require those extensions.

## Field observations: 2026-09-22

Owner report: app-controlled driving with the current 12 V battery and
TMC2209 drivers stalled on slight hills and small sticks in grass. It drove
well on concrete, including similarly slight driveway hills. Slope angles,
stick dimensions, command histories, wheel speeds, loaded supply voltage and
the installed app/settings snapshot were not recorded here. Do not assign
numeric values or a stall threshold from this qualitative observation.

Follow-up: the owner did not try or does not recall whether reducing joystick
speed restored motion versus needing to back up/reposition. Recovery behavior
remains unknown; neither response should be inferred from this outing.

This supplies a calibration ordering: reproduce successful concrete travel
and shallow climbs, then investigate added grass resistance and obstacle
loads that can cause loss of synchronism. Grade alone does not explain the
reported surface contrast. Possible contributions include turf deformation,
vegetation drag, caster resistance or a snag; the observation does not identify
which contribution dominates or establish supply sag as the cause.

The synthetic benchmark applies an immediate 0.4 wheel-turn/s target.
That is not a replay of the manual app drive. The current app source shapes
stick deflection through a linear/cubic response; the actual thumb motion,
installed app version and resulting command trajectory are unknown. Thus
the benchmark's flat-ground startup stall is a calibration concern, not
proof of disagreement under identical inputs or confirmation of the grass
failure mechanism.

Next calibration comparison: capture or reproduce representative app wheel
commands on concrete, then repeat with comparable commands on the grass
slope and at a measured small obstacle. Keep the same motor parameters
across surfaces. Record whether reducing speed restores motion or backing
up/repositioning is necessary. Retain successful runs as constraints as well
as failures; do not tune only until the grass run stalls. The field report
does not yet establish whether the 24 V upgrade will resolve these stalls.
