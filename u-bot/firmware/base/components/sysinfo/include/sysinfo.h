#pragma once
// Who am I: firmware version (from version.txt at build time), hardware
// revision (stored in NVS with `hw set`), device name, serial (the base MAC).
// Shared by the console, the WebSocket status message and the BLE Device
// Information Service so all three agree.
#include <stddef.h>
#include <stdint.h>

#include "esp_err.h"

#ifdef __cplusplus
extern "C" {
#endif

void sysinfo_init(void);

const char *sysinfo_fw_version(void);     // e.g. "0.1.0"
const char *sysinfo_project(void);        // "ubot_base"
const char *sysinfo_build(void);          // "Sep  2 2026 10:15:00"
const char *sysinfo_idf(void);            // "v6.1"
const char *sysinfo_hw_rev(void);         // stored, or CONFIG_UBOT_HW_REV_DEFAULT
esp_err_t sysinfo_set_hw_rev(const char *rev);
const char *sysinfo_name(void);           // stored, or CONFIG_UBOT_NAME_DEFAULT
esp_err_t sysinfo_set_name(const char *name);
const char *sysinfo_serial(void);         // base MAC, 12 hex digits
const char *sysinfo_mac(void);            // base MAC, colon form
const char *sysinfo_reset_reason(void);
const char *sysinfo_partition(void);      // running app partition label
const char *sysinfo_ota_state(void);      // "valid", "pending verify", ...
uint32_t sysinfo_uptime_s(void);

#ifdef __cplusplus
}
#endif
