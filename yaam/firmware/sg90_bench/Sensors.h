#pragma once
#include <Arduino.h>
#include <Wire.h>

// AS5600 and INA219 share Wire (I2C1 on D4/D5) at 400 kHz, the INA219's
// limit. Only core 1 touches the bus.

namespace i2c {

inline bool write(uint8_t addr, const uint8_t *d, size_t n) {
    Wire.beginTransmission(addr);
    Wire.write(d, n);
    return Wire.endTransmission() == 0;
}

// Pointer write, repeated start, read.
inline bool read(uint8_t addr, uint8_t reg, uint8_t *dst, size_t n) {
    Wire.beginTransmission(addr);
    Wire.write(reg);
    if (Wire.endTransmission(false) != 0) return false;
    if (Wire.requestFrom(addr, n) != n) return false;
    for (size_t i = 0; i < n; i++) dst[i] = (uint8_t)Wire.read();
    return true;
}

// A slave that browned out mid-byte can hold SDA low forever; clock it out
// and finish with a STOP before handing the pins back to the peripheral.
inline void recover(uint8_t sda, uint8_t scl) {
    Wire.end();
    pinMode(sda, INPUT_PULLUP);
    pinMode(scl, OUTPUT);
    for (int i = 0; i < 9 && digitalRead(sda) == LOW; i++) {
        digitalWrite(scl, LOW);
        delayMicroseconds(5);
        digitalWrite(scl, HIGH);
        delayMicroseconds(5);
    }
    pinMode(sda, OUTPUT);
    digitalWrite(sda, LOW);
    delayMicroseconds(5);
    digitalWrite(scl, HIGH);
    delayMicroseconds(5);
    digitalWrite(sda, HIGH);
    delayMicroseconds(5);
}

}  // namespace i2c

// AS5600, the registers the bench needs. Register map as in
// robots/u-bot/firmware/base/components/drive/AS5600.cpp, plus CONF: nothing in the
// repo set it before, so everything ran on the power-on 16x slow filter
// (2.2 ms lag). The bench wants the 2x filter (0.286 ms, 0.043 deg RMS), the
// fast filter off so the response stays one known linear filter, and no
// hysteresis, which would hide exactly the small motions we're after. CONF is
// volatile; it's written at every begin() and never burned.
class As5600 {
  public:
    static constexpr uint8_t ADDR = 0x36;
    static constexpr uint16_t CONF_BENCH = 0x0300;   // SF=11, FTH=000, HYST=00, PM=00, WD=0

    bool begin() {
        uint8_t w[3] = {0x07, (uint8_t)(CONF_BENCH >> 8), (uint8_t)CONF_BENCH};
        present_ = i2c::write(ADDR, w, 3) && conf() == CONF_BENCH;
        return present_;
    }

    bool present() const { return present_; }

    // RAW ANGLE (0x0C): unscaled, no 360-degree-wrap hysteresis.
    bool rawAngle(uint16_t &a) {
        uint8_t v[2];
        if (!i2c::read(ADDR, 0x0C, v, 2)) return false;
        a = (uint16_t)(((v[0] << 8) | v[1]) & 0x0FFF);
        return true;
    }

    uint16_t conf() { return reg16(0x07) & 0x3FFF; }
    uint8_t status() { return reg8(0x0B); }        // MD 0x20, ML 0x10, MH 0x08
    uint8_t agc() { return reg8(0x1A); }           // 0..128 at 3.3 V; aim for the middle
    uint16_t magnitude() { return reg16(0x1B) & 0x0FFF; }

  private:
    uint8_t reg8(uint8_t r) {
        uint8_t v = 0;
        i2c::read(ADDR, r, &v, 1);
        return v;
    }
    uint16_t reg16(uint8_t r) {
        uint8_t v[2] = {0, 0};
        i2c::read(ADDR, r, v, 2);
        return (uint16_t)((v[0] << 8) | v[1]);
    }

    bool present_ = false;
};

// INA219 on the servo's supply, high side. Only the shunt and bus voltage
// registers are used; current is computed on the host from the shunt value
// (10 uV per count), so the calibration register is left alone.
//
// CONFIG 0x119F: 16 V bus range, PGA /4 (+/-160 mV, so +/-1.6 A with the
// breakout's 0.1 ohm shunt), 12-bit shunt and bus conversions (532 us each),
// both continuously. Each register refreshes about every 1.06 ms and holds the
// average over its 532 us conversion -- the sim has to average the same way.
class Ina219 {
  public:
    static constexpr uint8_t ADDR = 0x40;
    static constexpr uint16_t CONFIG_BENCH = 0x119F;

    bool begin() {
        uint8_t reset[3] = {0x00, 0x80, 0x00};
        if (!i2c::write(ADDR, reset, 3)) return present_ = false;
        delay(1);
        uint8_t w[3] = {0x00, (uint8_t)(CONFIG_BENCH >> 8), (uint8_t)CONFIG_BENCH};
        present_ = i2c::write(ADDR, w, 3) && config() == CONFIG_BENCH;
        return present_;
    }

    bool present() const { return present_; }

    bool shunt(int16_t &v) { return reg(0x01, v); }

    // Bus register: voltage in bits 15..3 (4 mV per count), CNVR bit 1, OVF bit 0.
    bool bus(int16_t &v) { return reg(0x02, v); }

    uint16_t config() {
        int16_t v = 0;
        reg(0x00, v);
        return (uint16_t)v;
    }

  private:
    bool reg(uint8_t r, int16_t &v) {
        uint8_t b[2];
        if (!i2c::read(ADDR, r, b, 2)) return false;
        v = (int16_t)((b[0] << 8) | b[1]);
        return true;
    }

    bool present_ = false;
};
