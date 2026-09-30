#undef NDEBUG   // these asserts are the test
#include <cassert>
#include <cstdio>
#include <initializer_list>
#include "BoostPolicy.h"

using BP = BoostPolicy;

// One wheel as the drive runs it: update() once per 5 ms tick.
struct Wheel {
    BP p;
    BP::Inputs in;
    BP::Output o;

    explicit Wheel(const BP::Config &c, uint32_t t0 = 1000) {
        p.configure(c);
        p.reset(t0);
        in.nowMs = t0;
        in.energised = true;
        o = p.update(in);
    }
    uint32_t now() const { return in.nowMs; }
    void tick(uint32_t ms = 5) {
        in.nowMs += ms;
        o = p.update(in);
    }
    void run(uint32_t ms) {
        for (uint32_t t = 0; t < ms; t += 5) tick();
    }
    void request(BP::Reason r, uint32_t ms) { p.request(r, in.nowMs, ms); }
    // Ticks until done(o); the milliseconds that took.
    template <typename F> uint32_t until(F done, uint32_t most = 60000) {
        const uint32_t t0 = in.nowMs;
        while (!done(o)) {
            assert(in.nowMs - t0 < most);
            tick();
        }
        return in.nowMs - t0;
    }
};

static bool is(const BP::Output &o, uint8_t run, uint8_t hold) { return o.run == run && o.hold == hold; }
static bool notBoosting(const BP::Output &o) { return !o.boosting; }
static bool runAtBase(const BP::Output &o) { return o.run == 20; }
static bool holdAtBase(const BP::Output &o) { return o.hold == 9; }

int main() {
    {   // Nothing asked for: base.
        Wheel w({20, 9, 31, 1500});
        w.run(2000);
        assert(is(w.o, 20, 9) && !w.o.boosting && !w.o.reasons && !w.o.limitedBy);
    }

    {   // MANUAL: up in the same tick; after expiry one CS per 100 ms, run and hold each.
        Wheel w({26, 9, 31, 0});
        w.request(BP::MANUAL, 1000);
        w.tick(0);
        assert(is(w.o, 31, 31) && w.o.boosting && w.o.reasons == BP::MANUAL);
        w.run(995);
        assert(is(w.o, 31, 31) && w.o.boosting);
        w.tick();   // the expiry: the boost is over, the current hasn't moved yet
        assert(is(w.o, 31, 31) && !w.o.boosting && !w.o.reasons);
        const uint32_t end = w.now();
        uint32_t runAt[32] = {}, holdAt[32] = {};
        uint8_t r = 31, h = 31;
        while (r > 26 || h > 9) {
            w.tick();
            assert(w.now() - end <= 3000);
            if (w.o.run != r) {
                assert(w.o.run == r - 1);
                r = w.o.run;
                runAt[r] = w.now() - end;
            }
            if (w.o.hold != h) {
                assert(w.o.hold == h - 1);
                h = w.o.hold;
                holdAt[h] = w.now() - end;
            }
        }
        for (int cs = 30; cs >= 26; cs--) assert(runAt[cs] == (31u - cs) * 100);
        for (int cs = 30; cs >= 9; cs--) assert(holdAt[cs] == (31u - cs) * 100);
        assert(runAt[26] == 500 && holdAt[9] == 2200);   // the plan's 0.5 s and 2.2 s
        w.run(1000);
        assert(is(w.o, 26, 9));
    }

    {   // A slow, uneven caller doesn't stretch the ramp: steps stay on the 100 ms grid.
        Wheel w({20, 9, 31, 0});
        w.request(BP::MANUAL, 100);
        w.tick(0);
        while (w.o.boosting) w.tick(40);
        const uint32_t end = w.now();
        while (w.o.hold > 9) w.tick(40);
        assert(w.now() - end >= 2200 && w.now() - end < 2240);   // not 22 x 120 ms
    }

    {   // Renewal extends and never shortens; cancel and a zero duration end it.
        Wheel w({20, 9, 31, 0});
        w.request(BP::MANUAL, 300);
        w.run(200);
        w.request(BP::MANUAL, 300);   // now 500 ms after the first request
        w.run(295);
        assert(w.o.boosting);
        w.tick();
        assert(!w.o.boosting && !w.o.reasons);
        w.request(BP::MANUAL, 1000);
        w.tick();
        w.request(BP::MANUAL, 10);    // a shorter renewal
        w.run(500);
        assert(w.o.boosting);         // still on the 1000
        w.p.cancel(BP::MANUAL);
        w.tick();
        assert(!w.o.boosting && !w.o.reasons && is(w.o, 31, 31));   // and down the ramp from here
        w.request(BP::MANUAL, 1000);
        w.tick();
        assert(w.o.boosting);
        w.request(BP::MANUAL, 0);
        w.tick();
        assert(!w.o.boosting && !w.o.reasons);
        w.request(BP::MANUAL, 1000);
        w.request(BP::RECOVERY, 1000);
        w.p.cancel(BP::MANUAL);       // one reason ending leaves the others
        w.tick();
        assert(w.o.boosting && w.o.reasons == BP::RECOVERY);
    }

    {   // START needs a standstill of at least 500 ms, from reset() or from the last stop.
        Wheel w({20, 9, 31, 1500});
        w.run(490);
        w.in.moving = true;
        w.tick();                     // 495 ms after reset: too soon
        assert(!w.o.reasons && is(w.o, 20, 9));
        w.run(1000);
        w.in.moving = false;
        w.tick();                     // stopped...
        w.run(490);
        w.in.moving = true;
        w.tick();                     // ...for 495 ms: the same move
        assert(!w.o.reasons);
        w.run(500);
        w.in.moving = false;          // a reversal through zero: one tick at rest
        w.tick();
        w.in.moving = true;
        w.tick();
        assert(!w.o.reasons);
        w.in.moving = false;
        w.tick();
        w.run(495);
        w.in.moving = true;
        w.tick();                     // at rest exactly 500 ms
        assert(w.o.reasons == BP::START && w.o.boosting && is(w.o, 31, 31));
        w.run(1495);
        assert(w.o.boosting);
        w.tick();                     // START lasts startMs
        assert(!w.o.boosting && !w.o.reasons);
        w.run(5000);                  // still moving: no second START
        assert(!w.o.reasons && is(w.o, 20, 9));
    }

    {   // startMs 0 disables START, and turning it off ends one in progress.
        Wheel w({20, 9, 31, 0});
        w.run(2000);
        w.in.moving = true;
        w.tick();
        assert(!w.o.reasons && is(w.o, 20, 9));
        Wheel v({20, 9, 31, 1500});
        v.run(600);
        v.in.moving = true;
        v.tick();
        assert(v.o.reasons == BP::START);
        v.p.configure({20, 9, 31, 0});
        v.tick();
        assert(!v.o.reasons && !v.o.boosting);
    }

    {   // Heat, supply and derate each refuse a boost, and say so.
        Wheel w({20, 9, 31, 0});
        w.in.heatLimited = w.in.supplyInhibit = true;
        w.in.derate = 1;
        w.tick();
        assert(!w.o.limitedBy);       // nothing asked, nothing refused
        w.request(BP::MANUAL, 60000);
        w.tick();
        assert(!w.o.boosting && w.o.reasons == BP::MANUAL && is(w.o, 20, 9) &&
               w.o.limitedBy == (BP::LIMIT_HEAT | BP::LIMIT_SUPPLY | BP::LIMIT_DERATE));
        w.in.supplyInhibit = false;
        w.in.derate = 0;
        w.tick();
        assert(!w.o.boosting && w.o.limitedBy == BP::LIMIT_HEAT);
        w.in.heatLimited = false;
        w.tick();
        assert(w.o.boosting && !w.o.limitedBy && is(w.o, 31, 31));
        struct { bool heat, supply; uint8_t derate, bit; } cases[] = {
            {true, false, 0, BP::LIMIT_HEAT}, {false, true, 0, BP::LIMIT_SUPPLY},
            {false, false, 1, BP::LIMIT_DERATE}, {false, false, 3, BP::LIMIT_DERATE}};
        for (auto &c : cases) {
            w.in.heatLimited = c.heat;
            w.in.supplyInhibit = c.supply;
            w.in.derate = c.derate;
            w.tick();                 // a boost in progress ends...
            assert(!w.o.boosting && w.o.limitedBy == c.bit && is(w.o, 31, 31));
            w.run(100);               // ...down the usual ramp
            assert(is(w.o, 30, 30));
            w.in.heatLimited = w.in.supplyInhibit = false;
            w.in.derate = 0;
            w.tick();                 // and comes straight back
            assert(w.o.boosting && is(w.o, 31, 31));
        }
    }

    {   // Derate 2 and 3 cut base run and hold, and hold stays at or below run.
        assert(BP::derated(20, 0) == 20 && BP::derated(20, 1) == 20);
        assert(BP::derated(20, 2) == 14 && BP::derated(20, 3) == 9);   // 1160 -> 829 / 552 mA
        assert(BP::derated(9, 2) == 6 && BP::derated(9, 3) == 4);
        assert(BP::derated(26, 2) == 19 && BP::derated(26, 3) == 12);
        assert(BP::derated(31, 2) == 23 && BP::derated(31, 3) == 15);
        assert(BP::derated(0, 3) == 0 && BP::derated(1, 3) == 0 && BP::derated(20, 7) == 9);
        for (int run = 0; run <= 31; run++)
            for (int hold = 0; hold <= run; hold++)
                for (uint8_t lvl = 0; lvl <= 4; lvl++)
                    assert(BP::derated(hold, lvl) <= BP::derated(run, lvl) && BP::derated(run, lvl) <= run);
        Wheel w({20, 9, 31, 0});
        w.in.derate = 2;
        w.run(2000);
        assert(is(w.o, 14, 6) && !w.o.limitedBy);
        w.in.derate = 3;
        w.run(2000);
        assert(is(w.o, 9, 4));
        w.in.derate = 0;
        w.tick();
        assert(is(w.o, 20, 9));       // back up at once
        Wheel e({20, 20, 31, 0});     // hold_ma = run_ma stays pinned to run
        e.in.derate = 3;
        e.run(2000);
        assert(is(e.o, 9, 9));
        Wheel b({20, 9, 31, 0});      // from a boost into derate 2
        b.request(BP::MANUAL, 60000);
        b.tick();
        assert(is(b.o, 31, 31));
        b.in.derate = 2;
        for (int i = 0; i < 1000; i++) {
            b.tick();
            assert(b.o.hold <= b.o.run);
        }
        assert(is(b.o, 14, 6) && b.o.limitedBy == BP::LIMIT_DERATE);
    }

    {   // Not energised: base at once, and the next enable starts from base.
        Wheel w({20, 9, 31, 0});
        w.request(BP::MANUAL, 1000);
        w.tick();
        assert(is(w.o, 31, 31));
        w.in.energised = false;
        w.tick();
        assert(is(w.o, 20, 9) && !w.o.boosting && w.o.reasons == BP::MANUAL && !w.o.limitedBy);
        w.in.energised = true;
        w.tick();
        assert(is(w.o, 31, 31) && w.o.boosting);   // still wanted: straight back up
        w.p.cancel(BP::MANUAL);
        w.tick();
        w.run(300);
        assert(is(w.o, 28, 28));                   // part way down...
        w.in.energised = false;
        w.tick();
        w.in.energised = true;
        w.tick();
        assert(is(w.o, 20, 9));                    // ...and re-enabled at base, not 28
        w.in.energised = false;
        w.tick();
        w.in.derate = 2;                           // hot at enable: up at base, then down
        w.in.energised = true;
        w.tick();
        assert(is(w.o, 20, 9));
        w.run(100);
        assert(is(w.o, 19, 8));
    }

    {   // Boost at or below base run is boost off.
        for (uint8_t cs : {20, 5, 0}) {
            Wheel w({20, 9, cs, 0});
            w.request(BP::MANUAL, 1000);
            w.tick();
            assert(!w.o.boosting && w.o.limitedBy == BP::LIMIT_OFF && is(w.o, 20, 9));
        }
        Wheel w({20, 9, 21, 0});
        w.request(BP::MANUAL, 1000);
        w.tick();
        assert(w.o.boosting && is(w.o, 21, 21));
        w.p.configure({40, 35, 50, 0});            // pulled into range, not refused
        const BP::Config &c = w.p.config();
        assert(c.baseRun == 31 && c.baseHold == 31 && c.boostCs == 31);
        w.tick();
        assert(!w.o.boosting && w.o.limitedBy == BP::LIMIT_OFF && is(w.o, 31, 31));
        w.p.configure({20, 25, 31, 0});
        assert(w.p.config().baseHold == 20);
    }

    {   // Across the 2^32 ms wrap: expiry, ramp and START.
        Wheel w({20, 9, 31, 1500}, 0xFFFFFFFFu - 250);
        w.request(BP::MANUAL, 500);                // expires at 249, after the wrap
        w.tick(0);
        assert(w.o.boosting);
        assert(w.until(notBoosting) == 500 && w.now() == 249);
        assert(w.until(runAtBase) == 1100);
        assert(w.until(holdAtBase) == 1100);       // 2.2 s after the expiry
        Wheel s({20, 9, 31, 1500}, 0xFFFFFF00u);   // 256 ms before the wrap
        s.run(600);
        s.in.moving = true;
        s.tick();
        assert(s.o.reasons == BP::START);
        Wheel q({20, 9, 31, 1500}, 0xFFFFFF00u);
        q.run(400);                                // across the wrap, but too short
        q.in.moving = true;
        q.tick();
        assert(!q.o.reasons);
        Wheel l({20, 9, 31, 1500});                // parked past the int32 window (~25 days)
        l.run(600);
        l.tick(3000000000u);
        l.in.moving = true;
        l.tick();
        assert(l.o.reasons == BP::START);
    }

    // RECOVERY, LOAD and an explicit START behave exactly like MANUAL.
    for (BP::Reason r : {BP::MANUAL, BP::START, BP::RECOVERY, BP::LOAD}) {
        Wheel w({20, 9, 31, 0});
        w.request(r, 250);
        w.tick(0);
        assert(w.o.boosting && w.o.reasons == r && is(w.o, 31, 31));
        assert(w.until(notBoosting) == 250 && !w.o.reasons);
        assert(w.until(runAtBase) == 1100);
        assert(w.until(holdAtBase) == 1100);
    }

    {   // Invariants under arbitrary input, across the wrap: the grant rule exactly,
        // hold <= run, and every step down while energised is one CS at least
        // 100 ms after the last on that channel.
        uint32_t seed = 7;
        auto rnd = [&seed](uint32_t n) {
            seed = seed * 1664525u + 1013904223u;
            return (seed >> 8) % n;
        };
        BP p;
        uint32_t now = 0xFFF00000u;
        p.reset(now);
        BP::Inputs in;
        in.nowMs = now;
        in.energised = true;
        BP::Output prev = p.update(in);
        bool prevOn = true;
        uint32_t downRun = now - 1000, downHold = now - 1000;
        for (int i = 0; i < 400000; i++) {
            now += 5;
            in.nowMs = now;
            switch (rnd(100)) {
                case 0: in.energised = !in.energised; break;
                case 1: case 2: in.moving = !in.moving; break;
                case 3: in.heatLimited = !in.heatLimited; break;
                case 4: in.supplyInhibit = !in.supplyInhibit; break;
                case 5: in.derate = (uint8_t)rnd(4); break;
                case 6: case 7: p.request((BP::Reason)(1u << rnd(4)), now, rnd(3000)); break;
                case 8: p.cancel((BP::Reason)(1u << rnd(4))); break;
                case 9:
                    if (!rnd(10)) {
                        uint8_t run = (uint8_t)rnd(32);
                        p.configure({run, (uint8_t)rnd(run + 1u), (uint8_t)rnd(32), rnd(2) ? 1500u : 0u});
                    }
                    break;
                default: break;
            }
            const BP::Output o = p.update(in);
            const BP::Config &c = p.config();
            const bool off = c.boostCs <= c.baseRun;
            const uint8_t lim = (uint8_t)((in.heatLimited ? BP::LIMIT_HEAT : 0) |
                                          (in.derate ? BP::LIMIT_DERATE : 0) |
                                          (in.supplyInhibit ? BP::LIMIT_SUPPLY : 0) |
                                          (off ? BP::LIMIT_OFF : 0));
            assert(o.boosting == (o.reasons && in.energised && !lim));
            assert(o.limitedBy == (o.reasons && in.energised ? lim : 0));
            assert(o.hold <= o.run && o.run <= 31);
            if (!in.energised) {
                assert(o.run == c.baseRun && o.hold == c.baseHold);
            } else {
                // Never below the target, straight up to it from below; above it
                // only on the way down (e.g. boostCs lowered mid-boost).
                uint8_t tr = o.boosting ? c.boostCs : BP::derated(c.baseRun, in.derate);
                uint8_t th = o.boosting ? c.boostCs : BP::derated(c.baseHold, in.derate);
                if (th > tr) th = tr;
                assert(o.run >= tr && o.hold >= th);
                if (prev.run <= tr) assert(o.run == tr);
                if (prev.hold <= th) assert(o.hold == th);
            }
            if (in.energised && prevOn) {
                if (o.run < prev.run) {
                    assert(o.run == prev.run - 1 && now - downRun >= 100);
                    downRun = now;
                }
                if (o.hold < prev.hold) {
                    assert(o.hold == prev.hold - 1 && now - downHold >= 100);
                    downHold = now;
                }
            }
            prev = o;
            prevOn = in.energised;
        }
    }

    // --- OtpwDerate ---

    // The plan's bench check, `debug otpw A 40` seen by the 500 ms health poll:
    // levels 1/2/3 at 0/10/20 s, back down at 70/100/130 s. Once plainly, once
    // straddling the wrap.
    for (uint32_t t0 : {1000u, 0xFFFFFFFFu - 20000}) {
        OtpwDerate d;
        uint32_t when[8];
        uint8_t lvl[8], last = d.level();
        int n = 0;
        for (uint32_t t = 0; t <= 150000; t += 500) {
            uint8_t l = d.sample(t < 40000, t0 + t);
            if (l == last) continue;
            assert(n < 8);
            when[n] = t;
            lvl[n++] = last = l;
        }
        const uint32_t wantWhen[] = {0, 10000, 20000, 70000, 100000, 130000};
        const uint8_t wantLvl[] = {1, 2, 3, 2, 1, 0};
        assert(n == 6);
        for (int i = 0; i < 6; i++) assert(when[i] == wantWhen[i] && lvl[i] == wantLvl[i]);
        assert(d.events() == 1);
    }
    {   // Sampled every 5 ms tick instead: the same times.
        OtpwDerate d;
        for (uint32_t t = 0; t < 30000; t += 5) {
            uint8_t l = d.sample(true, t);
            assert(l == (t < 10000 ? 1 : t < 20000 ? 2 : 3));
        }
    }
    {   // Flapping on alternate samples still escalates on schedule, never restores,
        // and is one episode.
        OtpwDerate d;
        for (uint32_t t = 0; t <= 60000; t += 500) {
            uint8_t l = d.sample((t / 500) % 2 == 0, t);
            assert(l == (t < 10000 ? 1 : t < 20000 ? 2 : 3));
        }
        assert(d.events() == 1);
        // One OTPW sample every 20 s. Restarting the step clock at each new
        // OTPW would pin this at level 1 forever; it reaches 3.
        OtpwDerate s;
        for (uint32_t t = 0; t <= 100000; t += 500) {
            uint8_t l = s.sample(t % 20000 == 0, t);
            assert(l == (t < 20000 ? 1 : t < 40000 ? 2 : 3));
        }
        // Clear from 100.5 s: a level back every 30 s.
        for (uint32_t t = 100500; t <= 200000; t += 500) {
            uint8_t l = s.sample(false, t);
            assert(l == (t < 130500 ? 3 : t < 160500 ? 2 : t < 190500 ? 1 : 0));
        }
        assert(s.events() == 1);
        assert(s.sample(true, 200500) == 1 && s.events() == 2);   // a new episode
    }
    {   // reset(): OTPW already up at enable starts at 2, clocks from the next sample.
        OtpwDerate d;
        d.sample(true, 0);                        // one episode on record
        d.reset(2);
        assert(d.level() == 2);
        assert(d.sample(true, 50000) == 2);       // long after the last change, but the clock restarted
        assert(d.sample(true, 59999) == 2);
        assert(d.sample(true, 60000) == 3);
        d.reset(2);
        assert(d.sample(false, 70000) == 2);
        assert(d.sample(false, 99999) == 2 && d.sample(false, 100000) == 1);
        assert(d.sample(false, 130000) == 0);
        d.reset(9);
        assert(d.level() == 3);
        d.reset();
        assert(d.level() == 0 && d.events() == 1);   // episodes are history
    }

    puts("PASS: boost reasons, instant up and 100 ms step-down on run and hold, renew/cancel, "
         "START after 500 ms still, heat/supply/derate/off limits, derate targets, de-energised "
         "base, 2^32 wrap, grant invariants; OTPW derate escalation, restore, flapping, events");
    return 0;
}
