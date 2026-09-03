#include "I2cBus.h"

#include "driver/gpio.h"
#include "platform.h"

// ------------------------------------------------------------------ hardware

bool HwI2c::begin() {
    if (bus_) return true;
    i2c_master_bus_config_t cfg = {};
    cfg.i2c_port = port_;
    cfg.sda_io_num = (gpio_num_t)sda_;
    cfg.scl_io_num = (gpio_num_t)scl_;
    cfg.clk_source = I2C_CLK_SRC_DEFAULT;
    cfg.glitch_ignore_cnt = 7;
    cfg.flags.enable_internal_pullup = 1;   // the breakout has its own; this only helps
    return i2c_new_master_bus(&cfg, &bus_) == ESP_OK;
}

i2c_master_dev_handle_t HwI2c::dev(uint8_t addr) {
    if (!bus_) return nullptr;
    for (int i = 0; i < MAXDEV; i++) {
        if (devH_[i] && devAddr_[i] == addr) return devH_[i];
    }
    for (int i = 0; i < MAXDEV; i++) {
        if (devH_[i]) continue;
        i2c_device_config_t dc = {};
        dc.dev_addr_length = I2C_ADDR_BIT_LEN_7;
        dc.device_address = addr;
        dc.scl_speed_hz = hz_;
        if (i2c_master_bus_add_device(bus_, &dc, &devH_[i]) != ESP_OK) return nullptr;
        devAddr_[i] = addr;
        return devH_[i];
    }
    return nullptr;
}

// 5 ms is an eternity against a ~100 us transaction, but the point of the
// timeout is to bound the damage of a wedged bus, and the servo backs off for
// 100 ms after any failure so this cannot be paid on every tick.
bool HwI2c::writeRead(uint8_t addr, const uint8_t *w, size_t wn, uint8_t *r, size_t rn) {
    i2c_master_dev_handle_t d = dev(addr);
    if (!d) return false;
    return i2c_master_transmit_receive(d, w, wn, r, rn, 5) == ESP_OK;
}

bool HwI2c::write(uint8_t addr, const uint8_t *w, size_t wn) {
    i2c_master_dev_handle_t d = dev(addr);
    if (!d) return false;
    return i2c_master_transmit(d, w, wn, 5) == ESP_OK;
}

bool HwI2c::probe(uint8_t addr) {
    if (!bus_) return false;
    return i2c_master_probe(bus_, addr, 5) == ESP_OK;
}

// ---------------------------------------------------------------- bit-banged

inline void SoftI2c::driveLow(int pin) { gpio_set_level((gpio_num_t)pin, 0); }
inline void SoftI2c::release(int pin) { gpio_set_level((gpio_num_t)pin, 1); }
inline bool SoftI2c::readPin(int pin) const { return gpio_get_level((gpio_num_t)pin) != 0; }
inline void SoftI2c::hold() const { delayUs(halfUs_); }

bool SoftI2c::begin() {
    // Open drain with the input buffer live: the output drives low or lets go,
    // and reading the pin always reports what is actually on the wire.
    gpio_config_t io = {};
    io.pin_bit_mask = (1ULL << sda_) | (1ULL << scl_);
    io.mode = GPIO_MODE_INPUT_OUTPUT_OD;
    io.pull_up_en = GPIO_PULLUP_DISABLE;   // external 4.7k does the work
    io.pull_down_en = GPIO_PULLDOWN_DISABLE;
    io.intr_type = GPIO_INTR_DISABLE;
    if (gpio_config(&io) != ESP_OK) return false;
    release(sda_);
    release(scl_);
    recoverBus();
    return true;
}

void SoftI2c::recoverBus() {
    release(sda_);
    for (uint8_t i = 0; i < 9; i++) {
        sclHigh();
        driveLow(scl_);
        hold();
    }
    stop();
}

bool SoftI2c::probe(uint8_t addr) {
    if (!start()) return false;
    bool ack = writeByte((uint8_t)(addr << 1));
    stop();
    return ack;
}

bool SoftI2c::writeRead(uint8_t addr, const uint8_t *w, size_t wn, uint8_t *r, size_t rn) {
    if (!start() || !writeByte((uint8_t)(addr << 1))) { stop(); return false; }
    for (size_t i = 0; i < wn; i++) {
        if (!writeByte(w[i])) { stop(); return false; }
    }
    // Repeated start: no stop in between, or a glitch could take the bus
    // between setting the register pointer and reading it.
    if (!start() || !writeByte((uint8_t)((addr << 1) | 1))) { stop(); return false; }
    for (size_t i = 0; i < rn; i++) {
        // ACK every byte but the last; the NACK tells the slave to let go of
        // SDA so the stop can happen.
        if (!readByte(r[i], i + 1 < rn)) { stop(); return false; }
    }
    stop();
    return true;
}

bool SoftI2c::write(uint8_t addr, const uint8_t *w, size_t wn) {
    if (!start() || !writeByte((uint8_t)(addr << 1))) { stop(); return false; }
    for (size_t i = 0; i < wn; i++) {
        if (!writeByte(w[i])) { stop(); return false; }
    }
    stop();
    return true;
}

bool SoftI2c::start() {
    release(sda_);
    hold();
    if (!sclHigh()) return false;
    driveLow(sda_);  // SDA falls while SCL is high
    hold();
    driveLow(scl_);
    hold();
    return true;
}

void SoftI2c::stop() {
    driveLow(sda_);
    hold();
    sclHigh();
    release(sda_);  // SDA rises while SCL is high
    hold();
}

// Returns true if the slave pulled SDA down on the ninth clock.
bool SoftI2c::writeByte(uint8_t b) {
    for (uint8_t i = 0; i < 8; i++) {
        if (!sendBit((b & 0x80) != 0)) return false;
        b <<= 1;
    }
    release(sda_);  // ninth clock: the slave owns SDA
    hold();
    if (!sclHigh()) return false;
    bool ack = !readPin(sda_);
    driveLow(scl_);
    return ack;
}

bool SoftI2c::readByte(uint8_t &out, bool ack) {
    uint8_t b = 0;
    release(sda_);
    for (uint8_t i = 0; i < 8; i++) {
        hold();
        if (!sclHigh()) return false;
        b = (uint8_t)((b << 1) | (readPin(sda_) ? 1 : 0));  // sampled with SCL high
        driveLow(scl_);
    }
    out = b;
    return sendBit(!ack);  // ack = drive SDA low, nack = leave it released
}

// Two holds per bit: the first is the SCL low period and doubles as data setup
// time, the second is the high period inside sclHigh().
bool SoftI2c::sendBit(bool bit) {
    if (bit) release(sda_); else driveLow(sda_);
    hold();
    if (!sclHigh()) return false;
    driveLow(scl_);
    return true;
}

// Release SCL and make sure it actually came up. The pull-up has to charge the
// bus capacitance, and a slave is allowed to hold it down -- the AS5600 never
// does, but checking turns a shorted SCL into a clean failure.
bool SoftI2c::sclHigh() {
    release(scl_);
    hold();
    if (readPin(scl_)) return true;
    uint32_t t0 = micros();
    while (!readPin(scl_)) {
        if (micros() - t0 > STRETCH_US) return false;
    }
    return true;
}
