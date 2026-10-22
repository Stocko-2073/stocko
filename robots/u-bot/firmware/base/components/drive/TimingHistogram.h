#pragma once
#include <stdint.h>
#include <string.h>

// Durations in microseconds, binned so p50 and p99 come out without keeping
// the samples: four buckets per octave, so no bucket is more than 25% wide,
// exact below 8 us, and everything from ~131 ms up in the last one. The
// maximum is kept exactly.
//
// add() is cheap enough to call on every control tick. A reader on another
// task can see the counts a sample apart, which statistics do not mind, so
// there is no lock.
class TimingHistogram {
  public:
    static constexpr int BUCKETS = 64;

    void add(uint32_t us) {
        _n[bucket(us)]++;
        _count++;
        if (us > _max) _max = us;
    }
    void reset() {
        memset(_n, 0, sizeof _n);
        _count = 0;
        _max = 0;
    }
    uint32_t count() const { return _count; }
    uint32_t max() const { return _max; }

    // An upper bound on the p-th fraction of the samples (0.5 for the median):
    // the top of the bucket it falls in, never above the maximum. 0 when there
    // are no samples.
    uint32_t percentile(double p) const {
        uint32_t n[BUCKETS];
        memcpy(n, _n, sizeof n);   // one view, even while add() runs elsewhere
        uint32_t total = 0;
        for (uint32_t v : n) total += v;
        if (!total) return 0;
        const double x = p * total;
        uint32_t want = (uint32_t)x;
        if (want < x) want++;
        if (want < 1) want = 1;
        if (want > total) want = total;
        uint32_t cum = 0;
        for (int b = 0; b < BUCKETS; b++) {
            cum += n[b];
            if (cum < want) continue;
            const uint32_t top = b == BUCKETS - 1 ? _max : upper(b);
            return top < _max ? top : _max;
        }
        return _max;
    }

    // Values 0..3 have a bucket each. From 4 up, the octave [2^o, 2^(o+1)) is
    // split in four by the two bits after the leading one.
    static int bucket(uint32_t us) {
        if (us < 4) return (int)us;
        const int o = 31 - __builtin_clz(us);
        const int b = 4 * (o - 1) + (int)((us >> (o - 2)) & 3);
        return b < BUCKETS ? b : BUCKETS - 1;
    }
    // The largest value that lands in bucket b (the last one has no top).
    static uint32_t upper(int b) {
        if (b < 4) return (uint32_t)b;
        const int o = b / 4 + 1, sub = b % 4;
        return ((uint32_t)(5 + sub) << (o - 2)) - 1;
    }

  private:
    uint32_t _n[BUCKETS] = {};
    uint32_t _count = 0;
    uint32_t _max = 0;
};
