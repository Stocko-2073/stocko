#undef NDEBUG   // these asserts are the test
#include <cassert>
#include <cstdio>
#include <initializer_list>
#include "UartSlot.h"

// The control tick's extra bus group, chosen without drive.cpp: what goes
// first, how often each wheel may be written, what the tick budget holds back,
// and the health poll's 50 ms guarantee.

using U = UartSlot;

static const uint32_t TICK = 5;   // ms, the 200 Hz control tick

static U::Request live(bool a, bool b, bool raiseA = false, bool raiseB = false) {
    U::Request r;
    r.live[0] = a;
    r.live[1] = b;
    r.raise[0] = raiseA;
    r.raise[1] = raiseB;
    return r;
}

static bool is(const U::Choice &c, U::Group g, uint8_t wheel = 0) {
    return c.group == g && (g != U::LIVE || c.wheel == wheel);
}

int main() {
    {   // Nothing pending: a health step every 125 ms, on the dot, and nothing between.
        U s;
        s.reset(1000);
        uint32_t last = 1000;
        int steps = 0;
        for (uint32_t t = 1000 + TICK; t <= 3000; t += TICK) {
            U::Choice c = s.next(t, 500, U::Request());
            if (c.group == U::NONE) continue;
            assert(is(c, U::HEALTH) && t - last == 125);
            last = t;
            steps++;
        }
        assert(steps == 16 && s.runs(U::HEALTH) == 16 && !s.deferred() && !s.forced());
    }

    {   // A pending write goes at once, then waits out the 100 ms gap on its wheel.
        U s;
        s.reset(1000);
        assert(is(s.next(1005, 0, live(true, false)), U::LIVE, 0));
        for (uint32_t t = 1010; t < 1105; t += TICK) {
            assert(s.next(t, 0, live(true, false)).group == U::NONE);   // 95 ms and under: too soon
        }
        assert(is(s.next(1105, 0, live(true, false)), U::LIVE, 0));
        // The other wheel's gap is its own.
        assert(is(s.next(1110, 0, live(true, true)), U::LIVE, 1));
    }

    {   // Two wheels wanting the same kind of write alternate, A first.
        for (bool up : {false, true}) {
            U s;
            s.reset(0);
            assert(is(s.next(5, 0, live(true, true, up, up)), U::LIVE, 0));
            assert(is(s.next(10, 0, live(true, true, up, up)), U::LIVE, 1));
            assert(s.next(15, 0, live(true, true, up, up)).group == U::NONE);
            assert(is(s.next(105, 0, live(true, true, up, up)), U::LIVE, 0));
            assert(is(s.next(110, 0, live(true, true, up, up)), U::LIVE, 1));
        }
        // After a write to A, B is looked at first, whichever is asked first.
        U s;
        s.reset(0);
        assert(is(s.next(5, 0, live(true, false)), U::LIVE, 0));
        assert(is(s.next(120, 0, live(true, true)), U::LIVE, 1));
    }

    {   // Down before up, whatever the turn says.
        U s;
        s.reset(0);
        // A's turn, but A raises and B lowers: B.
        assert(is(s.next(5, 0, live(true, true, true, false)), U::LIVE, 1));
        assert(is(s.next(10, 0, live(true, false, true, false)), U::LIVE, 0));
        s.healthRan(100);
        // A wrote last, so it is B's turn -- but B raises and A lowers: A.
        assert(is(s.next(110, 0, live(true, true, false, true)), U::LIVE, 0));
        assert(is(s.next(115, 0, live(false, true, false, true)), U::LIVE, 1));
        // A lowering write still in its gap does not hold a raise back.
        U t;
        t.reset(0);
        assert(is(t.next(5, 0, live(true, false)), U::LIVE, 0));
        assert(is(t.next(10, 0, live(true, true, false, true)), U::LIVE, 1));
    }

    {   // Live writes go before a due health step, and MSCNT goes last of all.
        U s;
        s.reset(0);
        U::Request r = live(true, false);
        r.mscnt = true;
        assert(is(s.next(125, 0, r), U::LIVE, 0));
        assert(is(s.next(130, 0, r), U::HEALTH));     // A is in its gap now
        assert(is(s.next(135, 0, r), U::MSCNT));
        U::Request m;
        m.mscnt = true;
        assert(is(s.next(140, 0, m), U::MSCNT));
        assert(s.runs(U::LIVE) == 1 && s.runs(U::HEALTH) == 1 && s.runs(U::MSCNT) == 2);
    }

    {   // Over budget, nothing runs -- counted only when something was due.
        U s;
        s.reset(0);
        assert(s.next(5, U::BUDGET_US + 1, U::Request()).group == U::NONE && !s.deferred());
        assert(s.next(10, U::BUDGET_US + 1, live(true, false)).group == U::NONE && s.deferred() == 1);
        assert(is(s.next(15, U::BUDGET_US, live(true, false)), U::LIVE, 0));   // exactly 3 ms is within it
        U::Request m;
        m.mscnt = true;
        assert(s.next(20, U::BUDGET_US + 1, m).group == U::NONE && s.deferred() == 2);
        // A due health step waits for the budget...
        for (uint32_t t = 125; t < 175; t += TICK) {
            assert(s.next(t, 10000, U::Request()).group == U::NONE);
        }
        // ...until it is 50 ms late, when it runs anyway.
        assert(is(s.next(175, 10000, U::Request()), U::HEALTH) && s.forced() == 1);
        assert(s.deferred() == 2 + 10);
        s.resetStats();
        assert(!s.deferred() && !s.forced() && !s.runs(U::HEALTH));
    }

    {   // 50 ms late, health goes before a write that could go too.
        U s;
        s.reset(0);
        assert(is(s.next(5, 0, live(true, true)), U::LIVE, 0));
        assert(is(s.next(10, 0, live(true, true)), U::LIVE, 1));
        for (uint32_t t = 15; t < 105; t += TICK) assert(s.next(t, 0, live(true, true)).group == U::NONE);
        for (uint32_t t = 105; t < 175; t += TICK) assert(s.next(t, U::BUDGET_US + 1, live(true, true)).group == U::NONE);
        assert(is(s.next(175, 0, live(true, true)), U::HEALTH) && s.forced() == 1);
        assert(is(s.next(180, 0, live(true, true)), U::LIVE, 0));
        assert(is(s.next(185, 0, live(true, true)), U::LIVE, 1));
    }

    {   // healthDue()/healthRan(): the calibration keeps the cadence by hand.
        U s;
        s.reset(0);
        assert(!s.healthDue(124) && s.healthDue(125));
        s.healthRan(130);
        assert(!s.healthDue(254) && s.healthDue(255));
        assert(s.next(250, 0, U::Request()).group == U::NONE);
        assert(is(s.next(255, 0, U::Request()), U::HEALTH));
    }

    {   // Across the 2^32 ms wrap: the gap, the cadence and the deferral limit.
        const uint32_t t0 = 0xFFFFFFFFu - 60;
        U s;
        s.reset(t0);
        assert(is(s.next(t0 + 5, 0, live(true, false)), U::LIVE, 0));
        assert(s.next(t0 + 100, 0, live(true, false)).group == U::NONE);
        assert(is(s.next(t0 + 105, 0, live(true, false)), U::LIVE, 0));   // after the wrap
        assert(s.next(t0 + 124, 20000, U::Request()).group == U::NONE);
        assert(s.next(t0 + 170, 20000, U::Request()).group == U::NONE);
        assert(is(s.next(t0 + 175, 20000, U::Request()), U::HEALTH));
    }

    {   // Neither wheel starves: both always pending, raising or lowering at
        // random, the budget always fine. Each is written within its gap plus two
        // ticks (one for the other wheel, one for a health step), and health
        // keeps its cadence to within the 50 ms.
        uint32_t seed = 3;
        auto rnd = [&seed](uint32_t n) {
            seed = seed * 1664525u + 1013904223u;
            return (seed >> 8) % n;
        };
        U s;
        s.reset(0);
        uint32_t lastWrite[2] = {0, 0}, lastHealth = 0;
        for (uint32_t t = TICK; t <= 600000; t += TICK) {
            const U::Choice c = s.next(t, 0, live(true, true, rnd(2), rnd(2)));
            if (c.group == U::LIVE) lastWrite[c.wheel] = t;
            if (c.group == U::HEALTH) lastHealth = t;
            for (uint32_t w : lastWrite) assert(t - w <= U::WRITE_GAP_MS + 2 * TICK);
            assert(t - lastHealth <= U::HEALTH_MS + U::HEALTH_DEFER_MS);
        }
        assert(s.runs(U::LIVE) > 2 * 5000 && s.runs(U::HEALTH) > 4000);
    }

    {   // Invariants under arbitrary input, late ticks and a busy budget included:
        // one group a tick; each wheel written at least 100 ms apart; nothing
        // but health past the budget; health never left more than 50 ms late;
        // a raise going first only when the other wheel's write is a raise too
        // or has to wait.
        uint32_t seed = 11;
        auto rnd = [&seed](uint32_t n) {
            seed = seed * 1664525u + 1013904223u;
            return (seed >> 8) % n;
        };
        U s;
        uint32_t now = 0xFFF00000u;   // wraps part way through
        s.reset(now);
        uint32_t lastHealth = now, lastWrite[2] = {0, 0};
        bool wrote[2] = {false, false}, pending[2] = {false, false};
        for (int i = 0; i < 400000; i++) {
            now += TICK + (rnd(20) == 0 ? rnd(4) : 0);   // mostly on time, sometimes late
            U::Request r;
            for (int w = 0; w < 2; w++) {
                if (rnd(50) == 0) pending[w] = !pending[w];
                r.live[w] = pending[w];
                r.raise[w] = rnd(3) == 0;
            }
            r.mscnt = rnd(4) == 0;
            const uint32_t servo = rnd(10) == 0 ? U::BUDGET_US + 1 + rnd(3000) : rnd(U::BUDGET_US + 1);
            const U::Choice c = s.next(now, servo, r);
            assert(c.group < U::NGROUPS && c.wheel < 2);
            if (c.group == U::HEALTH) lastHealth = now;
            else assert((int32_t)(now - lastHealth) < (int32_t)(U::HEALTH_MS + U::HEALTH_DEFER_MS));
            if (c.group == U::LIVE || c.group == U::MSCNT) assert(servo <= U::BUDGET_US);
            if (c.group == U::MSCNT) assert(r.mscnt);
            if (c.group == U::LIVE) {
                const int w = c.wheel, o = 1 - w;
                assert(r.live[w]);
                assert(!wrote[w] || now - lastWrite[w] >= U::WRITE_GAP_MS);
                const bool otherReady = r.live[o] && (!wrote[o] || now - lastWrite[o] >= U::WRITE_GAP_MS);
                if (r.raise[w] && otherReady) assert(r.raise[o]);
                wrote[w] = true;
                lastWrite[w] = now;
            }
        }
        // forced() stays 0 here: a 10% budget miss almost never puts off ten
        // ticks in a row. The overdue path has its own checks above.
        assert(s.runs(U::LIVE) && s.runs(U::HEALTH) && s.runs(U::MSCNT) && s.deferred());
    }

    puts("PASS: uart slot: health every 125 ms, live writes first with a 100 ms gap per wheel, alternation, "
         "down before up, MSCNT last, 3 ms budget, health never > 50 ms late, no starvation, 2^32 wrap, "
         "randomized invariants");
    return 0;
}
