#undef NDEBUG   // these asserts are the test
#include <cassert>
#include <cstdio>
#include "TimingHistogram.h"

// The log-bucket histogram behind 'stats': buckets that tile the range in
// order, no wider than 25%, and percentiles that are honest upper bounds.

using H = TimingHistogram;

int main() {
    // Every value lands in a bucket whose top is at or above it, the buckets
    // run in order without gaps, and none is more than a quarter of its bottom
    // wide (exact below 8 us).
    int prev = 0;
    uint32_t bottom = 0;
    for (uint32_t us = 0; us < 300000; us++) {
        const int b = H::bucket(us);
        assert(b >= 0 && b < H::BUCKETS);
        assert(b == prev || b == prev + 1);
        if (b != prev) {
            assert(H::upper(prev) == us - 1);   // the last bucket ended just below
            bottom = us;
        }
        prev = b;
        if (b < H::BUCKETS - 1) {
            assert(H::upper(b) >= us);
            if (us < 8) assert(H::upper(b) == us);
            else assert((H::upper(b) + 1 - bottom) * 4 <= bottom);
        }
    }
    assert(H::bucket(0xFFFFFFFFu) == H::BUCKETS - 1 && H::bucket(131072) == H::BUCKETS - 1);
    assert(H::bucket(131071) == H::BUCKETS - 1 && H::upper(H::BUCKETS - 2) == (7u << 14) - 1);   // the last spans 114688..

    // Empty: nothing to say.
    H h;
    assert(h.count() == 0 && h.max() == 0 && h.percentile(0.5) == 0 && h.percentile(0.99) == 0);

    // One value: every percentile is that value, never the top of its bucket.
    h.add(3100);
    assert(h.count() == 1 && h.max() == 3100);
    assert(h.percentile(0.5) == 3100 && h.percentile(0.99) == 3100 && h.percentile(0) == 3100);

    // 1..1000 us: bounds within a bucket of the truth, max exact.
    h.reset();
    assert(h.count() == 0 && h.max() == 0);
    for (uint32_t us = 1; us <= 1000; us++) h.add(us);
    const uint32_t p50 = h.percentile(0.5), p99 = h.percentile(0.99);
    assert(p50 >= 500 && p50 <= 625);
    assert(p99 >= 990 && p99 <= 1000);
    assert(h.max() == 1000 && h.count() == 1000 && h.percentile(1.0) == 1000);

    // A tick profile: mostly ~1.2 ms, 1% at ~4 ms, one 9 ms outlier.
    h.reset();
    for (int i = 0; i < 9900; i++) h.add(1150 + i % 100);
    for (int i = 0; i < 99; i++) h.add(4000);
    h.add(9000);
    assert(h.percentile(0.5) >= 1199 && h.percentile(0.5) < 1500);
    assert(h.percentile(0.99) >= 1249 && h.percentile(0.99) < 1600);   // 9900/10000 exactly: still the body
    assert(h.percentile(0.995) >= 4000 && h.percentile(0.995) < 5000);
    assert(h.max() == 9000 && h.percentile(1.0) == 9000);

    // Past the last bucket's bottom, the max is the answer.
    h.reset();
    h.add(500000);
    h.add(400000);
    assert(h.percentile(0.5) == 500000 && h.percentile(0.99) == 500000);

    puts("PASS: timing histogram: ordered gapless buckets <= 25% wide, exact below 8 us, overflow bucket, "
         "percentiles as upper bounds capped at the max, reset");
    return 0;
}
