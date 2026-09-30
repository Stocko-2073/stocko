#pragma once
#include <math.h>
#include <stdint.h>

#include "MotorCurrent.h"

// A heat budget for one motor, so boost can run it past its continuous rating
// for as long as that is safe and no longer. Nothing on the robot measures
// motor temperature; this models it from the current the driver delivers.
//
//   heat h     normalized: 1.0 is where the motor settles after running
//              continuously at its rated current, 1.5 A RMS. Copper loss goes
//              as I^2, so a steady current I settles at h_ss = (I/rated)^2:
//              boost at 1768 mA settles at 1.39, cruise at 1160 mA at 0.60,
//              parked on 552 mA of hold current at 0.14.
//   response   first order. h heads for h_ss with tauHeatS while heating and
//              coolRatio times slower while cooling. The motor's real tau is
//              estimated at ~1000 s, so 600 s up and 1200 s down warms the
//              model faster and cools it slower than the motor: it errs hot
//              both ways.
//   limit      boost is refused from the moment h reaches `limit` until h is
//              back down to limit - hysteresis. 1.10 lets bursts run ~10% past
//              continuous-rating heat, which the PETG housings take; the gap
//              keeps boost from chattering on and off at the line.
//   BOOT_H     the motor's history is unknown at power-on, so it is assumed
//              warm, most of the way to rated heat.
//
// What that buys with boost at 1768 mA and the limit at 1.10 ("warm" is
// settled at the cruise current; a recharge is 1.10 back down to 1.00).
// test_thermal checks each of these:
//
//   cruise    boost from warm   from power-on   recharge cruising   recharge parked
//   1160 mA       10.1 min          7.1 min          4.4 min            2.2 min
//   1492 mA        3.2 min          7.1 min         46.8 min            2.2 min
//
// Time comes in as arguments; nothing here reads a clock.
class ThermalModel {
  public:
    struct Params {
        float ratedMa = 1500;       // RMS current that settles at h = 1.0 (17HS15-1504S)
        float tauHeatS = 600;       // s, time constant while heating
        float coolRatio = 2.0f;     // cooling runs this many times slower
        float limit = 1.10f;        // boost refused from here...
        float hysteresis = 0.10f;   // ...until h is this far back below it
    };

    static constexpr float BOOT_H = 0.8f;   // assumed at power-on

    // I^2 is integrated this long between exponential steps; see accumulate().
    static constexpr float STEP_S = 0.1f;

    // Refuses, keeping the parameters it had, anything non-finite or not
    // positive, and a hysteresis that would put the resume point at or below
    // zero. A new limit applies at once to the heat already there.
    bool configure(const Params &p) {
        if (!positive(p.ratedMa) || !positive(p.tauHeatS) || !positive(p.coolRatio) ||
            !positive(p.limit) || !isfinite(p.hysteresis) || p.hysteresis < 0 ||
            p.hysteresis >= p.limit) return false;
        flush();   // what has accumulated so far ran under the old parameters
        _p = p;
        latch();
        return true;
    }
    const Params &params() const { return _p; }

    // Start from a known heat: BOOT_H at power-on, or a value carried across a
    // warm reset. Checking that a carried value is genuine is the caller's job;
    // this only refuses what cannot be a heat at all (NaN, infinite, negative)
    // and falls back to BOOT_H. At or past the limit it starts limited.
    void reset(float h) {
        _h = (isfinite(h) && h >= 0) ? h : BOOT_H;
        _pendS = _pendQ = 0;
        _limited = _h >= _p.limit;
    }

    // dtS seconds at `ma` RMS. The drive calls this every 5 ms tick.
    //
    // One exact exponential step per call would be right in real arithmetic
    // but not in float: 5 ms against a 600 s tau closes 1e-5 of the gap to
    // h_ss, and near equilibrium that falls below float resolution, so h would
    // stall ~0.4% short of h_ss at 5 ms ticks and ~2% short at 1 ms. Instead
    // I^2 is integrated for STEP_S and applied as one exact step toward its
    // mean. That is exact at any dt while the current is steady, and
    // indistinguishable from exact across a change (STEP_S is 1/6000 of tau),
    // so the answer doesn't depend on the tick size. heat() and limited() lag
    // by at most STEP_S, nothing on a 600 s time constant.
    //
    // NaN, infinite or negative input is dropped rather than poisoning the
    // state.
    void accumulate(float dtS, float ma) {
        if (!isfinite(dtS) || !isfinite(ma) || dtS < 0 || ma < 0) return;
        float r = ma / _p.ratedMa;
        _pendS += dtS;
        _pendQ += r * r * dtS;
        if (_pendS >= STEP_S) flush();
    }

    float heat() const { return _h; }
    bool limited() const { return _limited; }

    // How long `ma` could run from here before the limit trips: 0 if it has
    // already, INFINITY if `ma` settles at or below the limit and so never gets
    // there. Solves h(t) = h_ss + (h - h_ss) e^(-t/tau) for h(t) = limit.
    float secondsToLimit(float ma) const {
        if (_limited || !isfinite(ma) || ma < 0) return 0;   // nonsense gets no budget
        float r = ma / _p.ratedMa, hss = r * r;
        if (hss <= _p.limit) return INFINITY;
        if (_h >= _p.limit) return 0;
        return _p.tauHeatS * logf((hss - _h) / (hss - _p.limit));
    }

    // The current the motor is actually getting, from what was last written to
    // its driver. The TMC2209 cuts its own current at standstill without saying
    // so, and that cut is most of the difference between a parked wheel and a
    // moving one, so the model has to follow it:
    //
    //   not energised    0: EN is high
    //   moving           IRUN
    //   still < tpdMs    still IRUN. The driver flags standstill (stst) 2^20
    //                    clocks after the last step, then waits TPOWERDOWN x
    //                    2^18 clocks before it starts reducing.
    //   after that       one CS down every IHOLDDELAY x 2^18 clocks until
    //                    IHOLD; IHOLDDELAY 0 drops straight to IHOLD.
    //
    // The caller converts both delays to ms with a 10% margin, so the model
    // keeps believing in the higher current a little longer than the driver
    // delivers it:
    //
    //   tpdMs  = (2^20 + TPOWERDOWN * 2^18) / (12 MHz * clockGain) * 1.1
    //            ~570 ms at TPOWERDOWN 20
    //   stepMs = IHOLDDELAY * 2^18 / 12 MHz * 1.1
    //            ~192 ms per step at IHOLDDELAY 8
    //
    // (The oscillator times stepMs as well, but the measured gains are within
    // 2% of 1, well inside the margin.) stillMs is the time since the step
    // generator last ran, i.e. since VACTUAL went to zero. The first reduction
    // is counted a whole stepMs after tpdMs, erring hot again.
    static float inferMa(bool energised, bool moving, uint32_t stillMs, uint8_t liveRunCs,
                         uint8_t liveHoldCs, uint32_t tpdMs, uint32_t stepMs) {
        if (!energised) return 0;
        if (liveRunCs > 31) liveRunCs = 31;     // unprogrammable; take the hot side
        if (liveHoldCs > 31) liveHoldCs = 31;
        if (moving || stillMs < tpdMs) return MotorCurrent::milliamps(liveRunCs);
        uint8_t cs = liveHoldCs;
        if (stepMs && liveRunCs > liveHoldCs) {
            uint32_t steps = (stillMs - tpdMs) / stepMs;
            if (steps < (uint32_t)(liveRunCs - liveHoldCs)) cs = (uint8_t)(liveRunCs - steps);
        }
        return MotorCurrent::milliamps(cs);
    }

  private:
    static bool positive(float x) { return isfinite(x) && x > 0; }

    // Step h toward the mean h_ss of the pending span. Where that mean lies,
    // above or below h, decides heating or cooling and so the tau.
    void flush() {
        if (_pendS <= 0) return;
        float hss = _pendQ / _pendS;
        float tau = hss > _h ? _p.tauHeatS : _p.tauHeatS * _p.coolRatio;
        _h += (hss - _h) * -expm1f(-_pendS / tau);   // 1 - e^-x without the cancellation
        _pendS = _pendQ = 0;
        latch();
    }

    void latch() {
        if (_h >= _p.limit) _limited = true;
        else if (_h <= _p.limit - _p.hysteresis) _limited = false;
    }

    Params _p;
    float _h = BOOT_H;
    bool _limited = false;
    float _pendS = 0;   // s since the last step
    float _pendQ = 0;   // integral of (I/rated)^2 dt over the same span
};
