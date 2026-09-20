#include <string.h>
#include <stdlib.h>

#include "esp_event.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "freertos/semphr.h"
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
static SemaphoreHandle_t trial_lock;
static volatile bool trial_busy, trial_cancel;
void net_wifi_trial_cancel(void){trial_cancel=true;}
static volatile int trial_result;
typedef struct {char ssid[33],pass[65];} credentials_t;
bool net_wifi_trial_busy(void){return trial_busy;}
int net_wifi_trial_result(void){return trial_result;}


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

}

static void retry_cb(void *arg) {
    if (s_configured && s_started && !s_connected) {
        ESP_LOGI(TAG, "connecting to configured network");
        esp_wifi_connect();
    }
}

static void on_wifi(void *arg, esp_event_base_t base, int32_t id, void *data) {
    switch (id) {
        case WIFI_EVENT_STA_START:
            s_started = true;
            if (s_configured) {
                ESP_LOGI(TAG, "connecting to configured network");
                esp_wifi_connect();
            } else {
                ESP_LOGI(TAG, "no credentials stored -- 'wifi set <ssid> <password>' on the console");
            }
            break;
        case WIFI_EVENT_STA_CONNECTED:
            ESP_LOGI(TAG, "associated, waiting for address");
            break;
        case WIFI_EVENT_STA_DISCONNECTED: {
            wifi_event_sta_disconnected_t *e = (wifi_event_sta_disconnected_t *)data;
            bool was = s_connected;
            s_connected = false;
            s_ip[0] = 0;
            if (!s_configured) break;
            ESP_LOGW(TAG,"network %s (reason %d)",was?"disconnected":"unavailable",e->reason);
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
    wifi_ap_record_t ap;
    if(esp_wifi_sta_get_ap_info(&ap)!=ESP_OK || strcmp((const char*)ap.ssid,s_ssid))return;
    s_connected = true;
    s_backoff_ms = 2000;
    ESP_LOGI(TAG, "connected: %s -- http://%s.local/  ws://%s.local/ws", s_ip, sysinfo_name(), sysinfo_name());
    start_services();
}

static void load_creds(void) {
    settings_get_str("wifi_ssid", s_ssid, sizeof s_ssid, "");
    settings_get_str("wifi_pass", s_pass, sizeof s_pass, "");
    credentials_t c;
    if(settings_get_blob("wifi_creds",&c,sizeof c)){memcpy(s_ssid,c.ssid,sizeof s_ssid);memcpy(s_pass,c.pass,sizeof s_pass);s_ssid[32]=0;s_pass[64]=0;}
    s_configured = s_ssid[0] != 0;
}

static void apply_config(void) {
    wifi_config_t wc;
    memset(&wc, 0, sizeof wc);
    memcpy(wc.sta.ssid, s_ssid, sizeof wc.sta.ssid);
    strncpy((char *)wc.sta.password, s_pass, sizeof wc.sta.password - 1);
    wc.sta.threshold.authmode = s_pass[0] ? WIFI_AUTH_WPA2_PSK : WIFI_AUTH_OPEN;
    wc.sta.pmf_cfg.capable = true;
    wc.sta.pmf_cfg.required = false;
    wc.sta.sae_pwe_h2e = WPA3_SAE_PWE_BOTH;
    esp_wifi_set_config(WIFI_IF_STA, &wc);
}

esp_err_t net_init(void) {
    trial_lock=xSemaphoreCreateBinary();if(!trial_lock)return ESP_ERR_NO_MEM;
    xSemaphoreGive(trial_lock);
    esp_log_level_set("wifi",ESP_LOG_WARN);
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
    // A teleoperated robot prioritizes command latency over radio power saving.
    // Keep this switchable at runtime for access-point compatibility diagnosis.
    err = net_wifi_power_save(false);
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
    err=ws_server_start();
    if(err!=ESP_OK)return err;
    return esp_wifi_start();
}

esp_err_t net_wifi_power_save(bool enabled) {
    esp_err_t err = esp_wifi_set_ps(enabled ? WIFI_PS_MIN_MODEM : WIFI_PS_NONE);
    if (err == ESP_OK) ESP_LOGI(TAG, "Wi-Fi modem power save %s", enabled ? "on" : "off");
    return err;
}

static void credential_trial(void *arg) {
    credentials_t *candidate=arg;
    esp_timer_stop(s_retry);
    s_configured=false;esp_wifi_disconnect();vTaskDelay(pdMS_TO_TICKS(250));
    s_connected=false;
    memcpy(s_ssid,candidate->ssid,sizeof s_ssid);memcpy(s_pass,candidate->pass,sizeof s_pass);
    s_configured=true;apply_config();s_backoff_ms=1000;esp_wifi_connect();
    int64_t end=esp_timer_get_time()+30000000;
    while(!s_connected && !trial_cancel && esp_timer_get_time()<end)vTaskDelay(pdMS_TO_TICKS(100));
    trial_result=trial_cancel?130:1;
    if(!trial_cancel && s_connected && settings_set_blob("wifi_creds",candidate,sizeof *candidate)==ESP_OK) {
        trial_result=0;ESP_LOGI(TAG,"credential trial committed");
    } else {
        s_configured=false;esp_timer_stop(s_retry);esp_wifi_disconnect();vTaskDelay(pdMS_TO_TICKS(250));
        s_connected=false;load_creds();apply_config();if(s_configured)esp_wifi_connect();
        ESP_LOGW(TAG,"credential trial failed; previous credentials restored");
    }
    memset(candidate,0,sizeof *candidate);free(candidate);
    trial_busy=false;xSemaphoreGive(trial_lock);vTaskDelete(NULL);
}
esp_err_t net_wifi_set(const char *ssid,const char *pass) {
    if(!ssid||!*ssid||strlen(ssid)>32||(pass&&strlen(pass)>63))return ESP_ERR_INVALID_ARG;
    if(!trial_lock||!s_started||xSemaphoreTake(trial_lock,0)!=pdTRUE)return ESP_ERR_INVALID_STATE;
    credentials_t *c=calloc(1,sizeof *c);if(!c){xSemaphoreGive(trial_lock);return ESP_ERR_NO_MEM;}
    strcpy(c->ssid,ssid);if(pass)strcpy(c->pass,pass);
    trial_cancel=false;trial_busy=true;trial_result=-1;
    if(xTaskCreate(credential_trial,"wifi_trial",4096,c,4,NULL)!=pdPASS){free(c);trial_busy=false;xSemaphoreGive(trial_lock);return ESP_ERR_NO_MEM;}
    return ESP_OK;
}

esp_err_t net_wifi_clear(void) {
    if(trial_busy)return ESP_ERR_INVALID_STATE;
    settings_erase("wifi_creds");
    settings_erase("wifi_ssid");
    settings_erase("wifi_pass");
    load_creds();
    esp_timer_stop(s_retry);
    if (s_started) esp_wifi_disconnect();
    return ESP_OK;
}

esp_err_t net_wifi_reconnect(void) {
    if(trial_busy)return ESP_ERR_INVALID_STATE;
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
