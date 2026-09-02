#include "AS5600.h"

static const uint8_t REG_STATUS    = 0x0B;
static const uint8_t REG_RAW_ANGLE = 0x0C;
static const uint8_t REG_ANGLE     = 0x0E;
static const uint8_t REG_AGC       = 0x1A;
static const uint8_t REG_MAGNITUDE = 0x1B;

bool AS5600::begin() {
    if (!bus_.begin()) { err_ = ERR_NOBUS; return false; }
    return isConnected();
}

bool AS5600::isConnected() { return bus_.probe(addr_); }

uint8_t AS5600::reg8(uint8_t reg) {
    uint8_t v = 0;
    err_ = bus_.writeRead(addr_, &reg, 1, &v, 1) ? OK : ERR_READ;
    return err_ == OK ? v : 0;
}

uint16_t AS5600::reg16(uint8_t reg) {
    uint8_t v[2] = {0, 0};
    err_ = bus_.writeRead(addr_, &reg, 1, v, 2) ? OK : ERR_READ;
    return err_ == OK ? (uint16_t)(((uint16_t)v[0] << 8) | v[1]) : 0;
}

uint16_t AS5600::readAngle() {
    uint16_t a = reg16(REG_ANGLE) & 0x0FFF;
    if (err_ != OK) return lastAngle_;
    lastAngle_ = a;
    return a;
}

uint16_t AS5600::rawAngle() { return reg16(REG_RAW_ANGLE) & 0x0FFF; }
uint8_t AS5600::readStatus() { return reg8(REG_STATUS); }
uint8_t AS5600::readAGC() { return reg8(REG_AGC); }
uint16_t AS5600::readMagnitude() { return reg16(REG_MAGNITUDE) & 0x0FFF; }

const char *AS5600::magnetText(uint8_t status) {
    if (!(status & MAGNET_DETECT)) return "none";
    if (status & MAGNET_LOW) return "too weak (magnet too far / off-axis)";
    if (status & MAGNET_HIGH) return "too strong (magnet too close)";
    return "ok";
}
