#pragma once
#include <stdint.h>

#include "I2cBus.h"

// AS5600 12-bit magnetic encoder, the registers this firmware needs. Replaces
// the RobTillaart Arduino library the bench sketches used; same behaviour for
// the calls that were in use (readAngle with direction CW, status, AGC,
// magnitude), and nothing else.
class AS5600 {
  public:
    static const uint8_t DEFAULT_ADDRESS = 0x36;

    // STATUS register bits.
    static const uint8_t MAGNET_HIGH   = 0x08;  // magnet too close
    static const uint8_t MAGNET_LOW    = 0x10;  // magnet too far
    static const uint8_t MAGNET_DETECT = 0x20;

    enum Error { OK = 0, ERR_READ = -10, ERR_WRITE = -11, ERR_NOBUS = -12 };

    AS5600(I2cBus &bus, uint8_t address = DEFAULT_ADDRESS) : bus_(bus), addr_(address) {}

    bool begin();
    bool isConnected();
    uint8_t address() const { return addr_; }
    const char *busKind() const { return bus_.kind(); }

    // ANGLE (0x0E): the scaled/filtered 12-bit angle. On a read error the
    // previous value is returned and lastError() says so -- the servo relies on
    // that to hold position rather than integrate garbage.
    uint16_t readAngle();
    uint16_t rawAngle();       // RAW_ANGLE (0x0C), unscaled
    uint8_t readStatus();      // STATUS (0x0B)
    uint8_t readAGC();         // AGC (0x1A): 0..128 on 3V3, aim for ~64
    uint16_t readMagnitude();  // MAGNITUDE (0x1B)
    int lastError() const { return err_; }

    static const char *magnetText(uint8_t status);

  private:
    uint8_t reg8(uint8_t reg);
    uint16_t reg16(uint8_t reg);

    I2cBus &bus_;
    uint8_t addr_;
    int err_ = OK;
    uint16_t lastAngle_ = 0;
};
