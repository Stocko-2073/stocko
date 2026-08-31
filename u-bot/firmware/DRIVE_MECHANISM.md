# Drive mechanism

One drive axis, end to end: NEMA 17 -> TMC2209 -> 12:40 bevel pair -> output
shaft -> wheel, with an AS5600 magnetic encoder reading the output shaft
directly. Two of these, one per wheel, differential drive.

The encoder is on the output side of the reduction, so it sees the wheel and
not the motor. Everything the loop knows about where the robot actually is
comes from there; the step count is only ever what the motor was *asked* to do.

Numbers below are marked by where they come from. Measured ones were taken on
the bench and are worth more than the nominal ones.


## The chain

| | value | source |
|---|---|---|
| motor | NEMA 17, 1.8 deg | 200 full steps/rev |
| microstep | 1/8 | MS1=MS2=0; MRES=5 read back over UART |
| interpolation | to 256 | `intpol=1`, TMC2209 reset default |
| bevel pair | 12:40, module 5 | `drive_teeth`/`wheel_teeth`, u-bot.scad |
| reduction | 3.333333 | 40/12 |
| encoder | AS5600, 12-bit | 4096 counts/rev, output shaft |

Derived, and all of it exact — no fudge factors anywhere in this drivetrain:

    microsteps per motor rev     200 x 8            = 1600
    microsteps per output rev    1600 x 40/12       = 5333.333
    encoder counts per output    4096
    steps per count              5333.333 / 4096    = 1.3020833

Calibration on 2026-08-21 measured **1.302083 steps/count, 0.000% off nominal
over 3 output turns**. The ratio is exactly 1/8 microstep and exactly 12:40.
Calibration probes whole output revolutions on purpose — see the encoder note
below.


## Wheel

The wheel is the 40-tooth bevel gear with a treaded rim on it. `wheel()` in
u-bot.scad puts 20 staggered lugs at `r + zz` = **107.5 mm, so 215 mm diameter**
on the tread tips. That is the rolling surface.

Two traps in that module: `id=208` and `od=218` are declared at the top and
never used, so they are not the answer; and the `d=195` disc and `d=205` rim are
structure, not tread.

215 mm is good to about a millimetre, which is far better than this robot
deserves. It runs on grass and dirt, where slip, sinkage and tread digging all
swamp the geometry — effective rolling radius out there is a soft number, not a
CAD number. Odometry will need to be earned from the encoders, an IMU and
probably wheel-slip rejection, not from a precise diameter. Do not spend effort
sharpening this constant.

    circumference           pi x 215        = 675.4 mm
    per encoder count       675.4 / 4096    = 0.165 mm
    per microstep           675.4 / 5333.3  = 0.127 mm

Sub-millimetre either way, so quantisation is never the limiting factor
outdoors.


## Measured limits (2026-08-21)

| | output turns/s | m/s |
|---|---|---|
| clean | 1.0 | 0.68 |
| marginal | 2.0 | 1.35 |
| sheds steps | 2.76 | 1.86 |

`VMAX_LIMIT` is set to 2.0 turns/s and `ACCEL_LIMIT` to 20 turns/s^2, so a full
0 -> VMAX ramp takes 100 ms. Peak step rate at VMAX is 10667 steps/s.

Encoder character, same session: rock steady standing still (0 counts p-p), but
**~20 counts of angle-dependent nonlinearity around a turn** — about 3.3 mm at
the rim. It is systematic, not noise, which is why calibration has to span whole
output revolutions to be honest, and why chasing position corrections finer than
a few millimetres is chasing the sensor rather than the robot.


## UART control (2026-08-30)

Replaces STEP/DIR. The driver runs its own step generator from the `VACTUAL`
velocity register and the MCU only updates a setpoint.

**Wiring.** `D6/GPIO16` (TX) --[1k]-- `D7/GPIO17` (RX), and one wire from the
D7 side to **module pin 4, silkscreened `RX`**. On the BTT TMC2209 V1.3, pin 5
(`TX`) is an unpopulated alternate — the selection resistor has to be moved to
use it. Both header pins are marked `PDN` on the card that ships with the
module, which is how an afternoon gets lost.

**Address 0**, from MS1=MS2=0. A second driver needs MS1 high for address 1,
which in pin mode would also switch it to 1/2 microstep — so set
`mstep_reg_select=1` and put MRES in `CHOPCONF`, making the pins address-only.

**Baud: 250000 or 500000. Never below 115200.** At 57600 reads work but writes
fail outright, 0/20. The discriminator is datagram duration against the driver's
receive window: an 8-byte write is 1.39 ms at 57600 and dies, 0.69 ms at 115200
and lives; a 4-byte read is 0.69 ms at 57600 and lives. Anything under about
700 us gets through.

**The first datagram after `Serial1.begin()` is always lost** — reconfiguring
the pad glitches the line and desyncs the driver's receiver. Send a throwaway
read at startup.

No inter-datagram pacing is needed: writes issued the instant a read reply lands
were accepted 20/20. A fire-and-forget write costs **~118 us**, flat from
115200 to 500000, because the cost is draining the 8 echo bytes and not wire
time. Two wheels at 200 Hz is 4.7% of the CPU.

`VACTUAL` is signed 24-bit, one LSB = f_clk/2^24 = 0.715 steps/s:

    VACTUAL = output_turns_per_s x 7455

0.09 mm/s per LSB at the rim, so quantisation is irrelevant. **The internal
oscillator is only good to about +/-10%**, though, so commanded velocity is not
trustworthy open loop — the encoder loop absorbs it, but never use `VACTUAL` as
a dead-reckoning source.

Wheel A's driver measured **1.0158** on 2026-08-30: 1.6% fast, far inside the
allowance. It is baked into `test_servo.ino` as `CLOCK_GAIN`, but it belongs to
that individual chip -- wheel B's driver will need its own, and it drifts with
temperature. `c` measures it and prints the number to paste in.

**Control rate: 200 Hz.** 1 kHz was inherited from STEP/DIR and is not needed
now the driver generates its own steps. 200 Hz gives 20 updates across the
acceleration ramp, and one tick at full speed is 3.4 mm — already level with the
encoder's own 3.3 mm nonlinearity.


## Velocity mode, measured 2026-08-30

The port off STEP/DIR, checked on the bench against the 2026-08-21 numbers.
Calibration, 3 output turns out and back at 1500 steps/s commanded:

    +12288 counts in 10.501 s          exactly 3.000 output turns
    clock gain 1.0158                  asked 1500 steps/s, got 1524
    return leg -12288 vs +12288        residual +0 counts, no steps lost
    shaft polarity normal              agrees with the old DIR_PLUS_LEVEL=LOW

Closed-loop step response at the default tuning (kp 16, vmax 1.0, accel 8):

| | peak slip | peak vel | peak rate | settled | final err |
|---|---|---|---|---|---|
| goto 0.5 turns | 26 steps | 1.021 turns/s | 5333 sps | 740 ms | -3 counts |
| back to 0 | 37 steps | 1.023 turns/s | 5333 sps | 760 ms | +3 counts |

Peak rate matches 1.0 turns/s exactly. Slip against the 29 measured under
STEP/DIR: 26 out, 37 back. The return leg reads higher because slip now carries
clock error as well as real divergence, and both sit far below the 200 limit.

The +0 round-trip residual is the number that matters. It is the one figure
velocity mode can still produce that open-loop step counting used to give, and
it says the motor did exactly what it was told in both directions.


## EN is the killswitch, and it is fail-safe

`ENN` is active low and gates the power stage in hardware. It does not go
through the UART and does not depend on any register, so it still works when the
bus is down, the firmware is wedged, or the MCU is held in reset.

Measured on 2026-08-30 by reading `IOIN` back over UART while driving D0:

    D0 driven HIGH  -> ENN=1, disabled
    D0 driven LOW   -> ENN=0, enabled
    D0 released     -> ENN=1, disabled

It floats high. So MCU reset, watchdog reset, and a broken EN wire all fail to
the safe state on their own. Keep this pin hardwired; do not be tempted to save
it by disabling the driver with `toff=0` over the bus, which fails exactly when
you need it.

**This matters more under UART than it did under STEP/DIR.** Before, a hung MCU
stopped the robot for free: no pulses, no motion. Now the driver keeps stepping
from `VACTUAL` whether or not anyone is talking to it, so EN is the only thing
that stops a runaway.

Two rules that follow:

- **Zero `VACTUAL` before enabling.** It survives an MCU reset even though the
  power stage was off, so re-enabling EN without clearing it first resumes the
  pre-reset speed instantly.
- **Park EN high before anything else in `setup()`,** the way `test_servo.ino`
  already does, so the driver is disabled from the first instruction.


## Free-wheeling and recovery (not built yet)

EN high switches the power stage off, so the coils go open and the wheels free-
wheel. Detent torque is all that is left -- order 0.02-0.04 Nm at the motor, so
about 1 N at the contact patch through the reduction, against roughly 17 N of
downhill pull for a 10 kg robot on a 10 degree slope. It will roll. The
killswitch stops the robot driving itself away; it does not stop gravity.

Recovering from a reset while moving is future work, but two facts belong here
before anyone designs it:

- **`VACTUAL` is write-only.** There is no reading back what the driver was
  doing. Use the encoders instead -- and they are the better trigger anyway,
  because a robot rolling downhill after a reset may never have been commanded
  to move at all. "Are the wheels turning" covers strictly more than "was I
  driving".
- **Synchronise before decelerating.** Enabling with `VACTUAL = 0` against a
  turning wheel just skips steps until the motor wins, which is violent and
  throws away position. Read the wheel velocity, set `VACTUAL` to match it,
  enable, then ramp to zero at `ACCEL_LIMIT` -- both wheels on the same ramp, or
  the robot steers itself while braking.

Nothing in software covers the reset window itself, a few hundred ms of ESP32
boot with the wheels free. If that turns out to matter in the yard, the hardware
answer is dynamic braking: a relay held open while powered that shorts the motor
phases when it is not. Shorted windings resist rotation strongly, but the effect
is speed-dependent -- it caps runaway speed rather than holding position. A
parking brake on a slope needs a mechanical brake or a self-locking drive, which
a 12:40 bevel pair is not.


## Pins, XIAO ESP32-C6

| pin | now | under UART |
|---|---|---|
| D0 / GPIO0 | EN, driver A | EN, both drivers |
| D1 / GPIO1 | STEP | free |
| D2 / GPIO2 | DIR | free |
| D4 / GPIO22 | encoder A SDA | unchanged |
| D5 / GPIO23 | encoder A SCL | unchanged |
| D6 / GPIO16 | — | UART TX, shared |
| D7 / GPIO17 | — | UART RX, shared |
| D8 / GPIO19 | encoder B SCL | unchanged |
| D9 / GPIO20 | encoder B SDA | unchanged |

Wheel B's encoder is on a bit-banged bus because the AS5600's address is fixed
at 0x36 and the C6's second I2C controller is LP_I2C, which only lives on
GPIO6/7 — pins the XIAO does not break out. See `AS5600Soft.h`.

Pin economy is the real argument for UART here. Two drivers on STEP/DIR would
need six pins and leave exactly one spare for lights, IMU and bumpers. Sharing
one bus needs two, and gives D1/D2 back.
