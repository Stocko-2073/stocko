#pragma once
#include <math.h>
#include <stdint.h>
#include <stdlib.h>

#include "AS5600.h"
#include "VelGen.h"
#include "platform.h"

// Closed-loop servo: NEMA 17 through a TMC2209 in UART velocity mode, with an
// AS5600 magnetic encoder reading the *output* shaft through a 12:40 bevel
// pair. Every public number is in output-shaft units -- turns, or the encoder's
// 4096 counts per output turn -- because that is the shaft that matters.
//
// Why closed loop on a stepper at all: open-loop steps are already precise, so
// the loop is not there to fix resolution. It is there to (a) give an absolute
// reference the step counter cannot have, and (b) notice when the motor did not
// actually go where it was told.
//
// Two ways to command it:
//
//   position   moveToTurns(): P term -> velocity, sqrt(2*a*e) braking ceiling,
//              slew-limited, no integral term (a stepper has no droop to
//              integrate away), a velocity floor walks the last counts in.
//   velocity   setVelocityTps(): what a joystick wants. The commanded velocity
//              is slew-limited at the same accel and handed to the driver;
//              the encoder is not in the velocity loop -- the calibrated clock
//              gain makes VACTUAL trustworthy to a few tenths of a percent --
//              but the slip detector stays armed, so a stalled or pushed wheel
//              still faults. The position target tracks the shaft so a later
//              position command starts from where the wheel actually is.
//
// Resolution note: one encoder count is ~1.3 microsteps at 1/8, so the encoder
// is the coarser of the two. Tolerance below ~2 counts just makes it hunt.
class StepperServo {
  public:
    static const int32_t COUNTS_PER_REV = 4096;  // AS5600, output shaft

    // FAULT_PEER is raised by the drive layer on the healthy wheel when the
    // other one faults: on a differential drive, one wheel holding while the
    // other drives pivots the robot rather than stopping it.
    enum Fault : uint8_t { FAULT_NONE = 0, FAULT_SLIP, FAULT_ENCODER, FAULT_MAGNET, FAULT_PEER };

    StepperServo(AS5600 &enc, VelGen &gen) : _enc(enc), _gen(gen) {}

    // --- tuning (output-shaft units unless noted) ---
    //
    // Defaults are the fastest setting measured clean on this axis:
    //
    //   vmax  accel  kp | peak rate   worst |slip|
    //   0.5     4    12 |  2667 sps        25   clean
    //   1.0     8    16 |  5333 sps        29   clean          <- default
    //   1.5    12    20 |  8000 sps        33   marginal
    //   2.0    20    24 | 10667 sps        38   marginal
    //   3.0    30    30 | 14721 sps       144   SKIPPED, faulted
    float kp = 16.0f;          // (counts/s) per count of error, i.e. 1/s
    float vmaxTps = 1.0f;      // turns/s ceiling
    float accelTps2 = 8.0f;    // turns/s^2, also the brake authority
    float vminSps = 12.0f;     // steps/s floor while outside tolerance
    int32_t tolCounts = 3;     // ~0.26 deg at the output shaft
    float stepsPerCount = 1.302083f;  // 200 * 8 * 40/12 / 4096, exact by gearing
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

    // The EN pin itself is shared and belongs to the drive layer; this is only
    // this axis's half of the transaction.
    void enableDriver(bool on) {
        if (!on) servoOn(false);
        _gen.setEnabled(on);
    }
    bool driverEnabled() const { return _gen.enabled(); }

    // Closing the loop parks the target on the present position, so turning the
    // servo on can never make it lurch toward a stale setpoint.
    void servoOn(bool on) {
        if (on) {
            _target = _encPos;
            _vcmd = 0;
            _vgoal = 0;
            _velMode = false;
            _fault = FAULT_NONE;
            resyncSlip();
        } else {
            _gen.stop();
            _vcmd = 0;
            _vgoal = 0;
            _velMode = false;
        }
        _servo = on;
    }
    bool servoOn() const { return _servo; }
    bool velocityMode() const { return _servo && _velMode; }

    // Call this the moment anything makes the commanded integral and the
    // encoder disagree on purpose (zeroing, calibrating, open-loop jogging).
    void resyncSlip() {
        _gen.zero((double)_encPos * (double)stepsPerCount);
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

    // Raised from outside the loop: an encoder that stopped answering, a magnet
    // that went missing, or the other wheel faulting. Same consequence as a
    // slip fault -- the step generator stops, the driver holds.
    void raiseFault(Fault f) {
        if (f == FAULT_NONE) return;
        _fault = f;
        _gen.stop();
        _vcmd = 0;
        _vgoal = 0;
        _velMode = false;
        _servo = false;
    }

    // --- commands ---

    void moveToTurns(float t) { moveToCounts((int32_t)lroundf(t * COUNTS_PER_REV)); }
    void moveByTurns(float t) { moveToCounts(_target + (int32_t)lroundf(t * COUNTS_PER_REV)); }
    void moveToCounts(int32_t c) {
        _velMode = false;
        _vgoal = 0;
        _target = c;
        if (_fault == FAULT_NONE) return;
        _fault = FAULT_NONE;  // a fresh command is an implicit acknowledgement
        resyncSlip();
    }

    // Velocity mode. Needs the loop closed (servoOn(true)) so the slip detector
    // is armed; the drive layer does that. A faulted axis ignores this -- the
    // drive layer clears faults explicitly, never a joystick.
    void setVelocityTps(float tps) {
        if (!_servo || _fault != FAULT_NONE) return;
        _velMode = true;
        _vgoal = tps * COUNTS_PER_REV;
    }
    float velocityGoalTps() const { return _vgoal / COUNTS_PER_REV; }

    // --- state ---

    int32_t positionCounts() const { return _encPos; }
    float positionTurns() const { return (float)_encPos / COUNTS_PER_REV; }
    int32_t targetCounts() const { return _target; }
    float targetTurns() const { return (float)_target / COUNTS_PER_REV; }
    int32_t errorCounts() const { return _target - _encPos; }
    float velocityTps() const { return _vel / COUNTS_PER_REV; }
    float commandedTps() const { return _vcmd / COUNTS_PER_REV; }
    uint16_t rawAngle() const { return _lastRaw; }
    bool encoderOk() const { return _encOk; }
    uint32_t worstReadUs() const { return _worstUs; }
    void resetWorstRead() { _worstUs = 0; }
    int32_t slipSteps() const { return (int32_t)lroundf(_slipRaw - _slipRef); }
    bool atTarget() const { return labs((long)(_target - _encPos)) <= tolCounts; }
    uint8_t fault() const { return _fault; }
    const char *faultName() const { return faultName((Fault)_fault); }
    static const char *faultName(Fault f) {
        switch (f) {
            case FAULT_SLIP:
                return "slip (velocity commanded, shaft did not follow -- "
                       "stalled, pushed, current too low, or shaft polarity backwards)";
            case FAULT_ENCODER: return "encoder stopped answering";
            case FAULT_MAGNET:  return "encoder reports no magnet";
            case FAULT_PEER:    return "stopped because the other wheel faulted";
            default: return "none";
        }
    }

    // --- control loop, call at a fixed rate (200 Hz here) ---

    void update(float dt) {
        _gen.tick();          // integrate the commanded rate, close out budgets
        readEncoder(dt);

        // What we asked for vs. where the shaft actually got to. The reference
        // is high-passed with a leak so a steady gain error -- an uncalibrated
        // clock, a few tenths of a percent in stepsPerCount -- drifts off
        // harmlessly, while a real stall still trips.
        _slipRaw = (float)(_gen.position() - (double)_encPos * (double)stepsPerCount);
        if (_fault == FAULT_NONE) _slipRef += (_slipRaw - _slipRef) * (dt / SLIP_TAU);

        if (!_servo) return;

        if (fabsf(_slipRaw - _slipRef) > (float)slipLimit) {
            raiseFault(FAULT_SLIP);
            return;
        }

        float accel = accelTps2 * COUNTS_PER_REV;
        float vmax = vmaxTps * COUNTS_PER_REV;
        float slew = accel * dt;

        if (_velMode) {
            // The target follows the shaft: a position command issued later
            // starts from wherever the wheel actually is, not from a stale
            // setpoint left over from before the drive.
            _target = _encPos;
            float vdes = constrain(_vgoal, -vmax, vmax);
            _vcmd += constrain(vdes - _vcmd, -slew, slew);
            // Snap the tail of a deceleration to a true standstill. VACTUAL of
            // zero is a real stop, not an absence of pulses, so the chopper
            // holds position properly.
            if (vdes == 0.0f && fabsf(_vcmd) < SETTLE_VEL) _vcmd = 0;
            _gen.setRate(_vcmd * stepsPerCount);
            return;
        }

        float err = (float)(_target - _encPos);
        bool goal = fabsf(err) <= (float)tolCounts;

        // Inside tolerance and no longer coasting: stop the step generator and
        // let the driver hold.
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

        _vcmd += constrain(vdes - _vcmd, -slew, slew);

        float sps = _vcmd * stepsPerCount;
        // The last count or two of error asks for a rate rounding to nothing;
        // walk it in instead of parking just outside the band.
        if (!goal && fabsf(sps) < vminSps) sps = copysignf(vminSps, err);
        _gen.setRate(sps);
    }

    // --- calibration -----------------------------------------------------
    //
    // Two unknowns, one probe: which sign of VACTUAL makes the encoder count
    // up, and how fast the driver's oscillator really is.
    //
    // Hold a known rate, time a known distance, and see what velocity actually
    // came out. The gearing and the clock both sit in that ratio, but the
    // gearing is exact (12:40 at 1/8, measured 0.000% off over 3 output
    // turns), so what is left is clock.
    //
    // The timed window spans whole OUTPUT revolutions on purpose. The AS5600's
    // integral nonlinearity is a fixed function of shaft angle, not noise: it
    // warps a partial arc by up to 20 counts, plenty to fake a 0.5% error.
    // Over whole revolutions the warp cancels.
    //
    // Spin-up is excluded from the window at both ends. Blocks for roughly
    // twice the travel time, pumping the encoder itself. Needs the driver
    // enabled and motor power.
    struct CalResult {
        bool ok;
        bool flipped;      // shaft polarity was inverted to agree with the encoder
        int32_t counts;    // signed counts over the timed window
        int32_t back;      // counts over the equal-length return window
        float seconds;     // length of the timed window
        float sps;         // rate held during it
        float clockGain;   // measured actual/commanded velocity
        int32_t residual;  // counts + back; nonzero means a leg lost steps
        const char *note;
    };

    CalResult calibrate(int32_t outRevs = 3, float sps = 1500.0f,
                        bool (*abort)() = nullptr) {
        CalResult r = {false, false, 0, 0, 0, sps, _gen.clockGain(), 0, "ok"};
        if (!_gen.enabled()) {
            r.note = "driver disabled -- enable it first";
            return r;
        }
        servoOn(false);

        const int32_t travel = outRevs * COUNTS_PER_REV;
        const int32_t home = _encPos;
        const uint32_t timeout = legTimeoutMs(travel, sps);

        // Measure with the correction out of circuit, then put the answer back.
        float priorGain = _gen.clockGain();
        _gen.presetClockGain(1.0f);

        // --- outbound: settle, then time a whole number of revolutions ---
        _gen.setRate(sps);
        if (!pumpMs(SPINUP_MS, abort)) return calBail(r, "aborted", priorGain);

        int32_t p0 = _encPos;
        uint32_t t0 = micros();
        if (!pumpTravel(p0, travel, timeout, abort)) {
            return calBail(r, "shaft did not cover the probe distance in time", priorGain);
        }
        r.counts = _encPos - p0;
        r.seconds = (float)(micros() - t0) * 1e-6f;
        _gen.stop();
        pumpMs(SETTLE_MS, nullptr);

        if (labs((long)r.counts) < (long)travel / 2) {
            return calBail(r, "encoder barely moved -- motor power off, Vref "
                              "too low, or EN not landing on the driver", priorGain);
        }

        float achievedSps = fabsf((float)r.counts) / r.seconds * stepsPerCount;
        r.clockGain = achievedSps / sps;

        // --- return: the mirror image of that window, then home ---
        //
        // Deliberately NOT closed on the encoder. Running the same window at
        // the opposite sign and comparing distances is the only integrity
        // check velocity mode still allows. Always the opposite of the
        // outbound rate: reversing the MOTOR is the point.
        _gen.setRate(-sps);
        if (!pumpMs(SPINUP_MS, abort)) return calBail(r, "aborted", priorGain);
        int32_t p1 = _encPos;
        if (!pumpMs((uint32_t)(r.seconds * 1000.0f), abort)) {
            return calBail(r, "aborted", priorGain);
        }
        r.back = _encPos - p1;
        r.residual = r.counts + r.back;

        // Coast the rest of the way home so the axis ends where it started.
        pumpToMark(home, (r.counts > 0) ? -1 : +1, timeout, abort);
        _gen.stop();
        pumpMs(SETTLE_MS, nullptr);

        // Adopt the polarity only after the return leg: flipping first would
        // re-resolve the sign and send the shaft another turn the wrong way.
        if (r.counts < 0) {
            _gen.flipInvert();
            r.flipped = true;
        }

        _gen.setClockGain(r.clockGain);
        resyncSlip();
        _target = _encPos;
        r.ok = true;
        return r;
    }

    // Open-loop, for poking at the mechanism with the loop out of the way.
    void spin(float sps) {
        servoOn(false);
        _gen.setRate(sps);
    }

    // --- pumps ----------------------------------------------------------
    //
    // Blocking moves still have to keep the encoder integrated and the
    // commanded integral advancing, since neither has an ISR behind it. All of
    // these poll `abort` throughout, so a blocking move never traps the caller,
    // and they sleep a tick between 1 ms samples so the rest of the system
    // keeps running.

    bool pumpMs(uint32_t ms, bool (*abort)() = nullptr) {
        uint32_t t0 = millis();
        uint32_t last = micros();
        while (millis() - t0 < ms) {
            if (abort && abort()) { _gen.stop(); return false; }
            pumpOnce(last);
        }
        return true;
    }

    bool pumpTravel(int32_t from, int32_t travel, uint32_t timeoutMs,
                    bool (*abort)() = nullptr) {
        uint32_t t0 = millis();
        uint32_t last = micros();
        while (labs((long)(_encPos - from)) < (long)travel) {
            if (millis() - t0 > timeoutMs) return false;
            if (abort && abort()) { _gen.stop(); return false; }
            pumpOnce(last);
        }
        return true;
    }

    // Run until the encoder crosses `mark` travelling in `sign`. Falling short
    // is not fatal -- the caller stops where it got to.
    bool pumpToMark(int32_t mark, int sign, uint32_t timeoutMs,
                    bool (*abort)() = nullptr) {
        uint32_t t0 = millis();
        uint32_t last = micros();
        while (millis() - t0 < timeoutMs) {
            if (abort && abort()) { _gen.stop(); return false; }
            if (sign > 0 ? (_encPos >= mark) : (_encPos <= mark)) return true;
            pumpOnce(last);
        }
        return false;
    }

  private:
    static constexpr float VEL_TAU = 0.01f;      // s, ~16 Hz one-pole
    static constexpr float SETTLE_VEL = 205.0f;  // counts/s, ~0.05 turns/s
    static constexpr float SLIP_TAU = 1.0f;      // s, slip reference leak
    static const uint32_t SPINUP_MS = 400;       // excluded from the timed window
    static const uint32_t SETTLE_MS = 250;

    // Twice the ideal duration, so a slow-but-working leg is never cut short.
    uint32_t legTimeoutMs(int32_t travel, float sps) const {
        float ideal = (float)travel * stepsPerCount / fmaxf(fabsf(sps), 1.0f);
        return (uint32_t)(2000.0f * ideal) + 1000;
    }

    CalResult calBail(CalResult r, const char *note, float priorGain) {
        _gen.stop();
        _gen.presetClockGain(priorGain);
        resyncSlip();
        _target = _encPos;
        r.ok = false;
        r.note = note;
        return r;
    }

    void pumpOnce(uint32_t &last) {
        uint32_t now = micros();
        if (now - last < 1000) { pumpYield(); return; }
        _gen.tick();
        readEncoder((float)(now - last) * 1e-6f);
        last = now;
    }

    // One-pole on a time constant rather than a fixed alpha, so the corner
    // does not move with the control rate.
    //
    // A failed read holds position instead of integrating, because readAngle()
    // hands back the stale angle on error and treating that as real motion
    // would inject a step into the loop. The backoff matters on the bit-banged
    // bus: with no pull-ups SCL never rises and every read burns the full
    // stretch timeout, so a wiring fault must not cost the control loop a
    // millisecond on every tick.
    void readEncoder(float dt) {
        if (!_encOk && (int32_t)(millis() - _retryMs) < 0) return;

        uint32_t t0 = micros();
        uint16_t raw = _enc.readAngle();
        uint32_t took = micros() - t0;
        if (took > _worstUs) _worstUs = took;

        _encOk = (_enc.lastError() == AS5600::OK);
        if (!_encOk) {
            _retryMs = millis() + 100;
            return;
        }
        int16_t d = (int16_t)((raw - _lastRaw) & 0x0FFF);
        if (d > 2048) d -= 4096;
        _lastRaw = raw;
        _encPos += d;
        if (dt > 0) _vel += (dt / (VEL_TAU + dt)) * ((float)d / dt - _vel);
    }

    AS5600 &_enc;
    VelGen &_gen;

    uint16_t _lastRaw = 0;
    int32_t _encPos = 0;   // multiturn output-shaft counts
    int32_t _target = 0;
    float _vel = 0;        // counts/s, filtered
    float _vcmd = 0;       // counts/s, slew-limited command
    float _vgoal = 0;      // counts/s, velocity-mode goal
    bool _velMode = false;
    float _slipRaw = 0;
    float _slipRef = 0;
    bool _servo = false;
    uint8_t _fault = FAULT_NONE;
    bool _encOk = true;
    uint32_t _retryMs = 0;
    uint32_t _worstUs = 0;   // worst encoder read since boot
};
