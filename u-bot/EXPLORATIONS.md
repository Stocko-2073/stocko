# Yard driving explorations

Discussion notes, 2026-09-20. Ideas for the next work session; no firmware or
hardware changes are part of this exploration.

## What we observed

The first reported grass outing was positive overall, but the robot got stuck
several times on a hill and on small sticks. The owner confirmed these were
**stalls with chatter**, rather than tires spinning against the grass. This is
consistent with the steppers losing synchronism under load and makes a torque
boost worth testing. It does not yet distinguish insufficient torque reserve
from a mechanical snag, excessive commanded speed/acceleration, or supply sag.
There is no outdoor telemetry attached to these notes.

The owner confirmed the current battery is **12 V, 8 Ah**. The firmware models
it as 4S LiFePO4; confirm the pack label, discharge/BMS ratings and charger
specification before choosing a replacement.

An X mutual suggested:

> Dynamic phase amp control or static settings on the driver? If you could give
> it a *overdrive* mode when commanded position slips from the encoder it would
> generally run cooler but pull out of holes better when needed.

**Yes: our hardware has the ingredients for this. It would require firmware
work. The confirmed stalls make it a promising experiment, although the cause
of the overload still needs investigating.**

## What that means

“Phase amps” means current through the motor windings. The suggestion is to
use modest current during easy travel, briefly increase it when a wheel falls
behind its commanded motion, then return to the normal setting. More current
can provide more torque, at the cost of more heat and electrical demand.

This would be a torque boost, not a speed boost. It need not exceed the motor's
rating: initially, treat “boost” as using more of the existing allowed current
range. Lower average heating is plausible compared with running at the high
setting all the time. Adding bursts to today's baseline would not, by itself,
make it run cooler than today.

## What we already have

The current source and [rack record](firmware/base/components/drive/tests/RACK_TEST_2026-09-20.md)
establish the following. The earlier “Investigate drive speed limit” session
verified saved settings of `vmax_tps=1.0`, `accel_tps2=8.0` and
`decel_tps2=2.0`, with nominal programmed run/hold currents of 1160/552 mA RMS.
Commit `7969c8856f00f648f974c7c5d1dc15edc9377627` also records the speed and
acceleration restoration. These are the last verified settings, not a live
readback during this discussion; actual stick position at each stall is unknown.

| Part | Current arrangement | Relevance |
|---|---|---|
| Motors | STEPPerOnline 17HS15-1504S-X1, rated 1.50 A/phase | Existing firmware caps requested current at 1500 mA RMS |
| Drivers | BTT TMC2209 V1.3, UART, external R110 sense resistors | Software sets current; VREF pots are ignored |
| Current profile | 1200/600 mA requested run/hold; approximately 1160/552 mA nominal programmed | Already reduces current at rest; running current is fixed |
| Chopper | SpreadCycle | Keep this for the initial comparisons |
| Feedback | AS5600 on each wheel output shaft, after the 12:40 gears | Observes wheel motion rather than assuming commanded steps happened |
| Control | 200 Hz; joystick velocity commands with encoder-based slip monitoring | Existing mismatch signal is a starting point for detection |

The TMC2209 supports situation-dependent run-current changes through UART.
Its built-in CoolStep is another adaptive-current option, but depends on
StallGuard4 and StealthChop; switching to SpreadCycle disables it. StallGuard4
also has limitations at low motor speeds. An encoder-based approach fits our
existing SpreadCycle configuration better as the first investigation.
[Driver datasheet, sections 9, 11 and 12](https://www.analog.com/media/en/technical-documentation/data-sheets/TMC2209_datasheet_rev1.09.pdf).

The motor's rating and the manufacturer's RMS/peak guidance support retaining
our existing nominal 1500 mA request ceiling for this exploration; neither
establishes the assembled robot's thermal margin.
[Motor datasheet](https://omc-stepperonline.com/download/17HS15-1504S-X1.pdf),
[manufacturer current-setting guidance](https://help.omc-stepperonline.com/hc/s/articles/how-to-set-the-current-on-stepper-driver-rms-or-peak).

Using the conversion in [MotorCurrent.h](firmware/base/components/drive/MotorCurrent.h),
1500 mA requested programs about 1492 mA. Compared with the present 1160 mA
nominal run setting, that is about **29% more current**. A rough proportional
torque estimate suggests a modest reserve, not twice the pulling power. At
equal winding resistance, winding heating scales as current squared: about
**65% more while boosted**. These are estimates, not measured yard performance
or total battery-power predictions.

## First distinguish the failure

| Observation | Possible explanation | Useful next comparison |
|---|---|---|
| Wheel stops or chatters despite a motion command | Insufficient torque, lost motor synchronism, or a mechanical blockage | Log command versus shaft motion; try slower travel and gentler acceleration |
| Wheel rotates but robot stays put | Tire slip or a wheel losing ground contact | Inspect tread, contact and weight distribution |
| Caster catches a stick or digs into grass | Obstacle geometry, caster alignment or rolling resistance | Watch the caster and underbody during a repeatable crossing |
| App reports a fault or motion stops abruptly | Slip protection, driver/power/encoder fault, or command loss | Record the exact fault, rail voltage and command timing |

Our firmware's “slip” means commanded motor motion disagreeing with the output
encoder. It does **not** mean tire slip against the ground. A spinning tire can
track its commanded angle perfectly while the robot goes nowhere. Ground
progress needs another observation, initially video; eventually camera/IMU
information could help. Planned caster encoders measure swivel angle, not
ground distance.

More torque could help climb a small obstruction, but could also spin a tire,
dig a caster in further, or load a jammed gear train. This is why observing the
failure comes before choosing the remedy.

## A possible boost design

This is a proposal to investigate, not an implementation specification.

- Begin with a deliberately requested, time-limited boost to establish whether
  extra current helps at all. Consider automatic triggering only after that.
- For automatic triggering, look for sustained, direction-consistent lag while
  motion is requested, before the existing hard slip limit. Require healthy
  encoder data and distinguish ordinary reversals, backlash and acceleration.
- Use separate entry/exit thresholds and a minimum stable interval to avoid
  rapid current toggling. Bound each burst and total time boosted; require
  recovery/cooldown before another burst. Tune these from measurements.
- If motion does not recover, stop and retain the fault. Keep deadman, driver,
  encoder and peer-wheel protections authoritative. Do not automatically clear
  a latched fault or restart motion.
- Compare boost alone with reduced speed/acceleration. Once a stepper loses
  synchronism, raising current at the same commanded speed may not recover it.
- Decide whether boost applies per wheel or to both, and test its effect on
  steering. A unilateral recovery must not produce an unexpected pivot.

Implementation details that matter later:

- [VelGen.h](firmware/base/components/drive/VelGen.h) currently stages current
  only while disabled. A dedicated, verified runtime-current path is needed;
  simply removing that guard is insufficient. Keep transient boost separate
  from persisted settings and preserve the hold-current profile.
- In [StepperServo.h](firmware/base/components/drive/StepperServo.h), joystick
  mode makes the position target follow the encoder. `errorCounts()` therefore
  is not the desired trigger. Examine commanded-step integral versus encoder
  motion (`slipSteps()`), together with commanded/measured velocity.
- That slip signal has a one-second leaking reference, not an absolute position
  error. Characterize slow stalls as well as abrupt ones. The recorded encoder
  nonlinearity is about 20 counts around a revolution; wheel B also has an
  unresolved weak-magnet report. Do not interpret every small mismatch as load.
- Current writes and verification share the motor UART. Schedule transitions
  without compromising the 5 ms control period, expose actual programmed state,
  and stop on failed writes. Avoid register traffic on every control tick.

## Would higher battery voltage help?

**Potentially, especially for torque at speed. It is not yet a justified
rebuild for these stalls.** Current produces motor torque; additional supply
voltage helps that current rise quickly enough as the motor steps faster.
Winding inductance resists rapid current changes, and motor back EMF increases
with speed. Higher voltage can therefore preserve torque that falls away at
higher speed. At standstill or very low speed, if the driver already reaches
the same commanded phase current, extra voltage gives little additional torque.
Doubling supply voltage does not double holding torque.
[Analog Devices explanation](https://ez.analog.com/motor-control-hardware-platforms2/a/documents/DO19271/what-voltage-supply-is-ideal-for-a-stepper-motor),
[motor current and voltage background](https://www.analog.com/en/resources/technical-articles/low-voltage-motor-control.html).

The distinction is the speed commanded **before** the stall: a stopped,
chattering rotor does not establish that the original problem was low-speed
torque. With our 3⅓:1 reduction, 0.3 wheel turns/s corresponds to 60 motor RPM;
1 wheel turn/s corresponds to 200 motor RPM. The last verified saved maximum
was 1 wheel turn/s; actual commands preceding each stall are unknown, and
these conversions alone cannot establish a voltage bottleneck.

The 8 Ah rating describes charge capacity, not an 8 A discharge limit or motor
phase current. Battery/BMS current capability and loaded voltage drop need
their own measurements. A higher-capacity pack at the same voltage could help
if the existing pack sags under load, but capacity alone does not establish
that it would.

There are concrete limits to a voltage upgrade:

- The TMC2209 datasheet gives 29 V as the upper operating supply limit; this
  is not a target voltage. Leave room for transients, including energy returned
  during braking. Absolute maximum ratings are not operating allowances.
  [Driver datasheet, sections 19–20](https://www.analog.com/media/en/technical-documentation/data-sheets/TMC2209_datasheet_rev1.09.pdf).
- A nominal “24 V” battery is not a regulated 24 V supply. For example, an 8S
  LiFePO4 pack charged to 3.65 V/cell reaches 29.2 V, already above that chip
  operating limit before transients. Do not assume a direct pack swap works;
  
  verify the exact carrier-board rating too.
- The [power-board notes](firmware/protoboard/README.md) specify a 100 µF
  capacitor rated **25 V or higher**, with the installed rating unconfirmed.
  They also leave the 5 V converter's input rating unverified. Both connect to
  the battery rail and need checking or replacement for the chosen maximum
  voltage. Review every other load on that rail and the charger/BMS arrangement.
- Battery sensing uses a 100k/10k divider and a 4S LiFePO4 percentage table.
  Review ADC range and divider margin, recalibrate, and update the pack model.

**Decision experiment:** first compare the same obstacle at lower speed and
gentler acceleration, then compare current settings separately. If slower
travel substantially restores pulling ability, higher voltage deserves a
controlled comparison, although resonance and other speed-dependent effects
can produce a similar result. If the robot still stalls while creeping with
adequate phase current and a healthy supply, investigate mechanical resistance,
gearing or motor torque before investing in higher voltage.

If warranted, compare motor supply voltages on a controlled bench fixture with
verified component ratings and a provision for braking energy, holding current,
load and speed constant. Establish a repeatable improvement before changing the
robot's battery system. A boost converter is not a free shortcut: input current,
losses and returned braking energy also need engineering.

## Could a larger STEPPerOnline NEMA 17 help?

Catalog checked 2026-09-20. The CAD does have room to investigate:
[motor()](u-bot.scad) uses a 39 mm body, while the motor cutout uses 50 mm
(`h=50`, line 470 at the time of review). A 48 mm body is therefore a plausible
candidate with only 2 mm nominal length margin. This is a source-level envelope
check, not a rendered collision check or verified physical fit; connector and
wire clearance still matter.

| Motor | Body length | Rated holding torque | Rated phase current | Inductance | Assessment |
|---|---:|---:|---:|---:|---|
| Existing 17HS15-1504S-X1 | 39 mm in CAD; current catalog lists 40 mm | 0.45 N·m | 1.5 A | 4.4 mH | First establish performance near its existing current ceiling |
| 17HS19-2004S1 | 48 mm | 0.59 N·m | 2.0 A | 3.0 mH | Best holding-torque candidate among these plausible fits, but needs more current to earn that rating |
| 17HE19-2004S | 48 mm | 0.55 N·m | 2.0 A | 2.4 mH | Lower-inductance alternative worth comparing for speed performance; less rated holding torque than the S1 |
| 17HS24-2104S | 60 mm | 0.65 N·m | 2.1 A | 3.0 mH | Exceeds the existing cutout by 10 mm; larger mechanical change for a modest further gain |

Manufacturer specifications:
[existing motor](https://www.omc-stepperonline.com/nema-17-bipolar-45ncm-63-74oz-in-1-5a-42x42x39mm-4-wires-w-1m-pin-connector-17hs15-1504s-x1),
[17HS19-2004S1](https://www.omc-stepperonline.com/nema-17-bipolar-59ncm-84oz-in-2a-42x48mm-4-wires-w-1m-cable-connector-17hs19-2004s1),
[17HE19-2004S](https://www.omc-stepperonline.com/e-series-nema-17-bipolar-55ncm-77-88oz-in-2a-42x48mm-4-wires-w-1m-cable-connector-17he19-2004s),
[17HS24-2104S](https://www.omc-stepperonline.com/nema-17-bipolar-1-8deg-65ncm-92oz-in-2-1a-3-36v-42x42x60mm-4-wires-17hs24-2104s).

The key comparison is **equal current**, not just the advertised torque.
Using torque proportional to current as a rough screening estimate, the S1 at
1.5 A gives 0.59 × 1.5/2 = **0.44 N·m**, essentially the existing motor's
0.45 N·m rating at 1.5 A. This is not a measured torque curve; saturation and
drive conditions affect the result. The lower inductance may help while moving,
but does not prove improved obstacle clearance at 12 V. Its published
[pull-out curve](https://www.omc-stepperonline.com/download/17HS19-2004S1_Torque_Curve.pdf)
is labeled 2 A, 24 V, half step, so it does not establish our 12 V performance.
At their respective full rated currents, 0.59 versus 0.45 N·m is a 31% increase
in holding torque, not a guaranteed 31% increase in running torque.

There is a hardware ceiling as well as the firmware's 1500 mA limit. With the
present R110 resistors, digital reference and vsense=0, the formula in
[MotorCurrent.h](firmware/base/components/drive/MotorCurrent.h) reaches only
about **1.77 A RMS at maximum scale**. A software limit change alone cannot
provide the S1's full 2 A. Driver cooling, board ratings and the power path would
need assessment even below that maximum; exploiting the full motor rating
would require a different driver arrangement or an engineered board change.
No increase to the current limit is proposed here.

All four catalog listings specify a 5 mm diameter, 24 mm shaft; the CAD's
30 mm shaft is an envelope rather than an exact catalog model. Verify actual
pinion engagement, mounting boss/holes and connector clearance against the
chosen revision. The
[17HS19-2004S2](https://www.omc-stepperonline.com/full-d-cut-shaft-nema-17-bipolar-59ncm-84oz-in-2a-42x48mm-4-wires-w-1m-cable-connector-17hs19-2004s2)
offers the same listed electrical specifications with a full-length shaft
flat, which may help set-screw placement. The E-series motor uses a different
wiring sequence from the S1; verify coil pairs rather than swapping plugs
blindly. The present output-shaft encoders can remain part of the design.

**Recommendation:** keep the 48 mm S1/S2 family on the shortlist, but test the
existing motors at a validated higher current first. A motor-only replacement
with unchanged current is not yet a convincing low-speed torque upgrade.
Consider a motor/driver change together if more reserve is still needed, and
compare it with increased gear reduction at the cost of travel speed.

## NEMA 23 candidate — high-effort drivetrain rework

The owner is considering the
[STEPPerOnline 23HS22-1504S-C14](https://www.omc-stepperonline.com/nema-23-stepper-motor-bipolar-1-8deg-1-16nm-164-3oz-in-1-5a-57x57x56mm-with-165mm-cable-molex-connector-23hs22-1504s-c14)
as a high-effort option. This is a candidate for investigation, not a selected
replacement or authorization to modify the drivetrain.

| Property | Existing NEMA 17 | Candidate NEMA 23 |
|---|---:|---:|
| Rated holding torque | 0.45 N·m | 1.16 N·m |
| Rated phase current | 1.5 A | 1.5 A |
| Phase resistance | 2.3 Ω | 3.6 Ω |
| Phase inductance | 4.4 mH | 13 mH |
| Frame/body | 42 × 42 × 39–40 mm | 57 × 57 × 56 mm |
| Shaft diameter/length | 5 / 24 mm catalog | 6.35 / 21 mm |
| Catalog motor mass | 0.28 kg | 0.68 kg |

**Assessment: a credible route to substantially more low-speed torque, with
12 V running performance as the main electrical uncertainty.** The rated
holding-torque ratio is 1.16/0.45 = 2.58. Unlike the 2 A NEMA 17 shortlist,
this motor's rated current fits the existing nominal current ceiling. NEMA
frame size alone does not require a new driver. The TMC2209 setup is a plausible
bench-test driver, subject to current waveform, chopper tuning and thermal
validation; suitability across the driving envelope is not established.

If the 3⅓:1 reduction is retained, ideal wheel holding torque at the motors'
rated conditions rises from 1.50 to 3.87 N·m per wheel before losses. These are
holding calculations, not measured driving torque or the present 1.16 A run
setting. We cannot promise 2.58 times the obstacle-clearing force.

The high inductance makes the torque-versus-speed curve and supply voltage
particularly important. At our present reduction, 0.20 m/s corresponds to about
59 motor RPM and 0.675 m/s to 200 RPM. Confirm performance at the desired speeds
on the actual 12 V supply. The
[base-model listing](https://www.omc-stepperonline.com/nema-23-bipolar-1-8deg-1-16nm-164-3oz-in-1-5a-5-4v-57x57x56mm-4-wires-23hs22-1504s)
links a torque curve, but an exact-variant curve under our conditions has not
been established. The C14 description also references a different 2804S model;
confirm the 1.5 A winding specification and dimension drawing with the supplier.

At equal phase RMS current, nominal winding copper loss scales with resistance:
3.6/2.3 = about 1.57 times the existing motor's loss. That does not predict a
57% higher case temperature; the larger motor has different thermal properties.
Two motors also add roughly 0.8 kg, affecting slope load and weight distribution.

Mechanical work includes wider/deeper leg housings, new motor mounting features,
a pinion hub for the larger and shorter shaft, and checking gear alignment and
clearances. Review printed gear teeth, hub fasteners and structural loads for
the higher torque. Output encoders and the existing ratio could potentially be
retained. The 165 mm leads and connector require wiring adaptation.

Before committing to printed parts, test one securely mounted sample under a
repeatable load with the existing driver and supply, initially at the current
baseline. Compare low-speed pull, stall behavior, temperature, supply sag and
usable speed with the existing motor, then assess a validated higher current.
If it only performs well at an unacceptably low speed, compare a lower-inductance
NEMA 23 with a suitable higher-current driver or a redesigned supply. Evaluate
those as complete alternatives before choosing the motor around its holding
torque alone. Keep the agreed joystick/current experiments ahead of this rework.

### Payload feasibility: 5 kg base plus 3–5 kg of tools

The owner's updated mass estimate is **5 kg for the NEMA 23 base and 3–5 kg
of payload**, giving **8–10 kg total**. Preliminary sizing makes the proposed
motors plausible for carrying that mass at low speed on level ground and modest
slopes, but does not establish generous reserve for hills, obstacles or tools
that push/drag against the ground.

Screening assumptions, not measured properties:

- Retain two driven wheels, 215 mm diameter and 40/12 reduction.
- Assume 80% transmission efficiency and equal torque sharing between motors.
- Use an illustrative rolling-resistance coefficient of 0.10 for the complete
  robot. This is a scenario value, not a validated coefficient for our grass,
  wheels or casters. Existing simulation rolling settings are also uncalibrated.
- Straight, steady uphill travel; exclude acceleration, sharp obstacles,
  steering scrub, tool working forces and traction limits.

With slope angle theta, the calculation is:

```text
required ground force = mass * 9.81 * (sin(theta) + 0.10 * cos(theta))
required torque per motor = ground force * 0.1075 / (2 * (40/12) * 0.80)
```

| Slope angle (grade) | Torque per motor, 8 kg | Torque per motor, 10 kg | 10 kg target with 2× steady-load reserve |
|---|---:|---:|---:|
| Level | 0.16 N·m | 0.20 N·m | 0.40 N·m |
| 5° (9%) | 0.30 N·m | 0.37 N·m | 0.74 N·m |
| 10° (18%) | 0.43 N·m | 0.54 N·m | 1.08 N·m |
| 15° (27%) | 0.56 N·m | 0.70 N·m | 1.41 N·m |
| 20° (36%) | 0.69 N·m | 0.86 N·m | 1.72 N·m |

The 2× column is a proposed screening reserve, not a universal requirement or
proof of obstacle capability. Its values must be available **while running at
the intended speed**, not merely as holding torque. Acceleration and tool loads
must be added before final sizing. See
[Oriental Motor sizing guidance](https://blog.orientalmotor.com/motor-sizing-basics-part-3-acceleration-torque-and-rms-torque?hs_amp=true).

Using the proposed motor's 1.16 N·m holding rating and assumed efficiency gives
a reference total wheel force of about **58 N**. It is not a validated continuous
driving force. For sensitivity, if testing found only 0.60 N·m available per
motor at the chosen speed/current/voltage, total force would be about **30 N**:
just above the 10 kg, 10° scenario's 27 N demand and below the 15° scenario's
35 N. The 0.60 value is an illustration, not an estimate from a torque curve.

Tool mass and tool working resistance are separate. An additional **20 N of
drag adds 0.40 N·m per motor** under these assumptions, taking the 10 kg, 10°
case to about 0.94 N·m before reserve or acceleration. Dense grass, caster
snags and one-wheel obstacles can likewise defeat a design that passes the
steady straight-line calculation. Payload position also determines how much
weight rests on the driven wheels versus passive casters, affecting traction,
rolling resistance and stability.

Before committing to the rebuild, measure the steepest intended slope and
define travel speed and tool working forces. Measure rolling pull force on
representative ground with the drivetrain genuinely free to roll (a disabled
stepper still has detent/gear resistance), record peak obstacle forces, and
check loaded axle/caster weight distribution. Compare against measured motor
torque at the required RPM on 12 V. For reliable 10 kg operation around 15°,
the present example calls for roughly 1.4 N·m of running torque per motor even
before separately accounting for tool forces and acceleration; this candidate's
1.16 N·m holding rating does not establish that margin. More reduction or a
stronger motor/driver combination may be appropriate if that becomes the target.

## Softer joystick response before hardware changes

**Implemented 2026-09-21:** the native app now uses the proposed `expo=0.6`,
`turnScale=1` response with independent physical knob tracking. See
[app response notes](app/README.md#stick-response). The discussion below records
the original proposal; acceleration, braking, current and robot settings were
not changed with this implementation. Physical driving validation remains.

The owner reports that a recent joystick change allowed a higher top speed
but also made starts quick. This makes input response and acceleration a useful
early experiment, before replacing motors or the battery.

### What “slow yard travel” means relative to today's stick

For this exploration, “slow” means a proposed testing band of roughly
**0.1–0.2 m/s**, not a verified operating envelope for the proposed NEMA 23.
With 215 mm wheels, the last verified `vmax_tps=1.0` means full straight-forward
stick requests **0.675 m/s (2.43 km/h, 1.51 mph)**. The current linear response
therefore gives the following, assuming those saved settings are unchanged:

| Straight-forward stick | Requested ground speed | mph | Motor RPM |
|---|---:|---:|---:|
| 15% | 0.101 m/s | 0.23 | 30 |
| 30% | 0.203 m/s | 0.45 | 60 |
| 50% | 0.338 m/s | 0.76 | 100 |
| 100% | 0.675 m/s | 1.51 | 200 |

Thus the proposed slow band is approximately **15–30% stick**; full stick is
about 3.4–6.8 times faster. Turning changes the individual wheel speeds.
Firmware defaults of 0.3 wheel turns/s and 1.0 wheel turns/s² do not describe
the restored saved settings. The earlier session verified a much brisker
`accel_tps2=8.0`: a nominal commanded ramp from rest to full speed takes only
**0.125 s**, equivalent to 5.4 m/s². This is a command calculation, not measured
physical acceleration, and provides a plausible contributor to abrupt starts.

The steady-load torque estimates above do not depend on travel speed, but
available motor torque does. Before promising the proposed motor can carry
8–10 kg at full stick on 12 V, verify running torque at **200 motor RPM**.
Testing at 30–60 RPM would assess the slower band separately.

### Proposed response curve

The app already implements a linear/cubic blend in
[StickResponse.swift](app/Packages/UBotCore/Sources/UBotCore/StickResponse.swift):

```text
output = (1 - expo) * input + expo * input³
```

`StickResponse.standard` currently uses `expo=0`, `turnScale=1`: fully linear.
An initial trial of `expo=0.6`, retaining `turnScale=1`, would give:

| Stick travel along one axis | Current speed request | Proposed speed request |
|---|---:|---:|
| 25% | 25% | 10.9% |
| 50% | 50% | 27.5% |
| 75% | 75% | 55.3% |
| 100% | 100% | 100% |

Reverse is symmetric. The existing function shapes forward and turn separately,
after clamping the input to the unit disc. Full travel along either axis retains
full authority; mixed forward/turn behavior needs a driving check.

**A response curve is not an acceleration ramp.** It makes low-speed requests
easier to select, but a jump straight to full stick still requests full speed
immediately. The firmware already slew-limits velocity using `accel_tps2`;
compare a gentler setting against the last verified value of 8.0 wheel turns/s²
separately from the curve.
Top speed (`vmax_tps`) and acceleration can be tuned independently. Keep braking
and deadman behavior unchanged during this comparison.

For the next outing, start the acceleration trial at **1 wheel turn/s²** and
consider **2 wheel turns/s²** if it feels sluggish. At the saved maximum of
1 wheel turn/s, these give nominal rest-to-full-speed command ramps of 1.0 s
and 0.5 s respectively, versus 0.125 s at the current value of 8. The owner
agreed that the current acceleration seems high. These are proposed trial
settings, not changes made tonight; gentler acceleration preserves top speed
and the configured current limit while reducing acceleration torque demand.

When implementing the curve, also separate visual stick position from the
shaped drive command: [JoystickPad.swift](app/UBot/Controls/JoystickPad.swift)
currently draws its knob from `model.command`. Changing expo alone would make
the knob lag behind the finger spatially. Preserve the knob's physical tracking
and its centering on release/lock while shaping only the transmitted command.
The app response is shared by BLE and Wi-Fi driving; the firmware web joystick
is a separate implementation.

This section proposes a later trial only; no app code or robot settings were
changed during this discussion.

### Could gentle acceleration prevent a useful burst of torque?

It could limit how quickly we build momentum over a short approach, but it is
not itself a torque ceiling. In the present firmware, `accel_tps2` limits the
change in commanded step rate; it does not lower the configured running current.
A slowly moving stepper can still develop substantial torque as its rotor lags
the commanded magnetic field. Conversely, asking for a sudden speed increase
does not command extra phase current and can provoke loss of synchronism.

Acceleration also requires torque to accelerate the robot and drivetrain, on
top of torque needed to overcome the external load. A gentler ramp can leave
more torque available for the obstacle, within the motor's speed-dependent
limits. [Motor sizing and acceleration torque](https://blog.orientalmotor.com/motor-sizing-basics-part-3-acceleration-torque-and-rms-torque?hs_amp=true).

A short run-up or deliberate rocking maneuver might help a particular stick or
depression through momentum and changing contact geometry. That is a different
experiment from current boost; a very slow acceleration setting could make such
a maneuver less effective. Neither maneuver has been tested on this robot.

**Agreed direction (owner confirmed, 2026-09-20):** use a soft joystick center,
moderate normal acceleration, and an independent, bounded short torque boost
if testing supports it. Preserve full-stick top speed. Exact curve, acceleration
and boost parameters remain to be tested; this records agreement on the approach,
not a decision to deploy untested settings.

Do not equate obstacle recovery with maximum
acceleration. At steady commanded speed the existing acceleration limiter does
not react to an obstacle at all; slowing the step rate when shaft lag grows
would require a separate adaptive recovery policy. Keep curve, acceleration,
current boost and any rocking maneuver as separately evaluated changes.

## Temperature visibility in the app

The owner saw no temperature warning during the yard outing and wondered
whether the drivers were hot. Source review shows that a detected driver
overtemperature prewarning while enabled disables both motors and latches a
generic driver fault. The native app displays **"Fault: Motor driver"** with
the explanation **"A motor driver reported a power, communication, or temperature
fault."** It does not identify heat specifically or show a temperature gauge.

BLE carries the generic fault code. Wi-Fi telemetry includes raw per-driver
status and a snapshot saved when a fault latches, but the native app's Wi-Fi
decoder currently ignores those detailed fields. An earlier latched fault can
also remain the displayed fault even if a later driver problem disables motion.

No observed warning does not establish that the drivers or motors stayed cool.
The chip only exposes high-temperature thresholds, not a continuous temperature
reading, and it does not measure the motors. Without a recorded trace from the
outing, actual temperatures and whether a thermal flag occurred remain unknown.

For a later diagnostics improvement, distinguish thermal warnings from other
driver faults in the app, identify the wheel, and retain a timestamped event
history. Carry equivalent detail over BLE and Wi-Fi, including sample validity
and age. Show "no thermal warning" rather than claiming "cool" when no flag is
set. This is a proposed improvement, not an implemented change.

### External motor temperature sensors — deferred, higher implementation effort

**Owner decision (2026-09-20): defer this to a later phase.** Adding permanent
motor temperature sensors requires mounting and protected wiring, an electrical
interface, and firmware/app integration. It is not a prerequisite for the next
joystick, acceleration or current experiments; those can use external test
measurements. Prioritize the agreed drive-response experiments first.

For external motor-temperature sensing, the proposed starting location is the
middle of a flat side of each motor's central stator body, between the front
and rear end caps. Choose an accessible, sheltered side with clearance from the
printed housing and wires; use the same location on both motors. This is an
engineering recommendation for repeatable case measurements, not a verified
hotspot map of this motor. Mounting-flange measurements can be biased by heat
flow into the mount.

Use a small surface sensor with intimate thermal contact and strain-relieved
leads: a surface thermocouple for the initial measurements, or a suitably
insulated thermistor for later integration. A thin, suitable thermal adhesive
layer or a retained contact probe avoids measuring mainly the surrounding air;
do not bury the sensing element in a thick adhesive blob. See
[Omega surface sensor mounting guidance](https://assets.omega.com/manuals/M5698.pdf).
Case readings lag winding heating and do not establish winding temperature
through a fixed offset. Select limits for the actual motor, printed mount
material and installed conditions; the TMC2209's chip thresholds are unrelated
to an acceptable motor-case temperature. No sensor or mounting change is made
in this discussion.

## Next daylight session

1. **Reproduce the confirmed stall.** Use the same short grass route, modest
   slope and one measured stick. Record which wheel chatters, whether a caster
   or chassis part snags, travel direction, speed and any fault. Note whether
   it happens during acceleration or steady travel. Save the actual current
   and motion settings. Repeat enough to separate improvement from route
   variation.
2. **Capture a baseline.** Log each wheel's commanded and measured velocity,
   slip, faults, current setting, driver status/age, battery voltage and control
   timing. Record motor/driver temperatures before and after comparable runs.
   Use video if the wireless link cannot reliably carry telemetry.
3. **Check the known uncertainties.** Crimp repairs improved the earlier
   unloaded rail minimum from 11.2 V to 13.08 V, but loaded grass voltage still
   needs measuring. Recheck battery scaling on the replacement controller and
   wheel B's magnet. The rack result does not establish loaded thermal margin.
4. **Try motion changes first.** Compare slower travel and gentler acceleration
   at the existing current, changing one variable at a time. Inspect caster
   rolling/swiveling and where sticks contact the chassis.
5. **Test whether current helps.** If these are torque-limited stalls and power
   and temperature observations support it, compare modestly higher static
   current within the existing cap, changing settings while disabled. This
   experiment is already supported and can precede any boost implementation.
6. **Only then build a bounded boost trial.** First verify transitions, failed
   writes, time limits, deadman/fault priority and timing on the bench; then
   repeat the same outdoor obstacles. Add automatic detection after a manual
   trial demonstrates useful recovery.

Success means repeatably clearing an obstacle that defeated the baseline,
without excess tire spin, unexpected steering, unacceptable temperature rise,
power faults or missed control deadlines. If extra current adds heat without
improving clearance, prioritize traction, caster geometry or gearing instead.

## Questions to carry forward

- Did a reported fault accompany the chatter, and did both wheels stall or
  only one? Did stopping and retrying at a lower speed restore motion?
- Which part contacted the sticks first: drive tire, caster or chassis?
- Were the last verified saved settings unchanged during the outing, and what
  stick position/speed preceded each stall?
- What are the pack's chemistry, full-charge voltage and continuous/peak
  discharge ratings? Does its output sag during a loaded stall?
- Is the main goal better obstacle clearance, cooler cruising, or both?
- Is the available reserve within the present motor/driver profile enough to
  matter, or would mechanical changes offer a larger improvement?
