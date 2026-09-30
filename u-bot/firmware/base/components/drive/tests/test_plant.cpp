// Plant and rig validation. Before Phase 2 builds on the host rig, show that
// the plant under the real servo stack reproduces what is already known: the
// robot stays in sync where it does, today's 1 s leak detector trips when the
// analysis says it should, calibration finds the chip's clock, and pull-out
// comes where the motor's rating puts it.
#include <math.h>
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>

#include <initializer_list>

#include "Rig.h"

using P = StepperPlant;

static int failures = 0;

static void check(bool ok, const char *fmt, ...) {
    va_list ap;
    va_start(ap, fmt);
    printf("  %s ", ok ? "ok  " : "FAIL");
    vprintf(fmt, ap);
    printf("\n");
    va_end(ap);
    if (!ok) failures++;
}

static double runMa(const RigConfig &c) { return MotorCurrent::milliamps(MotorCurrent::scale(c.runMa)); }
static double sps(double tps) { return tps * P::MS_PER_OUT_TURN; }

// Today's detector against a clean full stall: the commanded integral runs on
// at v while the encoder stops, and the reference leaks toward it with tau, so
// the gap is v tau (1 - e^-t/tau). It trips when that reaches the limit -- or
// never, if v tau settles below it.
static double analyticTripS(double tps, double limit) {
    const double tau = 1.0;   // StepperServo::SLIP_TAU (private)
    double settles = sps(tps) * tau;
    return settles <= limit ? INFINITY : -tau * log(1.0 - limit / settles);
}

static void bringUp(Rig &rig) {
    if (!rig.setup() || !rig.enable()) {
        printf("FAIL: rig setup/enable\n");
        exit(1);
    }
}

// (a) Cruising in sync, nothing may trip: INL on both encoders, both chips
// 0.05% faster than the firmware believes, and rolling resistance at 30% of
// pull-out. The worst |slip| is INL plus load angle, far under the 200 limit.
static void inSync() {
    printf("(a) in sync: INL on, clock +0.05%%, 30%% friction, 10 s at each speed\n");
    for (double tps : {0.02, 0.05, 0.1, 0.2, 0.5, 1.0}) {
        RigConfig c;
        for (RigWheelConfig *w : {&c.a, &c.b}) w->presetGain = (float)(w->plant.gTrue / 1.0005);
        Rig rig(c);
        bringUp(rig);
        rig.addFriction(0.3 * P::pulloutNm(runMa(c)));
        double from[2] = {rig.a.plant.outputTurns(), rig.b.plant.outputTurns()};
        double ramp = tps / c.accelTps2;
        int32_t worstSlip[2] = {0, 0};
        double worstAngle = 0;
        bool faulted = false;
        rig.drive((float)tps, (float)-tps);
        rig.run(ramp + 10.0, [&](Rig &r) {
            for (int i = 0; i < 2; i++) {
                Rig::Wheel &w = *r.wheels[i];
                if (abs(w.servo.slipSteps()) > worstSlip[i]) worstSlip[i] = abs(w.servo.slipSteps());
                worstAngle = fmax(worstAngle, fabs(w.plant.loadAngleDeg()));
                faulted |= w.servo.fault() != StepperServo::FAULT_NONE;
            }
        });
        // Travel is a sanity check on the clock chain, loose because VACTUAL is
        // an integer: 0.02 turns/s is 147 LSB, so up to 0.3% off as commanded.
        // Whether anything slipped is the load angle's to say.
        double expect = tps * (ramp / 2 + 10.0) * 1.0005;
        double travelErr = 0;
        for (int i = 0; i < 2; i++) {
            double travel = rig.wheels[i]->plant.outputTurns() - from[i];
            travelErr = fmax(travelErr, fabs(travel / expect - 1.0));
        }
        check(!faulted && worstAngle < 90.0 && travelErr < 0.005,
              "%.2f turns/s: no fault, worst |slip| A %ld B %ld steps (trip 200), "
              "worst load angle %.0f deg, travel within %.3f%%",
              tps, (long)worstSlip[0], (long)worstSlip[1], worstAngle, travelErr * 100);
    }
}

// (b) Cruise into an unbreakable wall. Friction as in (a): the robot is on
// the ground, and without it the stalled rotor rings back several cycles on
// the robot's inertia, which a wheel in the grass does not.
static void wall() {
    printf("(b) unbreakable wall while cruising, 30%% friction, today's 1 s leak detector\n");
    for (int wi = 0; wi < 2; wi++) {
        for (double tps : {0.02, 0.05, 0.2}) {
            RigConfig c;
            Rig rig(c);
            bringUp(rig);
            rig.addFriction(0.3 * P::pulloutNm(runMa(c)));
            rig.drive((float)tps, (float)-tps);
            rig.run(tps / c.accelTps2 + 5.0);   // up to speed, and the leak has settled
            Rig::Wheel &w = *rig.wheels[wi];
            Rig::Wheel &other = *rig.wheels[1 - wi];
            P::Load &face = w.plant.addWall(w.plant.xo() + 50);
            double faultT = -1, rebound = 0;
            rig.run(12.0, [&](Rig &r) {
                if (face.contactT >= 0) rebound = fmax(rebound, face.x0 - w.plant.xo());
                if (w.servo.fault() == StepperServo::FAULT_SLIP) {
                    faultT = r.t();
                    return false;
                }
                return face.contactT < 0 || r.t() - face.contactT < 10.0;
            });
            double expect = analyticTripS(tps, w.servo.slipLimit);
            bool otherOk = other.servo.fault() == StepperServo::FAULT_NONE;
            if (face.contactT < 0) {
                check(false, "wheel %s %.2f turns/s: never reached the wall", w.name, tps);
            } else if (isinf(expect)) {
                check(faultT < 0 && otherOk,
                      "wheel %s %.2f turns/s: no FAULT_SLIP in 10 s against the wall "
                      "(analytic: never), rebound %.0f steps",
                      w.name, tps, rebound);
            } else {
                double dt = faultT - face.contactT;
                check(faultT >= 0 && fabs(dt / expect - 1.0) <= 0.15 && otherOk,
                      "wheel %s %.2f turns/s: FAULT_SLIP %.3f s after contact "
                      "(analytic %.3f, %+.1f%%), rebound %.0f steps",
                      w.name, tps, dt, expect, (dt / expect - 1.0) * 100, rebound);
            }
        }
    }
}

// (c) calibrate() on the rack finds the chip's clock over whole output turns,
// and the polarity: first with each wheel's shaft bit already right (B's is
// set), then with both wrong (A's set), which it has to notice and flip.
static void calibration() {
    const double gTrue = 1.0163;
    printf("(c) calibrate(3, 1500) on the rack, gTrue %.4f, INL and flicker on\n", gTrue);
    for (bool wrong : {false, true}) {
        RigConfig c;
        for (RigWheelConfig *w : {&c.a, &c.b}) {
            w->plant.J = P::J_RACK;
            w->plant.gTrue = gTrue;
            w->plant.flicker = true;
            if (wrong) w->invert = !w->invert;
        }
        Rig rig(c);
        bringUp(rig);
        for (Rig::Wheel *w : rig.wheels) {
            bool shaftBefore = w->gen.inverted();
            StepperServo::CalResult r = w->servo.calibrate(3, 1500.0f);
            bool right = w->gen.inverted() == (w->plant.params().encSign < 0);
            double err = r.clockGain / gTrue - 1.0;
            check(r.ok && r.flipped == wrong && right && fabs(err) <= 0.001 && abs(r.residual) < 16,
                  "wheel %s, shaft bit %d %s: gain %.5f (%+.3f%%), %sflipped, residual %ld counts, %s",
                  w->name, shaftBefore ? 1 : 0, wrong ? "(wrong)" : "(right)", r.clockGain, err * 100,
                  r.flipped ? "" : "not ", (long)r.residual, r.note);
        }
    }
}

// (d) The weight-lift fixture: robot clamped, a mass on a string from the
// tread, lifted at 0.03 turns/s while it grows until the motor lets go. At
// that speed pull-out is the static torque, Kt sqrt(2) I at 1160 mA.
static void pullout() {
    RigConfig c;
    for (RigWheelConfig *w : {&c.a, &c.b}) w->plant.J = P::J_RACK;
    double ideal = P::pulloutNm(runMa(c));
    printf("(d) weight-lift fixture at %.0f mA: mass ramped 0.1 kg/s at 0.03 turns/s\n", runMa(c));
    Rig rig(c);
    bringUp(rig);
    rig.drive(0.03f, 0.0f);
    rig.run(1.0);
    P::Load &mass = rig.a.plant.hangMass(0.0, 0.1);
    double slipT = -1, slipNm = 0, slipKg = 0, faultT = -1;
    rig.run(20.0, [&](Rig &r) {
        if (slipT < 0 && fabs(r.a.plant.loadAngleDeg()) > 180.0) {
            slipT = r.t();
            slipNm = mass.lastNm;
            slipKg = mass.massAt(r.t());
        }
        if (faultT < 0 && r.a.servo.fault() == StepperServo::FAULT_SLIP) faultT = r.t();
        return slipT < 0 || faultT < 0;
    });
    check(slipT >= 0 && fabs(slipNm / ideal - 1.0) <= 0.10,
          "slipped at %.3f N m, %.3f kg (ideal %.3f N m, %.2f kg; %+.1f%%)", slipNm, slipKg, ideal,
          ideal / P::NM_PER_KG, (slipNm / ideal - 1.0) * 100);
    check(faultT >= slipT && faultT - slipT < 1.0,
          "today's detector latched FAULT_SLIP %.0f ms after the slip, as the mass fell", (faultT - slipT) * 1000);
}

// (e) The driver model against the datasheet, as later phases lean on it:
// current timing at standstill, CS_ACTUAL and MSCNT through the real VelGen, a
// live IHOLD_IRUN write, and the backlash dead band on a reversal.
static void driverAndGear() {
    printf("(e) driver current timing, computed registers, live current, backlash\n");
    RigConfig c;
    c.a.plant.backlash = 24;
    Rig rig(c);
    bringUp(rig);
    const uint8_t irun = rig.a.gen.runCurrent(), ihold = rig.a.gen.holdCurrent();
    const uint8_t boost = 26;   // 1492 mA
    check(rig.a.plant.csActual() == ihold, "enabled at a standstill: CS %d = IHOLD", rig.a.plant.csActual());

    rig.drive(0.2f, 0.0f);
    rig.run(2.0);
    bool ok1, ok2;
    uint32_t mscnt = rig.a.gen.readReg(Tmc2209Uart::MSCNT, &ok1);
    uint32_t drv = rig.a.gen.readReg(Tmc2209Uart::DRVSTATUS, &ok2);
    check(ok1 && ok2 && mscnt == rig.a.plant.mscnt() && ((drv >> 16) & 31) == irun && !(drv >> 31) &&
              fabs(rig.a.plant.currentA() * 1000 - MotorCurrent::milliamps(irun)) < 1.0,
          "moving: MSCNT %lu from the field, CS_ACTUAL %lu = IRUN, stst 0, %.0f mA", (unsigned long)mscnt,
          (unsigned long)((drv >> 16) & 31), rig.a.plant.currentA() * 1000);

    // A live current change lands within a few phase time constants.
    uint32_t boosted = (uint32_t)ihold | ((uint32_t)boost << 8) | ((uint32_t)rig.a.gen.holdDelay() << 16);
    rig.uart.write(0, Tmc2209Uart::IHOLD_IRUN, boosted);
    rig.run(0.01);
    double boostMa = MotorCurrent::milliamps(boost);
    check(fabs(rig.a.plant.currentA() * 1000 - boostMa) < 0.01 * boostMa,
          "IRUN %d written while moving: %.0f mA after 10 ms", boost, rig.a.plant.currentA() * 1000);

    // Reversal on the flat: the output stands still while the rotor crosses
    // the dead band, then trails it on the other face.
    double before = rig.a.plant.xr() - rig.a.plant.xo();
    rig.drive(-0.2f, 0.0f);
    rig.run(3.0);
    double after = rig.a.plant.xr() - rig.a.plant.xo();
    check(fabs(before - 12) < 1e-6 && fabs(after + 12) < 1e-6,
          "reversal crosses the 24-step backlash: rotor-output %+.1f then %+.1f steps", before, after);

    // Stopping: IRUN for 2^20 + TPOWERDOWN * 2^18 clocks, then one CS per
    // IHOLDDELAY * 2^18 clocks down to IHOLD, all on the chip's own clock.
    rig.release();
    rig.run(3.0, [](Rig &r) { return r.a.chip().regs[Tmc2209Uart::VACTUAL] != 0; });
    double t0 = rig.t();
    double fclk = P::FCLK * rig.a.plant.params().gTrue;
    double tDown = (1048576.0 + 20 * 262144.0) / fclk;
    double tStep = rig.a.gen.holdDelay() * 262144.0 / fclk;
    double firstDrop = -1, atHold = -1;
    rig.run(5.0, [&](Rig &r) {
        int cs = r.a.plant.csActual();
        if (firstDrop < 0 && cs < boost) firstDrop = r.t() - t0;
        if (atHold < 0 && cs == ihold) atHold = r.t() - t0;
        return atHold < 0;
    });
    double expectHold = tDown + (boost - ihold) * tStep;
    check(fabs(firstDrop - (tDown + tStep)) < 0.006 && fabs(atHold - expectHold) < 0.006,
          "stopped: first step down at %.3f s (expect %.3f), IHOLD at %.3f s (expect %.3f)", firstDrop,
          tDown + tStep, atHold, expectHold);
}

// (f) The fakes, where the rig leans on them beyond test_velgen: a hook that
// waits does not re-enter, a counted injection disarms itself, every write is
// logged in order, and a failed encoder read holds position through the real
// AS5600 and StepperServo until the servo's retry.
static void fakes() {
    printf("(f) fakes: clock hook, counted injection, write log, encoder read failure\n");
    int calls = 0;
    FakeClock::setHook([&](int64_t, int64_t) {
        calls++;
        FakeClock::advance(7);
    });
    int64_t t0 = FakeClock::now();
    FakeClock::advance(10);
    check(calls == 1 && FakeClock::now() == t0 + 17, "a hook that waits moves the clock without re-entering");
    FakeClock::clearHook();

    RigConfig c;
    Rig rig(c);
    bringUp(rig);
    double counts0 = rig.a.plant.encoderCounts();   // where servo.begin() read its first angle
    FakeTmc::Node &chipA = rig.a.chip();
    chipA.dropReg = Tmc2209Uart::VACTUAL;
    chipA.dropTimes = 1;
    FakeTmc::clearLog();
    rig.drive(0.2f, -0.2f);
    rig.run(0.1);
    int seenA = 0, seenB = 0;
    bool firstDropped = false, restLanded = true, ordered = true;
    int64_t last = 0;
    for (const FakeTmc::Write &w : FakeTmc::log()) {
        ordered &= w.timeUs >= last;
        last = w.timeUs;
        if (w.reg != Tmc2209Uart::VACTUAL) continue;
        if (w.addr == 1) seenB++;
        if (w.addr != 0) continue;
        if (seenA++ == 0) firstDropped = !w.accepted;
        else restLanded &= w.accepted;
    }
    check(firstDropped && restLanded && chipA.dropReg < 0 && seenA > 1 && seenB > 1 && ordered,
          "one dropped VACTUAL, then %d landed; %d on B; log in time order", seenA - 1, seenB);

    rig.run(1.0);
    rig.a.i2c.failReads(1);
    rig.tick();
    bool heldOff = !rig.a.servo.encoderOk();
    int32_t heldAt = rig.a.servo.positionCounts();
    rig.run(0.05);
    bool stillHeld = rig.a.servo.positionCounts() == heldAt;
    rig.run(0.055);
    double behind = (rig.a.plant.encoderCounts() - counts0) - rig.a.servo.positionCounts();
    check(heldOff && stillHeld && rig.a.servo.encoderOk() && fabs(behind) < 2 &&
              rig.a.servo.fault() == StepperServo::FAULT_NONE,
          "failed read: position held, back after the 100 ms retry and caught up (%.1f counts), no fault",
          behind);
}

int main() {
    setvbuf(stdout, nullptr, _IOLBF, 0);   // keep every line if a sanitizer aborts mid-run
    inSync();
    wall();
    calibration();
    pullout();
    driverAndGear();
    fakes();
    if (failures) {
        printf("FAIL: %d plant check%s\n", failures, failures == 1 ? "" : "s");
        return 1;
    }
    puts("PASS: plant in sync 0.02-1.0 turns/s, wall trips match the 1 s leak, calibration within 0.1%, "
         "pull-out at rated torque, driver current timing, live current, backlash, fakes");
}
