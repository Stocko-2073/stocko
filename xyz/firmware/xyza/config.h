#pragma once
#include <Arduino.h>

namespace Config {
constexpr uint8_t dirPins[] = {D0, D2, D4, D8};
constexpr uint8_t stepPins[] = {D1, D3, D5, D9};
constexpr uint8_t enablePin = D10; // A4988 active LOW, shared by all drivers.
// Index = X,Y,Z,A. Working drill driver moved to M0/X; M2/drill is unavailable.
// Axis A stays unmapped until its failed driver is replaced.
constexpr int8_t axisMotor[] = {0, 1, 3, -1};
// Raw jog convention: +X board right, +Y board away from tower, +Z drill UP.
// Bedslinger: for work axes +X right / +Y toward tower / +Z up,
// tool-relative displacement has signs {-1, +1, +1} versus these raw jogs.
// MS2 tied to 3.3 V: quarter-step if MS1/MS3 low.
// XYZ each measured ~2 mm per 200 pulses with a ruler: ~100 pulses/mm,
// provisional only; motion commands still use pulses, not physical units.
constexpr bool inverted[] = {false, false, false, false};
// Per physical motor, so remapping an axis cannot bypass the Z restriction.
// Relative jog caps, not cumulative travel limits or collision protection.
constexpr long maxJogSteps[] = {1000, 2000, 200, 500};
constexpr long defaultRate = 500; // requested cruise rate; clamped to motor cap.
constexpr long maxRate[] = {3000, 3000, 200, 2000}; // pulses/sec; not validated motor limits.
constexpr long acceleration[] = {10000, 10000, 500, 10000}; // pulses/sec^2; XYZ ~100 mm/sec^2.
constexpr size_t profileCapacity = 2000;
constexpr uint32_t pulseUs = 3; // A4988 minimum high/low is 1 us.
constexpr uint32_t armIdleMs = 30000;
}
