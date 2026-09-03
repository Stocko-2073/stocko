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
#include "settings.h"
#include "sysinfo.h"
#include "ulog.h"

static const char *TAG = "main";

static void confirm_image(void) {
    // With rollback enabled the bootloader boots a fresh OTA image exactly
    // once as "pending verify". Getting this far -- drivers probed, console
    // up, radios started -- is the self-test; anything that crashes before
    // here leaves the previous image to boot next time.
    const esp_partition_t *running = esp_ota_get_running_partition();
    esp_ota_img_states_t state;
    if (running && esp_ota_get_state_partition(running, &state) == ESP_OK &&
        state == ESP_OTA_IMG_PENDING_VERIFY) {
        if (esp_ota_mark_app_valid_cancel_rollback() == ESP_OK) {
            ESP_LOGI(TAG, "new firmware %s confirmed valid on %s", sysinfo_fw_version(), running->label);
        } else {
            ESP_LOGE(TAG, "could not mark this image valid -- it will roll back on reboot");
        }
    }
}

void app_main(void) {
    drive_park_en();

    ESP_ERROR_CHECK(settings_init());
    ulog_init();
    sysinfo_init();

    ESP_LOGI(TAG, "U-BOT base %s (built %s), hardware rev %s, %s, serial %s, reset: %s",
             sysinfo_fw_version(), sysinfo_build(), sysinfo_hw_rev(), sysinfo_idf(),
             sysinfo_serial(), sysinfo_reset_reason());

    if (drive_init() != ESP_OK) ESP_LOGE(TAG, "drive did not start -- nothing will move");
    if (battery_init() != ESP_OK) ESP_LOGE(TAG, "battery sense did not start");

    // The console before the radios: a bad WiFi config or a BLE stack that
    // refuses to start must never lock us out of the serial port.
    if (console_start() != ESP_OK) ESP_LOGE(TAG, "console did not start");

    if (ble_init() != ESP_OK) ESP_LOGE(TAG, "BLE did not start");
    if (net_init() != ESP_OK) ESP_LOGE(TAG, "network did not start");

    confirm_image();
}
