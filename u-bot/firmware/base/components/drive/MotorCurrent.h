#pragma once
#include <math.h>
#include <stdint.h>

// 17HS15-1504S-X1 on BTT TMC2209 V1.3 modules (external R110 resistors).
// Digital reference, vsense=0. Board properties are not user tuning knobs.
//
// Three ceilings, for three different things:
//   MAX_MA        the continuous run_ma cap: what the drive may ask for as a
//                 base current, all day.
//   RATED_MA      the motor's rated 1.5 A RMS, where the thermal model puts
//                 h = 1.0. The same number as MAX_MA today, but a thermal
//                 constant, not a policy one.
//   BOOST_MAX_MA  IRUN 31, everything R110 gives with vsense=0: milliamps(31)
//                 is 1767.8 mA, so 1768 is the smallest request that scales to
//                 31 (1767 rounds down to 30). Only ever for bursts, and only
//                 as far as the thermal model allows.
namespace MotorCurrent {
constexpr int MAX_MA = 1500;
constexpr int MIN_MA = 100;
constexpr int RATED_MA = 1500;
constexpr int BOOST_MAX_MA = 1768;
constexpr int DEFAULT_RUN_MA = 1200;
constexpr int DEFAULT_HOLD_MA = 600;
constexpr float RSENSE = 0.11f;
constexpr float MA_PER_SCALE = 1000.0f * 0.325f / ((RSENSE + 0.02f) * 1.41421356f * 32.0f);

inline bool valid(int runMa, int holdMa) {
    return runMa >= MIN_MA && runMa <= MAX_MA && holdMa >= MIN_MA && holdMa <= runMa;
}
// boost_ma: 0 is boost off; otherwise at least the run current it boosts from
// (equal is allowed and boosts nothing) and at most IRUN 31.
inline bool validBoost(int runMa, int boostMa) {
    return boostMa == 0 || (boostMa >= runMa && boostMa <= BOOST_MAX_MA);
}
// Round DOWN: nominal programmed current must not exceed the request.
inline uint8_t scale(int ma) {
    int steps = (int)floorf(ma / MA_PER_SCALE);
    return (uint8_t)(steps < 1 ? 0 : steps > 32 ? 31 : steps - 1);
}
inline float milliamps(uint8_t cs) { return (cs + 1) * MA_PER_SCALE; }
}
