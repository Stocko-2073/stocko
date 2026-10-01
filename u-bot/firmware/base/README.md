# U-BOT base firmware

Firmware for the base of the U-BOT outdoor utility robot: a XIAO ESP32-S3
driving two NEMA 17 wheels through TMC2209s in UART velocity mode, with an
AS5600 encoder on each output shaft. Built on ESP-IDF v6.1, not Arduino.

The mechanism, bench measurements and design rationale are in
[`../DRIVE_MECHANISM.md`](../DRIVE_MECHANISM.md).

See [serial-free maintenance](MAINTENANCE.md) for the native Mac CLI, management
protocol, Wi-Fi recovery, OTA confirmation, and acceptance results.

## What it does

- **Drive.** Robot-frame velocity (m/s, rad/s) mapped onto two wheels, each a
  closed-loop stepper servo at 200 Hz with slip detection. Every motion
  command carries a hold time; when it lapses the wheels ramp to a stop. A
  fault on one wheel stops both. EN is one shared, fail-safe pin.
- **Stall recovery.** A stall caught at any speed, crawl included, and retried
  -- freeze both wheels, boost, re-lock, re-ramp -- up to three times before it
  latches the slip fault (below).
- **Torque.** The motor current changes while driving: a boost to IRUN 31
  (1768 mA) on the operator's request and for 1.5 s after each standstill,
  paced by a per-motor thermal model, and a derate instead of a shutdown when
  a driver warns it is hot (below).
- **Console** over the USB port: linenoise line editing, history, tab
  completion. Calibration, tuning, WiFi provisioning, settings, OTA, logging
  levels, CSV telemetry. `help` lists everything.
- **Unified logging.** Every module logs through `ESP_LOG` with its own tag;
  levels are set live with `log <tag> <level>`. Output is asynchronous (a
  printer task, never the caller) so a slow USB host cannot stall the control
  loop, and the stream can be mirrored to WebSocket clients.
- **WiFi** station with credentials in NVS, automatic reconnect with backoff,
  **mDNS** as `ubot.local`, a **WebSocket** drive server at `ws://ubot.local/ws`
  with JSON both ways, a minimal joystick page at `http://ubot.local/`, and
  **HTTPS OTA** with the built-in certificate bundle (an S3 URL works as-is)
  and bootloader rollback.
- **BLE** peripheral (NimBLE): Device Information (firmware and hardware
  revision, serial), Battery Service, and a custom drive service for the phone
  app.
- **Battery** voltage through a divider into ADC1, judged against the
  configured pack: a percentage from its resting-voltage table and a state
  (ok, low, cutoff) that the drive acts on. The default pack is `li5s`, the
  5S Li-ion power-tool pack (Skil PWR CORE 20, 15.0 V empty to 21.0 V full)
  the robot has run on since 2026-09-30; `lfp4s` keeps the original 12 V 8 Ah
  LiFePO4 table.
- **Firmware and hardware revision** from `version.txt` and NVS, reported the
  same way on console, WebSocket and BLE.

## Building and flashing

ESP-IDF v6.1 is installed at `~/esp/esp-idf`. mDNS and cJSON come from the
component registry on the first build (needs network once).

```sh
. ~/esp/esp-idf/export.sh
cd u-bot/firmware/base
idf.py set-target esp32s3        # first time only
idf.py build
idf.py -p /dev/cu.usbmodem2101 flash monitor
```

`idf.py monitor` is a full terminal, so the console's line editing works in it.
Ctrl-] leaves it. The board resets on flash and comes up with both drivers
disabled.

Version: edit `version.txt`. Pins, baud, control rate and defaults:
`idf.py menuconfig` under "U-BOT base" (or `main/Kconfig.projbuild`).

## Layout

```
base/
  main/main.c              boot order -- EN parked high first, then everything else
  components/
    drive/                 C++: Tmc2209Uart, I2cBus (hardware + bit-banged), AS5600,
                           VelGen, StepperServo, Demo, and drive.cpp (control task,
                           robot frame, deadman, faults, calibration). C API in
                           include/drive.h; everything else talks to that.
    settings/              NVS-backed typed settings, one namespace
    console_cmds/          the console commands
    net/                   wifi.c (STA + mDNS), ws.c (HTTP + WebSocket + joystick
                           page), ota.c (HTTPS OTA)
    ble/                   NimBLE peripheral: DIS, BAS, U-BOT drive service
    battery/               ADC sense; pack tables and the low/cutoff rules in
                           battery_model.c, free of IDF so the host tests run it
    sysinfo/               versions, serial, reset reason, partition state
    ulog/                  async log printer, per-tag levels, WebSocket mirror
  monitor.sh               open the console (idf.py monitor)
  ota_provisioning.sh      create the S3 bucket, once
  push_firmware.sh         bump version, build, upload to the bucket
  partitions.csv           nvs + otadata + two 1.9 MB OTA slots, 4 MB flash
  sdkconfig.defaults       everything that differs from the IDF defaults, commented
```

## Safety model

- **EN is the killswitch** (GPIO8 / D9, active low, shared by both drivers, 4.7k
  pull-up). It is driven high before any other line of `app_main` runs, and it
  floats high through an MCU reset, a watchdog reset or a broken wire. `estop`
  writes it directly from any task without taking a lock.
- **VACTUAL is zeroed before EN drops**, on every driver, every time. The
  register survives an MCU reset with the power stage off.
- **The control task is on the task watchdog** (3 s), with panic on
  (`CONFIG_ESP_TASK_WDT_PANIC`, since 0.2.9; before that it only logged). A
  wedged loop resets the chip, and the reset is what lets EN float high: until
  then a driver keeps stepping at its last VACTUAL. A bench build
  (`CONFIG_UBOT_BENCH_FAULTS`, never for outdoors) adds `debug wedge <ms>` to
  prove it on the stand.
- **Battery cutoff.** A pack below its cutoff (`batt_cut_v`: 20 s under it, or
  5 s of readings more than 1 V under it) latches a robot-level fault. Both
  wheels ramp to a stop at `decel_tps2` and **hold with the drivers on** --
  cutting EN would let the robot freewheel down the slope that drained the pack.
  The hold is the one a released stick gets, so it is only as strong as
  `hold_ma`: in the host plant, 552 mA holds 8 degrees but can slip at 10 and
  more once the current has settled to it. `enable` and `faults clear` are
  refused until the battery leaves cutoff (10 s at cut + hysteresis); then
  clear it. A low pack (10 s under `batt_warn_v`) only warns, and a robot with
  no battery sense is never stopped by it.
- **Deadman.** `drive` commands hold for a given time (console default 2 s,
  WebSocket and BLE 500 ms). Keep sending or the robot stops.
- **Fault propagation.** Slip on one wheel, an encoder that stops answering, or
  a magnet that disappears faults that wheel; the other wheel is stopped too,
  because on a differential drive a wheel holding while its partner drives
  pivots the robot. Motion is refused until `faults clear` (or the WebSocket /
  BLE clear op) -- never cleared by a joystick. The battery fault above is the
  one robot-level fault: it names no wheel. Slip is found two ways since
  0.3.1. In velocity mode each wheel's **stall detector** measures lag against
  a reference that leaks by distance, so a full stall trips ~42 microsteps
  into it at any speed: 0.4 s at a 0.02 turns/s crawl, which the old check
  never caught. Behind it, and alone in position mode and the demo, the
  servo's own **1 s slip check** (200 steps against a reference that leaks
  over a second) stays as the backstop. Both wait out an encoder gap (a
  failed read backs the encoder off for 100 ms) and judge it on the next good
  read, so a stall inside the gap still faults. Before 0.3.1 the 1 s check
  counted the command against the frozen read, and a single failed read
  above ~0.4 turns/s faulted as slip.
- **Stall recovery** (0.3.1, `recover 1`). A stall-detector trip during a live,
  deadman-refreshed stick command, with both wheels driving, is retried before
  it is a fault: both wheels freeze (the tripped one's field snaps to the speed
  its rotor is actually doing, the partner slews to the same fraction of its
  own command at `decel_tps2`), both get the recovery boost, the field follows
  the rotor until it is locked again (`rec_lock_ms`), and then the normal ramp
  takes both back to whatever the stick says. `rec_tries` attempts without
  `rec_prog` of progress, or 10 inside a minute, latch FAULT_SLIP exactly as
  before, the peer stopped in the same tick. It never goes faster than the
  command (backwards included), never clears a fault, and is cancelled -- no
  fault -- by releasing the stick, `stop`, the deadman, a stick reversal on
  either wheel, or a setting change. With `recover 0`, with no live stick (the
  bench's `wheel X vel`), in a demo or for a lead (the wheel pushed ahead of its
  field), a trip latches FAULT_SLIP at once. Recovery is never shown as
  calibrating, a demo or an update, so the app's stick stays live through it.
- **Driver faults.** A driver that stops answering on the UART, resets, reports
  a short, undervoltage (GSTAT), an overtemperature shutdown (OT) or 143 C and
  up cuts EN for both wheels and latches FAULT_DRIVER, as always. The ~120 C
  pre-warning (OTPW, or t120) no longer does, since 0.3.0: cutting EN at the
  warning let the wheels freewheel down whatever hill heated the driver, and
  the datasheet names OTPW as the cue to reduce current. That driver's wheel
  derates instead: no boost at once, base current to 75% after 10 s and 50%
  after 20 s while OTPW persists, one level back per 30 s clear. There are at
  least 23 C between OTPW and OT, and OT is still fatal.
- **Boost limits.** Boost (IRUN 31, 1768 mA, above the motor's 1.5 A rating) is
  only ever granted with the drivers on, while the thermal model has headroom,
  the driver is not derating and the battery is not low. A manual boost lasts
  as long as the drive command carrying it (at most 60 s per request) and ends
  with the first command without the flag, with `stop`, a fault or a cutoff.
  The current comes back down one step per 100 ms.
- **Drivers start disabled** and will not energise while either TMC2209 is not
  answering on the bus, or reports a hard fault. A hot one (OTPW) is
  energised, derated from level 2.

## Console

Connect with `idf.py monitor` (or any terminal at any baud; the port is USB).
The prompt is `ubot> `. A few worth knowing:

```
status                        everything on one screen
enable / disable              power stage on / off (both drivers, shared EN)
stop / estop                  ramp to zero / EN high right now
drive <v m/s> <w rad/s> [s] [boost]
                              robot frame; positive w is anticlockwise from above;
                              'boost' asks for boost current while it holds
boost on [ms] / boost off     manual boost on both wheels (default 2000 ms, at most
                              60000); 'boost' alone: reasons, live and base mA, heat,
                              limit and resume point, derate, OTPW, CS_ACTUAL, settings
wheel A goto 0.5              bench: position move on one wheel (also move, vel,
                              spin, zero, loop on|off, invert, reg, kp vmax ...)
cal A / cal B                 measure shaft polarity and clock gain, ~23 s each;
                              stored in NVS, results in the log
demo short                    both wheels, ~9 s, round-trip check as the outro
faults / faults clear
stream on [hz] / stream off   CSV telemetry, test_servo's columns with more appended
                              (batt_v, batt_st; then per wheel run, hold, boost, heat,
                              derate, otpw as arun..aotpw, brun..botpw; then alag, blag,
                              rec, rtry: each wheel's stall lag in steps, the recovery
                              state 0 idle 1 lock 2 ramp and its attempt); 'on' first
                              prints '# ' and the header
stream header                 just the '# ' header line, so a capture names its columns
                              (ubotctl stream sends it first, then subscribes)
batt                          voltage, percentage, state, pack and thresholds
set / set <key> <value>       settings (below)
wifi set <ssid> <password>    provisioning; wifi scan / wifi / wifi clear
wifi ps on|off               runtime modem-sleep diagnostic; boot defaults off
ota <https://...>/firmware.bin   or: ota url <...> once, then ota start
log drive debug               per-tag level: none error warn info debug verbose; 'rec'
                              is stall recovery, one line per event
hw set B                      hardware revision
stats / stats reset           control tick and encoder read p50/p99/max, the tick's
                              extra bus group, live current writes, UART timing,
                              bus health, dropped log lines
debug wedge <ms>              bench builds only (CONFIG_UBOT_BENCH_FAULTS): stall the
                              control loop to prove the watchdog reset, wheels clear
debug otpw <A|B> [s]          bench builds only: that wheel's DRV_STATUS samples read
                              OTPW for s seconds (default 40, at most 120, 0 ends it),
                              so the derate runs as for a hot driver
```

`status` has a `torque:` line per wheel: the live run/hold pair, whether boost
is on and why (or what refused it), the heat, the derate level, OTPW, the last
CS_ACTUAL and how many CS_ACTUAL samples disagreed with the written IRUN.
Since 0.3.1 each wheel also has a `stall:` line -- the detector's lag now
(steps, + behind; "not armed" while stopped, in position mode or crossing the
gear play after a start or reversal), the worst since `stats reset`, its trips
since boot, and HELD while a recovery holds it -- and the drive a `recovery:`
line: on or off, idle or LOCK/RAMP with the wheels and the attempt, the
attempts, recoveries and give-ups since boot, and the last event and how long
ago. Each event is logged on the `rec` tag as it happens, e.g.

```
W (61234) rec: attempt: wheel A cmd +0.300 rotor +0.036 turns/s, lag +43 steps, attempt 1/3 -- froze at k +0.12: field snapped to the rotor, partner slewing to match, boost
I (61465) rec: locked: wheel A cmd -0.099 rotor -0.101 turns/s, lag +0 steps, attempt 1/3 -- rotors on their holds: ramping back to the stick under boost
I (63126) rec: recovered: wheel A cmd +0.300 rotor +0.302 turns/s, lag +2 steps, attempt 1/3 -- made 0.25 turn: recovered in 1.9 s, no fault
```

### Settings (`set`)

| key | default | meaning |
|---|---|---|
| `sign_a`, `sign_b` | +1, -1 | robot-forward to wheel-encoder-positive. A is +1 by fiat; B is the mirror. See below. |
| `a_left` | 0 | 1 if wheel A is the left wheel, 0 if the right (decides the sign of a turn). On this build A is on the right |
| `track_m` | 0.263 | wheel centre to wheel centre, m. From the CAD; **measure it** |
| `vmax_tps`, `accel_tps2` | 0.3, 1.0 | output turns/s ceiling and turns/s^2 speeding up, both wheels; clamped to the measured envelope (2.0, 20). `accel_tps2` must be above 0 |
| `decel_tps2` | 2.0 | turns/s^2 slowing down in velocity mode: a released stick, `stop`, and the deadman all brake at this rate. Gentler than `accel_tps2` on purpose; raise it for a sharper stop |
| `gain_a`, `gain_b`, `inv_a`, `inv_b` | measured | written by `cal`, not by hand |
| `run_ma`, `hold_ma` | 1200, 600 | requested RMS mA per phase, both wheels; 100..1500 with hold <= run. Rounded down to the driver's discrete scale. Change with drivers disabled. `run_ma` above a nonzero `boost_ma` is refused |
| `boost_ma` | 1768 | boost current, mA: 0 turns boost off, else `run_ma`..1768 (1768 is IRUN 31, the most R110 gives). Live |
| `boost_start_ms` | 1500 | how long a START boost lasts after leaving a standstill of 0.5 s or more; 0..5000, 0 = no start boost. Live |
| `therm_tau_s` | 600 | the thermal model's heating time constant, s (cooling is twice it); 60..3600. The real motor's is estimated at ~1000 s, so 600 errs hot. Live |
| `therm_lim` | 1.10 | the heat at which boost pauses, 1.0 being the steady state at the rated 1.5 A; it resumes 0.10 below. 0.5..1.30. Live |
| `recover` | 1 | 1: a stall during a live stick command is retried (freeze, boost, re-lock, re-ramp) before it faults; 0: the stall detector faults on its first trip. Live, like all the stall settings below; a change starts the detectors over and cancels a recovery in progress |
| `rec_tries` | 3 | attempts without progress before the slip fault latches; 1..10 |
| `rec_lock_ms` | 200 | the shortest lock: how long both wheels are held, the tripped one following its rotor, before the ramp; 50..2000 |
| `rec_prog` | 0.25 | output turns every involved wheel must make toward the stick before an episode counts as recovered (and the attempt count starts over); 0.05..2 |
| `lag_trip` | 40 | stall detector trip level, microsteps of lag (5333 to the output turn at 1/8 microstepping): a full stall trips after ~42 steps of commanded travel at any speed. 0 turns the detector off and leaves only the servos' 1 s check; else 16 up to 0.8 x `lag_leak` |
| `lag_leak` | 400 | the commanded travel, microsteps, over which the detector's reference forgets: it high-passes the encoder's error and the clock's. 100..4000 |
| `lag_rev` | 48 | microsteps of commanded travel ignored after a start or a reversal, for the gear play; set it to the backlash measured on the stand plus 24. 0..400 |
| `iholddly` | 8 | how gradually current decays to hold current; 0..15, change disabled |
| `spread` | 1 | 1 SpreadCycle, 0 StealthChop; change disabled |
| `pwmthrs` | 0 | selected-microstep steps/s above which StealthChop hands over to SpreadCycle; only applies with `spread 0`, change disabled |
| `name` | `ubot` | mDNS host and BLE name (reboot to apply) |
| `hw_rev` | `A` | hardware revision string |
| `ota_url` | -- | default image URL for `ota start` |
| `batt_pack` | `li5s` | `li5s` 5S Li-ion (15.0-21.0 V) or `lfp4s` 4S LiFePO4 (10.0-13.6 V): the percentage table and the default thresholds. Setting it (or `unset batt_pack`) also erases the two overrides below, so a pack never inherits another's thresholds |
| `batt_warn_v`, `batt_cut_v` | 16.5, 15.5 (`li5s`); 12.4, 11.6 (`lfp4s`) | overrides of the pack's low warning and cutoff, V, warn above cut. `li5s` cuts within 12.5..20.0 V and warns up to 20.5 V, `lfp4s` 10.0..13.0 and 13.4: wide on purpose, so a bench can force low (`set batt_warn_v 20.5`) and cutoff (`set batt_cut_v 20.0`) on a charged pack. `unset` returns to the pack's own |
| `batt_div` | 11.0 | battery divider ratio, Vpack / Vpin, 1..100; calibrate against a meter |
| `wifi_ssid`, `wifi_pass` | -- | via `wifi set` |

The four `batt_` keys apply at once, not at the next boot, and `set` alone
lists them on their own `effective battery settings:` line after the drive
line (which is the one the app parses).

### Motor current and torque

The motors are **STEPPerOnline 17HS15-1504S-X1**: 1.50 A/phase,
0.45 N·m holding torque, 2.3 Ω/phase, 4.4 mH/phase, 1.8° full steps.
Sources: [motor datasheet](https://omc-stepperonline.com/download/17HS15-1504S-X1.pdf),
[manufacturer RMS/peak guidance](https://help.omc-stepperonline.com/hc/s/articles/how-to-set-the-current-on-stepper-driver-rms-or-peak).
Holding torque is not the running torque available on grass.

Current is entirely digital: `I_scale_analog=0`, `internal_Rsense=0`,
`vsense=0`, with the BTT TMC2209 V1.3's external 0.11 Ω sense resistors.
The VREF pots are ignored. These board constants live in `MotorCurrent.h`;
a replacement module with different resistors requires updating that profile.
The 1500 mA ceiling on `run_ma` is the motor's rating and is nominal;
component tolerances and cooling still matter. Only boost goes above it, to
IRUN 31 (1768 mA, all R110 gives), and only in bursts the thermal model allows.

```
disable
set run_ma 1200
set hold_ma 600
set spread 1
enable
```

Changes are persisted, staged while disabled, and verified on the next enable.
The default requests program approximately **1160 mA run / 552 mA hold**
(IRUN=20, IHOLD=9). A 1500 mA request programs approximately 1492 mA (IRUN=26).
`status` reports the programmed nominal current, not a current measurement.
`CS_ACTUAL` is the driver's scale, also not a measurement of coil current.

**Live current (0.3.0).** That pair is the base. With the drivers on, the
firmware rewrites IHOLD_IRUN as it goes, and `status`'s `torque:` line shows
the pair in force:

- **Boost** raises IRUN and IHOLD together to `boost_ma` (1768 mA, IRUN 31),
  so a robot stopped on a slope holds at boost current too. Reasons, each with
  its own expiry: *manual* (drive commands carrying the boost flag, `boost on`),
  *start* (`boost_start_ms` after leaving a standstill of 0.5 s or more,
  including the first move after `enable`), *recovery* (0.3.1: from a stall
  recovery's freeze, renewed through its ramp until it has made progress, at
  most 5 s an episode) and later *load*.
  Up is instant; down is one CS step per 100 ms on run and hold, so at
  `run_ma` 1500 a lapsed boost is back at IRUN 26 in 0.5 s, and a stationary
  one ramps to IHOLD 9 over 2.2 s.
- **Thermal model** (`ThermalModel.h`), one per motor, in normalized heat: 1.0
  is the steady state at the rated 1.5 A RMS, and a current I settles at
  (I / 1.5 A)². It heats with `therm_tau_s` (600 s) and cools twice as slowly,
  erring hot both ways against the motor's estimated ~1000 s. The current it
  integrates is inferred from the pair last written, following the driver's
  own standstill reduction, or the last CS_ACTUAL when that is higher and
  recent. Boost pauses at `therm_lim` (1.10, allowed by the PETG housings) and
  comes back at 1.00. Power-on assumes 0.80; a warm reset carries the heat over
  in RTC memory. From warm at 1160 mA cruise there are ~10 minutes of boost,
  from power-on ~7; a recharge takes ~4.4 min cruising, ~2.2 parked.
- **OTPW derate** (`OtpwDerate` in `BoostPolicy.h`) per driver, from its
  DRV_STATUS samples: level 1 no boost, 2 base at 75%, 3 at 50% (see Safety
  model). A driver already hot when it is configured starts at level 2.
- **Battery low** (and cutoff) refuses boost: no extra draw from a sagging pack.

Writes go out through the control tick's one spare bus slot: current going
down before current going up, the two wheels alternating, each at most once per
100 ms, IFCNT-verified with one retry before the driver is declared lost (EN
cut, as for any driver fault). The slot also carries the health poll, which it
never delays by more than 50 ms, and it waits when the servos have already
used 3 ms of the 5 ms tick. While a wheel runs in SpreadCycle its CS_ACTUAL
must equal the written IRUN; `stats` and `boost` count the samples that did
not (`cs_mismatch`), with a warning at most every 10 s. Every boost on/off
(with reasons and duration), heat pause/resume and derate level change is
logged.

The UART now waits 3 idle symbol times rather than the driver's default 10
before it hands a reply over (120 us instead of 400 us at 250 kbaud, per read
and per write echo) and has no TX ring buffer, so a datagram starts inside the
write call: an IFCNT-verified write is estimated at ~2.0 ms rather than ~2.8.
`stats` shows the longest read and write the bus has actually taken, lock
held.

Legacy NVS `irun`, `ihold`, `iscale`, and `rsense` values are ignored; attempts
to set them are refused. Old motion settings remain effective if saved in NVS.
Fresh defaults are 0.3 wheel turns/s (~0.20 m/s) and 1 turn/s² acceleration.

Before each enable, EN stays high while both drivers receive zero velocity and
configuration. IFCNT checks accepted writes, GCONF/CHOPCONF are read back,
and GSTAT/DRV_STATUS are checked. Initialization compensates for the SPREAD pin.
A failed check refuses enable. A driver reset or lost VMOT requires explicit
re-enabling; the firmware never resumes motion automatically.

Both drivers are polled for health, each approximately every 500 ms, including
during calibration. A communication failure, reset, undervoltage, short,
overtemperature shutdown or a t143/t150/t157 flag disables both drivers and
latches a driver fault. The **OTPW warning** (and t120) derates that wheel
instead, since 0.3.0; the chip itself never reduces current for it.
Open-load bits are reported but do not fault: they can appear at standstill.
The console and WebSocket status include raw driver status, its age/validity,
and a frozen copy of the most recent sample when a motion fault latches.
An older or unavailable sample must not be treated as the exact fault-time state.

`wheel A reg 6F` / `wheel B reg 6F` decode live driver status; read while moving
to inspect run current and active chopper. GCONF (00) and CHOPCONF (6C) are also
readable. See the [TMC2209 datasheet](https://www.analog.com/media/en/technical-documentation/data-sheets/TMC2209_datasheet_rev1.09.pdf).

Host fault-injection tests (no hardware), among them stall detection and
recovery on the plant rig (`test_recovery_rig`: in sync at 0.02-1.5 turns/s, a
stall caught within 100 steps at every speed, a ridge and a hill recovered, a
wall given up after 3 attempts, boost before the snap, encoder gaps without a
false slip fault), the live current path on
the plant rig (`test_torque`), the slot scheduler (`test_uartslot`) and the
live-write retry and soft/hard masks (`test_velgen`):

```sh
python3 components/drive/tests/run_host_tests.py
python3 components/battery/tests/run_host_tests.py
```

Rack checks: use short timed velocity commands in each direction, confirm
SpreadCycle and CS_ACTUAL=20 while running at the default current, confirm the
deadman stops motion, and finish with `disable`. Free spin checks configuration,
tracking and communications; it does not establish available grass torque or
long-duration thermal performance. Do not use fingers near the wheel/gear mesh
as a load fixture. A later controlled outdoor test is still required.

### Which way is forward

Calibration makes each wheel self-consistent (+VACTUAL counts its own encoder
up) and stops there. The wheels are mirrored, so `sign_b = -1` is what the
mechanism predicts and has not been confirmed by watching the robot. Run
`enable` then `demo short` and watch beat 2, "in phase": if the wheels
counter-rotate instead of rolling the same way, `set sign_b 1`. If the robot
drives backwards on `drive 0.2 0`, flip **both** signs. If forward is right but
a turn goes the wrong way (stick left, robot turns right), the wheels sit on
the opposite sides from what `a_left` says: flip `a_left` (default 0). Never
fix a frame problem with `wheel X invert` -- that bit was measured together
with the clock gain and the loop depends on it.

## WebSocket protocol (`ws://ubot.local/ws`)

One JSON object per text frame. Client to robot:

```json
{"t":"drive","v":0.5,"w":-0.2}            normalised, -1..1 of the current limits
{"t":"drive","v_mps":0.3,"w_radps":0.0}   or physical units; optional "hold" in ms
{"t":"drive","v":0,"w":0,"boost":true}    optional "boost": boost while this command holds;
                                          a drive without it ends a boost (0.3.0)
{"t":"stop"}  {"t":"enable"}  {"t":"disable"}  {"t":"estop"}  {"t":"clear"}
{"t":"status"}                            a status frame now
{"t":"log","on":true}                     mirror the log to this client
{"t":"ota_check"}                         compare the bucket's version.txt; result lands in status.ota
{"t":"ota_update"}                        install the bucket's firmware.bin (disables drivers, reboots)
```

Robot to client: a `status` frame on connect and at 5 Hz, `ack` frames for
everything but `drive` (a `drive` is only acknowledged when refused), and
`log` frames when subscribed.

```json
{"t":"status","fw":"0.3.1","hw":"A","name":"ubot","up":64,
 "enabled":true,"faulted":false,"fault":null,"fault_wheel":"A","fault_code":0,"caps":["boost"],
 "cal":false,"demo":null,
 "cmd":{"v":0.2,"w":0.0,"active":true},"limits":{"v":0.675,"w":5.14},
 "rec":{"on":true,"state":"idle","try":0,"wheels":0,"n":4,"ok":3,"fail":0},
 "batt":{"present":true,"v":19.97,"pct":79,"state":"ok","pack":"li5s"},"wifi":{"rssi":-61},
 "ota":{"busy":false,"state":"update available: 0.1.2","available":"0.1.2","configured":true},
 "wheels":[{"name":"A","driver":true,"pos":0.588,"vel":0.296,"slip":1,"lag":-3,"trips":4,"enc":true,
            "agc":128,"magnet":"ok","fault":0,"gain":1.0159,"loop":true,"run_ma":1160,"hold_ma":552,...,
            "torque":{"run":1768,"hold":1768,"boost":2,"act":true,"h":0.84,"hot":false,
                      "derate":0,"otpw":false}}, {...}]}
```

`caps` lists what this firmware accepts beyond the basics; `"boost"` (0.3.0)
means drive frames may carry `"boost":true`. Per wheel, `run_ma`/`hold_ma` are
the base pair and `torque` the live one: `run` and `hold` in mA, `boost` the
active reasons (1 manual, 2 start, 4 recovery, 8 load, granted or not), `act`
whether boost is granted, `h` the thermal model's heat (1.0 = rated steady
state), `hot` whether it is in its limited band (from `therm_lim` down to the
resume point), `derate` the OTPW level 0-3 and `otpw` the driver's last sample.
Also per wheel since 0.3.1, `lag` is the stall detector's lag in whole
microsteps (0 while it is not armed) and `trips` its trips since boot.

`rec` (0.3.1) is stall recovery: `on` the `recover` setting, `state` `idle`,
`lock` or `ramp` -- anything but `idle` is one episode, from the first trip until
it recovers, is cancelled or gives up, never `idle` between its retries --
`try` the episode's attempt (0 when idle), `wheels` the wheels in it (bit 0 A,
bit 1 B), and since boot `n` attempts (BLE status byte 16 is its low byte),
`ok` recoveries and `fail` give-ups. A recovery never shows as `cal`, `demo` or
`ota`, which lock the app's stick.

When a fault is latched, `fault` is its "name (reason)" and `fault_code` its
`drive_fault_t` (always present since 0.2.9, 0 when nothing is latched). A
wheel fault names its wheel in `fault_wheel`; the battery cutoff (code 6) is
robot-level and sends `"fault_wheel":"-"`. A cutoff therefore reads
`"enabled":true,"faulted":true,"fault_code":6` with `batt.state` `"cutoff"`.
`batt.state` is `none`, `ok`, `low` or `cutoff`, the robot's own judgement;
`batt.pack` is `batt_pack`. A status frame that would not fit its 3 KB buffer
is logged and not sent, never sent cut short.

The joystick page at `http://ubot.local/` speaks exactly this protocol and is
the quickest way to check it from a laptop or a phone browser. Everything on it
is driven by the status frame. A state card says what the robot is doing
(motors off or on, a fault with the wheel and the reason or the battery
cutoff, calibrating, a demo, installing an update, not connected), and the
battery chip shows low and cut off; one power button toggles the drivers and
its label says what pressing it will do; the actions that only make sense in
one state (clear fault, stop demo, abort calibration, stop a command from
another controller) appear inside the card only in that state. The stick is
locked, with the reason under it, whenever a drive would be refused, so it
never sends `drive` frames the robot will bounce. E-STOP is always in the same
place, follows the page as it scrolls, and is only greyed out when there is no
connection to carry it. A refused command shows as a toast and lands in the log
pane under Details, which also holds the per-wheel numbers and the switch for
the log mirror.

On connect the page sends `ota_check`; if the bucket holds a newer version an
"Update to x.y.z" chip appears (two taps within 4 s to install, so a stray touch
cannot start it), then the state card follows the download. Use the Mac updater for installation
and confirmation; the browser cannot confirm a pending candidate.

## BLE

Advertises as the device name (`ubot`), 16-bit UUIDs for DIS and Battery in
the advertisement, the drive service UUID in the scan response.

| service | characteristic | |
|---|---|---|
| Device Information `0x180A` | `2A29` manufacturer, `2A24` model, `2A25` serial, `2A26` firmware rev, `2A27` hardware rev | read |
| Battery `0x180F` | `2A19` level % | read, notify (1 Hz) |
| U-BOT `7b1a0000-6f4b-4c2e-9d3a-2e5f1c8a9b01` | `7b1a0001` drive | write w/o response: `int16 v, int16 w` little-endian, thousandths of the limits, plus since 0.3.0 an optional `u8 flags` (bit 0 boost while held; other bits ignored). 4 or 5 bytes, any other length is refused; send 5 only after status flags2 bit 7, since older firmware refuses them. Held 500 ms |
| | `7b1a0002` control | write: `0` stop `1` enable `2` disable `3` estop `4` clear faults |
| | `7b1a0003` status | read, notify at 5 Hz, 20 bytes since 0.3.0 (18 in 0.2.9, 13 before): `u8 flags, u8 fault, u16 batt_mV, u8 batt_pct, i16 velA, i16 velB (thousandths turn/s), i16 v_mm/s, i16 w_mrad/s`, then `u8 flags2, u8 heat_a, u8 heat_b, u8 recoveries, u8 batt_state, u8 derate, u8 reserved`. flags: b0 enabled, b1 faulted, b2 cmd active, b3 enc A ok, b4 enc B ok, b5 battery present. `fault` is the latched `drive_fault_t`, the battery cutoff's 6 included. flags2, each "on either wheel": b0 boost granted (START included), b1 manual boost asked, b2 derate level 1+, b3 heat-limited (the whole limited band), b4 OTPW, b5 recovering (0.3.1: from a stall recovery's first trip until it recovers, is cancelled or gives up, set throughout its retries), b6 load estimate valid (0 until 0.4.0), b7 set: 5-byte drive frames accepted and bytes 14-16 and 18 valid. heat = round(h x 100), saturating at 255. recoveries: the low byte of the stall recovery attempt counter since boot (WebSocket `rec.n`), wrapping; 0 before 0.3.1. batt_state 0 none, 1 ok, 2 low, 3 cutoff. derate: wheel A's level in bits 0-1, B's in bits 2-3. 20 bytes is all a default-MTU notification carries |

## OTA

The existing two-slot layout is unchanged. Updates use an immutable release
image and a manifest containing version, project, target, size, full binary
SHA-256, and ELF identity. `push_firmware.sh` publishes the manifest last and
also maintains `firmware.bin` / `version.txt` for older firmware.

```sh
./ota_provisioning.sh             # creates/updates the firmware bucket policy
./push_firmware.sh                # bump, build, publish
ubotctl ota source https://BUCKET.s3.REGION.amazonaws.com --wifi ubot.local
ubotctl ota check --wifi ubot.local
ubotctl ota install --wifi ubot.local
ubotctl ota upload build/ubot_base.bin --wifi ubot.local
```

BLE can initiate and monitor S3 installation. Binary upload requires Wi-Fi.
The Mac updater verifies the boot, version and full ELF identity before
confirming the candidate. A candidate without confirmation rolls back after
120 seconds when a valid fallback exists. Automatic installation is disabled.
Use the Mac updater for installation: the legacy browser's update chip cannot
perform management confirmation. See [MAINTENANCE.md](MAINTENANCE.md).

## Verified on the rack, 2026-09-02

Both drivers answer, both encoders read, console, BLE (all three services read
from a Mac, status notifications at 5 Hz) and WiFi scan all work. `cal A` gave
1.0159, `cal B` 1.0096, both with residuals within 2
counts and both stored. `demo short` ran 9.1 s against 9.1 planned, wheels back
within 1 and 3 counts. `drive 0.2 0 2` moved each wheel 0.59 turns with
mirrored encoder signs, as the frame predicts. A forced slip on A stopped B and
latched. Worst control tick 3.0 ms of 5 ms over 6700 ticks with logging
asynchronous.

On the network (after `wifi set`): `ubot.local` resolves, the joystick page
serves in ~0.1 s, a WebSocket client gets its status frame on connect, a status
request round-trips in ~80 ms, status arrives at 5 Hz, the log mirror works, a
normalised drive of 0.3 became 0.203 m/s and moved both wheels 0.55 turns in
opposite encoder senses, the deadman stopped it 0.6 s after the client went
quiet, and a drive while disabled came back as a refused `ack`. Ping averages
~60 ms with WiFi modem power-save on in that test. Since 0.1.6, modem sleep
defaults off to prioritize command latency; `wifi ps on|off` changes it until
reboot for diagnosis. BLE coexistence still shares radio time.

Since 0.1.7, the Wi-Fi task runs on core 1 and the Bluetooth controller and
NimBLE host stay on core 0. Software radio coexistence remains enabled. For a
Wi-Fi-only diagnostic build, disable `U-BOT base -> Start BLE at boot`
(`CONFIG_UBOT_BLE_ENABLE`) in `idf.py menuconfig`, then build and flash. This
skips Bluetooth initialization and advertising entirely. Restore the option
after the comparison; it defaults on. Existing build configurations must also
select Wi-Fi task core 1 in menuconfig, since `sdkconfig.defaults` does not
override an existing `sdkconfig`.
The replacement board's [Wi-Fi comparison](components/net/WIFI_DIAGNOSTICS.md)
still showed unreliable connectivity with both configurations; core separation
is not a confirmed fix.

OTA, end to end: `ota_provisioning.sh` made the bucket, `push_firmware.sh`
published 0.1.1 (1.77 MB), and on the robot `set ota_url <bucket>` then
`ota check` found 0.1.1 newer than the running 0.1.0, disabled the drivers,
downloaded it over HTTPS with the stock certificate bundle, rebooted into
`ota_1`, rejoined WiFi and marked itself valid. About 40 s from `ota check` to
the prompt coming back on the new image. Then from the page: it showed
"firmware 0.1.2 -- 0.1.3 available" with the button, two taps installed 0.1.3
(~45 s, progress in the status line and the log pane), the page noticed the
robot go silent at the reboot and reconnected on its own to the new image.
The page treats 3 s without a status frame as a dead connection so it can
reconnect promptly after a reboot.

## Known items and assumptions

- **`track_m` 0.263** is read off `u-bot.scad` (body 250 wide, wheel plane
  3.35 mm outboard of the leg), not measured. It only scales the turn rate.
- **Battery sense** is on GPIO2 (D1) through the 100k over 10k divider, with no
  internal pull-down: the ~19k one measured on this S3 loaded the 10k leg and
  made the pack read a third low. With nothing connected the divider's 10k
  holds the pin near zero and the reports say "no sense". The pack is the 5S
  Li-ion `li5s` (15.0 V empty, 19.97 V is 79%, 21.0 V full; warn 16.5 V, cut
  15.5 V, 3.3 and 3.1 V a cell); `set batt_pack lfp4s` for the original 12 V
  LiFePO4 (10.0 V empty, 13.6 V full). A full 5S pack puts ~1.9 V on the pin,
  inside the ADC's range. Calibrate `batt_div` against a meter; a reading that
  makes no sense for the configured pack comes with a hint naming the fix
  (`batt`, and the log).
- **Wheel B's magnet** still reads weak at AGC 128. The firmware
  warns before `cal` and `demo short`; the fix is mechanical.
- **Flash is tight**: 1.76 MB image in a 1.92 MB slot (10% free). mbedTLS,
  WiFi and NimBLE are most of it. If it bites: drop IPv6 in lwIP, or trim the
  certificate bundle to Amazon's roots. Size optimisation is already on.
- **Control tick worst case ~3 ms** with the radios up and idle. The bit-banged
  bus is preempted by the WiFi task (priority 23 against the control task's
  20); if the margin shrinks once WebSocket traffic is flowing, raising the
  control task above WiFi is the first thing to try.
- **Deadman on the console** defaults to 2 s per `drive`; `drive v w 0` holds
  until `stop`, for bench use only.
- **Stall recovery is tuned on the host plant, not yet on the robot.** On the
  plant (`test_recovery_rig`) a ridge or a hill between base and boosted
  pull-out is recovered in one attempt at 0.2-0.5 turns/s, but at a crawl (0.1
  turns/s) a wheel that slips under a load pushing back rolls back faster than
  it was asked to go forward. The hold never goes faster than the command, so it
  cannot catch it and those end in the ordinary latch. The plant's rotor-on-robot
  mode is barely damped and its friction is a guess, so the stand and the yard
  decide; `lag_rev` wants the backlash measured first.
