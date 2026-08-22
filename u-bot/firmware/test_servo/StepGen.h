#pragma once
#include <Arduino.h>
#include <soc/gpio_reg.h>
#include <soc/soc.h>

// Hardware-timed STEP/DIR pulse generator for a stepper driver (TMC2209 here).
//
// A general-purpose timer ticks at TICK_HZ and a DDS phase accumulator decides
// which ticks emit a pulse, so the step rate is set by a 32-bit number rather
// than by how promptly loop() gets called. Steps are counted in the ISR, which
// makes position() the exact number of pulses the driver has been handed --
// the reference the encoder gets compared against.
//
// Pulse shape: a step drives STEP high on one tick and low on the next, so the
// pulse is one tick wide and the rate is capped below TICK_HZ/2. That cap also
// guarantees two pulses are never emitted on consecutive ticks, which is what
// keeps the low time between them from collapsing to a couple of clock cycles.
//
// setRate() only sets a rate; ramping belongs to the caller (StepperServo does
// it). moveSteps() is deliberately unramped and meant for slow open-loop
// probing -- start it above the motor's pull-in rate and it will just buzz.
class StepGen {
  public:
    // 25 us ticks: 20 kHz of headroom on the step rate for ~5% of the CPU.
    static const uint32_t DEFAULT_TICK_HZ = 40000;

    // enActiveLow matches the A4988/DRV8825/TMC2209 family: EN low = driving.
    void begin(uint8_t enPin, uint8_t stepPin, uint8_t dirPin,
               uint32_t tickHz = DEFAULT_TICK_HZ, bool enActiveLow = true) {
        _enPin = enPin;
        _enActiveLow = enActiveLow;
        // One 32-bit set/clear register covers every GPIO on the C6 (0..30).
        _dirPin = dirPin;
        _stepMask = 1UL << stepPin;
        _dirMask = 1UL << dirPin;

        pinMode(_enPin, OUTPUT);
        enable(false);
        pinMode(stepPin, OUTPUT);
        digitalWrite(stepPin, LOW);
        pinMode(dirPin, OUTPUT);
        digitalWrite(dirPin, LOW);
        _dirApplied = false;
        _wantDirLevel = false;

        _tickHz = tickHz;
        _maxRate = tickHz * 0.49f;
        // 1 MHz timebase, alarm every (1e6 / tickHz) counts.
        _timer = timerBegin(1000000);
        timerAttachInterruptArg(_timer, isr, this);
        timerAlarm(_timer, 1000000UL / tickHz, true, 0);
    }

    // --- driver enable ---

    void enable(bool on) {
        digitalWrite(_enPin, (on == _enActiveLow) ? LOW : HIGH);
        _enabled = on;
        if (!on) stop();
    }
    bool enabled() const { return _enabled; }

    // --- direction polarity ---

    // Which DIR level counts as the positive direction. Calibration flips this
    // until +rate makes the encoder count up.
    void setDirPlusLevel(bool level) {
        stop();
        _dirPlusLevel = level;
    }
    void flipDirPlusLevel() { setDirPlusLevel(!_dirPlusLevel); }
    bool dirPlusLevel() const { return _dirPlusLevel; }
    // The level actually on the pin right now -- reading back an output tells
    // you what the driver is seeing, which is the wiring question itself.
    bool dirPinLevel() const { return digitalRead(_dirPin) != 0; }

    // --- rate ---

    float maxRate() const { return _maxRate; }

    // Signed steps/sec, free-running (no step budget).
    void setRate(float sps) { arm(sps, false, 0); }

    // Unramped budgeted move: `n` signed steps at |sps|.
    void moveSteps(int32_t n, float sps) {
        if (n == 0) { stop(); return; }
        float mag = fabsf(sps);
        arm(n > 0 ? mag : -mag, true, n > 0 ? n : -n);
    }

    void stop() {
        _inc = 0;
        _remaining = 0;
        _budgeted = false;
        _rateSps = 0;
    }

    bool busy() const { return _inc != 0; }
    float rate() const { return _rateSps; }
    int32_t stepsLeft() const { return _remaining; }

    // --- step count ---

    // Pulses handed to the driver since begin()/zero(), signed by direction.
    // int32 at 5333 steps per output turn is ~400k turns of headroom, and a
    // 32-bit load is atomic against the ISR, so no critical section is needed.
    int32_t position() const { return _pos; }
    void zero(int32_t p = 0) { _pos = p; }

    // Called from the timer ISR.
    void tick();

  private:
    static void ARDUINO_ISR_ATTR isr(void *arg) { ((StepGen *)arg)->tick(); }

    // Lock-free handoff to the ISR: _inc is zeroed first, so the ISR either
    // sees the old rate or a stopped generator, never a torn combination of
    // rate, direction and budget.
    void arm(float sps, bool budgeted, int32_t steps) {
        _inc = 0;
        bool neg = sps < 0;
        float mag = fabsf(sps);
        if (mag > _maxRate) mag = _maxRate;

        _rateSps = neg ? -mag : mag;
        _stepDelta = neg ? -1 : 1;
        _wantDirLevel = neg ? !_dirPlusLevel : _dirPlusLevel;
        _budgeted = budgeted;
        _remaining = steps;

        if (!_enabled || mag <= 0.0f) { _rateSps = 0; return; }
        _inc = (uint32_t)((double)mag / (double)_tickHz * 4294967296.0);
        if (_inc == 0) _inc = 1;  // slower than one step per ~4 billion ticks
    }

    hw_timer_t *_timer = nullptr;
    uint32_t _tickHz = DEFAULT_TICK_HZ;
    float _maxRate = 0;

    uint8_t _enPin = 0;
    uint8_t _dirPin = 0;
    bool _enActiveLow = true;
    bool _enabled = false;
    uint32_t _stepMask = 0;
    uint32_t _dirMask = 0;

    bool _dirPlusLevel = true;  // DIR level that makes position() count up
    volatile bool _wantDirLevel = true;
    bool _dirApplied = false;   // ISR-only
    bool _pulseHigh = false;    // ISR-only

    volatile uint32_t _inc = 0;       // DDS increment per tick, 0 = idle
    uint32_t _accum = 0;              // ISR-only
    volatile int8_t _stepDelta = 1;
    volatile bool _budgeted = false;
    volatile int32_t _remaining = 0;
    volatile int32_t _pos = 0;
    volatile float _rateSps = 0;
};

inline void ARDUINO_ISR_ATTR StepGen::tick() {
    // Close out the pulse opened on the previous tick.
    if (_pulseHigh) {
        REG_WRITE(GPIO_OUT_W1TC_REG, _stepMask);
        _pulseHigh = false;
    }

    uint32_t inc = _inc;
    if (inc == 0) {
        _accum = 0;
        return;
    }

    // Retime a direction change onto its own tick: the driver samples DIR on
    // the STEP edge, and back-to-back register writes would leave it only a
    // few nanoseconds of setup. One skipped tick is 25 us, and reversals only
    // happen where the commanded rate crosses zero.
    bool want = _wantDirLevel;
    if (want != _dirApplied) {
        REG_WRITE(want ? GPIO_OUT_W1TS_REG : GPIO_OUT_W1TC_REG, _dirMask);
        _dirApplied = want;
        return;
    }

    uint32_t prev = _accum;
    _accum += inc;
    if (_accum >= prev) return;  // no wrap this tick, no pulse

    if (_budgeted) {
        if (_remaining <= 0) {
            _inc = 0;
            return;
        }
        int32_t left = _remaining - 1;     // read-modify-write, spelled out:
        _remaining = left;                 // volatile -- ++/-- is deprecated
        if (left == 0) _inc = 0;           // this was the last one
    }

    REG_WRITE(GPIO_OUT_W1TS_REG, _stepMask);
    _pulseHigh = true;
    _pos += _stepDelta;
}
