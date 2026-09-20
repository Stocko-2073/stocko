# U-BOT phone app

An iPhone app that drives U-BOT over Bluetooth Low Energy or Wi-Fi and films
it with the phone's own camera. BLE works without a Wi-Fi network; Wi-Fi uses
the robot's existing WebSocket interface.

The app is portrait-locked and records its whole screen, so the clip you get out
of it has the camera view of the robot on top and a live joystick underneath, in
one 19.5:9 vertical video.

There are no firmware changes. The base firmware has served a BLE drive service
since 0.1.4; this is the phone app its header comment was written for.


## Layout

    project.yml            XcodeGen spec. The source of truth for the project.
    UBot/                  The app: SwiftUI, iOS 17, no entitlements.
    Packages/UBotCore/     BLE and Wi-Fi transports, as a plain SPM package.
      Sources/UBotCore/    Protocol, transport, drive ticker, lock model, stick feel.
      Sources/ubotctl/     A macOS bench harness that speaks the same protocol.
      Tests/               Protocol, connection lifecycle, and lock-model tests (Swift Testing).

`UBotCore` builds for macOS as well as iOS, and that is deliberate rather than
incidental. `ubotctl` drives a real robot from a Mac terminal using the exact
`BLERobotLink` / `WiFiRobotLink` the phone uses, so the wire protocol can be
verified against hardware with no Xcode involved, and so there is a known-good
reference on the desk when the phone misbehaves in a field.


## Building

The app needs Xcode. The core does not.

    # The core, today, with only the Command Line Tools:
    cd Packages/UBotCore
    swift build
    swift run ubotctl selftest      # 39 checks, no radio, no robot
    swift test                      # 43 tests

    # The app, once Xcode is installed:
    brew install xcodegen
    xcodegen generate
    open UBot.xcodeproj

Do the first device run from the Xcode GUI: team selection and the "trust this
developer" step in Settings > General > VPN & Device Management are GUI flows.
After that, `xcodebuild` and `xcrun devicectl` are faster to drive from a
terminal.

The app declares no capabilities and no entitlements -- BLE, camera, ReplayKit
and add-only Photos access are all Info.plist usage strings -- so it provisions
the same way under a free personal team as under a paid one. Under a free team
the signature expires after seven days and you rebuild.

Neither Bluetooth nor the camera exists in the Simulator. The Simulator build
uses `MockRobotLink` for BLE and the real Wi-Fi transport when Wi-Fi is selected.
The mock emits synthetic status at the same 5 Hz the
firmware does and honours the control ops, so every screen state can be reached
and screenshotted without hardware.


## Wi-Fi and connection selection

Use the **BLE / Wi-Fi** selector at the top right. The selection is saved; an
existing installation starts in BLE mode. The gear opens connection settings.
Wi-Fi defaults to `ubot.local`; enter an IP address or hostname, optionally
with a port, if name resolution is unavailable. The endpoint is always
`ws://<address>/ws`. Allow **Local Network** access when iOS prompts.

The robot must already be provisioned onto a network reachable from the phone.
This app does not provision Wi-Fi or create a hotspot. There is no automatic
fallback between transports. Changing transport or the active Wi-Fi address
releases the joystick, attempts a stop on the old link, clears old telemetry,
and connects again. A fresh touch is required to drive after reconnection.
Motors are never automatically enabled by connecting.

Wi-Fi supports normalized joystick commands at 10 Hz, a 500 ms command hold,
all five control operations, and status at 5 Hz. Commands are acknowledged;
refusals are displayed. Motion updates are coalesced rather than queued. Status
silence for 1.5 seconds locks driving and reconnects with 1/2/4/8-second backoff.
Connection loss never replays a held joystick or queued control command.
Calibration, demos, and OTA activity reported over Wi-Fi lock the joystick.
Motor-driver fault code 5 and unknown faults are visible on both transports.

The bench harness selects Wi-Fi with an optional argument:

    swift run ubotctl status --wifi ubot.local
    swift run ubotctl status --wifi 192.168.1.47

Without `--wifi`, the harness uses BLE. The iPhone controller and UI tests are
included in the generated `UBot` Xcode scheme, alongside the package tests.

## Safety model

The robot is a 12 V machine with two NEMA 17s and no compliance in the
drivetrain. Three independent things stop it, listed slowest to fastest to
fail:

1. **The gesture.** Lifting your thumb releases the stick, which sends a zero
   immediately plus a ~200 ms tail of zeros.
2. **The scene phase.** Anything that takes the app off screen zeroes the drive;
   actually backgrounding also sends an explicit stop. `isIdleTimerDisabled` is
   set while the app is active so the phone cannot auto-lock mid-drive.
3. **The firmware's 500 ms deadman.** `DRIVE_HOLD_MS` in `ble.c`. If drive
   packets stop arriving for any reason -- app crash, flat phone, out of range,
   a thumb through the antenna -- the robot ramps itself to a stop.

Only the third one has to work. The first two exist so the robot stops
*promptly* in the ordinary cases rather than half a second later.

**The app declares no background modes at all.** That is a safety decision, not
an oversight: a backgrounded U-BOT app physically cannot drive. It also means
the BLE link drops shortly after backgrounding and there is no state
restoration, which is the intended behaviour.

E-STOP is always in the same place and is only greyed out when there is no link
to carry it.


## Camera lifecycle

Camera capture starts when the app becomes active, including first launch and
returning from the background. Backgrounding stops capture. A pending permission
request cannot restart it after backgrounding, and failed camera setup is retried
on the next activation. Camera interruptions are shown over the preview.


## Stick response

The stick follows your finger up to the rim of its travel. Input is linear:
half travel requests half rate, and full travel requests the full configured
forward, reverse, or turn rate. There is no additional app turn cap or response
curve. Diagonal input is clamped to the unit circle; the firmware scales mixed
forward/turn commands together when needed to respect wheel speed limits.

Actual speed and acceleration are saved robot settings (`vmax_tps` and
`accel_tps2`), adjustable through `ubotctl exec set` without reflashing. For
reference, 1.0 wheel turns/s is approximately 0.675 m/s straight ahead.


## BLE

A mirror of the table in `firmware/base/README.md`, so the two can be diffed.

Advertised as the robot's name (`ubot` by default, `set name` changes it). The
advertisement carries the name plus 16-bit `0x180A` and `0x180F`; the 128-bit
service UUID is in the **scan response** only, because it does not fit in 31
bytes beside the name. The app therefore scans unfiltered and matches on either
the service UUID or the name -- `scanForPeripherals(withServices:)` filters
against the advertisement, and relying on it to see a scan-response UUID is
betting on undocumented behaviour.

    service  7B1A0000-6F4B-4C2E-9D3A-2E5F1C8A9B01
      drive    ...0001  write, write-no-rsp   4 B: i16 v, i16 w, LE, thousandths
      control  ...0002  write                 1 B: 0 stop 1 enable 2 disable
                                                   3 estop 4 clear
      status   ...0003  read, notify 5 Hz     13 B packed LE
    battery  0x180F / 0x2A19  level %, notify 1 Hz
    devinfo  0x180A          manufacturer, model, serial, fw rev, hw rev

No pairing, no bonding, no encryption. Connect and write.

Three properties of this interface shape most of the app:

- **A refused drive write still returns success.** The firmware only logs the
  refusal; nothing crosses BLE. So the app never presents your intent as the
  truth. It mirrors the web page's lock model instead -- the stick is greyed
  out, with the reason, whenever a drive would be refused. The readout under
  the pad shows the command actually in force, in real units, straight from the
  status frame -- so what is on screen is the robot's account of itself, never
  the app's. Measured wheel speeds are no longer displayed: `TelemetryPanel`
  still exists but is out of the layout, because over live camera it cost more
  screen than it earned. Put it back if a stall ever needs to be visible.
- **Control writes do report failure**, as `BLE_ATT_ERR_UNLIKELY` (0x0E). Those
  become toasts.
- **`enable` also clears latched faults**, so when the robot is faulted *and*
  disabled the single offered remedy is Enable.

Drive packets go out at 20 Hz. The web joystick uses 10 Hz over TCP, but a BLE
write-without-response can be deferred by the radio scheduler; at 20 Hz nine
consecutive packets can be lost and the deadman still holds. Every packet
carries absolute state, so a dropped one is harmless and the ticker coalesces
rather than queues. If the unacknowledged queue stays shut for a quarter of the
deadman, the ticker escalates to an acknowledged write -- the characteristic
accepts both.


## Known items and assumptions

- **Battery reads "not sensed."** The 11:1 divider on GPIO1 is not wired on this
  build, so flag bit 5 is clear and the millivolts and percent are meaningless.
  The app renders "not sensed" as a first-class state and never a scary 0%. This
  is expected, not an app bug.
- **Wheel B trips `MAGNET_LOW`** on current hardware -- both encoder magnets read
  at maximum AGC because the CAD magnet is 4x2 mm against the AS5600's reference
  6x2.5 mm. A `MAGNET` fault during testing is a known mechanical issue.
- **`s_status_subscribed` is a single global bool in `ble.c`**, set by whichever
  peer last touched a CCCD. A laptop that connects and then unsubscribes turns
  notifications off for the phone too, with the link perfectly healthy and
  CoreBluetooth reporting nothing wrong. The app detects this by absence: 1.5 s
  without a status frame locks the stick, re-arms the CCCD and falls back to
  polling the characteristic, which is `READ | NOTIFY`. Practical advice: don't
  leave a laptop connected while you're flying the phone.
- **ReplayKit records at screen resolution, not sensor resolution**, and stops
  when the app backgrounds or the screen locks. Both are inherent to in-app
  screen capture. For clips destined for social, both are fine.
- **Which way is forward** is set on the robot, not here. `sign_a`, `sign_b` and
  `a_left` are settings; the base README notes they were inferred from the CAD
  rather than confirmed on the bench. If the robot drives backwards or turns the
  wrong way, fix it with `set sign_b` / `set a_left` on the console. Do not
  "fix" it in Swift.
- **No OTA controls, log viewer, or Wi-Fi provisioning in the app.** Use
  the browser for OTA/logs and the serial console for Wi-Fi provisioning. If the phone is ever meant to replace the browser entirely,
  provisioning-over-BLE is the notable gap.


## Verified

Append to this section after each session, in the style of
`firmware/base/README.md`.

**On the bench, 2026-09-06.** `ubotctl status` against the real robot from a
Mac, with no Xcode installed. Confirmed end to end:

- Discovery. Scanning unfiltered and matching by hand finds the robot. On a
  second run `retrievePeripherals(withIdentifiers:)` reconnected with no scan
  at all -- straight to Connecting.
- Service and characteristic discovery, and a Device Information read:
  model came back `U-BOT base`.
- Status notifications at 5 Hz, decoding correctly: flags, fault byte,
  battery, both wheel velocities, and the command in force.
- Battery reports **not sensed**, exactly as the unwired divider predicts. The
  millivolts and percent are 0 and are correctly suppressed rather than shown
  as a flat battery.
- Flags at rest read `...AB.` -- motors off, no fault, no command active, both
  encoders answering, no battery. Every bit as expected.

Measurement worth keeping: at rest, **wheel A reads exactly 0.000 turns/s on
every sample while wheel B dithers between -0.014 and +0.013**. Both encoder
flags are set, so this is not a dead encoder. Velocity crosses the wire as
thousandths of a turn/s, so wheel A's noise floor is under half an LSB and
rounds to zero while wheel B's is 4 to 14 raw units. That asymmetry is
consistent with the known weak-magnet defect on wheel B: the encoder answers
and does not fault, it is just measurably noisier than A. Worth re-measuring
after the magnet is changed -- if B's noise floor drops to A's, that confirms
the diagnosis.

**Motion, wheels off the ground, same session.** The control and drive paths:

- `enable` and `disable` both came back accepted, so the acknowledged-write path
  works and its response reaches the app. The ATT 0x0E refusal branch has still
  not been seen -- nothing refused a command this session.
- Driving at `v = 0.2` produced a commanded 0.135 m/s, which is exactly
  0.2 x 0.675. The wheels tracked it at +/-0.20 turns/s against a predicted
  0.135 / 0.6754 = 0.1999. The closed loop follows the command.
- Wheel A and wheel B report opposite signs while driving straight, which is
  `sign_b = -1` doing its job, not a fault.
- Wheel B's at-rest dither disappears the moment the driver is energised and
  holds the shaft, which supports reading it as encoder noise rather than
  movement.

**Deadman, verified.** Driving at 0.135 m/s, the controlling process was
`SIGKILL`ed -- no clean shutdown, no zero packet, no disconnect handshake. The
robot stopped on its own: command-active flag cleared, both wheels at 0.000.
It stayed *enabled*, which is correct -- the deadman zeroes motion, it does not
drop EN. This is the mechanism the whole app leans on and it does what the
firmware README says it does.

**Two bugs found and fixed by running this against hardware**, neither of which
any amount of unit testing would have caught:

- `peripheralIsReady(toSendWriteWithoutResponse:)` was calling `send()`
  unconditionally, so each write refilled the transmit queue, which drained,
  which called back, which wrote again. Measured **158-224 writes per second**
  against an intended 20. The ticker now only makes good a tick it actually
  dropped, and measures **21 writes per second**.
- `ubotctl` printed its status table to a block-buffered stdout, so piping it to
  a file swallowed every row for seconds while the stderr progress lines
  appeared immediately. Now line-buffered.

Link quality worth knowing: in the first second after connecting, roughly 17 of
20 ticks are dropped for backpressure and 3 escalate to acknowledged writes --
the escape hatch doing exactly its job while the connection settles. Steady
state is about 16 written, 4 dropped, 1 escalated per second.

- The wire protocol is also covered by `ubotctl selftest` (39 checks) and
  `swift test` (23 tests), both green on the Command Line Tools toolchain
  without Xcode. That is byte-layout and lock-model coverage only -- it proves
  the codec agrees with `ble.c`, not that the robot answers.


**On the bench, 2026-09-20 (firmware 0.1.5).** The native app uses BLE,
independently of Wi-Fi provisioning. The remembered BLE peripheral on the Mac
stayed at Connecting, while fresh discovery connected and streamed status.
`BLERobotLink` now abandons an unavailable remembered peripheral after eight
seconds and scans again, ignoring callbacks from the abandoned connection.
Replaying the actual stale identifier with the rebuilt `ubotctl status`
confirmed Connecting -> Looking -> Connected and live telemetry. Motors stayed
disabled throughout. `swift build` and `ubotctl selftest` passed. The updated
iPhone app still needs to be rebuilt, installed, and verified on the phone.


**Wi-Fi app implementation, 2026-09-20.** Added the main-screen transport
selector, editable address, WebSocket transport, switching lifecycle guards,
and local-network permission configuration. The 43 package tests cover codec,
backpressure, acknowledgements/refusals, stale telemetry, and reconnect behavior.
Two iPhone controller tests cover retired callbacks and rapid transport changes;
a UI test checks selector reachability and address settings on an iPhone 16e
simulator. Simulator and physical-device builds succeeded. The signed update
was installed on the connected iPhone 16 Pro. Live Wi-Fi/rack verification and
physical-phone permission/recording checks are pending robot connectivity.
The actual URLSession WebSocket adapter also passed a localhost integration
check against a synthetic server: connection, telemetry, acknowledged control,
10 Hz drive frames with a 500 ms hold, and zero frames on release. This is not
a substitute for the outstanding live robot test.
