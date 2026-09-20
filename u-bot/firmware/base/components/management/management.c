#include "management.h"
#include "cJSON.h"
#include "drive.h"
#include "esp_app_desc.h"
#include "esp_random.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/queue.h"
#include "freertos/semphr.h"
#include "freertos/task.h"
#include "net.h"
#include "sysinfo.h"
#include "ulog.h"
#include <math.h>
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define JOBS 4
#define OUT_DEPTH 4
#define RESULT_SIZE 4096
/* All state is protected by mu. No transport or drive calls while holding mu.
 */
typedef struct {
  mgmt_client_t handle;
  QueueHandle_t out;
  uint32_t last_id, dropped, cursor, sample_seq;
  float hz;
  int64_t next_sample;
  bool logs;
} client_t;
typedef struct {
  uint32_t id, request;
  mgmt_client_t client;
  int code, kind, wheel;
  bool done, cancelled;
  int64_t started, deadline, lease, finish_at, progress_at;
  uint32_t lease_seq;
  char result[RESULT_SIZE];
  unsigned truncated, sent;
  bool notified;
} job_t;
typedef struct {
  uint32_t job;
  char request[MGMT_REQUEST];
} work_t;
static client_t clients[MGMT_CLIENTS];
static job_t jobs[JOBS];
static uint32_t next_client, next_job, active;
static SemaphoreHandle_t mu;
static QueueHandle_t work;
static command_handler_t handler;
static TaskHandle_t worker_handle;
static char boot[17];
static bool ready;
static volatile bool stop_requested;
static void take(void) { xSemaphoreTake(mu, portMAX_DELAY); }
static void give(void) { xSemaphoreGive(mu); }
static client_t *client(mgmt_client_t h) {
  for (int i = 0; i < MGMT_CLIENTS; i++)
    if (h && clients[i].handle == h)
      return &clients[i];
  return NULL;
}
static job_t *job(uint32_t id) {
  if (id)
    for (int i = 0; i < JOBS; i++)
      if (jobs[i].id == id)
        return &jobs[i];
  return NULL;
}
static void emit(mgmt_client_t h, cJSON *r) {
  client_t *c = client(h);
  if (c && r) {
    cJSON_AddNumberToObject(r, "dropped", c->dropped);
    char *s = cJSON_PrintUnformatted(r);
    char frame[MGMT_FRAME];
    if (s && strlen(s) < sizeof frame) {
      strcpy(frame, s);
      if (xQueueSend(c->out, frame, 0) != pdTRUE)
        c->dropped++;
    } else
      c->dropped++;
    free(s);
  }
  cJSON_Delete(r);
}
static cJSON *event(const char *type, uint32_t id, uint32_t jid) {
  cJSON *r = cJSON_CreateObject();
  cJSON_AddStringToObject(r, "type", type);
  cJSON_AddNumberToObject(r, "id", id);
  if (jid)
    cJSON_AddNumberToObject(r, "job", jid);
  return r;
}
// Never split a UTF-8 code point across output frames or truncation boundaries.
static size_t text_prefix(const char *text, size_t limit) {
  size_t n = strlen(text);
  if (n <= limit)
    return n;
  n = limit;
  while (n && ((unsigned char)text[n] & 0xc0) == 0x80)
    n--;
  return n;
}
static void finish(job_t *j, int code) {
  j->done = true;
  j->code = code;
}
static void reply_error(mgmt_client_t h, uint32_t id, int code,
                        const char *why) {
  cJSON *r = event("finished", id, 0);
  cJSON_AddNumberToObject(r, "code", code);
  cJSON_AddStringToObject(r, code ? "error" : "message", why);
  emit(h, r);
}
const char *management_boot_id(void) { return boot; }
bool management_ready(void) { return ready; }
void management_stop(bool emergency) {
  stop_requested = true;
  drive_maintenance_cancel();
  /* E-stop also aborts calibration without waiting for its drive mutex. */
  if (emergency)
    drive_estop();
  else {
    drive_calibrate_abort();
    drive_stop();
  }
}
mgmt_client_t management_open(void) {
  if (!mu)
    return 0;
  take();
  mgmt_client_t h = 0;
  for (int i = 0; i < MGMT_CLIENTS; i++)
    if (!clients[i].handle) {
      client_t *c = &clients[i];
      QueueHandle_t q = xQueueCreate(OUT_DEPTH, MGMT_FRAME);
      if (!q)
        break;
      memset(c, 0, sizeof *c);
      c->out = q;
      xQueueReset(q);
      c->handle = h = ++next_client;
      cJSON *r = event("hello", 0, 0);
      cJSON_AddNumberToObject(r, "protocol", 1);
      cJSON_AddNumberToObject(r, "session", h);
      cJSON_AddStringToObject(r, "boot", boot);
      cJSON_AddStringToObject(r, "version", sysinfo_fw_version());
      cJSON_AddStringToObject(r, "project", sysinfo_project());
      cJSON_AddStringToObject(r, "target", "esp32s3");
      char sha[65];
      sysinfo_image_id(sha);
      cJSON_AddStringToObject(r, "image", sha);
      cJSON_AddStringToObject(
          r, "capabilities",
          "exec,jobs,cancel,lease,logs,stream,wifi,ota,confirm");
      cJSON_AddNumberToObject(r, "max_request", MGMT_REQUEST - 1);
      emit(h, r);
      break;
    }
  give();
  return h;
}
void management_close(mgmt_client_t h) {
  if (!mu)
    return;
  take();
  client_t *c = client(h);
  if (c) {
    c->handle = 0;
    vQueueDelete(c->out);
    c->out = NULL;
  }
  give();
}
bool management_pop(mgmt_client_t h, char out[MGMT_FRAME]) {
  if (!mu)
    return false;
  take();
  client_t *c = client(h);
  bool ok = c && xQueueReceive(c->out, out, 0) == pdTRUE;
  give();
  return ok;
}
void command_printf(command_context_t *ctx, const char *fmt, ...) {
  char buf[512];
  va_list ap;
  va_start(ap, fmt);
  int len = vsnprintf(buf, sizeof buf, fmt, ap);
  va_end(ap);
  take();
  job_t *j = job(ctx->job);
  if (j) {
    size_t used = strlen(j->result), n = strlen(buf),
           room = sizeof j->result - used - 1;
    size_t copy = n < room ? n : text_prefix(buf, room);
    memcpy(j->result + used, buf, copy);
    j->result[used + copy] = 0;
    if (len > 0)
      j->truncated += (unsigned)len - copy;
  }
  give();
}
int management_stream(mgmt_client_t h, float hz) {
  if (!isfinite(hz) || hz < 0 || hz > 50 || (hz > 0 && hz < 0.5f))
    return 2;
  take();
  client_t *c = client(h);
  if (c)
    c->hz = hz;
  give();
  return c ? 0 : 1;
}
static bool number(cJSON *r, const char *name, uint32_t *out) {
  cJSON *v = cJSON_GetObjectItem(r, name);
  if (!cJSON_IsNumber(v) || v->valuedouble < 1 || v->valuedouble > UINT32_MAX ||
      floor(v->valuedouble) != v->valuedouble)
    return false;
  *out = (uint32_t)v->valuedouble;
  return true;
}
esp_err_t management_receive(mgmt_client_t h, const char *json) {
  if (!mu || !json || strlen(json) >= MGMT_REQUEST)
    return ESP_ERR_INVALID_ARG;
  cJSON *r = cJSON_ParseWithOpts(json, NULL, true);
  uint32_t id = 0;
  const char *op = cJSON_GetStringValue(cJSON_GetObjectItem(r, "op"));
  take();
  client_t *c = client(h);
  if (!c) {
    give();
    cJSON_Delete(r);
    return ESP_ERR_INVALID_STATE;
  }
  uint32_t session = 0;
  if (!op || !number(r, "session", &session) || session != h ||
      !number(r, "id", &id) || id <= c->last_id) {
    reply_error(h, id, 2, "invalid or replayed request id");
    goto out;
  }
  c->last_id = id;
  if (cJSON_HasObjectItem(r, "deadline_ms")) {
    uint32_t deadline;
    if (!number(r, "deadline_ms", &deadline) || deadline > 3600000) {
      reply_error(h, id, 2, "deadline must be 1..3600000 ms");
      goto out;
    }
  }
  if (!strcmp(op, "exec")) {
    cJSON *a = cJSON_GetObjectItem(r, "args");
    const char *cmd = cJSON_GetStringValue(cJSON_GetArrayItem(a, 0));
    const char *sub = cJSON_GetStringValue(cJSON_GetArrayItem(a, 1));
    if (cmd && (!strcmp(cmd, "stop") || !strcmp(cmd, "disable") ||
                !strcmp(cmd, "estop") ||
                (sub && ((!strcmp(cmd, "cal") && !strcmp(sub, "abort")) ||
                         (!strcmp(cmd, "demo") && !strcmp(sub, "stop"))))))
      op = !strcmp(cmd, "disable") || !strcmp(cmd, "estop") ? "estop" : "stop";
  }
  if (!strcmp(op, "stop") || !strcmp(op, "estop") || !strcmp(op, "cancel")) {
    uint32_t jid = 0;
    if (!strcmp(op, "cancel")) {
      if (!number(r, "job", &jid) || !job(jid) || job(jid)->done) {
        reply_error(h, id, 2, "job not active");
        goto out;
      }
      job(jid)->cancelled = true;
    }
    if (!jid)
      for (int k = 0; k < JOBS; k++)
        if (jobs[k].id && !jobs[k].done)
          jobs[k].cancelled = true;
    bool halt = !jid || jid == active;
    int cancel_kind = jid ? job(jid)->kind : 0;
    give();
    if (cancel_kind == 6)
      net_ota_cancel();
    if (cancel_kind == 7)
      net_wifi_trial_cancel();
    if (halt)
      management_stop(!strcmp(op, "estop"));
    take();
    reply_error(h, id, 0, "stopped");
    goto out;
  }
  if (!strcmp(op, "renew")) {
    uint32_t jid = 0, seq = 0;
    job_t *j = NULL;
    if (number(r, "job", &jid))
      j = job(jid);
    if (!j || j->done || j->client != h || !j->lease ||
        esp_timer_get_time() >= j->lease || !number(r, "seq", &seq) ||
        seq <= j->lease_seq) {
      reply_error(h, id, 1, "lease expired, wrong owner, or replay");
      goto out;
    }
    j->lease_seq = seq;
    j->lease = esp_timer_get_time() + 1000000;
    reply_error(h, id, 0, "renewed");
    goto out;
  }
  if (!strcmp(op, "logs")) {
    c->logs = true;
    cJSON *v = cJSON_GetObjectItem(r, "since");
    if (cJSON_IsNumber(v) && v->valuedouble >= 0)
      c->cursor = v->valuedouble;
    reply_error(h, id, 0, "subscribed");
    goto out;
  }
  if (!strcmp(op, "jobs")) {
    cJSON *v = event("jobs", id, 0), *list = cJSON_AddArrayToObject(v, "jobs");
    for (int i = 0; i < JOBS; i++)
      if (jobs[i].id) {
        cJSON *j = cJSON_CreateObject();
        cJSON_AddNumberToObject(j, "job", jobs[i].id);
        cJSON_AddBoolToObject(j, "done", jobs[i].done);
        cJSON_AddNumberToObject(j, "code", jobs[i].code);
        cJSON_AddItemToArray(list, j);
      }
    emit(h, v);
    reply_error(h, id, 0, "listed");
    goto out;
  }
  if (!strcmp(op, "result")) {
    uint32_t jid = 0;
    job_t *j = NULL;
    if (number(r, "job", &jid))
      j = job(jid);
    if (!j) {
      reply_error(h, id, 2, "result expired or unknown job");
      goto out;
    }
    cJSON *o = cJSON_GetObjectItem(r, "offset");
    unsigned off = 0;
    if (o) {
      if (!cJSON_IsNumber(o) || o->valuedouble < 0 ||
          o->valuedouble > strlen(j->result)) {
        reply_error(h, id, 2, "invalid offset");
        goto out;
      }
      off = o->valuedouble;
    }
    char chunk[97];
    snprintf(chunk, sizeof chunk, "%.*s", (int)text_prefix(j->result + off, 96),
             j->result + off);
    cJSON *v = event("result", id, jid);
    cJSON_AddStringToObject(v, "data", chunk);
    cJSON_AddNumberToObject(v, "next", off + strlen(chunk));
    cJSON_AddNumberToObject(v, "total", strlen(j->result));
    cJSON_AddBoolToObject(v, "done", j->done);
    cJSON_AddNumberToObject(v, "code", j->code);
    cJSON_AddNumberToObject(v, "truncated", j->truncated);
    emit(h, v);
    goto out;
  }
  /* exec, diagnostics and confirm always pass through the worker. */
  if (strcmp(op, "exec") && strcmp(op, "diagnostics") &&
      strcmp(op, "confirm")) {
    reply_error(h, id, 2, "unsupported operation");
    goto out;
  }
  uint32_t jid = next_job + 1;
  job_t *j = NULL;
  for (int k = 0; k < JOBS; k++)
    if (!jobs[k].id ||
        (jobs[k].done && (jobs[k].notified || !client(jobs[k].client)))) {
      if (!j || jobs[k].id < j->id)
        j = &jobs[k];
    }
  if (!j || uxQueueSpacesAvailable(work) == 0) {
    reply_error(h, id, 1, "worker queue full");
    goto out;
  }
  memset(j, 0, sizeof *j);
  j->id = next_job = jid;
  j->client = h;
  j->request = id;
  j->started = esp_timer_get_time();
  work_t item = {.job = jid};
  strcpy(item.request, json);
  xQueueSend(work, &item, 0);
  emit(h, event("accepted", id, jid));
out:
  give();
  cJSON_Delete(r);
  return ESP_OK;
}
/* Classifies only operations that own motion. Other setters still use the drive
 * interlock. */
static int motion(int argc, char **a, int *wheel, double *seconds) {
  *seconds = 0;
  *wheel = 0;
  if (!strcmp(a[0], "cal") && argc > 1 &&
      (!strcasecmp(a[1], "a") || !strcasecmp(a[1], "b")))
    return 1;
  if (!strcmp(a[0], "demo") && argc > 1 && strcmp(a[1], "stop"))
    return 2;
  if (!strcmp(a[0], "drive")) {
    *seconds = argc > 3 ? atof(a[3]) : 2;
    return *seconds > 0 ? 3 : 5;
  }
  if (!strcmp(a[0], "wheel") && argc > 2) {
    *wheel = !strcasecmp(a[1], "b");
    if (!strcmp(a[2], "goto") || !strcmp(a[2], "move"))
      return 4;
    if (!strcmp(a[2], "vel")) {
      *seconds = argc > 4 ? atof(a[4]) : 2;
      return *seconds > 0 ? 3 : 5;
    }
    if (!strcmp(a[2], "spin") ||
        (!strcmp(a[2], "loop") && argc > 3 && !strcmp(a[3], "on")))
      return 5;
  }
  if (!strcmp(a[0], "ota") && argc > 1 &&
      (!strcmp(a[1], "start") || !strcmp(a[1], "check")))
    return 6;
  if (!strcmp(a[0], "wifi") && argc > 1 && !strcmp(a[1], "set"))
    return 7;
  return 0;
}
static bool wheel_inspection(int argc, char **argv) {
  if (strcmp(argv[0], "wheel"))
    return false;
  if (argc == 2 || (argc == 4 && !strcmp(argv[2], "reg")))
    return true;
  if (argc != 3)
    return false;
  size_t count;
  const char *const *names = drive_param_names(&count);
  for (size_t i = 0; i < count; i++)
    if (!strcmp(argv[2], names[i]))
      return true;
  return false;
}
static void worker(void *arg) {
  work_t item;
  for (;;) {
    if (xQueueReceive(work, &item, pdMS_TO_TICKS(50)) != pdTRUE) {
      ready = true;
      continue;
    }
    take();
    job_t *j = job(item.job);
    bool cancelled = j->cancelled;
    command_context_t ctx = {j->client, j->id};
    give();
    int rc = 2, kind = 0, wheel = 0;
    double seconds = 0;
    cJSON *r = cJSON_Parse(item.request);
    const char *op = cJSON_GetStringValue(cJSON_GetObjectItem(r, "op"));
    if (cancelled) {
      rc = 130;
      goto done;
    }
    if (!strcmp(op, "diagnostics")) {
      char outcome[160];
      net_ota_outcome(outcome, sizeof outcome);
      command_printf(
          &ctx, "boot %s; reset %s; firmware %s; OTA %s; previous boot %s\n",
          boot, sysinfo_reset_reason(), sysinfo_fw_version(), outcome,
          ulog_previous_boot());
      if (ulog_previous_panic()[0])
        command_printf(&ctx, "previous panic: %s\n", ulog_previous_panic());
      char *args[] = {"status"};
      handler(&ctx, 1, args);
      args[0] = "free";
      handler(&ctx, 1, args);
      args[0] = "stats";
      handler(&ctx, 1, args);
      char line[128];
      uint32_t cursor = 0, lost = 0;
      while (ulog_previous_read(&cursor, line, sizeof line, &lost))
        command_printf(&ctx, "previous log: %s\n", line);
      rc = 0;
      goto done;
    }
    if (!strcmp(op, "confirm")) {
      const char *v = cJSON_GetStringValue(cJSON_GetObjectItem(r, "version"));
      const char *i = cJSON_GetStringValue(cJSON_GetObjectItem(r, "image"));
      const char *b = cJSON_GetStringValue(cJSON_GetObjectItem(r, "boot"));
      char sha[65];
      sysinfo_image_id(sha);
      rc = ready && v && i && b && !strcmp(b, boot) &&
                   !strcmp(v, sysinfo_fw_version()) && !strcmp(i, sha) &&
                   net_ota_confirm() == ESP_OK
               ? 0
               : 1;
      goto done;
    }
    cJSON *args = cJSON_GetObjectItem(r, "args");
    int argc = cJSON_GetArraySize(args);
    char *argv[16];
    if (!cJSON_IsArray(args) || argc < 1 || argc > 16)
      goto done;
    for (int i = 0; i < argc; i++) {
      argv[i] = (char *)cJSON_GetStringValue(cJSON_GetArrayItem(args, i));
      if (!argv[i] || strlen(argv[i]) > 255)
        goto done;
    }
    kind = motion(argc, argv, &wheel, &seconds);
    if (!isfinite(seconds) || seconds < 0 || seconds > 3600) {
      rc = 2;
      goto done;
    }
    if (!strcmp(argv[0], "stop") || !strcmp(argv[0], "estop") ||
        !strcmp(argv[0], "disable") ||
        (argc > 1 && ((!strcmp(argv[0], "cal") && !strcmp(argv[1], "abort")) ||
                      (!strcmp(argv[0], "demo") && !strcmp(argv[1], "stop")))))
      management_stop(!strcmp(argv[0], "estop"));
    if (kind == 5) {
      take();
      bool connected = client(ctx.client) != NULL;
      give();
      if (!connected) {
        rc = 4;
        goto done;
      }
    }
    if (kind && kind < 6) {
      if (drive_maintenance_claim(false) != ESP_OK) {
        command_printf(&ctx, "refused: motion or update already active\n");
        rc = 1;
        goto done;
      }
      take();
      active = j->id;
      stop_requested = false;
      give();
    }
    /* Reject all competing drive mutations, including calls from this worker.
     */
    take();
    bool owned = active && active != j->id;
    give();
    bool read_only =
        !strcmp(argv[0], "status") || !strcmp(argv[0], "version") ||
        !strcmp(argv[0], "free") || !strcmp(argv[0], "stats") ||
        !strcmp(argv[0], "batt") || !strcmp(argv[0], "ble") ||
        !strcmp(argv[0], "help") || !strcmp(argv[0], "stream") ||
        !strcmp(argv[0], "log") || (!strcmp(argv[0], "set") && argc == 1) ||
        wheel_inspection(argc, argv) ||
        (!strcmp(argv[0], "wifi") && argc == 1) ||
        (!strcmp(argv[0], "faults") && argc == 1) ||
        (!strcmp(argv[0], "ota") && argc == 1) ||
        (!strcmp(argv[0], "cal") && argc == 2 && !strcmp(argv[1], "show"));
    if (owned && !read_only) {
      command_printf(&ctx, "refused: maintenance motion owns robot\n");
      rc = 1;
      goto done;
    }
    rc = handler(&ctx, argc, argv);
    take();
    if (j->cancelled)
      rc = 130;
    give();
    if (rc == 0 && kind) {
      uint32_t deadline = 60000;
      cJSON *d = cJSON_GetObjectItem(r, "deadline_ms");
      if (d && !number(r, "deadline_ms", &deadline))
        deadline = 60000;
      if (deadline > 3600000)
        deadline = 3600000;
      int64_t now = esp_timer_get_time();
      take();
      j->kind = kind;
      j->wheel = wheel;
      j->started = now;
      j->deadline = now + (int64_t)deadline * 1000;
      j->finish_at = now + (int64_t)(seconds * 1000000);
      j->lease = kind == 5 ? now + 1000000 : 0;
      give();
      cJSON_Delete(r);
      ready = true;
      continue;
    }
    if (kind && kind < 6) {
      drive_maintenance_release(false);
      take();
      if (active == j->id)
        active = 0;
      give();
    }
  done:
    take();
    finish(j, rc);
    give();
    cJSON_Delete(r);
    ready = true;
  }
}
static void monitor(void *arg) {
  bool release_pending = false;
  for (;;) {
    int64_t now = esp_timer_get_time();
    drive_status_t s;
    drive_get_status(&s);
    bool release = false, halt = false;
    take();
    for (int i = 0; i < JOBS; i++) {
      job_t *j = &jobs[i];
      if (!j->id || j->done || !j->kind)
        continue;
      int code = -1;
      if (j->kind == 7) {
        if (!net_wifi_trial_busy())
          code = net_wifi_trial_result();
      } else if (j->kind == 6) {
        if (!net_ota_busy())
          code = !strcmp(net_ota_status(), "cancelled") ? 130
                 : strstr(net_ota_status(), "failed")   ? 1
                                                        : 0;
      } else if (j->cancelled || stop_requested)
        code = 130;
      else if (s.faulted)
        code = 1;
      else if (now >= j->deadline || (j->lease && now >= j->lease))
        code = 124;
      else if (now - j->started > 100000) {
        if (j->kind == 1 && !drive_calibrate_busy()) {
          drive_cal_result_t r;
          code = drive_calibrate_last(&r) && r.ok ? 0 : 1;
        }
        if (j->kind == 2 && !s.demo_running)
          code = 0;
        if (j->kind == 3 && now >= j->finish_at)
          code = 0;
        if (j->kind == 4 && s.wheel[j->wheel].at_target)
          code = 0;
      }
      if (code >= 0) {
        size_t used = strlen(j->result);
        if (j->kind == 6)
          snprintf(j->result + used, sizeof j->result - used, "%s\n",
                   net_ota_status());
        if (j->kind == 7)
          snprintf(j->result + used, sizeof j->result - used, "%s\n",
                   code == 0 ? "credentials committed"
                             : "credential trial failed or cancelled; previous "
                               "credentials restored");
        if (j->kind == 1 && !drive_calibrate_busy()) {
          drive_cal_result_t r;
          if (drive_calibrate_last(&r))
            snprintf(
                j->result + used, sizeof j->result - used,
                "calibration %s: gain %.5f, counts %ld, residual %ld, %s\n",
                r.ok ? "ok" : "failed", r.clock_gain, (long)r.counts,
                (long)r.residual, r.note ? r.note : "");
        }
        finish(j, code);
        if (active == j->id) {
          active = 0;
          release = true;
          halt = true;
        }
      }
    }
    for (int k = 0; k < JOBS; k++) {
      job_t *j = &jobs[k];
      client_t *c = client(j->client);
      if (!j->id || !c || j->notified || uxQueueSpacesAvailable(c->out) < 2)
        continue;
      if (!j->done && j->kind && now - j->progress_at >= 1000000 &&
          uxQueueSpacesAvailable(c->out) > 2) {
        cJSON *r = event("progress", j->request, j->id);
        cJSON_AddNumberToObject(r, "elapsed_ms", (now - j->started) / 1000);
        if (j->kind == 6)
          cJSON_AddStringToObject(r, "status", net_ota_status());
        emit(c->handle, r);
        j->progress_at = now;
      }
      if (j->sent < strlen(j->result)) {
        char chunk[97];
        snprintf(chunk, sizeof chunk, "%.*s",
                 (int)text_prefix(j->result + j->sent, 96),
                 j->result + j->sent);
        cJSON *r = event("output", j->request, j->id);
        cJSON_AddStringToObject(r, "data", chunk);
        cJSON_AddNumberToObject(r, "offset", j->sent);
        emit(c->handle, r);
        j->sent += strlen(chunk);
      } else if (j->done) {
        cJSON *r = event("finished", j->request, j->id);
        cJSON_AddNumberToObject(r, "code", j->code);
        cJSON_AddNumberToObject(r, "truncated", j->truncated);
        emit(c->handle, r);
        j->notified = true;
      }
    }
    for (int i = 0; i < MGMT_CLIENTS; i++) {
      client_t *c = &clients[i];
      if (!c->handle)
        continue;
      if (c->logs)
        for (int n = 0; n < 2 && uxQueueSpacesAvailable(c->out) > 1; n++) {
          char line[128];
          uint32_t lost = 0;
          if (!ulog_read(&c->cursor, line, sizeof line, &lost))
            break;
          cJSON *r = event("log", 0, 0);
          cJSON_AddNumberToObject(r, "seq", c->cursor);
          cJSON_AddNumberToObject(r, "lost", lost);
          cJSON_AddStringToObject(r, "data", line);
          emit(c->handle, r);
        }
      if (c->hz > 0 && now >= c->next_sample) {
        c->next_sample = now + (int64_t)(1000000 / c->hz);
        c->sample_seq++;
        if (uxQueueSpacesAvailable(c->out) <= 1) {
          c->dropped++;
          continue;
        }
        char line[256];
        drive_csv_line(line, sizeof line);
        cJSON *r = event("stream", 0, 0);
        cJSON_AddNumberToObject(r, "seq", c->sample_seq);
        cJSON_AddStringToObject(r, "data", line);
        emit(c->handle, r);
      }
    }
    give();
    if (halt) {
      drive_calibrate_abort();
      drive_stop();
    }
    release_pending |= release;
    if (release_pending && drive_maintenance_release(false))
      release_pending = false;
    vTaskDelay(pdMS_TO_TICKS(20));
  }
}
esp_err_t management_init(command_handler_t fn) {
  if (mu)
    return ESP_OK;
  handler = fn;
  snprintf(boot, sizeof boot, "%08lx%08lx", (unsigned long)esp_random(),
           (unsigned long)esp_random());
  ulog_set_boot(boot);
  mu = xSemaphoreCreateMutex();
  work = xQueueCreate(6, sizeof(work_t));
  if (!mu || !work)
    return ESP_ERR_NO_MEM;
  if (xTaskCreate(worker, "commands", 8192, NULL, 4, &worker_handle) != pdPASS)
    return ESP_ERR_NO_MEM;
  if (xTaskCreate(monitor, "jobs", 6144, NULL, 4, NULL) != pdPASS)
    return ESP_ERR_NO_MEM;
  return ESP_OK;
}
