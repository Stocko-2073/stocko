#pragma once
#include <math.h>
#include <stdint.h>

#include "StallDetector.h"

// Stall recovery: what the robot does when a StallDetector trips, for both
// wheels at once, because on a differential drive nothing one wheel does is
// private.
//
// Why a slipped stepper needs help at all: while the field runs ahead of the
// rotor, the torque averages to almost nothing, and the robot's reflected
// inertia (~500x the rotor's) means the rotor can never catch a field that
// keeps moving away. So each attempt goes:
//
//   freeze   the tripped wheel's field SNAPS to the speed its rotor is actually
//            doing (k = rotor/cmd, clamped to [-1, 1]), so field and rotor meet.
//            The partner SLEWS to k times its own command at the servo's decel:
//            it is still in sync and carries the robot's momentum, and snapping
//            it would throw that away and slip it too. Same k, same arc -- unless
//            the stick has already turned the partner round and it is braking
//            through zero, when k times its old-direction command would hold it
//            the old way: then it slews to 0, braking as it already was. Boost
//            is requested for both wheels on this tick, so the current write
//            (this tick's UART slot) lands before the snapped VACTUAL (the
//            servo's next update()).
//   lock     next tick, resync both -- the snap has landed, so raw now measures
//            slip against the held field. Then hold for lockMs, ~3 periods of the
//            ~15 Hz rotor-on-robot mode and well before the driver's ~0.5 s drop
//            to hold current, until each rotor matches its hold. A partner that
//            trips meanwhile joins the attempt.
//
//            The snapped holds FOLLOW their rotors through the lock, from the
//            first tick the detector has a speed again, and the partner keeps
//            the arc at the new k. A slipped rotor under a load that pushes
//            back -- a bump, a hill -- is still decelerating when it trips, and
//            the speed the snap took from a 20 ms average is already behind
//            it: a field held there only catches it by luck, and on the host
//            plant mostly did not. A field that follows it keeps the slip slow,
//            so the load angle walks into the holding half of the field and
//            settles there. Never past the clamp below: it can only follow a
//            rotor rolling back as fast as it was asked to go forward.
//   ramp     release the holds; the servo's normal slew re-ramps toward whatever
//            the stick says now. Boost is renewed until every involved wheel
//            has made progressSteps in its goal direction, or boostMaxMs.
//
// Exactly `tries` attempts without progress; the next failure latches today's
// FAULT_SLIP (drive.cpp's latchFault() stops the peer, Clear required). More
// than rateAttempts inside rateWindowMs gives up too, progress or not: that is
// a hill just past the limit, sawtoothing.
//
// The operator can always take it back: the stick released (or stop, or the
// deadman), eligibility lost, cancel(), a settings change, or EITHER wheel's
// goal reversing ends the episode -- holds released, no fault. The partner
// counts too: a reversal on either side is a new decision, swinging into a spin
// turn say, and holding the partner the old way for up to lockMs +
// partnerWaitMs would be the wrong feel.
//
// EXPLORATIONS.md's rule holds by construction: this only ever acts on a live,
// deadman-refreshed operator command (cmdLive, eligible), before any fault
// latches; |k| <= 1, so never above the commanded speed; it raises faults but
// never clears one. Anything it is not allowed to handle -- recover off, the
// bench's `wheel X vel`, a released stick, a LEAD (a push: gravity would need a
// >33 degree slope to overhaul this robot) -- faults directly, as the servo's
// own slip fault would have.
//
// Units: *Cps are encoder counts/s at the output shaft, like the servo's
// velocities; lag and progress are motor microsteps, like the detector.
//
// Pure: std headers and StallDetector.h only. recoveryTick() at the bottom is
// the glue drive.cpp and the host rig share.

struct RecoveryConfig {
    bool enabled = true;             // recover: false faults on the first trip
    uint8_t tries = 3;               // rec_tries: attempts without progress
    uint16_t lockMs = 200;           // rec_lock_ms: minimum hold before the ramp
    float progressSteps = 1333;      // rec_prog: 0.25 output turn, microsteps
    uint16_t partnerWaitMs = 1000;   // extra lock time for the partner to slew down
    float lockCps = 80;              // rotor within this of its hold is locked, counts/s
    uint16_t boostMs = 1500, boostMaxMs = 5000;   // boost past the lock; renewals' cap
    uint8_t rateAttempts = 10;       // this many attempts inside...
    uint32_t rateWindowMs = 60000;   // ...this long gives up; 0 attempts = no guard
    float stepsPerCount = 1.302083f;
    float lockLagSteps = 40;         // a locking wheel's raw slip past this fails the
                                     // lock: set it to the detector's tripSteps
};

struct RecoveryWheelIn {
    StallSample stall;   // this tick's detector sample
    float goalCps;       // the stick's goal (servo _vgoal)
    float cmdCps;        // slew-limited command in force (servo _vcmd)
    float rawLag;        // servo raw slip since its last resync, microsteps
    int32_t encCounts;
    bool velMode, faulted, encOk;
};

struct RecoveryIn {
    RecoveryWheelIn w[2];
    bool cmdLive;    // a live, deadman-refreshed stick command
    bool eligible;   // drivers on, no latched fault, no demo or cal
    uint32_t nowMs;
};

// Holds are levels: reported every tick they are in force. HOLD_NONE on a wheel
// that is holding means release it.
struct RecoveryWheelOut {
    enum Hold : uint8_t { HOLD_NONE, HOLD_SNAP, HOLD_SLEW } hold;
    float holdCps;
    bool resync;       // resyncSlip() now
    bool fault;        // latch FAULT_SLIP on this wheel
    uint32_t boostMs;  // request BOOST_RECOVERY for this long; 0 = no request
};

enum RecoveryState : uint8_t { REC_IDLE, REC_LOCK, REC_RAMP };

enum RecoveryEvent : uint8_t {
    REV_NONE,
    REV_FAULT_DIRECT,   // a trip it may not handle: faulted as a plain slip
    REV_ATTEMPT,        // froze and started an attempt (attempt() says which)
    REV_JOINED,         // the partner tripped during the lock and joined it
    REV_LOCKED,         // rotors matched their holds; ramping
    REV_LOCK_FAILED,    // re-froze on the rotors' current speeds as the next attempt
    REV_RECOVERED,      // progress on every involved wheel; the count starts over
    REV_CANCELLED,      // stick released or stopped, either goal reversed, cancel()
    REV_GAVE_UP,        // out of attempts, rate guard, or an encoder lost: faulted
};

struct RecoveryOut {
    RecoveryWheelOut w[2];
    RecoveryEvent event;   // at most one per tick
    uint8_t wheel;         // the wheel the event is about
    float k;               // the current attempt's rotor/cmd ratio, 0 when idle
};

class Recovery {
  public:
    static constexpr float PARTNER_CPS = 20;         // partner "at its hold", counts/s
    static constexpr uint32_t RENEW_MS = 500;        // each boost renewal in the ramp...
    static constexpr uint32_t RENEW_EVERY_MS = 250;  // ...this often
    static constexpr uint8_t RATE_MAX = 32;          // rateAttempts is clamped to this

    // A settings change cancels whatever is running (the next update reports
    // it) and starts the rate guard afresh.
    void configure(const RecoveryConfig &c) {
        _cfg = c;
        if (_cfg.rateAttempts > RATE_MAX) _cfg.rateAttempts = RATE_MAX;
        _nRate = 0;
        cancel();
    }
    const RecoveryConfig &config() const { return _cfg; }

    // From the deadman, stop, or anything else that takes the stick away. The
    // next update() releases the holds and reports REV_CANCELLED.
    void cancel() {
        if (_state != REC_IDLE) _cancelReq = true;
    }

    RecoveryOut update(const RecoveryIn &in) {
        RecoveryOut out = {};
        _now = in.nowMs;
        const RecoveryWheelIn *w = in.w;
        bool can = _cfg.enabled && in.eligible && in.cmdLive && w[0].velMode && w[1].velMode &&
                   !w[0].faulted && !w[1].faulted;
        uint8_t lag = 0, lead = 0;
        for (int i = 0; i < 2; i++) {
            if (w[i].faulted) continue;   // never write over someone else's fault
            if (w[i].stall.trip > 0) lag |= bit(i);
            if (w[i].stall.trip < 0) lead |= bit(i);
        }

        // Whatever ends an episode without being a failure of it. A reversal
        // names the wheel whose goal turned round.
        if (_state != REC_IDLE) {
            uint8_t reversed = goalReversed(in);
            if (_cancelReq || !can || reversed) {
                event(out, REV_CANCELLED, reversed ? first(reversed) : first(_involved));
                end();
            }
        }
        _cancelReq = false;

        if (lead) {
            if (_state != REC_IDLE) end();
            fault(out, first(lead), REV_FAULT_DIRECT);
            return finish(out);
        }
        if (!can) {
            if (lag) fault(out, first(lag), REV_FAULT_DIRECT);
            return finish(out);
        }

        switch (_state) {
            case REC_IDLE:
                if (lag) freeze(out, in, lag, REV_ATTEMPT, first(lag));
                break;
            case REC_LOCK: lockTick(out, in, lag); break;
            case REC_RAMP: rampTick(out, in, lag); break;
        }
        return finish(out);
    }

    RecoveryState state() const { return _state; }
    uint8_t attempt() const { return _attempt; }     // 0 when idle
    uint8_t involved() const { return _involved; }   // bit per wheel
    uint32_t attempts() const { return _attempts; }  // since boot
    uint32_t recoveries() const { return _recoveries; }
    uint32_t giveups() const { return _giveups; }

    static const char *name(RecoveryEvent e) {
        switch (e) {
            case REV_FAULT_DIRECT: return "fault";
            case REV_ATTEMPT:      return "attempt";
            case REV_JOINED:       return "joined";
            case REV_LOCKED:       return "locked";
            case REV_LOCK_FAILED:  return "lock failed";
            case REV_RECOVERED:    return "recovered";
            case REV_CANCELLED:    return "cancelled";
            case REV_GAVE_UP:      return "gave up";
            default:               return "none";
        }
    }
    static const char *stateName(RecoveryState s) {
        switch (s) {
            case REC_LOCK: return "lock";
            case REC_RAMP: return "ramp";
            default:       return "idle";
        }
    }

  private:
    typedef RecoveryWheelOut::Hold Hold;

    static uint8_t bit(int i) { return (uint8_t)(1u << i); }
    static uint8_t first(uint8_t mask) { return (mask & 1) ? 0 : ((mask & 2) ? 1 : 0); }
    static int8_t sign(float v) { return v > 0 ? 1 : (v < 0 ? -1 : 0); }

    // What a wheel's hold is measured against: the command in force when the
    // hold began, kept for the attempt. Taking a re-freeze's k against the
    // hold itself would let each one only shrink the hold, never catch a
    // rotor rolling back faster than it.
    float refCps(const RecoveryWheelIn &w, int i) const { return _held[i] ? _refCps[i] : w.cmdCps; }

    // What the rotor is really doing as a fraction of what was asked. Clamped
    // so a hold is never faster than the command, nor further backwards than
    // it was forwards; below a count a second there is no ratio to take.
    float ratio(const RecoveryWheelIn &w, int i) const {
        const float ref = refCps(w, i);
        if (!(fabsf(ref) >= 1.0f)) return 0.0f;
        float k = w.stall.rotorCps / ref;
        return k > 1.0f ? 1.0f : (k < -1.0f ? -1.0f : k);
    }

    // The stick already points this wheel one way while its command is still
    // going the other, braking through zero. A goal of zero is a stop, not a
    // reversal.
    static bool reversing(const RecoveryWheelIn &w) {
        return sign(w.goalCps) * sign(w.cmdCps) < 0;
    }

    void event(RecoveryOut &out, RecoveryEvent e, uint8_t wheel) {
        out.event = e;
        out.wheel = wheel;
    }

    void fault(RecoveryOut &out, uint8_t wheel, RecoveryEvent e) {
        out.w[wheel].fault = true;
        event(out, e, wheel);
    }

    void boostBoth(RecoveryOut &out, uint32_t ms) {
        for (int i = 0; i < 2; i++) {
            if (ms > out.w[i].boostMs) out.w[i].boostMs = ms;
        }
    }

    void resyncBoth(RecoveryOut &out) { out.w[0].resync = out.w[1].resync = true; }

    // Both wheels' goal directions are taken at the freeze (or the first time
    // a wheel has one); the stick turning EITHER of them the other way ends
    // the episode, the partner as much as the tripped wheel -- see the top of
    // the file. A goal that merely goes to zero is not a reversal. Returns the
    // wheels that reversed.
    uint8_t goalReversed(const RecoveryIn &in) {
        uint8_t reversed = 0;
        for (int i = 0; i < 2; i++) {
            int8_t s = sign(in.w[i].goalCps);
            if (_goalSign[i] == 0) _goalSign[i] = s;
            else if (s != 0 && s != _goalSign[i]) reversed |= bit(i);
        }
        return reversed;
    }

    void end() {
        _state = REC_IDLE;
        _attempt = 0;
        _involved = _locking = 0;
        _resyncDue = false;
        _k = 0;
        for (int i = 0; i < 2; i++) {
            release(i);
            _goalSign[i] = 0;
        }
    }

    void release(int i) {
        _hold[i] = RecoveryWheelOut::HOLD_NONE;
        _holdCps[i] = 0;
        _held[i] = _brake[i] = false;
    }

    void giveUp(RecoveryOut &out, uint8_t wheel) {
        end();
        _giveups++;
        _nRate = 0;   // the latched fault is the answer; a Clear starts afresh
        fault(out, wheel, REV_GAVE_UP);
    }

    // The attempt that would start now makes rateAttempts inside the window.
    bool rateExceeded() const {
        if (_cfg.rateAttempts == 0) return false;
        uint8_t recent = 0;
        for (uint8_t k = 0; k < _nRate; k++) {
            if (_now - _rateMs[k] < _cfg.rateWindowMs) recent++;
        }
        return recent + 1 >= _cfg.rateAttempts;
    }

    void recordAttempt() {
        _rateMs[_rateHead] = _now;
        _rateHead = (uint8_t)((_rateHead + 1) % RATE_MAX);
        if (_nRate < RATE_MAX) _nRate++;
    }

    // The next attempt on the wheels in `mask`, each snapped to its own rotor;
    // anything else slews to the first one's k. Or, out of attempts, give up.
    void freeze(RecoveryOut &out, const RecoveryIn &in, uint8_t mask, RecoveryEvent e,
                uint8_t wheel) {
        if (_attempt >= _cfg.tries || rateExceeded()) {
            giveUp(out, wheel);
            return;
        }
        recordAttempt();
        if (_state == REC_IDLE) _episodeMs = _now;
        _attempt++;
        _attempts++;
        _involved |= mask;
        _locking = mask;
        _k = ratio(in.w[first(mask)], first(mask));
        for (int i = 0; i < 2; i++) {
            const RecoveryWheelIn &w = in.w[i];
            if (_goalSign[i] == 0) _goalSign[i] = sign(w.goalCps);
            const float ref = refCps(w, i);
            if (mask & bit(i)) {
                _hold[i] = RecoveryWheelOut::HOLD_SNAP;
                _holdCps[i] = ratio(w, i) * ref;
                _brake[i] = false;
            } else {
                // A partner mid-reversal brakes to a stop instead of keeping the
                // arc: the ramp after the lock takes it on into the new direction.
                // Once braking it stays so for the attempt, even after its
                // command has come to rest and no longer looks like a reversal.
                _hold[i] = RecoveryWheelOut::HOLD_SLEW;
                _brake[i] = _brake[i] || reversing(w);
                _holdCps[i] = _brake[i] ? 0.0f : _k * ref;
            }
            if (!_held[i]) {
                _refCps[i] = w.cmdCps;
                _held[i] = true;
            }
        }
        _state = REC_LOCK;
        _resyncDue = true;
        boostBoth(out, (uint32_t)_cfg.lockMs + _cfg.boostMs);
        event(out, e, wheel);
    }

    // A partner that slipped while slewing down: snap it to its own rotor too,
    // and give the lock its full time again from the next resync.
    void join(RecoveryOut &out, const RecoveryIn &in, uint8_t mask) {
        for (int i = 0; i < 2; i++) {
            if (!(mask & bit(i))) continue;
            const RecoveryWheelIn &w = in.w[i];
            _hold[i] = RecoveryWheelOut::HOLD_SNAP;
            _holdCps[i] = ratio(w, i) * refCps(w, i);
            _brake[i] = false;
        }
        _locking |= mask;
        _involved |= mask;
        _resyncDue = true;
        boostBoth(out, (uint32_t)_cfg.lockMs + _cfg.boostMs);
        event(out, REV_JOINED, first(mask));
    }

    // Never resume blind: an involved wheel whose encoder stops answering
    // cannot be locked or ramped, so the episode ends as a fault.
    bool blind(RecoveryOut &out, const RecoveryIn &in) {
        for (int i = 0; i < 2; i++) {
            if ((_involved & bit(i)) && !in.w[i].encOk) {
                giveUp(out, (uint8_t)i);
                return true;
            }
        }
        return false;
    }

    void lockTick(RecoveryOut &out, const RecoveryIn &in, uint8_t lag) {
        if (blind(out, in)) return;
        uint8_t joining = lag & (uint8_t)~_locking;
        if (_resyncDue) {
            // The snap landed in this tick's servo update. Raw from before the
            // resync means nothing, so the lock checks start next tick.
            resyncBoth(out);
            _lockStartMs = _now;
            _resyncDue = false;
            if (joining) join(out, in, joining);
            return;
        }
        follow(in);

        uint8_t failing = lag & _locking;
        uint8_t unmatched = 0;
        for (int i = 0; i < 2; i++) {
            if (!(_locking & bit(i))) continue;
            const RecoveryWheelIn &w = in.w[i];
            if (fabsf(w.rawLag) > _cfg.lockLagSteps) failing |= bit(i);
            if (!(fabsf(w.stall.rotorCps - w.cmdCps) <= _cfg.lockCps)) unmatched |= bit(i);
        }
        if (failing) {
            freeze(out, in, _locking | joining, REV_LOCK_FAILED, first(failing));
            return;
        }
        if (joining) {
            join(out, in, joining);
            return;
        }

        uint32_t t = _now - _lockStartMs;
        uint32_t limit = (uint32_t)_cfg.lockMs + _cfg.partnerWaitMs;
        bool partnerReady = true;
        for (int i = 0; i < 2; i++) {
            if (_locking & bit(i)) continue;
            if (!(fabsf(in.w[i].cmdCps - _holdCps[i]) <= PARTNER_CPS)) partnerReady = false;
        }
        if (t >= limit) partnerReady = true;   // its slew is the servo's business now
        if (t >= _cfg.lockMs && partnerReady && !unmatched) {
            locked(out, in);
        } else if (t >= limit) {
            freeze(out, in, _locking, REV_LOCK_FAILED, first(unmatched));
        }
    }

    // The lock's holds track the rotors: each snapped wheel's from its own
    // rotor's speed, the partner's at the first one's k, as freeze() set them,
    // whenever the detector has a speed to give (its ring restarts at every
    // resync, and reads 0 until it has two reads). A braking partner stays at
    // 0. Whatever comes next this tick -- a join, a failed lock, the ramp --
    // starts from these.
    void follow(const RecoveryIn &in) {
        for (int i = 0; i < 2; i++) {
            if ((_locking & bit(i)) && in.w[i].stall.velValid) _holdCps[i] = ratio(in.w[i], i) * _refCps[i];
        }
        const uint8_t f = first(_locking);
        if (!in.w[f].stall.velValid) return;
        _k = ratio(in.w[f], f);
        for (int i = 0; i < 2; i++) {
            if (!(_locking & bit(i)) && !_brake[i]) _holdCps[i] = _k * _refCps[i];
        }
    }

    void locked(RecoveryOut &out, const RecoveryIn &in) {
        resyncBoth(out);
        for (int i = 0; i < 2; i++) {
            release(i);
            _anchor[i] = in.w[i].encCounts;
        }
        _state = REC_RAMP;
        _nextRenewMs = _now + RENEW_EVERY_MS;
        event(out, REV_LOCKED, first(_involved));
    }

    // Every involved wheel has gone progressSteps its goal's way since the
    // lock. One the stick has since stopped has nothing left to prove.
    bool progressed(const RecoveryIn &in) const {
        for (int i = 0; i < 2; i++) {
            if (!(_involved & bit(i))) continue;
            int8_t s = sign(in.w[i].goalCps);
            if (s == 0) continue;
            int32_t dc = (int32_t)((uint32_t)in.w[i].encCounts - (uint32_t)_anchor[i]);
            if ((float)dc * (float)s * _cfg.stepsPerCount < _cfg.progressSteps) return false;
        }
        return true;
    }

    void rampTick(RecoveryOut &out, const RecoveryIn &in, uint8_t lag) {
        if (blind(out, in)) return;
        if (lag) {
            freeze(out, in, lag, REV_ATTEMPT, first(lag));
            return;
        }
        if (progressed(in)) {
            _recoveries++;
            event(out, REV_RECOVERED, first(_involved));
            end();
            return;
        }
        // Keep the current up while the wheels climb back to speed, but never
        // past boostMaxMs from the first trip: the thermal model caps each
        // burst, this caps the episode.
        uint32_t since = _now - _episodeMs;
        if (since < _cfg.boostMaxMs && (int32_t)(_now - _nextRenewMs) >= 0) {
            uint32_t left = _cfg.boostMaxMs - since;
            boostBoth(out, left < RENEW_MS ? left : RENEW_MS);
            _nextRenewMs = _now + RENEW_EVERY_MS;
        }
    }

    RecoveryOut &finish(RecoveryOut &out) const {
        for (int i = 0; i < 2; i++) {
            out.w[i].hold = _hold[i];
            out.w[i].holdCps = _holdCps[i];
        }
        out.k = _k;
        return out;
    }

    RecoveryConfig _cfg;
    RecoveryState _state = REC_IDLE;
    bool _cancelReq = false;
    uint32_t _now = 0;

    uint8_t _attempt = 0;
    uint8_t _involved = 0;   // tripped at some point this episode
    uint8_t _locking = 0;    // snapped in the current lock
    bool _resyncDue = false;
    float _k = 0;
    Hold _hold[2] = {RecoveryWheelOut::HOLD_NONE, RecoveryWheelOut::HOLD_NONE};
    float _holdCps[2] = {0, 0};
    float _refCps[2] = {0, 0};          // the command each hold is measured against
    bool _held[2] = {false, false};     // _refCps is set: the wheel has a hold this attempt
    bool _brake[2] = {false, false};    // a partner braking through a reversal: held at 0
    int8_t _goalSign[2] = {0, 0};
    int32_t _anchor[2] = {0, 0};
    uint32_t _episodeMs = 0, _lockStartMs = 0, _nextRenewMs = 0;

    uint32_t _rateMs[RATE_MAX] = {};
    uint8_t _rateHead = 0, _nRate = 0;

    uint32_t _attempts = 0, _recoveries = 0, _giveups = 0;
};

// ------------------------------------------------------------------ the glue
//
// One call per control tick, after both servos' update() and before
// checkFaults(), so a fault raised here latches through the normal path in the
// same tick. It samples both detectors, runs Recovery, and applies what comes
// back. Duck-typed so the host tests can hand it a fake; Servo must provide:
//
//   double   commandedSteps() const  commanded integral, microsteps (VelGen::position())
//   float    slipRawSteps() const    that minus encoder x stepsPerCount (_slipRaw)
//   int32_t  positionCounts() const  multiturn encoder, counts
//   uint32_t resyncCount() const     bumped inside every resyncSlip()
//   bool     encoderOk() const
//   bool     velocityMode() const
//   float    goalCps() const         the stick's goal, counts/s (_vgoal)
//   float    commandedCps() const    the slew-limited command, counts/s (_vcmd)
//   uint8_t  fault() const           0 = none
//   bool     holding() const
//   void     holdVelocity(float cps, bool snap)
//            Hold the command at cps instead of the stick's goal. snap = jump
//            there, else slew there at decel. Only sets state: the next
//            update() writes VACTUAL, so the boost requested in the same tick
//            gets its current write in first. Called every tick while a hold
//            is in force, so it must be idempotent, and ignored while faulted.
//   void     releaseHold()           slew back toward the goal from where it is
//   void     resyncSlip()
//   void     raiseFault(Fault)       with Servo::FAULT_SLIP
//
// boost(uint8_t wheel, uint32_t ms) requests BOOST_RECOVERY; a no-op until
// BoostPolicy exists. Per wheel, the order is boost, hold, resync, fault: the
// fault goes last so nothing is applied to a wheel after it has been stopped.
// A cancel also re-anchors both detectors (below).
template <class Servo, class BoostFn>
RecoveryOut recoveryTick(Recovery &rec, StallDetector (&det)[2], StallSample (&st)[2],
                         Servo *(&s)[2], bool cmdLive, bool eligible, uint32_t nowMs,
                         float dt, BoostFn &&boost) {
    RecoveryIn in = {};
    for (int i = 0; i < 2; i++) {
        const Servo &v = *s[i];
        StallInput si;
        si.cmdSteps = v.commandedSteps();
        si.rawLag = v.slipRawSteps();
        si.encCounts = v.positionCounts();
        si.epoch = v.resyncCount();
        si.encOk = v.encoderOk();
        si.velMode = v.velocityMode();
        si.dt = dt;
        st[i] = det[i].update(si);

        RecoveryWheelIn &w = in.w[i];
        w.stall = st[i];
        w.goalCps = v.goalCps();
        w.cmdCps = v.commandedCps();
        w.rawLag = si.rawLag;
        w.encCounts = si.encCounts;
        w.velMode = si.velMode;
        w.faulted = v.fault() != 0;
        w.encOk = si.encOk;
    }
    in.cmdLive = cmdLive;
    in.eligible = eligible;
    in.nowMs = nowMs;

    RecoveryOut out = rec.update(in);
    // A cancel that lands before the lock's resync -- the partner's goal
    // swinging round on the tick after the trip, say -- would leave the tripped
    // wheel's detector latched while it carries on the same way: blind, the
    // crawl chatter all over again. Start both over; a wheel still slipping
    // trips again after its settle.
    if (out.event == REV_CANCELLED) {
        det[0].reanchor();
        det[1].reanchor();
    }
    for (int i = 0; i < 2; i++) {
        const RecoveryWheelOut &o = out.w[i];
        Servo &v = *s[i];
        if (o.boostMs) boost((uint8_t)i, o.boostMs);
        switch (o.hold) {
            case RecoveryWheelOut::HOLD_SNAP: v.holdVelocity(o.holdCps, true); break;
            case RecoveryWheelOut::HOLD_SLEW: v.holdVelocity(o.holdCps, false); break;
            default:
                if (v.holding()) v.releaseHold();
                break;
        }
        if (o.resync) v.resyncSlip();
        if (o.fault) v.raiseFault(Servo::FAULT_SLIP);
    }
    return out;
}
