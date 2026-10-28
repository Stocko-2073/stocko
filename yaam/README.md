# Yet Another Actuator Model

A MuJoCo model of the SG90 micro servo, built from bench measurements. The target: on
motions the model wasn't fitted to, sim-vs-real error no bigger than one real servo's
run-to-run scatter, plus randomization ranges that cover the spread between units.

- `firmware/sg90_bench/`: XIAO RP2040 firmware. It generates servo pulses and streams the
  encoder angle, supply current and voltage, and the servo's internal motor and pot
  signals, all timestamped on one clock.
- `src/yaam/bench/`: the host side: protocol, serial link, experiment schedules, recorder,
  `yaam-bench` CLI.
- `cad/sg90_bench.scad`: the printed bench: frame with the index plate, pendulum arm with
  the magnet stalk, the tower that holds the AS5600, and mass carriers.
- `board/`: the stripboard for the electronics, with its own `README.md` and layout tests.
- `WIRING.md`: power, pins, the servo taps and their dividers.
- `data/<unit>/`: recordings, one `.npz` per run (routed to Git LFS) with a `.json` of its
  metadata alongside.

## Setup

```sh
uv sync
uv run pytest
arduino-cli compile --upload -p /dev/cu.usbmodem2101 firmware/sg90_bench
uv run yaam-bench selftest
```

The selftest checks:
- AS5600: present, filter configured, magnet strength.
- INA219: present and configured.
- The tap voltages.
- The frame period and the pulse width, both measured on the D9 pin itself.
- Tick overruns and USB drops.

## Bring-up (E0)

1. With the servo unplugged, run `selftest`. The motor and wiper taps read near their
   no-signal values. Fix anything marked FAIL first.
2. **Before the servo is connected**, set the adjustable buck to 5.00 V.
3. Plug in the servo, run `yaam-bench hold 1500`, then `selftest` again. Note what the
   motor taps read at rest: about +1.65 V each means the H-bridge lets the motor float,
   about 0 V means it brakes.
4. **Find the end stops before the first sweep.** Step `hold` outward (1200, 900, 700, 600,
   then the same upward to 2400) and listen. If the servo strains or buzzes at either end,
   keep the schedules inside that with `--lo-us` / `--hi-us`.
5. Mount the horn so that 1500 µs leaves the arm hanging straight down.

## Experiments

Calibrate the encoder first, servo unpowered, using the index plate (E1):

```sh
uv run yaam-bench index-cal --unit S01
```

Then the runs (E2–E6). Each `run` plays its schedule `--repeat` times (default 2) with a rest
between, and saves every repeat:

```sh
uv run yaam-bench run static-map    --unit S01 --load "arm only"
uv run yaam-bench run static-map    --unit S01 --load "arm + 50g @ 70mm"
uv run yaam-bench run steps         --unit S01 --load "arm + 50g @ 70mm" --raw
uv run yaam-bench run sines         --unit S01 --load "arm + 50g @ 70mm"
uv run yaam-bench run chirp         --unit S01 --load "arm + 50g @ 70mm"
uv run yaam-bench run multisine     --unit S01 --load "arm + 50g @ 70mm"
uv run yaam-bench run up-and-down   --unit S01 --load "arm + 150g @ 70mm"
uv run yaam-bench run lift-and-drop --unit S01 --load "arm + 150g @ 70mm"
uv run yaam-bench run hold          --unit S01 --load "arm + 150g @ 70mm"
uv run yaam-bench run steps --unit S01 --load "arm + 50g @ 70mm" --supply-v 6.0   # after setting the buck
```

- `--dry-run` prints a schedule's length and pulse range without moving anything.
- `--raw` adds the 20 kS/s motor and wiper samples (about 160 kB/s), needed to see the
  drive bursts.
- `--reference` runs a short drift check before each repeat.
- `--frame-us 10000` runs at 100 Hz.
- Describe `--load` exactly: the masses and radii you weighed. The model is built from it.

Until the static map is fitted, schedules use the nominal SG90 pulse map: 1500 µs at
center, 11.1 µs per degree, within 600–2400 µs.

`yaam-bench monitor` prints live readings; `yaam-bench show data/S01/<file>.npz`
summarizes a recording.
