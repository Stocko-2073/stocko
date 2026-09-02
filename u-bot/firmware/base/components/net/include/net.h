#pragma once
// WiFi station, mDNS (<name>.local), the WebSocket drive server, and HTTPS
// OTA. Credentials come from the console (`wifi set`) and live in NVS; there
// is no captive portal. With no credentials stored the radio stays up for
// scanning and BLE is the way in.
#include <stdbool.h>
#include <stddef.h>

#include "esp_err.h"

#ifdef __cplusplus
extern "C" {
#endif

esp_err_t net_init(void);

esp_err_t net_wifi_set(const char *ssid, const char *pass);
esp_err_t net_wifi_clear(void);
esp_err_t net_wifi_reconnect(void);

typedef void (*net_scan_fn)(const char *ssid, int rssi, const char *auth, void *arg);
// Blocking, a few seconds. Emits the strongest 20.
esp_err_t net_wifi_scan(net_scan_fn emit, void *arg);

typedef struct {
    bool configured, started, connected, server_up;
    char ssid[33];
    char ip[16];
    char hostname[32];
    int rssi;
    int ws_clients;
} net_status_t;

void net_get_status(net_status_t *out);
bool net_connected(void);

// OTA over HTTPS with the built-in certificate bundle (covers Amazon's roots,
// so an S3 URL works as-is). The stored `ota_url` is the bucket base that
// ota_provisioning.sh prints; firmware.bin and version.txt live under it.
//
// net_ota_start(NULL) installs <base>/firmware.bin unconditionally (a full
// .bin URL is also accepted). net_ota_check(install) reads <base>/version.txt
// and compares it with the running version; with install=true it goes on to
// install a newer one, with install=false it only records it, readable via
// net_ota_available(). Installing disables the drivers before writing flash
// and reboots on success; a bad image rolls back on its own. With the
// `ota_auto` setting non-zero, a check-and-install runs every time WiFi
// connects. All of these return at once; the work is on its own task.
esp_err_t net_ota_start(const char *url);
esp_err_t net_ota_check(bool install);
const char *net_ota_available(void);   // newer version seen in the bucket, or ""
bool net_ota_auto(void);
esp_err_t net_ota_set_url(const char *url);
bool net_ota_get_url(char *buf, size_t len);
bool net_ota_busy(void);
const char *net_ota_status(void);
esp_err_t net_ota_confirm(void);

#ifdef __cplusplus
}
#endif
