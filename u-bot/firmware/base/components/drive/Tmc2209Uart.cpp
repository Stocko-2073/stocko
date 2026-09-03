#include "Tmc2209Uart.h"

#include "driver/gpio.h"
#include "platform.h"

bool Tmc2209Uart::begin(uint32_t baud) {
    if (!mtx_) mtx_ = xSemaphoreCreateMutex();
    lock();
    if (installed_) {
        uart_driver_delete(port_);
        installed_ = false;
        delayMs(5);
    }
    uart_config_t cfg = {};
    cfg.baud_rate = (int)baud;
    cfg.data_bits = UART_DATA_8_BITS;
    cfg.parity = UART_PARITY_DISABLE;
    cfg.stop_bits = UART_STOP_BITS_1;
    cfg.flow_ctrl = UART_HW_FLOWCTRL_DISABLE;
    cfg.source_clk = UART_SCLK_DEFAULT;

    bool ok = uart_driver_install(port_, 256, 256, 0, nullptr, 0) == ESP_OK &&
              uart_param_config(port_, &cfg) == ESP_OK &&
              uart_set_pin(port_, tx_, rx_, UART_PIN_NO_CHANGE, UART_PIN_NO_CHANGE) == ESP_OK;
    if (ok) {
        // Push-pull TX through the 1k; nothing pulling on either pin. The
        // internal ~45k pulls were only ever for the open-drain arrangement.
        gpio_set_pull_mode((gpio_num_t)tx_, GPIO_FLOATING);
        gpio_set_pull_mode((gpio_num_t)rx_, GPIO_FLOATING);
        installed_ = true;
        delayMs(5);
    }
    unlock();
    return ok;
}

void Tmc2209Uart::end() {
    lock();
    if (installed_) uart_driver_delete(port_);
    installed_ = false;
    unlock();
}

void Tmc2209Uart::lock() {
    if (mtx_) xSemaphoreTake(mtx_, portMAX_DELAY);
}
void Tmc2209Uart::unlock() {
    if (mtx_) xSemaphoreGive(mtx_);
}

void Tmc2209Uart::drain() { uart_flush_input(port_); }

// Collect up to `want` bytes or give up after `timeoutMs`. uart_read_bytes
// returns as soon as `want` have arrived, so a driver that answers promptly
// never waits out the timeout.
int Tmc2209Uart::readBytes(uint8_t *dst, int want, uint32_t timeoutMs) {
    int n = 0;
    uint32_t t0 = millis();
    while (n < want) {
        uint32_t el = millis() - t0;
        if (el >= timeoutMs) break;
        int got = uart_read_bytes(port_, dst + n, want - n,
                                  pdMS_TO_TICKS(timeoutMs - el));
        if (got > 0) n += got;
        else if (got < 0) break;
    }
    return n;
}

Tmc2209Uart::Result Tmc2209Uart::read(uint8_t addr, uint8_t reg) {
    Result r;
    r.st = NO_ECHO;
    r.value = 0;
    r.n = 0;
    if (!installed_) return r;

    lock();
    drain();
    uint8_t req[4] = {0x05, addr, reg, 0};
    req[3] = crc(req, 3);
    uart_write_bytes(port_, req, 4);
    uart_wait_tx_done(port_, pdMS_TO_TICKS(20));

    // 4 bytes of echo, then an 8 byte reply if the driver is listening.
    r.n = (uint8_t)readBytes(r.buf, 12, 40);
    unlock();

    if (r.n == 0)                               { r.st = NO_ECHO;     return r; }
    if (r.n < 4 || memcmp(r.buf, req, 4) != 0)  { r.st = BAD_ECHO;    return r; }
    if (r.n == 4)                               { r.st = NO_REPLY;    return r; }
    if (r.n < 12)                               { r.st = SHORT_REPLY; return r; }

    const uint8_t *p = r.buf + 4;
    if (p[0] != 0x05 || p[1] != 0xFF || p[2] != reg) { r.st = BAD_FRAME; return r; }
    if (crc(p, 7) != p[7])                           { r.st = BAD_CRC;   return r; }

    r.value = ((uint32_t)p[3] << 24) | ((uint32_t)p[4] << 16) |
              ((uint32_t)p[5] << 8)  |  (uint32_t)p[6];
    r.st = OK;
    return r;
}

Tmc2209Uart::Result Tmc2209Uart::write(uint8_t addr, uint8_t reg, uint32_t val) {
    uint8_t d[8] = {0x05, addr, (uint8_t)(reg | 0x80),
                    (uint8_t)(val >> 24), (uint8_t)(val >> 16),
                    (uint8_t)(val >> 8),  (uint8_t)val, 0};
    d[7] = crc(d, 7);

    Result r;
    r.value = 0;
    r.n = 0;
    r.st = NO_ECHO;
    if (!installed_) return r;

    lock();
    drain();
    uart_write_bytes(port_, d, 8);
    // TX and RX are the same wire, so by the time the last bit has left the
    // pad the whole echo is already sitting in the RX FIFO. This is the ~320 us
    // at 250k that a write costs, and it is spent asleep on a semaphore.
    uart_wait_tx_done(port_, pdMS_TO_TICKS(20));
    r.n = (uint8_t)readBytes(r.buf, 8, 5);
    writes_++;
    r.st = (r.n == 8 && memcmp(r.buf, d, 8) == 0) ? OK : BAD_ECHO;
    if (r.st != OK) echoFaults_++;
    unlock();

    memcpy(r.buf + 8, d, 8);   // what we meant to send, for comparison
    return r;
}

const char *Tmc2209Uart::statusName(Status s) {
    switch (s) {
        case OK:          return "ok";
        case NO_ECHO:     return "NO ECHO -- nothing came back on RX at all";
        case BAD_ECHO:    return "BAD ECHO -- RX saw bytes, but not the ones sent";
        case NO_REPLY:    return "echo ok, NO REPLY from driver";
        case SHORT_REPLY: return "echo ok, reply truncated";
        case BAD_FRAME:   return "reply framing wrong";
        case BAD_CRC:     return "reply CRC bad -- link is noisy";
    }
    return "?";
}

uint8_t Tmc2209Uart::crc(const uint8_t *d, size_t n) {
    uint8_t c = 0;
    for (size_t i = 0; i < n; i++) {
        uint8_t b = d[i];
        for (uint8_t j = 0; j < 8; j++) {
            c = ((c >> 7) ^ (b & 0x01)) ? (uint8_t)((c << 1) ^ 0x07) : (uint8_t)(c << 1);
            b >>= 1;
        }
    }
    return c;
}
