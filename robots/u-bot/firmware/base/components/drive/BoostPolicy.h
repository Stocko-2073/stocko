#pragma once
#include <stdint.h>

#include "MotorCurrent.h"

// When one wheel may run above its base current, and how it comes back down.
//
// Boost is a current, not a mode: IRUN and IHOLD both go to boostCs (IRUN 31,
// 1768 mA, is everything R110 gives with vsense=0) for as long as at least one
// reason for it is active. Reasons are independent bits, each with its own
// expiry, so one ending never cuts another short:
//
//   MANUAL    the operator's Boost button: drive frames carrying the flag
//   START     leaving a standstill of at least START_STILL_MS, for startMs;
//             detected here, from the `moving` input
//   RECOVERY  stall recovery: freeze, resync and re-ramp
//   LOAD      the load-angle estimate nearing pull-out
//
// A reason is only a request. It is granted while the motor is energised, the
// thermal model has headroom, the supply isn't inhibiting extra draw, the
// driver isn't derating for temperature, and boost is configured above the
// base run current. Otherwise the wheel runs its base current, derated if the
// driver is hot, and limitedBy says what refused the boost.
//
// Hold goes up with run, so a robot braced on a slope holds at boost current.
//
// Up is instant: when the torque is wanted it is wanted now, and the thermal
// model has already budgeted for it. Down is one CS step per STEP_DOWN_MS, run
// and hold each on their own clock: a wheel leaving a boost under load gives
// the torque back a step at a time instead of losing a third of it in one
// tick, and the drive's current writes (at most one per wheel per 100 ms) keep
// pace with it.
//
// Times are the caller's milliseconds. Nothing here reads a clock or touches
// the bus; the output is the CS pair to program.
class BoostPolicy {
  public:
    enum Reason : uint8_t { MANUAL = 1, START = 2, RECOVERY = 4, LOAD = 8 };
    enum Limit : uint8_t { LIMIT_HEAT = 1, LIMIT_DERATE = 2, LIMIT_SUPPLY = 4, LIMIT_OFF = 8 };

    static constexpr uint32_t STEP_DOWN_MS = 100;    // per CS step on the way down
    static constexpr uint32_t START_STILL_MS = 500;  // a standstill this long makes the next move a START

    struct Config {
        uint8_t baseRun = MotorCurrent::scale(MotorCurrent::DEFAULT_RUN_MA);    // IRUN 20
        uint8_t baseHold = MotorCurrent::scale(MotorCurrent::DEFAULT_HOLD_MA);  // IHOLD 9
        uint8_t boostCs = 31;     // 1768 mA; at or below baseRun, boost is off
        uint32_t startMs = 1500;  // how long a START lasts; 0 disables START
    };

    struct Inputs {
        uint32_t nowMs = 0;
        bool energised = false;      // EN low with this driver configured
        bool moving = false;         // step generator running (VACTUAL != 0)
        bool heatLimited = false;    // ThermalModel::limited()
        bool supplyInhibit = false;  // the supply can't take the extra draw
        uint8_t derate = 0;          // OtpwDerate::level()
    };

    struct Output {
        uint8_t run = 0, hold = 0;   // CS to program as IRUN / IHOLD
        uint8_t reasons = 0;         // active Reason bits, granted or not
        uint8_t limitedBy = 0;       // Limit bits that refused them
        bool boosting = false;       // granted this tick
    };

    BoostPolicy() { reset(0); }

    // Takes effect at the next update(): up at once, down on the ramp.
    // Out-of-range values are pulled into range rather than refused: CS stops
    // at 31 and hold at run. Turning START off ends one in progress.
    void configure(const Config &c) {
        _cfg = c;
        if (_cfg.baseRun > 31) _cfg.baseRun = 31;
        if (_cfg.boostCs > 31) _cfg.boostCs = 31;
        if (_cfg.baseHold > _cfg.baseRun) _cfg.baseHold = _cfg.baseRun;
        if (!_cfg.startMs) cancel(START);
    }
    const Config &config() const { return _cfg; }

    // For enable and disable: no reasons, base current (what begin() programs),
    // and the standstill START looks for counted from nowMs.
    void reset(uint32_t nowMs) {
        _active = 0;
        _run.jump(_cfg.baseRun);
        _hold.jump(_cfg.baseHold);
        _moving = false;
        _stillLong = false;
        _stillSince = nowMs;
    }

    // Keeps `r` active until at least nowMs + durationMs. A renewal can extend
    // an expiry but never shortens one, and a duration of 0 cancels. Durations
    // stop at 2^31 - 1 ms, the furthest a wrap-safe comparison can see.
    void request(Reason r, uint32_t nowMs, uint32_t durationMs) {
        if (!durationMs) {
            cancel(r);
            return;
        }
        if (durationMs > MAX_DURATION_MS) durationMs = MAX_DURATION_MS;
        const uint32_t exp = nowMs + durationMs;
        for (int i = 0; i < NREASONS; i++) {
            const uint8_t bit = (uint8_t)(1u << i);
            if (!(r & bit)) continue;
            if (!(_active & bit) || (int32_t)(exp - _expires[i]) > 0) _expires[i] = exp;
            _active |= bit;
        }
    }
    void cancel(Reason r) { _active &= (uint8_t)~r; }

    // Once per control tick.
    Output update(const Inputs &in) {
        const uint32_t now = in.nowMs;
        detectStart(in.moving, now);
        for (int i = 0; i < NREASONS; i++) {
            const uint8_t bit = (uint8_t)(1u << i);
            if ((_active & bit) && elapsed(_expires[i], now, 0)) _active &= (uint8_t)~bit;
        }

        Output o;
        o.reasons = _active;
        if (!in.energised) {
            // Nothing to boost, and the driver comes back at base because
            // begin() programs it, so the ramp starts over from there. A
            // de-energised motor isn't a limit: limitedBy stays clear, and the
            // drive's status already says the drivers are off.
            _run.jump(_cfg.baseRun);
            _hold.jump(_cfg.baseHold);
            o.run = _cfg.baseRun;
            o.hold = _cfg.baseHold;
            return o;
        }

        if (_active) {
            if (in.heatLimited) o.limitedBy |= LIMIT_HEAT;
            if (in.derate) o.limitedBy |= LIMIT_DERATE;
            if (in.supplyInhibit) o.limitedBy |= LIMIT_SUPPLY;
            if (_cfg.boostCs <= _cfg.baseRun) o.limitedBy |= LIMIT_OFF;
        }
        o.boosting = _active && !o.limitedBy;

        // configure() keeps baseHold <= baseRun and derated() is monotonic, so
        // the hold target never passes the run target, and ramps that start
        // consistent never cross. The driver write insists on hold <= run all
        // the same, so it is made structural here rather than argued.
        _run.toward(o.boosting ? _cfg.boostCs : derated(_cfg.baseRun, in.derate), now);
        _hold.toward(o.boosting ? _cfg.boostCs : derated(_cfg.baseHold, in.derate), now);
        if (_hold.cs > _run.cs) _hold.cs = _run.cs;
        o.run = _run.cs;
        o.hold = _hold.cs;
        return o;
    }

    // A derate level applied to a base CS. Current goes as CS + 1, so the
    // fraction is taken of that and floored: IRUN 20 (1160 mA) becomes 14
    // (829 mA) at level 2 and 9 (552 mA) at level 3. Levels 0 and 1 leave it
    // alone (level 1 only blocks boost); anything past 3 counts as 3.
    static uint8_t derated(uint8_t cs, uint8_t level) {
        if (level < 2) return cs;
        unsigned n = cs + 1u;
        n = level == 2 ? n * 3 / 4 : n / 2;
        return n ? (uint8_t)(n - 1) : 0;
    }

  private:
    static constexpr int NREASONS = 4;
    static constexpr uint32_t MAX_DURATION_MS = 0x7FFFFFFFu;

    // Wrap-safe: true once `now` is at least `ms` past `since`. Correct across
    // the 2^32 ms wrap (every ~50 days) for spans up to 2^31 ms.
    static bool elapsed(uint32_t since, uint32_t now, uint32_t ms) {
        return (int32_t)(now - since) >= (int32_t)ms;
    }

    // One channel, run or hold, heading for its target.
    struct Ramp {
        uint8_t cs = 0;
        bool falling = false;
        uint32_t stepMs = 0;   // when the last step down was due

        void jump(uint8_t v) {
            cs = v;
            falling = false;
        }

        void toward(uint8_t target, uint32_t now) {
            if (target >= cs) {
                jump(target);
                return;
            }
            // The first step comes a whole period after the target dropped, so
            // 31 -> 26 takes 5 periods, not 4. Later steps are due on that grid
            // rather than a period after whichever tick noticed the last one,
            // so a slow or uneven caller doesn't stretch the ramp.
            if (!falling) {
                falling = true;
                stepMs = now;
                return;
            }
            while (cs > target && elapsed(stepMs, now, STEP_DOWN_MS)) {
                cs--;
                stepMs += STEP_DOWN_MS;
            }
            if (cs == target) falling = false;
        }
    };

    // START fires on the first moving tick after a standstill of at least
    // START_STILL_MS, measured from reset() or from the tick motion last
    // stopped. A reversal through zero, or any pause shorter than that, is
    // still the same move. _stillLong notes once the standstill has lasted, so
    // one of any length still counts after the ~25-day window of the wrap-safe
    // comparison has gone by.
    void detectStart(bool moving, uint32_t now) {
        if (!moving) {
            if (_moving) {
                _stillSince = now;
                _stillLong = false;
            } else if (!_stillLong) {
                _stillLong = elapsed(_stillSince, now, START_STILL_MS);
            }
        } else if (!_moving && _cfg.startMs &&
                   (_stillLong || elapsed(_stillSince, now, START_STILL_MS))) {
            request(START, now, _cfg.startMs);
        }
        _moving = moving;
    }

    Config _cfg;
    uint8_t _active = 0;               // Reason bits
    uint32_t _expires[NREASONS] = {};  // per bit, meaningful while it is active
    Ramp _run, _hold;
    bool _moving = false;
    bool _stillLong = false;
    uint32_t _stillSince = 0;
};

// The driver's overtemperature pre-warning, turned into a derate level instead
// of a shutdown. The TMC2209 raises OTPW at ~120 C, and at OT, ~143 C, switches
// itself off until it has cooled below OTPW again. Disabling at the warning,
// as the drive used to, puts EN high and lets the wheels freewheel down
// whatever hill heated them; the datasheet names OTPW as the cue to reduce
// current instead. So:
//
//   level 0   nothing
//         1   no boost                          at the first OTPW
//         2   base run and hold at 75% (floor)  STEP_MS later if OTPW persists
//         3   base run and hold at 50% (floor)  another STEP_MS later
//
// and each RESTORE_MS of OTPW continuously clear gives one level back. The
// percentages are BoostPolicy::derated()'s. The hard OT path is unchanged; the
// datasheet gives >= 23 C between OTPW and OT.
//
// Flapping: a flag sampled near its threshold comes and goes. The step clock
// runs from the last level change, not from the last OTPW edge, so a warning
// that keeps coming back escalates on schedule even if it never stays up for
// STEP_MS in one go: the chip keeps touching 120 C, which is exactly when less
// current is wanted. Only an unbroken RESTORE_MS clear steps down, and any
// OTPW sample restarts that.
//
// Call sample() at the DRV_STATUS poll, or every tick with the latest flag;
// either gives the same levels to within a sample.
class OtpwDerate {
  public:
    static constexpr uint32_t STEP_MS = 10000;     // OTPW still there: one level more
    static constexpr uint32_t RESTORE_MS = 30000;  // OTPW clear throughout: one level back

    // One DRV_STATUS sample; returns the level to run at.
    uint8_t sample(bool otpw, uint32_t nowMs) {
        if (_fresh) {   // the first sample after reset() starts the clocks
            _fresh = false;
            _changedMs = nowMs;
        }
        if (otpw) {
            _clearing = false;
            if (_level == 0) {
                _level = 1;
                _events++;
                _changedMs = nowMs;
            } else if (_level < 3 && elapsed(_changedMs, nowMs, STEP_MS)) {
                _level++;
                _changedMs = nowMs;
            }
        } else {
            if (!_clearing) {
                _clearing = true;
                _clearSince = nowMs;
            }
            if (_level > 0 && elapsed(_clearSince, nowMs, RESTORE_MS)) {
                _level--;
                _changedMs = _clearSince = nowMs;
            }
        }
        return _level;
    }

    uint8_t level() const { return _level; }

    // Derate episodes: level 0 -> 1 on an OTPW sample.
    uint32_t events() const { return _events; }

    // For enable and disable, with the level to start at (OTPW already up at
    // enable starts at 2). There is no time here, so that level's clocks start
    // at the next sample(). events() is history and reset() leaves it alone.
    void reset(uint8_t level = 0) {
        _level = level > 3 ? 3 : level;
        _clearing = false;
        _fresh = true;
    }

  private:
    static bool elapsed(uint32_t since, uint32_t now, uint32_t ms) {   // as BoostPolicy's
        return (int32_t)(now - since) >= (int32_t)ms;
    }

    uint8_t _level = 0;
    bool _clearing = false;    // every sample since _clearSince was clear
    bool _fresh = true;
    uint32_t _changedMs = 0;   // the last level change: the step clock
    uint32_t _clearSince = 0;
    uint32_t _events = 0;
};
