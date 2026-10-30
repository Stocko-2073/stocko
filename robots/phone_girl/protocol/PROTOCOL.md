# phone_girl link, protocol 1

The phone (an iPhone 16 Pro, the robot's head) runs the policy. A microcontroller
in the backpack drives the 17 Dynamixel XL330-M288-T servos. This document is the
contract between the two, and with the simulator, which models exactly this
timing and quantization. The firmware is assumed to be an ESP32-S3.

Two transports carry the same frames:

- **USB-C NCM, the default.** Ethernet over USB Full Speed, 12 Mbps at best.
  The tick is 10 ms.
- **BLE, the option.** NimBLE on the ESP32-S3. The tick is one 15 ms connection
  interval.

The code that defines the frames:

- [`phone_girl_link.h`](phone_girl_link.h) defines the frames in C.
- [`sim/src/phone_girl/protocol.py`](../sim/src/phone_girl/protocol.py) is the
  reference implementation. Its golden frames are checked against the C header
  by `sim/tests/test_protocol.py`.

## Roles

| | Phone | MCU |
| --- | --- | --- |
| Bus | none | Dynamixel Protocol 2.0 master, half duplex |
| Clock for the control tick | follows the MCU | owns it |
| USB | host | device with a CDC-NCM network function |
| BLE | central | peripheral, advertises as `phone_girl` |

## The control tick

The steps are the same over either transport:

1. **Read.** The MCU Fast Sync Reads Present PWM, Current, Velocity and Position
   (addresses 124–135, 12 bytes per servo). It also does one slow Read, round
   robin: the temperature, hardware error and input voltage of one servo.
2. **State.** It sends the state frame.
3. **Policy.** The app receives the frame, takes the newest CoreMotion
   `deviceMotion` sample, runs the policy and sends the command. The policy
   takes well under 1 ms on the CPU for these networks.
4. **Apply.** On arrival the MCU checks the version, length and sequence, clamps
   the goals to the soft limits, and immediately Sync Writes Goal Position (116).
   It does not wait for the next tick. It records
   `command_latency = now − read_us(state_seq)`.

The transports differ in when the state and the command can travel.

## USB-C NCM (default)

The ESP32-S3's USB-OTG port runs TinyUSB's CDC-NCM device class with lwIP. The
phone is the USB host and sees a wired network interface. The MCU is
self-powered from the robot's pack and doesn't drive VBUS.

- **Addressing.** The MCU runs a DHCP server on 192.168.47.0/30. The MCU is .1,
  and it leases .2 to the phone.
- **Frames.** Each frame is one UDP datagram. The port says which frame it is,
  as the characteristic does over BLE:

  | Port | Frame | Direction |
  | --- | --- | --- |
  | 47001 | state | MCU to phone, every tick |
  | 47002 | command | phone to MCU, every tick |
  | 47003 | control | phone to MCU; replies go back to the sender |
  | 47004 | info | an empty datagram gets the JSON back |
  | 47005 | capture | MCU to phone |

- **Loss.** USB retries bulk transfers in hardware, so datagrams are rarely
  lost. Nothing relies on that:
  - Commands carry absolute goals, so a lost one needs no repair.
  - The app resends a control request that gets no reply within 100 ms, with the
    same `request_id`.
  - The MCU answers a repeated `request_id` with its last reply rather than
    acting twice.

**The tick.** The tick is T = 10 ms, so the policy runs at 100 Hz, CoreMotion's
rate. The MCU reads at the start of the tick and sends the state as soon as the
read finishes. The command comes back within the same tick. No phase lock is
needed, because the MCU's timer is the tick.

```
 MCU    read servos   send state k                 apply command k
         |<-- r -->|--------->                     | w |
 phone                  read CoreMotion,
                        run policy, send command ------>
```

**Latency budget.** These are design targets: measure them with
`command_latency`, then update the simulator's `LinkCfg`.

| Step | Time |
| --- | --- |
| Fast Sync Read, 17 servos at 3 Mbps | ~1.2 ms |
| State to the app over USB | ~0.3–1.5 ms |
| CoreMotion sample and policy | ~0.5–1.5 ms |
| Command to the MCU over USB | ~0.3–1.5 ms |
| Command to goals written and picked up | 0.5–3 ms |
| **Read to goals applied** | **~3–9 ms**, inside the tick |

**Stalls.** None are known over USB, and none are modelled until measurements
show some.

## BLE (option)

Advertise the name plus the 128-bit service UUID in the scan response; it does
not fit beside the name in 31 bytes. The app scans unfiltered and matches either.

| Characteristic | UUID | Properties | Content |
| --- | --- | --- | --- |
| service | `a7470000-77c3-4dbd-b507-83058991dbc6` | | |
| state | `a7470001-…` | notify | 154-byte state, every tick |
| command | `a7470002-…` | write without response | 40-byte goals, every tick |
| control | `a7470003-…` | write, notify | requests and their replies |
| info | `a7470004-…` | read | JSON, see below |
| capture | `a7470005-…` | notify | high-rate samples for identification |

The remaining UUIDs share the service's suffix, `-77c3-4dbd-b507-83058991dbc6`.

After connecting, the MCU sets up the link:

- It **requests connection parameters**: interval min = max = 15 ms, latency 0, and
  a 6 s supervision timeout. Apple's Accessory Design Guidelines (R31, §58.6) allow
  15 ms as the minimum, with min = max = 15. iOS ignores the Peripheral Preferred
  Connection Parameters characteristic, so the MCU must send an L2CAP update
  request. Anything other than 15 ms is reported in `info` and refused for torque
  on; see below.
- iOS starts the switch to the **2M PHY** itself.
- Do the link-layer **data length update** (251 bytes) before the MTU exchange.
  The app checks `maximumWriteValueLength(for: .withoutResponse)` and needs an ATT
  MTU of at least 157 for the state notification.
- There is no pairing. Anyone in range can connect, as with U-BOT. Add LE Secure
  Connections before this leaves the bench.

**The tick.** One tick is one connection interval, T = 15 ms, so the policy runs
at 66.7 Hz. The MCU reads just before connection event n and queues the state
frame, which leaves at event n. iOS sends the command at event n+1, or at event
n+2 if a packet is lost.

```
 MCU   read servos   notify state k          apply command k
        |<-- r -->|    :                          | w |
 BLE ------------- event n --------------- event n+1 --------- event n+2
 phone              :  receive, read CoreMotion,   :
                    :  run policy, write command   :
```

**Phase lock.** NimBLE on the ESP32-S3 has no connection-event callback. But the
phone's commands arrive at connection events, one interval apart. The MCU
low-pass filters their arrival phase modulo T and schedules each read to finish
about 1.5 ms before the next event. Until commands flow, it free-runs at T.

**Latency budget.** These are design targets: measure them with
`command_latency`, then update the simulator's `LinkCfg`.

| Step | Time |
| --- | --- |
| Fast Sync Read, 17 servos at 3 Mbps | ~1.2 ms |
| Wait for the connection event, once phase locked | ~0.5–1.5 ms |
| State to command, one interval | 15 ms |
| Command to goals written and picked up | 0.5–3 ms |
| **Read to goals applied** | **~16–19 ms**; one more interval per lost packet |

**Stalls.** iOS has been seen to pause BLE callbacks for about 250 ms every few
seconds. A stall shows as a gap in `command_seq`. During one the MCU keeps
writing the last goals; see Safety.

## Frames

All frames are little-endian and packed. Positions are servo ticks minus 2048;
calibration makes 2048 the home pose.

### State: MCU to phone, 154 bytes, every tick

| Offset | Type | Field | |
| --- | --- | --- | --- |
| 0 | u8 | version | 1 |
| 1 | u8 | flags | bit 0 torque on, 1 command fresh, 2 holding, 3 deadman, 4 servo error, 5 low voltage |
| 2 | u16 | seq | the tick count |
| 4 | u32 | read_us | MCU clock when the read began |
| 8 | u16 | command_seq | last command applied |
| 10 | u16 | command_latency | 0.1 ms, from reading the state it answered to applying it; 0xFFFF if unknown |
| 12 | u16 | bus_mv | supply voltage, from the MCU's ADC or the round-robin servo |
| 14 | u8 | slot | servo whose slow fields follow |
| 15 | i8 | temperature_c | |
| 16 | u8 | hardware_error | Hardware Error Status (70) |
| 17 | u8 | bus_errors | failed reads since the last state, saturating |
| 18 + 8i | i16 ×4 | servo i | position (ticks − 2048), velocity (0.229 rpm), current (mA), PWM (0.113 %, 885 = full) |

The XL330 measures current at its power input, not at the motor, so `current`
says little about torque. The policy instead estimates torque from PWM, voltage
and velocity with the BAM motor model; see the simulator README.

### Command: phone to MCU, 40 bytes, every tick

| Offset | Type | Field | |
| --- | --- | --- | --- |
| 0 | u8 | version | 1 |
| 1 | u8 | flags | bit 0 hold: keep the current goals (the app is pausing on purpose) |
| 2 | u16 | seq | |
| 4 | u16 | state_seq | the state the policy acted on |
| 6 + 2i | i16 | goal i | ticks − 2048 |

A command whose `seq` is not newer than the last applied one is ignored; it is
a duplicate or out of order. Every command carries absolute goals, so a lost
one needs no repair.

### Control: phone to MCU

A request is `opcode, request_id, payload`. Over BLE it is a write with
response. The reply comes back on the same characteristic or port, as
`opcode | 0x80, request_id, status, payload`. Status is 0 ok, 1 bad request,
2 refused, 3 bus error, 4 busy.

| Opcode | Request payload | Reply payload | Notes |
| --- | --- | --- | --- |
| 1 torque | u32 slot mask | | 0 turns all off. Refused unless the tick is the transport's (10 ms over USB, 15 ms over BLE) and soft limits are set |
| 2 gain | u16 Position P Gain | | default 400; the simulator's `kp` must match |
| 3 limits | u16 current limit mA, u16 PWM limit | | torque off only (EEPROM) |
| 4 calibrate home | | 17 × i32 Homing Offset | torque off, robot held in the home pose |
| 5 safety | u16 hold_ms, u8 after (0 torque off, 1 freeze), u16 freeze_ms | | |
| 6 reboot | u32 slot mask | | clears servo errors |
| 7 capture | u32 slot mask, u16 rate Hz, u16 duration ms | | streams capture frames |
| 8 soft limits | 17 × (i16 low, i16 high) | | also written to Min/Max Position Limit as a backstop |

### Info: JSON

Over BLE the app reads it. Over USB it is the reply to an empty datagram on the
info port.

```json
{"protocol": 1, "firmware": "0.1.0", "transport": "usb-ncm", "interval_ms": 10, "baud": 3000000,
 "servos": [{"slot": 0, "id": 1, "model": 1200, "firmware": 46}, ...],
 "soft_limits_set": true, "calibrated": true}
```

`transport` is `usb-ncm` or `ble`.

### Capture: MCU to phone

The header is u8 version, u8 slot, u8 count, u16 seq, u32 start_us and
u16 period_us. Then come `count` samples of i16 goal, position, velocity,
current and PWM, at up to ~1 kHz for one or two servos. These logs feed BAM's
identification (`bam.fit`) and the replay test in the simulator.

## Servo setup

The MCU writes this at boot, and the simulator assumes it.

| Register | Value | Why |
| --- | --- | --- |
| ID | slot + 1 | Slot order is the simulator's joint order; the joint names are in every exported policy |
| Baud Rate (8) | 3 Mbps, or 4 Mbps if the wiring is clean | read time |
| Return Delay Time (9) | 0 | the default is 500 µs per servo |
| Operating Mode (11) | 3, position | what BAM models |
| Drive Mode (10) | 0 | CCW from the horn is positive, as in the simulator |
| Position P Gain (84) | 400 | must equal the simulator's `kp` |
| Position I, D Gain (82, 80) | 0 | |
| Profile Acceleration, Velocity (108, 112) | 0 | BAM models the raw P loop, without profiles |
| PWM Limit (36) | 885 | |
| Current Limit (38) | 1750 mA | BAM's limiter |
| Bus Watchdog (98) | 5 (100 ms) | the servos stop if the MCU hangs |
| Max Voltage Limit (32) | 70 (7.0 V), the highest allowed | a full 2S pack still flags bit 0; see Safety |
| Shutdown (63) | 52, the default | overheating, electrical shock and overload stop a servo; voltage doesn't |
| Homing Offset (20) | from calibration | home reads 2048 |
| Min/Max Position Limit (52, 48) | soft limits | backstop for the MCU's clamp |

Fast Sync Read needs servo firmware v46 or newer.

## Calibration

The home pose is the CAD's `default_pose`, which is the simulator's qpos0.

1. Hold the robot in the home pose (a printed jig is best) with torque off.
2. Send control 4. The MCU sets each Homing Offset so Present Position reads 2048,
   then reads it back.
3. Then for every joint: joint angle − home = (Present Position − 2048) × 2π/4096.
   No per-joint sign or offset tables are needed.

## Safety

- **Deadman.** After `hold_ms` without a fresh command (default 300 ms, longer
  than an iOS BLE stall) the MCU sets `holding`. Then it does the `after` behaviour:
  freeze for `freeze_ms` (default 2 s), then torque off; or torque off at once.
  `holding` also appears for shorter gaps.
- **Limits.** Goals are clamped to the soft limits by the MCU, and by the servos'
  Min/Max Position Limit as a backstop. The policy's actions are clipped to the
  same limits in the simulator.
- **Watchdogs.** The Bus Watchdog stops the servos if the MCU hangs. If the phone
  vanishes, BLE's supervision timeout ends the connection, and over USB
  TinyUSB's unmount callback does. The deadman covers an app that goes silent.
- **App.** The app declares no background modes, so leaving it drops the link
  and the deadman takes over. A torque-off control is always one tap away.
- **Voltage.** Two 18650s in series feed the servos directly: 6.6–8.4 V, above
  the XL330's 6.0 V rating, as BAM's XL330 identification ran (7.5 V). The `low
  voltage` flag is set below 6.4 V, 3.2 V a cell under load. Max Voltage Limit (32) tops out
  at 7.0 V, so a fuller pack sets bit 0, input voltage, of every servo's Hardware
  Error Status. That is expected: mask bit 0 when setting `servo error`, and keep
  it out of Shutdown (63); the default, 52, already leaves it out.

## What the simulator assumes

`link.LinkCfg()` is the USB column, and `link.ble_link()` the BLE one. Every
exported policy names the link it was trained over (`deploy.py`). The app
refuses to run it over the other transport.

| Behaviour here | USB-C NCM | BLE | Simulator (`sim/src/phone_girl`) |
| --- | --- | --- | --- |
| Tick | 10 ms | 15 ms | `LinkCfg.interval_s`; 4 or 6 physics steps of 2.5 ms |
| Read before the state leaves | 0.5–1.5 ms | 0.5–4 ms | `LinkCfg.read_s`: telemetry age |
| State leaving to command arriving | 1.5–5 ms | one interval | `LinkCfg.turnaround_s` |
| Command to goals picked up | 0.5–3 ms | 0.5–3 ms | `LinkCfg.write_s` |
| Late commands | none | 3%, one more interval | `LinkCfg.late_probability`, `late_s` |
| Stalls: the last goals are held | none until measured | 0.05/s, 50–250 ms each | `LinkCfg.stall_rate_hz`, `stall_s`; `Xl330Actuator.stall` |

| Behaviour here, either transport | Simulator (`sim/src/phone_girl`) |
| --- | --- |
| Ticks − 2048, 0.229 rpm, mA, 0.113 % | `xl330.TICK`, `VELOCITY_LSB`, `CURRENT_LSB`, `PWM_LIMIT` |
| Current measured at the servo's input | `Xl330ActuatorCfg.current_sensing = "input"` |
| Position P Gain 400, no profiles | `Xl330ActuatorCfg.kp` |

When the hardware disagrees with these tables, change the hardware or the
simulator, then change the tables.
