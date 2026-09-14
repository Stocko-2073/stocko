# XYZA stripboard cutter firmware

Commissioning scaffold for a Seeed XIAO ESP32-C6 and four A4988 drivers.
`A` is the stepper-driven drill spindle. Current mapping is X=M0, Y=M1, Z=M3;
A=M2 with its replacement driver installed. Initial directions and ruler
measurements and coordinate conventions are recorded below; precise calibration
and work zero are still pending. No automatic motion happens on boot.

## Wi-Fi provisioning and xyz.local (firmware v0.4)

Build/upload with `make upload`, then open `make monitor` at 115200 baud.
Commands are uppercase. Provision a 2.4 GHz network through the USB console:

```text
OFF
WIFI SET
```

At the `SSID` prompt, type the network name and press Enter. At the password
prompt, type its password and press Enter (empty for an open network). Input
is not echoed by firmware; disable local echo in your terminal if needed.
Spaces and punctuation, including `!`, are literal inside these two prompts.
Backspace edits input; Ctrl-C cancels provisioning. LF, CR, and CRLF line
endings work. SSIDs accept 1–32 bytes; passwords accept 8–63 bytes or a
64-digit hexadecimal key. While either prompt is active, all lines are
credential input, including text that normally names a motion command.
Motors must be disabled to enter provisioning and remain disabled during it.
USB disconnection cancels an unfinished prompt.

`WIFI STATUS` reports whether credentials are configured, connection state,
IP address, and mDNS readiness. `WIFI FORGET` (motors disabled) removes the
saved credentials and disconnects. Credentials are stored in ESP32 NVS across
reboots; they are not printed in status output or compiled into the firmware.
This uses ordinary flash storage, not an encrypted credential vault.

Connection runs in the background and retries every 30 seconds while motors
are disabled. Incorrect credentials can be replaced with `WIFI SET`.
Once connected, mDNS publishes **xyz.local**; try `ping xyz.local` from a
computer on the same LAN with mDNS support. Client isolation or multicast
filtering can prevent name resolution. There is no HTTP server or network
motion interface in this change; motion commands remain on USB serial.
Network management in the main loop is deferred while motors are armed;
Wi-Fi radio activity can still occur, so motion timing with Wi-Fi enabled
has not yet been validated on hardware.

Hardware verification (2026-09-14): user confirmed `xyz.local` responds to
ping after provisioning.

The implementation uses Espressif's [Wi-Fi API](https://docs.espressif.com/projects/arduino-esp32/en/latest/api/wifi.html)
and [Preferences storage API](https://docs.espressif.com/projects/arduino-esp32/en/latest/api/preferences.html).

## Commissioning findings (2026-09-13)

Update 2026-09-14: replacement M2/A driver installed. User tested 200 pulses
at 200 pulses/sec and reported smooth rotation. A now maps to M2 by default;
its initial jog cap and requested cruise cap were 1000 pulses and 1000 pulses/sec.
Acceleration remains 500 pulses/sec². The requested next test is
`python3 tests/commission_jog.py M2 1000 --rate 1000`: a rest-to-rest triangular
move with approximately 707 pulses/sec peak and 2.83 seconds planned duration.
Positive spindle rotation is confirmed as the cutting direction. Replacement
M2 has MS2 high and MS1/MS3 unconnected; the A4988's internal pull-downs select
quarter stepping. User confirmed the drill motor is 1.8 degrees per full step:
200 full steps/revolution, or **800 pulses/revolution** at this setting.
XYZ settings
are unchanged. The September 13 unavailable-driver/pause notes below are history.

M2 1000/1000 test completed in **2.865 s**. Firmware reported all 1000 positive
drill pulses, no XYZ pulses, and drivers disabled. User confirmed smooth motion
and positive rotation in the cutting direction; M2 inversion remains false.
With unchanged 500 pulses/sec²
acceleration, planned peak is ~707 pulses/sec; this is not yet a sustained
1000-pulses/sec test.

Next sustained spindle test: M2's jog cap and profile capacity are increased to
6000 pulses, while rate stays capped at 1000 pulses/sec and acceleration stays
500 pulses/sec². `python3 tests/commission_jog.py A 6000 --rate 1000` plans
2 seconds accelerating, 4 seconds cruising at 1000 pulses/sec, and 2 seconds
decelerating. XYZ limits are unchanged. With the confirmed 1.8-degree motor and
quarter stepping, **1000 pulses/sec corresponds to nominal 75 RPM** and the
6000-pulse test commands 7.5 revolutions. This is calculated from commanded
pulses, not measured by a tachometer. Convert using `RPM = pulses/sec * 60 / 800`.
See the A4988 mode table linked below.

Sustained A test completed in **8.174 s**, all 6000 positive spindle pulses
reported, no XYZ pulses, and drivers disabled. Profile includes approximately
four seconds at the requested 1000 pulses/sec cruise. User confirmed the
steady-speed portion was smooth. This supports nominal **75 RPM unloaded**;
there is no tachometer measurement or cutting-load validation yet. Drivers
remain disabled after the test.

- Original M0 driver failed: enable noise came from the other motors, and X did
  not move. Earlier pulse counts therefore do not describe physical X movement.
- User swapped the M0 and M2 drivers to make X available; M2/drill is now out of
  service. Firmware defaults to X=M0, Y=M1, Z=M3, A unassigned.
- EN pull-up fitted. XYZ use lead screws.
- User confirmed MS2 is tied to 3.3 V on each driver. With MS1/MS3 low or
  unconnected (internal pull-downs), this selects **1/4 stepping**, not 1/8.
  Eighth stepping would require MS1=HIGH, MS2=HIGH, MS3=LOW. Keep the present
  setting during calibration. See the A4988 reference below.
- X, Y, and Z each moved approximately 2 mm for 200 positive pulses at a
  requested 100 pulses/sec, suggesting **100 pulses/mm on each axis**. Distances
  were checked with a ruler, not calipers; timing appeared similar, but was not
  independently measured. These are provisional observations, not active
  firmware calibration or evidence of cutting accuracy.
- Confirmed bedslinger: X/Y move the board; Z moves the drill. Positive X moves
  the board right; positive Y moves it forward, away from the Z tower; positive
  Z moves the drill UP, away from the board. Raw jog inversion remains false.
- Next calibration uses longer X/Y travel, followed by return/repeatability and
  backlash checks. M0 jogs permit 1000 pulses; M1 permits 2000 for the longer
  Y speed test; M2 now permits 6000 pulses, M3 permits 500 for Z up/down tests.
  These are per-command caps, not cumulative travel limits.

Current-position clearance estimates supplied after the initial 2 mm tests:

| Axis | Positive clearance | Negative clearance |
| --- | --- | --- |
| X | about 38 mm right | unknown; mechanism obscures it |
| Y | about 20 mm forward/away from tower | about 55 mm back/toward tower |
| Z | user ceiling: no more than 10 mm farther up | drill tip about 15 mm above board |

These estimates are relative to that physical position, not a homed origin.
Z has about 10 mm of exposed screw above the carriage, which does not by itself
establish usable upward travel. Keep Z tests small. The 15 mm tip clearance is
not a permitted downward cutting move. None of these estimates are enforced as
  software travel limits; pulse counts do not track trustworthy absolute position.

Longer X check completed: 1000 positive pulses at requested 100 pulses/sec
produced **10 mm right** by ruler, with command-to-DONE time **11.006 s**.
The later X return of **-1000 pulses** at requested 100 pulses/sec completed in
**11.003 s** and measured **10 mm left**. The ruler had been repositioned for Y,
so this confirms reverse travel at ruler precision, not an exact return to the
original mark. Both directions support **100 pulses/mm for X**. Return-to-mark
repeatability and sub-ruler backlash remain unverified. Net commanded X travel
over this pair is zero; estimated rightward clearance is again about 38 mm,
assuming no intervening physical movement. This is bookkeeping, not an enforced
limit or proof of absolute position.

Longer Y check completed: 1000 positive pulses at requested 100 pulses/sec
produced **10 mm away from the tower** by ruler, with command-to-DONE time
**11.005 s**. This supports retaining **100 pulses/mm for Y** at ruler precision.
The subsequent Y return of **-1000 pulses** at requested 100 pulses/sec completed
in **11.007 s**. User confirmed the board returned to its original ruler mark:
no visible return error at ruler resolution in this single out-and-back check.
This does not quantify sub-ruler backlash or establish repeatability over many
cycles. Y clearance estimates are again approximately 20 mm forward and 55 mm
back, assuming no intervening physical movement. Net commanded travel for both
X and Y is now zero over their respective out-and-back pairs. Z has not moved
during these longer checks.

Command used for that X measurement (do not repeat without checking clearance):

```sh
python3 tests/commission_jog.py X 1000 --rate 100
```

Expected travel is approximately 10 mm right. Measure actual travel before
commanding another move. A longer distance reduces the relative ruler error.

## Table motion and board coordinates

The design is in [xyz.scad](../xyz.scad), with assembly notes in
[MECHANISM.md](../MECHANISM.md). Current `JOG` commands describe the observed
physical carriage directions, not tool-relative work coordinates.

For a board work frame with +X right, +Y toward the tower, and +Z up:

| Positive raw jog | Physical movement | Drill relative to the board |
| --- | --- | --- |
| X / M0 | board right | left: negative work X |
| Y / M1 | board away from tower | toward tower: positive work Y |
| Z / M3 | drill up | up: positive work Z |

Thus a future tool-relative planner should apply displacement signs
`[-1, +1, +1]` to convert these work-axis moves to the present raw jog axes.
Do not invert both X/Y just because both move the bed: the chosen work +Y is
opposite the raw table +Y. Existing jog behavior is preserved.

The model agrees: `bit_on_board(xy) = [42-xy.x, xy.y-35]`, where `xy` is table
travel. Its 42/35 offsets describe the CAD placement, not an established physical
work zero. Likewise, the demo's through-board depth and rapid speeds are animation
settings, not calibrated settings for shallow strip cutting.

`nema17_tr8.scad` specifies 2 mm pitch with four starts: 8 mm lead per revolution.
If the installed motors are 1.8 degrees (200 full steps/revolution), quarter-step
drive predicts `200 * 4 / 8 = 100 pulses/mm`, consistent with all three ruler
measurements. The motor step angle and physical screw lead still need confirmation;
the model alone does not establish accuracy, backlash, or safe travel.

## Accelerated motion (firmware v0.2)

The original cooperative step loop produced about 11 seconds for the measured
1000-pulse moves at 100 pulses/sec. Pulse generation now uses a 1 MHz hardware
timer with one-shot interrupts and precomputed rest-to-rest acceleration profiles.
USB processing and the main loop's 1 ms yield no longer set the pulse cadence.
Each move accelerates, cruises if distance permits, and decelerates to rest.
Short moves use a triangular profile and may never reach the requested rate.

| Motor | Maximum requested rate (pulses/sec) | Acceleration (pulses/sec²) | Jog cap (pulses) |
| --- | --- | --- | --- |
| M0 / X | 3000 | 10000 | 1000 |
| M1 / Y | 3000 | 10000 | 2000 |
| M2 / A drill | 1000 | 500 | 6000 |
| M3 / Z | 2000 | 10000 | 500 |

Firmware and Python default to 500 pulses/sec (clamped to the motor cap).
At the provisional 100 pulses/mm, that is 5 mm/sec cruise for XYZ; X/Y
acceleration is now 100 mm/sec². These are commissioning settings, not validated
maximum motor speeds. First test X at 500 pulses/sec, confirm the full 10 mm
travel, then test its return and Y before increasing to 1000 and beyond.
Keep checking physical distance; DONE confirms emitted pulses, not that the
motor followed them. Do not change the microstep jumpers during these checks.

With the updated acceleration, planned X/Y duration for 1000 pulses is about
2.05 seconds at 500 pulses/sec, 1.1 seconds at 1000, and 0.7 seconds at 2000,
plus small interrupt/USB overhead. At 3000 pulses/sec, this distance now briefly
reaches the requested rate (planned total about 0.633 seconds).

First hardware check after v0.2 upload: X +1000 pulses at 500 pulses/sec
completed in **2.129 s**, versus about 11 seconds for the earlier slow test.
Firmware reported all 1000 pulses and drivers were disabled afterward. User
confirmed smooth motion and the full 10 mm travel at ruler precision. This
supports 500 pulses/sec for this X move; higher speeds and Y remain untested.
X is now nominally 10 mm right of the earlier reference
(about 28 mm right clearance remains if no other movement occurred). Y and Z
were not moved for this test.

Next X test: -1000 pulses at 1000 pulses/sec completed in **1.229 s**;
drivers disabled afterward. User answered yes to the return-move check and
explicitly confirmed motion was still smooth.
Net commanded X travel over these two speed tests is zero (nominal right
clearance back to about 38 mm, subject to actual motion). Y/Z remain unchanged.

First faster Y test: +1000 pulses at 500 pulses/sec completed in **2.129 s**;
drivers disabled afterward. User confirmed smooth motion and the full 10 mm
travel away from the tower.
Y is nominally 10 mm forward of its reference, leaving approximately 10 mm
forward and 65 mm back clearance if actual motion followed the pulses. X is
at its nominal reference and Z has not moved during speed testing.

Next Y test: -1000 pulses at 1000 pulses/sec completed in **1.229 s**;
drivers disabled afterward. User confirmed smooth motion and return to the
starting mark within ruler resolution.
Net commanded X/Y travel across the speed tests is now zero; nominal clearances
return to X right 38 mm, Y forward 20 mm/back 55 mm, subject to actual motion.
Z remains unchanged.

Current tested X/Y cruise rate: **1000 pulses/sec**, approximately **10 mm/sec**
at the ruler-supported scale, with 5000 pulses/sec² acceleration. Both axes
completed the 1000-pulse return test in 1.229 s (about nine times faster than the
original 11-second moves). This is initial commissioning evidence over short
moves, not a maximum-speed or endurance qualification. Use `--rate 1000` in the
jog tool; the conservative default remains 500. Z has not been speed-tested,
and M2/drill remains unavailable. Higher configured caps are not yet tested.

For example, after verifying clearance and direction:

```sh
python3 tests/commission_jog.py Z 200 --rate 100
python3 tests/commission_jog.py Z -200 --rate 100
```

Run and measure each separately; the tool disables all drivers after each jog.
At 100 pulses/mm, requested rates of 50, 100, and 200 pulses/sec correspond to
0.5, 1, and 2 mm/sec cruise. Acceleration adds time to each move. The tool
prints command-to-DONE elapsed time, excluding connection setup. Distance is
capped at 1000 pulses for M0, 2000 for M1, 6000 for M2, and 500 for M3; increasing rate does not
increase commanded travel. Firmware applies these caps to the mapped physical
motor, including when using named axes.
Measure XYZ independently, taking up backlash in the measuring direction first:
`pulses/mm = commanded pulses / measured travel in mm`. Do not reuse this scale
after changing microstep settings. The timer ISR performs no floating-point
calculations, allocation, or serial output. It emits a 3 µs high pulse and schedules
the next interval from the actual interrupt time, preventing catch-up bursts if
an interrupt is delayed. Profiles are computed before motion. See Espressif's
[timer API](https://docs.espressif.com/projects/arduino-esp32/en/latest/api/timer.html).

## Video demo (firmware v0.3)

Longer speed test: user requested 20 mm back, interpreted as Y toward the tower.
M1's jog cap/profile capacity were increased to 2000 pulses, tested and uploaded;
other motor caps, rates, and acceleration stayed unchanged. Upload reset pulse
counters but did not establish a physical zero. Y -2000 pulses at 2000 pulses/sec
completed in **1.461 s**, drivers disabled afterward. User confirmed smooth
motion and the full 20 mm travel. Planned profile: 4 mm accelerating,
12 mm cruise, 4 mm decelerating
(0.4 + 0.6 + 0.4 seconds). Relative to the original clearance reference, X remains
nominally +10 mm and Y is now -10 mm; estimated clearance X right 28 mm,
Y forward 30 mm/back 45 mm. Z has not moved.

Subsequent speed exploration (after the first video run): X +1000 pulses at
**2000 pulses/sec** cruise and unchanged 5000 pulses/sec² acceleration completed
in **0.936 s**. Drivers disabled; user answered yes to the move check and
explicitly reported it was still very smooth. X is nominally 10 mm right of the reference (about 28 mm right
clearance remaining); Y/Z unchanged. The demo itself still uses 1000 pulses/sec.
Doubling cruise rate does not halve these short moves: planned time changes
from 1.2 to 0.9 seconds because acceleration/deceleration consume most of the
distance at the higher rate. Higher acceleration requires separate testing.

Next Y test: +1000 pulses at 2000 pulses/sec with unchanged acceleration
completed in **0.935 s**; drivers disabled. User answered yes to the smoothness
and full-travel check, reporting everything seemed normal. Both X and Y have
now passed one positive 10 mm test at **2000 pulses/sec (~20 mm/sec)** with
unchanged 5000 pulses/sec² acceleration. Return accuracy at this speed and
faster circles remain untested. Use `--rate 2000` to request this cruise rate;
the default and video-demo rate have not been changed.
X and Y are now each nominally 10 mm positive from their reference;
estimated remaining clearances are X right 28 mm, Y forward 10 mm/back 65 mm.
Z has not moved. Return X/Y before repeating the positive-envelope video demo.

`python3 tests/video_demo.py` gives a five-second camera countdown, enables
drivers, runs a square then circle **three times**, and disables drivers at the
end. With the latest 20 mm/sec cruise and 100 mm/sec² X/Y acceleration,
the enlarged 20 mm pattern takes approximately 30 seconds, plus countdown and USB setup.
From an existing serial console, use `ARM` then `DEMO` (no countdown).

The square is 20 mm per side and the circle is 20 mm diameter, at the current
100 pulses/mm scale. The entire pattern lies within +0..20 mm raw X (board
right) and +0..20 mm raw Y (board away from tower) relative to its starting
position. Each repetition returns to its start, with a short straight transfer
to/from the circle's bottom point. It now uses 2000 pulses/sec path speed
and 10000 pulses/sec² acceleration on straight sections; square corners stop,
while the circle is a continuous
360-segment approximation with coordinated X/Y pulses.

For the circle, tangential acceleration is 6000 pulses/sec² (60 mm/sec²).
At 20 mm/sec around the enlarged 10 mm radius, radial acceleration is 40 mm/sec²;
reserving that component keeps the ideal smooth-curve vector acceleration
within 100 mm/sec². The actual path is quantized to pulses and polygon segments.
The updated parameters pass the geometry, timing, no-Z/A-pulses, and stop tests;
physical assessment of the faster demo is recorded below when run.

Faster demo hardware run completed in **17.214 s** (three square/circle cycles,
excluding countdown), versus 29.021 s originally. Firmware reported zero net
X/Y pulse displacement, no Z/A pulses, and drivers disabled. Physical smoothness
and return accuracy were confirmed by the user, who accepted this speed and
acceleration. X/Y remain nominally +10/-10 mm
relative to the earlier clearance reference, since this routine returns to its
own start. No extra positioning was performed. The new X/Y acceleration settings
remain installed; Z and drill settings were unchanged.

At the user's request, the subsequent demo is enlarged to 20 mm square sides
and 20 mm circle diameter. Cruise, acceleration, and three repeats are unchanged.
The event buffer was enlarged and tests cover the complete 20 mm envelope,
circle, three closed cycles, cancellation, and no Z/A pulses. One cycle plans
to take 9.685 s. From the recorded current position, farthest excursion leaves
approximately 8 mm X right clearance and 10 mm Y forward clearance. The jog
command limits are unchanged; DEMO uses its separately tested trajectory buffer.

The 20 mm demo completed all three cycles in **29.762 s**. Firmware reported
DONE, zero net X/Y pulse displacement, no Z/A pulses, and drivers disabled.
User confirmed the 20 mm demo was smooth. No extra positioning was
performed; the nominal X/Y starting offset remains +10/-10 mm relative to the
earlier clearance reference.

Z speed commissioning begins with +200 pulses (approximately 2 mm UP), at
500 pulses/sec cruise and the existing 2000 pulses/sec² acceleration. Z had
not moved during the X/Y speed and demo tests. User's earlier upward allowance
was at most 10 mm from that position; paired small up/down tests will avoid
accumulating travel. Z scale remains provisional at 100 pulses/mm.
First +200-pulse Z move completed in **0.658 s**; drivers disabled. User
confirmed smooth upward motion and that the drill stayed in place after disable.
Z is nominally 2 mm above its earlier position, leaving
at most 8 mm of the stated upward allowance. X/Y were not stepped.

Next Z test settings: max cruise 1000 pulses/sec (~10 mm/sec), acceleration
5000 pulses/sec² (~50 mm/sec²), with the 200-pulse distance cap unchanged.
A 200-pulse move uses a triangular profile, just reaching the requested speed
at its midpoint; planned duration is 0.4 seconds. The next commanded direction
is down over the same 2 mm previously ascended, not below the prior reference.

Z return -200 pulses at 1000 pulses/sec completed in **0.408 s**; drivers
disabled, X/Y/A not stepped. User confirmed smooth motion and return to the
previous height.
The upload reset counters, so the reported -200 does not mean 2 mm below the
original height: this move cancels the prior +200, nominally restoring the
original Z reference and its stated 10 mm upward allowance.

Z upward check +200 pulses at 1000 pulses/sec and 5000 pulses/sec² completed
in **0.411 s**; drivers disabled. User confirmed the lift and subsequent hold
were good, with no reported slipping or settling.
Z is again nominally 2 mm above its original reference (8 mm of the stated
upward allowance remaining). X/Y/A were not stepped.

Next Z acceleration test: 10000 pulses/sec² (~100 mm/sec²), requested cruise
2000 pulses/sec (~20 mm/sec), same 200-pulse distance cap. Over only 2 mm,
the triangular profile peaks at ~14.14 mm/sec, with planned duration 0.283 s;
this cannot validate sustained 20 mm/sec motion. The next direction is down
over the previously ascended 2 mm, to restore the original Z reference.

That Z -200-pulse return completed in **0.292 s** after upload; drivers disabled,
X/Y/A not stepped. User confirmed the return was still smooth. Z is
nominally back at its original reference; the upload reset the diagnostic counts,
so -200 in STATUS describes only the post-upload return, not an absolute height.

Requested 5 mm Z up/down test: M3 jog cap increased to 500 pulses, retaining
2000 pulses/sec cruise and 10000 pulses/sec² acceleration. Command:
`python3 tests/commission_jog.py Z 500 --rate 2000 --return-to-start`.
This runs +500 pulses UP, waits 0.5 seconds enabled, then -500 pulses DOWN
and disables the drivers. It returns only after a successful first DONE;
interruptions/errors stop and disable instead of attempting recovery motion.
Each leg plans 0.45 seconds (2 mm accelerate, 1 mm cruise, 2 mm decelerate).
From the nominal original Z height, its top is 5 mm up, halfway through the
user's stated 10 mm upward allowance. It never intentionally goes below the
starting height. This is a relative pattern, not an absolute position limit.

The 5 mm up/down pattern completed: **0.468 s up**, 0.5 s pause, **0.468 s
down**. Firmware reported net zero Z pulse displacement and no X/Y/A pulses;
drivers disabled afterward. User confirmed the pattern looked great and accepted
the result. Z nominally returned to its original reference.

Commissioning is paused pending a replacement M2/drill driver. Accepted motion
settings are 20 mm/sec requested cruise and 100 mm/sec² acceleration for XYZ,
using the provisional 100 pulses/mm scale. The CLI/firmware default cruise remains
500 pulses/sec; pass `--rate 2000` for the tested rate. X/Y passed the 20 mm
square/circle demo, and Z passed the 5 mm up/down test. Drivers were disabled at
pause. No homing, work zero, drilling depth, or spindle operation is established.

No Z or drill STEP pulses are generated. Common EN still energizes all drivers.
The demo requires X=M0, Y=M1, and no inversion, preserving this known envelope;
it refuses other mappings. STOP, `!`, OFF, and USB disconnect cancel the demo.
There is no resume after cancellation. The path is relative to wherever the
board starts and does not establish work zero or override the need for clearance.
Host tests check the envelope, circle radius, closure, all three repeats,
absence of Z/A pulses, and cancellation. This is a motion demonstration with
the tool raised, not a cutting cycle.

First video run completed in **29.021 s** after the five-second countdown.
Firmware reported DONE, drivers disabled, and zero net X/Y pulse displacement;
Z/A pulse counters remained zero. Physical pattern quality awaits the user's
observation. No additional positioning was commanded after the routine.

## Wiring

| Motor | DIR | STEP | ESP32 GPIOs (DIR / STEP) |
| --- | --- | --- | --- |
| M0 | D0 | D1 | 0 / 1 |
| M1 | D2 | D3 | 2 / 21 |
| M2 | D4 | D5 | 22 / 23 |
| M3 | D8 | D9 | 19 / 20 |

Common active-low EN: **D10 / GPIO18**. These are Arduino board pin names,
not sequential ESP32 GPIO numbers. Native USB leaves D6/D7 unused.

Use 3.3 V driver logic VDD and a common ground with the controller and motor
supply. Set each driver's current limit for its motor and actual carrier sense
resistors. RESET and SLEEP must be held high for operation; configure MS1–MS3
deliberately and record their settings. Keep suitable bulk decoupling near VMOT
(Pololu recommends at least 47 µF on its carrier). Never plug/unplug motor leads
with the driver powered.

Add an external pull-up (for example 10 kΩ to logic 3.3 V) on common EN to keep
drivers disabled during reset, bootloader, and upload. Firmware can only drive EN
after startup. STEP/DIR inputs should not float during reset; external pull-downs
can establish their idle states. See the [A4988 carrier documentation](https://www.pololu.com/product/1182),
[A4988 datasheet](https://www.pololu.com/file/0J450/A4988.pdf), and
[XIAO pin reference](https://wiki.seeedstudio.com/xiao_esp32c6_getting_started/).

## Build and USB console

Requires `arduino-cli` and `esp32:esp32` (built with installed core 3.3.10).
No additional Arduino libraries are needed.

```sh
make compile
make test                           # host tests: parser, pulse counts, stop paths
make upload                         # default /dev/cu.usbmodem2101
make upload PORT=/dev/cu.usbmodemXXXX
make monitor                        # 115200, uppercase commands + newline
python3 tests/usb_smoke.py            # USB protocol test; keeps drivers disabled
```

Close other serial consoles before upload or tests. `make boards` finds the port.
The board target explicitly enables USB CDC on boot. There is no startup wait for
a serial connection. `HELP` and `STATUS` work even if the startup banner was missed.

## Identify the motors

Start with motor power disconnected. `STATUS` should report `armed=0`, `busy=0`,
and X=0, Y=1, Z=3, A=2. Keep the tool clear of the workpiece. With
motor power off, arrange the mechanism so a small move in either direction is
possible, and support any axis that can fall when torque is removed.

When ready, connect motor power with the drivers disabled and try one small jog:

```text
ARM
JOG M0 10 20
STATUS
JOG M0 -10 20
OFF
```

Wait for `DONE` after each jog. Identify which mechanism moved and what positive
motion means. Repeat as needed for M1 and M3; M2 rotates the drill. A step count means STEP pulses, so physical travel
depends on microstepping, gearing, and mechanics. Even ten pulses are not a
guaranteed safe distance. ARM enables **all four drivers**, including the drill,
but does not generate pulses. Drivers hold after a jog until OFF, disconnect, or
30 seconds idle; removing torque can let an unsupported Z axis drop.

Record observations before assigning axes:

| Motor | Mechanism moved | Positive pulse direction | Microstep setting |
| --- | --- | --- | --- |
| M0 | X (after driver swap) | board right | MS2 high; 1/4 if MS1/MS3 low |
| M1 | Y | board forward, away from tower | MS2 high; 1/4 if MS1/MS3 low |
| M2 | drill; replacement driver installed | cutting direction | 1/4: MS2 high, MS1/MS3 unconnected |
| M3 | Z | UP, away from board | MS2 high; 1/4 if MS1/MS3 low |

With drivers disabled, use `MAP X M0` and `INVERT M0 1` if positive
motion should be reversed. `JOG X 10` then addresses that mapped motor. Mapping a
motor to another axis removes its previous assignment. Inversion affects both
raw motor and named-axis jogs. Runtime settings are RAM-only; once established,
copy them to `xyza/config.h` and rebuild.

If one motor moves multiple axes (e.g. coupled belt kinematics), stop at raw motor
identification: named-axis mapping currently assumes independent axes.

## Command reference

| Command | Behavior |
| --- | --- |
| `HELP`, `STATUS` | Commands, enable/busy state, mapping, inversion, pulse counters |
| `ARM` | Enable all drivers; required before each session |
| `OFF`, `STOP` | Abort motion and disable all drivers |
| `!` | Same stop without waiting for newline; discard input through next newline |
| `JOG M0 10 [rate]` | Relative motor jog; M0–M3 or a mapped X/Y/Z/A |
| `MAP X M0` | Assign axis to motor while disabled |
| `INVERT M0 1` | Reverse direction while disabled; 0 restores default |

Jog bounds: nonzero ±1000 pulses for M0, ±2000 for M1, ±6000 for M2, ±500 for M3; rates start at 1
pulse/sec and are capped per motor as listed above. Motion uses the hardware
timer, one motor at a time, with acceleration and no queue. Send one command
at a time and wait for its reply; wait for `DONE` before the next motion.
Busy motion rejects mapping, arming, and more jogs. STOP/OFF/disconnect cancel
immediately when serviced, without a deceleration ramp; position is then unknown.
Invalid jogs do not start motion; overlong or NUL-containing lines abort and disable.

`!` is a software stop serviced by the loop, **not a hardware emergency stop**.
USB CDC disconnect disarms when detected; USB state is not a guaranteed host
heartbeat. The idle timer starts at ARM or motion completion, and does not
interrupt a valid slow jog. Pulse counters describe commands emitted since reset,
not actual position; there is no motor-power sensing or missed-step detection.

## Next stage: calibrated cutting

There is no homing command and no assumed zero. This scaffold deliberately has
no G-code, millimetre moves, continuous spindle mode, or automatic cutting cycle.
Before implementing those, establish independent/coupled kinematics, positive
directions, pulses/mm for XYZ, pulses/revolution for A, usable travel, manual
work-zero procedure, board hole pitch, safe Z clearance, cut depth, and feed/RPM.
With no switches, work position must be manually established each session and
invalidated after disable, reset, or any suspected lost motion. A later cutting
cycle should retract, travel to a selected hole, run A while feeding Z through
the strip, and retract before the next travel move.
