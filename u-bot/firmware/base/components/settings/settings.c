#include "settings.h"

#include <stdio.h>
#include <string.h>

#include "esp_log.h"
#include "nvs.h"
#include "nvs_flash.h"

static const char *TAG = "settings";
static const char *NS = "ubot";
static nvs_handle_t s_nvs = 0;

esp_err_t settings_init(void) {
    esp_err_t err = nvs_flash_init();
    if (err == ESP_ERR_NVS_NO_FREE_PAGES || err == ESP_ERR_NVS_NEW_VERSION_FOUND) {
        ESP_LOGW(TAG, "NVS partition needs erasing (%s)", esp_err_to_name(err));
        ESP_ERROR_CHECK(nvs_flash_erase());
        err = nvs_flash_init();
    }
    if (err != ESP_OK) return err;
    err = nvs_open(NS, NVS_READWRITE, &s_nvs);
    if (err != ESP_OK) ESP_LOGE(TAG, "nvs_open(%s): %s", NS, esp_err_to_name(err));
    return err;
}

bool settings_get_str(const char *key, char *out, size_t len, const char *def) {
    if (!out || len == 0) return false;
    size_t n = len;
    if (s_nvs && nvs_get_str(s_nvs, key, out, &n) == ESP_OK) return true;
    if (def) { strncpy(out, def, len - 1); out[len - 1] = 0; }
    else out[0] = 0;
    return false;
}

esp_err_t settings_set_str(const char *key, const char *val) {
    if (!s_nvs) return ESP_ERR_INVALID_STATE;
    esp_err_t err = nvs_set_str(s_nvs, key, val ? val : "");
    return err == ESP_OK ? nvs_commit(s_nvs) : err;
}

float settings_get_f32(const char *key, float def) {
    uint32_t bits;
    if (s_nvs && nvs_get_u32(s_nvs, key, &bits) == ESP_OK) {
        float f;
        memcpy(&f, &bits, sizeof f);
        return f;
    }
    return def;
}

esp_err_t settings_set_f32(const char *key, float v) {
    if (!s_nvs) return ESP_ERR_INVALID_STATE;
    uint32_t bits;
    memcpy(&bits, &v, sizeof bits);
    esp_err_t err = nvs_set_u32(s_nvs, key, bits);
    return err == ESP_OK ? nvs_commit(s_nvs) : err;
}

int32_t settings_get_i32(const char *key, int32_t def) {
    int32_t v;
    if (s_nvs && nvs_get_i32(s_nvs, key, &v) == ESP_OK) return v;
    return def;
}

esp_err_t settings_set_i32(const char *key, int32_t v) {
    if (!s_nvs) return ESP_ERR_INVALID_STATE;
    esp_err_t err = nvs_set_i32(s_nvs, key, v);
    return err == ESP_OK ? nvs_commit(s_nvs) : err;
}

bool settings_exists(const char *key) {
    if (!s_nvs) return false;
    nvs_type_t t;
    return nvs_find_key(s_nvs, key, &t) == ESP_OK;
}

esp_err_t settings_erase(const char *key) {
    if (!s_nvs) return ESP_ERR_INVALID_STATE;
    esp_err_t err = nvs_erase_key(s_nvs, key);
    if (err == ESP_ERR_NVS_NOT_FOUND) return ESP_OK;
    return err == ESP_OK ? nvs_commit(s_nvs) : err;
}

esp_err_t settings_erase_all(void) {
    if (!s_nvs) return ESP_ERR_INVALID_STATE;
    esp_err_t err = nvs_erase_all(s_nvs);
    return err == ESP_OK ? nvs_commit(s_nvs) : err;
}

void settings_dump(settings_visit_fn visit, void *arg) {
    if (!s_nvs || !visit) return;
    nvs_iterator_t it = NULL;
    esp_err_t err = nvs_entry_find("nvs", NS, NVS_TYPE_ANY, &it);
    while (err == ESP_OK && it) {
        nvs_entry_info_t info;
        nvs_entry_info(it, &info);
        char text[96];
        char type = '?';
        switch (info.type) {
            case NVS_TYPE_STR: {
                type = 's';
                size_t n = sizeof text;
                if (nvs_get_str(s_nvs, info.key, text, &n) != ESP_OK) strcpy(text, "?");
                break;
            }
            case NVS_TYPE_U32: {
                type = 'f';
                float f = settings_get_f32(info.key, 0);
                snprintf(text, sizeof text, "%.6g", f);
                break;
            }
            case NVS_TYPE_I32: {
                type = 'i';
                snprintf(text, sizeof text, "%ld", (long)settings_get_i32(info.key, 0));
                break;
            }
            default:
                snprintf(text, sizeof text, "(type %d)", (int)info.type);
                break;
        }
        visit(info.key, type, text, arg);
        err = nvs_entry_next(&it);
    }
    nvs_release_iterator(it);
}
