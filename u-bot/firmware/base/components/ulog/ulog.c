#include "ulog.h"

#include <stdarg.h>
#include <stdio.h>
#include <string.h>
#include <strings.h>

#include "esp_log.h"
#include "freertos/FreeRTOS.h"
#include "freertos/ringbuf.h"
#include "freertos/task.h"

// Logging is asynchronous. The hook below runs on whatever task called
// ESP_LOGx, formats the line, and drops it into a ring buffer; a low-priority
// printer task is the only thing that ever writes to the console. The reason
// is the USB console: when the host is slow to read, a write blocks until it
// does, and a control task blocked on a log line is a control task not
// controlling. Measured before this change: a 20 ms tick where 5 ms was due.
//
// A full buffer drops the line and counts it rather than waiting.

static vprintf_like_t s_orig = NULL;
static RingbufHandle_t s_out = NULL;      // to the console
static RingbufHandle_t s_mirror = NULL;   // to WebSocket clients, when asked
static volatile bool s_mirror_on = false;
static volatile unsigned s_dropped = 0;

static void printer_task(void *arg) {
    for (;;) {
        size_t sz = 0;
        char *item = (char *)xRingbufferReceive(s_out, &sz, portMAX_DELAY);
        if (!item) continue;
        fwrite(item, 1, sz, stdout);
        vRingbufferReturnItem(s_out, item);
        fflush(stdout);
    }
}

static int ulog_vprintf(const char *fmt, va_list ap) {
    char line[256];
    int n = vsnprintf(line, sizeof line, fmt, ap);
    if (n < 0) return n;
    size_t len = (size_t)n < sizeof line - 1 ? (size_t)n : sizeof line - 1;
    if (len == 0) return 0;

    if (s_out) {
        if (xRingbufferSend(s_out, line, len, 0) != pdTRUE) s_dropped++;
    } else {
        fwrite(line, 1, len, stdout);
    }

    if (s_mirror_on && s_mirror) {
        size_t l = len;
        while (l > 0 && (line[l - 1] == '\n' || line[l - 1] == '\r')) l--;
        if (l > 0) xRingbufferSend(s_mirror, line, l, 0);   // best effort
    }
    return n;
}

esp_err_t ulog_init(void) {
    if (!s_out) s_out = xRingbufferCreate(8192, RINGBUF_TYPE_NOSPLIT);
    if (!s_mirror) s_mirror = xRingbufferCreate(6144, RINGBUF_TYPE_NOSPLIT);
    if (!s_out || !s_mirror) return ESP_ERR_NO_MEM;
    if (xTaskCreate(printer_task, "log", 3072, NULL, 2, NULL) != pdPASS) return ESP_ERR_NO_MEM;
    if (!s_orig) s_orig = esp_log_set_vprintf(ulog_vprintf);
    return ESP_OK;
}

void ulog_mirror(bool on) {
    if (on == s_mirror_on) return;
    s_mirror_on = on;
    if (!on && s_mirror) {
        size_t sz;
        void *item;
        while ((item = xRingbufferReceive(s_mirror, &sz, 0)) != NULL) vRingbufferReturnItem(s_mirror, item);
    }
}

bool ulog_mirrored(void) { return s_mirror_on; }

size_t ulog_pop(char *buf, size_t len) {
    if (!s_mirror || !buf || len == 0) return 0;
    size_t sz = 0;
    void *item = xRingbufferReceive(s_mirror, &sz, 0);
    if (!item) return 0;
    size_t n = sz < len - 1 ? sz : len - 1;
    memcpy(buf, item, n);
    buf[n] = 0;
    vRingbufferReturnItem(s_mirror, item);
    return n;
}

unsigned ulog_dropped(void) { return s_dropped; }

static int parse_level(const char *s) {
    if (!s || !*s) return -1;
    if (!strcasecmp(s, "none") || !strcasecmp(s, "n")) return ESP_LOG_NONE;
    if (!strcasecmp(s, "error") || !strcasecmp(s, "e")) return ESP_LOG_ERROR;
    if (!strcasecmp(s, "warn") || !strcasecmp(s, "w") || !strcasecmp(s, "warning")) return ESP_LOG_WARN;
    if (!strcasecmp(s, "info") || !strcasecmp(s, "i")) return ESP_LOG_INFO;
    if (!strcasecmp(s, "debug") || !strcasecmp(s, "d")) return ESP_LOG_DEBUG;
    if (!strcasecmp(s, "verbose") || !strcasecmp(s, "v")) return ESP_LOG_VERBOSE;
    return -1;
}

esp_err_t ulog_set_level(const char *tag, const char *level) {
    int l = parse_level(level);
    if (l < 0) return ESP_ERR_INVALID_ARG;
    esp_log_level_set(tag ? tag : "*", (esp_log_level_t)l);
    return ESP_OK;
}

const char *ulog_level_name(int level) {
    switch (level) {
        case ESP_LOG_NONE: return "none";
        case ESP_LOG_ERROR: return "error";
        case ESP_LOG_WARN: return "warn";
        case ESP_LOG_INFO: return "info";
        case ESP_LOG_DEBUG: return "debug";
        case ESP_LOG_VERBOSE: return "verbose";
    }
    return "?";
}
