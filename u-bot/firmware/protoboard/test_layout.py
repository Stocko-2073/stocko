"""Electrical regression checks on the routed board.

Nets are extracted with the library's own flood-fill (`trace_point`), which walks
copper along a row, stops at cuts and hops jumpers. It does not walk through
components, so a part pin landing in a net means real copper connectivity.

These assert the topology the board is *meant* to have, not the one it currently
routes -- a failure here is a layout bug to fix in `ubot_base.py`, not a test to
update. The firmware pin map is checked against `../base/main/Kconfig.projbuild`
so the two cannot drift apart silently.
"""
import re
import unittest
import warnings
from pathlib import Path

from stripboard import StripBoard

import ubot_base


class LayoutTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.board = StripBoard()
        cls.board.begin_view('DESIGN', ubot_base.BOARD_WIDTH, ubot_base.BOARD_HEIGHT)
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter('always')
            cls.parts = ubot_base.draw(cls.board)
            cls.draw_warnings = [str(w.message) for w in caught]
        # draw() traces every net once; clear the origins so our own tracing
        # below does not report a collision against those first passes.
        cls.board.trace_origins = []
        cls.pin_at = {}
        for ref, comp in cls.parts.items():
            for pin, xy in (comp.pins or {}).items():
                cls.pin_at.setdefault((int(xy[0]), int(xy[1])), []).append(
                    '%s.%s' % (ref, pin))

    def net(self, part, pin):
        """Every component pin reachable in copper from `part`.`pin`."""
        if part not in self.parts:
            self.fail('no part %r on the board' % part)
        x, y = self.parts[part].pins[str(pin)]
        holes = []
        with warnings.catch_warnings():
            warnings.simplefilter('ignore')
            self.board.trace_point(int(x), int(y), holes, (0, 0, 0), first=True)
        self.board.trace_origins = []
        return {n for h in holes for n in self.pin_at.get((int(h[0]), int(h[1])), [])}

    def assertSameNet(self, a, b):
        part, pin = a.rsplit('.', 1)
        self.assertIn(b, self.net(part, pin), '%s and %s are not the same net' % (a, b))

    def assertDifferentNets(self, a, b):
        part, pin = a.rsplit('.', 1)
        self.assertNotIn(b, self.net(part, pin), '%s and %s are shorted' % (a, b))

    def test_draw_is_clean(self):
        self.assertEqual(self.draw_warnings, [])

    def test_power_rails(self):
        """Pack feeds VM, the drivers and the buck input; buck output feeds 5V."""
        for pin in ('C1.2', 'DRIVE A.VM', 'DRIVE B.VM', 'R7.2', 'BUCK.IN+'):
            self.assertSameNet('PWR.2', pin)
        for pin in ('C1.1', 'BUCK.GND', 'XIAO.GND', 'R8.2',
                    'DRIVE A.GND', 'DRIVE B.GND', 'ENC A.GND', 'ENC B.GND'):
            self.assertSameNet('PWR.1', pin)
        # No diode on the protoboard: VO+ ties straight to the XIAO 5V pin.
        # Deliberate (see README); the production board reinstates it.
        self.assertSameNet('BUCK.VO+', 'XIAO.5V')

    def test_rails_are_isolated(self):
        """The three supplies must not meet anywhere."""
        for a, b in (('PWR.2', 'XIAO.3V3'), ('PWR.2', 'XIAO.5V'),
                     ('XIAO.5V', 'XIAO.3V3'), ('PWR.2', 'PWR.1'),
                     ('BUCK.IN+', 'BUCK.VO+'), ('XIAO.3V3', 'XIAO.GND')):
            self.assertDifferentNets(a, b)

    def test_battery_divider(self):
        """100k from VM to D1, 10k from D1 to GND: nominal ratio 11."""
        self.assertSameNet('XIAO.D1', 'R7.1')
        self.assertSameNet('XIAO.D1', 'R8.1')
        self.assertSameNet('R7.2', 'PWR.2')
        self.assertSameNet('R8.2', 'PWR.1')

    def test_en_is_shared_and_pulled_up(self):
        """One EN pin for both drivers, held high by R6 when released."""
        for pin in ('DRIVE A.EN', 'DRIVE B.EN', 'R6.2'):
            self.assertSameNet('XIAO.D9', pin)
        self.assertSameNet('R6.1', 'XIAO.3V3')

    def test_uart_is_one_wire_with_series_tx(self):
        """TX reaches the shared node through R1; RX sits on the node itself."""
        self.assertSameNet('XIAO.TX', 'R1.1')
        for pin in ('R1.2', 'DRIVE A.PDN', 'DRIVE B.PDN'):
            self.assertSameNet('XIAO.RX', pin)
        self.assertDifferentNets('XIAO.TX', 'XIAO.RX')

    def test_driver_addresses(self):
        """MS1 low on A, high on B: UART addresses 0 and 1."""
        self.assertSameNet('DRIVE A.MS1', 'PWR.1')
        self.assertSameNet('DRIVE B.MS1', 'XIAO.3V3')
        for driver in ('DRIVE A', 'DRIVE B'):
            self.assertSameNet('%s.VIO' % driver, 'XIAO.3V3')

    def test_encoders(self):
        """Both encoders on their own bus, each pulled up to 3V3."""
        for xiao, enc, pull in (('D4', 'ENC A.SDA', 'R2'), ('D5', 'ENC A.SCL', 'R3'),
                                ('D2', 'ENC B.SDA', 'R4'), ('D3', 'ENC B.SCL', 'R5')):
            self.assertSameNet('XIAO.%s' % xiao, enc)
            self.assertSameNet('XIAO.%s' % xiao, '%s.2' % pull)
            self.assertSameNet('%s.1' % pull, 'XIAO.3V3')
        for enc in ('ENC A', 'ENC B'):
            self.assertSameNet('%s.3V3' % enc, 'XIAO.3V3')

    def test_motor_phases(self):
        """Red/blue is coil 1, green/black is coil 2, on both wheels."""
        for mot, drv in (('MOT A', 'DRIVE A'), ('MOT B', 'DRIVE B')):
            for colour, phase in (('R', '1A'), ('B', '1B'), ('G', '2A'), ('K', '2B')):
                self.assertSameNet('%s.%s' % (mot, colour), '%s.%s' % (drv, phase))

    def test_spare_pins_are_isolated(self):
        """D0, D8 and D10 are free on this revision and must stay unconnected."""
        for pin in ('D0', 'D8', 'D10'):
            self.assertEqual(self.net('XIAO', pin), {'XIAO.%s' % pin})

    def test_firmware_pin_defaults(self):
        config = (Path(__file__).parent / '../base/main/Kconfig.projbuild').read_text()
        expected = {'EN': 20, 'BATT_ADC': 1, 'TMC_TX': 16, 'TMC_RX': 17,
                    'ENC_A_SDA': 22, 'ENC_A_SCL': 23, 'ENC_B_SDA': 2, 'ENC_B_SCL': 21}
        for name, gpio in expected.items():
            match = re.search(rf'config UBOT_PIN_{name}\b(.*?)(?=\n    config|\nendmenu)',
                              config, re.S)
            self.assertIsNotNone(match, name)
            default = re.search(r'\bdefault (\d+)', match.group(1))
            self.assertEqual(int(default.group(1)), gpio, name)


if __name__ == '__main__':
    unittest.main()
