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
bool net_wifi_trial_busy(void);
int net_wifi_trial_result(void);
void net_wifi_trial_cancel(void);
esp_err_t net_wifi_clear(void);
esp_err_t net_wifi_reconnect(void);
// Runtime diagnostic; boot defaults to no modem sleep for responsive control.
esp_err_t net_wifi_power_save(bool enabled);

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

// HTTPS release manifests and local /ota uploads share one streaming writer.
// start(NULL) loads <ota_url>/manifest.json; an explicit URL must name a
// manifest, never an unverified bare .bin. check(false) only discovers.
// Installation locks out motion, verifies metadata/hash and boots pending.
// The updater must confirm the expected identity within 120 seconds.
// All transfers are asynchronous. Automatic installation is disabled.
esp_err_t net_ota_start(const char *url);
esp_err_t net_ota_check(bool install);
const char *net_ota_available(void);   // newer version seen in the bucket, or ""
bool net_ota_auto(void);
esp_err_t net_ota_set_url(const char *url);
bool net_ota_get_url(char *buf, size_t len);
bool net_ota_busy(void);
bool net_ota_can_rollback(void);
void net_ota_cancel(void);
const char *net_ota_status(void);
esp_err_t net_ota_confirm(void);
void net_ota_health_prepare(void);
void net_ota_health_start(bool services_ready);
void net_ota_outcome(char *out, size_t len);

#ifdef __cplusplus
}
#endif
