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
- **Battery** voltage through a divider into ADC1, percentage from a 4S
  LiFePO4 resting-voltage table (the pack is 12 V 8 Ah LiFePO4).
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
    battery/               ADC sense
    sysinfo/               versions, serial, reset reason, partition state
    ulog/                  async log printer, per-tag levels, WebSocket mirror
  monitor.sh               open the console (idf.py monitor)
  ota_provisioning.sh      create the S3 bucket, once
  push_firmware.sh         bump version, build, upload to the bucket
  partitions.csv           nvs + otadata + two 1.9 MB OTA slots, 4 MB flash
  sdkconfig.defaults       everything that differs from the IDF defaults, commented
```

## Safety model

- **EN is the killswitch** (GPIO20 / D9, active low, shared by both drivers, 4.7k
  pull-up). It is driven high before any other line of `app_main` runs, and it
  floats high through an MCU reset, a watchdog reset or a broken wire. `estop`
  writes it directly from any task without taking a lock.
- **VACTUAL is zeroed before EN drops**, on every driver, every time. The
  register survives an MCU reset with the power stage off.
- **The control task is on the task watchdog** (3 s). A wedged loop reboots the
  chip and EN goes high on the way.
- **Deadman.** `drive` commands hold for a given time (console default 2 s,
  WebSocket and BLE 500 ms). Keep sending or the robot stops.
- **Fault propagation.** Slip on one wheel, an encoder that stops answering, or
  a magnet that disappears faults that wheel; the other wheel is stopped too,
  because on a differential drive a wheel holding while its partner drives
  pivots the robot. Motion is refused until `faults clear` (or the WebSocket /
  BLE clear op) -- never cleared by a joystick.
- **Drivers start disabled** and will not energise while either TMC2209 is not
  answering on the bus.

## Console

Connect with `idf.py monitor` (or any terminal at any baud; the port is USB).
The prompt is `ubot> `. A few worth knowing:

```
status                        everything on one screen
enable / disable              power stage on / off (both drivers, shared EN)
stop / estop                  ramp to zero / EN high right now
drive <v m/s> <w rad/s> [s]   robot frame; positive w is anticlockwise from above
wheel A goto 0.5              bench: position move on one wheel (also move, vel,
                              spin, zero, loop on|off, invert, reg, kp vmax ...)
cal A / cal B                 measure shaft polarity and clock gain, ~23 s each;
                              stored in NVS, results in the log
demo short                    both wheels, ~9 s, round-trip check as the outro
faults / faults clear
stream on [hz] / stream off   CSV telemetry, same columns as test_servo streamed
set / set <key> <value>       settings (below)
wifi set <ssid> <password>    provisioning; wifi scan / wifi / wifi clear
wifi ps on|off               runtime modem-sleep diagnostic; boot defaults off
ota <https://...>/firmware.bin   or: ota url <...> once, then ota start
log drive debug               per-tag level: none error warn info debug verbose
hw set B                      hardware revision
stats / stats reset           control timing, bus health, dropped log lines
```

### Settings (`set`)

| key | default | meaning |
|---|---|---|
| `sign_a`, `sign_b` | +1, -1 | robot-forward to wheel-encoder-positive. A is +1 by fiat; B is the mirror. See below. |
| `a_left` | 0 | 1 if wheel A is the left wheel, 0 if the right (decides the sign of a turn). On this build A is on the right |
| `track_m` | 0.263 | wheel centre to wheel centre, m. From the CAD; **measure it** |
| `vmax_tps`, `accel_tps2` | 0.3, 1.0 | output turns/s ceiling and turns/s^2 speeding up, both wheels; clamped to the measured envelope (2.0, 20) |
| `decel_tps2` | 2.0 | turns/s^2 slowing down in velocity mode: a released stick, `stop`, and the deadman all brake at this rate. Gentler than `accel_tps2` on purpose; raise it for a sharper stop |
| `gain_a`, `gain_b`, `inv_a`, `inv_b` | measured | written by `cal`, not by hand |
| `run_ma`, `hold_ma` | 1200, 600 | requested RMS mA per phase, both wheels; 100..1500 with hold <= run. Rounded down to the driver's discrete scale. Change with drivers disabled |
| `iholddly` | 8 | how gradually current decays to hold current; 0..15, change disabled |
| `spread` | 1 | 1 SpreadCycle, 0 StealthChop; change disabled |
| `pwmthrs` | 0 | selected-microstep steps/s above which StealthChop hands over to SpreadCycle; only applies with `spread 0`, change disabled |
| `name` | `ubot` | mDNS host and BLE name (reboot to apply) |
| `hw_rev` | `A` | hardware revision string |
| `ota_url` | -- | default image URL for `ota start` |
| `batt_div` | 11.0 | battery divider ratio, Vpack / Vpin; calibrate against a meter |
| `wifi_ssid`, `wifi_pass` | -- | via `wifi set` |

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
The 1500 mA ceiling is nominal; component tolerances and cooling still matter.

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
overtemperature shutdown, or **OTPW warning** disables both drivers and latches
a driver fault. OTPW does not automatically reduce current in the chip.
Open-load bits are reported but do not fault: they can appear at standstill.
The console and WebSocket status include raw driver status, its age/validity,
and a frozen copy of the most recent sample when a motion fault latches.
An older or unavailable sample must not be treated as the exact fault-time state.

`wheel A reg 6F` / `wheel B reg 6F` decode live driver status; read while moving
to inspect run current and active chopper. GCONF (00) and CHOPCONF (6C) are also
readable. See the [TMC2209 datasheet](https://www.analog.com/media/en/technical-documentation/data-sheets/TMC2209_datasheet_rev1.09.pdf).

Host fault-injection tests (no hardware):

```sh
python3 components/drive/tests/run_host_tests.py
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
{"t":"status","fw":"0.1.0","hw":"A","name":"ubot","up":64,
 "enabled":true,"faulted":false,"fault":null,"fault_wheel":"A","cal":false,"demo":null,
 "cmd":{"v":0.2,"w":0.0,"active":true},"limits":{"v":0.675,"w":5.14},
 "batt":{"present":false,"v":0.0,"pct":-1},"wifi":{"rssi":-61},
 "ota":{"busy":false,"state":"update available: 0.1.2","available":"0.1.2","configured":true},
 "wheels":[{"name":"A","driver":true,"pos":0.588,"vel":0.296,"slip":1,"enc":true,
            "agc":128,"magnet":"ok","fault":0,"gain":1.0159,"loop":true}, {...}]}
```

The joystick page at `http://ubot.local/` speaks exactly this protocol and is
the quickest way to check it from a laptop or a phone browser. Everything on it
is driven by the status frame. A state card says what the robot is doing
(motors off or on, a fault with the wheel and the reason, calibrating, a demo,
installing an update, not connected); one power button toggles the drivers and
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
| U-BOT `7b1a0000-6f4b-4c2e-9d3a-2e5f1c8a9b01` | `7b1a0001` drive | write w/o response: `int16 v, int16 w` little-endian, thousandths of the limits. Held 500 ms |
| | `7b1a0002` control | write: `0` stop `1` enable `2` disable `3` estop `4` clear faults |
| | `7b1a0003` status | read, notify at 5 Hz: `u8 flags, u8 fault, u16 batt_mV, u8 batt_pct, i16 velA, i16 velB (thousandths turn/s), i16 v_mm/s, i16 w_mrad/s`. flags: b0 enabled, b1 faulted, b2 cmd active, b3 enc A ok, b4 enc B ok, b5 battery present |

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
- **Battery sense** is on GPIO2 (D1) with a weak internal pull-down so an unwired
  pin reads "no sense", which is what the robot reports today: nothing is wired
  yet. The pack is a 12 V 8 Ah LiFePO4, so the percentage uses a 4S
  resting-voltage table (10.0 V empty, 12.9 V is 20%, 13.2 V is 70%, 13.6 V
  full) rather than a linear window. `batt_div` is still the nominal 11.0 for a
  100k over 10k divider; calibrate it against a meter once the divider is
  wired, because the pin's pull-down loads the lower leg.
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
