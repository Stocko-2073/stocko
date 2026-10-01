#include <cassert>
#include <cmath>
#include <cstdarg>
#include <cstdio>
#include <cstring>
#include <initializer_list>
#include "Recovery.h"

static const float DT = 0.005f;
static const double SPC = 200.0 * 8.0 * 40.0 / 12.0 / 4096.0;   // microsteps per count
typedef RecoveryWheelOut W;

// Synthetic samples: each wheel's command, rotor and encoder are whatever the
// test says, and a minimal servo obeys Recovery's holds between ticks so a lock
// can complete. Trips are edges: they last the one tick they are set for.
struct Bench {
    Recovery rec;
    RecoveryIn in = {};
    double pos[2] = {0, 0};             // encoder, counts
    bool stalled[2] = {false, false};   // rotor stays where the test put it
    float slewCps = 41;                 // 2 turns/s^2 over a 5 ms tick

    explicit Bench(const RecoveryConfig &c = RecoveryConfig()) {
        rec.configure(c);
        for (int i = 0; i < 2; i++) {
            RecoveryWheelIn &w = in.w[i];
            w.goalCps = w.cmdCps = w.stall.rotorCps = 1000;   // ~0.24 turns/s
            w.velMode = w.encOk = true;
        }
        in.cmdLive = in.eligible = true;
        in.nowMs = 1000;
    }

    uint32_t now() const { return in.nowMs; }   // the next tick's time

    RecoveryOut tick() {
        RecoveryOut o = rec.update(in);
        for (int i = 0; i < 2; i++) {
            RecoveryWheelIn &w = in.w[i];
            const RecoveryWheelOut &h = o.w[i];
            w.stall.trip = 0;
            if (h.hold == W::HOLD_SNAP) {
                w.cmdCps = h.holdCps;
            } else {
                float target = h.hold == W::HOLD_SLEW ? h.holdCps : w.goalCps;
                w.cmdCps += fmaxf(-slewCps, fminf(slewCps, target - w.cmdCps));
            }
            if (!stalled[i]) w.stall.rotorCps = w.cmdCps;
            if (h.resync) w.rawLag = 0;
            pos[i] += w.stall.rotorCps * DT;
            w.encCounts = (int32_t)lround(pos[i]);
        }
        in.nowMs += 5;
        return o;
    }

    RecoveryOut trip(int i, float rotorCps, int8_t kind = +1) {
        in.w[i].stall.trip = kind;
        in.w[i].stall.rotorCps = rotorCps;
        return tick();
    }

    // Tick until `e`, insisting nothing else happens on the way.
    RecoveryOut until(RecoveryEvent e, int maxTicks = 20000) {
        for (int n = 0; n < maxTicks; n++) {
            RecoveryOut o = tick();
            if (o.event == e) return o;
            if (o.event != REV_NONE) {
                fprintf(stderr, "waiting for '%s', got '%s' at %u ms\n", Recovery::name(e),
                        Recovery::name(o.event), (unsigned)(in.nowMs - 5));
            }
            assert(o.event == REV_NONE);
        }
        assert(!"the event never came");
        return RecoveryOut();
    }
};

static bool near(float a, float b) { return fabsf(a - b) < 0.01f; }

// --- the fake servo recoveryTick drives -----------------------------------

static char g_log[4096];
static void note(const char *fmt, ...) {
    size_t n = strlen(g_log);
    va_list ap;
    va_start(ap, fmt);
    vsnprintf(g_log + n, sizeof g_log - n, fmt, ap);
    va_end(ap);
}

// What recoveryTick touches, around a toy velocity loop: the command slews
// toward the goal or the hold, a snap lands at the next update() as the real
// one must, and the shaft follows the command unless it is stalled.
struct FakeServo {
    enum Fault : uint8_t { FAULT_NONE = 0, FAULT_SLIP };
    int id = 0;
    double cmd = 0, shaft = 0;
    int32_t enc = 0;
    uint32_t epoch = 0;
    bool encOk = true, vel = true, stalled = false;
    float slipFrac = 0;   // share of the command the shaft loses while slipping
    float goal = 1000, vcmd = 1000, hold = 0;
    bool held = false, snapNext = false;
    uint8_t flt = 0;

    double commandedSteps() const { return cmd; }
    float slipRawSteps() const { return (float)(cmd - enc * SPC); }
    int32_t positionCounts() const { return enc; }
    uint32_t resyncCount() const { return epoch; }
    bool encoderOk() const { return encOk; }
    bool velocityMode() const { return vel && !flt; }
    float goalCps() const { return goal; }
    float commandedCps() const { return vcmd; }
    uint8_t fault() const { return flt; }
    bool holding() const { return held; }
    void holdVelocity(float cps, bool snap) {
        note("%d:%s ", id, snap ? "snap" : "slew");
        if (flt) return;
        held = true;
        hold = cps;
        if (snap) snapNext = true;
    }
    void releaseHold() { note("%d:release ", id); held = false; }
    void resyncSlip() { note("%d:resync ", id); cmd = enc * SPC; epoch++; }
    void raiseFault(Fault f) { note("%d:fault ", id); flt = f; held = false; vcmd = 0; }
    void update(float dt) {
        if (flt) return;
        if (snapNext) {
            vcmd = hold;
            snapNext = false;
        } else {
            float target = held ? hold : goal;
            vcmd += fmaxf(-41.0f, fminf(41.0f, target - vcmd));
        }
        cmd += vcmd * SPC * dt;
        if (!stalled) shaft += vcmd * (1.0f - slipFrac) * dt;
        enc = (int32_t)lround(shaft);
    }
};

struct Robot {
    FakeServo a, b;
    FakeServo *s[2] = {&a, &b};
    StallDetector det[2];
    StallSample st[2];
    Recovery rec;
    uint32_t now = 0;
    bool live = true;

    explicit Robot(const RecoveryConfig &c = RecoveryConfig()) {
        a.id = 0;
        b.id = 1;
        rec.configure(c);
        for (StallDetector &d : det) d.configure(StallConfig());
    }
    RecoveryOut step() {
        g_log[0] = 0;
        a.update(DT);
        b.update(DT);
        auto boost = [](uint8_t i, uint32_t ms) { note("%d:boost%u ", i, (unsigned)ms); };
        RecoveryOut o = recoveryTick(rec, det, st, s, live, true, now, DT, boost);
        now += 5;
        return o;
    }
    RecoveryOut until(RecoveryEvent e) {
        for (int n = 0; n < 20000; n++) {
            RecoveryOut o = step();
            if (o.event == e) return o;
            if (o.event != REV_NONE) {
                fprintf(stderr, "waiting for '%s', got '%s' at %u ms\n", Recovery::name(e),
                        Recovery::name(o.event), (unsigned)(now - 5));
            }
            assert(o.event == REV_NONE);
        }
        assert(!"the event never came");
        return RecoveryOut();
    }
};

int main() {
    // --- freeze: k clamps, snap the tripped wheel, slew the partner by the same k ---
    {
        Bench b;
        RecoveryOut o = b.trip(0, -2000);   // rolling back twice as fast as it was driving
        assert(o.event == REV_ATTEMPT && o.wheel == 0 && o.k == -1.0f);
        assert(o.w[0].hold == W::HOLD_SNAP && o.w[0].holdCps == -1000);
        assert(o.w[1].hold == W::HOLD_SLEW && o.w[1].holdCps == -1000);
        assert(o.w[0].boostMs == 1700 && o.w[1].boostMs == 1700);   // lockMs + boostMs, both, this tick
        assert(!o.w[0].resync && !o.w[1].resync);
        assert(b.rec.state() == REC_LOCK && b.rec.attempt() == 1 && b.rec.involved() == 1);
    }
    {
        Bench b;
        b.in.w[1].goalCps = b.in.w[1].cmdCps = 600;
        RecoveryOut o = b.trip(0, 1500);
        assert(o.k == 1.0f && o.w[0].holdCps == 1000 && o.w[1].holdCps == 600);
    }
    {
        Bench b;
        b.in.w[0].cmdCps = 0.5f;   // under a count a second: no ratio to take
        RecoveryOut o = b.trip(0, 300);
        assert(o.k == 0 && o.w[0].hold == W::HOLD_SNAP && o.w[0].holdCps == 0 && o.w[1].holdCps == 0);
    }
    {
        Bench b;
        RecoveryOut o = b.trip(1, 350);
        assert(o.wheel == 1 && near(o.k, 0.35f));
        assert(o.w[1].hold == W::HOLD_SNAP && near(o.w[1].holdCps, 350));
        assert(o.w[0].hold == W::HOLD_SLEW && near(o.w[0].holdCps, 350));
    }
    {
        Bench b;   // a partner mid-reversal brakes to 0 rather than keep the arc the old way
        b.in.w[1].goalCps = -1000;                             // the stick has turned it round...
        b.in.w[1].cmdCps = b.in.w[1].stall.rotorCps = 600;    // ...and it is still braking forward
        RecoveryOut o = b.trip(0, 350);
        assert(o.event == REV_ATTEMPT && near(o.k, 0.35f));
        assert(o.w[0].hold == W::HOLD_SNAP && near(o.w[0].holdCps, 350));   // the tripped wheel as before
        assert(o.w[1].hold == W::HOLD_SLEW && o.w[1].holdCps == 0);
        float prev = b.in.w[1].cmdCps;
        for (;;) {
            o = b.tick();
            if (o.event == REV_LOCKED) break;
            assert(o.event == REV_NONE && o.w[1].hold == W::HOLD_SLEW && o.w[1].holdCps == 0);
            float c = b.in.w[1].cmdCps;
            assert(c >= 0 && c <= prev);   // the decel ramp down, never held the old way
            prev = c;
        }
        assert(prev == 0);   // stopped for the lock, not pushed the new way yet
        for (int i = 0; i < 30; i++) assert(b.tick().event == REV_NONE);
        assert(b.in.w[1].cmdCps == -1000);   // released, it carries on into the reversal
    }
    {
        Bench b;   // stopping is not reversing: a partner whose goal is 0 keeps the arc
        b.in.w[1].goalCps = 0;
        b.in.w[1].cmdCps = b.in.w[1].stall.rotorCps = 600;
        RecoveryOut o = b.trip(0, 350);
        assert(o.w[1].hold == W::HOLD_SLEW && near(o.w[1].holdCps, 0.35f * 600));
    }

    // --- lock: resync on the next tick, then lockMs once the partner has slewed down ---
    {
        Bench b;
        b.trip(0, 350);
        RecoveryOut o = b.tick();
        assert(o.event == REV_NONE && o.w[0].resync && o.w[1].resync);
        assert(o.w[0].hold == W::HOLD_SNAP && o.w[1].hold == W::HOLD_SLEW);   // holds are levels
        assert(o.w[0].boostMs == 0 && o.w[1].boostMs == 0);
        uint32_t t0 = b.now() - 5;
        o = b.until(REV_LOCKED);
        assert(b.now() - 5 - t0 == 200);
        assert(o.w[0].resync && o.w[1].resync);
        assert(o.w[0].hold == W::HOLD_NONE && o.w[1].hold == W::HOLD_NONE);
        assert(b.rec.state() == REC_RAMP && b.rec.attempt() == 1);
    }
    {
        Bench b;   // a partner still slewing holds the lock open past lockMs
        b.slewCps = 2;
        b.trip(0, 350);
        b.tick();
        uint32_t t0 = b.now() - 5;
        b.until(REV_LOCKED);
        assert(b.now() - 5 - t0 == 1200);   // lockMs + partnerWaitMs: then it is waived
    }

    // --- both on the same tick: one attempt, each snapped to its own rotor ---
    {
        Bench b;
        b.in.w[0].stall.trip = b.in.w[1].stall.trip = +1;
        b.in.w[0].stall.rotorCps = 300;
        b.in.w[1].stall.rotorCps = 500;
        RecoveryOut o = b.tick();
        assert(o.event == REV_ATTEMPT && b.rec.attempt() == 1 && b.rec.attempts() == 1);
        assert(b.rec.involved() == 3);
        assert(o.w[0].hold == W::HOLD_SNAP && near(o.w[0].holdCps, 300));
        assert(o.w[1].hold == W::HOLD_SNAP && near(o.w[1].holdCps, 500));
        b.tick();
        uint32_t t0 = b.now() - 5;
        b.until(REV_LOCKED);
        assert(b.now() - 5 - t0 == 200);
    }

    // --- a partner that trips during the lock joins the same attempt ---
    {
        Bench b;
        b.trip(0, 350);
        for (int i = 0; i < 6; i++) assert(b.tick().event == REV_NONE);
        float partnerCmd = b.in.w[1].cmdCps;
        assert(partnerCmd < 1000 && partnerCmd > 500);   // still slewing down
        RecoveryOut o = b.trip(1, 500);
        assert(o.event == REV_JOINED && o.wheel == 1);
        assert(b.rec.attempt() == 1 && b.rec.attempts() == 1 && b.rec.involved() == 3);
        assert(o.w[1].hold == W::HOLD_SNAP && near(o.w[1].holdCps, 500));
        assert(o.w[0].hold == W::HOLD_SNAP && near(o.w[0].holdCps, 350));
        assert(o.w[0].boostMs == 1700 && o.w[1].boostMs == 1700);
        o = b.tick();
        assert(o.w[0].resync && o.w[1].resync);   // the timer starts over from here
        uint32_t t0 = b.now() - 5;
        b.until(REV_LOCKED);
        assert(b.now() - 5 - t0 == 200);
    }

    // --- a failed lock re-freezes on the rotor as it is now, as the next attempt ---
    {
        Bench b;
        b.trip(0, 350);
        b.tick();
        b.tick();
        b.stalled[0] = true;
        b.in.w[0].stall.rotorCps = 200;
        b.in.w[0].rawLag = 41;
        RecoveryOut o = b.tick();
        assert(o.event == REV_LOCK_FAILED && o.wheel == 0);
        assert(b.rec.attempt() == 2 && b.rec.attempts() == 2 && b.rec.state() == REC_LOCK);
        assert(o.w[0].hold == W::HOLD_SNAP && near(o.w[0].holdCps, 200));
        assert(o.w[1].hold == W::HOLD_SLEW);
        assert(o.w[0].boostMs == 1700 && o.w[1].boostMs == 1700);
    }
    {
        Bench b;   // ...or when the rotor never comes to its hold
        b.trip(0, 350);
        b.stalled[0] = true;
        b.in.w[0].stall.rotorCps = 0;
        b.tick();
        uint32_t t0 = b.now() - 5;
        RecoveryOut o = b.until(REV_LOCK_FAILED);
        assert(b.now() - 5 - t0 == 1200 && b.rec.attempt() == 2);
        assert(o.w[0].holdCps == 0 && o.k == 0);
    }

    // --- a re-freeze measures k against the command the hold began from ---
    {
        Bench b;
        b.trip(0, 350);   // hold 350: k 0.35 of the 1000 it was asked for
        b.tick();         // the resync
        b.stalled[0] = true;
        b.in.w[0].stall.rotorCps = -700;   // rolling back, twice as fast as its hold
        b.in.w[0].rawLag = 41;
        RecoveryOut o = b.tick();
        // Against the hold that would have been k -2, clamped to -1: a hold of
        // -350 the rotor would leave behind. Against the 1000 it is -0.7.
        assert(o.event == REV_LOCK_FAILED && near(o.k, -0.7f));
        assert(near(o.w[0].holdCps, -700) && near(o.w[1].holdCps, -700));   // the partner: -0.7 of its 1000
        b.in.w[0].stall.rotorCps = -1500;  // faster backwards than it was ever asked forwards
        b.tick();
        b.in.w[0].rawLag = -45;
        o = b.tick();
        assert(o.event == REV_LOCK_FAILED && o.k == -1.0f && o.w[0].holdCps == -1000);   // the clamp still holds
    }

    // --- through the lock the snapped hold follows its rotor, the partner at the new k ---
    {
        Bench b;
        for (RecoveryWheelIn &w : b.in.w) w.stall.velValid = true;
        RecoveryOut o = b.trip(0, 600);
        assert(near(o.w[0].holdCps, 600) && near(o.w[1].holdCps, 600));
        b.stalled[0] = true;
        b.in.w[0].stall.velValid = false;   // the detector's ring restarts at the resync...
        b.in.w[0].stall.rotorCps = 0;       // ...and reads 0 until it has two reads
        b.tick();                           // the resync
        o = b.tick();
        assert(o.event == REV_NONE && near(o.w[0].holdCps, 600) && near(o.k, 0.6f));   // nothing to follow yet
        b.in.w[0].stall.velValid = true;
        for (float r : {300.0f, 100.0f, -50.0f, -200.0f}) {   // slowing, then rolling back
            b.in.w[0].stall.rotorCps = r;
            o = b.tick();
            assert(o.event == REV_NONE && o.w[0].hold == W::HOLD_SNAP && near(o.w[0].holdCps, r));
            assert(near(o.k, r / 1000) && o.w[1].hold == W::HOLD_SLEW && near(o.w[1].holdCps, r));
        }
        b.in.w[0].stall.rotorCps = -1500;   // never past what it was asked: the clamp, as at the freeze
        o = b.tick();
        assert(o.w[0].holdCps == -1000 && o.k == -1.0f && o.w[1].holdCps == -1000);
        b.in.w[0].stall.rotorCps = -200;    // settled: it locks there once the partner has slewed round
        uint32_t t0 = b.now();
        o = b.until(REV_LOCKED);
        assert(near(o.k, -0.2f) && b.now() - t0 < 1000);   // well inside the partner's wait: it got there
        assert(o.w[0].hold == W::HOLD_NONE && o.w[1].hold == W::HOLD_NONE && o.w[0].resync);
    }
    {
        Bench b;   // a rotor that stops dead is followed to a standstill and locks there, on time
        for (RecoveryWheelIn &w : b.in.w) w.stall.velValid = true;
        b.trip(0, 350);
        b.stalled[0] = true;
        b.in.w[0].stall.rotorCps = 0;
        b.tick();
        uint32_t t0 = b.now() - 5;
        b.until(REV_LOCKED);
        assert(b.now() - 5 - t0 == 200 && b.rec.attempt() == 1);
    }
    {
        Bench b;   // a braking partner stays at 0 through the follow and through a re-freeze,
        for (RecoveryWheelIn &w : b.in.w) w.stall.velValid = true;   // even once it has come to rest
        b.in.w[1].goalCps = -1000;
        b.in.w[1].cmdCps = b.in.w[1].stall.rotorCps = 600;
        RecoveryOut o = b.trip(0, 350);
        assert(o.w[1].holdCps == 0);
        b.tick();
        b.stalled[0] = true;
        b.in.w[0].stall.rotorCps = 200;
        for (int i = 0; i < 20; i++) {
            o = b.tick();
            assert(o.event == REV_NONE && o.w[1].holdCps == 0 && near(o.w[0].holdCps, 200));
        }
        assert(b.in.w[1].cmdCps == 0);   // braked to a stop: no longer looks like a reversal
        b.in.w[0].rawLag = 50;
        o = b.tick();
        assert(o.event == REV_LOCK_FAILED && o.w[1].hold == W::HOLD_SLEW && o.w[1].holdCps == 0);
    }

    // --- progress ends the episode and resets the count ---
    {
        Bench b;
        b.trip(0, 350);
        b.until(REV_LOCKED);
        double from = b.pos[0];
        RecoveryOut o = b.until(REV_RECOVERED);
        double moved = b.pos[0] - b.in.w[0].stall.rotorCps * DT - from;   // at the recovering tick
        assert(moved * SPC >= 1333 && moved * SPC < 1333 + 10);
        assert(o.w[0].hold == W::HOLD_NONE && o.w[0].boostMs == 0);
        assert(b.rec.state() == REC_IDLE && b.rec.attempt() == 0 && b.rec.involved() == 0);
        assert(b.rec.recoveries() == 1 && b.rec.giveups() == 0);
        o = b.trip(0, 350);
        assert(o.event == REV_ATTEMPT && b.rec.attempt() == 1 && b.rec.attempts() == 2);
    }
    {
        Bench b;   // a wheel whose goal is now zero has nothing left to prove
        b.trip(0, 350);
        b.until(REV_LOCKED);
        b.in.w[0].goalCps = 0;
        assert(b.tick().event == REV_RECOVERED);
    }

    // --- cancel: either goal reversing, stick released, not eligible, cancel(), settings ---
    {
        Bench b;   // the tripped wheel's goal turning round, during the lock
        b.trip(0, 350);
        b.tick();
        b.tick();
        b.in.w[0].goalCps = 0;   // merely stopping is not a reversal
        assert(b.tick().event == REV_NONE && b.rec.state() == REC_LOCK);
        b.in.w[0].goalCps = -1000;
        RecoveryOut o = b.tick();
        assert(o.event == REV_CANCELLED && o.wheel == 0);
        assert(o.w[0].hold == W::HOLD_NONE && o.w[1].hold == W::HOLD_NONE);
        assert(!o.w[0].fault && !o.w[1].fault);
        assert(b.rec.state() == REC_IDLE && b.rec.attempt() == 0);
    }
    {
        Bench b;   // ...and in the ramp
        b.trip(0, 350);
        b.until(REV_LOCKED);
        b.tick();
        b.in.w[0].goalCps = -500;
        assert(b.tick().event == REV_CANCELLED);
    }
    {
        Bench b;   // the partner alone turning round, during the lock: a spin turn is a new decision
        b.trip(0, 350);
        b.tick();
        b.tick();
        assert(b.rec.involved() == 1 && b.rec.state() == REC_LOCK);
        b.in.w[1].goalCps = 0;   // merely stopping is not a reversal
        assert(b.tick().event == REV_NONE && b.rec.state() == REC_LOCK);
        b.in.w[1].goalCps = -1000;
        RecoveryOut o = b.tick();
        assert(o.event == REV_CANCELLED && o.wheel == 1);   // names the wheel that turned round
        assert(o.w[0].hold == W::HOLD_NONE && o.w[1].hold == W::HOLD_NONE);   // the old way no longer
        assert(!o.w[0].fault && !o.w[1].fault && o.w[0].boostMs == 0 && o.w[1].boostMs == 0);
        assert(b.rec.state() == REC_IDLE && b.rec.attempt() == 0 && b.rec.giveups() == 0);
    }
    {
        Bench b;   // the partner alone turning round, during the ramp
        b.trip(0, 350);
        b.until(REV_LOCKED);
        for (int i = 0; i < 20; i++) assert(b.tick().event == REV_NONE);
        assert(b.rec.state() == REC_RAMP);
        b.in.w[1].goalCps = 0;
        assert(b.tick().event == REV_NONE && b.rec.state() == REC_RAMP);
        b.in.w[1].goalCps = -1000;
        RecoveryOut o = b.tick();
        assert(o.event == REV_CANCELLED && o.wheel == 1 && !o.w[0].fault && !o.w[1].fault);
        assert(b.rec.state() == REC_IDLE && b.rec.attempt() == 0 && b.rec.recoveries() == 0);
    }
    {
        Bench b;
        b.trip(0, 350);
        b.tick();
        b.in.cmdLive = false;   // stick released, stop, or the deadman
        RecoveryOut o = b.tick();
        assert(o.event == REV_CANCELLED && o.w[0].hold == W::HOLD_NONE && o.w[1].hold == W::HOLD_NONE);
        b.in.w[0].stall.trip = +1;   // a trip while not live is a plain slip fault
        o = b.tick();
        assert(o.event == REV_FAULT_DIRECT && o.wheel == 0 && o.w[0].fault && !o.w[1].fault);
        assert(b.rec.attempts() == 1);
    }
    {
        Bench b;
        b.trip(1, 350);
        b.until(REV_LOCKED);
        b.in.eligible = false;
        assert(b.tick().event == REV_CANCELLED);
    }
    {
        Bench b;
        b.trip(0, 350);
        b.until(REV_LOCKED);
        b.rec.cancel();
        assert(b.rec.state() == REC_RAMP);   // reported, and released, by the next update
        RecoveryOut o = b.tick();
        assert(o.event == REV_CANCELLED && b.rec.state() == REC_IDLE && b.rec.attempt() == 0);
        b.rec.cancel();   // idle: nothing to report
        assert(b.tick().event == REV_NONE);
        b.trip(0, 350);
        b.rec.configure(RecoveryConfig());   // a settings change cancels too
        assert(b.tick().event == REV_CANCELLED);
    }

    // --- faults it must not handle: recover off, a LEAD, not both in velocity mode ---
    {
        RecoveryConfig c;
        c.enabled = false;
        Bench b(c);
        RecoveryOut o = b.trip(1, 300);
        assert(o.event == REV_FAULT_DIRECT && o.wheel == 1 && o.w[1].fault && !o.w[0].fault);
        assert(o.w[0].hold == W::HOLD_NONE && o.w[1].hold == W::HOLD_NONE && o.w[1].boostMs == 0);
        assert(b.rec.state() == REC_IDLE && b.rec.attempts() == 0);
    }
    {
        Bench b;
        RecoveryOut o = b.trip(0, 1200, -1);
        assert(o.event == REV_FAULT_DIRECT && o.wheel == 0 && o.w[0].fault);
    }
    {
        Bench b;   // a LEAD mid-episode: holds released and faulted, not retried
        b.trip(0, 350);
        b.tick();
        RecoveryOut o = b.trip(1, 1000, -1);
        assert(o.event == REV_FAULT_DIRECT && o.wheel == 1 && o.w[1].fault && !o.w[0].fault);
        assert(o.w[0].hold == W::HOLD_NONE && o.w[1].hold == W::HOLD_NONE && b.rec.state() == REC_IDLE);
    }
    {
        Bench b;   // the bench's `wheel A vel`: the other wheel is not in velocity mode
        b.in.w[1].velMode = false;
        RecoveryOut o = b.trip(0, 300);
        assert(o.event == REV_FAULT_DIRECT && o.wheel == 0 && o.w[0].fault);
    }
    {
        Bench b;   // a wheel already faulted keeps its own fault
        b.in.w[0].faulted = true;
        b.in.w[0].velMode = false;
        RecoveryOut o = b.trip(0, 300);
        assert(o.event == REV_NONE && !o.w[0].fault && !o.w[1].fault);
    }

    // --- exactly `tries` attempts; the next failure latches ---
    {
        Bench b;
        for (int a = 1; a <= 3; a++) {
            RecoveryOut o = b.trip(0, 350);
            assert(o.event == REV_ATTEMPT && b.rec.attempt() == a);
            b.until(REV_LOCKED);
            for (int i = 0; i < 10; i++) assert(b.tick().event == REV_NONE);   // no progress yet
        }
        RecoveryOut o = b.trip(0, 350);
        assert(o.event == REV_GAVE_UP && o.wheel == 0 && o.w[0].fault && !o.w[1].fault);
        assert(o.w[0].hold == W::HOLD_NONE && o.w[1].hold == W::HOLD_NONE);
        assert(b.rec.state() == REC_IDLE && b.rec.attempt() == 0);
        assert(b.rec.attempts() == 3 && b.rec.giveups() == 1 && b.rec.recoveries() == 0);
    }
    {
        Bench b;   // a failed third lock is a failure too
        b.trip(0, 350);
        b.until(REV_LOCKED);
        b.trip(1, 350);
        b.until(REV_LOCKED);
        b.trip(0, 350);
        assert(b.rec.attempt() == 3);
        b.tick();
        b.in.w[0].rawLag = -50;
        RecoveryOut o = b.tick();
        assert(o.event == REV_GAVE_UP && o.wheel == 0 && o.w[0].fault);
    }

    // --- the rate guard: the 10th attempt inside 60 s gives up, progress or not ---
    {
        Bench b;
        for (int e = 0; e < 9; e++) {
            RecoveryOut o = b.trip(e & 1, 350);
            assert(o.event == REV_ATTEMPT && b.rec.attempt() == 1);
            b.until(REV_LOCKED);
            b.until(REV_RECOVERED);
        }
        assert(b.now() - 1000 < 60000);
        RecoveryOut o = b.trip(0, 350);
        assert(o.event == REV_GAVE_UP && o.w[0].fault);
        assert(b.rec.attempts() == 9 && b.rec.recoveries() == 9 && b.rec.giveups() == 1);
        o = b.trip(0, 350);   // after the latch and a Clear, the guard starts afresh
        assert(o.event == REV_ATTEMPT);
    }
    {
        Bench b;   // the same attempts spread out are fine
        for (int e = 0; e < 12; e++) {
            assert(b.trip(0, 350).event == REV_ATTEMPT);
            b.until(REV_LOCKED);
            b.until(REV_RECOVERED);
            b.in.nowMs += 8000;
        }
        assert(b.rec.giveups() == 0 && b.rec.recoveries() == 12);
    }

    // --- boost: both wheels on the trip tick, renewed in the ramp, capped per episode ---
    {
        Bench b;
        uint32_t start = b.now();
        RecoveryOut o = b.trip(0, 350);
        assert(o.w[0].boostMs == 1700 && o.w[1].boostMs == 1700);
        do {
            o = b.tick();
            assert(o.event == REV_LOCKED || (o.w[0].boostMs == 0 && o.w[1].boostMs == 0));
        } while (o.event != REV_LOCKED);
        uint32_t locked = b.now() - 5;
        assert(locked - start == 205);
        b.stalled[0] = true;   // no progress, so the ramp runs to the cap
        b.in.w[0].stall.rotorCps = 0;
        int renewals = 0;
        uint32_t last = locked, end = 0;
        for (int i = 0; i < 2000; i++) {
            uint32_t t = b.now();
            o = b.tick();
            assert(o.event == REV_NONE && o.w[0].boostMs == o.w[1].boostMs);
            if (!o.w[0].boostMs) continue;
            assert(t - last == 250);   // every 250 ms from the lock
            if (t + 500 <= start + 5000) assert(o.w[0].boostMs == 500);
            last = t;
            end = t + o.w[0].boostMs;
            assert(end <= start + 5000);   // never past boostMaxMs from the first trip
            renewals++;
        }
        assert(renewals == 19 && end == start + 5000);
    }

    // --- an involved wheel's encoder dropping out gives up; the partner's does not ---
    {
        Bench b;
        b.trip(0, 350);
        b.tick();
        b.in.w[1].encOk = false;
        assert(b.tick().event == REV_NONE);
        b.in.w[1].encOk = true;
        b.in.w[0].encOk = false;
        RecoveryOut o = b.tick();
        assert(o.event == REV_GAVE_UP && o.wheel == 0 && o.w[0].fault);
    }
    {
        Bench b;
        b.trip(0, 350);
        b.until(REV_LOCKED);
        b.in.w[0].encOk = false;
        assert(b.tick().event == REV_GAVE_UP);
    }

    assert(!strcmp(Recovery::name(REV_GAVE_UP), "gave up") && !strcmp(Recovery::name(REV_NONE), "none"));
    assert(!strcmp(Recovery::stateName(REC_LOCK), "lock"));

    // --- recoveryTick: the real detectors, a fake servo, calls in order ---
    {
        Robot r;   // a wall: exactly three attempts, then the fault
        for (int i = 0; i < 200; i++) assert(r.step().event == REV_NONE);
        r.a.stalled = true;
        RecoveryOut o = r.until(REV_ATTEMPT);
        assert(o.wheel == 0 && o.k == 0 && r.rec.attempt() == 1);
        assert(!strcmp(g_log, "0:boost1700 0:snap 1:boost1700 1:slew "));
        assert(r.a.vcmd == 1000);   // the snap only lands at the next update
        o = r.step();
        assert(r.a.vcmd == 0 && r.a.held && r.b.held);
        assert(!strcmp(g_log, "0:snap 0:resync 1:slew 1:resync "));
        o = r.until(REV_LOCKED);
        assert(!strcmp(g_log, "0:release 0:resync 1:release 1:resync "));
        assert(!r.a.held && !r.b.held);
        for (int a = 2; a <= 3; a++) {
            o = r.until(REV_ATTEMPT);   // re-armed after the settle, tripped again
            assert(o.wheel == 0 && r.rec.attempt() == a);
            r.until(REV_LOCKED);
        }
        o = r.until(REV_GAVE_UP);
        assert(o.wheel == 0 && !strcmp(g_log, "0:fault "));
        assert(r.a.flt == FakeServo::FAULT_SLIP && r.b.flt == 0);
        assert(r.rec.attempts() == 3 && r.rec.giveups() == 1 && r.det[0].trips() == 4);
        printf("wall: 3 attempts, then gave up %.2f s after the wheel stopped (detector trips %u)\n",
               (r.now - 5) * 0.001f - 1.0f, (unsigned)r.det[0].trips());
    }
    {
        Robot r;   // a bump: the obstacle gives way once the field lets go
        for (int i = 0; i < 200; i++) r.step();
        r.a.stalled = true;
        r.until(REV_ATTEMPT);
        r.a.stalled = false;
        r.until(REV_LOCKED);
        RecoveryOut o = r.until(REV_RECOVERED);
        assert(o.wheel == 0 && r.rec.recoveries() == 1 && r.rec.attempts() == 1);
        assert(!r.a.flt && !r.b.flt && !r.a.held && !r.b.held);
        for (int i = 0; i < 400; i++) assert(r.step().event == REV_NONE);   // back up to speed, no trips
        assert(r.a.vcmd == 1000 && r.b.vcmd == 1000);
    }
    {
        Robot r;   // stick released mid-lock: both holds let go within the tick
        for (int i = 0; i < 200; i++) r.step();
        r.a.stalled = true;
        r.until(REV_ATTEMPT);
        r.step();
        r.live = false;
        RecoveryOut o = r.step();
        assert(o.event == REV_CANCELLED && !strcmp(g_log, "0:release 1:release "));
        assert(!r.a.held && !r.b.held && !r.a.flt);
    }
    {
        Robot r;   // a cancel before the lock's resync must not leave a detector latched
        for (int i = 0; i < 200; i++) r.step();
        r.a.slipFrac = 0.5f;   // A slipping at half speed, still turning the same way
        RecoveryOut o = r.until(REV_ATTEMPT);
        assert(o.wheel == 0 && o.k > 0.4f && o.k < 0.6f);
        r.b.goal = -1000;   // the stick swings into a spin turn on the very next tick
        o = r.step();
        assert(o.event == REV_CANCELLED && o.wheel == 1 && !strcmp(g_log, "0:release 1:release "));
        uint32_t cancelled = r.now;
        o = r.until(REV_ATTEMPT);   // A, still slipping, is caught again after its settle
        assert(o.wheel == 0 && r.rec.attempt() == 1 && r.now - cancelled < 300);
        assert(!r.a.flt && !r.b.flt && r.det[0].trips() == 2);
    }
    {
        Robot r;   // the spin-turn swing: B already braking into its reversal when A slips
        for (int i = 0; i < 200; i++) r.step();
        r.b.goal = -1000;      // B starts braking through zero at decel...
        r.a.slipFrac = 0.6f;   // ...and the turn loads A until it slips
        RecoveryOut o = r.until(REV_ATTEMPT);
        assert(o.wheel == 0 && o.k > 0.3f && o.k < 0.5f);
        assert(o.w[1].hold == W::HOLD_SLEW && o.w[1].holdCps == 0);
        float v0 = r.b.vcmd;
        assert(v0 > 300);   // still well into the old direction
        double x0 = r.b.shaft, forward = 0;
        r.a.slipFrac = 0;   // with the field let go, A locks
        do {
            o = r.step();
            forward = fmax(forward, r.b.shaft - x0);
            assert(r.b.vcmd >= 0);   // nor pushed the new way during the lock
        } while (o.event != REV_LOCKED);
        assert(r.b.vcmd == 0);
        double ramp = 0;   // what braking at decel from v0 gives, tick by tick
        for (float v = v0 - 41.0f; v > 0; v -= 41.0f) ramp += v * DT;
        assert(forward <= ramp + 0.01);
        printf("partner mid-reversal: braking from %.0f counts/s, went %.1f counts the old way "
               "(the decel ramp alone gives %.1f), held at 0 through the lock\n", v0, forward, ramp);
        r.until(REV_RECOVERED);   // A makes its progress; B is on its way into the turn
        assert(r.b.vcmd < 0 && !r.a.flt && !r.b.flt);
    }
    {
        RecoveryConfig c;   // recover 0: the new detector, faulting on its first trip
        c.enabled = false;
        Robot r(c);
        for (int i = 0; i < 200; i++) r.step();
        r.a.stalled = true;
        RecoveryOut o = r.until(REV_FAULT_DIRECT);
        assert(o.wheel == 0 && !strcmp(g_log, "0:fault ") && r.a.flt == FakeServo::FAULT_SLIP);
    }

    puts("PASS: recovery k clamp, freeze/lock/ramp timing, same-tick double trip, JOINED, LOCK_FAILED, "
         "re-freeze k against the command the hold began from, the lock following its rotor (partner at the "
         "new k, braking partner held at 0, clamp kept), progress reset, cancels (either wheel's goal reversing in lock or ramp, stick, eligibility, "
         "cancel(), settings), FAULT_DIRECT (recover off, LEAD, bench wheel), exactly 3 attempts, rate guard, "
         "boost timing, encoder give-up, recoveryTick call order through the real detectors, "
         "no latched detector after an early cancel, partner mid-reversal brakes to 0");
    return 0;
}
