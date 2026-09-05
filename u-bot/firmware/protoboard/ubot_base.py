"""U-BOT base board -- stripboard layout of the breadboard in breadboard.jpeg.

XIAO ESP32-C6 driving two BTT TMC2209 sticks over one UART bus, an AS5600
encoder per wheel, battery sense through a divider. The netlist is the
"Pins, XIAO ESP32-C6" table in ../DRIVE_MECHANISM.md plus
../base/main/Kconfig.projbuild; nothing here was traced off the photo except
the parts count (six resistors: one 1k, five 4.7k).

Run:  python ubot_base.py   ->   ubot_base.pdf (FRONT/BACK/DESIGN build sheet)
                                  ubot_base-label.pdf (silkscreen)
Set designing = True for a one-page DESIGN preview while moving things.

Layout, top to bottom (28 x 22 holes, 71 x 56 mm):

    rows  1- 2   GND and 3V3 rails across the top, spare AUX header on them
    rows  3- 9   XIAO, USB-C at the top edge; encoder headers and pull-ups
                 either side of it, battery divider tap top-left
    rows 10-11   the UART bus and the EN line cross the board here
    rows 12-20   TMC2209 A (left, flipped, motor pins to the left edge) and
                 TMC2209 B (right, motor pins to the right edge); both
                 PDN_UART pins land on row 16, so that strip is the bus
    rows 20-22   12 V screw terminal, bulk cap, GND / divider / VM rails

Most of the copper is autorouted. Four wires are placed by hand (see link())
because the router only enumerates a few tree shapes for nets spanning more
than five rows and needs a nudge on the crowded left edge; it still validates
the whole board with them in place.
"""

from stripboard import project

designing = False

# BTT TMC2209 V1.3 in the StepStick pin order: physical pins 1-8 down the logic
# row, 9-16 back up the power row -- the order dip() wants. Pin 4 is the one
# silkscreened RX (PDN_UART); pin 5 "TX" is unpopulated on this module. Both
# GND pins are one net on the module; only GND1 (beside VM) is wired here.
TMC_PINS = ['EN', 'MS1', 'MS2', 'PDN', 'TX', 'CLK', 'STEP', 'DIR',
            'GND2', 'VIO', '1B', '1A', '2A', '2B', 'GND1', 'VM']


def tmc2209(sb, x, y, name, upside_down=False):
    u = sb.dip(x, y, 6, 8, name, pins=TMC_PINS, upside_down=upside_down, label_scale=0.6)
    sb.keepout(x + 1, y, 5, 8, show=False)   # socketed: no wire ends under the stick
    return u


def link(sb, x, y1, y2, color='y', ref='LINK'):
    """A hand-placed wire between two strips, registered so the router routes
    around it: its ends are pins and the span between them is a keep-out."""
    sb.jumper(x, y1, x, y2, color=color)
    if y2 - y1 > 1:
        sb.keepout(x, y1 + 1, 1, y2 - y1 - 1, show=False)
    return sb._register(ref, {'1': (x, y1), '2': (x, y2)}, (x, y1), True)


def draw(sb):
    sb.text(1, 1, 'U-BOT BASE', x_scale=0.7)

    # --- modules -------------------------------------------------------------
    xiao = sb.xiao(11, 3)                       # rows 3-9, USB-C over rows 1-2
    sb.keepout(12, 1, 5, 9, show=False)         # body + USB overhang
    drvA = tmc2209(sb, 4, 12, 'TMC2209 A', upside_down=True)   # rows 12-19
    drvB = tmc2209(sb, 18, 13, 'TMC2209 B')                    # rows 13-20

    # --- connectors ----------------------------------------------------------
    motA = sb.sip(1, 14, 4, 'MOT A', pins=['1B', '1A', '2A', '2B'], label_scale=0.6)
    motB = sb.sip(28, 15, 4, 'MOT B', pins=['2B', '2A', '1A', '1B'], flip=True, label_scale=0.6)
    encA = sb.sip(7, 5, 4, 'ENC A', pins=['GND', '3V3', 'SDA', 'SCL'], flip=True, label_scale=0.6)
    encB = sb.sip(26, 5, 4, 'ENC B', pins=['3V3', 'GND', 'SDA', 'SCL'], flip=True, label_scale=0.6)
    v5 = sb.sip(26, 3, 2, '5V', pins=['5V', 'GND'], flip=True, label_scale=0.6)
    aux = sb.sip(9, 1, 2, 'AUX', pins=['GND', '3V3'], label_scale=0.6)   # spare logic power
    pwr = sb.terminal(15, 20, 4, mod=2)         # 1 = GND, 2 = VM (12 V pack)
    sb.text(16.6, 20, 'GND', x_scale=0.6)
    sb.text(16.6, 22, 'VM+', x_scale=0.6)
    c1 = sb.cap(12, 20, l=2, upside_down=True)  # 100u bulk: pin 2 (+) on VM

    # --- resistors (pin 1 is the top hole, pin 2 the bottom) -----------------
    r1 = sb.resist(10, 9, '1K', l=1)            # TX -> bus
    r2 = sb.resist(13, 11, '4K7', l=1)          # EN pull-up: row 11 = EN, row 12 = 3V3
    r3 = sb.resist(8, 6, '4K7', l=1)            # SDA A pull-up
    r4 = sb.resist(9, 6, '4K7', l=2)            # SCL A pull-up
    r5 = sb.resist(21, 5, '4K7', l=2)           # SDA B pull-up
    r6 = sb.resist(22, 5, '4K7', l=3)           # SCL B pull-up
    r7 = sb.resist(5, 21, '100K', l=1)          # BATT -> VM
    r8 = sb.resist(6, 4, '10K', l=1)            # BATT -> GND

    # Wheel B is UART address 1: MS1 strapped to 3V3 (VIO). The strap is a wire
    # from the 3V3 strip on row 12 down to MS1's row; declaring it as its own
    # short net keeps the big 3V3 net inside what the router can enumerate.
    strap = link(sb, 16, 12, 14, ref='STRAP')
    # Battery sense: D1's strip (row 4) down the left edge to the divider on row
    # 21. Column 2 is the only free path, so it is placed by hand as well.
    batt = link(sb, 2, 4, 21, color='w', ref='BATT_LINK')
    # Ground down the left edge: encoder A's GND strip (row 5) to driver A's GND
    # (row 18), then to the terminal's GND strip (row 20). Columns 1-3 are the
    # only vertical room on that edge, so these two are placed by hand as well;
    # the router then has one column each left for 3V3 and VM.
    gnd1 = link(sb, 3, 5, 18, color='k', ref='GND_LINK')
    gnd2 = link(sb, 1, 18, 20, color='k', ref='GND_LINK2')

    # --- nets ----------------------------------------------------------------
    sb.net('GND', xiao.pin('GND'), drvB.pin('GND1'), v5.pin('GND'), aux.pin('GND'),
           encA.pin('GND'), encB.pin('GND'), r8.pin(2), gnd1.pin(1), color='k')
    sb.net('GND_A', gnd1.pin(2), drvA.pin('GND1'), gnd2.pin(1), color='k')
    sb.net('GND_PWR', gnd2.pin(2), pwr.pin(1), c1.pin(1), color='k')
    sb.net('3V3', xiao.pin('3V3'), drvA.pin('VIO'), drvB.pin('VIO'), strap.pin(1),
           encA.pin('3V3'), encB.pin('3V3'), aux.pin('3V3'),
           r2.pin(2), r3.pin(1), r4.pin(1), r5.pin(1), r6.pin(1), color='y')
    sb.net('ADDR_B', drvB.pin('MS1'), strap.pin(2), color='y')
    sb.net('VM', drvA.pin('VM'), drvB.pin('VM'), pwr.pin(2), c1.pin(2), r7.pin(2), color='r')
    sb.net('5V', xiao.pin('5V'), v5.pin('5V'), color='w')
    sb.net('EN', xiao.pin('D0'), drvA.pin('EN'), drvB.pin('EN'), r2.pin(1), color='g')
    sb.net('UART', xiao.pin('RX'), drvA.pin('PDN'), drvB.pin('PDN'), r1.pin(2), color='b')
    sb.net('TX', xiao.pin('TX'), r1.pin(1), color='b')
    sb.net('SDA_A', xiao.pin('D4'), encA.pin('SDA'), r3.pin(2))
    sb.net('SCL_A', xiao.pin('D5'), encA.pin('SCL'), r4.pin(2))
    sb.net('SDA_B', xiao.pin('D9'), encB.pin('SDA'), r5.pin(2))
    sb.net('SCL_B', xiao.pin('D8'), encB.pin('SCL'), r6.pin(2))
    sb.net('BATT', xiao.pin('D1'), r8.pin(1), batt.pin(1), color='w')
    sb.net('BATT_DIV', batt.pin(2), r7.pin(1), color='w')
    for ph in ('1A', '1B', '2A', '2B'):
        sb.net(f'A_{ph}', drvA.pin(ph), motA.pin(ph))
        sb.net(f'B_{ph}', drvB.pin(ph), motB.pin(ph))
    # Open, as on the breadboard: MS2/TX/CLK/STEP/DIR on both sticks, MS1 on A,
    # GND2 on both (common with GND1 on the module), D2/D3/D10 on the XIAO.
    # The router isolates each with cuts.

    sb.autoroute(seed=0)


if __name__ == '__main__':
    project(draw, name='ubot_base', width=28, height=22, designing=designing,
            label=True)
