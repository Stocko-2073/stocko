// Host tests for the battery model: the pack tables, the threshold ranges and
// how overrides resolve, the low/cutoff monitor, and the misconfiguration
// hint. Built and run by run_host_tests.py under ASan and UBSan.
#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

#include "battery_model.h"

static int checks, failures;

static void check(bool ok, const char *what, int line) {
    checks++;
    if (ok) return;
    failures++;
    fprintf(stderr, "test_battery_model.c:%d: FAILED %s\n", line, what);
}

static void check_int(long got, long want, const char *what, int line) {
    checks++;
    if (got == want) return;
    failures++;
    fprintf(stderr, "test_battery_model.c:%d: %s is %ld, expected %ld\n", line, what, got, want);
}

static void check_str(const char *got, const char *want, const char *what, int line) {
    checks++;
    if (got && !strcmp(got, want)) return;
    failures++;
    fprintf(stderr, "test_battery_model.c:%d: %s is \"%s\", expected \"%s\"\n", line, what,
            got ? got : "(null)", want);
}

#define CHECK(cond) check((cond), #cond, __LINE__)
#define CHECK_INT(got, want) check_int((long)(got), (long)(want), #got, __LINE__)
#define CHECK_STR(got, want) check_str((got), (want), #got, __LINE__)

// ------------------------------------------------------------------ tables

// The percentage code as it stood before 5S support, table and all, copied
// from battery.c: the reference that lfp4s did not move.
static const struct { float v; uint8_t pct; } OLD_LFP[] = {
    {10.0f, 0}, {12.0f, 9}, {12.5f, 14}, {12.8f, 17}, {12.9f, 20}, {13.0f, 30},
    {13.1f, 40}, {13.2f, 70}, {13.3f, 90}, {13.4f, 99}, {13.6f, 100},
};

static int old_lfp_percent(float v) {
    const size_t n = sizeof OLD_LFP / sizeof OLD_LFP[0];
    if (v <= OLD_LFP[0].v) return OLD_LFP[0].pct;
    if (v >= OLD_LFP[n - 1].v) return OLD_LFP[n - 1].pct;
    for (size_t i = 1; i < n; i++) {
        if (v <= OLD_LFP[i].v) {
            float t = (v - OLD_LFP[i - 1].v) / (OLD_LFP[i].v - OLD_LFP[i - 1].v);
            return (int)lroundf(OLD_LFP[i - 1].pct + t * (OLD_LFP[i].pct - OLD_LFP[i - 1].pct));
        }
    }
    return OLD_LFP[n - 1].pct;
}

static bool near(float a, float b) { return fabsf(a - b) < 1e-4f; }

// Readings from `lo` to `hi` in 1 mV steps never lower the percentage and
// stay in 0..100.
static void check_monotonic(const batt_pack_t *p, float lo, float hi, int line) {
    int prev = -1, bad = 0;
    long steps = lroundf((hi - lo) * 1000.0f);
    for (long i = 0; i <= steps; i++) {
        int pct = batt_percent(p, lo + (float)i * 0.001f);
        if (pct < prev || pct < 0 || pct > 100) bad++;
        prev = pct;
    }
    check_int(bad, 0, "non-monotonic or out-of-range percentages", line);
}

static void test_profiles(void) {
    int count = 0;
    for (size_t i = 0; batt_pack_at(i); i++) {
        const batt_pack_t *p = batt_pack_at(i);
        count++;
        CHECK(p->name && *p->name && p->label && *p->label);
        CHECK(batt_pack_find(p->name) == p);
        CHECK(p->n >= 2);
        CHECK_INT(p->table[0].pct, 0);
        CHECK_INT(p->table[p->n - 1].pct, 100);
        for (size_t j = 1; j < p->n; j++) {
            CHECK(p->table[j].v > p->table[j - 1].v);
            CHECK(p->table[j].pct >= p->table[j - 1].pct);
        }
        CHECK(p->hyst_v > 0.0f);
        CHECK(batt_thresholds_valid(p, p->warn_v, p->cut_v));
        // The profile's cut sits inside its own override range.
        CHECK(p->min_cut_v <= p->cut_v && p->cut_v <= p->max_cut_v);
        CHECK(p->warn_v <= p->max_warn_v);
    }
    CHECK_INT(count, 2);
    CHECK(batt_pack_at(2) == NULL);
    CHECK(batt_pack_at(SIZE_MAX) == NULL);

    const batt_pack_t *li = &BATT_LI5S;
    CHECK_STR(li->name, "li5s");
    CHECK_STR(li->label, "5S Li-ion");
    CHECK_INT(li->cells, 5);
    CHECK(li->warn_v == 16.5f && li->cut_v == 15.5f && li->hyst_v == 0.5f);
    CHECK(near(li->warn_v / li->cells, 3.3f) && near(li->cut_v / li->cells, 3.1f));
    CHECK(li->min_cut_v == 12.5f && li->max_cut_v == 20.0f && li->max_warn_v == 20.5f);

    const batt_pack_t *lfp = &BATT_LFP4S;
    CHECK_STR(lfp->name, "lfp4s");
    CHECK_STR(lfp->label, "4S LiFePO4");
    CHECK_INT(lfp->cells, 4);
    CHECK(lfp->warn_v == 12.4f && lfp->cut_v == 11.6f && lfp->hyst_v == 0.4f);
    CHECK(lfp->min_cut_v == 10.0f && lfp->max_cut_v == 13.0f && lfp->max_warn_v == 13.4f);
}

static void test_li5s_percent(void) {
    const batt_pack_t *p = &BATT_LI5S;
    static const struct { float v; int pct; } points[] = {
        {15.0f, 0}, {16.0f, 2}, {16.5f, 4}, {17.0f, 8}, {17.5f, 14}, {18.0f, 25},
        {18.5f, 42}, {19.0f, 57}, {19.5f, 69}, {20.0f, 80}, {20.5f, 90}, {21.0f, 100},
    };
    for (size_t i = 0; i < sizeof points / sizeof points[0]; i++)
        CHECK_INT(batt_percent(p, points[i].v), points[i].pct);
    // This morning's reading from the pack the robot now carries.
    CHECK_INT(batt_percent(p, 19.97f), 79);
    // Interpolated between points.
    CHECK_INT(batt_percent(p, 18.25f), 34);
    CHECK_INT(batt_percent(p, 15.5f), 1);
    // Clamped at both ends; NaN and nothing read as empty.
    CHECK_INT(batt_percent(p, 14.99f), 0);
    CHECK_INT(batt_percent(p, 13.1f), 0);
    CHECK_INT(batt_percent(p, 0.0f), 0);
    CHECK_INT(batt_percent(p, -3.0f), 0);
    CHECK_INT(batt_percent(p, -INFINITY), 0);
    CHECK_INT(batt_percent(p, NAN), 0);
    CHECK_INT(batt_percent(p, 21.01f), 100);
    CHECK_INT(batt_percent(p, 30.0f), 100);
    CHECK_INT(batt_percent(p, INFINITY), 100);
    check_monotonic(p, 10.0f, 25.0f, __LINE__);
    // No table, no percentage.
    CHECK_INT(batt_percent(NULL, 19.97f), -1);
    batt_pack_t empty = BATT_LI5S;
    empty.n = 0;
    CHECK_INT(batt_percent(&empty, 19.97f), -1);
}

static void test_lfp4s_percent(void) {
    const batt_pack_t *p = &BATT_LFP4S;
    // Every point of the old table reads what it always read...
    for (size_t i = 0; i < sizeof OLD_LFP / sizeof OLD_LFP[0]; i++)
        CHECK_INT(batt_percent(p, OLD_LFP[i].v), OLD_LFP[i].pct);
    // ...and so does everything in between, to the millivolt.
    int differ = 0;
    for (int i = 0; i <= 8000; i++) {
        float v = 8.0f + (float)i * 0.001f;
        if (batt_percent(p, v) != old_lfp_percent(v)) differ++;
    }
    CHECK_INT(differ, 0);
    CHECK_INT(batt_percent(p, 9.0f), 0);
    CHECK_INT(batt_percent(p, 14.6f), 100);
    CHECK_INT(batt_percent(p, 12.4f), 13);   // the warning
    CHECK_INT(batt_percent(p, 11.6f), 7);    // the cutoff
    check_monotonic(p, 8.0f, 16.0f, __LINE__);
    // The one deliberate change: NaN used to fall through to 100%.
    CHECK_INT(batt_percent(p, NAN), 0);
    CHECK_INT(old_lfp_percent(NAN), 100);
}

// -------------------------------------------------------------- thresholds

static void test_thresholds(void) {
    const batt_pack_t *li = &BATT_LI5S, *lfp = &BATT_LFP4S;
    CHECK(batt_thresholds_valid(li, 16.5f, 15.5f));
    // cut 12.5..20.0
    CHECK(batt_thresholds_valid(li, 16.5f, 12.5f));
    CHECK(!batt_thresholds_valid(li, 16.5f, 12.49f));
    CHECK(batt_thresholds_valid(li, 20.5f, 20.0f));
    CHECK(!batt_thresholds_valid(li, 20.5f, 20.01f));
    // warn up to 20.5, and above cut
    CHECK(batt_thresholds_valid(li, 20.5f, 15.5f));
    CHECK(!batt_thresholds_valid(li, 20.51f, 15.5f));
    CHECK(!batt_thresholds_valid(li, 16.0f, 16.0f));
    CHECK(!batt_thresholds_valid(li, 15.0f, 16.0f));
    CHECK(batt_thresholds_valid(li, 15.51f, 15.5f));
    // The bench sequence that forces low then cutoff with a charged pack only
    // works in that order: the cut cannot pass the warning.
    CHECK(batt_thresholds_valid(li, 20.5f, 15.5f) && batt_thresholds_valid(li, 20.5f, 20.0f));
    CHECK(!batt_thresholds_valid(li, 16.5f, 20.0f));
    // Not numbers.
    CHECK(!batt_thresholds_valid(li, NAN, 15.5f));
    CHECK(!batt_thresholds_valid(li, 16.5f, NAN));
    CHECK(!batt_thresholds_valid(li, INFINITY, 15.5f));
    CHECK(!batt_thresholds_valid(li, 16.5f, -INFINITY));
    CHECK(!batt_thresholds_valid(NULL, 16.5f, 15.5f));

    CHECK(batt_thresholds_valid(lfp, 12.4f, 11.6f));
    CHECK(batt_thresholds_valid(lfp, 12.4f, 10.0f));
    CHECK(!batt_thresholds_valid(lfp, 12.4f, 9.99f));
    CHECK(batt_thresholds_valid(lfp, 13.4f, 13.0f));
    CHECK(!batt_thresholds_valid(lfp, 13.4f, 13.01f));
    CHECK(!batt_thresholds_valid(lfp, 13.41f, 11.6f));
    CHECK(!batt_thresholds_valid(lfp, 11.6f, 11.6f));
    // One pack's numbers are not the other's.
    CHECK(!batt_thresholds_valid(lfp, 16.5f, 15.5f));
    CHECK(!batt_thresholds_valid(li, 12.4f, 11.6f));
}

static void test_resolve(void) {
    const batt_pack_t *li = &BATT_LI5S;
    batt_thresholds_t t = batt_thresholds_resolve(li, NULL, NULL);
    CHECK(t.warn_v == 16.5f && t.cut_v == 15.5f && !t.warn_ignored && !t.cut_ignored);

    float w = 20.5f, c = 20.0f;
    t = batt_thresholds_resolve(li, &w, &c);
    CHECK(t.warn_v == 20.5f && t.cut_v == 20.0f && !t.warn_ignored && !t.cut_ignored);
    t = batt_thresholds_resolve(li, &w, NULL);
    CHECK(t.warn_v == 20.5f && t.cut_v == 15.5f && !t.warn_ignored && !t.cut_ignored);
    // A cut left behind after its warn was unset: above the default warning,
    // so it is ignored and the robot is back on the profile's pair.
    t = batt_thresholds_resolve(li, NULL, &c);
    CHECK(t.warn_v == 16.5f && t.cut_v == 15.5f && !t.warn_ignored && t.cut_ignored);
    c = 16.0f;
    t = batt_thresholds_resolve(li, NULL, &c);
    CHECK(t.warn_v == 16.5f && t.cut_v == 16.0f && !t.warn_ignored && !t.cut_ignored);
    // Out of range on their own.
    c = 12.4f;
    t = batt_thresholds_resolve(li, NULL, &c);
    CHECK(t.warn_v == 16.5f && t.cut_v == 15.5f && t.cut_ignored && !t.warn_ignored);
    w = 20.6f;
    t = batt_thresholds_resolve(li, &w, NULL);
    CHECK(t.warn_v == 16.5f && t.cut_v == 15.5f && t.warn_ignored && !t.cut_ignored);
    w = 12.5f;   // at the lowest cut: nothing could sit below it
    t = batt_thresholds_resolve(li, &w, NULL);
    CHECK(t.warn_ignored && t.warn_v == 16.5f);
    // A bad cut does not take a good warn with it...
    w = 17.0f; c = 25.0f;
    t = batt_thresholds_resolve(li, &w, &c);
    CHECK(t.warn_v == 17.0f && t.cut_v == 15.5f && !t.warn_ignored && t.cut_ignored);
    // ...but two that contradict each other are both dropped.
    w = 16.0f; c = 17.0f;
    t = batt_thresholds_resolve(li, &w, &c);
    CHECK(t.warn_v == 16.5f && t.cut_v == 15.5f && t.warn_ignored && t.cut_ignored);
    w = NAN;
    t = batt_thresholds_resolve(li, &w, NULL);
    CHECK(t.warn_ignored && t.warn_v == 16.5f);
    t = batt_thresholds_resolve(NULL, NULL, NULL);
    CHECK(t.warn_v == 0.0f && t.cut_v == 0.0f);

    // Whatever is stored, the result is a pair the profile accepts; an
    // override is either in force or flagged; nothing absent is flagged.
    static const float values[] = {-INFINITY, 0.0f, 9.0f, 10.0f, 11.6f, 12.4f, 12.5f, 13.0f, 13.4f,
                                   15.5f, 16.0f, 16.5f, 17.0f, 20.0f, 20.5f, 21.0f, INFINITY, NAN};
    const size_t nv = sizeof values / sizeof values[0];
    int bad = 0;
    for (size_t pi = 0; batt_pack_at(pi); pi++) {
        const batt_pack_t *p = batt_pack_at(pi);
        for (size_t i = 0; i <= nv; i++) {
            for (size_t j = 0; j <= nv; j++) {
                const float *wp = i < nv ? &values[i] : NULL;
                const float *cp = j < nv ? &values[j] : NULL;
                t = batt_thresholds_resolve(p, wp, cp);
                if (!batt_thresholds_valid(p, t.warn_v, t.cut_v)) bad++;
                if (!wp && t.warn_ignored) bad++;
                if (!cp && t.cut_ignored) bad++;
                if (wp && !t.warn_ignored && t.warn_v != *wp) bad++;
                if (cp && !t.cut_ignored && t.cut_v != *cp) bad++;
                if (t.warn_ignored && t.warn_v != p->warn_v) bad++;
                if (t.cut_ignored && t.cut_v != p->cut_v) bad++;
                // An override that the pair check accepts is never dropped.
                if (wp && cp && batt_thresholds_valid(p, *wp, *cp) && (t.warn_ignored || t.cut_ignored)) bad++;
            }
        }
    }
    CHECK_INT(bad, 0);
}

static void test_names(void) {
    CHECK(batt_pack_find("li5s") == &BATT_LI5S);
    CHECK(batt_pack_find("lfp4s") == &BATT_LFP4S);
    static const char *const unknown[] = {"", "LI5S", "Li5s", "li5", "li5s ", " li5s", "li5s\n", "lfp4",
                                          "lfp4s4", "lifepo4", "li6s", "5S Li-ion", "4S LiFePO4"};
    for (size_t i = 0; i < sizeof unknown / sizeof unknown[0]; i++)
        CHECK(batt_pack_find(unknown[i]) == NULL);
    CHECK(batt_pack_find(NULL) == NULL);

    CHECK_STR(batt_state_name(BATT_NONE), "none");
    CHECK_STR(batt_state_name(BATT_OK), "ok");
    CHECK_STR(batt_state_name(BATT_LOW), "low");
    CHECK_STR(batt_state_name(BATT_CUTOFF), "cutoff");
    CHECK_STR(batt_state_name(4), "?");
    CHECK_STR(batt_state_name(-1), "?");
}

// ------------------------------------------------------------------- hint

static void hint_is(const batt_pack_t *p, float volts, float cut_v, const char *want, int line) {
    char buf[128];
    memset(buf, 'x', sizeof buf);
    bool got = batt_hint(buf, sizeof buf, p, volts, cut_v);
    check(got == (want[0] != 0), "batt_hint's return matches its text", line);
    check_str(buf, want, "hint", line);
}
#define HINT_IS(p, v, cut, want) hint_is((p), (v), (cut), (want), __LINE__)

static void test_hint(void) {
    const batt_pack_t *li = &BATT_LI5S, *lfp = &BATT_LFP4S;
    // The old pack fitted with the new default.
    HINT_IS(li, 13.1f, 15.5f, "13.1 V is below the li5s cutoff; if this is a 4S LiFePO4 pack: set batt_pack lfp4s");
    HINT_IS(li, 11.0f, 15.5f, "11.0 V is below the li5s cutoff; if this is a 4S LiFePO4 pack: set batt_pack lfp4s");
    HINT_IS(li, 14.8f, 15.5f, "14.8 V is below the li5s cutoff; if this is a 4S LiFePO4 pack: set batt_pack lfp4s");
    // The new pack with the old setting: the bug this replaces, which read 100%.
    HINT_IS(lfp, 19.97f, 11.6f, "20.0 V is above a full lfp4s pack; if this is a 5S Li-ion pack: set batt_pack li5s");
    HINT_IS(lfp, 15.0f, 11.6f, "15.0 V is above a full lfp4s pack; if this is a 5S Li-ion pack: set batt_pack li5s");
    // Right pack, sensible reading: nothing to say.
    HINT_IS(li, 19.97f, 15.5f, "");
    HINT_IS(li, 21.0f, 15.5f, "");
    HINT_IS(li, 22.5f, 15.5f, "");
    HINT_IS(lfp, 13.3f, 11.6f, "");
    HINT_IS(lfp, 14.6f, 11.6f, "");   // on its charger
    // A flat pack of the right kind is the state's business, not a hint's.
    HINT_IS(li, 15.2f, 15.5f, "");
    HINT_IS(li, 14.9f, 15.5f, "");
    HINT_IS(lfp, 11.0f, 11.6f, "");
    // Bench cutoffs forced high with a charged pack.
    HINT_IS(li, 19.97f, 20.0f, "");
    HINT_IS(lfp, 12.8f, 13.0f, "");
    // Nothing fits: the divider is the suspect.
    HINT_IS(li, 8.9f, 15.5f, "8.9 V is below the li5s cutoff; check batt_div against a meter");
    HINT_IS(li, 23.0f, 15.5f, "23.0 V is above a full li5s pack; check batt_div against a meter");
    HINT_IS(lfp, 9.5f, 11.6f, "9.5 V is below the lfp4s cutoff; check batt_div against a meter");
    HINT_IS(lfp, 30.0f, 11.6f, "30.0 V is above a full lfp4s pack; check batt_div against a meter");
    // Nothing to judge.
    HINT_IS(NULL, 13.1f, 15.5f, "");
    HINT_IS(li, NAN, 15.5f, "");

    // A short buffer is truncated, never overrun; no buffer still answers.
    char small[8];
    CHECK(batt_hint(small, sizeof small, li, 13.1f, 15.5f));
    CHECK_STR(small, "13.1 V ");
    CHECK(batt_hint(NULL, 0, li, 13.1f, 15.5f));
    CHECK(!batt_hint(NULL, 0, li, 19.97f, 15.5f));
    char one[1] = {'x'};
    CHECK(batt_hint(one, sizeof one, li, 13.1f, 15.5f));
    CHECK_INT(one[0], 0);
}

// ---------------------------------------------------------------- monitor

typedef struct {
    batt_monitor_t m;
    float warn, cut, hyst;
    int changes;
    batt_state_t last;
} rig_t;

static rig_t rig(const batt_pack_t *p) {
    rig_t r;
    memset(&r, 0, sizeof r);
    r.warn = p->warn_v;
    r.cut = p->cut_v;
    r.hyst = p->hyst_v;
    return r;
}

static batt_state_t feed(rig_t *r, bool present, float filtered, float raw) {
    batt_state_t s = batt_monitor_step(&r->m, present, filtered, raw, r->warn, r->cut, r->hyst);
    if (s != r->last) r->changes++;
    r->last = s;
    return s;
}

// `n` samples at (filtered, raw): the first n-1 must leave the state at
// `before` and the nth must give `after`, which is what "after N s" means.
static void expect_after(rig_t *r, float filtered, float raw, int n, batt_state_t before,
                         batt_state_t after, int line) {
    for (int i = 1; i <= n; i++) {
        batt_state_t got = feed(r, true, filtered, raw), want = i < n ? before : after;
        checks++;
        if (got != want) {
            failures++;
            fprintf(stderr, "test_battery_model.c:%d: sample %d of %d at %.2f V (raw %.2f): %s, expected %s\n",
                    line, i, n, (double)filtered, (double)raw, batt_state_name(got), batt_state_name(want));
            return;
        }
    }
}
#define EXPECT_AFTER(r, f, raw, n, before, after) expect_after((r), (f), (raw), (n), (before), (after), __LINE__)
#define EXPECT_HOLD(r, f, raw, n, state) expect_after((r), (f), (raw), (n), (state), (state), __LINE__)

// 20 s under the 15.5 V li5s cut, which passes through LOW on the way.
static void cut_sustained(rig_t *r) {
    EXPECT_AFTER(r, 15.4f, 15.4f, 10, BATT_OK, BATT_LOW);
    EXPECT_AFTER(r, 15.4f, 15.4f, 10, BATT_LOW, BATT_CUTOFF);
}

static void test_low(void) {
    rig_t r = rig(&BATT_LI5S);
    CHECK_INT(r.m.state, BATT_NONE);
    CHECK_INT(feed(&r, true, 19.97f, 19.97f), BATT_OK);
    // Exactly the tenth sample below warn.
    EXPECT_AFTER(&r, 16.4f, 16.4f, 10, BATT_OK, BATT_LOW);
    // Above warn but inside the hysteresis band it stays low...
    EXPECT_HOLD(&r, 16.9f, 16.9f, 100, BATT_LOW);
    // ...and nine good samples are not ten.
    EXPECT_HOLD(&r, 17.0f, 17.0f, 9, BATT_LOW);
    EXPECT_HOLD(&r, 16.9f, 16.9f, 1, BATT_LOW);
    // At warn + hyst exactly, the tenth sample clears it.
    EXPECT_AFTER(&r, 17.0f, 17.0f, 10, BATT_LOW, BATT_OK);

    // At warn exactly is not below it.
    r = rig(&BATT_LI5S);
    EXPECT_HOLD(&r, 16.5f, 16.5f, 200, BATT_OK);
    // A run broken by one sample at warn starts again.
    EXPECT_HOLD(&r, 16.4f, 16.4f, 9, BATT_OK);
    EXPECT_HOLD(&r, 16.5f, 16.5f, 1, BATT_OK);
    EXPECT_AFTER(&r, 16.4f, 16.4f, 10, BATT_OK, BATT_LOW);
}

static void test_cut(void) {
    rig_t r = rig(&BATT_LI5S);
    CHECK_INT(feed(&r, true, 19.97f, 19.97f), BATT_OK);
    // Exactly the twentieth sample below cut.
    cut_sustained(&r);
    CHECK(!r.m.collapsed);

    // At cut exactly is not below it.
    r = rig(&BATT_LI5S);
    EXPECT_AFTER(&r, 15.5f, 15.5f, 10, BATT_OK, BATT_LOW);
    EXPECT_HOLD(&r, 15.5f, 15.5f, 200, BATT_LOW);
    // A run broken at nineteen starts again.
    EXPECT_HOLD(&r, 15.4f, 15.4f, 19, BATT_LOW);
    EXPECT_HOLD(&r, 15.5f, 15.5f, 1, BATT_LOW);
    EXPECT_AFTER(&r, 15.4f, 15.4f, 20, BATT_LOW, BATT_CUTOFF);
}

static void test_collapse(void) {
    // The filter still says 16 V, but five raw samples more than 1 V under
    // the cut are a pack giving out.
    rig_t r = rig(&BATT_LI5S);
    CHECK_INT(feed(&r, true, 19.97f, 19.97f), BATT_OK);
    EXPECT_AFTER(&r, 16.0f, 14.49f, 5, BATT_OK, BATT_CUTOFF);
    CHECK(r.m.collapsed);

    // Exactly 1 V under is not more than 1 V under.
    r = rig(&BATT_LI5S);
    EXPECT_HOLD(&r, 17.5f, 14.5f, 100, BATT_OK);
    // Four, a good one, four: a surge, not a collapse.
    EXPECT_HOLD(&r, 17.5f, 14.4f, 4, BATT_OK);
    EXPECT_HOLD(&r, 17.5f, 14.6f, 1, BATT_OK);
    EXPECT_HOLD(&r, 17.5f, 14.4f, 4, BATT_OK);
    EXPECT_HOLD(&r, 17.5f, 17.5f, 1, BATT_OK);
    EXPECT_AFTER(&r, 17.5f, 14.4f, 5, BATT_OK, BATT_CUTOFF);

    // The filtered voltage never left 18 V, yet leaving cutoff still takes ten
    // good samples counted from the cut, not from before it.
    r = rig(&BATT_LI5S);
    EXPECT_AFTER(&r, 18.0f, 14.0f, 5, BATT_OK, BATT_CUTOFF);
    EXPECT_AFTER(&r, 18.0f, 18.0f, 10, BATT_CUTOFF, BATT_OK);   // never low: straight to ok
    // And it stays out while the pack keeps collapsing.
    r = rig(&BATT_LI5S);
    EXPECT_AFTER(&r, 18.0f, 14.0f, 5, BATT_OK, BATT_CUTOFF);
    EXPECT_HOLD(&r, 18.0f, 14.0f, 100, BATT_CUTOFF);
}

static void test_recovery(void) {
    // Out of cutoff into low: 16.0 V clears the cut but not the warning.
    rig_t r = rig(&BATT_LI5S);
    cut_sustained(&r);
    EXPECT_HOLD(&r, 15.9f, 15.9f, 100, BATT_CUTOFF);   // above cut, inside the hysteresis
    EXPECT_HOLD(&r, 16.0f, 16.0f, 9, BATT_CUTOFF);
    EXPECT_HOLD(&r, 15.9f, 15.9f, 1, BATT_CUTOFF);
    EXPECT_AFTER(&r, 16.0f, 16.0f, 10, BATT_CUTOFF, BATT_LOW);
    EXPECT_AFTER(&r, 17.0f, 17.0f, 10, BATT_LOW, BATT_OK);

    // Straight out of cutoff to ok when the pack comes back above warn + hyst
    // (a fresh pack on USB power, say): both clear on the same sample.
    r = rig(&BATT_LI5S);
    cut_sustained(&r);
    EXPECT_AFTER(&r, 17.5f, 17.5f, 10, BATT_CUTOFF, BATT_OK);

    // Clearing the cut and setting the warning on the same sample lands in low
    // (lfp4s: 12.0 V is cut + hyst, and under the 12.4 V warning).
    r = rig(&BATT_LFP4S);
    CHECK_INT(feed(&r, true, 13.1f, 13.1f), BATT_OK);
    EXPECT_AFTER(&r, 12.5f, 10.5f, 5, BATT_OK, BATT_CUTOFF);
    EXPECT_AFTER(&r, 12.0f, 12.0f, 10, BATT_CUTOFF, BATT_LOW);
}

static void test_lfp4s_monitor(void) {
    rig_t r = rig(&BATT_LFP4S);
    CHECK_INT(feed(&r, true, 13.1f, 13.1f), BATT_OK);
    EXPECT_AFTER(&r, 12.3f, 12.3f, 10, BATT_OK, BATT_LOW);
    EXPECT_HOLD(&r, 12.7f, 12.7f, 50, BATT_LOW);
    EXPECT_AFTER(&r, 12.8f, 12.8f, 10, BATT_LOW, BATT_OK);
    EXPECT_AFTER(&r, 11.5f, 11.5f, 10, BATT_OK, BATT_LOW);
    EXPECT_AFTER(&r, 11.5f, 11.5f, 10, BATT_LOW, BATT_CUTOFF);
    EXPECT_HOLD(&r, 11.9f, 11.9f, 50, BATT_CUTOFF);
    EXPECT_AFTER(&r, 13.0f, 13.0f, 10, BATT_CUTOFF, BATT_OK);
}

static void test_none(void) {
    // Nothing at the pin is none, whatever the numbers say.
    rig_t r = rig(&BATT_LI5S);
    int wrong = 0;
    for (int i = 0; i < 1000; i++)
        if (feed(&r, false, (float)(i % 31), (float)(i % 17)) != BATT_NONE) wrong++;
    CHECK_INT(wrong, 0);

    // Losing the sense in cutoff is none at once...
    r = rig(&BATT_LI5S);
    cut_sustained(&r);
    CHECK_INT(feed(&r, false, 0.0f, 0.0f), BATT_NONE);
    // ...and a pack that then reads, even a hopeless one, starts at ok and
    // earns its cutoff again: five raw samples here, all counted afresh.
    EXPECT_AFTER(&r, 13.0f, 13.0f, 5, BATT_OK, BATT_CUTOFF);

    // The sustained rule restarts from nothing too.
    r = rig(&BATT_LI5S);
    cut_sustained(&r);
    CHECK_INT(feed(&r, false, 0.0f, 0.0f), BATT_NONE);
    cut_sustained(&r);

    // And low.
    r = rig(&BATT_LI5S);
    EXPECT_AFTER(&r, 16.4f, 16.4f, 10, BATT_OK, BATT_LOW);
    CHECK_INT(feed(&r, false, 16.4f, 16.4f), BATT_NONE);
    EXPECT_AFTER(&r, 16.4f, 16.4f, 10, BATT_OK, BATT_LOW);

    // Random presence and voltages: none exactly when absent, and none only
    // ever becomes ok.
    r = rig(&BATT_LI5S);
    uint32_t seed = 12345;
    int bad = 0;
    batt_state_t prev = BATT_NONE;
    for (int i = 0; i < 200000; i++) {
        seed = seed * 1664525u + 1013904223u;
        bool present = (seed >> 28) != 0;   // absent one sample in 16
        float v = 10.0f + (float)((seed >> 8) % 1200) * 0.01f;
        float raw = v - (float)((seed >> 4) % 16) * 0.2f;
        batt_state_t s = feed(&r, present, v, raw);
        if ((s == BATT_NONE) != !present) bad++;
        if (prev == BATT_NONE && s != BATT_NONE && s != BATT_OK) bad++;
        prev = s;
    }
    CHECK_INT(bad, 0);
}

static void test_no_flapping(void) {
    // Square waves that never hold one side long enough.
    rig_t r = rig(&BATT_LI5S);
    CHECK_INT(feed(&r, true, 19.0f, 19.0f), BATT_OK);
    for (int i = 0; i < 40; i++) {
        EXPECT_HOLD(&r, 16.4f, 16.4f, 5, BATT_OK);
        EXPECT_HOLD(&r, 16.6f, 16.6f, 5, BATT_OK);
    }
    EXPECT_AFTER(&r, 16.4f, 16.4f, 10, BATT_OK, BATT_LOW);
    for (int i = 0; i < 40; i++) {
        EXPECT_HOLD(&r, 16.4f, 16.4f, 5, BATT_LOW);
        EXPECT_HOLD(&r, 16.9f, 16.9f, 5, BATT_LOW);
    }
    for (int i = 0; i < 40; i++) {
        EXPECT_HOLD(&r, 17.0f, 17.0f, 9, BATT_LOW);
        EXPECT_HOLD(&r, 16.9f, 16.9f, 1, BATT_LOW);
    }
    EXPECT_AFTER(&r, 15.4f, 15.4f, 20, BATT_LOW, BATT_CUTOFF);
    for (int i = 0; i < 40; i++) {
        EXPECT_HOLD(&r, 15.4f, 15.4f, 5, BATT_CUTOFF);
        EXPECT_HOLD(&r, 15.9f, 15.9f, 5, BATT_CUTOFF);
    }
    for (int i = 0; i < 40; i++) {
        EXPECT_HOLD(&r, 16.0f, 16.0f, 9, BATT_CUTOFF);
        EXPECT_HOLD(&r, 15.9f, 15.9f, 1, BATT_CUTOFF);
    }

    // An hour sitting on each threshold with noise, through the same ~5 s
    // one-pole battery.c uses: at most the one change into the next state,
    // never back.
    static const struct { float mean; batt_state_t start; } hover[] = {
        {16.5f, BATT_OK},       // on the warning
        {17.0f, BATT_LOW},      // on the warning's release
        {15.5f, BATT_LOW},      // on the cut
        {16.0f, BATT_CUTOFF},   // on the cut's release
    };
    for (size_t h = 0; h < sizeof hover / sizeof hover[0]; h++) {
        r = rig(&BATT_LI5S);
        if (hover[h].start == BATT_LOW) EXPECT_AFTER(&r, 16.0f, 16.0f, 10, BATT_OK, BATT_LOW);
        if (hover[h].start == BATT_CUTOFF) cut_sustained(&r);
        if (hover[h].start == BATT_OK) CHECK_INT(feed(&r, true, 19.0f, 19.0f), BATT_OK);
        r.changes = 0;
        uint32_t seed = 777u + (uint32_t)h;
        float f = hover[h].mean;
        for (int i = 0; i < 3600; i++) {
            seed = seed * 1664525u + 1013904223u;
            float raw = hover[h].mean + ((float)(seed >> 16) / 65536.0f - 0.5f) * 0.6f;
            f += 0.2f * (raw - f);
            feed(&r, true, f, raw);
        }
        check(r.changes <= 1, "at most one change while hovering on a threshold", __LINE__);
    }

    // A whole discharge with motor sag, then a charge: every state once, in
    // order, and nothing else.
    r = rig(&BATT_LI5S);
    uint32_t seed = 4242u;
    float f = 18.5f;
    batt_state_t seen[8];
    int nseen = 0;
    batt_state_t prev = BATT_NONE;
    for (int i = 0; i < 5400; i++) {
        float mean = i < 3600 ? 18.5f - 3.5f * (float)i / 3600.0f : 15.0f + 5.0f * (float)(i - 3600) / 1800.0f;
        seed = seed * 1664525u + 1013904223u;
        float raw = mean - (float)(seed >> 16) / 65536.0f * 0.8f;   // the load only ever pulls down
        f += 0.2f * (raw - f);
        batt_state_t s = feed(&r, true, f, raw);
        if (s != prev && nseen < 8) seen[nseen++] = s;
        prev = s;
    }
    static const batt_state_t want[] = {BATT_OK, BATT_LOW, BATT_CUTOFF, BATT_LOW, BATT_OK};
    CHECK_INT(nseen, 5);
    for (int i = 0; i < nseen && i < 5; i++) CHECK_INT(seen[i], want[i]);
}

static void test_long_runs(void) {
    // Days on one side of a threshold neither wrap a count nor change a state.
    rig_t r = rig(&BATT_LI5S);
    EXPECT_HOLD(&r, 19.97f, 19.97f, 70000, BATT_OK);
    CHECK_INT(r.m.over_warn, UINT16_MAX);
    EXPECT_AFTER(&r, 16.4f, 16.4f, 10, BATT_OK, BATT_LOW);
    EXPECT_HOLD(&r, 16.4f, 16.4f, 70000, BATT_LOW);
    EXPECT_AFTER(&r, 15.0f, 15.0f, 20, BATT_LOW, BATT_CUTOFF);
    EXPECT_HOLD(&r, 15.0f, 15.0f, 70000, BATT_CUTOFF);
    EXPECT_AFTER(&r, 17.5f, 17.5f, 10, BATT_CUTOFF, BATT_OK);
}

static void test_bench_forcing(void) {
    // The stand check for this change: a charged pack, low and cutoff forced
    // by the overrides, then the overrides unset in either order.
    rig_t r = rig(&BATT_LI5S);
    CHECK_INT(feed(&r, true, 19.97f, 19.97f), BATT_OK);
    r.warn = 20.5f;   // set batt_warn_v 20.5
    EXPECT_AFTER(&r, 19.97f, 19.97f, 10, BATT_OK, BATT_LOW);
    r.cut = 20.0f;    // set batt_cut_v 20.0
    EXPECT_AFTER(&r, 19.97f, 19.97f, 20, BATT_LOW, BATT_CUTOFF);
    r.cut = 15.5f;    // unset batt_cut_v: out of cutoff, still low under 20.5 V
    EXPECT_AFTER(&r, 19.97f, 19.97f, 10, BATT_CUTOFF, BATT_LOW);
    r.warn = 16.5f;   // unset batt_warn_v
    EXPECT_AFTER(&r, 19.97f, 19.97f, 10, BATT_LOW, BATT_OK);

    // Unsetting the warning first leaves a cut above the default warning,
    // which resolves back to the profile's pair: straight out to ok.
    r = rig(&BATT_LI5S);
    r.warn = 20.5f;
    r.cut = 20.0f;
    EXPECT_AFTER(&r, 19.97f, 19.97f, 10, BATT_OK, BATT_LOW);
    EXPECT_AFTER(&r, 19.97f, 19.97f, 10, BATT_LOW, BATT_CUTOFF);
    float cut = 20.0f;
    batt_thresholds_t t = batt_thresholds_resolve(&BATT_LI5S, NULL, &cut);
    r.warn = t.warn_v;
    r.cut = t.cut_v;
    EXPECT_AFTER(&r, 19.97f, 19.97f, 10, BATT_CUTOFF, BATT_OK);
}

int main(void) {
    test_profiles();
    test_li5s_percent();
    test_lfp4s_percent();
    test_thresholds();
    test_resolve();
    test_names();
    test_hint();
    test_low();
    test_cut();
    test_collapse();
    test_recovery();
    test_lfp4s_monitor();
    test_none();
    test_no_flapping();
    test_long_runs();
    test_bench_forcing();
    if (failures) {
        printf("FAIL: %d of %d checks\n", failures, checks);
        return 1;
    }
    printf("PASS: %d checks -- li5s/lfp4s tables (19.97 V = 79%%, old LFP curve unchanged), threshold ranges "
           "and override resolution, pack names, hints, low/cutoff timing (10/20 s, 5 s collapse), "
           "recovery with hysteresis, none handling, no flapping\n", checks);
    return 0;
}
