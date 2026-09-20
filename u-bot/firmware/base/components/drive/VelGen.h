#pragma once
#include <math.h>
#include <stdint.h>

#include "Tmc2209Uart.h"
#include "platform.h"
#include "MotorCurrent.h"

// Velocity actuator for a TMC2209 over its single-wire UART.
//
// The driver runs its own step generator from the VACTUAL register and its own
// oscillator, and nothing comes back. So:
//
//   position()   the integral of what we ASKED for, not a tally of what
//                happened. Compare it against the encoder and the difference
//                is real, but it includes clock error as well as slip.
//   clockGain    the TMC2209's internal 12 MHz oscillator is only good to
//                about +/-10%, which lands as a straight velocity gain error.
//                calibrate() measures it; until then commanded speed is off by
//                however far the chip's clock is. It is a property of the
//                individual chip and is persisted per wheel in NVS.
//
// Writes are only issued when the register value actually changes, so holding
// a steady rate -- or standing still -- costs nothing on the bus.
class VelGen {
  public:
    // VACTUAL is signed 24-bit; one LSB is f_clk / 2^24 = 0.715 steps/s, so
    // quantisation is ~0.09 mm/s at the wheel and never the limiting factor.
    static constexpr float FCLK        = 12000000.0f;
    static constexpr float VACTUAL_LSB = FCLK / 16777216.0f;
    static constexpr int32_t VACTUAL_MAX = 8388607;

    // Not a hardware ceiling -- the driver would happily accept far more. This
    // is a guard rail at ~3 output turns/s, above the 2.76 where this axis was
    // measured to shed steps.
    static constexpr float DEFAULT_MAX_RATE = 16000.0f;

    VelGen(Tmc2209Uart &uart, uint8_t addr) : _uart(uart), _addr(addr) {}

    // EN is deliberately not ours. It is one pin shared by every driver on the
    // bus, so the drive layer owns it and parks it high before any of this
    // runs. Refuses an active EN pin, missing driver, failed configuration, or fault.
    bool begin(uint16_t microsteps = 8) {
        _enabled = false;
        _ok = false;
        _rate = 0;
        _budgeted = false;
        _remaining = 0;
        _lastUs = micros();
        _uart.read(_addr, Tmc2209Uart::IOIN); // discard startup framing glitch
        delayMs(5);
        auto r = _uart.read(_addr, Tmc2209Uart::IOIN);
        _version = r.st == Tmc2209Uart::OK ? (uint8_t)(r.value >> 24) : 0;
        _lastStatus = r.st;
        // Initialization is only allowed with the physical output disabled.
        if (r.st != Tmc2209Uart::OK || _version != 0x21 || !(r.value & 1)) return false;
        _spreadPin = (r.value & (1UL << 8)) != 0;
        _gconf = (1UL << 6) | (1UL << 7) | (1UL << 8);
        if (_invert) _gconf |= 1UL << 3;
        if (_spread != _spreadPin) _gconf |= 1UL << 2;
        // Analog scaling and internal sense resistors are both off.
        _ok = true;
        if (!writeChecked(Tmc2209Uart::VACTUAL, 0)) return false;
        _lastVactual = 0;
        if (!writeGconf() || !setMicrosteps(microsteps) || !writeCurrent() ||
            !writePwmThreshold() || !writeChecked(Tmc2209Uart::TPOWERDOWN, 20) ||
            !writeChecked(Tmc2209Uart::GSTAT, 7)) return false;
        r = _uart.read(_addr, Tmc2209Uart::GSTAT);
        if (r.st != Tmc2209Uart::OK || (r.value & 7)) return fail();
        r = _uart.read(_addr, Tmc2209Uart::DRVSTATUS);
        if (r.st != Tmc2209Uart::OK || (r.value & 0x3F)) return fail();
        return true;
    }

    void invalidate() { _ok = false; }

    bool ok() const { return _ok; }
    uint8_t version() const { return _version; }
    uint8_t address() const { return _addr; }
    Tmc2209Uart::Status lastStatus() const { return _lastStatus; }

    // --- driver enable ---

    // Zero velocity before energising, always. Re-enabling with a live VACTUAL
    // is the one way this axis can lurch without being told to. Call this on
    // every driver BEFORE the shared EN goes low, and after it goes high.
    void setEnabled(bool on) {
        if (on) {
            if (!_ok || !writeChecked(Tmc2209Uart::VACTUAL, 0)) {
                _enabled = false;
                return;
            }
            _lastVactual = 0;
            _rate = 0;
        }
        _enabled = on && _ok;
        if (!on) stop();
    }
    bool enabled() const { return _enabled; }

    // --- direction polarity ---

    // Which way is positive, held in the driver's own GCONF.shaft bit rather
    // than by negating on our side. It reads back, which makes it answerable.
    void setInvert(bool inv) {
        stop();
        _invert = inv;
        if (inv) _gconf |= (1UL << 3); else _gconf &= ~(1UL << 3);
        if (_ok) writeGconf();
    }
    void flipInvert() { setInvert(!_invert); }
    bool inverted() const { return _invert; }

    int8_t shaftBit() {
        Tmc2209Uart::Result r = _uart.read(_addr, Tmc2209Uart::GCONF);
        return (r.st == Tmc2209Uart::OK) ? (int8_t)((r.value >> 3) & 1) : -1;
    }

    // --- microstepping ---

    // Only meaningful because mstep_reg_select is set: MRES in CHOPCONF wins
    // over the MS1/MS2 pins. The driver interpolates to 256 regardless.
    bool setMicrosteps(uint16_t m) {
        int8_t mres = -1;
        switch (m) {
            case 256: mres = 0; break;  case 128: mres = 1; break;
            case 64:  mres = 2; break;  case 32:  mres = 3; break;
            case 16:  mres = 4; break;  case 8:   mres = 5; break;
            case 4:   mres = 6; break;  case 2:   mres = 7; break;
            case 1:   mres = 8; break;
            default: return false;
        }
        Tmc2209Uart::Result r = _uart.read(_addr, Tmc2209Uart::CHOPCONF);
        if (r.st != Tmc2209Uart::OK) return fail();
        delayMs(2);
        // Fix vsense=0 to match the digital mA conversion; retain chopper timing.
        uint32_t c = (r.value & ~((0xFUL << 24) | (1UL << 17))) | ((uint32_t)mres << 24);
        if (!(c & 15) || !writeChecked(Tmc2209Uart::CHOPCONF, c)) return fail();
        r = _uart.read(_addr, Tmc2209Uart::CHOPCONF);
        if (r.st != Tmc2209Uart::OK || r.value != c) return fail();
        _microsteps = m;
        return writePwmThreshold();
    }
    uint16_t microsteps() const { return _microsteps; }

    // --- current ---

    // Stage settings while disabled. begin() verifies them before EN goes low.
    bool setCurrentMa(int runMa, int holdMa, int delay) {
        if (_enabled || !MotorCurrent::valid(runMa, holdMa) || delay < 0 || delay > 15) return false;
        _irun = MotorCurrent::scale(runMa);
        _ihold = MotorCurrent::scale(holdMa);
        _iholdDelay = (uint8_t)delay;
        _ok = false;
        return true;
    }
    float runMilliamps() const { return MotorCurrent::milliamps(_irun); }
    float holdMilliamps() const { return MotorCurrent::milliamps(_ihold); }
    uint8_t runCurrent() const { return _irun; }
    uint8_t holdCurrent() const { return _ihold; }
    uint8_t holdDelay() const { return _iholdDelay; }

    // --- chopper ---

    // Stage chopper selection. SPREAD pin polarity is accounted for at begin().
    void setSpreadCycle(bool on) {
        _spread = on;
        _ok = false;
    }
    bool spreadCycle() const { return _spread; }

    // Hand StealthChop over to SpreadCycle above this step rate: quiet when
    // crawling, strong when moving. Only means anything while spreadCycle() is
    // off, since with it on SpreadCycle already runs everywhere. 0 disables
    // the handover, which is the TMC2209's own reset state.
    //
    // Note the shape of TPWMTHRS: it is a TSTEP threshold, a step INTERVAL in
    // driver clocks, so a HIGHER speed is a SMALLER number. The driver's clock
    // times the interval and also generates the steps, so clockGain belongs on
    // both sides -- see pwmThresholdReg().
    void setSpreadAboveRate(float sps) {
        _spreadAboveSps = fabsf(sps);
        _ok = false;
    }
    float spreadAboveRate() const { return _spreadAboveSps; }

    // --- rate ---

    float maxRate() const { return _maxRate; }
    void setMaxRate(float r) { _maxRate = fabsf(r); }

    // Signed steps/s, free-running.
    void setRate(float sps) {
        accrue();
        _budgeted = false;
        _remaining = 0;
        applyRate(sps);
    }

    // Budgeted move, closed on our own integral rather than on emitted pulses:
    // it runs until we have COMMANDED n steps' worth of time at this rate.
    void moveSteps(double n, float sps) {
        accrue();
        if (n == 0) { stop(); return; }
        float mag = fabsf(sps);
        _remaining = fabs(n);
        _budgeted = true;
        applyRate(n > 0 ? mag : -mag);
    }

    void stop() {
        accrue();
        _budgeted = false;
        _remaining = 0;
        applyRate(0);
    }

    bool busy() const { return _budgeted && _remaining > 0; }
    float rate() const { return _rate; }
    double stepsLeft() const { return _remaining; }

    // --- commanded position ---

    // The integral of the commanded rate. Fractional on purpose: at 200 Hz a
    // tick is a few dozen steps and rounding each one would walk away visibly.
    double position() const { return _pos; }
    void zero(double p = 0) { _pos = p; }

    // Integrate, and close out a budgeted move. Must be called regularly.
    void tick() {
        accrue();
        if (_budgeted && _remaining <= 0) {
            _budgeted = false;
            applyRate(0);
        }
    }

    // --- measured clock gain ---

    float clockGain() const { return _clockGain; }

    // Measured by calibrate(), on this driver, today.
    void setClockGain(float g) { applyGain(g); _measured = true; }

    // Carried over from NVS. Close enough to start with -- the oscillator is a
    // property of the individual chip and it drifts with temperature.
    void presetClockGain(float g) { applyGain(g); _measured = false; }

    bool calibrated() const { return _measured; }

    // --- driver status passthrough ---

    uint32_t readReg(uint8_t reg, bool *okOut = nullptr) {
        Tmc2209Uart::Result r = _uart.read(_addr, reg);
        if (okOut) *okOut = (r.st == Tmc2209Uart::OK);
        return (r.st == Tmc2209Uart::OK) ? r.value : 0;
    }

  private:
    void applyGain(float g) {
        if (g > 0.5f && g < 2.0f) _clockGain = g;
        // The handover threshold is a clock-domain number too, so a newly
        // measured gain moves it by however far the chip's oscillator is off.
        if (_ok && _spreadAboveSps > 0) writePwmThreshold();
        applyRate(_rate);   // the correction takes effect immediately
    }

    bool fail() { _ok = false; return false; }

    // The single control mutex serializes config with velocity writes.
    // Echo alone is not acknowledgement: IFCNT must advance even at wraparound.
    bool writeChecked(uint8_t reg, uint32_t value) {
        auto before = _uart.read(_addr, Tmc2209Uart::IFCNT);
        if (before.st != Tmc2209Uart::OK) return fail();
        auto wr = _uart.write(_addr, reg, value);
        if (wr.st != Tmc2209Uart::OK) return fail();
        auto after = _uart.read(_addr, Tmc2209Uart::IFCNT);
        if (after.st != Tmc2209Uart::OK ||
            (uint8_t)(after.value - before.value) != 1) return fail();
        return true;
    }

    bool writeGconf() {
        if (!writeChecked(Tmc2209Uart::GCONF, _gconf)) return false;
        auto r = _uart.read(_addr, Tmc2209Uart::GCONF);
        if (r.st != Tmc2209Uart::OK || r.value != _gconf) return fail();
        return true;
    }

    bool writeCurrent() {
        uint32_t v = (uint32_t)_ihold | ((uint32_t)_irun << 8) | ((uint32_t)_iholdDelay << 16);
        return writeChecked(Tmc2209Uart::IHOLD_IRUN, v);
    }

    // TSTEP is normalized to 256 microsteps, independent of selected MRES.
    uint32_t pwmThresholdReg() const {
        if (_spreadAboveSps <= 0) return 0;
        double t = (double)FCLK * _clockGain * _microsteps / (256.0 * _spreadAboveSps);
        if (t > 1048575.0) t = 1048575.0;
        if (t < 1.0) t = 1.0;
        return (uint32_t)t;
    }

    bool writePwmThreshold() {
        return writeChecked(Tmc2209Uart::TPWMTHRS, pwmThresholdReg());
    }

    // Integrate the rate that has been standing since the last call, then leave
    // the clock at now. Every path that changes the rate goes through here
    // first, so the integral never attributes time to the wrong rate.
    void accrue() {
        uint32_t now = micros();
        uint32_t el = now - _lastUs;
        _lastUs = now;
        if (el > 500000UL) return;   // a gap that long is a stall, not motion
        if (_rate == 0) return;
        double d = (double)_rate * (double)el * 1e-6;
        _pos += d;
        if (_budgeted) {
            _remaining -= fabs(d);
            if (_remaining < 0) _remaining = 0;
        }
    }

    void applyRate(float sps) {
        if (!_enabled || !_ok) sps = 0;
        if (sps > _maxRate) sps = _maxRate;
        if (sps < -_maxRate) sps = -_maxRate;
        _rate = sps;
        writeVactual(vactualFor(sps));
    }

    int32_t vactualFor(float sps) const {
        float v = sps / (VACTUAL_LSB * _clockGain);
        if (v > (float)VACTUAL_MAX) v = (float)VACTUAL_MAX;
        if (v < -(float)VACTUAL_MAX) v = -(float)VACTUAL_MAX;
        return (int32_t)lroundf(v);
    }

    // Skip the write when nothing changed: at 200 Hz a needless write on every
    // tick would be CPU spent telling the driver what it knows.
    void writeVactual(int32_t v) {
        if (v == _lastVactual) return;
        if (!_ok) return;
        auto r = _uart.write(_addr, Tmc2209Uart::VACTUAL, (uint32_t)v);
        if (r.st != Tmc2209Uart::OK) { fail(); return; }
        _lastVactual = v;
    }

    Tmc2209Uart &_uart;
    uint8_t _addr;
    bool _ok = false;
    uint8_t _version = 0;
    Tmc2209Uart::Status _lastStatus = Tmc2209Uart::NO_ECHO;

    bool _enabled = false;
    bool _invert = false;
    uint32_t _gconf = 0x000001C4UL;
    uint16_t _microsteps = 8;
    uint8_t _irun = MotorCurrent::scale(MotorCurrent::DEFAULT_RUN_MA);
    uint8_t _ihold = MotorCurrent::scale(MotorCurrent::DEFAULT_HOLD_MA);
    uint8_t _iholdDelay = 8;
    bool _spread = true;
    bool _spreadPin = false;
    float _spreadAboveSps = 0;

    float _rate = 0;             // commanded steps/s
    float _maxRate = DEFAULT_MAX_RATE;
    float _clockGain = 1.0f;
    bool _measured = false;
    int32_t _lastVactual = 0x7FFFFFFF;   // force the first write

    double _pos = 0;             // integrated commanded steps
    double _remaining = 0;
    bool _budgeted = false;
    uint32_t _lastUs = 0;
};
