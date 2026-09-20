#pragma once
/* Portable BLE framing used by production and the host boundary tests.
 * Five-byte header: flags (START=1, END=2), message LE16, offset LE16. */
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <string.h>
#define MANAGEMENT_REASSEMBLY_MAX 768

typedef struct {
    bool active;
    uint16_t id, length;
    uint64_t started_ms;
    char data[MANAGEMENT_REASSEMBLY_MAX];
} management_fragment_t;

/* -1 invalid/reset, 0 incomplete, 1 complete JSON in state->data. */
static inline int management_fragment_feed(management_fragment_t *s,
                                           const uint8_t *p, size_t len,
                                           uint64_t now_ms) {
    if (len <= 5 || (p[0] & ~3)) goto invalid;
    uint16_t id = p[1] | (uint16_t)p[2] << 8;
    uint16_t off = p[3] | (uint16_t)p[4] << 8;
    if (p[0] & 1) {
        if (off) goto invalid;
        s->active = true;
        s->id = id;
        s->length = 0;
        s->started_ms = now_ms;
    }
    if (!s->active || s->id != id || off != s->length ||
        now_ms - s->started_ms > 5000 ||
        len - 5 >= sizeof s->data - s->length || memchr(p + 5, 0, len - 5))
        goto invalid;
    memcpy(s->data + s->length, p + 5, len - 5);
    s->length += len - 5;
    if (p[0] & 2) {
        s->data[s->length] = 0;
        s->active = false;
        return 1;
    }
    return 0;
invalid:
    s->active = false;
    s->length = 0;
    return -1;
}
