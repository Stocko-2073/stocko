"""U-BOT stripboard: XIAO ESP32-S3, two TMC2209s and an onboard 5 V buck.

Coordinates are 1-based holes, viewed from the component side. Copper strips
run horizontally; the generated BACK view is mirrored for cutting.
Firmware pin assignments come from ../base/main/Kconfig.projbuild.
Run `uv run ubot_base.py`; add --preview for a single DESIGN view.
"""

from argparse import ArgumentParser
from pathlib import Path

from stripboard import project

BOARD_WIDTH = 34
BOARD_HEIGHT = 26
PITCH_MM = 2.54
BUCK_LENGTH_MM = 20
BUCK_WIDTH_MM = 10


TMC_PINS = [
    "EN",
    "MS1",
    "MS2",
    "PDN",
    "TX",
    "CLK",
    "STEP",
    "DIR",
    "GND",
    "VIO",
    "1B",
    "1A",
    "2A",
    "2B",
    "GND",
    "VM",
]


def tmc2209(sb, x, y, name, upside_down=False):
    u = sb.dip(
        x,
        y,
        6,
        8,
        name,
        ref=name,
        pins=TMC_PINS,
        upside_down=upside_down,
        label_scale=0.6,
    )
    sb.keepout(x + 1, y, 5, 8, show=False)
    return u


def buck_converter(sb, x, row):
    """Four pads on the left, EN/IN+/GND/VO+ top to bottom as in buck_spec.jpg.

    Reserve an 8 x 4 hole envelope for the measured 20 x 10 mm PCB.
    Pad-to-edge offset is assumed centered across the 10 mm width; allow a
    half-pitch at the pad edge and keep the whole body clear of wire ends.
    """
    y = sb.row(row)
    buck = sb.sip(
        x, y, 4, pins=["EN", "IN+", "GND", "VO+"], label_scale=0.55, ref="BUCK"
    )
    sb.box(x - 0.5, y - 0.5, BUCK_LENGTH_MM / PITCH_MM, BUCK_WIDTH_MM / PITCH_MM)
    sb.text(x + 3, y + 1, "BUCK")
    sb.text(x + 3, y + 2, "5V")
    sb.keepout(x + 1, y, 7, 4, show=False)
    return buck


def draw(sb):
    sb.text(1, 1, "U-BOT")

    # XIAO ESP32-S3
    xiao = sb.xiao(14, "A")
    sb.jumper(17, "B", 17, "M")
    sb.cut(16, "A", "G")
    sb.cut(22, "F")
    sb.cut(22, "G")

    driver_a = tmc2209(sb, 23, "S", "DRIVE A")
    sb.cut(22, "I", "L")
    driver_b = tmc2209(sb, 23, "E", "DRIVE B")

    motor_a = sb.sip(
        29,
        "O",
        4,
        "MOTA",
        ref="MOT A",
        pins=["R", "B", "G", "K"],
    )
    motor_b = sb.sip(
        29,
        "A",
        4,
        "MOTB",
        ref="MOT B",
        pins=["R", "B", "G", "K"],
    )

    # Motor A jumpers
    sb.jumper(34, "O", 34, "W")
    sb.jumper(33, "P", 33, "X")
    sb.jumper(32, "Q", 32, "V")
    sb.jumper(31, "R", 31, "U")
    sb.cut(28, "U", "X")
    sb.cut(28, "O", "R")

    # Motor B jumpers
    sb.jumper(34, "A", 34, "I")
    sb.jumper(33, "B", 33, "J")
    sb.jumper(32, "C", 32, "H")
    sb.jumper(31, "D", 31, "G")
    sb.cut(28, "G", "J")
    sb.cut(28, "A", "D")

    encoder_a = sb.sip(
        2,
        "C",
        4,
        "ENCA",
        ref="ENC A",
        pins=["GND", "3V3", "SDA", "SCL"],
        flip=False,
    )

    encoder_b = sb.sip(
        2,
        "H",
        4,
        "ENCB",
        ref="ENC B",
        pins=["GND", "3V3", "SDA", "SCL"],
        flip=False,
    )

    buck = buck_converter(sb, 2, "R")
    # d1 = sb.diode(26, 1, len=2, ref="D1")
    # sb.keepout(26, 2, 1, 1, show=True)

    # Logic Power
    sb.jumper(32, "K", 32, "N")
    sb.jumper(25, "N", 25, "Y")
    sb.cut(24, "Y")
    sb.jumper(26, "F", 26, "N")
    sb.jumper(25, "C", 25, "F")
    sb.cut(28, "K")
    sb.jumper(10, "D", 10, "I")
    sb.jumper(11, "I", 11, "N")
    sb.cut(10, "G", "H")
    sb.cut(12, "I")
    sb.cut(11, "C", "D")

    # Motor Power
    pwr = sb.terminal(2, "M", 3, mod=2, ref="PWR")
    sb.text(4, "M", "GND")
    sb.text(4, "O", "VM+")
    c1 = sb.cap(7, "M", l=2, upside_down=True, ref="C1")
    sb.jumper(27, "E", 27, "O")
    sb.cut(25, "E")
    sb.jumper(26, "O", 26, "S")
    sb.cut(25, "S")
    sb.jumper(19, "O", 19, "S")

    # GROUND
    sb.jumper(30, "F", 30, "L")
    sb.jumper(31, "M", 31, "L")
    sb.cut(28, "F")
    sb.cut(28, "L")
    sb.jumper(30, "M", 30, "T")
    sb.jumper(28, "Z", 28, "T")
    sb.jumper(7, "C", 7, "H")
    sb.jumper(9, "H", 9, "M")
    sb.cut(26, "Z")

    # Enable Pins
    sb.jumper(24, "E", 24, "S")
    sb.cut(22, "S")

    # I2C bus
    r2 = sb.resist(8, "D", "4K7", l=1, ref="R2")
    r3 = sb.resist(9, "D", "4K7", l=2, ref="R3")

    # SoftI2C bus
    sb.jumper(12, "C", 12, "J")
    sb.jumper(13, "D", 13, "K")
    sb.cut(14, "J", "K")
    r4 = sb.resist(7, "I", "4K7", l=1, ref="R4")
    r5 = sb.resist(8, "I", "4K7", l=2, ref="R5")

    # UART
    sb.jumper(21, "G", 21, "H")
    sb.jumper(22, "H", 22, "V")
    r1 = sb.resist(11, "G", "1K", l=1, ref="R1")
    sb.cut(19, "V")

    # Battery Sense
    sb.jumper(15, "B", 15, "L")
    r7 = sb.resist(14, "L", "100K", l=3, ref="R7")
    r8 = sb.resist(13, "L", "10K", l=1, ref="R8")

    # 5V Line
    sb.jumper(18, "A", 18, "U")
    sb.cut(19, "U")

    r6 = sb.resist(22, "C", "4K7", l=2, ref="R6")

    sb.trace(20, "C")  # 3v3
    sb.trace(2, "M")  # GND
    sb.trace(20, "A")  # 5V
    sb.trace(2, "O")  # 12V

    sb.trace(14, "A")  # D0 (Unconnected)
    sb.trace(14, "B")  # D1/Battery Sense
    sb.trace(2, "J")  # D2/SDA2
    sb.trace(2, "K")  # D3/SCL2
    sb.trace(2, "E")  # D4/SDA1
    sb.trace(2, "F")  # D5/SCL1
    sb.trace(14, "G")  # D6/UART/TX
    sb.trace(20, "G")  # D7/UART/RX
    sb.trace(20, "F")  # D8 (Unconnected)
    sb.trace(20, "E")  # D9/EN
    sb.trace(20, "D")  # D10 (Unconnected)

    sb.trace(29, "U")  # Drive B 2B
    sb.trace(29, "V")  # Drive B 2A
    sb.trace(29, "W")  # Drive B 1B
    sb.trace(29, "X")  # Drive B 1A
    sb.trace(29, "G")  # Drive A 2B
    sb.trace(29, "H")  # Drive A 2A
    sb.trace(29, "I")  # Drive A 1B
    sb.trace(29, "J")  # Drive A 1A

    # Every placed part, keyed by the ref on the silkscreen. test_layout.py
    # walks copper from these pins, so this is the contract it checks against --
    # returning them keeps it off the board object's private component list.
    return {
        part.id: part
        for part in (
            xiao, driver_a, driver_b, motor_a, motor_b, encoder_a, encoder_b,
            buck, pwr, c1, r1, r2, r3, r4, r5, r6, r7, r8,
        )
    }


def main():
    ap = ArgumentParser(description=__doc__)
    ap.add_argument("--preview", action="store_true",
                    help="single DESIGN view only; skip the build sheet and silkscreen")
    args = ap.parse_args()
    board = project(
        draw,
        name="ubot_base",
        width=BOARD_WIDTH,
        height=BOARD_HEIGHT,
        designing=args.preview,
        # ubot_base_cuts.txt: every track cut as a comma-separated list in
        # component-side coordinates, for working down the BACK view.
        cuts=True,
        label={"page": (BOARD_WIDTH + 8, BOARD_HEIGHT + 6)},
        # Four layers: a 0.2 mm initial layer then 3 x 0.08 mm. The artwork is
        # inlaid the top two, so the traces print as 0.16 mm of the second
        # colour and their floor lands on the 0.28 mm layer boundary.
        # Skipped in --preview so the watch loop stays fast.
        scad=not args.preview and {"plate_mm": 0.44, "inlay_mm": 0.16},
    )


if __name__ == "__main__":
    main()
