#pragma once
#include "StepperServo.h"

// Choreographed runs for the dev log: pick a script, press its key, and film.
//
// Non-blocking on purpose. Calibration blocks and the CSV stream stops dead
// while it runs, which is fine for a measurement and useless for a video --
// this is driven from the control tick instead, so the stream keeps flowing and
// plot.py stays live in the corner of the shot.
//
// A script is a table of beats and nothing else. Each beat is an absolute
// target per wheel, how long to sit on it once arrived, and optional tuning for
// that segment; edit the table, not the runner. A caption is printed as it
// starts, so the serial log doubles as a shot list.
//
// Targets are in the ROBOT's frame, not a wheel's: +1 turn means that wheel
// rolls its side of the robot forward, whichever way its own encoder happens to
// count. The two frames differ by one bit per wheel that no amount of
// calibration can supply, and it arrives here as Axis::sign -- see the note on
// DRIVE_SIGN_B in test_servo.ino.
class Demo {
  public:
    // 0.165 mm of rim travel per encoder count, from DRIVE_MECHANISM.md. Only
    // used to say something human in the closing report.
    static constexpr float MM_PER_COUNT = 0.165f;
    static const uint8_t MAXAXES = 2;

    struct Beat {
        const char *say;    // caption, printed when the beat starts
        float a;            // wheel A's absolute target, output turns
        float b;            // wheel B's, same units and same sense (solo: unused)
        uint16_t dwellMs;   // sit here this long after arriving
        float vmax;         // 0 keeps the current tuning
        float accel;        // 0 keeps the current tuning
        int32_t slipLimit;  // 0 keeps the current limit
    };

    struct Script {
        const char *name;
        const Beat *beats;
        uint8_t n;
        bool pair;          // true: both wheels; false: the selected one alone
    };

    // One thing a script drives: a servo, the name to print for it, and the
    // sign that maps the robot's frame onto that wheel.
    struct Axis {
        StepperServo *servo = nullptr;
        const char *name = "?";
        int8_t sign = +1;
    };

    static const Script BENCH;  // the long single-wheel bring-up run
    static const Script SHORT;  // both wheels, ~10 s, cut straight to video

    // Needs the drivers already enabled -- energising a motor stays an explicit
    // act, not something a demo key does for you. Prints its own reason and
    // returns false rather than starting a take that cannot finish.
    // A solo script only ever needs the one axis. This is an overload rather
    // than a default argument because Axis has member initialisers, which a
    // default argument in the same class cannot see yet.
    bool start(const Script &sc, const Axis &a) { return start(sc, a, Axis{}); }

    bool start(const Script &sc, const Axis &a, const Axis &b) {
        _sc = &sc;
        _n = 0;
        _ax[_n++] = a;
        if (sc.pair) {
            if (!b.servo) {
                Serial.println(F("# demo: this script drives both wheels and only one was given"));
                return false;
            }
            _ax[_n++] = b;
        }

        for (uint8_t i = 0; i < _n; i++) {
            if (!_ax[i].servo->driverEnabled()) {
                Serial.println(F("# demo: enable the drivers first (e) -- a demo key"
                                 " will not energise a motor for you"));
                return false;
            }
            if (!_ax[i].servo->encoderOk()) {
                Serial.printf("# demo: wheel %s's encoder is not responding --"
                              " nothing to close the loop on\n", _ax[i].name);
                return false;
            }
        }

        // Snapshot before anything is touched: a beat may retune, and the take
        // has to hand the bench back the way it found it.
        for (uint8_t i = 0; i < _n; i++) {
            StepperServo *s = _ax[i].servo;
            _saved[i] = {s->vmaxTps, s->accelTps2, s->slipLimit};
        }

        _planned = planSeconds();

        for (uint8_t i = 0; i < _n; i++) {
            StepperServo *s = _ax[i].servo;
            s->clearFault();
            s->zeroHere();     // everything in the table is absolute from here
            s->servoOn(true);
        }

        _i = 0;
        _running = true;
        _startMs = millis();
        Serial.printf("# demo %s: %u beats, ~%.1f s planned -- roll camera\n",
                      _sc->name, (unsigned)_sc->n, _planned);
        applyBeat();
        return true;
    }

    void stop() {
        if (!_running) return;
        _running = false;
        restore();
        _caption = "stopped";
        Serial.printf("# demo %s: stopped\n", _sc->name);
    }

    bool running() const { return _running; }
    const char *caption() const { return _caption; }
    uint8_t beat() const { return _i; }

    void update() {
        if (!_running) return;

        // A fault or a dropped driver ends the take rather than limping on. On
        // a pair script either wheel ends it: half a robot finishing the
        // choreography is not a shot anyone wants.
        for (uint8_t i = 0; i < _n; i++) {
            if (_ax[i].servo->fault() == StepperServo::FAULT_NONE) continue;
            Serial.printf("# demo %s: abandoned at beat %u -- wheel %s %s\n",
                          _sc->name, (unsigned)(_i + 1), _ax[i].name,
                          _ax[i].servo->faultName());
            _running = false;
            restore();
            return;
        }
        for (uint8_t i = 0; i < _n; i++) {
            if (!_ax[i].servo->driverEnabled()) { stop(); return; }
        }

        uint32_t now = millis();
        if (_arriving) {
            if (!allAtTarget() && (now - _t0) < _timeoutMs) return;
            if (!allAtTarget()) {
                for (uint8_t i = 0; i < _n; i++) {
                    if (_ax[i].servo->atTarget()) continue;
                    Serial.printf("# demo %s: beat %u timed out, wheel %s %ld counts"
                                  " short, carrying on\n", _sc->name,
                                  (unsigned)(_i + 1), _ax[i].name,
                                  (long)_ax[i].servo->errorCounts());
                }
            }
            _arriving = false;
            _t0 = now;
            return;
        }

        if ((now - _t0) < _sc->beats[_i].dwellMs) return;
        if (++_i >= _sc->n) { finish(); return; }
        applyBeat();
    }

  private:
    struct Saved { float vmax; float accel; int32_t slip; };

    // A beat's target for one axis, robot frame mapped onto that wheel.
    float targetFor(uint8_t i, const Beat &b) const {
        return ((i == 0) ? b.a : b.b) * (float)_ax[i].sign;
    }

    bool allAtTarget() const {
        for (uint8_t i = 0; i < _n; i++) {
            if (!_ax[i].servo->atTarget()) return false;
        }
        return true;
    }

    void applyBeat() {
        const Beat &b = _sc->beats[_i];
        for (uint8_t i = 0; i < _n; i++) {
            StepperServo *s = _ax[i].servo;
            if (b.vmax > 0) s->vmaxTps = b.vmax;
            if (b.accel > 0) s->accelTps2 = b.accel;
            if (b.slipLimit != 0 && b.slipLimit != s->slipLimit) {
                // Crossing a slip-limit boundary means the reference is stale --
                // the hold beat lets the shaft be shoved a long way off the
                // commanded integral on purpose.
                s->slipLimit = b.slipLimit;
                s->resyncSlip();
            }
        }

        if (b.say) {
            _caption = b.say;
            Serial.printf("# demo %s %u/%u: %s\n", _sc->name, (unsigned)(_i + 1),
                          (unsigned)_sc->n, b.say);
        }

        // The beat is over when the LAST wheel arrives, so the timeout is set
        // by the longest leg -- and both wheels are commanded before either is
        // waited on, or a pair script would move one side at a time.
        float worst = 0;
        for (uint8_t i = 0; i < _n; i++) {
            float to = targetFor(i, b);
            worst = fmaxf(worst, fabsf(to - _ax[i].servo->positionTurns()));
            _ax[i].servo->moveToTurns(to);
        }

        // Twice the ideal traverse plus a floor, so a slow segment is never cut
        // short but a jammed one cannot hang the run.
        _timeoutMs = (uint32_t)(2000.0f * worst /
                                fmaxf(_ax[0].servo->vmaxTps, 0.05f)) + 1500;
        _arriving = true;
        _t0 = millis();
    }

    void finish() {
        _running = false;
        restore();
        _caption = "done";
        Serial.printf("# demo %s: done in %.1f s (planned %.1f)\n", _sc->name,
                      (millis() - _startMs) * 0.001f, _planned);
        for (uint8_t i = 0; i < _n; i++) {
            int32_t err = _ax[i].servo->positionCounts();
            Serial.printf("#   wheel %s back at %+ld counts from where it started"
                          " (%.2f mm at the rim, %.2f deg)\n",
                          _ax[i].name, (long)err, err * MM_PER_COUNT,
                          err * 360.0f / StepperServo::COUNTS_PER_REV);
        }
        Serial.println(F("# demo: loops still closed and holding -- 'x' to stop"));
    }

    void restore() {
        for (uint8_t i = 0; i < _n; i++) {
            StepperServo *s = _ax[i].servo;
            s->vmaxTps = _saved[i].vmax;
            s->accelTps2 = _saved[i].accel;
            s->slipLimit = _saved[i].slip;
            s->resyncSlip();
        }
    }

    // What the table should take, walked through as if every beat arrived on
    // the ideal profile. Printed before the take so a script can be trimmed to
    // length without filming it first -- which is the whole job when the cut is
    // ten seconds long.
    float planSeconds() const {
        float vmax = _ax[0].servo->vmaxTps;
        float accel = _ax[0].servo->accelTps2;
        float at[MAXAXES] = {0.0f, 0.0f};
        float total = 0;
        for (uint8_t k = 0; k < _sc->n; k++) {
            const Beat &b = _sc->beats[k];
            if (b.vmax > 0) vmax = b.vmax;
            if (b.accel > 0) accel = b.accel;
            float worst = 0;
            for (uint8_t i = 0; i < _n; i++) {
                float to = targetFor(i, b);
                worst = fmaxf(worst, fabsf(to - at[i]));
                at[i] = to;
            }
            total += moveSeconds(worst, vmax, accel) + b.dwellMs * 0.001f;
        }
        return total;
    }

    // Trapezoid, or triangle if it never reaches vmax, plus a fixed allowance
    // for walking in the last few counts.
    //
    // That allowance started at 0.12 s, inferred from the 740 ms half-turn step
    // response against 625 ms of ideal profile. Measured against a real take on
    // 2026-08-31 it is 0.04 s: the short planned 9.8 s and ran 9.1 s over nine
    // moves. The step-response figure counts settling to a standstill, which a
    // beat does not wait for -- it only waits for the tolerance band.
    static constexpr float SETTLE_S = 0.04f;

    static float moveSeconds(float d, float vmax, float accel) {
        if (d <= 0.0f || vmax <= 0.0f || accel <= 0.0f) return 0.0f;
        float t = (d * accel <= vmax * vmax) ? 2.0f * sqrtf(d / accel)
                                            : d / vmax + vmax / accel;
        return t + SETTLE_S;
    }

    const Script *_sc = &BENCH;
    Axis _ax[MAXAXES];
    Saved _saved[MAXAXES];
    uint8_t _n = 0;
    bool _running = false;
    bool _arriving = false;
    uint8_t _i = 0;
    uint32_t _t0 = 0;
    uint32_t _startMs = 0;
    uint32_t _timeoutMs = 0;
    float _planned = 0;
    const char *_caption = "idle";
};

// ---------------------------------------------------------------- the scripts

// The bench run: one wheel, everything the axis can do, no clock on it. Only
// the `a` column is used -- it drives whichever wheel is selected, in that
// wheel's own frame, because single-wheel bring-up has no robot frame to be in.
//
// Nothing here goes past 1.0 turns/s. The axis is marginal by 2.0 and sheds
// steps at 2.76, and a take that faults halfway is a wasted take.
inline const Demo::Beat BENCH_BEATS[] = {
    // say                                                    turns    b dwell vmax accel slip
    {"zeroed here -- every move below is absolute",            0.00f, 0,  600, 0.5f, 6.0f, 200},
    {"quarter turns, slow enough to see each one stop",        0.25f, 0,  500, 0,    0,    0},
    {nullptr,                                                  0.50f, 0,  500, 0,    0,    0},
    {nullptr,                                                  0.75f, 0,  500, 0,    0,    0},
    {nullptr,                                                  1.00f, 0,  700, 0,    0,    0},
    {"one turn home in a single move",                         0.00f, 0,  800, 1.0f, 8.0f, 0},

    {"step response -- half a turn, there and back, twice",    0.50f, 0,  250, 0,    0,    0},
    {nullptr,                                                  0.00f, 0,  250, 0,    0,    0},
    {nullptr,                                                  0.50f, 0,  250, 0,    0,    0},
    {nullptr,                                                  0.00f, 0,  700, 0,    0,    0},

    // Slip detection off for this one. Back-driving the shaft by more than ~13
    // degrees is a stall as far as the loop is concerned, so a hand on the
    // wheel would fault it instantly at the normal limit.
    {"NOW PUSH THE WHEEL -- twist it, hold it, let go",        0.00f, 0, 9000, 0,    0,    200000},

    {"three turns at full speed",                              3.00f, 0,  600, 1.0f, 8.0f, 200},
    {"and back",                                               0.00f, 0,  800, 0,    0,    0},

    {"fine moves -- 0.01 turn each, 41 counts, 6.8 mm of rim", 0.01f, 0,  450, 0.2f, 4.0f, 0},
    {nullptr,                                                  0.02f, 0,  450, 0,    0,    0},
    {nullptr,                                                  0.03f, 0,  450, 0,    0,    0},
    {nullptr,                                                  0.04f, 0,  450, 0,    0,    0},
    {nullptr,                                                  0.05f, 0,  700, 0,    0,    0},

    {"home",                                                   0.00f, 0,  900, 1.0f, 8.0f, 0},
};

// The short: both wheels, one pattern, ~9.8 s planned. Written to be read
// without captions, because a ten-second clip has no room for them -- the
// shapes carry it, in three phases:
//
//   in phase      both wheels the same way, which is the robot driving
//   anti phase    the wheels opposing, which is the robot turning on the spot
//   canon         one wheel then the other, the same move offset in time --
//                 the phase that only means anything now there are two drivers
//
// Every move is 0.5 or 1.0 turns at 1.0 turns/s, well inside the measured
// envelope, and every wheel ends where it started so the closing report is a
// round-trip check as well as an outro.
inline const Demo::Beat SHORT_BEATS[] = {
    // say                                    A      B  dwell vmax accel slip
    {"two wheels, one bus, one script",     0.00f, 0.00f, 250, 1.0f, 8.0f, 200},

    {"in phase -- the robot drives",        1.00f, 1.00f, 150, 0,    0,    0},
    {"and back",                            0.00f, 0.00f, 150, 0,    0,    0},

    {"anti phase -- it turns on the spot",  0.50f,-0.50f, 150, 0,    0,    0},
    {"the other way",                      -0.50f, 0.50f, 150, 0,    0,    0},
    {"centre",                              0.00f, 0.00f, 150, 0,    0,    0},

    {"canon -- A leads, B answers",         0.50f, 0.00f, 120, 0,    0,    0},
    {nullptr,                               0.50f, 0.50f, 120, 0,    0,    0},
    {nullptr,                               0.00f, 0.50f, 120, 0,    0,    0},
    {"home, both of them",                  0.00f, 0.00f, 250, 0,    0,    0},
};

inline const Demo::Script Demo::BENCH = {
    "bench", BENCH_BEATS,
    (uint8_t)(sizeof(BENCH_BEATS) / sizeof(BENCH_BEATS[0])), false};

inline const Demo::Script Demo::SHORT = {
    "short", SHORT_BEATS,
    (uint8_t)(sizeof(SHORT_BEATS) / sizeof(SHORT_BEATS[0])), true};
