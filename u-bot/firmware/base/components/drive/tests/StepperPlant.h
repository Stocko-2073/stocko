#pragma once
#include <math.h>
#include <stdint.h>

#include <deque>

#include "MotorCurrent.h"
#include "Tmc2209Uart.h"
#include "fake_tmc.h"

// One drive axis as physics, for the host rig: the TMC2209's field, the
// motor's torque on the rotor, the load, the gear's backlash and the AS5600 on
// the output shaft. Deterministic -- the same test gives the same numbers.
//
// Everything positional is in motor microsteps at 1/8 (DRIVE_MECHANISM.md):
// 1600 per motor rev, 32 per electrical cycle, 5333.33 per output turn,
// 1.302083 per encoder count. Speeds and torques are at the motor shaft (rad/s,
// N m); loads are referred there too, positive resisting motion in the motor's
// + direction. On the robot's wiring (inv_a 0, inv_b 1, sign_b -1) that is
// robot-forward for both wheels, so a hill is a positive load on both.
//
// The plant reads the driver's registers straight from its FakeTmc node and
// supplies the registers the chip computes (MSCNT, CS_ACTUAL/stst) through the
// node's read hook, so the real VelGen drives it exactly as it drives a chip.
// Each step() is one 100 us substep:
//
//   field    xf += int24(VACTUAL) * (12 MHz * gTrue / 2^24) * shaft * h, where
//            gTrue is the chip's real oscillator and shaft is GCONF bit 3.
//   current  IRUN while stepping; once VACTUAL has been 0 for 2^20 clocks plus
//            TPOWERDOWN * 2^18, one CS per IHOLDDELAY * 2^18 clocks down to
//            IHOLD (IHOLDDELAY 0: at once). A raised IHOLD applies at once.
//            The phase current follows with a 1.6 ms lag.
//   torque   Tm = Kt sqrt(2) I sin(2 pi (xf - xr) / 32), I in A RMS.
//   rotor    J w' = Tm - T_load - b w - friction, semi-implicit Euler, the
//            damping terms implicit so a steep friction knee cannot go unstable.
//   output   xo trails xr through a dead band of `backlash` microsteps.
//   encoder  xo / 1.302083 * encSign plus two-harmonic INL, through the
//            AS5600's 0.7 ms filter, floored to 12 bits when read.
//
// What it leaves out, deliberately: detent torque, the driver's voltage limit
// at speed, chopper ripple, the robot's body coupling the two wheels (each
// wheel carries its own share of the robot's inertia), and the output's own
// inertia while it crosses the backlash.
class StepperPlant {
  public:
    // --- the mechanism, exact by gearing ---
    static constexpr double PI = 3.14159265358979323846;
    static constexpr double MS_PER_MOTOR_REV = 1600.0;    // 200 full steps x 8
    static constexpr double MS_PER_CYCLE = 32.0;          // one electrical cycle, 4 full steps
    static constexpr double GEAR = 40.0 / 12.0;
    static constexpr double MS_PER_OUT_TURN = MS_PER_MOTOR_REV * GEAR;   // 5333.33
    static constexpr double MS_PER_COUNT = MS_PER_OUT_TURN / 4096.0;     // 1.302083
    static constexpr double MS_PER_RAD = MS_PER_MOTOR_REV / (2.0 * PI);  // at the motor

    // --- motor and driver ---
    // 17HS15-1504S-X1: 0.45 N m holding at 1.5 A RMS (2.12 A peak per phase).
    static constexpr double KT = 0.2121;              // N m per A peak
    static constexpr double SQRT2 = 1.41421356237309505;
    static constexpr double FCLK = 12e6;              // nominal; the chip runs at FCLK * gTrue
    static constexpr int64_t H_US = 100;              // substep
    static constexpr double H = H_US * 1e-6;

    // --- inertia at the motor, and what hangs off the wheel ---
    static constexpr double J_GROUND = 0.0026;        // kg m^2: rotor, wheel and a share of the robot
    static constexpr double J_RACK = 2.3e-4;          // rotor and wheel only, wheel clear
    static constexpr double WHEEL_R = 0.1075;         // m, to the tread tips
    static constexpr double GRAVITY = 9.81;
    static constexpr double NM_PER_KG = GRAVITY * WHEEL_R / GEAR;         // 0.316 N m per kg hung
    static constexpr double J_PER_KG = WHEEL_R * WHEEL_R / (GEAR * GEAR); // kg m^2 per kg hung
    static constexpr double GRADE_NM = 0.639;         // N m per motor on a vertical face

    // Peak motor torque at a phase current, i.e. the static pull-out torque.
    static double pulloutNm(double mA) { return KT * SQRT2 * mA * 1e-3; }
    static double tpsToRadS(double tps) { return tps * GEAR * 2.0 * PI; }

    struct Params {
        double gTrue = 1.0;        // the driver's real oscillator over 12 MHz
        double J = J_GROUND;       // kg m^2 at the motor, not counting a hung mass
        double b = 5e-4;           // N m s/rad viscous loss: ~3% of pull-out at 1 turn/s
        double backlash = 0;       // microsteps of dead band between rotor and output
        int encSign = +1;          // which way the encoder counts for output motion in +
        double encOffset = 0;      // counts: where the magnet happens to sit at xo = 0
        double inlA1 = 8, inlPhi1 = 0.9;   // counts, rad: once per output turn
        double inlA2 = 3, inlPhi2 = 2.4;   // twice per output turn
        double encTau = 0.7e-3;    // s, the AS5600's output filter at SF 16x
        double curTau = 1.6e-3;    // s, phase current response
        bool flicker = false;      // +/-1 count on each read, from a seeded LCG
        uint32_t seed = 12345;
    };

    // One load, referred to the motor. Add them with the add*() calls below;
    // several of any kind may act at once and their torques sum.
    struct Load {
        enum Kind : uint8_t { CONST, GRADE, STEP, PULSE, FRICTION, BUMP, WALL, HUNG };
        Kind kind = CONST;
        double nm = 0;            // CONST/GRADE/STEP/PULSE torque, FRICTION level, BUMP peak
        double t0 = 0, t1 = INFINITY;   // s: STEP/PULSE act over [t0, t1); HUNG ramps from t0
        double x0 = 0, width = 0; // microsteps: BUMP over [x0, x0+width); WALL face; HUNG taut point
        double k = 50, zeta = 0.3;      // WALL: N m/rad spring and its damping ratio
        double breakNm = INFINITY;      // WALL: gives way above this
        double w0 = 0.05;         // FRICTION: rad/s, knee of the tanh
        double kg = 0, kgPerS = 0;      // HUNG: mass, and how fast it grows from t0
        // What happened, for the test to read.
        double contactT = -1;     // WALL: first contact; HUNG: first lift (plant s)
        bool broken = false;      // WALL: pushed past breakNm
        double lastNm = 0;        // torque applied in the latest substep
        double peakNm = 0;

        // HUNG: the mass on the string now.
        double massAt(double t) const { return kg + (t > t0 ? kgPerS * (t - t0) : 0); }
    };

    // Attaches to the FakeTmc node at `addr` for as long as it lives.
    explicit StepperPlant(uint8_t addr) : StepperPlant(addr, Params()) {}
    StepperPlant(uint8_t addr, const Params &p) : _addr(addr), _p(p) {
        _lcg = p.seed;
        _jPrev = p.J;
        _enc = trueCounts();
        FakeTmc::Node &n = FakeTmc::node(_addr);
        n.onRead = [this](uint8_t reg, uint32_t &v) { return supply(reg, v); };
    }
    ~StepperPlant() { FakeTmc::node(_addr).onRead = nullptr; }
    StepperPlant(const StepperPlant &) = delete;
    StepperPlant &operator=(const StepperPlant &) = delete;

    Params &params() { return _p; }
    const Params &params() const { return _p; }

    // The shared EN pin, low = power stage on. Off, the current decays and the
    // rotor is free: on a slope it rolls.
    void setEnergized(bool on) { _energized = on; }
    bool energized() const { return _energized; }

    // --- loads ---

    Load &addConst(double nm) { return add(Load::CONST, nm); }
    Load &addGrade(double deg) { return add(Load::GRADE, GRADE_NM * sin(deg * PI / 180.0)); }
    Load &addStep(double nm, double t0, double t1 = INFINITY) {
        Load &l = add(Load::STEP, nm);
        l.t0 = t0;
        l.t1 = t1;
        return l;
    }
    Load &addPulse(double nm, double t0, double t1) {
        Load &l = add(Load::PULSE, nm);
        l.t0 = t0;
        l.t1 = t1;
        return l;
    }
    // Coulomb, both ways, smoothed through zero speed: nm * tanh(w / w0).
    Load &addFriction(double nm, double w0 = 0.05) {
        Load &l = add(Load::FRICTION, nm);
        l.w0 = w0;
        return l;
    }
    // A ridge in position: a half-sine of torque over [x0, x0+width) microsteps.
    Load &addBump(double peakNm, double x0, double width) {
        Load &l = add(Load::BUMP, peakNm);
        l.x0 = x0;
        l.width = width;
        return l;
    }
    // A face at output position x (microsteps). It pushes back as a damped
    // spring once the output passes it, never pulls, and optionally gives way.
    Load &addWall(double x, double k = 50, double zeta = 0.3, double breakNm = INFINITY) {
        Load &l = add(Load::WALL, 0);
        l.x0 = x;
        l.k = k;
        l.zeta = zeta;
        l.breakNm = breakNm;
        return l;
    }
    // The weight-lift fixture: a mass on a string tied to the tread, taut from
    // output position xTaut (default: here) and lifted as the output moves in
    // +. Below xTaut it rests on the floor and the string is slack. While
    // lifted it adds its weight and its inertia; kgPerS grows it from t0.
    Load &hangMass(double kg, double kgPerS = 0, double xTaut = NAN, double t0 = NAN) {
        Load &l = add(Load::HUNG, 0);
        l.kg = kg;
        l.kgPerS = kgPerS;
        l.x0 = isnan(xTaut) ? _xo : xTaut;
        l.t0 = isnan(t0) ? _t : t0;
        return l;
    }
    std::deque<Load> &loads() { return _loads; }   // references stay valid as loads are added
    void clearLoads() { _loads.clear(); }

    // --- stepping ---

    // Simulate `us` more microseconds, carrying any part of a substep over to
    // the next call. This is what the clock hook calls.
    void advance(int64_t us) {
        _pendingUs += us;
        while (_pendingUs >= H_US) {
            step();
            _pendingUs -= H_US;
        }
    }

    void step() {
        const uint32_t *r = FakeTmc::node(_addr).regs;

        // --- the driver: field ---
        int32_t vact = (int32_t)(r[Tmc2209Uart::VACTUAL] & 0xFFFFFF);
        if (vact & 0x800000) vact -= 0x1000000;
        int shaft = (r[Tmc2209Uart::GCONF] >> 3) & 1 ? -1 : +1;
        // VACTUAL counts microsteps at the selected MRES; the plant's unit is 1/8.
        int mres = (int)((r[Tmc2209Uart::CHOPCONF] >> 24) & 15);
        double perEighth = 8.0 / (double)(256 >> (mres > 8 ? 8 : mres));
        double fclk = FCLK * _p.gTrue;
        _xf += (double)vact * (fclk / 16777216.0) * shaft * perEighth * H;

        // --- the driver: current ---
        uint32_t ihr = r[Tmc2209Uart::IHOLD_IRUN];
        int ihold = (int)(ihr & 31), irun = (int)((ihr >> 8) & 31), delay = (int)((ihr >> 16) & 15);
        double tDown = ststSeconds() + (double)(r[Tmc2209Uart::TPOWERDOWN] & 255) * 262144.0 / fclk;
        _stillS = vact != 0 ? 0 : _stillS + H;
        if (vact != 0 || _stillS < tDown) {
            _cs = irun;
            _rampS = 0;
        } else if (delay == 0 || _cs <= ihold) {
            _cs = ihold;
        } else if ((_rampS += H) >= delay * 262144.0 / fclk) {
            _rampS -= delay * 262144.0 / fclk;
            _cs--;
        }
        double target = _energized ? MotorCurrent::milliamps((uint8_t)_cs) * 1e-3 : 0.0;
        _i += (target - _i) * (1.0 - exp(-H / _p.curTau));

        // --- the loads, where the output stands ---
        double jHung = 0;
        double tl = loadsAt(_t, _xo, _w, true, &jHung);

        // --- the rotor ---
        double j = _p.J + jHung;
        // Taking up a mass at rest shares the momentum; setting one down does not.
        if (j > _jPrev) _w *= _jPrev / j;
        _jPrev = j;
        _tm = KT * SQRT2 * _i * sin(2.0 * PI * (_xf - _xr) / MS_PER_CYCLE);
        double fr = 0, dfr = 0;   // Coulomb friction and its slope at the present speed
        for (const Load &l : _loads) {
            if (l.kind != Load::FRICTION) continue;
            double s = tanh(_w / l.w0);
            fr += l.nm * s;
            dfr += l.nm * (1.0 - s * s) / l.w0;
        }
        double hj = H / j;
        _w = (_w + hj * (_tm - tl - fr + dfr * _w)) / (1.0 + hj * (_p.b + dfr));
        _xr += _w * MS_PER_RAD * H;
        for (Load &l : _loads) {
            if (l.kind != Load::FRICTION) continue;
            l.lastNm = l.nm * tanh(_w / l.w0);
            if (fabs(l.lastNm) > l.peakNm) l.peakNm = fabs(l.lastNm);
        }
        _tl = tl;

        // --- the output, through the backlash ---
        // A massless output: whichever face of the dead band reaches it drags
        // it, and a load that pushes it holds it against the face it pushes
        // toward. Friction does not move it, so a reversal on the flat crosses
        // the whole gap with the output standing still.
        double half = _p.backlash * 0.5;
        double lo = _xr - half, hi = _xr + half;
        double xo = _xo < lo ? lo : (_xo > hi ? hi : _xo);
        if (half > 0) {
            double probe = loadsAt(_t, xo, _w, false);
            if (probe > 0) xo = lo;
            else if (probe < 0) xo = hi;
        }
        _xo = xo;

        // --- the encoder ---
        _enc += (trueCounts() - _enc) * (1.0 - exp(-H / _p.encTau));
        _t += H;
    }

    // --- the encoder, as the AS5600 reports it ---

    // Filtered, floored, 12 bits: what a read of ANGLE returns now.
    uint16_t encoderAngle() {
        int64_t v = (int64_t)floor(_enc);
        if (_p.flicker) {
            _lcg = _lcg * 1664525u + 1013904223u;
            v += (int64_t)((_lcg >> 16) % 3) - 1;
        }
        return (uint16_t)(v & 4095);
    }
    double encoderCounts() const { return _enc; }   // filtered, unwrapped, unquantized

    // --- the driver's computed registers ---

    uint32_t mscnt() const { return (uint32_t)((int64_t)floor(_xf * 32.0) & 1023); }
    int csActual() const { return _cs; }
    bool standstill() const { return _stillS >= ststSeconds(); }

    // --- ground truth ---

    double t() const { return _t; }            // s since the plant was made
    double xf() const { return _xf; }          // field, microsteps
    double xr() const { return _xr; }          // rotor, microsteps
    double xo() const { return _xo; }          // output, microsteps
    double w() const { return _w; }            // rotor, rad/s
    double outputTurns() const { return _xo / MS_PER_OUT_TURN; }
    double outputTps() const { return _w / (GEAR * 2.0 * PI); }   // the rotor's speed, in output turns/s
    double currentA() const { return _i; }     // A RMS
    double motorNm() const { return _tm; }
    double loadNm() const { return _tl; }      // active loads, excluding friction
    // Field ahead of rotor in electrical degrees, unwrapped: past +/-180 the
    // rotor has let go, and every further 360 is one electrical cycle lost.
    double loadAngleDeg() const { return (_xf - _xr) * 360.0 / MS_PER_CYCLE; }

  private:
    Load &add(Load::Kind k, double nm) {
        _loads.emplace_back();
        Load &l = _loads.back();
        l.kind = k;
        l.nm = nm;
        return l;
    }

    double ststSeconds() const { return 1048576.0 / (FCLK * _p.gTrue); }   // 2^20 clocks

    double trueCounts() const {
        double turns = _xo / MS_PER_OUT_TURN;
        return _xo / MS_PER_COUNT * _p.encSign + _p.encOffset +
               _p.inlA1 * sin(2.0 * PI * turns + _p.inlPhi1) +
               _p.inlA2 * sin(4.0 * PI * turns + _p.inlPhi2);
    }

    // Sum of the loads that push (all but friction) with the output at xo.
    // Only a committed evaluation records contact, breakage and the torques.
    double loadsAt(double t, double xo, double w, bool commit, double *jHung = nullptr) {
        double sum = 0;
        for (Load &l : _loads) {
            double T = 0;
            switch (l.kind) {
                case Load::CONST:
                case Load::GRADE:
                    T = l.nm;
                    break;
                case Load::STEP:
                case Load::PULSE:
                    T = (t >= l.t0 && t < l.t1) ? l.nm : 0;
                    break;
                case Load::FRICTION:
                    continue;
                case Load::BUMP:
                    if (xo >= l.x0 && xo < l.x0 + l.width) T = l.nm * sin(PI * (xo - l.x0) / l.width);
                    break;
                case Load::WALL: {
                    double d = (xo - l.x0) / MS_PER_RAD;   // rad into the face, at the motor
                    if (l.broken || d <= 0) break;
                    T = l.k * d + 2.0 * l.zeta * sqrt(l.k * _p.J) * w;
                    if (T < 0) T = 0;
                    if (commit) {
                        if (l.contactT < 0) l.contactT = t;
                        if (T > l.breakNm) {
                            l.broken = true;
                            T = 0;
                        }
                    }
                    break;
                }
                case Load::HUNG:
                    if (xo <= l.x0) break;
                    T = l.massAt(t) * NM_PER_KG;
                    if (jHung) *jHung += l.massAt(t) * J_PER_KG;
                    if (commit && l.contactT < 0) l.contactT = t;
                    break;
            }
            if (commit) {
                l.lastNm = T;
                if (fabs(T) > l.peakNm) l.peakNm = fabs(T);
            }
            sum += T;
        }
        return sum;
    }

    bool supply(uint8_t reg, uint32_t &v) {
        if (reg == Tmc2209Uart::MSCNT) {
            v = mscnt();
            return true;
        }
        if (reg == Tmc2209Uart::DRVSTATUS) {
            // Keep any flags a test planted; the chip fills CS_ACTUAL and stst.
            v = (v & ~((31u << 16) | (1u << 31))) | ((uint32_t)_cs << 16) |
                (standstill() ? (1u << 31) : 0u);
            return true;
        }
        return false;
    }

    uint8_t _addr;
    Params _p;
    std::deque<Load> _loads;
    bool _energized = false;

    double _t = 0;
    int64_t _pendingUs = 0;
    double _xf = 0, _xr = 0, _xo = 0;   // microsteps
    double _w = 0;                      // rad/s at the motor
    double _jPrev;
    double _i = 0;                      // A RMS
    int _cs = 0;                        // current scale the driver is applying
    double _stillS = 1e9;               // s since VACTUAL went to 0: long ago
    double _rampS = 0;
    double _tm = 0, _tl = 0;            // N m, latest substep
    double _enc;                        // counts, filtered
    uint32_t _lcg;
};
