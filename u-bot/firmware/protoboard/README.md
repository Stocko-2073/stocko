# U-BOT base protoboard

Stripboard version of the breadboard in `breadboard.jpeg`: a XIAO ESP32-C6, two
BTT TMC2209 sticks on one UART bus, an AS5600 encoder header per wheel, battery
sense. Designed with [stripboard](https://github.com/Stocko-2073/stripboard-py).

```sh
uv run ubot_base.py     # -> ubot_base.pdf (FRONT / BACK / DESIGN) + ubot_base-label.pdf
```

Set `designing = True` in `ubot_base.py` for a single DESIGN page while moving
parts. The router validates the board every run and prints a one-line report;
`status=feasible valid=True routed=40/40` is the number to look for.

## Where the netlist came from

The wiring is the "Pins, XIAO ESP32-C6" table in `../DRIVE_MECHANISM.md` and
`../base/main/Kconfig.projbuild`, not the photo. The photo only confirmed the
parts count: one XIAO, two sticks, six resistors (one 1k, five 4.7k).

| XIAO | net | goes to |
|---|---|---|
| D0 | EN | both sticks' EN, 4.7k to 3V3 |
| D1 | BATT | 100k from VM, 10k to GND (ratio 11, the `batt_div` default) |
| D4 / D5 | SDA_A / SCL_A | ENC A header, 4.7k pull-ups |
| D6 (TX) | TX | 1k to the UART node |
| D7 (RX) | UART | both sticks' PDN_UART (pin 4, silkscreened RX) |
| D8 / D9 | SCL_B / SDA_B | ENC B header, 4.7k pull-ups |
| 3V3 | 3V3 | both VIO, stick B MS1 (address 1), encoders, pull-ups, AUX |
| 5V | 5V | 5V header |
| D2, D3, D10 | open | |

Stick pins left open, as on the breadboard: MS2, TX (pin 5, unpopulated), CLK,
STEP, DIR on both; MS1 on stick A (address 0); and the second GND pin on each
stick, which is common with the first on the module. The router isolates every
open pin with cuts.

## Parts

| ref | part | notes |
|---|---|---|
| XIAO | Seeed XIAO ESP32-C6 | on 2x 1x7 female headers, USB-C at the board edge |
| TMC2209 A, B | BTT TMC2209 V1.3 | each on 2x 1x8 female headers, heatsinks up |
| R1 | 1k | TX to UART node |
| R2 | 4.7k | EN pull-up |
| R3, R4 | 4.7k | SDA_A, SCL_A pull-ups |
| R5, R6 | 4.7k | SDA_B, SCL_B pull-ups |
| R7 | 100k | VM to BATT (divider top) |
| R8 | 10k | BATT to GND (divider bottom) |
| C1 | 100 uF, 25 V or better, electrolytic | across VM / GND, + toward the bottom edge (VM rail) |
| PWR | 2-way 5.08 mm screw terminal | 12 V pack; top pin GND, bottom pin VM+ |
| MOT A, MOT B | 1x4 header | phases 1B 1A 2A 2B (A) and 2B 2A 1A 1B (B), top to bottom |
| ENC A | 1x4 header | GND 3V3 SDA SCL, top to bottom |
| ENC B | 1x4 header | 3V3 GND SDA SCL, top to bottom |
| 5V | 1x2 header | 5V GND; feed for the XIAO when not on USB |
| AUX | 1x2 header | GND 3V3, spare logic power (IMU, bumpers) |
| board | 28 x 22 holes, 0.1" stripboard | 71 x 56 mm; cut from a larger sheet |
| wire | 16 autorouted jumpers + 4 hand-placed links | the four links are the two long left-edge runs (BATT, GND) and two short ones (GND, MS1 strap) |
| cuts | 34 | 23 of them sit under the three modules; make them before soldering the headers |

## Things I added that were not on the breadboard

- **Battery divider R7/R8** (100k / 10k). The firmware expects one on D1
  (`UBOT_PIN_BATT_ADC`) and the breadboard did not have it. 14.6 V at the pack
  puts 1.33 V on the pin. Set `batt_div` against a meter as battery.c says.
- **C1 bulk capacitor** on VM. The sticks' own caps are small and the pack is on
  a lead; a stepper driver without a local electrolytic is asking for a VM spike
  on decel.
- **5V header.** The photo runs the XIAO from USB. On the robot something has to
  feed the 5V pin; this is where a buck converter lands. Check the XIAO's 5V pin
  behaviour with USB and 5V both present before relying on it.
- **AUX header** (GND/3V3) on the top rails. Free, and it gives the router a pin
  on the top rows so GND and 3V3 can cross the board there.

## Before soldering

- **Check the stick pin order against the silkscreen.** The footprint assumes
  the StepStick order: EN MS1 MS2 RX TX CLK STEP DIR down the logic row, and
  VM GND 2B 2A 1A 1B VIO GND down the power row, VM opposite EN. Stick A is
  drawn rotated 180 degrees so its motor pins face the left edge; the labels on
  the FRONT view are what matters.
- **Cut before you solder.** The BACK view is mirrored and is the side you cut
  on. Every red X is one cut; 23 of the 34 are under the module bodies.
- **Thicken the VM and GND rails** (rows 22 and 20, and row 1) with a run of
  solder or bus wire. Stripboard copper is thin and both motors return through
  them.
- **Motor connectors.** Pin order on the headers is by phase, not by cable
  colour; wire the JST plugs to match, or swap A/B pairs at the header.
