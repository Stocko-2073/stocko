# U-BOT base firmware

Firmware for the base of the U-BOT outdoor utility robot: a XIAO ESP32-C6
driving two NEMA 17 wheels through TMC2209s in UART velocity mode, with an
AS5600 encoder on each output shaft. Built on ESP-IDF v6.1, not Arduino.

It is the `test_servo` bench work made permanent: the same servo loop, the same
calibration, the same two-wheel demo, moved under a control task and given a
robot frame, a deadman, a console, WiFi, BLE and OTA. The mechanism, its
measured numbers and the reasons behind the design are in
[`../DRIVE_MECHANISM.md`](../DRIVE_MECHANISM.md); this file is about the
firmware.

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
- **Battery** voltage through a divider into ADC1, percentage from a
  configurable window.
- **Firmware and hardware revision** from `version.txt` and NVS, reported the
  same way on console, WebSocket and BLE.

## Building and flashing

ESP-IDF v6.1 is installed at `~/esp/esp-idf`. mDNS and cJSON come from the
component registry on the first build (needs network once).

```sh
. ~/esp/esp-idf/export.sh
cd u-bot/firmware/base
idf.py set-target esp32c6        # first time only
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

- **EN is the killswitch** (GPIO0, active low, shared by both drivers, 4.7k
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
ota <https://...>/firmware.bin   or: ota url <...> once, then ota start
log drive debug               per-tag level: none error warn info debug verbose
hw set B                      hardware revision
stats / stats reset           control timing, bus health, dropped log lines
```

### Settings (`set`)

| key | default | meaning |
|---|---|---|
| `sign_a`, `sign_b` | +1, -1 | robot-forward to wheel-encoder-positive. A is +1 by fiat; B is the mirror. See below. |
| `a_left` | 1 | wheel A is the left wheel (decides the sign of a turn) |
| `track_m` | 0.263 | wheel centre to wheel centre, m. From the CAD; **measure it** |
| `vmax_tps`, `accel_tps2` | 1.0, 8.0 | output turns/s and turns/s^2, both wheels; clamped to the measured envelope (2.0, 20) |
| `gain_a`, `gain_b`, `inv_a`, `inv_b` | measured | written by `cal`, not by hand |
| `name` | `ubot` | mDNS host and BLE name (reboot to apply) |
| `hw_rev` | `A` | hardware revision string |
| `ota_url` | -- | default image URL for `ota start` |
| `batt_div`, `batt_vmin`, `batt_vmax` | 11.0, 10.0, 12.6 | divider ratio, and the 0%..100% voltage window |
| `wifi_ssid`, `wifi_pass` | -- | via `wifi set` |

### Which way is forward

Calibration makes each wheel self-consistent (+VACTUAL counts its own encoder
up) and stops there. The wheels are mirrored, so `sign_b = -1` is what the
mechanism predicts and has not been confirmed by watching the robot. Run
`enable` then `demo short` and watch beat 2, "in phase": if the wheels
counter-rotate instead of rolling the same way, `set sign_b 1`. If the robot
drives backwards on `drive 0.2 0`, flip **both** signs. Never fix a frame
problem with `wheel X invert` -- that bit was measured together with the clock
gain and the loop depends on it.

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
the quickest way to check it from a laptop or a phone browser. On connect it
sends `ota_check`; if the bucket holds a newer version the page shows an
"update to x.y.z" button (two taps to install, so a stray touch cannot start
it), then follows the download in the status line and reconnects to the new
image after the reboot.

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

Two OTA slots, no factory app, rollback on. Images come from an S3 bucket
with the layout corvid used: `firmware.bin` and `version.txt` at the top,
both public-read, everything else private, versioning on.

```sh
./ota_provisioning.sh        # once: creates ubot-ota-<account>, writes .ota_config
./push_firmware.sh           # bump patch version, build, upload both objects
./push_firmware.sh --bump-minor | --bump-major | --no-bump | --clean
```

On the robot, once: `set ota_url https://ubot-ota-<account>.s3.us-east-1.amazonaws.com`
(the URL the provisioning script prints). Then:

| command | does |
|---|---|
| `ota check` | reads `version.txt`; installs `firmware.bin` only if it is newer than the running version |
| `ota start` | installs `firmware.bin` regardless |
| `ota https://.../x.bin` | installs a specific image |
| `set ota_auto 1` | run `ota check` every time WiFi connects |
| `ota` | state, stored URL, a newer version seen in the bucket, which slot is running and whether it is verified |
| page at `ubot.local` | checks on load; offers an update button when the bucket is newer |

An update disables the drivers, downloads with the IDF certificate bundle
(Amazon's roots are in it), refuses an image whose project name is not
`ubot_base`, writes it and reboots. The new image boots once as "pending
verify" and marks itself valid at the end of `app_main`; if it never gets there
the bootloader boots the previous slot next time. Only `https://` is accepted.
`ota check` that finds nothing newer does not touch the drivers.

## Verified on the rack, 2026-09-02

Both drivers answer, both encoders read, console, BLE (all three services read
from a Mac, status notifications at 5 Hz) and WiFi scan all work. `cal A` gave
1.0159 (was 1.0158), `cal B` 1.0096 (was 1.0091), both with residuals within 2
counts and both stored. `demo short` ran 9.1 s against 9.1 planned, wheels back
within 1 and 3 counts. `drive 0.2 0 2` moved each wheel 0.59 turns with
mirrored encoder signs, as the frame predicts. A forced slip on A stopped B and
latched. Worst control tick 3.0 ms of 5 ms over 6700 ticks with logging
asynchronous (it was 20 ms with logging synchronous, which is why it is not).

On the network (after `wifi set`): `ubot.local` resolves, the joystick page
serves in ~0.1 s, a WebSocket client gets its status frame on connect, a status
request round-trips in ~80 ms, status arrives at 5 Hz, the log mirror works, a
normalised drive of 0.3 became 0.203 m/s and moved both wheels 0.55 turns in
opposite encoder senses, the deadman stopped it 0.6 s after the client went
quiet, and a drive while disabled came back as a refused `ack`. Ping averages
~60 ms with WiFi modem power-save on (the default); `esp_wifi_set_ps(WIFI_PS_NONE)`
in `wifi.c` is the knob if that ever matters.

OTA, end to end: `ota_provisioning.sh` made the bucket, `push_firmware.sh`
published 0.1.1 (1.77 MB), and on the robot `set ota_url <bucket>` then
`ota check` found 0.1.1 newer than the running 0.1.0, disabled the drivers,
downloaded it over HTTPS with the stock certificate bundle, rebooted into
`ota_1`, rejoined WiFi and marked itself valid. About 40 s from `ota check` to
the prompt coming back on the new image. Then from the page: it showed
"firmware 0.1.2 -- 0.1.3 available" with the button, two taps installed 0.1.3
(~45 s, progress in the status line and the log pane), the page noticed the
robot go silent at the reboot and reconnected on its own to the new image.
(The first attempt exposed why that watchdog exists: a browser can sit on a
WebSocket whose peer has rebooted for minutes without noticing, so the page
now treats 3 s without a status frame as a dead connection.)

## Known items and assumptions

- **`track_m` 0.263** is read off `u-bot.scad` (body 250 wide, wheel plane
  3.35 mm outboard of the leg), not measured. It only scales the turn rate.
- **Battery sense** is on GPIO1 (D1) with a weak internal pull-down so an unwired
  pin reads "no sense". The divider and the voltage window are settings because
  the pack is not chosen; calibrate `batt_div` against a meter once it is.
- **Wheel B's magnet** still reads weak at AGC 128, as before. The firmware
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
