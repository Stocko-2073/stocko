#include <cassert>
#include <cmath>
#include <cstdio>
#include <initializer_list>
#include "StallDetector.h"

// Synthetic streams, no plant: a command and an output shaft in motor
// microsteps, handed to the detector the way the servo samples them each tick.
static const double STEPS_PER_TURN = 200.0 * 8.0 * 40.0 / 12.0;   // 5333.3
static const double SPC = STEPS_PER_TURN / 4096.0;                 // microsteps per count
static const float DT = 0.005f;
static const double D = 400, L = 40;
static const double X_TRIP = -D * log(1.0 - L / D);                 // 42.14 microsteps

struct Wheel {
    StallDetector det;
    double cmd = 0;      // commanded integral
    double shaft = 0;    // true output shaft, in motor microsteps
    double inlA = 0, inlK = 0;   // encoder error: inlA sin(inlK shaft)
    double seen = 0;     // what the servo's position holds: frozen while the encoder is down
    uint32_t epoch = 0;
    bool encOk = true, velMode = true;

    Wheel() { det.configure(StallConfig()); }

    StallSample tick(double dcmd, double dshaft, float dt = DT) {
        cmd += dcmd;
        shaft += dshaft;
        if (encOk) seen = shaft + inlA * sin(inlK * shaft);
        StallInput in;
        in.cmdSteps = cmd;
        in.rawLag = (float)(cmd - seen);   // unquantized: this is a test of the math
        in.encCounts = (int32_t)lround(seen / SPC);
        in.epoch = epoch;
        in.encOk = encOk;
        in.velMode = velMode;
        in.dt = dt;
        return det.update(in);
    }
    // As StepperServo::resyncSlip(): the commanded integral jumps to the encoder.
    void resync() { cmd = seen; epoch++; }
};

static double perTick(double tps) { return tps * STEPS_PER_TURN * DT; }

// Run in sync until armed, then let go of the field: the shaft stops dead.
// Returns the commanded travel at the tick that tripped and, interpolated
// between that tick and the one before, where the lag actually crossed L.
struct Trip { double tick, crossing, ms; };
static Trip stallTrip(double tps, int sign) {
    Wheel w;
    const double v = perTick(tps) * sign;
    StallSample s = {};
    for (int i = 0; i < 400; i++) {
        s = w.tick(v, v);
        assert(s.trip == 0);
    }
    assert(s.armed && fabsf(s.lag) < 1e-3f);
    double travel = 0, prevTravel = 0;
    float prevLag = s.lag;
    for (int i = 0; i < 100000; i++) {
        s = w.tick(v, 0);
        travel += fabs(v);
        if (s.trip) {
            assert(s.trip == +1);   // behind, whichever way it was going
            assert(prevLag <= L && s.lag > L);   // fired on the first tick past the level
            double crossing = prevTravel + (L - prevLag) / (s.lag - prevLag) * (travel - prevTravel);
            return {travel, crossing, 1000.0 * crossing / fabs(v / DT)};
        }
        prevLag = s.lag;
        prevTravel = travel;
    }
    assert(!"a full stall never tripped");
    return {};
}

// Where lag settles with the shaft running (1 + eps) times the command.
static float clockLag(double eps, int sign) {
    Wheel w;
    const double v = perTick(0.5) * sign;
    StallSample s = {};
    for (int i = 0; i < 4000; i++) {   // 10 turns, ~130 leak lengths
        s = w.tick(v, v * (1.0 + eps));
        assert(s.trip == 0);
    }
    return s.lag;
}

// Amplitude of the lag an INL harmonic produces, over the INL's own amplitude.
static double inlGain(int h) {
    Wheel w;
    w.inlA = 13.0;   // ~10 counts: the AS5600's ~20 counts p-p
    w.inlK = 2.0 * M_PI * h / STEPS_PER_TURN;
    const int PER_TURN = 640;   // whole turns in whole ticks, so the projection is clean
    const double v = STEPS_PER_TURN / PER_TURN;
    double sn = 0, cs = 0;
    int n = 0;
    for (int i = 0; i < 7 * PER_TURN; i++) {
        StallSample s = w.tick(v, v);
        assert(s.trip == 0);
        if (i < 3 * PER_TURN) continue;   // let the start transient go
        sn += s.lag * sin(w.inlK * w.shaft);
        cs += s.lag * cos(w.inlK * w.shaft);
        n++;
    }
    return 2.0 / n * sqrt(sn * sn + cs * cs) / w.inlA;
}

// Output shaft in the gear play: dragged at one flank or the other, standing
// still while the motor crosses the gap after a reversal.
enum Shape { SINE, SQUARE, DWELL };
static float reversals(double b, double tps, Shape shape, uint32_t *trips) {
    Wheel w;
    w.shaft = -b / 2;
    const double vmax = perTick(tps);
    float worst = 0;
    for (int i = 0; i < 2000; i++) {   // 10 s: five 2 s periods
        double ph = fmod(i * DT, 2.0);
        double v = shape == SINE ? vmax * sin(M_PI * ph)
                 : shape == SQUARE ? (ph < 1.0 ? vmax : -vmax)
                 : (ph < 0.8 ? vmax : ph < 1.0 ? 0 : ph < 1.8 ? -vmax : 0);
        double motor = w.cmd + v;
        double out = fmin(fmax(w.shaft, motor - b / 2), motor + b / 2);
        StallSample s = w.tick(v, out - w.shaft);
        if (fabsf(s.lag) > worst) worst = fabsf(s.lag);
    }
    *trips = w.det.trips();
    return worst;
}

int main() {
    // --- the full stall: ~42 microsteps of travel at any speed ---
    for (double tps : {0.02, 0.05, 0.1, 0.2, 0.5, 1.0}) {
        for (int sign : {+1, -1}) {
            Trip t = stallTrip(tps, sign);
            assert(fabs(t.crossing - X_TRIP) <= 2.0);
            assert(t.tick >= t.crossing && t.tick - t.crossing < perTick(tps) + 1e-9);
            if (sign > 0) {
                printf("stall at %.2f turns/s: level crossed after %.1f microsteps (%.0f ms), "
                       "tripped on the tick at %.1f\n", tps, t.crossing, t.ms, t.tick);
            }
        }
    }

    // --- clock gain error: lag settles at -eps*D, either direction ---
    for (double eps : {0.003, -0.003, 0.01}) {
        for (int sign : {+1, -1}) {
            float lag = clockLag(eps, sign);
            assert(fabs(lag - (-eps * D)) <= 0.01 * fabs(eps * D));
        }
    }
    printf("clock gain +0.3%%: lag settles at %.3f microsteps (-eps*D = %.3f)\n",
           clockLag(0.003, +1), -0.003 * D);

    // --- INL through the distance high-pass ---
    for (int h : {1, 2}) {
        double w = 2.0 * M_PI * h / STEPS_PER_TURN;
        double expect = w * D / sqrt(1.0 + w * w * D * D);
        double got = inlGain(h);
        assert(fabs(got / expect - 1.0) <= 0.05);
        printf("INL harmonic %d: gain %.4f, formula %.4f\n", h, got, expect);
    }

    // --- backlash under the settle never trips; far past it, it does ---
    for (double b : {0.0, 8.0, 24.0, 40.0, 47.0}) {
        for (double tps : {0.02, 0.1, 0.3, 1.0}) {
            for (Shape sh : {SINE, SQUARE, DWELL}) {
                uint32_t trips = 0;
                float worst = reversals(b, tps, sh, &trips);
                assert(trips == 0);
                assert(worst < 1.0f);
            }
        }
    }
    {
        uint32_t trips = 0;
        reversals(48.0 + 80.0, 0.3, SQUARE, &trips);
        assert(trips > 0);   // the check above can fail
    }

    // --- an encoder dropout freezes the reference ---
    {
        Wheel w;
        const double v = perTick(0.3);
        StallSample s = {};
        for (int i = 0; i < 200; i++) s = w.tick(v, v);
        assert(s.armed && s.rotorCps > 0);
        w.encOk = false;
        for (int i = 0; i < 30; i++) {   // 150 ms: raw counts ~240 microsteps against a frozen shaft
            s = w.tick(v, v);
            assert(!s.armed && s.trip == 0 && s.lag == 0 && s.rotorCps == 0);
        }
        w.encOk = true;
        s = w.tick(v, v);   // the servo's position catches up in one read
        assert(s.armed && s.trip == 0 && fabsf(s.lag) < 0.01f);
        assert(s.rotorCps == 0);   // nothing to difference yet: the ring restarted
        s = w.tick(v, v);
        assert(fabs(s.rotorCps - v / DT / SPC) < 0.05 * v / DT / SPC);
        assert(w.det.trips() == 0);

        Wheel st;   // ...and a shaft that stalled inside the gap is caught on the first good read
        for (int i = 0; i < 200; i++) st.tick(v, v);
        st.encOk = false;
        for (int i = 0; i < 10; i++) assert(st.tick(v, 0).trip == 0);
        st.encOk = true;
        assert(st.tick(v, 0).trip == +1);
    }

    // --- a resync re-anchors, and its jump in the integral is not travel ---
    {
        Wheel w;
        const double v = perTick(0.3);
        StallSample s = {};
        for (int i = 0; i < 2000; i++) s = w.tick(v, v * 1.01);   // raw drifts to ~-160
        assert(s.armed && fabsf(s.lag + 4.0f) < 0.1f && w.cmd - w.seen < -150);
        w.resync();   // the integral jumps ~160 microsteps; lag would jump +160
        s = w.tick(v, v * 1.01);
        assert(!s.armed && s.trip == 0 && s.dir == 0);
        double travel = 0;
        do {
            s = w.tick(v, v * 1.01);
            travel += v;
            assert(s.trip == 0);
        } while (!s.armed);
        assert(travel > 48 - 0.01 && travel < 48 + v + 0.01);   // a full settle, not spent by the jump
        assert(w.det.trips() == 0);
    }

    // --- stopped, or not in velocity mode, is disarmed ---
    {
        Wheel w;
        const double v = perTick(0.3);
        for (int i = 0; i < 200; i++) w.tick(v, v);
        for (int i = 0; i < 400; i++) {   // standing still while the shaft is shoved
            StallSample s = w.tick(0, 2.0);
            assert(!s.armed && s.dir == 0 && s.lag == 0 && s.trip == 0);
        }
        w.velMode = false;
        for (int i = 0; i < 400; i++) {   // moving, but position mode: not ours
            StallSample s = w.tick(v, 0);
            assert(!s.armed && s.trip == 0);
        }
        w.velMode = true;
        StallSample s = w.tick(v, v);
        assert(!s.armed && s.dir == +1);   // back in velocity mode: a fresh start, settling
        assert(w.det.trips() == 0);
    }

    // --- sign: shaft ahead of the command is a LEAD, either direction ---
    for (int sign : {+1, -1}) {
        Wheel w;
        const double v = perTick(0.3) * sign;
        for (int i = 0; i < 200; i++) w.tick(v, v);
        StallSample s = {};
        int n = 0;
        do { s = w.tick(v, 2.0 * v); n++; } while (!s.trip && n < 1000);   // pushed along
        assert(s.trip == -1 && s.lag < -L);
    }

    // --- the trip is an edge, latched until re-anchored; counters ---
    {
        Wheel w;
        const double v = perTick(0.3);
        for (int i = 0; i < 200; i++) w.tick(v, v);
        int edges = 0;
        for (int i = 0; i < 400; i++) edges += w.tick(v, 0).trip != 0;
        assert(edges == 1 && w.det.trips() == 1 && w.det.worstLag() > 300);
        w.det.resetWorst();
        assert(w.det.worstLag() == 0);
        w.det.reanchor();
        StallSample s = w.tick(v, 0);
        assert(!s.armed);   // settling again
        edges = 0;
        for (int i = 0; i < 400; i++) edges += w.tick(v, 0).trip != 0;
        assert(edges == 1 && w.det.trips() == 2);
    }

    // --- lag_trip 0 is off: a full stall never trips ---
    {
        Wheel w;
        w.det.configure(StallConfig{0, 400, 48});
        const double v = perTick(0.3);
        for (int i = 0; i < 200; i++) w.tick(v, v);
        for (int i = 0; i < 2000; i++) {
            StallSample s = w.tick(v, 0);
            assert(!s.armed && s.trip == 0 && s.lag == 0);
        }
        assert(w.det.trips() == 0);
    }

    // --- rotor velocity: the boxcar, the actual time spanned, a fresh ring ---
    {
        StallDetector d;
        StallInput in = {0, 0, 0, 0, true, true, DT};
        assert(d.update(in).rotorCps == 0);   // one sample is no velocity
        in.encCounts += 5;
        assert(d.update(in).rotorCps == 1000.0f);
        for (int i = 0; i < 8; i++) {
            in.encCounts += 5;
            in.dt = (i & 1) ? 0.004f : 0.006f;   // jitter: still 5 counts per 5 ms on average
            float c = d.update(in).rotorCps;
            if (i >= 3) assert(fabsf(c - 1000.0f) < 0.5f);
        }
        in.dt = DT;
        float c = 0;
        for (int i = 0; i < StallDetector::WINDOW; i++) {   // step to 2000 counts/s
            in.encCounts += 10;
            c = d.update(in).rotorCps;
            if (i < StallDetector::WINDOW - 1) assert(c > 1000.0f && c < 2000.0f);
        }
        assert(fabsf(c - 2000.0f) < 0.5f);   // the whole window has moved over
        in.encCounts -= 60;   // backwards, and a partial window after a gap
        in.encOk = false;
        assert(d.update(in).rotorCps == 0);
        in.encOk = true;
        d.update(in);
        in.encCounts -= 6;
        assert(fabsf(d.update(in).rotorCps + 1200.0f) < 0.5f);
    }

    // --- configuration ---
    assert(StallConfig().valid());
    assert((StallConfig{0, 0, -1}).valid());   // off: nothing else is used
    assert((StallConfig{16, 100, 0}).valid());
    assert(!(StallConfig{15, 400, 48}).valid());
    assert((StallConfig{320, 400, 48}).valid());
    assert(!(StallConfig{321, 400, 48}).valid());   // above 0.8 D
    assert(!(StallConfig{40, 99, 48}).valid());
    assert(!(StallConfig{40, 400, -1}).valid());
    assert(!(StallConfig{NAN, 400, 48}).valid());
    assert(!(StallConfig{40, INFINITY, 48}).valid());
    assert(!(StallConfig{40, 400, NAN}).valid());
    {
        StallDetector d;
        d.configure(StallConfig{10, 400, 48});   // refused, keeps the default
        assert(d.config().tripSteps == 40);
        d.configure(StallConfig{60, 400, 30});
        assert(d.config().tripSteps == 60 && d.config().settleSteps == 30);
    }

    puts("PASS: stall trips at ~42 microsteps at 0.02-1.0 turns/s, clock gain -eps*D, INL high-pass gain, "
         "backlash under the settle, encoder dropout freeze, resync re-anchor, disarmed when stopped, "
         "LEAD sign, edge latch, off switch, rotor velocity window, config validity");
    return 0;
}
