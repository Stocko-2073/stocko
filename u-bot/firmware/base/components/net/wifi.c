#include <string.h>

#include "esp_event.h"
#include "esp_log.h"
#include "esp_netif.h"
#include "esp_timer.h"
#include "esp_wifi.h"
#include "mdns.h"
#include "net.h"
#include "net_internal.h"
#include "settings.h"
#include "sysinfo.h"

static const char *TAG = "wifi";

static esp_netif_t *s_sta = NULL;
static bool s_configured = false, s_started = false, s_connected = false;
static bool s_mdns_up = false;
static char s_ssid[33], s_pass[65], s_ip[16];
static esp_timer_handle_t s_retry;
static uint32_t s_backoff_ms = 2000;

static void start_services(void) {
    if (!s_mdns_up) {
        esp_err_t err = mdns_init();
        if (err == ESP_OK) {
            mdns_hostname_set(sysinfo_name());
            mdns_instance_name_set("U-BOT base");
            mdns_txt_item_t txt[] = {
                {"fw", sysinfo_fw_version()}, {"hw", sysinfo_hw_rev()}, {"path", "/ws"},
            };
            mdns_service_add(NULL, "_http", "_tcp", 80, txt, 3);
            mdns_service_add(NULL, "_ws", "_tcp", 80, txt, 3);
            s_mdns_up = true;
            ESP_LOGI(TAG, "mDNS: %s.local", sysinfo_name());
        } else {
            ESP_LOGE(TAG, "mdns_init: %s", esp_err_to_name(err));
        }
    }
    if (!ws_server_up()) ws_server_start();
    if (net_ota_auto()) {
        ESP_LOGI(TAG, "ota_auto is set -- checking the bucket for a newer image");
        net_ota_check(true);
    }
}

static void retry_cb(void *arg) {
    if (s_configured && s_started && !s_connected) {
        ESP_LOGI(TAG, "connecting to \"%s\"", s_ssid);
        esp_wifi_connect();
    }
}

static void on_wifi(void *arg, esp_event_base_t base, int32_t id, void *data) {
    switch (id) {
        case WIFI_EVENT_STA_START:
            s_started = true;
            if (s_configured) {
                ESP_LOGI(TAG, "connecting to \"%s\"", s_ssid);
                esp_wifi_connect();
            } else {
                ESP_LOGI(TAG, "no credentials stored -- 'wifi set <ssid> <password>' on the console");
            }
            break;
        case WIFI_EVENT_STA_CONNECTED:
            ESP_LOGI(TAG, "associated with \"%s\", waiting for an address", s_ssid);
            break;
        case WIFI_EVENT_STA_DISCONNECTED: {
            wifi_event_sta_disconnected_t *e = (wifi_event_sta_disconnected_t *)data;
            bool was = s_connected;
            s_connected = false;
            s_ip[0] = 0;
            if (!s_configured) break;
            if (was) ESP_LOGW(TAG, "disconnected from \"%s\" (reason %d), reconnecting", s_ssid, e->reason);
            else ESP_LOGW(TAG, "could not join \"%s\" (reason %d), retrying in %lu s", s_ssid, e->reason,
                          (unsigned long)(s_backoff_ms / 1000));
            esp_timer_stop(s_retry);
            esp_timer_start_once(s_retry, (uint64_t)s_backoff_ms * 1000);
            if (s_backoff_ms < 30000) s_backoff_ms *= 2;
            break;
        }
        default:
            break;
    }
}

static void on_ip(void *arg, esp_event_base_t base, int32_t id, void *data) {
    ip_event_got_ip_t *e = (ip_event_got_ip_t *)data;
    snprintf(s_ip, sizeof s_ip, IPSTR, IP2STR(&e->ip_info.ip));
    s_connected = true;
    s_backoff_ms = 2000;
    ESP_LOGI(TAG, "connected: %s -- http://%s.local/  ws://%s.local/ws", s_ip, sysinfo_name(), sysinfo_name());
    start_services();
}

static void load_creds(void) {
    settings_get_str("wifi_ssid", s_ssid, sizeof s_ssid, "");
    settings_get_str("wifi_pass", s_pass, sizeof s_pass, "");
    s_configured = s_ssid[0] != 0;
}

static void apply_config(void) {
    wifi_config_t wc;
    memset(&wc, 0, sizeof wc);
    strncpy((char *)wc.sta.ssid, s_ssid, sizeof wc.sta.ssid - 1);
    strncpy((char *)wc.sta.password, s_pass, sizeof wc.sta.password - 1);
    wc.sta.threshold.authmode = s_pass[0] ? WIFI_AUTH_WPA2_PSK : WIFI_AUTH_OPEN;
    wc.sta.pmf_cfg.capable = true;
    wc.sta.pmf_cfg.required = false;
    wc.sta.sae_pwe_h2e = WPA3_SAE_PWE_BOTH;
    esp_wifi_set_config(WIFI_IF_STA, &wc);
}

esp_err_t net_init(void) {
    esp_err_t err = esp_netif_init();
    if (err != ESP_OK) return err;
    err = esp_event_loop_create_default();
    if (err != ESP_OK && err != ESP_ERR_INVALID_STATE) return err;
    s_sta = esp_netif_create_default_wifi_sta();
    if (!s_sta) return ESP_FAIL;
    esp_netif_set_hostname(s_sta, sysinfo_name());

    wifi_init_config_t cfg = WIFI_INIT_CONFIG_DEFAULT();
    err = esp_wifi_init(&cfg);
    if (err != ESP_OK) return err;
    esp_event_handler_instance_register(WIFI_EVENT, ESP_EVENT_ANY_ID, on_wifi, NULL, NULL);
    esp_event_handler_instance_register(IP_EVENT, IP_EVENT_STA_GOT_IP, on_ip, NULL, NULL);

    const esp_timer_create_args_t targs = { .callback = retry_cb, .name = "wifi_retry" };
    esp_timer_create(&targs, &s_retry);

    // Credentials live in our own NVS namespace, not the WiFi driver's, so
    // `set`/`unset` and a factory erase see them.
    esp_wifi_set_storage(WIFI_STORAGE_RAM);
    esp_wifi_set_mode(WIFI_MODE_STA);
    load_creds();
    if (s_configured) apply_config();
    return esp_wifi_start();
}

esp_err_t net_wifi_set(const char *ssid, const char *pass) {
    if (!ssid || !*ssid || strlen(ssid) > 32) return ESP_ERR_INVALID_ARG;
    if (pass && strlen(pass) > 63) return ESP_ERR_INVALID_ARG;
    esp_err_t err = settings_set_str("wifi_ssid", ssid);
    if (err == ESP_OK) err = settings_set_str("wifi_pass", pass ? pass : "");
    if (err != ESP_OK) return err;
    load_creds();
    apply_config();
    s_backoff_ms = 2000;
    if (s_started) {
        esp_wifi_disconnect();
        esp_wifi_connect();
    }
    return ESP_OK;
}

esp_err_t net_wifi_clear(void) {
    settings_erase("wifi_ssid");
    settings_erase("wifi_pass");
    load_creds();
    esp_timer_stop(s_retry);
    if (s_started) esp_wifi_disconnect();
    return ESP_OK;
}

esp_err_t net_wifi_reconnect(void) {
    if (!s_configured) return ESP_ERR_INVALID_STATE;
    if (!s_started) return ESP_ERR_INVALID_STATE;
    esp_wifi_disconnect();
    return esp_wifi_connect();
}

static const char *auth_name(wifi_auth_mode_t m) {
    switch (m) {
        case WIFI_AUTH_OPEN: return "open";
        case WIFI_AUTH_WEP: return "WEP";
        case WIFI_AUTH_WPA_PSK: return "WPA";
        case WIFI_AUTH_WPA2_PSK: return "WPA2";
        case WIFI_AUTH_WPA_WPA2_PSK: return "WPA/WPA2";
        case WIFI_AUTH_WPA3_PSK: return "WPA3";
        case WIFI_AUTH_WPA2_WPA3_PSK: return "WPA2/WPA3";
        case WIFI_AUTH_WPA2_ENTERPRISE: return "WPA2-enterprise";
        default: return "other";
    }
}

esp_err_t net_wifi_scan(net_scan_fn emit, void *arg) {
    if (!s_started) return ESP_ERR_INVALID_STATE;
    wifi_scan_config_t sc;
    memset(&sc, 0, sizeof sc);
    esp_err_t err = esp_wifi_scan_start(&sc, true);
    if (err != ESP_OK) return err;
    uint16_t n = 20;
    wifi_ap_record_t recs[20];
    err = esp_wifi_scan_get_ap_records(&n, recs);
    if (err != ESP_OK) return err;
    for (uint16_t i = 0; i < n; i++) {
        if (emit) emit((const char *)recs[i].ssid, recs[i].rssi, auth_name(recs[i].authmode), arg);
    }
    return ESP_OK;
}

void net_get_status(net_status_t *out) {
    if (!out) return;
    memset(out, 0, sizeof *out);
    out->configured = s_configured;
    out->started = s_started;
    out->connected = s_connected;
    out->server_up = ws_server_up();
    out->ws_clients = ws_client_count();
    strncpy(out->ssid, s_ssid, sizeof out->ssid - 1);
    strncpy(out->ip, s_ip, sizeof out->ip - 1);
    strncpy(out->hostname, sysinfo_name(), sizeof out->hostname - 1);
    if (s_connected) {
        wifi_ap_record_t ap;
        if (esp_wifi_sta_get_ap_info(&ap) == ESP_OK) out->rssi = ap.rssi;
    }
}

bool net_connected(void) { return s_connected; }
