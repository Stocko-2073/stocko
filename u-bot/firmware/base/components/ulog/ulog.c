#include "ulog.h"

#include <stdarg.h>
#include <stdio.h>
#include <string.h>
#include <strings.h>

#include "esp_log.h"
#include "esp_attr.h"
#include "esp_system.h"
#include "esp_private/panic_internal.h"
#include "esp_memory_utils.h"
#include "freertos/FreeRTOS.h"
#include "freertos/ringbuf.h"
#include "freertos/task.h"

// ESP_LOGx formats into a ring buffer; a low-priority task writes to USB so a
// slow host cannot block the control task. A full buffer drops and counts lines.

static vprintf_like_t s_orig = NULL;
static RingbufHandle_t s_out = NULL;      // to the console
static RingbufHandle_t s_mirror = NULL;   // to WebSocket clients, when asked
static volatile bool s_mirror_on = false;
static volatile unsigned s_dropped = 0;

#define RECORDS 16
typedef struct { uint32_t seq; char line[128]; } record_t;
typedef struct { uint32_t magic, sequence; char boot[17]; record_t records[RECORDS]; } history_t;
static RTC_NOINIT_ATTR history_t retained;
static history_t previous;
typedef struct {
    uint32_t magic, core, exception, address;
    char detail[128];
} panic_record_t;
static RTC_NOINIT_ATTR panic_record_t panic_record;
static char previous_panic[224];
const char *ulog_previous_panic(void) { return previous_panic; }
void __real_esp_panic_handler(panic_info_t *info);
/* No allocation, locks, logging, flash reads or filesystem access in panic context. */
void IRAM_ATTR __wrap_esp_panic_handler(panic_info_t *info) {
    panic_record.magic = 0x50414e49;
    panic_record.core = info->core;
    panic_record.exception = info->exception;
    panic_record.address = (uint32_t)info->addr;
    panic_record.detail[0] = 0;
    const volatile char *detail = g_panic_abort_details;
    if (g_panic_abort && detail && esp_ptr_in_dram((const void *)detail)) {
        unsigned i;
        for (i = 0; i < sizeof panic_record.detail - 1 && detail[i]; i++)
            panic_record.detail[i] = detail[i];
        panic_record.detail[i] = 0;
    }
    __real_esp_panic_handler(info);
}
static portMUX_TYPE history_mux = portMUX_INITIALIZER_UNLOCKED;
void ulog_set_boot(const char *boot) { snprintf(retained.boot,sizeof retained.boot,"%s",boot); }
const char *ulog_previous_boot(void) { return previous.magic ? previous.boot : "unavailable"; }
static bool read_history(history_t *h,uint32_t *cursor,char *out,size_t len,uint32_t *lost) {
    if(!cursor||!out||!len)return false;
    portENTER_CRITICAL(&history_mux);
    uint32_t first=h->sequence>=RECORDS?h->sequence-RECORDS+1:1;
    uint32_t next=*cursor+1;
    if(next<first){*lost+=first-next;next=first;}
    bool ok=next<=h->sequence;
    if(ok){snprintf(out,len,"%s",h->records[next%RECORDS].line);*cursor=next;}
    portEXIT_CRITICAL(&history_mux);return ok;
}
bool ulog_read(uint32_t *cursor,char*out,size_t len,uint32_t*lost){return read_history(&retained,cursor,out,len,lost);}
bool ulog_previous_read(uint32_t *cursor,char*out,size_t len,uint32_t*lost){return read_history(&previous,cursor,out,len,lost);}

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

    portENTER_CRITICAL(&history_mux);
    uint32_t seq=++retained.sequence;
    record_t *r=&retained.records[seq%RECORDS];r->seq=seq;
    memcpy(r->line,line,len<127?len:127);r->line[len<127?len:127]=0;
    portEXIT_CRITICAL(&history_mux);

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
    if (esp_reset_reason() != ESP_RST_POWERON && panic_record.magic == 0x50414e49)
        snprintf(previous_panic, sizeof previous_panic,
                 "core %lu exception %lu address 0x%08lx %s",
                 (unsigned long)panic_record.core, (unsigned long)panic_record.exception,
                 (unsigned long)panic_record.address, panic_record.detail);
    panic_record.magic = 0;
    if(esp_reset_reason()!=ESP_RST_POWERON && retained.magic==0x55424f54)previous=retained;
    memset(&retained,0,sizeof retained);retained.magic=0x55424f54;
    if (!s_out) s_out = xRingbufferCreate(2048, RINGBUF_TYPE_NOSPLIT);
    if (!s_mirror) s_mirror = xRingbufferCreate(2048, RINGBUF_TYPE_NOSPLIT);
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
