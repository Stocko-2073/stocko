# SG90 bench board

Stripboard for the bench electronics: XIAO RP2040, the servo taps' dividers, INA219,
HX711 lead, TMC2209 and the power inputs. **38 × 30 holes** (about 97 × 76 mm), horizontal
copper strips, coordinates from the component side. Designed with
[stripboard](https://github.com/Stocko-2073/stripboard-py).

```sh
uv sync
uv run bench_board.py            # FRONT/BACK/DESIGN build sheet + silkscreen
uv run bench_board.py --preview  # DESIGN view only, for iterating
uv run watch.py                  # rebuild and preview on every save
uv run python -m unittest test_layout
```

The router places the signal jumpers and every cut. A solve takes several minutes, so
`bench_board.py` saves it in `bench_board_route.json` and reuses it until a part or net
changes. Text and labels don't count as changes, so cosmetic edits rebuild in seconds.
Commit the JSON with the board so a fresh checkout builds without solving.

`test_layout.py` walks the routed copper with the library's flood-fill and checks:

- the rails, and that they stay apart;
- the servo power path through the INA219 shunt;
- the tap dividers, I2C, the one-wire UART, EN, the driver straps, the motor phases, the
  HX711 lead and the servo signal;
- that the firmware's pin constants and ADC inputs still match the pads this board
  wires.

A failure is a layout bug to fix in `bench_board.py`, not a test to update.

## What goes where

| Part | Notes |
| --- | --- |
| XIAO | Socketed. USB at the top edge. Powered by USB only; its 5V pad stays unconnected. |
| TAPS (GND, A, B, W) | The tap wires from the servo, each with its series resistor at the servo end (20k on A and B, 1M on W). See ../WIRING.md. |
| R1–R5, C1–C3 | Tap dividers between the 3V3 rail (row 1) and the GND rail (row 2). C1–C3 are 1 nF ceramics; ignore the + the footprint draws on them. |
| ENC (SDA, SCL, GND, 3V3) | Lead to the AS5600 board on the bench tower. **Not U-BOT's order**: the pins line up with the D4/D5 strips. R6/R7 are the 4.7k I2C pull-ups. |
| HX711 (GND, 3V3, DT, —, SCK) | Five positions, the fourth left empty as a key. |
| INA219 | Socket for the breakout, in the order of `INA219_PINS`. Check your module before soldering the socket: clones differ. |
| SERVO (SIG, V+, GND) | The servo's own plug: orange, red, brown. R10 (220R) is in series with the signal. |
| 5V IN | From the adjustable buck. C4 is 470 µF, ahead of the shunt. |
| 12V IN, TMC2209, MOT | The backdrive stage. C5 is 100 µF on VM, R8 holds EN high, R9 is the UART's 1k. MOT is U-BOT's R/B/G/K reordered K/G/R/B to sit on the coil strips; the coils stay paired, so a U-BOT motor lead still works (the direction may flip). |
| L1–L12 | Hand-placed supply links: GND in black, 3V3 in yellow. |
