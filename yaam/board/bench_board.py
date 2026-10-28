"""SG90 bench board: XIAO RP2040, servo tap dividers, INA219, HX711 and a TMC2209.

Coordinates are 1-based holes, viewed from the component side. Copper strips run
horizontally; the generated BACK view is mirrored for cutting. The pin map must
match ../firmware/sg90_bench/sg90_bench.ino and ../WIRING.md, which
test_layout.py checks. Run `uv run bench_board.py`; add --preview for a single
DESIGN view.

Parts are placed by hand so that strips do most of the wiring. Row 1 is a 3V3
rail, row 2 and row 30 GND rails. The taps header and all eight divider parts
sit on the D0-D2 strips between the top rails and the XIAO; the encoder's
SDA/SCL share the D4/D5 strips, the HX711 header the XIAO's GND/3V3/D10/D8
strips, and the motor header the driver's coil outputs. The supply backbone is
hand-placed as links, which the router sees; it adds the signal jumpers and
every cut.
"""

from argparse import ArgumentParser
import hashlib
import json
from pathlib import Path

from stripboard import project
from stripboard.router import serialization

BOARD_WIDTH = 38
BOARD_HEIGHT = 30
ROUTE = Path(__file__).with_name("bench_board_route.json")

# INA219 breakout header in its own order, first pin to last. Clones differ:
# check against your module's silkscreen before soldering its socket.
INA219_PINS = ["VCC", "GND", "SCL", "SDA", "VIN-", "VIN+"]


def autoroute(sb, seed=0):
    """sb.autoroute(), with the solve kept in bench_board_route.json.

    A solve takes minutes and project() draws the board on several fresh
    StripBoards, each of which would solve again. The saved solve is reused
    until the parts or nets change; text and labels don't affect it. This
    seeds the library's own solve cache, so it leans on its private
    _build_problem/_signature/_route_cache.
    """
    board, instances, netlist = sb._build_problem()
    sig = sb._signature(board, instances, netlist, seed, None)
    key = hashlib.sha256(repr(sig).encode()).hexdigest()
    saved = json.loads(ROUTE.read_text()) if ROUTE.exists() else {}
    if saved.get("key") == key:
        sb._route_cache.setdefault(sig, serialization.from_dict(saved["result"]))
    result = sb.autoroute(seed=seed)
    if saved.get("key") != key and result.ok:
        ROUTE.write_text(json.dumps({"key": key, "result": serialization.to_dict(result)}) + "\n")
    return result


def draw(sb):
    sb.text(20, 29, "SG90 BENCH")

    xiao = sb.xiao(17, 3, ref="XIAO")

    # Servo taps and their dividers: each motor terminal into (V + 3.3) / 3 on
    # D0/D1, the wiper halved on D2.
    sb.text(1, 1, "TAPS")
    taps = sb.sip(4, 2, 4, ref="TAPS", pins=["GND", "A", "B", "W"], flip=True, label_scale=0.6)
    r1 = sb.resist(6, 1, "20K", l=2, ref="R1")
    r2 = sb.resist(7, 2, "20K", l=1, ref="R2")
    c1 = sb.cap(8, 2, ref="C1")
    r3 = sb.resist(10, 1, "20K", l=3, ref="R3")
    r4 = sb.resist(11, 2, "20K", l=2, ref="R4")
    c2 = sb.cap(12, 2, l=2, ref="C2")
    r5 = sb.resist(14, 2, "1M", l=3, ref="R5")
    c3 = sb.cap(15, 2, l=3, ref="C3")

    # I2C: the encoder lead on the D4/D5 strips, with the bus pull-ups to a 3V3
    # island on row 10.
    sb.text(1, 6, "ENC")
    enc = sb.sip(4, 7, 4, ref="ENC", pins=["SDA", "SCL", "GND", "3V3"], flip=True,
                 label_scale=0.6)
    r6 = sb.resist(6, 7, "4K7", l=3, ref="R6")
    r7 = sb.resist(7, 8, "4K7", l=2, ref="R7")

    # One-wire UART to the driver: TX through 1k onto row 11, which RX shares.
    r9 = sb.resist(15, 9, "1K", l=2, ref="R9")

    # Load cell amplifier lead on the XIAO's GND/3V3/D10 and D8 strips; the
    # fourth position sits on the D9 strip and stays empty, as a key.
    hx = sb.sip(35, 4, 5, "HX711", ref="HX711", pins=["GND", "3V3", "DT", "NC", "SCK"],
                label_scale=0.6)
    r10 = sb.resist(25, 7, "220", l=3, ref="R10")      # servo signal series R

    # Stepper driver at UART address 0, held off by R8 until the firmware
    # drives EN. CLK, STEP and DIR stay open, as on U-BOT: VACTUAL drives it.
    drv = sb.stepstick(17, 14, "TMC2209", variant="tmc2209", ref="TMC2209")
    r8 = sb.resist(14, 10, "4K7", l=4, ref="R8")
    mot = sb.sip(27, 16, 4, "MOT", ref="MOT", pins=["K", "G", "R", "B"], label_scale=0.6)
    c5 = sb.cap(25, 14, ref="C5")                      # 100 uF on VM
    v12 = sb.terminal(37, 12, 3, mod=2, ref="12V IN")
    sb.text(32, 12, "GND")
    sb.text(32, 14, "12V")

    # Servo power path: 5 V in, 470 uF, through the INA219's shunt, to the servo.
    v5 = sb.terminal(2, 28, 3, mod=2, ref="5V IN")
    sb.text(4, 28, "5V")
    sb.text(4, 30, "GND")
    c4 = sb.cap(8, 28, l=2, ref="C4")
    ina = sb.sip(11, 23, 6, "INA219", ref="INA219", pins=INA219_PINS, label_scale=0.55)
    servo = sb.sip(17, 26, 3, "SERVO", ref="SERVO", pins=["SIG", "V+", "GND"], label_scale=0.6)

    # Supply backbone.
    links = dict(
        gnd_top=sb.link(24, 2, 4, color="k", ref="L1"),      # top rail - XIAO GND
        gnd_enc=sb.link(3, 2, 9, color="k", ref="L2"),       # top rail - ENC GND
        gnd_drv=sb.link(29, 4, 15, color="k", ref="L3"),     # XIAO GND - driver GND1
        gnd_12v=sb.link(35, 12, 15, color="k", ref="L4"),    # 12V GND - driver GND1
        gnd_g2=sb.link(30, 15, 21, color="k", ref="L5"),     # GND1 - GND2
        gnd_bot=sb.link(31, 21, 30, color="k", ref="L6"),    # GND2 - bottom rail
        ms=sb.link(15, 15, 16, color="k", ref="L7"),         # MS1 - MS2
        ms_gnd=sb.link(13, 16, 30, color="k", ref="L8"),     # MS2 - bottom rail
        v33_top=sb.link(26, 1, 5, color="y", ref="L9"),      # top rail - XIAO 3V3
        v33_i2c=sb.link(5, 1, 10, color="y", ref="L10"),     # top rail - row 10 island
        v33_vio=sb.link(32, 5, 20, color="y", ref="L11"),    # XIAO 3V3 - driver VIO
        v33_ina=sb.link(9, 10, 23, color="y", ref="L12"),    # row 10 island - INA VCC
    )
    ends = lambda *names: [links[n].pin(p) for n in names for p in ("1", "2")]

    sb.net("GND", xiao.pin("GND"), taps.pin("GND"), enc.pin("GND"), hx.pin("GND"),
           servo.pin("GND"), v5.pin("2"), v12.pin("1"), ina.pin("GND"),
           drv.pin("GND1"), drv.pin("GND2"), drv.pin("MS1"), drv.pin("MS2"),
           r2.pin("1"), c1.pin("1"), r4.pin("1"), c2.pin("1"), r5.pin("1"), c3.pin("1"),
           c4.pin("2"), c5.pin("2"),
           *ends("gnd_top", "gnd_enc", "gnd_drv", "gnd_12v", "gnd_g2", "gnd_bot", "ms", "ms_gnd"),
           color="k")
    sb.net("3V3", xiao.pin("3V3"), enc.pin("3V3"), hx.pin("3V3"), ina.pin("VCC"),
           drv.pin("VIO"), r1.pin("1"), r3.pin("1"), r6.pin("2"), r7.pin("2"), r8.pin("1"),
           *ends("v33_top", "v33_i2c", "v33_vio", "v33_ina"), color="y")
    sb.net("5V_IN", v5.pin("1"), c4.pin("1"), ina.pin("VIN+"), color="r")
    sb.net("SERVO_V", ina.pin("VIN-"), servo.pin("V+"), color="r")
    sb.net("12V", v12.pin("2"), c5.pin("1"), drv.pin("VM"), color="r")
    sb.net("TAP_A", taps.pin("A"), r1.pin("2"), r2.pin("2"), c1.pin("2"), xiao.pin("D0"))
    sb.net("TAP_B", taps.pin("B"), r3.pin("2"), r4.pin("2"), c2.pin("2"), xiao.pin("D1"))
    sb.net("WIPER", taps.pin("W"), r5.pin("2"), c3.pin("2"), xiao.pin("D2"))
    sb.net("EN", xiao.pin("D3"), drv.pin("EN"), r8.pin("2"))
    sb.net("SDA", xiao.pin("D4"), enc.pin("SDA"), ina.pin("SDA"), r6.pin("1"))
    sb.net("SCL", xiao.pin("D5"), enc.pin("SCL"), ina.pin("SCL"), r7.pin("1"))
    sb.net("UART_TX", xiao.pin("TX"), r9.pin("1"))
    sb.net("UART", xiao.pin("RX"), r9.pin("2"), drv.pin("PDN"))
    sb.net("HX_DT", xiao.pin("D10"), hx.pin("DT"))
    sb.net("HX_SCK", xiao.pin("D8"), hx.pin("SCK"))
    sb.net("SERVO_PWM", xiao.pin("D9"), r10.pin("1"))
    sb.net("SERVO_SIG", r10.pin("2"), servo.pin("SIG"))
    for wire, phase in (("R", "1A"), ("B", "1B"), ("G", "2A"), ("K", "2B")):
        sb.net("MOT_" + wire, mot.pin(wire), drv.pin(phase))

    autoroute(sb)

    # Every placed part, keyed by the ref on the silkscreen; test_layout.py walks
    # copper from these pins.
    return {
        part.id: part
        for part in (
            xiao, taps, r1, r2, c1, r3, r4, c2, r5, c3, enc, r6, r7, r9, hx, r10,
            drv, r8, mot, c5, v12, v5, c4, ina, servo, *links.values(),
        )
    }


def main():
    ap = ArgumentParser(description=__doc__)
    ap.add_argument("--preview", action="store_true",
                    help="single DESIGN view only; skip the build sheet and silkscreen")
    args = ap.parse_args()
    project(
        draw,
        name="bench_board",
        width=BOARD_WIDTH,
        height=BOARD_HEIGHT,
        designing=args.preview,
        # Jumper lengths on the FRONT view, so wires can be cut straight off the sheet.
        front_numbers=True,
        cuts=True,
        label={"page": (BOARD_WIDTH + 8, BOARD_HEIGHT + 6)},
    )


if __name__ == "__main__":
    main()
