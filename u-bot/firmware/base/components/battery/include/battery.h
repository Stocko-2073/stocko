#pragma once
// Pack voltage through a divider into ADC1, sampled once a second and lightly
// filtered. The divider ratio and the voltage window that maps to 0..100% are
// runtime settings because the pack has not been chosen:
//
//   batt_div    Vpack / Vpin.  Default 11.0 (100k over 10k).
//   batt_vmin   0%   Default 10.0 V (3S Li-ion cut-off)
//   batt_vmax   100% Default 12.6 V (3S Li-ion full)
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
