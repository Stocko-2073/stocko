#pragma once
#include <AS5600.h>
#include <ESP32MX1508.h>

// Closed-loop multiturn servo: AS5600 magnetic encoder (4096 counts/rev) + MX1508
// brushed DC driver.
//
// Call update(dt) at a fixed rate from a control task. Multiturn position is
// accumulated into an int64 (~2.2e15 turns), valid as long as the magnet moves
// less than half a revolution between updates — at 1 kHz that's 30,000 RPM,
// faster than the motor can spin.
//
// Note: the AS5600 is only absolute within one turn, so the multiturn count
// resets at power-up. Home on boot or restore a saved count with zeroHere().
class MultiTurnServo {
  public:
    static const int32_t COUNTS_PER_REV = 4096;

    enum Fault : uint8_t { FAULT_NONE = 0, FAULT_STALL, FAULT_RUNAWAY };

    // direction: +1 if the encoder count increases when motorGo() runs, -1 if it decreases.
    MultiTurnServo(AS5600& enc, MX1508& motor, int8_t direction = +1)
        : _enc(enc), _motor(motor), _dir(direction >= 0 ? 1 : -1) {}

    // Call after encoder.begin(). Position starts at 0 (or pass a restored count).
    void begin(int64_t startCounts = 0) {
        _lastRaw = _enc.readAngle();
        _position = startCounts;
        _setpoint = (double)startCounts;
        _target = startCounts;
    }

    // --- commands (safe to call from another task than update()) ---

    void moveToTurns(float turns) { moveToCounts((int64_t)llroundf(turns * COUNTS_PER_REV)); }
    void moveByTurns(float turns) { moveToCounts(targetCounts() + (int64_t)llroundf(turns * COUNTS_PER_REV)); }

    void moveToCounts(int64_t counts) {
        portENTER_CRITICAL(&_mux);
        if (!_enabled) _setpoint = (double)_position;  // don't lurch from a stale setpoint
        _target = counts;
        _enabled = true;
        _fault = FAULT_NONE;
        _stallT = _runawayT = 0;
        portEXIT_CRITICAL(&_mux);
    }

    void disable() {
        portENTER_CRITICAL(&_mux);
        _enabled = false;
        _integ = 0;
        _stallT = _runawayT = 0;
        portEXIT_CRITICAL(&_mux);
        _motor.motorStop();
    }

    // Redefine the current physical position (homing / restoring after power-up).
    void zeroHere(int64_t counts = 0) {
        portENTER_CRITICAL(&_mux);
        _position = counts;
        _setpoint = (double)counts;
        _target = counts;
        _integ = 0;
        portEXIT_CRITICAL(&_mux);
    }

    // Flip feedback sign at runtime (for finding the right wiring). Disables first.
    void setDirection(int8_t direction) {
        disable();
        _dir = direction >= 0 ? 1 : -1;
    }

    // --- state ---

    int64_t positionCounts() {
        portENTER_CRITICAL(&_mux);
        int64_t p = _position;
        portEXIT_CRITICAL(&_mux);
        return p;
    }
    float positionTurns() { return (float)positionCounts() / COUNTS_PER_REV; }
    int64_t targetCounts() {
        portENTER_CRITICAL(&_mux);
        int64_t t = _target;
        portEXIT_CRITICAL(&_mux);
        return t;
    }
    float targetTurns() { return (float)targetCounts() / COUNTS_PER_REV; }
    float velocityTps() { return _vel / COUNTS_PER_REV; }  // turns/sec
    int lastPwm() { return _lastPwm; }
    bool enabled() { return _enabled; }
    int8_t direction() { return _dir; }
    uint8_t fault() { return _fault; }
    const char* faultName() {
        switch (_fault) {
            case FAULT_STALL: return "stall (driving but not moving)";
            case FAULT_RUNAWAY: return "runaway (moving against drive — feedback sign wrong?)";
            default: return "none";
        }
    }

    // --- tuning ---

    float kp = 0.6f;    // PWM per count of error
    float ki = 0.0f;    // PWM per count-second
    float kd = 0.01f;   // PWM per count/sec
    int maxPwm = 255;
    int minPwm = 40;          // feedforward to overcome H-bridge deadband + stiction
    int32_t tolerance = 8;    // counts (~0.7 deg at the magnet); inside this we brake & rest
    float maxSpeedTps = 0;    // setpoint slew limit in turns/sec, 0 = unlimited

    // --- control loop, call at a fixed rate (e.g. 1 kHz) ---

    void update(float dt) {
        // Accumulate multiturn position with wraparound math (mod 4096, recentered).
        uint16_t raw = _enc.readAngle();
        int16_t delta = (int16_t)((raw - _lastRaw) & 0x0FFF);
        if (delta > 2048) delta -= 4096;
        _lastRaw = raw;
        int32_t step = _dir * delta;

        portENTER_CRITICAL(&_mux);
        _position += step;
        int64_t position = _position;
        int64_t target = _target;
        bool enabled = _enabled;
        portEXIT_CRITICAL(&_mux);

        // Low-pass filtered velocity in counts/sec (raw derivative of 12-bit
        // counts at 1 kHz is too noisy to feed the D term directly).
        _vel += VEL_ALPHA * ((float)step / dt - _vel);

        if (!enabled) {
            _lastPwm = 0;
            return;
        }

        // Slew the setpoint toward the target for velocity-limited moves.
        if (maxSpeedTps > 0) {
            double maxStep = (double)maxSpeedTps * COUNTS_PER_REV * dt;
            double remain = (double)target - _setpoint;
            if (remain > maxStep) remain = maxStep;
            if (remain < -maxStep) remain = -maxStep;
            _setpoint += remain;
        } else {
            _setpoint = (double)target;
        }

        // Error near the goal is small so float is exact there; clamp first so a
        // multi-million-count error doesn't lose precision (it saturates anyway).
        int64_t err64 = (int64_t)llround(_setpoint) - position;
        if (err64 > 1000000) err64 = 1000000;
        if (err64 < -1000000) err64 = -1000000;
        float err = (float)err64;

        // Settled: brake (shorted windings hold better than coast) and bleed the
        // integrator so we don't buzz/hunt around the target.
        bool atGoal = llabs(target - position) <= tolerance;
        if (atGoal && fabsf(_vel) < SETTLE_VEL) {
            _integ *= 0.95f;
            _lastPwm = 0;
            _motor.motorBrake();
            return;
        }

        _integ += ki * err * dt;
        _integ = constrain(_integ, (float)-maxPwm, (float)maxPwm);
        float u = kp * err + _integ - kd * _vel;

        int pwm = constrain((int)(fabsf(u) + minPwm), 0, maxPwm);

        // Safety: a pinned brushed motor or reversed feedback cooks the motor and
        // H-bridge. Fault out if we're driving but not moving (stall), or moving
        // away from where we're pushing (runaway = feedback sign wrong).
        // Caution: closed-loop moves slower than ~0.05 turns/s look like a stall.
        float driveSign = (u >= 0) ? 1.0f : -1.0f;
        _stallT = (fabsf(_vel) < STALL_VEL) ? _stallT + dt : 0;
        _runawayT = (_vel * driveSign < -RUNAWAY_VEL) ? _runawayT + dt : 0;
        if (_stallT > 1.0f || _runawayT > 0.3f) {
            _fault = (_runawayT > 0.3f) ? FAULT_RUNAWAY : FAULT_STALL;
            disable();
            _lastPwm = 0;
            return;
        }

        _lastPwm = (u >= 0) ? pwm : -pwm;
        if (u >= 0) _motor.motorGo(pwm);
        else _motor.motorRev(pwm);
    }

  private:
    static constexpr float VEL_ALPHA = 0.1f;      // ~18 Hz one-pole filter at 1 kHz
    static constexpr float SETTLE_VEL = 1024.0f;  // counts/sec (~0.25 rev/s)
    static constexpr float STALL_VEL = 205.0f;    // counts/sec (~0.05 rev/s)
    static constexpr float RUNAWAY_VEL = 2048.0f; // counts/sec (~0.5 rev/s)

    AS5600& _enc;
    MX1508& _motor;
    int8_t _dir;

    portMUX_TYPE _mux = portMUX_INITIALIZER_UNLOCKED;
    uint16_t _lastRaw = 0;
    int64_t _position = 0;  // counts, multiturn
    int64_t _target = 0;
    double _setpoint = 0;   // slewed setpoint (double: 52-bit mantissa covers int64 range we use)
    bool _enabled = false;
    volatile uint8_t _fault = FAULT_NONE;
    float _vel = 0;         // counts/sec, filtered
    float _integ = 0;
    int _lastPwm = 0;
    float _stallT = 0;      // seconds spent in stall/runaway condition
    float _runawayT = 0;
};
