#pragma once
#include <math.h>
#include <stdint.h>

// 17HS15-1504S-X1 on BTT TMC2209 V1.3 modules (external R110 resistors).
// Digital reference, vsense=0. Board properties are not user tuning knobs.
namespace MotorCurrent {
constexpr int MAX_MA = 1500;
constexpr int MIN_MA = 100;
constexpr int DEFAULT_RUN_MA = 1200;
constexpr int DEFAULT_HOLD_MA = 600;
constexpr float RSENSE = 0.11f;
constexpr float MA_PER_SCALE = 1000.0f * 0.325f / ((RSENSE + 0.02f) * 1.41421356f * 32.0f);

inline bool valid(int runMa, int holdMa) {
    return runMa >= MIN_MA && runMa <= MAX_MA && holdMa >= MIN_MA && holdMa <= runMa;
}
// Round DOWN: nominal programmed current must not exceed the request.
inline uint8_t scale(int ma) {
    int steps = (int)floorf(ma / MA_PER_SCALE);
    return (uint8_t)(steps < 1 ? 0 : steps > 32 ? 31 : steps - 1);
}
inline float milliamps(uint8_t cs) { return (cs + 1) * MA_PER_SCALE; }
}
