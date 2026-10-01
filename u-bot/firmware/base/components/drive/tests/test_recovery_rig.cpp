// Stall detection and recovery on the host rig: two plants under the real
// VelGen, AS5600 and StepperServo (holds included), the real StallDetector and
// Recovery through recoveryTick(), and the real BoostPolicy, ThermalModel and
// live-current path through UartSlot, ticked in drive.cpp's order:
//
//   onDeadman    the deadman, cancelRecovery()
//   update() x2
//   onRecovery   recoveryStep(): recoveryTick() with the boost hook
//   onFaults     checkFaults() / latchFault(): FAULT_PEER and the cancel; demo.update()
//   onTorque     torqueUpdate()
//   onUartSlot   uartSlot(), urgent raises included
//
// Drive below is drive.cpp's stall glue, line for line where it matters;
// RigTorque.h is its torque glue. Every scenario on the ground carries rolling
// friction: without it a stalled rotor rings back on the robot's inertia and
// distorts the trip timing, which a wheel in the grass does not.
#include <math.h>
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include <initializer_list>
#include <vector>

#include "Demo.h"
#include "Recovery.h"
#include "Rig.h"
#include "RigTorque.h"

using P = StepperPlant;
using BP = BoostPolicy;
typedef RecoveryWheelOut H;

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

static double baseMa(const RigConfig &c) { return MotorCurrent::milliamps(MotorCurrent::scale(c.runMa)); }
static double basePullout(const RigConfig &c) { return P::pulloutNm(baseMa(c)); }
static const double BOOST_PULLOUT = P::pulloutNm(MotorCurrent::milliamps(31));
static double friction(const RigConfig &c) { return 0.3 * basePullout(c); }   // 30% of base pull-out, as test_plant

// drive.cpp's stall settings, at their defaults.
struct Settings {
    bool recover = true;
    int tries = 3, lockMs = 200;
    float prog = 0.25f;
    float lagTrip = 40, lagLeak = 400, lagRev = 48;
};

// drive.cpp's stall glue: configureRecovery(), recoveryStep(), cancelRecovery(),
// the deadman branch, and the part of checkFaults()/latchFault() that matters
// here -- the encoder timer, the latch, the peer stopped, the commands
// cancelled. eligible is drive.cpp's (no calibration runs on the rig).
struct Drive {
    struct Event {
        uint32_t tick;
        double t;              // plant s
        int64_t us;            // FakeClock, as the write log stamps it
        RecoveryEvent e;
        uint8_t wheel, attempt, attemptBefore;
        float k;
        size_t logAt;          // FakeTmc log size when it happened, before this tick's slot
    };

    Rig &rig;
    Settings set;
    Torque tq;
    StallDetector det[2];
    StallSample st[2] = {};
    Recovery rec;
    StepperServo *servos[2];
    RecoveryOut out = {};
    bool faultLatched = false;
    int faultWheel = -1;
    uint32_t faultTick = 0;
    Demo demo;
    int64_t cmdExpiresUs = 0;      // the deadman, 0 = held until released
    uint32_t encDownSince[2] = {0, 0};
    std::vector<Event> events;
    float worstLag = 0;            // max |lag| while armed, both wheels, since resetStats()
    uint32_t armedTicks = 0;

    Drive(Rig &r, const Settings &s = Settings(), bool stallGlue = true)
        : rig(r), set(s), tq(r), servos{&r.a.servo, &r.b.servo} {
        configure(s);
        rig.onDeadman = [this](Rig &) { deadman(); };
        if (stallGlue) rig.onRecovery = [this](Rig &) { recoveryStep(); };
        rig.onFaults = [this](Rig &) {
            checkFaults();
            demo.update();
        };
    }
    ~Drive() {
        rig.onDeadman = nullptr;
        rig.onRecovery = nullptr;
        rig.onFaults = nullptr;
    }

    // configureRecovery().
    void configure(const Settings &s) {
        StallConfig sc;
        sc.tripSteps = s.lagTrip;
        sc.leakSteps = s.lagLeak;
        sc.settleSteps = s.lagRev;
        for (StallDetector &d : det) d.configure(sc);
        RecoveryConfig rc;
        rc.enabled = s.recover;
        rc.tries = (uint8_t)s.tries;
        rc.lockMs = (uint16_t)s.lockMs;
        rc.stepsPerCount = rig.a.servo.stepsPerCount;
        rc.progressSteps = s.prog * StepperServo::COUNTS_PER_REV * rc.stepsPerCount;
        rc.lockLagSteps = s.lagTrip;
        rec.configure(rc);
        for (StepperServo *v : servos) v->releaseHold();
    }

    // drive_init() + drive_enable(true). Rig::setup() set stepsPerCount, so
    // the progress conversion is configured again, as drive_init() does.
    bool bringUp() {
        if (!rig.setup() || !tq.enable()) return false;
        configure(set);
        return true;
    }

    // A live stick, held (renewed) until released, or for holdMs.
    void drive(float tpsA, float tpsB, uint32_t holdMs = 0) {
        rig.drive(tpsA, tpsB);
        cmdExpiresUs = holdMs ? FakeClock::now() + (int64_t)holdMs * 1000 : 0;
    }
    // A zero frame from the stick: drive_set_velocity_ex(0, 0).
    void release() { rig.release(); }

    void cancelRecovery() {
        rec.cancel();
        for (StepperServo *v : servos) v->releaseHold();
    }
    // cancelCommands(), the parts that matter here.
    void cancelCommands() {
        rig.cmdActive = false;
        for (Torque::W &w : tq.w) w.boost.cancel(BP::MANUAL);
        cancelRecovery();
    }

    void deadman() {
        if (rig.cmdActive && cmdExpiresUs && FakeClock::now() > cmdExpiresUs) {
            rig.release();
            cancelRecovery();
        }
    }

    void recoveryStep() {
        const uint32_t now = millis();
        const bool eligible = rig.driversOn && !faultLatched && !demo.running();
        const uint8_t before = rec.attempt();
        out = recoveryTick(rec, det, st, servos, rig.cmdActive, eligible, now, rig.dt,
                           [&](uint8_t i, uint32_t ms) { tq.w[i].boost.request(BP::RECOVERY, now, ms); });
        for (int i = 0; i < 2; i++) {
            tq.snapping[i] = out.w[i].hold == H::HOLD_SNAP;
            if (st[i].armed) {
                armedTicks++;
                worstLag = fmaxf(worstLag, fabsf(st[i].lag));
            }
        }
        if (out.event != REV_NONE)
            events.push_back({rig.ticks, rig.t(), FakeClock::now(), out.event, out.wheel, rec.attempt(), before,
                              out.k, FakeTmc::log().size()});
    }

    void checkFaults() {
        for (int i = 0; i < 2; i++) {
            StepperServo &v = rig.wheels[i]->servo;
            if (rig.driversOn && v.servoOn() && !v.encoderOk()) {
                if (!encDownSince[i]) encDownSince[i] = millis() | 1;
                else if (millis() - encDownSince[i] > 250) v.raiseFault(StepperServo::FAULT_ENCODER);
            } else {
                encDownSince[i] = 0;
            }
        }
        if (faultLatched) return;
        for (int i = 0; i < 2; i++) {
            const uint8_t f = rig.wheels[i]->servo.fault();
            if (f == StepperServo::FAULT_NONE || f == StepperServo::FAULT_PEER) continue;
            faultLatched = true;
            faultWheel = i;
            faultTick = rig.ticks;
            StepperServo &o = rig.wheels[1 - i]->servo;
            if (o.servoOn()) o.raiseFault(StepperServo::FAULT_PEER);
            else o.spin(0);
            cancelCommands();
            return;
        }
    }

    // --- for the tests ---

    int count(RecoveryEvent e) const {
        int n = 0;
        for (const Event &v : events) n += v.e == e;
        return n;
    }
    const Event *first(RecoveryEvent e) const {
        for (const Event &v : events)
            if (v.e == e) return &v;
        return nullptr;
    }
    void resetStats() {
        worstLag = 0;
        armedTicks = 0;
    }
    uint8_t fault(int i) const { return rig.wheels[i]->servo.fault(); }
    int32_t vactual(int i) {
        int32_t v = (int32_t)(rig.wheels[i]->chip().regs[Tmc2209Uart::VACTUAL] & 0xFFFFFF);
        return (v & 0x800000) ? v - 0x1000000 : v;
    }
    // Tick until pred(rig) or seconds; returns whether pred came true.
    template <typename F>
    bool until(double seconds, F &&pred) {
        long n = lround(seconds / Rig::DT);
        for (long k = 0; k < n; k++) {
            rig.tick();
            if (pred(rig)) return true;
        }
        return false;
    }
};

// A late control tick now and then, as the ticker sees them: the period stays
// 5 ms and each tick lands up to 3 ms after its slot, so dt is 5 ms plus this
// tick's lateness less the last one's.
struct Jitter {
    uint32_t seed;
    int64_t late = 0;
    explicit Jitter(uint32_t s) : seed(s) {}
    int64_t next() {
        seed = seed * 1664525u + 1013904223u;
        const int64_t now = ((seed >> 8) % 10 == 0) ? (int64_t)((seed >> 12) % 3000) : 0;
        const int64_t us = Rig::TICK_US + now - late;
        late = now;
        return us;
    }
};

// Up to speed and past the START boost and its ramp back down (1.5 s, then
// 2.2 s), so a scenario's load meets the base current.
static void cruise(Drive &d, float tps, double extra = 4.0) {
    d.drive(tps, -tps);
    d.rig.run(tps / d.rig.cfg.accelTps2 + extra);
}

// --- (a) in sync: no trips ----------------------------------------------------

// Cruise with INL on both encoders, both chips 0.3% off what the firmware
// believes, 30% rolling friction and late ticks: start, ramp, cruise long
// enough for a whole output turn (or 10 s), stop. Then +/-0.2 turns/s square
// waves through 0, 8 and 24 counts of backlash.
static void inSync() {
    printf("(a) in sync: INL, clock +/-0.3%%, 30%% friction, late ticks, ramps; worst |lag| must stay <= 24\n");
    float worstAll = 0;
    for (double tps : {0.02, 0.05, 0.1, 0.2, 0.5, 1.0, 1.5}) {
        for (double eps : {+0.003, -0.003}) {
            RigConfig c;
            c.vmaxTps = (float)fmax(1.0, tps);
            for (RigWheelConfig *w : {&c.a, &c.b}) w->presetGain = (float)(w->plant.gTrue / (1.0 + eps));
            Rig rig(c);
            Drive d(rig);
            if (!d.bringUp()) {
                check(false, "rig bring-up");
                return;
            }
            rig.addFriction(friction(c));
            Jitter j((uint32_t)(tps * 1000) + (eps > 0 ? 7 : 3));
            d.drive((float)tps, (float)-tps);
            const double cruiseS = fmin(55.0, fmax(10.0, 1.1 / tps));
            const long n = lround((tps / c.accelTps2 + cruiseS) / Rig::DT);
            for (long k = 0; k < n; k++) rig.tick(j.next());
            d.release();
            for (long k = 0; k < 400; k++) rig.tick(j.next());   // 2 s: stopped at 2 turns/s^2
            const uint32_t trips = d.det[0].trips() + d.det[1].trips();
            const bool quiet = !trips && d.events.empty() && !d.faultLatched && !d.fault(0) && !d.fault(1);
            worstAll = fmaxf(worstAll, d.worstLag);
            check(quiet && d.worstLag <= 24 && d.armedTicks > 0,
                  "%.2f turns/s, chip %+.1f%% off its stored gain: %.0f s cruise, worst |lag| %.1f steps, %u trips, "
                  "%d events%s", tps, eps * 100, cruiseS, d.worstLag, (unsigned)trips, (int)d.events.size(),
                  d.faultLatched ? ", FAULTED" : "");
        }
    }
    for (double backlashCounts : {0.0, 8.0, 24.0}) {
        RigConfig c;
        for (RigWheelConfig *w : {&c.a, &c.b}) {
            w->plant.backlash = backlashCounts * P::MS_PER_COUNT;
            w->presetGain = (float)(w->plant.gTrue / 1.003);
        }
        Rig rig(c);
        Drive d(rig);
        if (!d.bringUp()) {
            check(false, "rig bring-up");
            return;
        }
        rig.addFriction(friction(c));
        Jitter j((uint32_t)backlashCounts + 11);
        for (int half = 0; half < 12; half++) {   // 6 periods of 4 s
            const float v = (half & 1) ? -0.2f : 0.2f;
            d.drive(v, -v);
            for (int k = 0; k < 400; k++) rig.tick(j.next());
        }
        d.release();
        for (int k = 0; k < 400; k++) rig.tick(j.next());
        const uint32_t trips = d.det[0].trips() + d.det[1].trips();
        worstAll = fmaxf(worstAll, d.worstLag);
        check(!trips && d.events.empty() && !d.faultLatched && d.worstLag <= 24,
              "+/-0.2 turns/s square wave, 4 s period, %2.0f counts of backlash (%.1f steps): worst |lag| %.1f, "
              "%u trips", backlashCounts, backlashCounts * P::MS_PER_COUNT, d.worstLag, (unsigned)trips);
    }
    printf("  worst |lag| over every in-sync run: %.1f steps (trip at 40)\n", worstAll);
}

// --- (b), (g): a full stall faults, recover 0 ---------------------------------

struct StallResult {
    bool reached = false, faulted = false, peer = false, sameTick = false, vzero = false;
    double travel = 0, ms = 0;
};

// Cruise into an unbreakable wall on one wheel with recover 0. Commanded
// travel and time are measured from contact (interpolated inside the tick) to
// the tick that latched the fault.
static StallResult wallNoRecover(int wi, double tps) {
    RigConfig c;
    Rig rig(c);
    Settings s;
    s.recover = false;
    Drive d(rig, s);
    StallResult r;
    if (!d.bringUp()) return r;
    rig.addFriction(friction(c));
    cruise(d, (float)tps, 3.0);
    Rig::Wheel &w = *rig.wheels[wi];
    P::Load &face = w.plant.addWall(w.plant.xo() + 50);
    double prevT = rig.t(), prevCmd = w.servo.commandedSteps(), atContact = NAN;
    d.until(8.0, [&](Rig &g) {
        const double t = g.t(), cmd = w.servo.commandedSteps();
        if (face.contactT >= 0 && isnan(atContact))
            atContact = prevCmd + (cmd - prevCmd) * (face.contactT - prevT) / (t - prevT);
        prevT = t;
        prevCmd = cmd;
        return d.faultLatched;
    });
    r.reached = face.contactT >= 0;
    if (!r.reached || !d.faultLatched) return r;
    r.faulted = d.faultWheel == wi && d.fault(wi) == StepperServo::FAULT_SLIP;
    r.peer = d.fault(1 - wi) == StepperServo::FAULT_PEER;
    const Drive::Event *e = d.first(REV_FAULT_DIRECT);
    r.sameTick = e && e->tick == d.faultTick && e->wheel == wi && d.events.size() == 1;
    r.vzero = d.vactual(0) == 0 && d.vactual(1) == 0;
    r.travel = fabs(prevCmd - atContact);
    r.ms = (rig.t() - face.contactT) * 1000;
    return r;
}

static void fullStall() {
    printf("(b) unbreakable wall, recover 0: caught within 100 steps of commanded travel from contact\n");
    for (int wi = 0; wi < 2; wi++) {
        for (double tps : {0.02, 0.05, 0.1, 0.2, 0.5, 1.0}) {
            StallResult r = wallNoRecover(wi, tps);
            check(r.reached && r.faulted && r.peer && r.sameTick && r.vzero && r.travel <= 100,
                  "wheel %s %.2f turns/s: FAULT_SLIP + FAULT_PEER in one tick, both VACTUAL 0, %.1f steps of travel "
                  "and %.0f ms after contact",
                  wi ? "B" : "A", tps, r.travel, r.ms);
        }
    }
    printf("(g) recover 0 at 0.02 turns/s: faults within 0.7 s of contact\n");
    for (int wi = 0; wi < 2; wi++) {
        StallResult r = wallNoRecover(wi, 0.02);
        check(r.faulted && r.peer && r.ms <= 700, "wheel %s: FAULT_SLIP %.0f ms after contact (old 1 s leak: never)",
              wi ? "B" : "A", r.ms);
    }
}


// --- the recovery scenarios: a load meets the base current at 0.3 turns/s ---

struct Ground {
    RigConfig c;
    Rig rig;
    Drive d;
    explicit Ground(const Settings &s = Settings(), const RigConfig &cfg = RigConfig()) : c(cfg), rig(c), d(rig, s) {
        if (!d.bringUp()) {
            printf("FAIL: rig bring-up\n");
            exit(1);
        }
        rig.addFriction(friction(c));
    }
};

// Where the tripped wheel's boost landed against its snapped VACTUAL, from the
// write log after an ATTEMPT: the raise must be in the trip tick and ahead of
// the snap, which goes out in the next tick's update(); the partner's raise
// follows in that next tick.
struct BoostOrder {
    bool raiseFirst = false, raiseInTripTick = false, snapNextTick = false, partnerNextTick = false;
    int32_t snapVactual = 0;
};
static BoostOrder boostOrder(const Drive::Event &e, uint8_t snapAddr, uint8_t partnerAddr) {
    BoostOrder o;
    const auto &log = FakeTmc::log();
    long raise = -1, snap = -1, partner = -1;
    for (size_t k = e.logAt; k < log.size(); k++) {
        const FakeTmc::Write &w = log[k];
        const bool boost = w.reg == Tmc2209Uart::IHOLD_IRUN && w.accepted && ((w.value >> 8) & 31) == 31;
        if (w.addr == snapAddr && boost && raise < 0) raise = (long)k;
        if (w.addr == snapAddr && w.reg == Tmc2209Uart::VACTUAL && snap < 0) snap = (long)k;
        if (w.addr == partnerAddr && boost && partner < 0) partner = (long)k;
    }
    if (raise < 0 || snap < 0) return o;
    o.raiseFirst = raise < snap;
    o.raiseInTripTick = log[raise].timeUs == e.us;
    o.snapNextTick = log[snap].timeUs == e.us + Rig::TICK_US;
    o.partnerNextTick = partner >= 0 && log[partner].timeUs == e.us + Rig::TICK_US;
    int32_t v = (int32_t)(log[snap].value & 0xFFFFFF);
    o.snapVactual = (v & 0x800000) ? v - 0x1000000 : v;
    return o;
}

// (c) A bump under wheel A: a half-sine ridge 800 steps (0.15 turn) long,
// peaking above what the base current pulls out at, below what boost does.
// (k) rides along: through each lock the partner's hold is k times the
// command it had when its hold began, and it gets there at no more than decel.
static void bump() {
    printf("(c) bump under wheel A at 0.30 turns/s, 30%% friction, peak load between base and boosted pull-out\n");
    printf("(k) through the lock: partner B's hold = k x its command +/-1%%, |dv/dt| <= decel\n");
    for (double frac : {1.05, 1.15, 1.25, 1.35}) {
        Ground g;
        Rig &rig = g.rig;
        Drive &d = g.d;
        cruise(d, 0.3f);
        const double load = frac * basePullout(g.c);
        const double x0 = rig.a.plant.xo(), from = x0 + 100, width = 800;
        rig.a.plant.addBump(load - friction(g.c), from, width);
        double back = 0, tripT = -1, okT = -1;
        float refB = 0, lastB = rig.b.servo.commandedCps(), worstHold = 0, worstDv = 0;
        const float decelStep = rig.b.servo.decelTps2 * StepperServo::COUNTS_PER_REV * Rig::DT;
        int lockTicks = 0;
        d.until(15.0, [&](Rig &r) {
            back = fmin(back, r.a.plant.xo() - x0);
            const float vB = r.b.servo.commandedCps();
            if (d.out.event == REV_ATTEMPT || d.out.event == REV_LOCK_FAILED) {
                if (tripT < 0) tripT = r.t();
                if (d.out.event == REV_ATTEMPT) refB = vB;   // what Recovery measured B's hold against
            } else if (d.rec.state() == REC_LOCK && d.out.w[1].hold == H::HOLD_SLEW) {
                lockTicks++;
                worstHold = fmaxf(worstHold, fabsf(d.out.w[1].holdCps - d.out.k * refB) / fabsf(refB));
                worstDv = fmaxf(worstDv, fabsf(vB - lastB) / decelStep);
            }
            lastB = vB;
            if (okT < 0 && d.rec.recoveries()) okT = r.t();
            return d.faultLatched || (okT >= 0 && r.a.plant.xo() > from + width);
        });
        const int attempts = (int)d.rec.attempts();
        rig.run(1.0);
        const bool idle = d.rec.state() == REC_IDLE && d.rec.attempt() == 0;
        const bool clean = !d.faultLatched && !d.fault(0) && !d.fault(1);
        check(okT >= 0 && clean && attempts >= 1 && attempts <= 3 && idle,
              "load %.0f%% of base pull-out (%.0f%% of boosted): recovered after %d attempt%s, %.2f s after the trip, "
              "rollback %.0f steps, past the ridge, idle at attempt 0",
              frac * 100, 100 * load / BOOST_PULLOUT, attempts, attempts == 1 ? "" : "s", okT - tripT, fmax(0.0, -back));
        check(lockTicks > 10 && worstHold <= 0.01f && worstDv <= 1.0001f,
              "  partner: %d lock ticks, hold off k x command by at most %.2f%%, steepest step %.2f x decel",
              lockTicks, worstHold * 100, worstDv);
    }
}

// (d) An unbreakable wall under A with recovery on, and (i) the boost order
// on its first attempt.
static void wallGivesUp() {
    printf("(d) unbreakable wall under wheel A at 0.30 turns/s, recover 1: exactly 3 attempts, then the latch\n");
    Ground g;
    Rig &rig = g.rig;
    Drive &d = g.d;
    cruise(d, 0.3f);
    P::Load &face = rig.a.plant.addWall(rig.a.plant.xo() + 50);
    d.until(20.0, [&](Rig &) { return d.faultLatched; });
    const Drive::Event *gave = d.first(REV_GAVE_UP), *first = d.first(REV_ATTEMPT);
    const bool latched = gave && gave->tick == d.faultTick && gave->wheel == 0 && d.faultWheel == 0;
    check(latched && d.rec.attempts() == 3 && d.fault(0) == StepperServo::FAULT_SLIP &&
              d.fault(1) == StepperServo::FAULT_PEER && d.vactual(0) == 0 && d.vactual(1) == 0,
          "%u attempts (%d locked), gave up %.2f s after contact: FAULT_SLIP on A and FAULT_PEER on B in that "
          "tick, both VACTUAL 0",
          (unsigned)d.rec.attempts(), d.count(REV_LOCKED), gave ? gave->t - face.contactT : -1.0);
    printf("(i) the recovery's boost write goes ahead of the snapped VACTUAL\n");
    BoostOrder o = first ? boostOrder(*first, 0, 1) : BoostOrder();
    check(first && o.raiseFirst && o.raiseInTripTick && o.snapNextTick && o.partnerNextTick,
          "first attempt: A's IHOLD_IRUN 31/31 in the trip tick, its snapped VACTUAL %ld in the next tick's update, "
          "B's raise in that next tick", (long)o.snapVactual);
}

// (i) again where it is hardest: the trip lands during a START boost's ramp
// back down, so wheel A was written within the last 100 ms (its write gap)
// and both wheels have a write pending.
static void boostDuringRampDown() {
    Ground g;
    Rig &rig = g.rig;
    Drive &d = g.d;
    // From a standstill: START boost for 1.5 s, then down one CS per 100 ms
    // until ~3.7 s. The wall is where the wheel gets to at ~2 s.
    rig.a.plant.addWall(rig.a.plant.xo() + 2000);
    d.drive(0.3f, -0.3f);
    d.until(4.0, [&](Rig &) { return !d.events.empty(); });
    rig.run(0.05);   // the snap and the partner's raise go out in the next tick
    const Drive::Event *e = d.first(REV_ATTEMPT);
    int64_t lastWrite = -1;
    if (e) {
        const auto &log = FakeTmc::log();
        for (size_t k = 0; k < e->logAt; k++)
            if (log[k].addr == 0 && log[k].reg == Tmc2209Uart::IHOLD_IRUN && log[k].accepted) lastWrite = log[k].timeUs;
    }
    BoostOrder o = e ? boostOrder(*e, 0, 1) : BoostOrder();
    const double sinceMs = e && lastWrite >= 0 ? (e->us - lastWrite) * 1e-3 : -1;
    check(e && sinceMs >= 0 && sinceMs < UartSlot::WRITE_GAP_MS && o.raiseFirst && o.raiseInTripTick && o.snapNextTick &&
              o.partnerNextTick && d.tq.urgentWrites >= 2,
          "trip %.0f ms after A's last ramp-down write (inside its 100 ms gap): A's raise still in the trip tick and "
          "ahead of the snap, B's next tick (%u urgent writes)", sinceMs, (unsigned)d.tq.urgentWrites);
}

// (e) A hill: the same grade under both wheels, above what the base current
// climbs at 30% friction, so a slipped wheel rolls back.
static void grade() {
    printf("(e) grade under both wheels at 0.30 turns/s, 30%% friction, above base pull-out: k < 0, rollback <= 0.1 turn, "
           "then progress\n");
    for (double frac : {1.1, 1.2, 1.3}) {
        Ground g;
        Rig &rig = g.rig;
        Drive &d = g.d;
        cruise(d, 0.3f);
        const double grade = frac * basePullout(g.c) - friction(g.c);
        const double deg = asin(grade / P::GRADE_NM) * 180.0 / P::PI;
        const double x0[2] = {rig.a.plant.xo(), rig.b.plant.xo()};
        double back[2] = {0, 0};
        float minK = 0;
        rig.addGrade(deg);
        d.until(10.0, [&](Rig &r) {
            for (int i = 0; i < 2; i++) back[i] = fmin(back[i], r.wheels[i]->plant.xo() - x0[i]);
            if (d.rec.state() != REC_IDLE) minK = fminf(minK, d.out.k);
            return d.faultLatched || d.rec.recoveries() > 0;
        });
        const double rollback = -fmin(back[0], back[1]) / P::MS_PER_OUT_TURN;
        check(d.rec.recoveries() == 1 && !d.faultLatched && minK < 0 && rollback <= 0.1,
              "%.0f%% of base pull-out (a %.0f degree grade on this model): %u attempt%s, %s, k down to %+.2f, "
              "rollback %.3f turn, then 0.25 turn of progress",
              frac * 100, deg, (unsigned)d.rec.attempts(), d.rec.attempts() == 1 ? "" : "s",
              d.count(REV_JOINED) ? "the partner joined" : "both on one tick", minK, rollback);
    }
    // The same hill, held: once each recovery's boost lapses the base current
    // slips again, a fresh episode each time -- a sawtooth up the hill until
    // one episode runs out of attempts (or ten attempts land inside a
    // minute), and the latch. The hill is past what the robot climbs without
    // boost; holding Boost, or Phase 3's limiter, is the answer there.
    Ground g;
    Rig &rig = g.rig;
    Drive &d = g.d;
    cruise(d, 0.3f);
    const double x0 = rig.a.plant.xo(), t0 = rig.t();
    rig.addGrade(asin((1.2 * basePullout(g.c) - friction(g.c)) / P::GRADE_NM) * 180.0 / P::PI);
    d.until(70.0, [&](Rig &) { return d.faultLatched; });
    const Drive::Event *gave = d.first(REV_GAVE_UP);
    check(d.faultLatched && gave && gave->tick == d.faultTick && d.rec.recoveries() >= 1 &&
              d.fault(1 - d.faultWheel) == StepperServo::FAULT_PEER,
          "held 120%% hill: %u recoveries in %u attempts climbed %.2f turn over %.1f s, then an episode gave up: "
          "the latch, FAULT_PEER on the other wheel",
          (unsigned)d.rec.recoveries(), (unsigned)d.rec.attempts(), (rig.a.plant.xo() - x0) / P::MS_PER_OUT_TURN,
          rig.t() - t0);
}

// (f) The stick let go in the middle of a lock -- a zero frame, then the
// deadman lapsing: cancelled in the very next tick, holds released, no fault.
static void releaseInLock() {
    printf("(f) the stick let go during the lock: cancelled in the next tick, no fault\n");
    for (int deadman = 0; deadman < 2; deadman++) {
        Ground g;
        Rig &rig = g.rig;
        Drive &d = g.d;
        cruise(d, 0.3f);
        rig.a.plant.addWall(rig.a.plant.xo() + 50);
        d.until(5.0, [&](Rig &) { return d.rec.state() == REC_LOCK; });
        rig.tick();   // the resync: well into the lock
        const bool inLock = d.rec.state() == REC_LOCK && rig.a.servo.holding() && rig.b.servo.holding();
        const uint32_t next = rig.ticks;
        if (deadman) d.cmdExpiresUs = FakeClock::now();   // lapses at the next tick's deadman check
        else d.release();
        rig.tick();
        const Drive::Event *c = d.first(REV_CANCELLED);
        const bool cancelled = c && c->tick == next && !rig.a.servo.holding() && !rig.b.servo.holding();
        rig.run(3.0);
        check(inLock && cancelled && !d.faultLatched && !d.fault(0) && !d.fault(1) && d.rec.state() == REC_IDLE &&
                  rig.a.servo.commandedCps() == 0 && rig.b.servo.commandedCps() == 0,
              "%s: CANCELLED in the tick after, holds released, both stopped 3 s later, no fault",
              deadman ? "deadman lapsing" : "zero stick frame");
    }
}

// (h) Position moves and the demo never see the detector: tick-for-tick the
// same with it on, with lag_trip 0, and with no stall glue at all.
struct Trace {
    double cmd[2];
    int32_t pos[2];
    uint32_t vactual[2], ihr[2];
    uint8_t fault[2];
    bool operator==(const Trace &o) const {
        for (int i = 0; i < 2; i++)
            if (cmd[i] != o.cmd[i] || pos[i] != o.pos[i] || vactual[i] != o.vactual[i] || ihr[i] != o.ihr[i] ||
                fault[i] != o.fault[i])
                return false;
        return true;
    }
};
static std::vector<Trace> positionAndDemo(int variant, bool *demoRan) {
    FakeClock::set(0);   // each run from the same clock, so the traces line up exactly
    FakeTmc::clearLog();
    RigConfig c;
    for (RigWheelConfig *w : {&c.a, &c.b}) w->plant.J = P::J_RACK;   // the stand: wheels clear
    Settings s;
    if (variant == 1) s.lagTrip = 0;
    Rig rig(c);
    Drive d(rig, s, variant != 2);
    std::vector<Trace> tr;
    auto record = [&](Rig &r) {
        Trace t;
        for (int i = 0; i < 2; i++) {
            Rig::Wheel &w = *r.wheels[i];
            t.cmd[i] = w.gen.position();
            t.pos[i] = w.servo.positionCounts();
            t.vactual[i] = w.chip().regs[Tmc2209Uart::VACTUAL];
            t.ihr[i] = w.chip().regs[Tmc2209Uart::IHOLD_IRUN];
            t.fault[i] = w.servo.fault();
        }
        tr.push_back(t);
    };
    if (!d.bringUp()) return tr;
    rig.addFriction(0.05 * basePullout(c));
    // drive_wheel_goto() on each wheel, there and back.
    for (Rig::Wheel *w : rig.wheels) w->servo.servoOn(true);
    rig.a.servo.moveToTurns(0.5f);
    rig.b.servo.moveToTurns(-0.5f);
    rig.run(4.0, record);
    rig.a.servo.moveToTurns(0);
    rig.b.servo.moveToTurns(0);
    rig.run(4.0, record);
    // drive_demo_start("short").
    d.cancelCommands();
    *demoRan = d.demo.start(Demo::SHORT, {&rig.a.servo, "A", +1}, {&rig.b.servo, "B", -1});
    rig.run(15.0, [&](Rig &r) {
        record(r);
        return d.demo.running();
    });
    *demoRan = *demoRan && !d.demo.running() && !strcmp(d.demo.caption(), "done");
    return tr;
}
static void positionModeUntouched() {
    printf("(h) position moves and demo short: tick-for-tick the same with the detector on, off, and absent\n");
    bool ran[3] = {false, false, false};
    std::vector<Trace> on = positionAndDemo(0, &ran[0]), off = positionAndDemo(1, &ran[1]),
                       none = positionAndDemo(2, &ran[2]);
    check(ran[0] && ran[1] && ran[2] && on.size() > 2000 && on == off && on == none,
          "%zu ticks of goto there and back plus the demo, which finished each time: commanded integral, encoder, "
          "VACTUAL, IHOLD_IRUN and faults identical",
          on.size());
}

// (j) The encoder drops out for 150 ms (200 ms blind, with the 100 ms retry),
// or a single read fails (100 ms blind): the detector holds its reference
// through the gap, and so does the servo's own 1 s check, which until 0.3.1
// counted the command against the frozen read and faulted as slip above ~0.2
// turns/s for the dropout, ~0.4 for the one read. Neither may hide a real
// stall: a wall met inside the gap faults on the first good read.
static void encoderDropout() {
    printf("(j) a 150 ms encoder dropout, or one failed read, on wheel A: no trip, no fault\n");
    for (double tps : {0.1, 0.2, 0.5, 1.0}) {
        for (int single = 0; single < 2; single++) {
            Ground g;
            Rig &rig = g.rig;
            Drive &d = g.d;
            cruise(d, (float)tps);
            // The servo reads first in a tick, so the failure is its read.
            if (single) rig.a.i2c.failReads(1);
            else rig.a.i2c.down = true;
            rig.tick();
            const bool blinded = !rig.a.servo.encoderOk();
            if (!single) {
                rig.run(0.145);
                rig.a.i2c.down = false;
            }
            rig.run(2.0);
            const bool quiet = !d.det[0].trips() && !d.det[1].trips() && d.events.empty();
            check(blinded && quiet && !d.faultLatched && !d.fault(0) && !d.fault(1) && rig.a.servo.encoderOk(),
                  "%.1f turns/s, %s: no detector trip, no recovery, no fault", tps,
                  single ? "one failed read" : "150 ms dropout");
        }
    }
    Settings s;
    s.recover = false;   // the stall itself, not what recovery makes of it
    Ground g(s);
    Rig &rig = g.rig;
    Drive &d = g.d;
    cruise(d, 0.3f);
    rig.a.i2c.down = true;
    rig.a.plant.addWall(rig.a.plant.xo() + 50);   // met ~30 ms into the gap
    rig.run(0.15);
    rig.a.i2c.down = false;
    const bool blindThrough = !d.faultLatched;
    double backT = -1;
    d.until(1.0, [&](Rig &r) {
        if (backT < 0 && r.a.servo.encoderOk()) backT = r.t();
        return d.faultLatched;
    });
    check(blindThrough && d.faultLatched && d.faultWheel == 0 && d.fault(0) == StepperServo::FAULT_SLIP &&
              d.fault(1) == StepperServo::FAULT_PEER && backT >= 0 && rig.t() - backT <= 0.05,
          "a wall met inside a 150 ms dropout at 0.30 turns/s: FAULT_SLIP + FAULT_PEER %.0f ms after the first good read",
          backT >= 0 ? (rig.t() - backT) * 1000 : -1.0);
}

// --- more: the trips it must not retry, and recovery without boost ---------

// A push from behind past pull-out: a LEAD, never retried, even with recovery
// on and a live stick.
static void leadFaults() {
    printf("(l) a push on wheel A past its pull-out: a lead, faulted at once with recover 1\n");
    Ground g;
    Rig &rig = g.rig;
    Drive &d = g.d;
    cruise(d, 0.2f);
    rig.a.plant.addStep(-2.0 * basePullout(g.c), rig.t());
    d.until(3.0, [&](Rig &) { return d.faultLatched; });
    const Drive::Event *e = d.first(REV_FAULT_DIRECT);
    check(e && e->wheel == 0 && d.events.size() == 1 && d.rec.attempts() == 0 && d.fault(0) == StepperServo::FAULT_SLIP &&
              d.fault(1) == StepperServo::FAULT_PEER && d.st[0].trip < 0,
          "FAULT_DIRECT on the lead, FAULT_SLIP + FAULT_PEER, no attempt");
}

// The bench's `wheel A vel`: no live stick and the other loop open, so a
// stall faults directly, recover 1 or not.
static void benchWheelFaults() {
    printf("(m) bench 'wheel A vel 0.3' into a wall: not eligible, faulted at once\n");
    Ground g;
    Rig &rig = g.rig;
    Drive &d = g.d;
    // drive_wheel_velocity(A): A's loop closed in velocity mode, no robot command.
    rig.a.servo.servoOn(true);
    rig.a.servo.setVelocityTps(0.3f);
    rig.cmdActive = false;
    rig.run(0.3 / g.c.accelTps2 + 4.0);
    rig.a.plant.addWall(rig.a.plant.xo() + 50);
    d.until(3.0, [&](Rig &) { return d.faultLatched; });
    const Drive::Event *e = d.first(REV_FAULT_DIRECT);
    check(e && d.rec.attempts() == 0 && d.fault(0) == StepperServo::FAULT_SLIP && d.fault(1) == StepperServo::FAULT_NONE,
          "FAULT_DIRECT, FAULT_SLIP on A, B (loop open) stopped with spin(0)");
}

// The thermal model has boost paused: the recovery still freezes, locks and
// ramps, at base current, and on a ridge base current cannot clear it ends in
// the normal give-up -- never a current raise.
static void recoveryWithoutBoost() {
    printf("(n) boost paused by the heat limit: recovery runs at base current, never raises it\n");
    Ground g;
    Rig &rig = g.rig;
    Drive &d = g.d;
    for (Torque::W &w : d.tq.w) w.thermal.reset(1.2f);   // past therm_lim 1.10: limited
    cruise(d, 0.3f);
    const size_t mark = FakeTmc::log().size();
    rig.a.plant.addBump(1.25 * basePullout(g.c) - friction(g.c), rig.a.plant.xo() + 100, 800);
    bool refused = false;
    d.until(15.0, [&](Rig &) {
        refused |= (d.tq.w[0].out.reasons & BP::RECOVERY) && (d.tq.w[0].out.limitedBy & BP::LIMIT_HEAT);
        return d.faultLatched;
    });
    bool raised = false;
    const auto &log = FakeTmc::log();
    for (size_t k = mark; k < log.size(); k++)
        raised |= log[k].reg == Tmc2209Uart::IHOLD_IRUN && ((log[k].value >> 8) & 31) > rig.a.gen.runCurrent();
    check(refused && !raised && d.first(REV_GAVE_UP) && d.rec.attempts() == 3 && d.fault(1) == StepperServo::FAULT_PEER,
          "boost asked and refused (heat), no IRUN above base written, 3 attempts at base current, then the latch");
}

// At a crawl a slipped wheel under a load that pushes back rolls back faster
// than it was ever asked to go forward, and the hold may not follow it past
// that (|k| <= 1: never faster than the command). The robot's limit, not a
// bug: whatever the outcome, it is a recovery or the ordinary latch.
static void crawl() {
    printf("(o) at a crawl: whatever a ridge does at 0.10 turns/s, it ends recovered or in the ordinary latch\n");
    Ground g;
    Rig &rig = g.rig;
    Drive &d = g.d;
    cruise(d, 0.1f);
    rig.a.plant.addBump(1.15 * basePullout(g.c) - friction(g.c), rig.a.plant.xo() + 100, 800);
    d.until(20.0, [&](Rig &) { return d.faultLatched || d.rec.recoveries() > 0; });
    const Drive::Event *gave = d.first(REV_GAVE_UP);
    const bool latch = d.faultLatched && gave && gave->tick == d.faultTick && d.fault(1) == StepperServo::FAULT_PEER;
    check(d.rec.recoveries() ? !d.faultLatched : latch, "115%% ridge at 0.10 turns/s: %s after %u attempt%s",
          d.rec.recoveries() ? "recovered" : "gave up, FAULT_SLIP + FAULT_PEER", (unsigned)d.rec.attempts(),
          d.rec.attempts() == 1 ? "" : "s");
}

int main() {
    setvbuf(stdout, nullptr, _IOLBF, 0);   // keep every line if a sanitizer aborts mid-run
    inSync();
    fullStall();
    bump();
    wallGivesUp();
    boostDuringRampDown();
    grade();
    releaseInLock();
    positionModeUntouched();
    encoderDropout();
    leadFaults();
    benchWheelFaults();
    recoveryWithoutBoost();
    crawl();
    if (failures) {
        printf("FAIL: %d recovery rig check%s\n", failures, failures == 1 ? "" : "s");
        return 1;
    }
    puts("PASS: recovery rig: in sync 0.02-1.5 turns/s with no trip, a full stall caught within 100 steps at "
         "0.02-1.0 (recover 0), bump cleared, wall 3 attempts then FAULT_SLIP + FAULT_PEER in one tick, hill "
         "rollback under 0.1 turn then progress, release/deadman cancel in a tick, position mode and demo "
         "untouched, boost before the snap, encoder dropout and a failed read with no fault (a stall inside "
         "the gap still caught), lead, bench wheel, no boost");
    return 0;
}
