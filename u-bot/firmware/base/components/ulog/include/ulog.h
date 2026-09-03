#pragma once
// One log stream. Every module uses ESP_LOGx with its own tag; this hooks the
// log writer so that, besides the console, each line can be mirrored to a
// ring buffer that the WebSocket server drains to any client that asked for
// logs. The console's `log` command sets per-tag levels at runtime.
#include <stdbool.h>
#include <stddef.h>

#include "esp_err.h"

#ifdef __cplusplus
extern "C" {
#endif

esp_err_t ulog_init(void);

// Turn the mirror on or off. Off by default so a robot nobody is watching does
// not fill a buffer for nothing.
void ulog_mirror(bool on);
bool ulog_mirrored(void);

// Pop the oldest mirrored line into `buf` (NUL-terminated). Returns its length,
// or 0 if there is nothing waiting.
size_t ulog_pop(char *buf, size_t len);

// How many console lines were dropped because the buffer was full (the host
// was not reading fast enough).
unsigned ulog_dropped(void);

// "none" "error" "warn" "info" "debug" "verbose" (or e/w/i/d/v). Tag "*" is all.
esp_err_t ulog_set_level(const char *tag, const char *level);
const char *ulog_level_name(int level);

#ifdef __cplusplus
}
#endif
