#pragma once
#include <assert.h>

#include <functional>
#include <type_traits>

#include "AS5600.h"
#include "StepperPlant.h"
#include "StepperServo.h"
#include "VelGen.h"
#include "fake_clock.h"
#include "fake_i2c.h"
#include "fake_tmc.h"
#include "platform.h"

// The robot's drive on the host: two StepperPlants under the real VelGen,
// AS5600 and StepperServo, on one shared fake UART (addresses 0 and 1) and two
// fake I2C buses, ticked in drive.cpp's order. The clock hook steps both plants
// whenever anything waits, so blocking firmware (begin()'s delays, calibrate()'s
// pumps) moves the wheels the way the robot's control task sleeping does.
//
// Sign convention: tpsA/tpsB are servo turns/s, encoder counts up, exactly what
// drive.cpp hands setVelocityTps(). With the robot's polarity (inv_a 0,
// inv_b 1, sign_a +1, sign_b -1) robot-forward is drive(+v, -v), and that is
// motor + on both plants, so a positive load resists robot-forward on both.
//
// The fakes and the clock are global, so only one Rig may exist at a time.

struct RigWheelConfig {
    bool invert;                  // GCONF.shaft, as drive.cpp loads inv_a / inv_b
    float presetGain;             // the clock gain the firmware believes (gain_a / gain_b)
    StepperPlant::Params plant;   // the physical truth, including gTrue
};

// Defaults are the robot as it was read on 2026-09-30.
struct RigConfig {
    int runMa = 1200, holdMa = 600, iholdDelay = 8;   // programs 1160/552 mA
    bool spreadCycle = true;
    float spreadAboveSps = 0;
    float vmaxTps = 1.0f, accelTps2 = 0.2f, decelTps2 = 2.0f;
    uint16_t microsteps = 8;
    RigWheelConfig a = wheel(false, 1.01616f, +1, 1000.0, 0.9, 2.4);
    RigWheelConfig b = wheel(true, 1.00971f, -1, 3000.0, 4.0, 0.7);

    // A wheel whose chip runs exactly as fast as its stored gain says, with its
    // encoder counting the way its shaft bit expects and INL at its defaults.
    static RigWheelConfig wheel(bool invert, float gain, int encSign, double encOffset,
                                double phi1, double phi2) {
        RigWheelConfig w = {invert, gain, StepperPlant::Params()};
        w.plant.gTrue = gain;
        w.plant.encSign = encSign;
        w.plant.encOffset = encOffset;
        w.plant.inlPhi1 = phi1;
        w.plant.inlPhi2 = phi2;
        w.plant.seed = (uint32_t)encOffset + 1;
        return w;
    }
};

class Rig {
  public:
    using Config = RigConfig;
    static constexpr float DT = 0.005f;          // s, one control tick at 200 Hz
    static constexpr int64_t TICK_US = 5000;     // 50 plant substeps

    // One axis, built the way drive.cpp's Wheel is: a driver on the shared bus,
    // the encoder on its own bus, the servo between them -- plus the physics.
    struct Wheel {
        const char *name;
        StepperPlant plant;
        FakeI2c i2c;
        AS5600 enc;
        VelGen gen;
        StepperServo servo;

        Wheel(const char *n, Tmc2209Uart &uart, uint8_t addr, const StepperPlant::Params &p)
            : name(n), plant(addr, p), enc(i2c), gen(uart, addr), servo(enc, gen) {
            i2c.angleFn = [this] { return plant.encoderAngle(); };
        }
        Wheel(const Wheel &) = delete;
        Wheel &operator=(const Wheel &) = delete;

        FakeTmc::Node &chip() { return FakeTmc::node(gen.address()); }
    };

    Config cfg;
    Tmc2209Uart uart;
    Wheel a, b;
    Wheel *const wheels[2];

    bool driversOn = false;   // the shared EN pin is low
    bool cmdActive = false;   // a live drive command, as drive.cpp's S.cmdActive
    uint32_t ticks = 0;

    // --- extension points, in drive.cpp's tick order ---
    //
    // Phase 2 hangs its pieces here rather than editing tick(). Each runs once
    // per tick with the rig; empty ones are skipped.
    std::function<void(Rig &)> onDeadman;    // before servo.update(): deadman, cancelRecovery()
    std::function<void(Rig &)> onDetect;     // after both servo.update(): stall detectors
    std::function<void(Rig &)> onRecovery;   // recoveryTick()
    std::function<void(Rig &)> onFaults;     // checkFaults() / latchFault() mirror
    std::function<void(Rig &)> onTorque;     // torqueUpdate(): thermal model + BoostPolicy
    std::function<void(Rig &)> onUartSlot;   // uartSlot(): live current writes, polls

    explicit Rig(const Config &c = Config())
        : cfg(c), uart(1, 1, 2), a("A", uart, 0, c.a.plant), b("B", uart, 1, c.b.plant), wheels{&a, &b} {
        assert(live_ == 0 && "one Rig at a time: the fakes and the clock are global");
        live_++;
        FakeClock::setHook([this](int64_t from, int64_t to) {
            for (Wheel *w : wheels) w->plant.advance(to - from);
        });
    }
    ~Rig() {
        FakeClock::clearHook();
        live_--;
    }
    Rig(const Rig &) = delete;
    Rig &operator=(const Rig &) = delete;

    // drive_init(): stage the settings as loadSettings() does, bring up both
    // drivers from a power-on reset, then the encoders and servos. EN stays high
    // (and is parked there first, so calling this again re-inits from scratch).
    bool setup() {
        disable();
        for (Wheel *w : wheels) {
            FakeTmc::resetChip(w->gen.address());
            w->servo.vmaxTps = cfg.vmaxTps;
            w->servo.accelTps2 = cfg.accelTps2;
            w->servo.decelTps2 = cfg.decelTps2;
            w->gen.setCurrentMa(cfg.runMa, cfg.holdMa, cfg.iholdDelay);
            w->gen.setSpreadCycle(cfg.spreadCycle);
            w->gen.setSpreadAboveRate(cfg.spreadAboveSps);
        }
        a.gen.setInvert(cfg.a.invert);
        b.gen.setInvert(cfg.b.invert);
        a.gen.presetClockGain(cfg.a.presetGain);
        b.gen.presetClockGain(cfg.b.presetGain);
        setEn(false);   // the chip reset put IOIN's ENN back high; keep the plants in step
        bool ok = true;
        for (Wheel *w : wheels) ok = w->gen.begin(cfg.microsteps) && ok;
        for (Wheel *w : wheels) {
            ok = w->enc.begin() && ok;
            w->servo.stepsPerCount = (float)(200.0 * cfg.microsteps * StepperPlant::GEAR / 4096.0);
            w->servo.begin();
        }
        return ok;
    }

    // enableDrivers(true): zero both VACTUALs, then drop EN, give the drivers
    // their 20 ms out of standby, then resync both slip references.
    bool enable() {
        for (Wheel *w : wheels) w->gen.setEnabled(true);
        for (Wheel *w : wheels) {
            if (!w->gen.enabled() || !w->gen.ok()) {
                disable();
                return false;
            }
        }
        setEn(true);
        driversOn = true;
        delayMs(20);
        for (Wheel *w : wheels) w->servo.resyncSlip();
        return true;
    }

    // enableDrivers(false): EN high first, then tidy up. The wheels freewheel.
    void disable() {
        setEn(false);
        for (Wheel *w : wheels) w->servo.enableDriver(false);
        driversOn = false;
        cmdActive = false;
    }

    // A live stick: setWheelVelocity() on both wheels, as applyRobotVelocity()
    // does for a fresh drive command.
    void drive(float tpsA, float tpsB) {
        cmdActive = true;
        setWheelVelocity(a, tpsA);
        setWheelVelocity(b, tpsB);
    }

    // The stick let go (or the deadman lapsed): both wheels ramp to zero.
    void release() {
        cmdActive = false;
        setWheelVelocity(a, 0);
        setWheelVelocity(b, 0);
    }

    // One control tick: 5 ms of physics (50 plant substeps), then drive.cpp's
    // order. A different `us` is a late or early tick -- jitter -- and the
    // servos see it as their dt, as drive.cpp measures it.
    void tick(int64_t us = TICK_US) {
        FakeClock::advance(us);
        if (onDeadman) onDeadman(*this);
        for (Wheel *w : wheels) w->servo.update(us == TICK_US ? DT : (float)us * 1e-6f);
        if (onDetect) onDetect(*this);
        if (onRecovery) onRecovery(*this);
        if (onFaults) onFaults(*this);
        if (onTorque) onTorque(*this);
        if (onUartSlot) onUartSlot(*this);
        ticks++;
    }

    // Tick for `seconds`, calling perTick(rig) after each tick. A callback that
    // returns bool stops the run by returning false. Returns seconds ticked.
    template <typename F>
    double run(double seconds, F &&perTick) {
        long n = lround(seconds / DT);
        for (long i = 0; i < n; i++) {
            tick();
            if constexpr (std::is_same_v<std::invoke_result_t<F &, Rig &>, bool>) {
                if (!perTick(*this)) return (double)(i + 1) * DT;
            } else {
                perTick(*this);
            }
        }
        return (double)n * DT;
    }
    double run(double seconds) {
        return run(seconds, [](Rig &) {});
    }

    double t() const { return a.plant.t(); }   // s of physics since the rig was built

    // --- loads on both wheels (per wheel: rig.a.plant.add*()) ---

    void addGrade(double deg) {
        for (Wheel *w : wheels) w->plant.addGrade(deg);
    }
    void addFriction(double nm, double w0 = 0.05) {
        for (Wheel *w : wheels) w->plant.addFriction(nm, w0);
    }
    void addConst(double nm) {
        for (Wheel *w : wheels) w->plant.addConst(nm);
    }

    // The shared EN pin: both power stages, and IOIN's ENN bit on both chips so
    // VelGen::begin() sees an energised driver the way it would on the robot.
    void setEn(bool energised) {
        for (Wheel *w : wheels) {
            uint32_t &ioin = w->chip().regs[Tmc2209Uart::IOIN];
            ioin = energised ? (ioin & ~1u) : (ioin | 1u);
            w->plant.setEnergized(energised);
        }
    }

  private:
    // drive.cpp's setWheelVelocity().
    static void setWheelVelocity(Wheel &w, float tps) {
        if (!w.gen.enabled()) return;
        if (w.servo.fault() != StepperServo::FAULT_NONE) return;
        if (!w.servo.servoOn()) w.servo.servoOn(true);
        w.servo.setVelocityTps(tps);
    }

    static inline int live_ = 0;
};
