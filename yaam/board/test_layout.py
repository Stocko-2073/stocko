"""Electrical checks on the routed bench board.

Nets are extracted with the library's own flood-fill (`trace_point`), which walks
copper along a row, stops at cuts and hops jumpers. It does not walk through
components, so a part pin landing in a net means real copper connectivity.

These assert the board WIRING.md describes and the pins the firmware drives. A
failure here is a layout bug to fix in `bench_board.py`, not a test to update.
"""
import re
import unittest
import warnings
from pathlib import Path

from stripboard import StripBoard

import bench_board

SKETCH = Path(__file__).parent / "../firmware/sg90_bench"
# XIAO RP2040 pads to GPIOs, as arduino-pico's seeed_xiao_rp2040 variant has them.
XIAO_GPIO = {"D0": 26, "D1": 27, "D2": 28, "D3": 29, "D4": 6, "D5": 7, "TX": 0, "RX": 1,
             "D8": 2, "D9": 4, "D10": 3}


class LayoutTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.board = StripBoard()
        cls.board.begin_view("DESIGN", bench_board.BOARD_WIDTH, bench_board.BOARD_HEIGHT)
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            cls.parts = bench_board.draw(cls.board)
            cls.draw_warnings = [str(w.message) for w in caught]
        cls.board.trace_origins = []
        cls.pin_at = {}
        for ref, comp in cls.parts.items():
            for pin, xy in (comp.pins or {}).items():
                cls.pin_at.setdefault((int(xy[0]), int(xy[1])), []).append(f"{ref}.{pin}")

    def net(self, part, pin):
        """Every component pin reachable in copper from `part`.`pin`."""
        if part not in self.parts:
            self.fail(f"no part {part!r} on the board")
        x, y = self.parts[part].pins[str(pin)]
        holes = []
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            self.board.trace_point(int(x), int(y), holes, (0, 0, 0), first=True)
        self.board.trace_origins = []
        return {n for h in holes for n in self.pin_at.get((int(h[0]), int(h[1])), [])}

    def assertSameNet(self, a, *others):
        part, pin = a.rsplit(".", 1)
        net = self.net(part, pin)
        for b in others:
            self.assertIn(b, net, f"{a} and {b} are not the same net")

    def assertDifferentNets(self, a, b):
        part, pin = a.rsplit(".", 1)
        self.assertNotIn(b, self.net(part, pin), f"{a} and {b} are shorted")

    def assertAlone(self, a):
        part, pin = a.rsplit(".", 1)
        self.assertEqual(self.net(part, pin), {a}, f"{a} should connect to nothing")

    def test_draw_is_clean(self):
        self.assertEqual(self.draw_warnings, [])

    def test_ground(self):
        self.assertSameNet("XIAO.GND", "TAPS.GND", "ENC.GND", "HX711.GND", "SERVO.GND",
                           "5V IN.2", "12V IN.1", "INA219.GND", "TMC2209.GND1",
                           "TMC2209.GND2", "R2.1", "C1.1", "R4.1", "C2.1", "R5.1", "C3.1",
                           "C4.2", "C5.2")

    def test_3v3(self):
        self.assertSameNet("XIAO.3V3", "ENC.3V3", "HX711.3V3", "INA219.VCC", "TMC2209.VIO",
                           "R1.1", "R3.1", "R6.2", "R7.2", "R8.1")

    def test_supplies_are_isolated(self):
        rails = ["XIAO.GND", "XIAO.3V3", "5V IN.1", "INA219.VIN-", "12V IN.2"]
        for i, a in enumerate(rails):
            for b in rails[i + 1:]:
                self.assertDifferentNets(a, b)
        # The servo supply never reaches the XIAO: it runs on USB.
        self.assertAlone("XIAO.5V")

    def test_servo_power_runs_through_the_shunt(self):
        self.assertSameNet("5V IN.1", "C4.1", "INA219.VIN+")
        self.assertSameNet("INA219.VIN-", "SERVO.V+")

    def test_tap_dividers(self):
        """Motor taps 20k/20k between 3V3 and GND with 1 nF; the wiper 1M and 1 nF to GND."""
        self.assertSameNet("XIAO.D0", "TAPS.A", "R1.2", "R2.2", "C1.2")
        self.assertSameNet("XIAO.D1", "TAPS.B", "R3.2", "R4.2", "C2.2")
        self.assertSameNet("XIAO.D2", "TAPS.W", "R5.2", "C3.2")
        for a, b in (("D0", "D1"), ("D1", "D2"), ("D0", "D2")):
            self.assertDifferentNets(f"XIAO.{a}", f"XIAO.{b}")

    def test_i2c(self):
        self.assertSameNet("XIAO.D4", "ENC.SDA", "INA219.SDA", "R6.1")
        self.assertSameNet("XIAO.D5", "ENC.SCL", "INA219.SCL", "R7.1")
        self.assertDifferentNets("XIAO.D4", "XIAO.D5")

    def test_uart_is_one_wire_with_series_tx(self):
        """TX reaches the line through R9; RX and PDN sit on the line itself."""
        self.assertSameNet("XIAO.TX", "R9.1")
        self.assertSameNet("XIAO.RX", "R9.2", "TMC2209.PDN")
        self.assertDifferentNets("XIAO.TX", "XIAO.RX")

    def test_driver_enable_is_pulled_up(self):
        self.assertSameNet("XIAO.D3", "TMC2209.EN", "R8.2")

    def test_driver_straps(self):
        """Address 0 (MS1, MS2 low); CLK, STEP, DIR and TX open, as on U-BOT."""
        self.assertSameNet("TMC2209.MS1", "XIAO.GND")
        self.assertSameNet("TMC2209.MS2", "XIAO.GND")
        for pin in ("CLK", "STEP", "DIR", "TX"):
            self.assertAlone(f"TMC2209.{pin}")

    def test_motor_phases(self):
        """Red/blue is coil 1, green/black coil 2, as on U-BOT."""
        for wire, phase in (("R", "1A"), ("B", "1B"), ("G", "2A"), ("K", "2B")):
            self.assertSameNet(f"MOT.{wire}", f"TMC2209.{phase}")

    def test_load_cell_amplifier(self):
        self.assertSameNet("XIAO.D10", "HX711.DT")
        self.assertSameNet("XIAO.D8", "HX711.SCK")
        self.assertAlone("HX711.NC")

    def test_servo_signal_goes_through_its_resistor(self):
        self.assertSameNet("XIAO.D9", "R10.1")
        self.assertSameNet("SERVO.SIG", "R10.2")
        self.assertDifferentNets("XIAO.D9", "SERVO.SIG")

    def test_firmware_pins_match_the_board(self):
        """The sketch's pin constants and ADC inputs must name the pads this
        board wires, through the XIAO RP2040's pad-to-GPIO map."""
        ino = (SKETCH / "sg90_bench.ino").read_text()
        adc = (SKETCH / "TapAdc.h").read_text()
        wired = {"PIN_SERVO": "D9", "PIN_TMC_EN": "D3", "PIN_HX_SCK": "D8", "PIN_HX_DT": "D10"}
        for name, pad in wired.items():
            match = re.search(rf"static const uint {name} = (\d+);", ino)
            self.assertIsNotNone(match, name)
            self.assertEqual(int(match.group(1)), XIAO_GPIO[pad], f"{name} should be {pad}")
        inputs = [int(g) for g in re.findall(r"adc_gpio_init\((\d+)\)", adc)]
        self.assertEqual(inputs, [XIAO_GPIO["D0"], XIAO_GPIO["D1"], XIAO_GPIO["D2"]])


if __name__ == "__main__":
    unittest.main()
