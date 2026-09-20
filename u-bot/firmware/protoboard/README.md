# U-BOT base protoboard

XIAO ESP32-S3, two BTT TMC2209 V1.3 drivers, two AS5600 encoder connectors,
battery sensing, and an onboard 5 V buck converter. Designed with
[stripboard](https://github.com/Stocko-2073/stripboard-py).

```sh
uv run ubot_base.py            # FRONT/BACK/DESIGN build sheet + silkscreen
uv run ubot_base.py --preview  # DESIGN view only, for iterating
uv run python -m unittest test_layout
```

The board is **34 × 26 holes**, approximately **86 × 66 mm** with half-pitch
edge margins. Horizontal copper strips; coordinates in the Python and assembly
list are viewed from the component side. Rows 1–26 are A–Z on the drawing.
The BACK view is mirrored for working on the copper side.

Outputs:

- `ubot_base.pdf`: FRONT / BACK / DESIGN build sheet, or the DESIGN view alone
  under `--preview`.
- `ubot_base_cuts.txt`: the cut list, written in both modes. One line of
  comma-separated track cuts in component-side coordinates (`A16` is row A,
  column 16), one entry per hole in declaration order. Read it against the
  mirrored BACK view when cutting.
- `ubot_base-label.pdf`: component-side silkscreen, full-build mode only.
- `ubot_base.scad`: the same silkscreen as a 3D-printable two-colour label,
  full-build mode only. 0.44 mm plate with the artwork inlaid the top 0.16 mm --
  four layers, a 0.2 mm initial layer then 3 x 0.08 mm, with the traces the top
  two. Every pin and wire end is drilled through at 1.2 mm. Render one body per
  filament:

  ```
  openscad -D 'part="plate"'  -o ubot_base-plate.stl  ubot_base.scad
  openscad -D 'part="traces"' -o ubot_base-traces.stl ubot_base.scad
  ```

  Both bodies are already positioned; import them together without moving them
  and they meet flush at the top face. Thickness can be retried in the `.scad`
  itself (`plate_h`, `inlay_h`) without regenerating from Python.

`test_layout.py` is the electrical check. It walks copper from every part pin
using the library's own flood-fill and asserts the topology this README
describes -- rails, divider, shared EN, UART, driver addresses, encoder buses and
motor phases -- plus that the firmware's pin defaults in
`../base/main/Kconfig.projbuild` still match the board. **A failure there is a
layout bug to fix in `ubot_base.py`, not a test to update.** `draw()` returns its
parts keyed by silkscreen ref, which is what the test walks.

Generation fails before exporting if routing is incomplete or validation fails.
Previously generated files remain on disk after a failed run; use only outputs
from a successful run. `POSTMORTEM_FEEDBACK.md` describes the original layout
and library limitations, not the current build counts.

Use the PDF or `test_layout.py`'s part table for assembly coordinates.
`ubot_base-build.md` is not a generated output and should not be used.

## Power and buck mounting

```text
Battery + ----+---- TMC A / TMC B VM
              +---- 100k ---- BATT / D1 ---- 10k ---- GND
              +---- BUCK IN+
Battery - ---------- common GND (buck, XIAO, drivers, encoders)
BUCK VO+ (5 V) ----------------------------------------- XIAO 5V
XIAO 3V3 ---------- driver VIO, encoder power, pull-ups
```

The buck is the **20 × 10 mm** module in `buck_spec.jpg`, with four pads on
**2.54 mm pitch**. Its header occupies column 19, rows 23–26; the body extends
to the right across columns 19–26, components facing up. A body keep-out
prevents routed wire ends or jumper spans under it. Use a 1×4 socket/header
and an insulating support under the far end. The pad-to-edge offset is assumed
to be about half a pitch; dry-fit the actual module before soldering.

| Pad, top to bottom | Connection |
|---|---|
| EN | isolated; separate from the motor EN signal |
| IN+ | battery / VM |
| GND | common negative |
| VO+ | 5 V output, direct to XIAO 5V |

Set the buck to **5.00 V before inserting the XIAO**. The pictured module is
adjustable by default, so use the potentiometer and a meter. The supplied image
mentions cutting a trace and bridging rear pads for fixed outputs, but does not
show those pads; this layout does not assume a particular rear-pad arrangement.
Confirm it produces 5 V with EN open. If it does not, identify the regulator
and its enable requirements before strapping EN; the image supplies no EN
voltage limits. Likewise, verify the module's input rating covers the pack's
full charge voltage (the firmware uses a 4S LiFePO4 table).

### USB and pack power

BUCK VO+ connects directly to XIAO 5V without a reverse-blocking diode.
**Do not connect USB and the pack at the same time:** this ties the buck output
to the USB rail. Use OTA for firmware updates on pack power. The production
board is planned to include a blocking diode.

## Wiring and parts

The firmware source of truth is `../base/main/Kconfig.projbuild`, and
`test_layout.py` asserts the two agree. The original breadboard photo is a
reference, not a complete netlist.

The board is wired by Dn pad. `test_layout.py` checks the firmware GPIO numbers
against the XIAO ESP32-S3 pinout.

On the S3, note that D2/GPIO3 is a strapping pin (GPIO0, GPIO3, GPIO45, GPIO46
are), carrying wheel B's SDA. It is inert unless the `JTAG_SEL_ENABLE` eFuse is
burned, but it is the only pad here with a boot-time role.

| XIAO | Connection |
|---|---|
| D0 | free |
| D1 | battery divider midpoint, 100k from VM / 10k to GND |
| D2 / D3 | encoder B SDA / SCL (bit-banged) |
| D4 / D5 | encoder A SDA / SCL |
| D6 (TX) | 1k series resistor to shared UART (470R-4.7k all fine) |
| D7 (RX) | shared UART, both driver PDN/RX pins |
| D8 | free |
| D9 | both driver EN pins, 4.7k pull-up to 3V3 |
| D10 | free |
| 3V3 | driver VIO, encoder supplies, pull-ups, driver B MS1 |
| 5V | buck output, direct |

| Reference | Part / assembly note |
|---|---|
| XIAO | XIAO ESP32-S3 on two 1×7 sockets, USB facing the top edge |
| TMC2209 A / B | BTT V1.3 on two 1×8 sockets each; A rotated 180°, B upright |
| BUCK | 20 × 10 mm module, 1×4 socket at 2.54 mm pitch |
| R1 | 1k, UART series resistor; anything 470R-4.7k works |
| R2 / R3 | 4.7k, encoder A SDA / SCL pull-ups |
| R4 / R5 | 4.7k, encoder B SDA / SCL pull-ups |
| R6 | 4.7k, motor EN pull-up |
| R7 / R8 | 100k / 10k battery divider; nominal ratio 11 |
| C1 | 100 uF electrolytic, 25 V or higher; positive at row 22 |
| PWR | 2-way 5.08 mm screw terminal; GND row 20, VM+ row 22 |
| MOT A (MA) | 1×4: 1B, 1A, 2A, 2B from top to bottom |
| MOT B (MB) | 1×4: 2B, 2A, 1A, 1B from top to bottom |
| ENC A (EA) | 1×4: GND, 3V3, SDA, SCL from top to bottom |
| ENC B (EB) | 1×4: GND, 3V3, SDA, SCL from top to bottom |

Both encoder connectors use **GND, 3V3, SDA, SCL**. Check this order before
reusing cables from earlier boards. The short-pitch resistors mount upright.
Use the PDF to identify them: not all resistor values fit on the
silkscreen -- and R2 through R6 are all 4.7k, so only their positions
distinguish them.

Driver B MS1 is strapped to 3V3 for UART address 1. Driver A MS1 and both MS2
pins are open as in the existing build (address 0 / 1). TX, CLK, STEP and DIR
are unused. Only GND1 is externally wired; GND2 is common inside each module.
All inter-row connections are routed jumpers; this revision has no separately
listed fixed links.

## Assembly checks

1. Cut tracks using the mirrored BACK drawing before installing module sockets.
   Check each cut for continuity and adjacent-net isolation.
2. Fit routed wires and passives, then connectors and sockets. Follow the C1
   polarity in the assembly list.
3. Reinforce the VM and motor-return paths with suitable wire for the actual
   motor current. Router validation checks connectivity and collisions, not
   current capacity, thermal behavior or transient protection.
4. Fit and verify the buck alone at 5.00 V, **on pack power with the XIAO out
   of its sockets**, then insert the XIAO and check its 3V3 rail. With no
   blocking diode, never do this with USB attached.
5. Check the driver silkscreen against the drawing before insertion, especially
   rotated driver A. Motor cable colors do not define phase order.
6. Calibrate the firmware's `batt_div` reading against a meter.
