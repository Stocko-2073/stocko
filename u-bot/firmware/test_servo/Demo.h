#pragma once
#include "StepperServo.h"

// A choreographed run for the dev log: press 'm' and film it.
//
// Non-blocking on purpose. Calibration blocks and the CSV stream stops dead
// while it runs, which is fine for a measurement and useless for a video --
// this is driven from the control tick instead, so the stream keeps flowing and
// plot.py stays live in the corner of the shot.
//
// The script is the BEATS table below and nothing else. Each beat is an
// absolute target, how long to sit on it once arrived, and optional tuning for
// that segment; edit the table, not the runner. A caption is printed as it
// starts, so the serial log doubles as a shot list.
class Demo {
  public:
    // 0.165 mm of rim travel per encoder count, from DRIVE_MECHANISM.md. Only
    // used to say something human in the closing report.
    static constexpr float MM_PER_COUNT = 0.165f;

    struct Beat {
        const char *say;    // caption, printed when the beat starts
        float turns;        // absolute target, output turns
        uint16_t dwellMs;   // sit here this long after arriving
        float vmax;         // 0 keeps the current tuning
        float accel;        // 0 keeps the current tuning
        int32_t slipLimit;  // 0 keeps the current limit
    };

    // Nothing here goes past 1.0 turns/s. The axis is marginal by 2.0 and sheds
    // steps at 2.76, and a take that faults halfway is a wasted take.
    static const Beat BEATS[];
    static const uint8_t NBEATS;

    // Needs the driver already enabled -- energising a motor stays an explicit
    // act, not something a demo key does for you.
    bool start(StepperServo &s) {
        if (!s.driverEnabled()) return false;
        _savedVmax = s.vmaxTps;
        _savedAccel = s.accelTps2;
        _savedSlip = s.slipLimit;
        s.zeroHere();          // everything in the table is absolute from here
        s.servoOn(true);
        _i = 0;
        _running = true;
        applyBeat(s);
        return true;
    }

    void stop(StepperServo &s) {
        if (!_running) return;
        _running = false;
        restore(s);
        _caption = "stopped";
        Serial.println(F("# demo: stopped"));
    }

    bool running() const { return _running; }
    const char *caption() const { return _caption; }
    uint8_t beat() const { return _i; }

    void update(StepperServo &s) {
        if (!_running) return;

        // A fault or a dropped driver ends the take rather than limping on.
        if (s.fault() != StepperServo::FAULT_NONE) {
            Serial.printf("# demo: abandoned at beat %u -- %s\n",
                          (unsigned)(_i + 1), s.faultName());
            _running = false;
            restore(s);
            return;
        }
        if (!s.driverEnabled()) { stop(s); return; }

        uint32_t now = millis();
        if (_arriving) {
            if (!s.atTarget() && (now - _t0) < _timeoutMs) return;
            if (!s.atTarget()) {
                Serial.printf("# demo: beat %u timed out %ld counts short,"
                              " carrying on\n", (unsigned)(_i + 1),
                              (long)s.errorCounts());
            }
            _arriving = false;
            _t0 = now;
            return;
        }

        if ((now - _t0) < BEATS[_i].dwellMs) return;
        if (++_i >= NBEATS) { finish(s); return; }
        applyBeat(s);
    }

  private:
    void applyBeat(StepperServo &s) {
        const Beat &b = BEATS[_i];
        if (b.vmax > 0) s.vmaxTps = b.vmax;
        if (b.accel > 0) s.accelTps2 = b.accel;
        if (b.slipLimit != 0 && b.slipLimit != s.slipLimit) {
            // Crossing a slip-limit boundary means the reference is stale --
            // the hold beat lets the shaft be shoved a long way off the
            // commanded integral on purpose.
            s.slipLimit = b.slipLimit;
            s.resyncSlip();
        }
        if (b.say) {
            _caption = b.say;
            Serial.printf("# demo %u/%u: %s\n", (unsigned)(_i + 1),
                          (unsigned)NBEATS, b.say);
        }

        float from = s.positionTurns();
        s.moveToTurns(b.turns);

        // Twice the ideal traverse plus a floor, so a slow segment is never cut
        // short but a jammed one cannot hang the run.
        float dist = fabsf(b.turns - from);
        _timeoutMs = (uint32_t)(2000.0f * dist / fmaxf(s.vmaxTps, 0.05f)) + 1500;
        _arriving = true;
        _t0 = millis();
    }

    void finish(StepperServo &s) {
        _running = false;
        restore(s);
        _caption = "done";
        int32_t err = s.positionCounts();
        Serial.printf("# demo: done. Back at %+ld counts from where it started"
                      " (%.2f mm at the rim, %.2f deg)\n",
                      (long)err, err * MM_PER_COUNT,
                      err * 360.0f / StepperServo::COUNTS_PER_REV);
        Serial.println(F("# demo: loop still closed and holding -- 'x' to stop"));
    }

    void restore(StepperServo &s) {
        s.vmaxTps = _savedVmax;
        s.accelTps2 = _savedAccel;
        s.slipLimit = _savedSlip;
        s.resyncSlip();
    }

    bool _running = false;
    bool _arriving = false;
    uint8_t _i = 0;
    uint32_t _t0 = 0;
    uint32_t _timeoutMs = 0;
    const char *_caption = "idle";
    float _savedVmax = 1.0f;
    float _savedAccel = 8.0f;
    int32_t _savedSlip = 200;
};

// ---------------------------------------------------------------- the script

inline const Demo::Beat Demo::BEATS[] = {
    // say                                                    turns dwell vmax accel slip
    {"zeroed here -- every move below is absolute",            0.00f,  600, 0.5f, 6.0f, 200},
    {"quarter turns, slow enough to see each one stop",        0.25f,  500, 0,    0,    0},
    {nullptr,                                                  0.50f,  500, 0,    0,    0},
    {nullptr,                                                  0.75f,  500, 0,    0,    0},
    {nullptr,                                                  1.00f,  700, 0,    0,    0},
    {"one turn home in a single move",                         0.00f,  800, 1.0f, 8.0f, 0},

    {"step response -- half a turn, there and back, twice",    0.50f,  250, 0,    0,    0},
    {nullptr,                                                  0.00f,  250, 0,    0,    0},
    {nullptr,                                                  0.50f,  250, 0,    0,    0},
    {nullptr,                                                  0.00f,  700, 0,    0,    0},

    // Slip detection off for this one. Back-driving the shaft by more than ~13
    // degrees is a stall as far as the loop is concerned, so a hand on the
    // wheel would fault it instantly at the normal limit.
    {"NOW PUSH THE WHEEL -- twist it, hold it, let go",        0.00f, 9000, 0,    0,    200000},

    {"three turns at full speed",                              3.00f,  600, 1.0f, 8.0f, 200},
    {"and back",                                               0.00f,  800, 0,    0,    0},

    {"fine moves -- 0.01 turn each, 41 counts, 6.8 mm of rim", 0.01f,  450, 0.2f, 4.0f, 0},
    {nullptr,                                                  0.02f,  450, 0,    0,    0},
    {nullptr,                                                  0.03f,  450, 0,    0,    0},
    {nullptr,                                                  0.04f,  450, 0,    0,    0},
    {nullptr,                                                  0.05f,  700, 0,    0,    0},

    {"home",                                                   0.00f,  900, 1.0f, 8.0f, 0},
};

inline const uint8_t Demo::NBEATS = sizeof(Demo::BEATS) / sizeof(Demo::BEATS[0]);
