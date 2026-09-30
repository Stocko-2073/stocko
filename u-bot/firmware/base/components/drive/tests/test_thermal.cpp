#undef NDEBUG   // these asserts are the test
#include <cassert>
#include <cmath>
#include <cstdio>
#include <initializer_list>
#include "ThermalModel.h"

// The plan's currents: boost is IRUN 31 (1768 mA), cruise IRUN 20 (1160) or
// IRUN 26 (1492), parked on IHOLD 9 (552).
static const float BOOST = 1768, CRUISE = 1160, CRUISE_HI = 1492, PARKED = 552;

static double hss(double ma) { return (ma / 1500) * (ma / 1500); }
static bool near(double got, double want, double rel) { return fabs(got - want) <= rel * fabs(want); }

// `seconds` of `ma` in ticks of dt, the way the drive feeds it.
static void run(ThermalModel &m, float ma, double seconds, float dt = 0.005f) {
    for (long i = lround(seconds / dt); i > 0; i--) m.accumulate(dt, ma);
}

// Ticks of `ma` until limited() reads `want`; the seconds that took.
static double until(ThermalModel &m, float ma, bool want, float dt = 0.005f) {
    const long most = lround(7200 / dt);   // two hours: something is wrong
    long n = 0;
    while (m.limited() != want) {
        m.accumulate(dt, ma);
        n++;
        assert(n < most);
    }
    return n * (double)dt;
}

int main() {
    ThermalModel m;
    assert(m.heat() == ThermalModel::BOOT_H && !m.limited());

    // Ten heating taus at rated current settle on 1.0.
    m.reset(0);
    run(m, 1500, 6000);
    assert(near(m.heat(), 1.0, 0.005));

    // One heating tau of boost from cold: 1 - 1/e of the way to h_ss = 1.389.
    m.reset(0);
    run(m, BOOST, 600);
    assert(near(m.heat(), 1.389 * (1 - exp(-1.0)), 0.01));

    // One cooling tau (2 x 600 s) with no current: 1/e of the way down.
    m.reset(1.0f);
    run(m, 0, 1200);
    assert(near(m.heat(), 0.368, 0.01));

    // The latch: on at the limit, off only at limit - hysteresis.
    m.reset(1.0f);
    assert(!m.limited());
    until(m, BOOST, true);
    assert(m.heat() >= 1.10f && m.heat() < 1.1005f);   // trips on the crossing, not late
    run(m, CRUISE, 120);                               // cools to ~1.05
    assert(m.limited() && m.heat() > 1.0f && m.heat() < 1.08f);
    until(m, CRUISE, false);
    assert(m.heat() <= 1.0f && m.heat() > 0.9995f);
    run(m, BOOST, 60);                                 // back up to ~1.04
    assert(!m.limited() && m.heat() > 1.02f && m.heat() < 1.10f);
    m.reset(1.10f);
    assert(m.limited());      // a carried heat at the limit starts limited...
    m.reset(1.05f);
    assert(!m.limited());     // ...one inside the band doesn't
    ThermalModel::Params p;   // a new limit applies to the heat already there
    m.reset(1.10f);
    p.limit = 1.30f;          // resume point 1.20: free again
    assert(m.configure(p) && !m.limited());
    p.limit = 1.00f;          // now well past it
    assert(m.configure(p) && m.limited());
    assert(m.configure(ThermalModel::Params()));

    // Tick size doesn't matter. A 20-minute mixed profile at 1 ms, 5 ms, 50 ms
    // and 1 s ticks against the exact answer: h never crosses h_ss inside a
    // segment, so each segment is one exponential.
    struct Seg { double s; float ma; };
    const Seg profile[] = {{120, CRUISE}, {90, BOOST}, {60, 0}, {150, PARKED},
                           {240, BOOST}, {60, CRUISE_HI}, {180, CRUISE}, {300, 0}};
    const float dts[] = {0.001f, 0.005f, 0.05f, 1.0f};
    double end[4];
    for (int k = 0; k < 4; k++) {
        ThermalModel t;
        double want = ThermalModel::BOOT_H;
        for (const Seg &g : profile) {
            run(t, g.ma, g.s, dts[k]);
            double ss = hss(g.ma), tau = ss > want ? 600 : 1200;
            want = ss + (want - ss) * exp(-g.s / tau);
            assert(near(t.heat(), want, 0.005));
        }
        end[k] = t.heat();
    }
    assert(near(end[1], end[2], 0.005));   // the drive's 5 ms tick against a 50 ms one
    const double bootToLimit = 600 * log((hss(BOOST) - ThermalModel::BOOT_H) / (hss(BOOST) - 1.10));
    for (float dt : dts) {
        ThermalModel t;
        assert(near(until(t, BOOST, true, dt), bootToLimit, 0.005));
    }
    // Uneven ticks anywhere from 1 ms to 1 s stay finite and inside what the
    // currents allow.
    uint32_t seed = 1;
    ThermalModel r;
    for (int i = 0; i < 100000; i++) {
        seed = seed * 1664525u + 1013904223u;
        r.accumulate(0.001f * (1 + (seed >> 8) % 1000), (float)((seed >> 20) % 1800));
        assert(isfinite(r.heat()) && r.heat() >= 0 && r.heat() < hss(1800));
    }

    // Bad input is dropped without disturbing anything, even mid-window.
    ThermalModel a, b;
    a.reset(0.5f);
    b.reset(0.5f);
    a.accumulate(0.05f, 1000);   // half a window pending in both
    b.accumulate(0.05f, 1000);
    a.accumulate(NAN, 1000);
    a.accumulate(-0.005f, 1000);
    a.accumulate(INFINITY, 1000);
    a.accumulate(0.005f, NAN);
    a.accumulate(0.05f, -BOOST);   // squared, it would look like real heat
    a.accumulate(0.005f, INFINITY);
    a.accumulate(-INFINITY, -INFINITY);
    run(a, BOOST, 30);
    run(b, BOOST, 30);
    assert(a.heat() == b.heat() && a.heat() > 0.5f);
    ThermalModel c;
    ThermalModel::Params q;
    q.tauHeatS = 900;
    assert(c.configure(q));
    for (int i = 0; i < 9; i++) {   // refused whole, keeping the old parameters
        ThermalModel::Params x;
        switch (i) {
            case 0: x.ratedMa = 0; break;
            case 1: x.ratedMa = NAN; break;
            case 2: x.tauHeatS = -600; break;
            case 3: x.tauHeatS = INFINITY; break;
            case 4: x.coolRatio = 0; break;
            case 5: x.limit = NAN; break;
            case 6: x.hysteresis = -0.1f; break;
            case 7: x.hysteresis = x.limit; break;   // resume point at zero
            default: x.hysteresis = NAN; break;
        }
        assert(!c.configure(x) && c.params().tauHeatS == 900);
    }
    for (float h : {NAN, -0.1f, INFINITY}) {
        c.reset(h);
        assert(c.heat() == ThermalModel::BOOT_H);
    }
    assert(c.secondsToLimit(NAN) == 0 && c.secondsToLimit(-1) == 0);

    // secondsToLimit() is the analytic budget, and running it out agrees.
    ThermalModel s;
    s.reset((float)hss(CRUISE));
    const double warmToLimit = 600 * log((hss(BOOST) - hss(CRUISE)) / (hss(BOOST) - 1.10));
    assert(near(s.secondsToLimit(BOOST), warmToLimit, 0.001));
    run(s, BOOST, 300);   // half of it spent
    assert(near(s.secondsToLimit(BOOST), warmToLimit - 300, 0.002));
    assert(near(until(s, BOOST, true), warmToLimit - 300, 0.005));
    assert(s.secondsToLimit(BOOST) == 0);   // limited: nothing left
    ThermalModel u;
    assert(near(u.secondsToLimit(BOOST), bootToLimit, 0.001));
    assert(isinf(u.secondsToLimit(1500)) && isinf(u.secondsToLimit(1570)) &&
           isinf(u.secondsToLimit(0)));   // settle at or below 1.10: never
    assert(isfinite(u.secondsToLimit(1580)));   // h_ss 1.11: slowly

    // inferMa(): what the driver is really putting through the motor.
    using TM = ThermalModel;
    const uint32_t TPD = 570, STEP = 192;
    const float run20 = MotorCurrent::milliamps(20), hold9 = MotorCurrent::milliamps(9);
    assert(TM::inferMa(false, true, 0, 20, 9, TPD, STEP) == 0);        // EN high
    assert(TM::inferMa(false, false, 9000, 20, 9, TPD, STEP) == 0);
    assert(TM::inferMa(true, true, 0, 20, 9, TPD, STEP) == run20);
    assert(TM::inferMa(true, true, 100000, 20, 9, TPD, STEP) == run20);   // moving wins
    assert(TM::inferMa(true, false, 0, 20, 9, TPD, STEP) == run20);
    assert(TM::inferMa(true, false, TPD - 1, 20, 9, TPD, STEP) == run20);   // power-down window
    assert(TM::inferMa(true, false, TPD, 20, 9, TPD, STEP) == run20);       // first step a whole STEP on
    assert(TM::inferMa(true, false, TPD + STEP - 1, 20, 9, TPD, STEP) == run20);
    for (uint32_t k = 1; k <= 11; k++) {                                    // then one CS per STEP
        assert(TM::inferMa(true, false, TPD + k * STEP, 20, 9, TPD, STEP) == MotorCurrent::milliamps(20 - k));
        assert(TM::inferMa(true, false, TPD + k * STEP - 1, 20, 9, TPD, STEP) ==
               MotorCurrent::milliamps(21 - k));
    }
    assert(TM::inferMa(true, false, TPD + 11 * STEP, 20, 9, TPD, STEP) == hold9);
    assert(TM::inferMa(true, false, TPD + 500 * STEP, 20, 9, TPD, STEP) == hold9);   // floored at IHOLD
    assert(TM::inferMa(true, false, 0xFFFFFFFFu, 20, 9, TPD, STEP) == hold9);
    assert(TM::inferMa(true, false, TPD - 1, 20, 9, TPD, 0) == run20);   // IHOLDDELAY 0:
    assert(TM::inferMa(true, false, TPD, 20, 9, TPD, 0) == hold9);       // straight to IHOLD
    assert(TM::inferMa(true, false, 60000, 31, 31, TPD, STEP) == MotorCurrent::milliamps(31));   // boosted hold
    assert(TM::inferMa(true, false, 60000, 40, 35, TPD, STEP) == MotorCurrent::milliamps(31));   // out of range: hot side
    // The drive's numbers, from the register formulas (TPOWERDOWN 20, IHOLDDELAY 8, wheel A's gain).
    const double tpd = (1048576.0 + 20 * 262144.0) / (12e6 * 1.0158) * 1.1 * 1000;
    const double step = 8 * 262144.0 / 12e6 * 1.1 * 1000;
    assert(tpd > 560 && tpd < 580 && (uint32_t)step == STEP);
    // Parked from IRUN 20: IHOLD 9 about 2.7 s after the last step.
    assert(TM::inferMa(true, false, (uint32_t)(tpd + 11 * step) + 1, 20, 9, (uint32_t)tpd, (uint32_t)step) == hold9);

    // The plan's table, boost 1768 and limit 1.10, to +/-3%.
    struct Case { const char *what; float h0, ma; bool want; double min; };
    const Case table[] = {
        {"boost from warm at 1160", (float)hss(CRUISE), BOOST, true, 10.1},
        {"boost from power-on", ThermalModel::BOOT_H, BOOST, true, 7.1},
        {"recharge cruising 1160", 1.10f, CRUISE, false, 4.4},
        {"recharge parked 552", 1.10f, PARKED, false, 2.2},
        {"boost from warm at 1492", (float)hss(CRUISE_HI), BOOST, true, 3.2},
        {"recharge cruising 1492", 1.10f, CRUISE_HI, false, 46.8},
    };
    for (const Case &k : table) {
        ThermalModel t;
        t.reset(k.h0);
        const double min = until(t, k.ma, k.want) / 60;
        printf("  %-24s %6.2f min (plan %.1f)\n", k.what, min, k.min);
        assert(near(min, k.min, 0.03));
    }

    puts("PASS: thermal settling, heating and cooling taus, limit latch and hysteresis, "
         "tick-size independence 1 ms..1 s, bad input, secondsToLimit, inferMa, plan durations");
    return 0;
}
