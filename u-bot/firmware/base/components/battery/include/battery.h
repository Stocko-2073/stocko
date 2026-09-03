#pragma once
// Pack voltage through a divider into ADC1, sampled once a second and lightly
// filtered. The pack is a 12 V 8 Ah LiFePO4 (four cells in series); the
// percentage comes from a resting-voltage table for that chemistry in
// battery.c, 10.0 V empty to 13.6 V full, because its discharge curve is too
// flat for a linear window. The reading sags under motor load, so the
// percentage is pessimistic while driving.
//
//   batt_div    Vpack / Vpin, runtime setting. Default 11.0 (100k over 10k).
//               Calibrate against a meter: the internal pull-down on the pin
//               loads the divider's lower leg.
//
// If nothing is wired to the sense pin the reading floats near zero and
// battery_present() says so; the status reports then say "no sense".
#include <stdbool.h>

#include "esp_err.h"

#ifdef __cplusplus
extern "C" {
#endif

esp_err_t battery_init(void);
float battery_voltage(void);   // pack volts, filtered
int battery_percent(void);     // 0..100, or -1 when not present
int battery_pin_mv(void);      // raw calibrated millivolts at the ADC pin
bool battery_present(void);
void battery_reload_settings(void);

#ifdef __cplusplus
}
#endif
