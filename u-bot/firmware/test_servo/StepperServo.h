#pragma once
#include <AS5600.h>

#include "StepGen.h"

// Closed-loop position servo: NEMA 17 through a TMC2209 in STEP/DIR mode, with
// an AS5600 magnetic encoder reading the *output* shaft through a 12:40 bevel
// pair. Every public number is in output-shaft units -- turns, or the encoder's
// 4096 counts per output turn -- because that is the shaft that matters.
//
// Why closed loop on a stepper at all: open-loop steps are already precise, so
// the loop is not there to fix resolution. It is there to (a) give an absolute
// reference the step counter cannot have, and (b) notice when the motor did not
// actually go where it was told. That second job is the whole point, and it
// falls out of comparing StepGen's pulse count against the encoder.
//
// Control law: position error -> velocity command -> step rate. A P term sets
// the velocity, a sqrt(2*a*e) ceiling makes sure there is always room to brake,
// and the commanded velocity is slew-limited so the motor never gets a step in
// rate it cannot follow. There is deliberately no integral term: a stepper has
// no proportional-band droop to integrate away, and a velocity floor outside
// the tolerance band already guarantees the last few counts get walked in.
//
// Resolution note: one encoder count is ~1.3 microsteps at 1/8, so the encoder
// is the coarser of the two. Tolerance below ~2 counts just makes it hunt.
class StepperServo {
  public:
    static const int32_t COUNTS_PER_REV = 4096;  // AS5600, output shaft

    enum Fault : uint8_t { FAULT_NONE = 0, FAULT_SLIP };

    StepperServo(AS5600 &enc, StepGen &gen) : _enc(enc), _gen(gen) {}

    // --- tuning (output-shaft units unless noted) ---
    //
    // Defaults are the fastest setting measured clean on this axis. Slip at
    // speed is drivetrain lag, not lost steps -- it returns to zero at rest --
    // and it climbs gently right up to the point where the motor gives up:
    //
    //   vmax  accel  kp | peak rate   worst |slip|
    //   0.5     4    12 |  2667 sps        25   clean
    //   1.0     8    16 |  5333 sps        29   clean          <- default
    //   1.5    12    20 |  8000 sps        33   marginal
    //   2.0    20    24 | 10667 sps        38   marginal
    //   3.0    30    30 | 14721 sps       144   SKIPPED, faulted
    //
    // The last row never even reached its 3.0 turns/s -- the motor topped out
    // at 2.76 and shed steps, and slip detection caught it. vmax and accel were
    // raised together in that sweep, so which of the two broke it is not
    // separated; treat both as being near their limit up there.
    float kp = 16.0f;          // (counts/s) per count of error, i.e. 1/s
    float vmaxTps = 1.0f;      // turns/s ceiling
    float accelTps2 = 8.0f;    // turns/s^2, also the brake authority
    float vminSps = 12.0f;     // steps/s floor while outside tolerance
    int32_t tolCounts = 3;     // ~0.26 deg at the output shaft
    float stepsPerCount = 1.302083f;  // 200 * 8 * 40/12 / 4096; calibrate() measures it
    int32_t slipLimit = 200;   // steps of sudden divergence before faulting

    // --- lifecycle ---

    // Call after enc.begin() and gen.begin().
    void begin() {
        _lastRaw = _enc.readAngle();
        _encPos = 0;
        _target = 0;
        _gen.zero(0);
        _slipRef = 0;
        _slipRaw = 0;
    }

    void enableDriver(bool on) {
        if (!on) servoOn(false);
        _gen.enable(on);
    }
    bool driverEnabled() const { return _gen.enabled(); }

    // Closing the loop parks the target on the present position, so turning the
    // servo on can never make it lurch toward a stale setpoint.
    void servoOn(bool on) {
        if (on) {
            _target = _encPos;
            _vcmd = 0;
            _fault = FAULT_NONE;
            resyncSlip();
        } else {
            _gen.stop();
            _vcmd = 0;
        }
        _servo = on;
    }
    bool servoOn() const { return _servo; }

    // Call this the moment anything makes the step count and the encoder
    // disagree on purpose (zeroing, calibrating, open-loop jogging).
    void resyncSlip() {
        _gen.zero((int32_t)lroundf((float)_encPos * stepsPerCount));
        _slipRaw = 0;
        _slipRef = 0;
    }

    // Redefine here as position zero.
    void zeroHere() {
        _encPos = 0;
        _target = 0;
        resyncSlip();
    }

    void clearFault() { _fault = FAULT_NONE; }

    // --- commands ---

    void moveToTurns(float t) { moveToCounts((int32_t)lroundf(t * COUNTS_PER_REV)); }
    void moveByTurns(float t) { moveToCounts(_target + (int32_t)lroundf(t * COUNTS_PER_REV)); }
    void moveToCounts(int32_t c) {
        _target = c;
        if (_fault == FAULT_NONE) return;
        _fault = FAULT_NONE;  // a fresh command is an implicit acknowledgement
        resyncSlip();
    }

    // --- state ---

    int32_t positionCounts() const { return _encPos; }
    float positionTurns() const { return (float)_encPos / COUNTS_PER_REV; }
    int32_t targetCounts() const { return _target; }
    float targetTurns() const { return (float)_target / COUNTS_PER_REV; }
    int32_t errorCounts() const { return _target - _encPos; }
    float velocityTps() const { return _vel / COUNTS_PER_REV; }
    uint16_t rawAngle() const { return _lastRaw; }
    int32_t slipSteps() const { return (int32_t)lroundf(_slipRaw - _slipRef); }
    bool atTarget() const { return labs((long)(_target - _encPos)) <= tolCounts; }
    uint8_t fault() const { return _fault; }
    const char *faultName() const {
        switch (_fault) {
            case FAULT_SLIP:
                return "slip (pulses sent, shaft did not follow -- stalled, "
                       "current too low, or DIR polarity backwards)";
            default: return "none";
        }
    }

    // --- control loop, call at a fixed rate (1 kHz here) ---

    void update(float dt) {
        readEncoder(dt);

        // Commanded pulses vs. where the shaft actually got to. The reference is
        // high-passed with a slow leak so a few tenths of a percent of error in
        // stepsPerCount drifts harmlessly, while a real stall -- which piles up
        // hundreds of steps in under a tenth of a second -- still trips.
        _slipRaw = (float)_gen.position() - (float)_encPos * stepsPerCount;
        if (_fault == FAULT_NONE) _slipRef += (_slipRaw - _slipRef) * (dt / SLIP_TAU);

        if (!_servo) return;

        if (fabsf(_slipRaw - _slipRef) > (float)slipLimit) {
            _fault = FAULT_SLIP;
            servoOn(false);
            return;
        }

        float err = (float)(_target - _encPos);
        float accel = accelTps2 * COUNTS_PER_REV;
        float vmax = vmaxTps * COUNTS_PER_REV;
        bool goal = fabsf(err) <= (float)tolCounts;

        // Inside tolerance and no longer coasting: stop pulsing and let the
        // driver hold. (A TMC2209 in standalone mode falls back to its hold
        // current after ~1 s of no steps, so holding torque is not full torque.)
        if (goal && fabsf(_vel) < SETTLE_VEL) {
            _vcmd = 0;
            _gen.setRate(0);
            return;
        }

        float vdes = kp * err;
        // Never go faster than we can still brake from within the error left.
        float vbrake = sqrtf(2.0f * accel * fabsf(err));
        if (fabsf(vdes) > vbrake) vdes = copysignf(vbrake, err);
        if (fabsf(vdes) > vmax) vdes = copysignf(vmax, err);

        float slew = accel * dt;
        _vcmd += constrain(vdes - _vcmd, -slew, slew);

        float sps = _vcmd * stepsPerCount;
        // The last count or two of error asks for a rate rounding to nothing;
        // walk it in instead of parking just outside the band.
        if (!goal && fabsf(sps) < vminSps) sps = copysignf(vminSps, err);
        _gen.setRate(sps);
    }

    // --- calibration -----------------------------------------------------
    //
    // Open-loop probe: hand the driver a known number of steps and watch which
    // way, and how far, the encoder goes. Settles both unknowns at once -- the
    // DIR level that counts as positive, and the real steps-per-count -- then
    // walks back to where it started.
    //
    // The probe must span a whole number of OUTPUT revolutions. The AS5600's
    // integral nonlinearity is a fixed function of shaft angle, not noise: it is
    // dead repeatable at any given angle (p-p 0 counts measured standing still)
    // but it warps a partial arc. On this axis the same 1600-step move reads
    // anywhere from 1216 to 1236 counts depending on where in the turn it
    // happens -- 20 counts, plenty to fake a 0.5% ratio error. Over whole
    // revolutions the warp cancels and the number is honest: 16000 steps
    // measured 12288.0 counts, exactly 3.000 turns, +0.000% off nominal.
    //
    // The return leg's residual is the integrity check that matters -- it is the
    // only number here that cannot be explained by nonlinearity, so anything
    // beyond a couple of counts means the motor really did lose steps. Blocks
    // for roughly 2 * steps / sps seconds. Needs the driver enabled and motor
    // power connected.
    struct CalResult {
        bool ok;
        bool flipped;        // DIR polarity was inverted to agree with the encoder
        int32_t steps;       // pulses commanded
        int32_t counts;      // signed encoder counts observed
        int32_t residual;    // round-trip error in counts; nonzero = lost steps
        float stepsPerCount; // measured
        const char *note;
    };

    CalResult calibrate(int32_t steps = 16000, float sps = 1500.0f,
                        bool (*abort)() = nullptr) {
        CalResult r = {false, false, steps, 0, 0, stepsPerCount, "ok"};
        if (!_gen.enabled()) {
            r.note = "driver disabled -- enable it first (e)";
            return r;
        }
        servoOn(false);

        int32_t start = _encPos;
        _gen.moveSteps(steps, sps);
        if (!pumpEncoder(moveTimeoutMs(steps, sps), 150, abort)) {
            resyncSlip();
            r.note = "aborted";
            return r;
        }
        r.counts = _encPos - start;

        // A quarter of the expected travel is a generous floor; below it the
        // shaft is not really following and the ratio would be noise.
        int32_t expect = (int32_t)((float)steps / stepsPerCount);
        if (labs((long)r.counts) < labs((long)expect) / 4) {
            _gen.stop();
            resyncSlip();
            r.note = "encoder barely moved -- motor power off, Vref too low, "
                     "or STEP/EN not landing on the driver";
            return r;
        }

        r.stepsPerCount = (float)steps / (float)labs((long)r.counts);
        stepsPerCount = r.stepsPerCount;

        // Walk back before adopting the corrected polarity, not after: -steps
        // is only the way home while the outbound move's polarity still stands.
        // Flipping first would re-resolve -steps to the same DIR level and send
        // the shaft another turn the wrong way.
        _gen.moveSteps(-steps, sps);
        pumpEncoder(moveTimeoutMs(steps, sps), 400, abort);
        r.residual = _encPos - start;

        if (r.counts < 0) {
            _gen.flipDirPlusLevel();
            r.flipped = true;
        }

        resyncSlip();
        _target = _encPos;
        r.ok = true;
        return r;
    }

    // Open-loop jog, for poking at the mechanism with the loop out of the way.
    void jogSteps(int32_t n, float sps) {
        servoOn(false);
        _gen.moveSteps(n, sps);
    }
    void spin(float sps) {
        servoOn(false);
        _gen.setRate(sps);
    }

    // Keep the encoder integrated at ~1 kHz while the generator runs a budgeted
    // move on its own, then hold on for `settleMs` so the last steps land in the
    // measurement. `timeoutMs` is only a backstop against a wedged generator.
    // `abort` is polled throughout; returning true stops the generator and
    // bails out, so a blocking move never traps the caller.
    bool pumpEncoder(uint32_t timeoutMs, uint32_t settleMs = 150,
                     bool (*abort)() = nullptr) {
        uint32_t t0 = millis();
        uint32_t last = micros();
        while (_gen.busy() && millis() - t0 < timeoutMs) {
            if (abort && abort()) {
                _gen.stop();
                return false;
            }
            pumpOnce(last);
        }
        t0 = millis();
        while (millis() - t0 < settleMs) pumpOnce(last);
        return true;
    }

  private:
    static constexpr float VEL_ALPHA = 0.1f;     // ~17 Hz one-pole at 1 kHz
    static constexpr float SETTLE_VEL = 205.0f;  // counts/s, ~0.05 turns/s
    static constexpr float SLIP_TAU = 3.0f;      // s, slip reference leak

    // Twice the ideal duration, so a slow-but-working move is never cut short.
    static uint32_t moveTimeoutMs(int32_t steps, float sps) {
        return (uint32_t)(2000.0f * fabsf((float)steps) / fmaxf(fabsf(sps), 1.0f)) + 500;
    }

    void pumpOnce(uint32_t &last) {
        uint32_t now = micros();
        if (now - last < 1000) return;
        readEncoder((float)(now - last) * 1e-6f);
        last = now;
    }

    void readEncoder(float dt) {
        uint16_t raw = _enc.readAngle();
        int16_t d = (int16_t)((raw - _lastRaw) & 0x0FFF);
        if (d > 2048) d -= 4096;
        _lastRaw = raw;
        _encPos += d;
        if (dt > 0) _vel += VEL_ALPHA * ((float)d / dt - _vel);
    }

    AS5600 &_enc;
    StepGen &_gen;

    uint16_t _lastRaw = 0;
    int32_t _encPos = 0;   // multiturn output-shaft counts
    int32_t _target = 0;
    float _vel = 0;        // counts/s, filtered
    float _vcmd = 0;       // counts/s, slew-limited command
    float _slipRaw = 0;
    float _slipRef = 0;
    bool _servo = false;
    uint8_t _fault = FAULT_NONE;
};
