#pragma once
// Pack voltage through a divider into ADC1, sampled once a second and
// filtered over ~5 s, then judged against the configured pack: a percentage
// from that pack's resting-voltage table, and a state the drive acts on. The
// tables and the rules live in battery_model.h, free of ESP-IDF so the host
// tests run them as they are. The reading sags under motor load, so the
// percentage is pessimistic while driving; the sustain times below are what
// keep that sag from tripping the rules.
//
// Packs (batt_pack):
//   li5s   5S Li-ion power-tool pack (the Skil PWR CORE 20 the robot has run
//          on since 2026-09-30), the default. 15.0 V empty to 21.0 V full;
//          warn 16.5 V (3.3 V a cell), cut 15.5 V (3.1 V), hysteresis 0.5 V.
//   lfp4s  12 V 8 Ah LiFePO4, four cells, the pack it was built with. 10.0 V
//          empty to 13.6 V full on a curve too flat for a linear window;
//          warn 12.4 V, cut 11.6 V, hysteresis 0.4 V.
//
// State (battery_state(), a batt_state_t), one step a second:
//   none    nothing at the sense pin. Never stops the robot; a pack that
//           appears starts at ok.
//   ok
//   low     10 s below warn; ok again after 10 s at or above warn + hysteresis.
//   cutoff  20 s below cut, or 5 s of unfiltered readings more than 1 V below
//           it (a pack collapsing under load). Left after 10 s at or above
//           cut + hysteresis, to low or ok by the low rule.
// Each change is logged. Nothing here moves or stops a motor: the drive reads
// battery_state() every control tick and handles cutoff itself.
//
// Settings, persisted and applied at once by battery_setting_set():
//   batt_div     Vpack / Vpin. Default 11.0 (100k over 10k); calibrate it
//                against a meter.
//   batt_pack    li5s | lfp4s. Changing it erases the two overrides below, so
//                the new pack starts from its own thresholds. An unknown
//                stored name falls back to li5s with a warning.
//   batt_warn_v  overrides of the pack's warn and cut; warn must stay above
//   batt_cut_v   cut. li5s cuts within 12.5..20.0 V and warns up to 20.5 V,
//                lfp4s 10.0..13.0 and 13.4. Wide on purpose: a bench can
//                force low (warn 20.5) and then cutoff (cut 20.0) with a
//                charged pack. Stored overrides that break these rules are
//                ignored with a warning.
//
// A reading that makes no sense for the configured pack comes with a hint
// naming the fix (battery_hint()), such as "set batt_pack lfp4s". If nothing
// is wired to the sense pin the reading sits near zero and battery_present()
// says so; the status reports then say "no sense".
#include <stdbool.h>
#include <stddef.h>

#include "battery_model.h"
#include "esp_err.h"

#ifdef __cplusplus
extern "C" {
#endif

esp_err_t battery_init(void);
float battery_voltage(void);   // pack volts, filtered; 0 when not present
int battery_percent(void);     // 0..100 on the configured pack's table, or -1 when not present
int battery_pin_mv(void);      // raw calibrated millivolts at the ADC pin
bool battery_present(void);
// Re-read batt_pack, the overrides and batt_div from NVS and apply them.
void battery_reload_settings(void);

int battery_state(void);                     // a batt_state_t; BATT_NONE until battery_init()
const char *battery_state_name(int state);   // "none", "ok", "low", "cutoff"
const char *battery_pack_name(void);         // the batt_pack in force, "li5s" or "lfp4s"
float battery_warn_v(void);                  // the thresholds in force, overrides included
float battery_cut_v(void);

// batt_div, batt_pack, batt_warn_v or batt_cut_v from its console text:
// validated, stored and applied at once. ESP_ERR_NOT_FOUND for any other
// key, ESP_ERR_INVALID_ARG for a value it refuses (the log says why),
// otherwise the NVS result.
esp_err_t battery_setting_set(const char *key, const char *value);
// The same keys erased and their defaults applied at once. Erasing batt_pack
// erases the overrides too, as setting it does.
esp_err_t battery_setting_unset(const char *key);
// "effective battery settings: batt_pack=li5s batt_warn_v=16.5 batt_cut_v=15.5
// batt_div=11.126", without a newline. Returns what snprintf returns.
int battery_settings_line(char *buf, size_t n);
// One line naming the likely fix when the voltage makes no sense for the
// configured pack, else "". The text is in a static buffer that the next
// call rewrites, so print it straight away.
const char *battery_hint(void);

#ifdef __cplusplus
}
#endif
