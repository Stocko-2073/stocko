# SG90 bench wiring

Everything below matches `firmware/sg90_bench` and the unit conversions in
`src/yaam/bench/units.py`. If you change a resistor, change it there too.

The stripboard in `board/` carries all of it: the dividers, pull-ups, series resistors
and capacitors, with sockets for the XIAO, INA219 and TMC2209 and headers for the
cables. `board/test_layout.py` checks its copper against this document and the
firmware. Part numbers below (R1, C4, …) are the board's.

## Power

```
12 V wall wart ─┬─────────────────────────────── TMC2209 VM (+100 µF)      [M4, later]
                │
                └─ adjustable buck ── 470 µF ── INA219 Vin+ ─ shunt ─ Vin− ── servo red
                   set to 5.00 V       ║                                      servo brown ─┐
                   BEFORE the servo    ║                                                   │
                   is connected        ╚══════════════ star ground at the buck ════════════┘
                                                         │
XIAO RP2040 ── USB to the Mac              XIAO GND ─────┘
```

- The 470 µF goes at the buck output, **before** the INA219, so the shunt sees the servo's
  own current and not the capacitor's.
- Keep the INA219 → servo leads short. The INA219 measures its bus voltage at Vin−, so the
  voltage it reports is the servo's (less those few centimetres of wire).
- The XIAO is powered by USB only. Never connect the 5 V servo supply to the XIAO's 5V or
  3V3 pins.
- Check that the INA219 shunt is marked R100 (0.1 Ω); the firmware assumes it.

## XIAO RP2040 pins

| Pin | Goes to |
| --- | --- |
| D0 / A0 | motor tap A (through the divider below) |
| D1 / A1 | motor tap B (through the divider below) |
| D2 / A2 | pot wiper tap (through the divider below) |
| D3 | TMC2209 EN, pulled up by R8 (driver off until the firmware drives it) |
| D4 (SDA), D5 (SCL) | AS5600 and INA219, both on this one bus |
| D6 (TX) | 1k (R9) to the TMC2209's PDN line |
| D7 (RX) | the TMC2209's PDN line |
| D8 | HX711 SCK |
| D9 | 220 Ω (R10) → servo signal (orange) |
| D10 | HX711 DT |
| 3V3 | AS5600 VCC, INA219 VCC, HX711 VCC, TMC2209 VIO |
| GND | star ground, tap dividers, sensor grounds |

The board has 4.7k I2C pull-ups (R6, R7). The breakouts' own pull-ups, if any, simply sit
in parallel with them.

The AS5600 lead plugs into the board's ENC header, ordered SDA, SCL, GND, 3V3 so its pins
sit on the D4/D5 strips. That is not U-BOT's order, so make a lead for it.

## The servo taps

### Find the pads (multimeter, servo unpowered)

From the photo of your open servo:

- **Motor:** the two white wires run from the motor's end cap (marked "+") to the two pads
  on the right edge of the board.
- **Pot:** the three pads in a column between the chip and those motor pads; the middle,
  round one should be the wiper.

Confirm before soldering:

1. The top and bottom pads of the column read a fixed few kΩ, whatever the shaft angle.
2. The middle pad to either end changes smoothly as you turn the output by hand.
3. The two motor pads read a few ohms.

Then power the servo at 5 V with a 1500 µs signal (`yaam-bench hold 1500`) and measure the
voltage on each pot end pad against GND. If either end is above 6.6 V, or the wiper ever
goes above it, tell me before connecting the wiper tap.

### Solder

- Thin wire: 30 AWG wire-wrap or thin silicone. Tack it onto the existing solder joints
  with a little flux and a quick touch. The pot body sits right under its pads.
- Route the wires out through the cable notch; glue strain relief to the outside of the
  case, not to the board.
- Put the series resistor **at the servo end**, in heat-shrink, so the long wire hangs off the
  resistor rather than the servo's own node:
  - each motor tap: 20 kΩ
  - wiper tap: 1 MΩ (keeps the wire's capacitance off the wiper; the 1 MΩ + 1 MΩ divider
    shifts the servo's own position reading by only about 0.1°)
- Optionally run a fourth wire from the servo's GND pad, twisted with the wiper wire.

### Dividers at the XIAO end

On the board: R1, R2 and C1 for tap A; R3, R4 and C2 for tap B; R5 and C3 for the wiper.

Motor tap A → A0 and motor tap B → A1, each identical:

```
from the servo ── 20k (at the servo) ──┬── A0 (or A1)
                                       ├── 20k ── 3V3
                                       ├── 20k ── GND
                                       └── 1 nF ── GND
```

The pin reads (V_tap + 3.3) / 3. That covers −3.3 to +6.6 V at the motor terminal, so a
floating motor's back-EMF, which can swing either way, stays readable.

Pot wiper → A2:

```
from the servo ── 1M (at the servo) ──┬── A2
                                      ├── 1M ── GND
                                      └── 1 nF ── GND
```

The pin reads V_wiper / 2.

Use ceramic 1 nF capacitors (C0G/NP0 if you have them). Before seating the XIAO in its
socket, power the servo and check with the meter that the socket's D0, D1 and D2 pins all
read between 0 and 3.3 V. A missing or wrong divider resistor shows up there instead of
on the RP2040.

## AS5600 breakout

- Power it from 3V3, and tie its VDD5V and VDD3V3 together if the board has a jumper for
  that (3.3 V mode). Then its I2C levels match the RP2040.
- Tie DIR to GND. Some boards leave it floating, which makes the reading unreliable.
- Use a 6 × 2.5 mm diametric magnet in the hub's pocket. Set the gap so `yaam-bench selftest`
  shows the magnet "ok" and an AGC near the middle of 0–128.

## HX711 and load cell (backdrive stage, but fine to wire now)

- Power the HX711 board from 3V3, so its DT output is safe for the RP2040.
- Cell wires: red E+, black E−, green A+, white A− (check your cell's label).
- DT → D10, SCK → D8. `yaam-bench selftest` shows "reading …" once it's alive.
