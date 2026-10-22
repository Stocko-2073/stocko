# Higher-voltage driver investigation

2026-09-22. Research only; no hardware or firmware changes implemented.
Target: existing 17HS15-1504S-X1 motors at approximately 1.16 A RMS, with
the proposed Talentcell LF8011 pack (25.6 V nominal, 29.2 V listed maximum).
Higher current and larger motors are optional experiments, not requirements.

Decision (2026-09-22): the owner selected TMC2208 drivers for the 24 V setup.
The investigation below is retained as reference. Exact carrier selection
and implementation details remain to be confirmed.

## Actual pin budget

The protoboard source, README, firmware defaults and current sdkconfig agree:

| XIAO pad | GPIO | Current allocation |
|---|---|---|
| D0 | 1 | Free |
| D1 | 2 | Battery ADC |
| D2 / D3 | 3 / 4 | Encoder B I2C |
| D4 / D5 | 5 / 6 | Encoder A I2C |
| D6 / D7 | 43 / 44 | Shared driver UART TX / RX |
| D8 | 7 | Free |
| D9 | 8 | Shared driver enable |
| D10 | 9 | Free |

Verified with the existing copper-connectivity and firmware-pin tests:
`test_layout.LayoutTests.test_spare_pins_are_isolated` and
`test_layout.LayoutTests.test_firmware_pin_defaults`: 2 tests passed.
This verifies the checked-in design, not physical assembly continuity.
The active sdkconfig uses USB Serial/JTAG for the console; the drive code
uses UART1. UART2 is available in the inspected firmware.

Proposed dual-UART allocation: keep motor A on D6/D7; put motor B on
D8/GPIO7 TX and D10/GPIO9 RX, with another TX series resistor and an isolated
PDN_UART node. D0 stays free. No STEP/DIR connections needed for 2208/2225
velocity mode. Update the driver initialization and settings for the actual
chip; the present code explicitly requires TMC2209 VERSION 0x21 and its
register bit layout. A pin rewire alone is insufficient.

Sources: [board source](../firmware/protoboard/ubot_base.py),
[electrical checks](../firmware/protoboard/test_layout.py),
[firmware defaults](../firmware/base/main/Kconfig.projbuild),
[Seeed pin multiplexing](https://wiki.seeedstudio.com/xiao_esp32s3_pin_multiplexing/).

## Practical candidates

| Chip | Chip operating maximum | Serial motion command | UART addressing | Assessment |
|---|---|---|---|---|
| TMC2208 | 36 V | VACTUAL | Fixed address 0 | Practical with separate UART nodes; confirm exact carrier rating |
| TMC2225 | 36 V | VACTUAL | Fixed address 0 | Overlooked candidate; BTT V1.0 module manual also specifies 36 V |
| TMC2224 | 36 V | VACTUAL | Fixed address 0 | Similar option, no better addressing; inexpensive carrier not verified |
| TMC2240 | 36 V | No 2209-style velocity generator | Up to 8 hardware addresses | Needs host motion generation; BTT V1.0 carrier does not expose UART data |
| TMC5130 | 46 V | Internal ramp/velocity controller | UART supported | Potential, but exact StepStick UART routing not verified |
| TMC5160/A | 60 V | Internal ramp/velocity controller | Two nodes by NAI straps; chaining for more | Strong alternative; carrier ratings and mode straps matter |
| TMC5240 | 36 V | Internal ramp/velocity controller | Up to 8 hardware addresses | Good chip fit; low-cost StepStick not verified |
| TMC5241 | 65 V | Internal ramp/velocity controller | UART supported | Newer chip alternative; low-cost StepStick not verified |

TMC2208/2225 have approximately 1.4 A RMS chip capability, subject to
temperature and PCB cooling. The current operating point needs a thermal
check on the selected carrier. They do not provide TMC2209 StallGuard4;
our existing slip detection uses output encoders, so this is not a loss of
the robot's existing encoder-based slip protection.

### BTT TMC2225 V1.0

Manufacturer manual specifies 4.75-36 V, UART and an internal pulse generator.
It shows the ordinary two-row StepStick layout. Counting down the control
row from EN, position 4 is UART by default and position 5 is unconnected.
R3 can bridge them or add a series resistor. This resembles our use of
position 4 on the current BTT 2209, but each motor needs a separate bus node.
Remove the obsolete address strap and configure current sensing, register
fields and clock calibration for the replacement. Current price/stock was
not established; availability is a separate purchasing check.

[BTT manual](https://github.com/bigtreetech/BIGTREETECH-TMC2225-V1.0/blob/master/TMC2225%20V1.0%20manual.pdf)

### BTT TMC2240 V1.0: correction to initial recommendation

The chip supports multi-address UART configuration, but not the 2209's
VACTUAL motion-command mechanism. Its actual register map omits that
register despite misleading generic examples elsewhere in its datasheet.

The BTT schematic has UART_EN pull-up R4 marked not populated and
DIAG1/SW (the UART data pin) marked unconnected. The auxiliary header
exposes DIAG0 and AIN, not DIAG1/SW. UART use therefore requires board-level
rework, not just moving the existing UART wire. J1 position 6 is CLK in the
actual schematic; BTT's generic wiki table says DIAG and is not reliable for
this revision. Do not use the earlier conversation's generic pin table as
a wiring instruction.

[BTT schematic](https://github.com/bigtreetech/BIGTREETECH-Stepper-Motor-Driver/blob/master/TMC2240/Hardware/TMC2240_V1.0-SCH.pdf),
[ADI register definitions](https://github.com/analogdevicesinc/TMC-API/blob/master/tmc/ic/TMC2240/TMC2240_HW_Abstraction.h),
[datasheet](https://www.analog.com/media/en/technical-documentation/data-sheets/tmc2240_datasheet.pdf).

### Watterott TMC5160 v1.5

Manufacturer documents UART mode with both SPI_MODE and SD_MODE low.
The schematic exposes DIAG1/SWP and DIAG0/SWN on the auxiliary header;
the mode jumpers have pull-downs when opened. The chip datasheet allows
two UART nodes by strapping NAI (SDI) differently. Single-wire operation
at 3.3 V also needs the documented SWN midpoint bias, so it is not an
identical electrical interface to the 2209.

Thus this exact module family can preserve one shared serial bus with
module configuration and wiring changes. Carrier supply ratings are
35 V or 50 V by variant, not automatically the chip's 60 V.

Alternatively, use SPI plus the internal motion controller: three shared
SPI signals and two chip-selects replace our two UART pins and use all
three free pads. Shared enable remains separate. This avoids host STEP
pulses but requires SD_MODE configuration and a new driver backend.
Do not assume printer-oriented modules ship with the motion controller
enabled, or that other 5160 carriers expose the same jumpers.

[Watterott pinout/mode guide](https://learn.watterott.com/silentstepstick/pinconfig/tmc5160/),
[v1.5 schematic](https://github.com/watterott/SilentStepStick/blob/master/hardware/SilentStepStick-TMC5160_v15.pdf),
[chip UART addressing and electrical interface](https://www.analog.com/media/en/technical-documentation/data-sheets/tmc5160a_datasheet_rev1.18.pdf).

## Other families checked

- TMC2209/2226: 29 V operating maximum, do not solve the battery issue.
- TMC2130/2160: higher-voltage SPI-configured drivers, require host stepping.
- TMC2241: newer 65 V UART/SPI driver; do not infer a motion controller from
  UART support or the similar 5241 name. Not a verified carrier option.
- TMC5262: newer 65 V integrated driver/controller, SPI rather than UART;
  potentially relevant with redesigned hardware, no inexpensive StepStick verified.
- TMC2262: 65 V SPI driver, no matching serial motion-controller advantage.
- TMC5161: manufacturer now marks it obsolete.
- TMC5072/5272 dual-axis devices: insufficient supply-voltage range for this pack.

Primary product sources:
[2208](https://www.analog.com/en/products/tmc2208.html),
[2224](https://www.analog.com/en/products/tmc2224.html),
[2225](https://www.analog.com/media/en/technical-documentation/data-sheets/TMC2225_datasheet_rev1.15.pdf),
[2226](https://www.analog.com/media/en/technical-documentation/data-sheets/TMC2226_datasheet_rev1.10.pdf),
[2130](https://www.analog.com/media/en/technical-documentation/data-sheets/tmc2130_datasheet_rev1.15.pdf),
[5130](https://www.analog.com/en/products/tmc5130.html),
[5240](https://www.analog.com/media/en/technical-documentation/data-sheets/tmc5240.pdf),
[2241](https://www.analog.com/en/products/tmc2241.html),
[5241](https://www.analog.com/en/products/tmc5241.html),
[5262](https://www.analog.com/en/products/tmc5262.html),
[2262](https://www.analog.com/en/products/tmc2262.html),
[5161](https://www.analog.com/en/products/tmc5161.html),
[5072](https://www.analog.com/en/products/tmc5072.html),
[5272](https://www.analog.com/en/products/tmc5272.html).

## Selection and remaining implementation details

Use the selected TMC2208 family for the 24 V setup. Confirm the exact carrier's
voltage rating and current sensing, and implement separate UART nodes and
the chip-specific firmware changes described above. Target the existing
motor current initially, subject to the selected carrier's thermal capability.

The protoboard BOM also permits a 25 V bulk capacitor and has a battery-fed
5 V buck of unspecified voltage rating. Those parts need checking for the
29.2 V pack regardless of driver choice; battery state-of-charge firmware
currently uses a 4S LiFePO4 curve and needs an 8S profile for the new pack.
