#pragma once
// The handful of Arduino-isms the ported drive code leans on, spelled in
// ESP-IDF. Kept tiny on purpose so the servo classes read the same as they did
// on the bench.
#include <math.h>
#include <stdint.h>
#include <stdlib.h>

#include "esp_rom_sys.h"
#include "esp_task_wdt.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

// Wrap-safe 32-bit microseconds, as micros() was. Every diff in the servo code
// is taken as uint32 so the wrap every ~71 minutes is harmless.
static inline uint32_t micros() { return (uint32_t)esp_timer_get_time(); }
static inline uint32_t millis() { return (uint32_t)(esp_timer_get_time() / 1000); }

// Task-level sleep. The tick is 1 kHz (sdkconfig.defaults) so 1 ms is real.
static inline void delayMs(uint32_t ms) { vTaskDelay(pdMS_TO_TICKS(ms ? ms : 1)); }

// Busy wait, for bit periods. Unaffected by interrupts stretching it: I2C is a
// static protocol and the TMC bus is a hardware UART.
static inline void delayUs(uint32_t us) { esp_rom_delay_us(us); }

// Called from the blocking pumps between 1 ms samples. Sleeps a tick so the
// rest of the system runs, and feeds the watchdog the control task is on --
// calibration blocks that task for ~10 s and must not be mistaken for a wedge.
static inline void pumpYield() {
    esp_task_wdt_reset();
    vTaskDelay(1);
}

template <typename T>
static inline T constrain(T v, T lo, T hi) { return v < lo ? lo : (v > hi ? hi : v); }
