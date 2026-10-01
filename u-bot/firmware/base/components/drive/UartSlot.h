#pragma once
#include <stdint.h>

// The control tick's one extra bus transaction group: whatever else the 5 ms
// tick does on the TMC2209 UART, or on an encoder's I2C, after the servos
// have had theirs.
//
// The servos' own traffic (two encoder reads, and a VACTUAL write whenever a
// rate changes) is the tick's fixed cost. Everything else shares what is left,
// and must never push the tick past its period, so at most one group runs per
// tick, picked here in priority order:
//
//   LIVE     a live-current write -- a boost, a step of its ramp down, a
//            derate: the pair BoostPolicy wants that the driver does not have
//            yet. IFCNT-verified, so ~2 ms at 250 kbaud. Current going down
//            goes before current going up: down is the protective direction,
//            and an up waits at most a tick. Between two wheels wanting the
//            same kind of write, the one not written last goes first, so
//            neither starves. Each wheel is written at most once per
//            WRITE_GAP_MS, the step of BoostPolicy's ramp down, which the
//            writes keep pace with.
//   HEALTH   the next step of the four-phase health poll (A encoder, A driver,
//            B encoder, B driver), one due every HEALTH_MS, so each encoder and
//            driver is looked at every 500 ms.
//   MSCNT    (Phase 3) an MSCNT read for the load-angle estimate. Nothing asks
//            for one yet.
//
// Budget: when the servo part of the tick has already taken more than
// BUDGET_US, nothing runs, so a slow encoder read or a preempted tick is not
// made worse. The health poll is the exception. It is how a reset, a short, a
// lost encoder or an OTPW is found, so it is never put off for more than
// HEALTH_DEFER_MS past its due time, by the budget or by live writes: from
// then on it runs first, whatever else is waiting.
//
// Pure: times are the caller's and nothing here touches a bus. next() books
// what it returns -- the write gap, the alternation, the health cadence -- so
// the caller must run it.
class UartSlot {
  public:
    static constexpr uint32_t HEALTH_MS = 125;        // one health step per this
    static constexpr uint32_t HEALTH_DEFER_MS = 50;   // longest a due step waits
    static constexpr uint32_t WRITE_GAP_MS = 100;     // per wheel, between live writes
    static constexpr uint32_t BUDGET_US = 3000;       // servo part of the tick past this: skip

    enum Group : uint8_t { NONE, LIVE, HEALTH, MSCNT, NGROUPS };

    struct Request {
        bool live[2] = {false, false};    // wheel i has a live-current write pending
        bool raise[2] = {false, false};   // ...and it raises IRUN or IHOLD
        bool mscnt = false;               // an MSCNT read is wanted (Phase 3)
    };

    struct Choice {
        Group group = NONE;
        uint8_t wheel = 0;   // for LIVE
    };

    UartSlot() { reset(0); }

    // Start over: the first health step is due HEALTH_MS after nowMs (boot
    // has just looked at everything), and no wheel has been written.
    void reset(uint32_t nowMs) {
        _lastHealth = nowMs;
        _wrote[0] = _wrote[1] = false;
        _lastWrite[0] = _lastWrite[1] = 0;
        _lastWheel = 1;   // so wheel A goes first
    }

    // Once per control tick, after the servos: servoUs is how long the tick
    // has taken so far.
    Choice next(uint32_t nowMs, uint32_t servoUs, const Request &rq) {
        Choice c;
        const bool healthDue = elapsed(_lastHealth, nowMs, HEALTH_MS);
        const bool healthLate = elapsed(_lastHealth, nowMs, HEALTH_MS + HEALTH_DEFER_MS);
        const int live = pickLive(nowMs, rq);
        const bool over = servoUs > BUDGET_US;
        if (healthLate) {
            if (over || live >= 0) _forced++;
            c.group = HEALTH;
        } else if (over) {
            if (healthDue || live >= 0 || rq.mscnt) _deferred++;
            return c;
        } else if (live >= 0) {
            c.group = LIVE;
            c.wheel = (uint8_t)live;
        } else if (healthDue) {
            c.group = HEALTH;
        } else if (rq.mscnt) {
            c.group = MSCNT;
        } else {
            return c;
        }
        if (c.group == LIVE) {
            _wrote[c.wheel] = true;
            _lastWrite[c.wheel] = nowMs;
            _lastWheel = c.wheel;
        } else if (c.group == HEALTH) {
            healthRan(nowMs);
        }
        _runs[c.group]++;
        return c;
    }

    // For a caller polling health on its own cadence (the calibration, which
    // holds the control task for ~20 s and never calls next()).
    bool healthDue(uint32_t nowMs) const { return elapsed(_lastHealth, nowMs, HEALTH_MS); }
    void healthRan(uint32_t nowMs) { _lastHealth = nowMs; }

    // How often each group ran; ticks when the budget put off something that
    // was due; health steps that ran overdue, past the budget or ahead of a
    // waiting write.
    uint32_t runs(Group g) const { return g < NGROUPS ? _runs[g] : 0; }
    uint32_t deferred() const { return _deferred; }
    uint32_t forced() const { return _forced; }
    void resetStats() {
        for (uint32_t &n : _runs) n = 0;
        _deferred = _forced = 0;
    }

  private:
    // Wrap-safe, as BoostPolicy's: true once `now` is at least `ms` past
    // `since`, across the 2^32 ms wrap, for spans up to 2^31 ms.
    static bool elapsed(uint32_t since, uint32_t now, uint32_t ms) {
        return (int32_t)(now - since) >= (int32_t)ms;
    }

    // The wheel whose pending write goes now, or -1. The wheel not written
    // last is looked at first and wins a tie; a lowering write beats a
    // raising one.
    int pickLive(uint32_t now, const Request &rq) const {
        int best = -1;
        for (int k = 0; k < 2; k++) {
            const int i = (_lastWheel + 1 + k) & 1;
            if (!rq.live[i] || (_wrote[i] && !elapsed(_lastWrite[i], now, WRITE_GAP_MS))) continue;
            if (best < 0 || (rq.raise[best] && !rq.raise[i])) best = i;
        }
        return best;
    }

    uint32_t _lastHealth = 0;
    bool _wrote[2] = {false, false};
    uint32_t _lastWrite[2] = {0, 0};
    uint8_t _lastWheel = 1;
    uint32_t _runs[NGROUPS] = {};
    uint32_t _deferred = 0;
    uint32_t _forced = 0;
};
