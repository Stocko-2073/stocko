#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include <stdarg.h>

#include "drive.h"
#include "esp_crt_bundle.h"
#include "esp_http_client.h"
#include "esp_https_ota.h"
#include "esp_log.h"
#include "esp_ota_ops.h"
#include "esp_system.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "net.h"
#include "settings.h"
#include "sysinfo.h"

static const char *TAG = "ota";

static volatile bool s_busy = false;
static char s_status[128] = "idle";
static char s_available[32] = "";   // a version in the bucket newer than the running one, or ""

static void set_status(const char *fmt, ...) __attribute__((format(printf, 1, 2)));
static void set_status(const char *fmt, ...) {
    va_list ap;
    va_start(ap, fmt);
    vsnprintf(s_status, sizeof s_status, fmt, ap);
    va_end(ap);
}

typedef struct {
    char image_url[220];
    char version_url[220];   // empty: update unconditionally
    bool check_only;         // compare and report; do not install
} ota_job_t;

// Parse "MAJOR.MINOR.PATCH" (anything after is ignored). Returns false if it
// does not start that way.
static bool parse_version(const char *s, int *maj, int *min, int *pat) {
    return s && sscanf(s, "%d.%d.%d", maj, min, pat) == 3;
}

// > 0 if a is newer than b, 0 if equal, < 0 if older.
static int compare_versions(const char *a, const char *b) {
    int a1, a2, a3, b1, b2, b3;
    if (!parse_version(a, &a1, &a2, &a3) || !parse_version(b, &b1, &b2, &b3)) return strcmp(a, b);
    if (a1 != b1) return a1 - b1;
    if (a2 != b2) return a2 - b2;
    return a3 - b3;
}

// GET a small text object over HTTPS into buf. Returns false on any failure.
static bool fetch_text(const char *url, char *buf, size_t len) {
    esp_http_client_config_t hc = {
        .url = url,
        .crt_bundle_attach = esp_crt_bundle_attach,
        .timeout_ms = 15000,
    };
    esp_http_client_handle_t c = esp_http_client_init(&hc);
    if (!c) return false;
    bool ok = false;
    if (esp_http_client_open(c, 0) == ESP_OK) {
        esp_http_client_fetch_headers(c);
        int status = esp_http_client_get_status_code(c);
        int n = esp_http_client_read_response(c, buf, (int)len - 1);
        if (status == 200 && n > 0) {
            buf[n] = 0;
            ok = true;
        } else {
            ESP_LOGE(TAG, "GET %s: HTTP %d, %d bytes", url, status, n);
        }
        esp_http_client_close(c);
    } else {
        ESP_LOGE(TAG, "GET %s: could not connect", url);
    }
    esp_http_client_cleanup(c);
    return ok;
}

static void ota_task(void *arg) {
    ota_job_t *job = (ota_job_t *)arg;
    const char *url = job->image_url;

    if (job->version_url[0]) {
        set_status("checking version");
        char remote[48];
        if (!fetch_text(job->version_url, remote, sizeof remote)) {
            set_status("check failed: could not read version.txt");
            goto out;
        }
        // Trim trailing whitespace/newline.
        for (size_t i = strlen(remote); i > 0 && (remote[i - 1] == '\n' || remote[i - 1] == '\r' || remote[i - 1] == ' '); i--) remote[i - 1] = 0;
        int cmp = compare_versions(remote, sysinfo_fw_version());
        if (cmp <= 0) {
            s_available[0] = 0;
            ESP_LOGI(TAG, "bucket has %s, running %s -- %s", remote, sysinfo_fw_version(),
                     cmp == 0 ? "up to date" : "running is newer");
            set_status("up to date (%s)", sysinfo_fw_version());
            goto out;
        }
        strncpy(s_available, remote, sizeof s_available - 1);
        if (job->check_only) {
            ESP_LOGI(TAG, "bucket has %s, running %s -- update available", remote, sysinfo_fw_version());
            set_status("update available: %s", remote);
            goto out;
        }
        ESP_LOGI(TAG, "bucket has %s, running %s -- updating", remote, sysinfo_fw_version());
        // Only now take the drivers down: a check that finds nothing must not
        // stop a robot that was driving.
        drive_enable(false);
    }

    ESP_LOGI(TAG, "downloading %s", url);
    set_status("connecting");

    esp_http_client_config_t hc = {
        .url = url,
        .crt_bundle_attach = esp_crt_bundle_attach,
        .timeout_ms = 20000,
        .keep_alive_enable = true,
        .buffer_size_tx = 1024,
    };
    esp_https_ota_config_t oc = { .http_config = &hc };
    esp_https_ota_handle_t h = NULL;
    esp_err_t err = esp_https_ota_begin(&oc, &h);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "begin failed: %s", esp_err_to_name(err));
        set_status("failed: %s", esp_err_to_name(err));
        goto out;
    }

    esp_app_desc_t desc;
    if (esp_https_ota_get_img_desc(h, &desc) == ESP_OK) {
        ESP_LOGI(TAG, "image: %s %s built %s %s (running %s)", desc.project_name, desc.version,
                 desc.date, desc.time, sysinfo_fw_version());
        if (strcmp(desc.project_name, sysinfo_project()) != 0) {
            ESP_LOGE(TAG, "image is for project '%s', not '%s' -- refusing", desc.project_name, sysinfo_project());
            set_status("failed: wrong project '%s'", desc.project_name);
            esp_https_ota_abort(h);
            goto out;
        }
    }

    int total = esp_https_ota_get_image_size(h);
    int lastPct = -10;
    for (;;) {
        err = esp_https_ota_perform(h);
        if (err != ESP_ERR_HTTPS_OTA_IN_PROGRESS) break;
        int got = esp_https_ota_get_image_len_read(h);
        int pct = total > 0 ? got * 100 / total : 0;
        if (pct >= lastPct + 10) {
            lastPct = pct;
            ESP_LOGI(TAG, "%d%% (%d of %d bytes)", pct, got, total);
            set_status("downloading %d%%", pct);
        }
    }
    if (err != ESP_OK || !esp_https_ota_is_complete_data_received(h)) {
        ESP_LOGE(TAG, "download failed: %s", esp_err_to_name(err));
        set_status("failed: %s", esp_err_to_name(err));
        esp_https_ota_abort(h);
        goto out;
    }
    err = esp_https_ota_finish(h);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "finish failed: %s", esp_err_to_name(err));
        set_status("failed: %s", esp_err_to_name(err));
        goto out;
    }
    ESP_LOGI(TAG, "update written, rebooting into it -- it must boot and reach the console to stay");
    set_status("done, rebooting");
    vTaskDelay(pdMS_TO_TICKS(1000));
    esp_restart();

out:
    free(job);
    s_busy = false;
    vTaskDelete(NULL);
}

// The stored ota_url is the bucket base, e.g.
// https://ubot-ota-1234.s3.us-east-1.amazonaws.com -- firmware.bin and
// version.txt live under it, the layout push_firmware.sh produces. A full
// image URL (ending in .bin) is accepted too, for one-off installs.
static bool base_url(char *buf, size_t len) {
    if (!settings_get_str("ota_url", buf, len, "") || !buf[0]) return false;
    size_t n = strlen(buf);
    while (n > 0 && buf[n - 1] == '/') buf[--n] = 0;
    return true;
}

static esp_err_t launch(const ota_job_t *tmpl, bool disable_now) {
    if (s_busy) return ESP_ERR_INVALID_STATE;
    if (!net_connected()) {
        set_status("failed: wifi not connected");
        return ESP_ERR_INVALID_STATE;
    }
    if (strncmp(tmpl->image_url, "https://", 8) != 0) {
        set_status("failed: url must be https://");
        return ESP_ERR_INVALID_ARG;
    }
    ota_job_t *job = malloc(sizeof *job);
    if (!job) return ESP_ERR_NO_MEM;
    *job = *tmpl;
    // A robot should not be driving while its firmware is replaced, and the
    // reboot at the end would disable the drivers anyway. Do it now, cleanly.
    if (disable_now) drive_enable(false);
    s_busy = true;
    if (xTaskCreate(ota_task, "ota", 8192, job, 5, NULL) != pdPASS) {
        free(job);
        s_busy = false;
        return ESP_ERR_NO_MEM;
    }
    return ESP_OK;
}

esp_err_t net_ota_start(const char *url) {
    ota_job_t job = {0};
    if (url && *url) {
        if (strlen(url) >= sizeof job.image_url) return ESP_ERR_INVALID_ARG;
        strcpy(job.image_url, url);
    } else {
        char base[200];
        if (!base_url(base, sizeof base)) {
            set_status("failed: no url -- 'set ota_url https://...'");
            return ESP_ERR_NOT_FOUND;
        }
        size_t n = strlen(base);
        if (n > 4 && strcmp(base + n - 4, ".bin") == 0) strcpy(job.image_url, base);
        else snprintf(job.image_url, sizeof job.image_url, "%s/firmware.bin", base);
    }
    return launch(&job, true);
}

esp_err_t net_ota_check(bool install) {
    char base[200];
    if (!base_url(base, sizeof base)) {
        set_status("failed: no url -- 'set ota_url https://...'");
        return ESP_ERR_NOT_FOUND;
    }
    ota_job_t job = {0};
    snprintf(job.image_url, sizeof job.image_url, "%s/firmware.bin", base);
    snprintf(job.version_url, sizeof job.version_url, "%s/version.txt", base);
    job.check_only = !install;
    return launch(&job, false);
}

const char *net_ota_available(void) { return s_available; }

esp_err_t net_ota_set_url(const char *url) {
    if (!url || strncmp(url, "https://", 8) != 0 || strlen(url) > 190) return ESP_ERR_INVALID_ARG;
    return settings_set_str("ota_url", url);
}

bool net_ota_auto(void) { return settings_get_i32("ota_auto", 0) != 0; }

bool net_ota_get_url(char *buf, size_t len) {
    return settings_get_str("ota_url", buf, len, "") && buf[0];
}

bool net_ota_busy(void) { return s_busy; }
const char *net_ota_status(void) { return s_status; }

esp_err_t net_ota_confirm(void) { return esp_ota_mark_app_valid_cancel_rollback(); }
