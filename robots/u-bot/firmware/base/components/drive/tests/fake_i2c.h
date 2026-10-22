#pragma once
#include <stddef.h>
#include <stdint.h>
#include <string.h>

#include <functional>

#include "I2cBus.h"

// An I2C bus with one AS5600 on it, so the real AS5600.cpp and StepperServo
// run on the host exactly as they do against either bus on the robot.
//
// The chip is a register map read with auto-increment from the pointer the
// write sets, which is all AS5600.cpp does: a one-byte pointer write, then one
// or two bytes back, big-endian for the 12-bit values.
//
// The angle is whatever angleFn says when the read happens -- a plant's
// encoder, typically -- or `angle` when no function is set. Registers not
// listed below read as whatever was last written there (CONF, for Phase 3's
// read-back), else 0.
class FakeI2c : public I2cBus {
  public:
    static constexpr uint8_t ADDRESS = 0x36;
    static constexpr uint8_t REG_STATUS = 0x0B, REG_RAW_ANGLE = 0x0C, REG_ANGLE = 0x0E,
                             REG_AGC = 0x1A, REG_MAGNITUDE = 0x1B;

    std::function<uint16_t()> angleFn;
    uint16_t angle = 0;          // 12-bit, used when angleFn is empty
    uint8_t status = 0x20;       // MD: magnet detected, neither too weak nor too strong
    uint8_t agc = 64;            // mid-range, where a well-placed magnet sits
    uint16_t magnitude = 2000;

    // Failure injection. failNext counts down one per read transaction; `down`
    // fails everything (unplugged, or a wedged bus) until cleared.
    int failNext = 0;
    bool down = false;

    uint32_t reads = 0;          // read transactions attempted
    uint32_t failures = 0;       // of those, failed

    void failReads(int n) { failNext = n; }

    bool begin() override { return !down; }

    bool writeRead(uint8_t addr, const uint8_t *w, size_t wn, uint8_t *r, size_t rn) override {
        reads++;
        if (down || addr != ADDRESS || wn < 1) { failures++; return false; }
        if (failNext > 0) {
            failNext--;
            failures++;
            return false;
        }
        uint8_t map[256];
        snapshot(map, w[0], rn);
        for (size_t i = 0; i < rn; i++) r[i] = map[(w[0] + i) & 0xFF];
        return true;
    }

    // A pointer write followed by data lands in the register map.
    bool write(uint8_t addr, const uint8_t *w, size_t wn) override {
        if (down || addr != ADDRESS) return false;
        for (size_t i = 1; i < wn; i++) written_[(w[0] + i - 1) & 0xFF] = w[i];
        return true;
    }

    bool probe(uint8_t addr) override { return !down && addr == ADDRESS; }
    const char *kind() const override { return "fake"; }

  private:
    // The register map as the chip would present it at this instant. The angle
    // is sampled only when the read covers it, so a status poll never consumes
    // a sample from angleFn (a plant's flicker sequence, say).
    void snapshot(uint8_t *map, uint8_t from, size_t n) {
        memcpy(map, written_, sizeof written_);
        if (from <= REG_ANGLE + 1 && from + n > REG_RAW_ANGLE) {
            uint16_t a = (angleFn ? angleFn() : angle) & 0x0FFF;
            // ANGLE and RAW_ANGLE agree: ZPOS/MPOS are never programmed on this robot.
            map[REG_RAW_ANGLE] = map[REG_ANGLE] = (uint8_t)(a >> 8);
            map[REG_RAW_ANGLE + 1] = map[REG_ANGLE + 1] = (uint8_t)a;
        }
        map[REG_STATUS] = status;
        map[REG_AGC] = agc;
        map[REG_MAGNITUDE] = (uint8_t)((magnitude >> 8) & 0x0F);
        map[REG_MAGNITUDE + 1] = (uint8_t)magnitude;
    }

    uint8_t written_[256] = {};
};
