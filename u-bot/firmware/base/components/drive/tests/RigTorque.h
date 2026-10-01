#pragma once
// drive.cpp's torque path for the host rig: torqueUpdate(), uartSlot(),
// pollDriver() and checkFaults(), line for line where it matters -- the thermal
// step on real elapsed time with CS_ACTUAL folded in, the policy inputs, what
// counts as a pending write and which way it goes, a stall recovery's urgent
// raise, the soft/hard split of DRV_STATUS, and the enable/disable resets. It
// hangs itself on the rig's onTorque and onUartSlot hooks.
//
// Used by test_torque (the live current path) and test_recovery_rig (the same
// path under a stall recovery's boost).
#include <math.h>
#include <stdint.h>

#include "BoostPolicy.h"
#include "Rig.h"
#include "ThermalModel.h"
#include "UartSlot.h"

struct Torque {
    using BP = BoostPolicy;

    struct W {
        ThermalModel thermal;
        BP boost;
        OtpwDerate derate;
        BP::Output out;
        bool pending = false;
        uint32_t lastMovingMs = 0, lastWriteMs = 0, sampleMs = 0;
        bool haveSample = false;
        uint32_t drv = 0, gstat = 0;
        uint8_t csActual = 0;
        bool otpw = false;
        uint32_t csMismatch = 0;
    };

    Rig &rig;
    W w[2];
    UartSlot slot;
    int64_t heatUs = 0;
    bool supplyInhibit = false;
    uint8_t healthIdx = 0;
    uint32_t liveWrites = 0, liveFailures = 0, urgentWrites = 0;
    // Which wheel this tick's stall recovery is snapping, as drive.cpp reads
    // it from the RecoveryOut: that wheel's raise goes first. The recovery
    // glue sets it; without one it stays false and nothing is urgent.
    bool snapping[2] = {false, false};

    int boostMa;
    uint32_t startMs;
    float tauS, lim;

    // drive_init(): the settings loadSettings() reads, then the hooks.
    Torque(Rig &r, int boostMa_ = MotorCurrent::BOOST_MAX_MA, uint32_t startMs_ = 1500, float tauS_ = 600,
           float lim_ = 1.10f)
        : rig(r), boostMa(boostMa_), startMs(startMs_), tauS(tauS_), lim(lim_) {
        configure();
        for (W &t : w) t.thermal.reset(ThermalModel::BOOT_H);
        heatUs = FakeClock::now();
        slot.reset(millis());
        rig.onTorque = [this](Rig &) { torqueUpdate(); };
        rig.onUartSlot = [this](Rig &) { uartSlot(); };
    }

    // configureTorque(): the policies follow the base pair the drivers are
    // staged with, which Rig::setup() sets, so this runs again at enable.
    void configure() {
        BP::Config bc;
        bc.boostCs = boostMa ? MotorCurrent::scale(boostMa) : 0;
        bc.startMs = startMs;
        ThermalModel::Params tp;
        tp.ratedMa = MotorCurrent::RATED_MA;
        tp.tauHeatS = tauS;
        tp.limit = lim;
        for (int i = 0; i < 2; i++) {
            bc.baseRun = rig.wheels[i]->gen.runCurrent();
            bc.baseHold = rig.wheels[i]->gen.holdCurrent();
            w[i].boost.configure(bc);
            w[i].thermal.configure(tp);
        }
    }
    ~Torque() {
        rig.onTorque = nullptr;
        rig.onUartSlot = nullptr;
    }

    // drive_enable(true): begin() both, poll both, EN low, then the resets
    // enableDrivers(true) does.
    bool enable() {
        configure();
        rig.setEn(false);
        for (Rig::Wheel *wh : rig.wheels) {
            if (!wh->gen.begin(rig.cfg.microsteps)) return false;
        }
        for (int i = 0; i < 2; i++) pollDriver(i);
        if (!rig.enable()) return false;
        const uint32_t now = millis();
        for (int i = 0; i < 2; i++) {
            w[i].boost.reset(now - BP::START_STILL_MS);
            const uint8_t level = w[i].derate.level();
            w[i].derate.reset(rig.wheels[i]->gen.hot() && level < 2 ? 2 : level);
            w[i].lastMovingMs = now;
            w[i].pending = false;
        }
        return true;
    }

    // enableDrivers(false).
    void disable() {
        rig.disable();
        for (W &t : w) {
            t.boost.reset(millis());
            t.pending = false;
        }
    }

    // drive_boost_manual(), and a drive command's flag.
    void manual(uint32_t ms) {
        for (W &t : w) t.boost.request(BP::MANUAL, millis(), ms);
    }

    static uint32_t standstillMs(const VelGen &g) {
        const float clocks = 1048576.0f + VelGen::TPOWERDOWN * 262144.0f;
        return (uint32_t)(clocks / (VelGen::FCLK * g.clockGain()) * 1000.0f * 1.1f);
    }
    static uint32_t reductionStepMs(const VelGen &g) {
        return (uint32_t)(g.holdDelay() * 262144.0f / VelGen::FCLK * 1000.0f * 1.1f);
    }

    float motorMa(int i, uint32_t now) {
        VelGen &g = rig.wheels[i]->gen;
        W &t = w[i];
        const bool energised = rig.driversOn && g.enabled();
        const bool moving = g.rate() != 0;
        if (moving) t.lastMovingMs = now;
        float ma = ThermalModel::inferMa(energised, moving, moving ? 0 : now - t.lastMovingMs, g.liveRun(),
                                         g.liveHold(), standstillMs(g), reductionStepMs(g));
        if (energised && t.haveSample && now - t.sampleMs < 600) ma = fmaxf(ma, MotorCurrent::milliamps(t.csActual));
        return ma;
    }

    void thermalStep() {
        const int64_t nowUs = FakeClock::now();
        const float dtS = (float)(nowUs - heatUs) * 1e-6f;
        heatUs = nowUs;
        const uint32_t now = millis();
        for (int i = 0; i < 2; i++) w[i].thermal.accumulate(dtS, motorMa(i, now));
    }

    void torqueUpdate() {
        thermalStep();
        const uint32_t now = millis();
        for (int i = 0; i < 2; i++) {
            VelGen &g = rig.wheels[i]->gen;
            W &t = w[i];
            BP::Inputs in;
            in.nowMs = now;
            in.energised = rig.driversOn && g.enabled();
            in.moving = g.rate() != 0;
            in.heatLimited = t.thermal.limited();
            in.supplyInhibit = supplyInhibit;
            in.derate = t.derate.level();
            t.out = t.boost.update(in);
            t.pending = in.energised && g.ok() && (t.out.run != g.liveRun() || t.out.hold != g.liveHold());
        }
    }

    void pollDriver(int i) {
        Rig::Wheel &wh = *rig.wheels[i];
        W &t = w[i];
        auto dr = rig.uart.read(wh.gen.address(), Tmc2209Uart::DRVSTATUS, 3);
        auto gs = dr.st == Tmc2209Uart::OK ? rig.uart.read(wh.gen.address(), Tmc2209Uart::GSTAT, 3) : dr;
        const bool ok = dr.st == Tmc2209Uart::OK && gs.st == Tmc2209Uart::OK;
        const uint32_t now = millis();
        if (ok) {
            t.drv = dr.value;
            t.gstat = gs.value;
            t.sampleMs = now;
            t.haveSample = true;
            t.csActual = (uint8_t)((dr.value >> 16) & 31);
            t.otpw = (t.drv & VelGen::DRV_SOFT) != 0;
            t.derate.sample(t.otpw, now);
            const bool stealth = t.drv & (1UL << 30), stst = t.drv & (1UL << 31);
            if (rig.driversOn && wh.gen.enabled() && !stealth && !stst && wh.gen.rate() != 0 &&
                now - t.lastWriteMs > 20 && t.csActual != wh.gen.liveRun())
                t.csMismatch++;
        }
        if (!ok || (t.gstat & 7) || (t.drv & VelGen::DRV_HARD)) {
            wh.gen.invalidate();
            if (rig.driversOn) {
                wh.servo.raiseFault(StepperServo::FAULT_DRIVER);
                disable();
            }
        }
    }

    void healthStep() {
        const int i = healthIdx / 2;
        if (healthIdx & 1) pollDriver(i);
        else rig.wheels[i]->enc.readStatus();   // the encoder half: nothing torque needs from it
        healthIdx = (healthIdx + 1) % 4;
    }

    void checkFaults() {
        for (Rig::Wheel *wh : rig.wheels) {
            if (rig.driversOn && !wh->gen.ok()) {
                wh->servo.raiseFault(StepperServo::FAULT_DRIVER);
                disable();
            }
        }
    }

    void uartSlot() {
        const uint32_t now = millis();
        UartSlot::Request rq;
        for (int i = 0; i < 2; i++) {
            const VelGen &g = rig.wheels[i]->gen;
            rq.live[i] = w[i].pending;
            rq.raise[i] = w[i].out.run > g.liveRun() || w[i].out.hold > g.liveHold();
            if (w[i].out.reasons & BP::RECOVERY)
                rq.urgent[i] = snapping[i] ? UartSlot::URGENT_SNAP : UartSlot::URGENT_PARTNER;
        }
        const UartSlot::Choice c = slot.next(now, 0, rq);
        if (c.group == UartSlot::LIVE) {
            W &t = w[c.wheel];
            t.lastWriteMs = now;
            urgentWrites += rq.raise[c.wheel] && rq.urgent[c.wheel];
            if (rig.wheels[c.wheel]->gen.setLiveCurrent(t.out.run, t.out.hold)) liveWrites++;
            else liveFailures++;
        } else if (c.group == UartSlot::HEALTH) {
            healthStep();
        } else {
            return;
        }
        checkFaults();
    }
};
