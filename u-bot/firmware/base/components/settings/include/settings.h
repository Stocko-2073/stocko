#pragma once
// Persistent settings, one NVS namespace, typed by key. Everything the robot
// has to remember across a reboot goes through here: measured calibration
// (per-chip clock gains, shaft polarity), the robot-frame signs, WiFi
// credentials, the hardware revision, the OTA URL.
//
// Keys are at most 15 characters (an NVS limit). Floats are stored as their
// 32-bit pattern. Getters take a default and never fail; setters report NVS
// errors. Every store is committed immediately.
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#include "esp_err.h"

#ifdef __cplusplus
extern "C" {
#endif

// Initialise NVS (erasing and retrying if the partition is from an older
// layout) and open the namespace.
esp_err_t settings_init(void);

// Returns true if a stored value existed; `out` always holds either the stored
// value or `def`.
bool settings_get_str(const char *key, char *out, size_t len, const char *def);
esp_err_t settings_set_str(const char *key, const char *val);

float settings_get_f32(const char *key, float def);
esp_err_t settings_set_f32(const char *key, float v);

int32_t settings_get_i32(const char *key, int32_t def);
esp_err_t settings_set_i32(const char *key, int32_t v);

bool settings_exists(const char *key);
esp_err_t settings_erase(const char *key);
esp_err_t settings_erase_all(void);

// Walk every key in the namespace. `value` is rendered as text; type is one of
// 's' (string), 'f' (float) or 'i' (int32).
typedef void (*settings_visit_fn)(const char *key, char type, const char *value, void *arg);
void settings_dump(settings_visit_fn visit, void *arg);

#ifdef __cplusplus
}
#endif
