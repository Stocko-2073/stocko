/* One coordinator and streaming writer for HTTPS releases and local uploads. */
#include "cJSON.h"
#include "drive.h"
#include "esp_app_desc.h"
#include "esp_app_format.h"
#include "esp_crt_bundle.h"
#include "esp_heap_caps.h"
#include "esp_http_client.h"
#include "esp_http_server.h"
#include "esp_log.h"
#include "esp_ota_ops.h"
#include "esp_system.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/semphr.h"
#include "freertos/task.h"
#include "management.h"
#include "net.h"
#include "psa/crypto.h"
#include "settings.h"
#include "sysinfo.h"
#include <ctype.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static portMUX_TYPE mux = portMUX_INITIALIZER_UNLOCKED;
static void checkpoint(const char *phase) {
  ESP_LOGI("ota", "%s: heap %u, stack reserve %u", phase,
           (unsigned)esp_get_free_heap_size(),
           (unsigned)uxTaskGetStackHighWaterMark(NULL));
}
static bool busy, healthy, pending, boot_gate;
static SemaphoreHandle_t health_lock;
static volatile bool cancelled;
void net_ota_cancel(void) { cancelled = true; }
static char status_text[128] = "idle", available[32];
static int64_t confirm_deadline;
typedef struct {
  char version[32], project[32], target[16], sha[65], image[65], url[256];
  size_t size;
} manifest_t;
typedef struct {
  char state[32], version[32], image[65], sha[65];
} outcome_t;
static outcome_t outcome;
static void status(const char *s) {
  portENTER_CRITICAL(&mux);
  snprintf(status_text, sizeof status_text, "%s", s);
  portEXIT_CRITICAL(&mux);
}
static void persist(const char *s) {
  snprintf(outcome.state, sizeof outcome.state, "%s", s);
  settings_set_blob("ota_outcome", &outcome, sizeof outcome);
}
void net_ota_outcome(char *out, size_t n) {
  snprintf(out, n, "%s version=%s image=%s", outcome.state, outcome.version,
           outcome.image);
}
bool net_ota_busy(void) {
  portENTER_CRITICAL(&mux);
  bool b = busy;
  portEXIT_CRITICAL(&mux);
  return b;
}
const char *net_ota_status(void) { return status_text; }
const char *net_ota_available(void) { return available; }
bool net_ota_can_rollback(void) { return esp_ota_check_rollback_is_possible(); }
bool net_ota_auto(void) { return false; }
bool net_ota_get_url(char *out, size_t n) {
  return settings_get_str("ota_url", out, n, "") && *out;
}
esp_err_t net_ota_set_url(const char *s) {
  if (!s || strncmp(s, "https://", 8) || strlen(s) > 190)
    return ESP_ERR_INVALID_ARG;
  return settings_set_str("ota_url", s);
}
static bool reserve(void) {
  portENTER_CRITICAL(&mux);
  bool ok = !busy;
  if (ok) {
    busy = true;
    cancelled = false;
  }
  portEXIT_CRITICAL(&mux);
  return ok;
}
static void release(bool gate) {
  if (gate)
    drive_maintenance_release(true);
  portENTER_CRITICAL(&mux);
  busy = false;
  portEXIT_CRITICAL(&mux);
}
static bool hex(const char *s) {
  if (!s || strlen(s) != 64)
    return false;
  for (int i = 0; i < 64; i++)
    if (!isxdigit((unsigned char)s[i]))
      return false;
  return true;
}
static bool valid(const manifest_t *m) {
  const esp_partition_t *p = esp_ota_get_next_update_partition(NULL);
  return p && m->size >= 288 && m->size <= p->size &&
         !strcmp(m->project, sysinfo_project()) &&
         !strcmp(m->target, "esp32s3") && m->version[0] && hex(m->sha) &&
         hex(m->image);
}
static bool field(cJSON *r, const char *k, char *out, size_t n) {
  const char *s = cJSON_GetStringValue(cJSON_GetObjectItem(r, k));
  if (!s || strlen(s) >= n)
    return false;
  strcpy(out, s);
  return true;
}
static bool parse_manifest(const char *json, manifest_t *m) {
  cJSON *r = cJSON_Parse(json);
  if (!r)
    return false;
  cJSON *n = cJSON_GetObjectItem(r, "size");
  bool ok = field(r, "version", m->version, sizeof m->version) &&
            field(r, "project", m->project, sizeof m->project) &&
            field(r, "target", m->target, sizeof m->target) &&
            field(r, "sha256", m->sha, sizeof m->sha) &&
            field(r, "image", m->image, sizeof m->image) &&
            field(r, "url", m->url, sizeof m->url) &&
            !strncmp(m->url, "https://", 8) && cJSON_IsNumber(n) &&
            n->valuedouble >= 288 && n->valuedouble <= 0x1e0000 &&
            n->valuedouble == (size_t)n->valuedouble;
  if (ok)
    m->size = (size_t)n->valuedouble;
  cJSON_Delete(r);
  return ok && valid(m);
}
static esp_http_client_handle_t open_url(const char *url) {
  esp_http_client_config_t cfg = {.url = url,
                                  .crt_bundle_attach = esp_crt_bundle_attach,
                                  .timeout_ms = 10000,
                                  .buffer_size = 2048};
  esp_http_client_handle_t h = esp_http_client_init(&cfg);
  if (!h)
    return NULL;
  if (esp_http_client_open(h, 0) != ESP_OK ||
      esp_http_client_fetch_headers(h) < 0 ||
      esp_http_client_get_status_code(h) != 200) {
    esp_http_client_cleanup(h);
    return NULL;
  }
  return h;
}
static bool fetch_manifest(const char *url, manifest_t *m) {
  esp_http_client_handle_t h = open_url(url);
  if (!h)
    return false;
  char text[1536];
  int n = esp_http_client_read_response(h, text, sizeof text - 1);
  bool complete = esp_http_client_is_complete_data_received(h);
  esp_http_client_close(h);
  esp_http_client_cleanup(h);
  if (n <= 0 || n >= sizeof text - 1 || !complete)
    return false;
  text[n] = 0;
  return parse_manifest(text, m);
}
typedef struct {
  esp_ota_handle_t ota;
  psa_hash_operation_t hash;
  size_t got, head_len;
  uint8_t head[288];
  const esp_partition_t *partition;
} writer_t;
static bool writer_init(writer_t *w) {
  memset(w, 0, sizeof *w);
  w->hash = (psa_hash_operation_t)PSA_HASH_OPERATION_INIT;
  w->partition = esp_ota_get_next_update_partition(NULL);
  return psa_crypto_init() == PSA_SUCCESS &&
         psa_hash_setup(&w->hash, PSA_ALG_SHA_256) == PSA_SUCCESS;
}
static void hash_text(const uint8_t *bytes, char *out) {
  for (int i = 0; i < 32; i++)
    sprintf(out + i * 2, "%02x", bytes[i]);
}
static bool writer_feed(writer_t *w, const manifest_t *m, const uint8_t *data,
                        size_t n) {
  if (cancelled || n > m->size - w->got ||
      psa_hash_update(&w->hash, data, n) != PSA_SUCCESS)
    return false;
  w->got += n;
  if (w->head_len < sizeof w->head) {
    size_t part = sizeof w->head - w->head_len;
    if (part > n)
      part = n;
    memcpy(w->head + w->head_len, data, part);
    w->head_len += part;
    data += part;
    n -= part;
    if (w->head_len < sizeof w->head)
      return true;
    esp_image_header_t header;
    esp_app_desc_t desc;
    memcpy(&header, w->head, sizeof header);
    memcpy(&desc, w->head + 32, sizeof desc);
    char image[65];
    hash_text(desc.app_elf_sha256, image);
    if (header.magic != ESP_IMAGE_HEADER_MAGIC ||
        header.chip_id != ESP_CHIP_ID_ESP32S3 ||
        desc.magic_word != ESP_APP_DESC_MAGIC_WORD ||
        !memchr(desc.version, 0, 32) || !memchr(desc.project_name, 0, 32) ||
        strcmp(desc.version, m->version) ||
        strcmp(desc.project_name, m->project) || strcasecmp(image, m->image))
      return false;
    checkpoint("image header validated");
    if (esp_ota_begin(w->partition, m->size, &w->ota) != ESP_OK)
      return false;
    checkpoint("OTA slot ready");
    if (esp_ota_write(w->ota, w->head, sizeof w->head) != ESP_OK)
      return false;
  }
  if (n && esp_ota_write(w->ota, data, n) != ESP_OK)
    return false;
  char progress[64];
  snprintf(progress, sizeof progress, "writing %u%%",
           (unsigned)(w->got * 100 / m->size));
  status(progress);
  return true;
}
static void writer_abort(writer_t *w) {
  if (w->ota)
    esp_ota_abort(w->ota);
  psa_hash_abort(&w->hash);
}
static bool writer_finish(writer_t *w, const manifest_t *m) {
  uint8_t digest[32];
  size_t n;
  char sha[65];
  if (cancelled || w->got != m->size || !w->ota ||
      psa_hash_finish(&w->hash, digest, sizeof digest, &n) != PSA_SUCCESS)
    return false;
  hash_text(digest, sha);
  if (strcasecmp(sha, m->sha))
    return false;
  esp_err_t err = esp_ota_end(w->ota);
  w->ota = 0;
  if (err != ESP_OK)
    return false;
  snprintf(outcome.version, sizeof outcome.version, "%s", m->version);
  snprintf(outcome.image, sizeof outcome.image, "%s", m->image);
  snprintf(outcome.sha, sizeof outcome.sha, "%s", m->sha);
  snprintf(outcome.state, sizeof outcome.state, "pending");
  if (settings_set_blob("ota_outcome", &outcome, sizeof outcome) != ESP_OK)
    return false;
  if (esp_ota_set_boot_partition(w->partition) != ESP_OK) {
    persist("selection failed");
    return false;
  }
  status("written; rebooting for verification");
  return true;
}
static void reboot_candidate(void) {
  vTaskDelay(pdMS_TO_TICKS(1200));
  esp_restart();
}
typedef struct {
  char url[256];
  bool check;
} download_t;
static void download(void *arg) {
  download_t *j = arg;
  manifest_t m = {0};
  writer_t w = {0};
  bool gate = false, ok = false;
  esp_http_client_handle_t h = NULL;
  status("checking manifest");
  checkpoint("manifest request");
  if (!fetch_manifest(j->url, &m)) {
    status("failed: invalid or unavailable manifest");
    goto out;
  }
  checkpoint("manifest validated");
  snprintf(available, sizeof available, "%s", m.version);
  if (cancelled) {
    status("cancelled");
    goto out;
  }
  if (j->check) {
    bool same = !strcmp(m.version, sysinfo_fw_version());
    if (same)
      available[0] = 0;
    status(same ? "up to date" : "release available");
    goto out;
  }
  if (drive_maintenance_claim(true) != ESP_OK) {
    status("failed: active motion");
    goto out;
  }
  gate = true;
  checkpoint("motor interlock acquired");
  if (!writer_init(&w)) {
    status("failed: hash initialization");
    goto out;
  }
  checkpoint("image request");
  h = open_url(m.url);
  checkpoint("image connected");
  if (!h) {
    status("failed: image download");
    goto out;
  }
  int64_t length = esp_http_client_get_content_length(h);
  if (length != (int64_t)m.size) {
    status("failed: image length");
    goto out;
  }
  uint8_t buf[2048];
  while (w.got < m.size) {
    int n = esp_http_client_read(h, (char *)buf, sizeof buf);
    if (n <= 0 || !writer_feed(&w, &m, buf, n)) {
      status("failed: transfer or image validation");
      goto out;
    }
  }
  ok = esp_http_client_is_complete_data_received(h) && writer_finish(&w, &m);
  if (!ok)
    status("failed: size, hash or image validation");
out:
  if (cancelled)
    status("cancelled");
  if (h) {
    esp_http_client_close(h);
    esp_http_client_cleanup(h);
  }
  if (!ok)
    writer_abort(&w);
  free(j);
  if (ok)
    reboot_candidate();
  if (gate)
    persist("transfer failed");
  release(gate);
  vTaskDelete(NULL);
}
static esp_err_t start_download(const char *url, bool check) {
  if (!net_connected())
    return ESP_ERR_INVALID_STATE;
  download_t *j = calloc(1, sizeof *j);
  if (!j)
    return ESP_ERR_NO_MEM;
  if (url && *url) {
    if (strlen(url) >= sizeof j->url || strncmp(url, "https://", 8)) {
      free(j);
      return ESP_ERR_INVALID_ARG;
    }
    strcpy(j->url, url);
  } else {
    char base[200];
    if (!net_ota_get_url(base, sizeof base)) {
      free(j);
      return ESP_ERR_NOT_FOUND;
    }
    size_t n = strlen(base);
    while (n && base[n - 1] == '/')
      base[--n] = 0;
    snprintf(j->url, sizeof j->url, "%s/manifest.json", base);
  }
  j->check = check;
  if (!reserve()) {
    free(j);
    return ESP_ERR_INVALID_STATE;
  }
  if (xTaskCreate(download, "ota", 16384, j, 4, NULL) != pdPASS) {
    free(j);
    release(false);
    return ESP_ERR_NO_MEM;
  }
  return ESP_OK;
}
esp_err_t net_ota_start(const char *url) { return start_download(url, false); }
esp_err_t net_ota_check(bool install) { return start_download(NULL, !install); }
typedef struct {
  httpd_req_t *req;
  manifest_t manifest;
} upload_t;
static void upload(void *arg) {
  upload_t *u = arg;
  writer_t w = {0};
  bool gate = drive_maintenance_claim(true) == ESP_OK, ok = false;
  if (!gate) {
    status("failed: active motion");
    goto out;
  }
  if (!writer_init(&w)) {
    status("failed: hash initialization");
    goto out;
  }
  uint8_t buf[2048];
  while (w.got < u->manifest.size) {
    size_t want = u->manifest.size - w.got;
    if (want > sizeof buf)
      want = sizeof buf;
    int n = httpd_req_recv(u->req, (char *)buf, want);
    if (n <= 0 || !writer_feed(&w, &u->manifest, buf, n)) {
      status("failed: interrupted upload or invalid image");
      goto out;
    }
  }
  ok = writer_finish(&w, &u->manifest);
  if (!ok)
    status("failed: size, hash or image validation");
out:
  if (cancelled)
    status("cancelled");
  if (!ok)
    writer_abort(&w);
  httpd_resp_set_status(u->req, ok ? "200 OK" : "409 Conflict");
  httpd_resp_set_type(u->req, "application/json");
  httpd_resp_sendstr(u->req, ok ? "{\"written\":true,\"confirmed\":false}"
                                : "{\"written\":false}");
  httpd_req_async_handler_complete(u->req);
  free(u);
  if (ok)
    reboot_candidate();
  if (gate)
    persist("transfer failed");
  release(gate);
  vTaskDelete(NULL);
}
static esp_err_t upload_request(httpd_req_t *req) {
  upload_t *u = calloc(1, sizeof *u);
  if (!u) {
    httpd_resp_send_err(req, HTTPD_500_INTERNAL_SERVER_ERROR, "memory");
    return ESP_FAIL;
  }
  manifest_t *m = &u->manifest;
  m->size = req->content_len;
  bool headers = httpd_req_get_hdr_value_str(req, "X-Ubot-Version", m->version,
                                             sizeof m->version) == ESP_OK &&
                 httpd_req_get_hdr_value_str(req, "X-Ubot-Project", m->project,
                                             sizeof m->project) == ESP_OK &&
                 httpd_req_get_hdr_value_str(req, "X-Ubot-Target", m->target,
                                             sizeof m->target) == ESP_OK &&
                 httpd_req_get_hdr_value_str(req, "X-Ubot-SHA256", m->sha,
                                             sizeof m->sha) == ESP_OK &&
                 httpd_req_get_hdr_value_str(req, "X-Ubot-Image", m->image,
                                             sizeof m->image) == ESP_OK;
  if (!headers || !valid(m)) {
    free(u);
    httpd_resp_send_err(req, HTTPD_400_BAD_REQUEST, "invalid image metadata");
    return ESP_FAIL; /* Close without draining an untrusted request body. */
  }
  if (!reserve()) {
    free(u);
    httpd_resp_set_status(req, "409 Conflict");
    httpd_resp_sendstr(req, "update busy");
    return ESP_FAIL;
  }
  if (httpd_req_async_handler_begin(req, &u->req) != ESP_OK) {
    free(u);
    release(false);
    return ESP_FAIL;
  }
  if (xTaskCreate(upload, "ota_upload", 8192, u, 4, NULL) != pdPASS) {
    httpd_resp_send_err(u->req, HTTPD_500_INTERNAL_SERVER_ERROR, "worker");
    httpd_req_async_handler_complete(u->req);
    free(u);
    release(false);
  }
  return ESP_OK;
}
esp_err_t ota_upload_register(httpd_handle_t s) {
  const httpd_uri_t u = {
      .uri = "/ota", .method = HTTP_POST, .handler = upload_request};
  return httpd_register_uri_handler(s, &u);
}
static void health(void *arg) {
  for (;;) {
    vTaskDelay(pdMS_TO_TICKS(500));
    xSemaphoreTake(health_lock, portMAX_DELAY);
    if (!pending) {
      xSemaphoreGive(health_lock);
      vTaskDelete(NULL);
      return;
    }
    if (esp_timer_get_time() >= confirm_deadline) {
      drive_estop();
      if (esp_ota_check_rollback_is_possible()) {
        persist("rollback: confirmation timeout");
        esp_ota_mark_app_invalid_rollback_and_reboot();
      }
      status("unconfirmed: no valid fallback");
      persist("unconfirmed: no fallback");
      xSemaphoreGive(health_lock);
      vTaskDelete(NULL);
      return;
    }
    xSemaphoreGive(health_lock);
  }
}
void net_ota_health_prepare(void) {
  esp_ota_img_states_t state;
  const esp_partition_t *p = esp_ota_get_running_partition();
  if (p && esp_ota_get_state_partition(p, &state) == ESP_OK &&
      state == ESP_OTA_IMG_PENDING_VERIFY)
    boot_gate = drive_maintenance_claim(true) == ESP_OK;
}
void net_ota_health_start(bool services_ready) {
  health_lock = xSemaphoreCreateMutex();
  healthy = services_ready && health_lock;
  settings_get_blob("ota_outcome", &outcome, sizeof outcome);
  esp_ota_img_states_t state;
  const esp_partition_t *p = esp_ota_get_running_partition();
  pending = p && esp_ota_get_state_partition(p, &state) == ESP_OK &&
            state == ESP_OTA_IMG_PENDING_VERIFY;
  if (pending) {
    // USB bootstrap has no OTA transaction in NVS. It still requires the
    // reconnecting installer to supply the expected version and ELF hash.
    if (!outcome.version[0]) {
      snprintf(outcome.version, sizeof outcome.version, "%s",
               sysinfo_fw_version());
      sysinfo_image_id(outcome.image);
      persist("pending bootstrap");
    }
    status("pending updater confirmation");
    confirm_deadline = esp_timer_get_time() + 120000000;
    if (!health_lock ||
        xTaskCreate(health, "ota_health", 4096, NULL, 4, NULL) != pdPASS) {
      drive_estop();
      esp_restart();
    }
  } else if (!strcmp(outcome.state, "pending")) {
    persist("rollback: candidate did not confirm");
    status(outcome.state);
  } else if (outcome.state[0])
    status(outcome.state);
}
esp_err_t net_ota_confirm(void) {
  if (!health_lock)
    return ESP_ERR_INVALID_STATE;
  xSemaphoreTake(health_lock, portMAX_DELAY);
  esp_err_t err = ESP_ERR_INVALID_STATE;
  char image[65];
  sysinfo_image_id(image);
  if (healthy && management_ready() && pending &&
      esp_timer_get_time() < confirm_deadline &&
      !strcmp(outcome.version, sysinfo_fw_version()) &&
      !strcmp(outcome.image, image)) {
    err = esp_ota_mark_app_valid_cancel_rollback();
    if (err == ESP_OK) {
      if (boot_gate) {
        while (!drive_maintenance_release(true))
          vTaskDelay(pdMS_TO_TICKS(10));
        boot_gate = false;
      }
      pending = false;
      persist("confirmed");
      status("confirmed");
    }
  }
  xSemaphoreGive(health_lock);
  return err;
}
