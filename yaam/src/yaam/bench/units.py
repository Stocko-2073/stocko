"""Raw bench readings to physical units, for the circuit in WIRING.md."""

import numpy as np

ADC_VREF = 3.3           # XIAO RP2040: ADC_VREF is the 3.3 V rail
ADC_COUNTS = 4096
SHUNT_OHM = 0.1          # INA219 breakout's R100
AS5600_COUNTS = 4096


def angle_rad(raw):
    """AS5600 RAW ANGLE counts to radians in [0, 2pi)."""
    return np.asarray(raw, float) * (2 * np.pi / AS5600_COUNTS)


def unwrap_angle(raw):
    """AS5600 counts to a continuous angle in radians (no jumps at the wrap)."""
    return np.unwrap(angle_rad(raw))


def shunt_amps(raw, shunt_ohm=SHUNT_OHM):
    """INA219 shunt register (10 uV per count) to amps."""
    return np.asarray(raw, float) * 10e-6 / shunt_ohm


def bus_volts(raw):
    """INA219 bus register to volts: bits 15..3 at 4 mV."""
    return ((np.asarray(raw).astype(np.int64) & 0xFFFF) >> 3) * 0.004


def adc_volts(counts):
    """ADC counts (12 bit) at the RP2040 pin."""
    return np.asarray(counts, float) * (ADC_VREF / ADC_COUNTS)


def motor_tap_volts(counts):
    """Motor terminal voltage. Each tap is 20k in series into a node with 20k to
    3V3 and 20k to GND, so V_pin = (V_tap + 3.3) / 3."""
    return 3 * adc_volts(counts) - ADC_VREF


def wiper_volts(counts):
    """Pot wiper voltage through the 1M / 1M divider."""
    return 2 * adc_volts(counts)


def rp2040_celsius(counts):
    """The RP2040's internal sensor, datasheet formula."""
    return 27 - (adc_volts(counts) - 0.706) / 0.001721
