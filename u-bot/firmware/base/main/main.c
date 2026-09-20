// U-BOT base firmware: boot order.
//
// Everything interesting lives in components/. This file only decides what
// comes up when, and the order matters in one place: EN is parked high before
// anything else runs, so both TMC2209s are disabled from the first instruction
// -- under UART velocity mode a driver keeps stepping from VACTUAL whether or
// not anyone is talking to it, and EN is the only thing that stops a runaway.
#include "battery.h"
#include "ble.h"
#include "console_cmds.h"
#include "drive.h"
#include "esp_log.h"
#include "esp_ota_ops.h"
#include "net.h"
#include "sdkconfig.h"
#include "settings.h"
#include "sysinfo.h"
#include "ulog.h"

static const char *TAG = "main";

void app_main(void) {
    drive_park_en();

    ESP_ERROR_CHECK(settings_init());
    ulog_init();
    sysinfo_init();

    ESP_LOGI(TAG, "U-BOT base %s (built %s), hardware rev %s, %s, serial %s, reset: %s",
             sysinfo_fw_version(), sysinfo_build(), sysinfo_hw_rev(), sysinfo_idf(),
             sysinfo_serial(), sysinfo_reset_reason());

    if (drive_init() != ESP_OK) ESP_LOGE(TAG, "drive did not start -- nothing will move");
    net_ota_health_prepare();
    if (battery_init() != ESP_OK) ESP_LOGE(TAG, "battery sense did not start");

    // The console before the radios: a bad WiFi config or a BLE stack that
    // refuses to start must never lock us out of the serial port.
    bool services_ready = true;
    if (console_start() != ESP_OK) ESP_LOGE(TAG, "console did not start");

#if CONFIG_UBOT_BLE_ENABLE
    if (ble_init() != ESP_OK) { services_ready=false; ESP_LOGE(TAG, "BLE did not start"); }
#else
    ESP_LOGW(TAG, "BLE disabled for Wi-Fi-only diagnostics");
#endif
    if (net_init() != ESP_OK) { services_ready=false; ESP_LOGE(TAG, "network did not start"); }

    net_ota_health_start(services_ready);
}
