// drive.cpp's torque path on the host rig: the real VelGen live-current
// writes, BoostPolicy, OtpwDerate, ThermalModel and UartSlot, on two plants
// whose driver current follows IHOLD_IRUN the way the TMC2209's does, ticked
// in drive.cpp's order through the rig's onTorque and onUartSlot hooks.
//
// The glue is RigTorque.h's Torque: drive.cpp's torqueUpdate(), uartSlot(),
// pollDriver() and checkFaults(), line for line where it matters.
#undef NDEBUG   // these asserts are the test
#include <cassert>
#include <cmath>
#include <cstdio>
#include <vector>

#include "BoostPolicy.h"
#include "Rig.h"
#include "RigTorque.h"
#include "ThermalModel.h"
#include "UartSlot.h"

using BP = BoostPolicy;

// --- helpers ---

static uint32_t ihr(uint8_t run, uint8_t hold, uint8_t delay = 8) {
    return (uint32_t)hold | ((uint32_t)run << 8) | ((uint32_t)delay << 16);
}
static uint8_t runOf(uint32_t v) { return (uint8_t)((v >> 8) & 31); }
static uint8_t holdOf(uint32_t v) { return (uint8_t)(v & 31); }

struct Write {
    int64_t us;
    uint32_t value;
};
// IHOLD_IRUN writes to one address that landed, from log entry `from` on.
static std::vector<Write> currentWrites(uint8_t addr, size_t from) {
    std::vector<Write> out;
    const auto &log = FakeTmc::log();
    for (size_t i = from; i < log.size(); i++)
        if (log[i].addr == addr && log[i].reg == Tmc2209Uart::IHOLD_IRUN && log[i].accepted)
            out.push_back({log[i].timeUs, log[i].value});
    return out;
}

static void bringUp(Rig &rig, Torque &tq) {
    assert(rig.setup());
    assert(tq.enable());
}

// (a) A manual boost lands IHOLD_IRUN 31 in the tick after it is asked for --
// wheel A's in that tick, B's in the next, one write per tick -- and the
// braced wheels hold at it.
static void manualLands() {
    RigConfig c;   // 1200/600 mA: IRUN 20, IHOLD 9
    Rig rig(c);
    Torque tq(rig);
    bringUp(rig, tq);
    size_t mark = FakeTmc::log().size();
    rig.run(1.0);
    assert(currentWrites(0, mark).empty() && currentWrites(1, mark).empty());   // standing at base: nothing to write
    assert(rig.a.gen.liveRun() == 20 && rig.a.gen.liveHold() == 9);

    mark = FakeTmc::log().size();
    tq.manual(5000);
    rig.tick();
    const int64_t t1 = FakeClock::now();
    auto a = currentWrites(0, mark), b = currentWrites(1, mark);
    assert(a.size() == 1 && a[0].us == t1 && a[0].value == ihr(31, 31) && b.empty());
    assert(rig.a.gen.liveRun() == 31 && rig.a.gen.liveHold() == 31);
    rig.tick();
    b = currentWrites(1, mark);
    assert(b.size() == 1 && b[0].us == t1 + Rig::TICK_US && b[0].value == ihr(31, 31));
    assert(tq.w[0].out.boosting && tq.w[1].out.boosting && tq.w[0].out.reasons == BP::MANUAL);
    // Standing still, the driver runs on IHOLD, which is the boost current too.
    rig.run(1.0);
    assert(rig.a.plant.csActual() == 31 && rig.b.plant.csActual() == 31);
    assert(tq.liveWrites == 2 && !tq.liveFailures && rig.driversOn);
    printf("  ok   (a) manual boost: IRUN 31 on A in the tick after the request, B one tick later; held at 31\n");
}

// (b) The plan's rack check at run_ma 1500: `boost on 5000` during a drive.
// CS_ACTUAL 31, then one CS per 100 ms after the lapse, 26 at +0.5 s; hold
// all the way to 9 at +2.2 s. Wheel A's writes land on the policy's 100 ms
// grid, B's a tick behind.
static void lapseRamps() {
    RigConfig c;
    c.runMa = 1500;   // IRUN 26
    Rig rig(c);
    Torque tq(rig);
    bringUp(rig, tq);
    rig.drive(0.1f, -0.1f);
    rig.run(4.0);   // up to speed; the START boost (1.5 s, then 2.2 s down) has come and gone
    assert(rig.a.gen.liveRun() == 26 && rig.a.gen.liveHold() == 9 && !tq.w[0].out.reasons);
    assert(rig.a.plant.csActual() == 26);

    tq.manual(5000);
    const int64_t asked = FakeClock::now();
    rig.run(0.5);
    assert(rig.a.plant.csActual() == 31 && rig.b.plant.csActual() == 31);
    for (int i = 0; i < 899; i++) rig.tick();   // to the tick before the expiry, 4.995 s in
    size_t mark = FakeTmc::log().size();
    assert(tq.w[0].out.boosting);
    rig.tick();
    const int64_t expiry = FakeClock::now();
    assert(expiry - asked == 5000000 && !tq.w[0].out.boosting && !tq.w[0].out.reasons);
    rig.run(2.5);
    auto a = currentWrites(0, mark), b = currentWrites(1, mark);
    assert(a.size() == 22 && b.size() == 22);   // hold 31 -> 9 is the longer ramp
    for (size_t k = 0; k < a.size(); k++) {
        const uint8_t run = (uint8_t)(k < 5 ? 30 - k : 26), hold = (uint8_t)(30 - k);
        assert(a[k].us == expiry + (int64_t)(k + 1) * 100000);
        assert(b[k].us == a[k].us + Rig::TICK_US);
        assert(a[k].value == ihr(run, hold) && b[k].value == ihr(run, hold));
    }
    assert(runOf(a[4].value) == 26 && a[4].us - expiry == 500000 && holdOf(a.back().value) == 9);
    // The plant has CS_ACTUAL at IRUN while it moves: 26 again.
    assert(rig.a.plant.csActual() == 26 && rig.b.plant.csActual() == 26);
    assert(!tq.liveFailures && !tq.w[0].csMismatch && !tq.w[1].csMismatch);
    printf("  ok   (b) lapse at run_ma 1500: 31 -> 26 in 5 steps of 100 ms (A on the grid, B a tick later), hold to 9 in 2.2 s\n");
}

// (c) START: leaving a standstill of 0.5 s or more boosts for boost_start_ms;
// a shorter pause is the same move.
static void startBoost() {
    RigConfig c;
    Rig rig(c);
    Torque tq(rig);
    bringUp(rig, tq);
    rig.run(0.1);
    size_t mark = FakeTmc::log().size();
    rig.drive(0.1f, -0.1f);
    rig.tick();   // the first update has the generators running
    assert(rig.a.gen.rate() != 0 && tq.w[0].out.reasons == BP::START && tq.w[0].out.boosting);
    assert(currentWrites(0, mark).size() == 1 && rig.a.gen.liveRun() == 31);
    rig.tick();
    assert(rig.b.gen.liveRun() == 31);
    rig.run(4.0);   // 1.5 s of START, then 2.2 s back down to base
    assert(!tq.w[0].out.reasons && rig.a.gen.liveRun() == 20 && rig.a.gen.liveHold() == 9);

    // Stop, 0.4 s still, go again: no START.
    rig.release();
    rig.run(1.0, [](Rig &r) { return r.a.gen.rate() != 0 || r.b.gen.rate() != 0; });
    assert(rig.a.gen.rate() == 0);
    rig.run(0.4);
    mark = FakeTmc::log().size();
    rig.drive(0.1f, -0.1f);
    rig.run(1.0);
    assert(!tq.w[0].out.reasons && currentWrites(0, mark).empty());

    // Stop, 0.6 s still, go again: START.
    rig.release();
    rig.run(1.0, [](Rig &r) { return r.a.gen.rate() != 0 || r.b.gen.rate() != 0; });
    rig.run(0.6);
    mark = FakeTmc::log().size();
    rig.drive(0.1f, -0.1f);
    rig.tick();
    assert(tq.w[0].out.reasons == BP::START && currentWrites(0, mark).size() == 1 && rig.a.gen.liveRun() == 31);
    printf("  ok   (c) START after >= 0.5 s still (and after enable), none after a 0.4 s pause\n");
}

// (d) OTPW in the fake DRV_STATUS derates through the soft path, one wheel
// only, while the drivers stay on; a hard bit still invalidates and cuts EN.
static void otpwSoftHard() {
    RigConfig c;
    Rig rig(c);
    Torque tq(rig);
    bringUp(rig, tq);
    rig.drive(0.2f, -0.2f);
    rig.run(3.0);
    rig.a.chip().regs[Tmc2209Uart::DRVSTATUS] |= VelGen::DRV_OTPW;   // the plant keeps planted flags
    const double t0 = rig.t();
    rig.run(1.0, [&](Rig &) { return tq.w[0].derate.level() == 0; });
    assert(tq.w[0].derate.level() == 1 && rig.t() - t0 <= 0.55);   // at A's next driver poll
    assert(rig.a.gen.ok() && rig.driversOn && tq.w[1].derate.level() == 0);
    // Level 1 is no boost: a manual boost is refused on A and granted on B.
    tq.manual(60000);
    rig.run(0.1);
    assert(!tq.w[0].out.boosting && (tq.w[0].out.limitedBy & BP::LIMIT_DERATE) && rig.a.gen.liveRun() == 20);
    assert(tq.w[1].out.boosting && rig.b.gen.liveRun() == 31);
    tq.manual(0);
    // Level 2 at +10 s: base at 75% (IRUN 20 -> 14, IHOLD 9 -> 6), down the ramp.
    rig.run(11.0);
    assert(tq.w[0].derate.level() == 2 && rig.a.gen.liveRun() == 14 && rig.a.gen.liveHold() == 6);
    assert(rig.a.plant.csActual() == 14);   // moving: the driver runs at the derated IRUN
    // Level 3 at +20 s: 50% (9 / 4).
    rig.run(10.0);
    assert(tq.w[0].derate.level() == 3 && rig.a.gen.liveRun() == 9 && rig.a.gen.liveHold() == 4);
    assert(tq.w[1].derate.level() == 0 && rig.b.gen.liveRun() == 20 && rig.b.gen.liveHold() == 9);
    assert(rig.a.gen.ok() && rig.b.gen.ok() && rig.driversOn && rig.a.servo.fault() == StepperServo::FAULT_NONE);
    // Clear for 30 s: one level back, and the current straight back up to 75%.
    rig.a.chip().regs[Tmc2209Uart::DRVSTATUS] &= ~VelGen::DRV_OTPW;
    rig.run(30.6);
    assert(tq.w[0].derate.level() == 2 && rig.a.gen.liveRun() == 14 && rig.a.gen.liveHold() == 6);
    assert(tq.w[0].derate.events() == 1 && !tq.liveFailures);

    // OT, a hard flag: invalidated at the next poll, EN cut, the wheel faulted.
    rig.a.chip().regs[Tmc2209Uart::DRVSTATUS] |= 1u << 1;
    rig.run(1.0, [&](Rig &r) { return r.driversOn; });
    assert(!rig.driversOn && !rig.a.gen.ok() && rig.a.servo.fault() == StepperServo::FAULT_DRIVER);
    // t143 is hard as well, and so is anything at begin(): OTPW alone is not.
    rig.a.chip().regs[Tmc2209Uart::DRVSTATUS] = VelGen::DRV_OTPW;
    assert(tq.enable() && rig.a.gen.hot() && tq.w[0].derate.level() == 2);   // hot at enable: level 2 at least
    rig.a.chip().regs[Tmc2209Uart::DRVSTATUS] = 1u << 9;
    rig.run(1.0, [&](Rig &r) { return r.driversOn; });
    assert(!rig.driversOn && !rig.a.gen.ok());
    printf("  ok   (d) OTPW derates A through levels 1/2/3 with the drivers on, B untouched; OT and t143 still cut EN\n");
}

// (e) The heat limit pauses a boost that is still being asked for, and gives
// it back at the resume point (therm_tau_s 60 to keep the run short).
static void heatLimit() {
    RigConfig c;
    Rig rig(c);
    Torque tq(rig, MotorCurrent::BOOST_MAX_MA, 1500, 60.0f, 1.10f);
    bringUp(rig, tq);
    for (Torque::W &t : tq.w) t.thermal.reset(1.05f);
    tq.manual(60000);   // braced where it stands, at 1768 mA
    rig.tick();
    rig.tick();
    assert(rig.a.gen.liveRun() == 31 && rig.b.gen.liveRun() == 31);
    // Heating at h_ss 1.39 until the limit.
    double limitedAt = -1;
    rig.run(20.0, [&](Rig &r) {
        if (!tq.w[0].thermal.limited()) return true;
        limitedAt = r.t();
        return false;
    });
    const float hLimit = tq.w[0].thermal.heat();
    assert(limitedAt > 0 && hLimit >= 1.10f && hLimit < 1.101f);
    assert(!tq.w[0].out.boosting && (tq.w[0].out.limitedBy & BP::LIMIT_HEAT) && tq.w[0].out.reasons == BP::MANUAL);
    // Back down to base, one CS per 100 ms, then cooling; boost stays refused
    // the whole way down to the resume point, and comes straight back there.
    float lowest = 2;
    bool resumed = false;
    uint8_t lastRun = 0, lastHold = 0;   // the live pair in the last tick still limited
    rig.run(60.0, [&](Rig &r) {
        const Torque::W &t = tq.w[0];
        if (!t.thermal.limited()) {
            resumed = true;
            return false;
        }
        assert(!t.out.boosting);
        lowest = fminf(lowest, t.thermal.heat());
        lastRun = r.a.gen.liveRun();
        lastHold = r.a.gen.liveHold();
        return true;
    });
    assert(resumed && tq.w[0].thermal.heat() <= 1.00f && tq.w[0].thermal.heat() > 0.999f);
    assert(lastRun == 20 && lastHold == 9);   // base, all the way down
    // Granted again in the very tick it resumed, and written there.
    assert(tq.w[0].out.boosting && rig.a.gen.liveRun() == 31 && rig.a.gen.liveHold() == 31);
    assert(lowest > 1.00f && !tq.liveFailures && rig.driversOn);
    printf("  ok   (e) heat limit: boost paused at h %.3f after %.1f s, refused while cooling, back at h %.3f\n",
           hLimit, limitedAt, tq.w[0].thermal.heat());
}

// (f) Disabling drops everything back to base; re-enabling starts clean,
// with the first move a START.
static void disableResets() {
    RigConfig c;
    Rig rig(c);
    Torque tq(rig);
    bringUp(rig, tq);
    tq.manual(60000);
    rig.run(0.1);
    assert(rig.a.gen.liveRun() == 31);
    tq.disable();
    rig.run(0.1);
    assert(!tq.w[0].out.reasons && !tq.w[0].pending && tq.w[0].out.run == 20);
    assert(tq.enable() && rig.a.gen.liveRun() == 20 && rig.a.gen.liveHold() == 9);
    size_t mark = FakeTmc::log().size();
    rig.run(0.2);
    assert(currentWrites(0, mark).empty());
    rig.drive(0.1f, -0.1f);
    rig.tick();
    assert(tq.w[0].out.reasons == BP::START && rig.a.gen.liveRun() == 31);
    printf("  ok   (f) disable resets to base, enable starts clean and arms START\n");
}

int main() {
    printf("torque path on the rig: VelGen live writes + BoostPolicy + OtpwDerate + ThermalModel + UartSlot\n");
    manualLands();
    lapseRamps();
    startBoost();
    otpwSoftHard();
    heatLimit();
    disableResets();
    puts("PASS: manual boost lands in the tick, lapse ramps one CS per 100 ms, START after 0.5 s still, "
         "OTPW soft derate vs hard fault, heat limit pause and resume, disable/enable resets");
    return 0;
}
