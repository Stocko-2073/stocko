#pragma once
#include <math.h>
#include <stdint.h>

// Speed-independent stall detection for one wheel in velocity mode.
//
// What it watches is the servo's raw slip: the commanded integral minus the
// encoder, both in motor microsteps (StepperServo's _slipRaw). A rotor in sync
// keeps that difference nearly constant; a rotor that has lost its field lets it
// grow by every microstep commanded from then on.
//
// Why not the servo's own slip check: that one references raw against a 1 s
// TIME leak, so it forgets at the same rate whatever the speed. Crawling at 0.02
// turns/s a full stall only adds ~107 microsteps a second, the leak eats it
// before it reaches the 200-step limit, and the wheel chatters forever. Leaking
// by DISTANCE instead gives the same answer at every speed:
//
//     ref += (raw - ref) * travel / (D + travel)     travel = |commanded change|
//     lag  = (raw - ref) * dir                       + means the rotor is behind
//
// A full stall grows raw by exactly the travel, so lag(x) = D (1 - e^(-x/D))
// crosses the trip level L after x = -D ln(1 - L/D) microsteps of commanded
// travel: 42 at D 400, L 40, whether that takes 0.4 s at 0.02 turns/s or 8 ms at
// 1.0. The leak is there for everything that is not a stall:
//
//   clock gain error e  raw ramps by e per microstep and lag settles at -e*D,
//                       ~1.2 microsteps for the 0.3% a calibrated clock drifts
//   encoder INL         a fixed function of shaft angle, so a sine in distance;
//                       the leak is a first-order high-pass in distance, gain
//                       wD / sqrt(1 + w^2 D^2) with w = 2 pi h / 5333.3 per
//                       microstep: 0.43 for the once-a-turn term, 0.69 twice
//   backlash            a start or a reversal re-anchors, then ignores
//                       settleSteps of travel -- the motor crossing the gear
//                       play while the output shaft stands still looks exactly
//                       like the first microsteps of a stall
//
// It is blind to a steady partial slip under ~10% (that drifts off like a clock
// error), and it only runs in velocity mode: position mode and the Demo keep the
// servo's 1 s slip fault, untouched. No state lives in the servo's public tuning
// fields, which the Demo rewrites every beat.
//
// Pure on purpose -- std headers only -- so the host tests drive it with
// synthetic streams. The drive layer samples everything once per control tick,
// right after the servo's update(), into a StallInput.

struct StallInput {
    double cmdSteps;     // commanded integral, microsteps (VelGen::position())
    float rawLag;        // cmdSteps - encoder x stepsPerCount, sampled with it
    int32_t encCounts;   // multiturn encoder position, output-shaft counts
    uint32_t epoch;      // the servo's resync counter: it bumps on every resyncSlip()
    bool encOk;          // this tick's encoder read succeeded
    bool velMode;        // the servo is closed and in velocity mode
    float dt;            // s since the previous sample
};

struct StallSample {
    float lag;           // microsteps, + = rotor behind the command; 0 unless armed
    float rotorCps;      // rotor velocity over the last WINDOW ticks, counts/s
    int8_t dir;          // sign of this tick's commanded travel (0 on a resync tick)
    bool armed;          // lag is live and may trip
    int8_t trip;         // +1 LAG, -1 LEAD, 0 none: an edge, at most once per anchor
    bool velValid;       // rotorCps is measured: two reads at least since the ring last
                         // restarted (a resync, a failed read); else it reads 0 for want of one
};

struct StallConfig {
    float tripSteps = 40;     // lag_trip: trip level, microsteps; 0 switches detection off
    float leakSteps = 400;    // lag_leak: D, the travel the reference forgets over
    float settleSteps = 48;   // lag_rev: travel ignored after a start or a reversal

    // Below 16 the in-sync budget alone (load angle up to 16) would trip it.
    // Above 0.8 D the stall curve creeps up on the level so slowly that the
    // trip distance runs away -- 1.6 D at 0.8, never at 1.0. The finiteness
    // checks are because a NaN fails every comparison the other way round.
    bool valid() const {
        if (tripSteps == 0) return true;
        return tripSteps >= 16 && tripSteps <= 0.8f * leakSteps &&
               leakSteps >= 100 && isfinite(leakSteps) &&
               settleSteps >= 0 && isfinite(settleSteps);
    }
};

class StallDetector {
  public:
    static constexpr int WINDOW = 4;   // rotor velocity boxcar, ticks: 20 ms at 200 Hz

    // An invalid config is refused and the previous one kept; the settings
    // layer is expected to have checked valid() and said why. Either way the
    // reference starts over, since a new D or L makes the old one meaningless.
    void configure(const StallConfig &c) {
        if (c.valid()) _cfg = c;
        reanchor();
    }
    const StallConfig &config() const { return _cfg; }

    // Forget the reference. The next moving sample is treated as a fresh
    // start: re-anchored, then disarmed for settleSteps.
    void reanchor() {
        _dir = 0;
        _armed = false;
        _latched = false;
        _settle = 0;
    }

    StallSample update(const StallInput &in) {
        StallSample s = {0.0f, 0.0f, 0, false, 0, false};

        // A resync moves raw on purpose, so whatever the reference was is
        // stale. The servo counts its resyncs rather than telling us, because
        // there are a dozen call sites. It also moves the commanded integral
        // itself (gen.zero() to the encoder), so the change seen on the first
        // tick of a new epoch is the resync's jump, not motion: counted as
        // travel it could spend the whole backlash settle in one tick. That
        // tick reads as a standstill instead, and the next one as a start.
        bool resync = !_primed || in.epoch != _epoch;
        // Commanded travel, differenced in double: the integral only ever
        // grows, and a float would round a crawl's half-microstep ticks away
        // after a few thousand turns.
        double d = resync ? 0.0 : in.cmdSteps - _lastCmd;
        _lastCmd = in.cmdSteps;
        _epoch = in.epoch;
        _primed = true;
        float travel = (float)fabs(d);
        int8_t dir = d > 0 ? 1 : (d < 0 ? -1 : 0);
        s.dir = dir;
        if (resync) {
            reanchor();
            _n = 0;   // zeroHere() re-zeroes the encoder under a resync too
        }

        if (in.encOk) pushRotor(in.encCounts, in.dt);
        else _n = 0;   // never difference across a gap
        s.rotorCps = rotorCps();
        s.velValid = _n >= 2;

        if (_cfg.tripSteps == 0) {   // off: inert, never trips
            reanchor();
            return s;
        }

        // A failed read leaves the servo's position where it was, so raw is
        // counting the command against a frozen shaft. Hold the reference
        // rather than leak it toward that. When the encoder answers again the
        // servo's position catches up in one read and raw with it, and the lag
        // carries on where it left off -- a rotor that stalled in the gap is
        // still caught. Direction and settle wait too: a reversal inside the
        // gap is seen, and re-anchored, on the first good sample.
        if (!in.encOk) return s;

        if (!in.velMode || dir == 0) {
            reanchor();
            _ref = in.rawLag;
            return s;
        }

        if (dir != _dir) {
            // A start, or a reversal: the motor crosses the gear play first.
            _dir = dir;
            _armed = false;
            _latched = false;
            _settle = _cfg.settleSteps;
        }
        if (!_armed) {
            // Follow raw until the play has been crossed, then arm on a fresh
            // anchor -- this tick's lag is zero by construction.
            _ref = in.rawLag;
            _settle -= travel;
            if (_settle > 0) return s;
            _armed = true;
            s.armed = true;
            return s;
        }

        _ref += (in.rawLag - _ref) * travel / (_cfg.leakSteps + travel);
        float lag = (in.rawLag - _ref) * (float)dir;
        s.lag = lag;
        s.armed = true;
        if (fabsf(lag) > _worst) _worst = fabsf(lag);
        // An edge: once tripped it stays quiet until something re-anchors it,
        // so one stall is one event however long the lag stays high.
        if (!_latched && fabsf(lag) > _cfg.tripSteps) {
            _latched = true;
            _trips++;
            s.trip = lag > 0 ? 1 : -1;
        }
        return s;
    }

    uint32_t trips() const { return _trips; }
    float worstLag() const { return _worst; }   // max |lag| while armed
    void resetWorst() { _worst = 0; }

  private:
    // WINDOW ticks of velocity need WINDOW + 1 positions.
    static constexpr int RING = WINDOW + 1;

    void pushRotor(int32_t counts, float dt) {
        _enc[_head] = counts;
        _dt[_head] = dt;
        _head = (uint8_t)((_head + 1) % RING);
        if (_n < RING) _n++;
    }

    // Counts over the time actually spanned, so a late tick cannot fake a
    // speed change. Until the ring fills it uses what it has.
    float rotorCps() const {
        if (_n < 2) return 0.0f;
        int newest = (_head + RING - 1) % RING;
        int oldest = (_head + RING - _n) % RING;
        float span = 0;
        for (int k = 1; k < _n; k++) span += _dt[(oldest + k) % RING];
        if (!(span > 0)) return 0.0f;
        // Wrap-safe difference, like the servo's time arithmetic.
        int32_t dc = (int32_t)((uint32_t)_enc[newest] - (uint32_t)_enc[oldest]);
        return (float)dc / span;
    }

    StallConfig _cfg;
    double _lastCmd = 0;
    uint32_t _epoch = 0;
    bool _primed = false;
    float _ref = 0;          // microsteps, the reference raw is measured against
    int8_t _dir = 0;         // direction the anchor was taken in; 0 = none
    float _settle = 0;       // travel left before arming, microsteps
    bool _armed = false;
    bool _latched = false;   // tripped since the last anchor
    uint32_t _trips = 0;
    float _worst = 0;

    int32_t _enc[RING] = {};
    float _dt[RING] = {};
    uint8_t _head = 0;
    uint8_t _n = 0;
};
