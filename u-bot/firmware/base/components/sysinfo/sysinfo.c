#include "sysinfo.h"

#include <stdio.h>
#include <string.h>

#include "esp_app_desc.h"
#include "esp_idf_version.h"
#include "esp_mac.h"
#include "esp_ota_ops.h"
#include "esp_system.h"
#include "esp_timer.h"
#include "sdkconfig.h"
#include "settings.h"

static char s_build[48];
static char s_hw[32];
static char s_name[32];
static char s_serial[16];
static char s_mac[20];

void sysinfo_init(void) {
    const esp_app_desc_t *d = esp_app_get_description();
    snprintf(s_build, sizeof s_build, "%s %s", d->date, d->time);
    uint8_t mac[6] = {0};
    esp_read_mac(mac, ESP_MAC_BASE);
    snprintf(s_serial, sizeof s_serial, "%02X%02X%02X%02X%02X%02X",
             mac[0], mac[1], mac[2], mac[3], mac[4], mac[5]);
    snprintf(s_mac, sizeof s_mac, "%02x:%02x:%02x:%02x:%02x:%02x",
             mac[0], mac[1], mac[2], mac[3], mac[4], mac[5]);
    settings_get_str("hw_rev", s_hw, sizeof s_hw, CONFIG_UBOT_HW_REV_DEFAULT);
    settings_get_str("name", s_name, sizeof s_name, CONFIG_UBOT_NAME_DEFAULT);
}

const char *sysinfo_fw_version(void) { return esp_app_get_description()->version; }
const char *sysinfo_project(void) { return esp_app_get_description()->project_name; }
const char *sysinfo_build(void) { return s_build; }
const char *sysinfo_idf(void) { return esp_app_get_description()->idf_ver; }
const char *sysinfo_hw_rev(void) { return s_hw; }
const char *sysinfo_name(void) { return s_name; }
const char *sysinfo_serial(void) { return s_serial; }
const char *sysinfo_mac(void) { return s_mac; }

esp_err_t sysinfo_set_hw_rev(const char *rev) {
    if (!rev || !*rev || strlen(rev) >= sizeof s_hw) return ESP_ERR_INVALID_ARG;
    esp_err_t err = settings_set_str("hw_rev", rev);
    if (err == ESP_OK) strcpy(s_hw, rev);
    return err;
}

esp_err_t sysinfo_set_name(const char *name) {
    if (!name || !*name || strlen(name) >= sizeof s_name) return ESP_ERR_INVALID_ARG;
    for (const char *p = name; *p; p++) {
        // Doubles as the mDNS host label and the BLE name: keep it a label.
        if (!((*p >= 'a' && *p <= 'z') || (*p >= 'A' && *p <= 'Z') ||
              (*p >= '0' && *p <= '9') || *p == '-')) return ESP_ERR_INVALID_ARG;
    }
    esp_err_t err = settings_set_str("name", name);
    if (err == ESP_OK) strcpy(s_name, name);
    return err;
}

const char *sysinfo_reset_reason(void) {
    switch (esp_reset_reason()) {
        case ESP_RST_POWERON: return "power-on";
        case ESP_RST_EXT: return "external pin";
        case ESP_RST_SW: return "software";
        case ESP_RST_PANIC: return "panic";
        case ESP_RST_INT_WDT: return "interrupt watchdog";
        case ESP_RST_TASK_WDT: return "task watchdog";
        case ESP_RST_WDT: return "other watchdog";
        case ESP_RST_DEEPSLEEP: return "deep sleep wake";
        case ESP_RST_BROWNOUT: return "brownout";
        case ESP_RST_SDIO: return "sdio";
        case ESP_RST_USB: return "usb";
        case ESP_RST_JTAG: return "jtag";
        default: return "unknown";
    }
}

const char *sysinfo_partition(void) {
    const esp_partition_t *p = esp_ota_get_running_partition();
    return p ? p->label : "?";
}

const char *sysinfo_ota_state(void) {
    const esp_partition_t *p = esp_ota_get_running_partition();
    esp_ota_img_states_t st;
    if (!p || esp_ota_get_state_partition(p, &st) != ESP_OK) return "unknown";
    switch (st) {
        case ESP_OTA_IMG_NEW: return "new";
        case ESP_OTA_IMG_PENDING_VERIFY: return "pending verify";
        case ESP_OTA_IMG_VALID: return "valid";
        case ESP_OTA_IMG_INVALID: return "invalid";
        case ESP_OTA_IMG_ABORTED: return "aborted";
        case ESP_OTA_IMG_UNDEFINED: return "undefined (no otadata record)";
        default: return "?";
    }
}

uint32_t sysinfo_uptime_s(void) { return (uint32_t)(esp_timer_get_time() / 1000000); }
