#pragma once
// Pack profiles and the low/cutoff rules, with no ESP-IDF in sight so the
// host tests compile this exactly as the firmware does
// (tests/run_host_tests.py). battery.c feeds it from the ADC once a second
// and owns the settings; nothing here does I/O or keeps global state.
//
// A profile is a resting-voltage table for the percentage plus warn and cut
// thresholds. A robot may override warn and cut (batt_warn_v, batt_cut_v)
// within the ranges the profile gives; those ranges are wide on purpose, so a
// bench can force low and cutoff with a charged pack.
//
// The monitor turns the ~5 s filtered voltage into a state, one step per
// 1 Hz sample. "N s" below means N consecutive samples.
//   LOW     after 10 s below warn; clears after 10 s at or above warn + hyst.
//   CUTOFF  after 20 s below cut, or after 5 s of raw samples more than 1 V
//           below cut: a pack collapsing under load, faster than the filter
//           follows. Left after 10 s in cutoff at or above cut + hyst, to LOW
//           or OK by the LOW rule, which keeps running underneath.
//   NONE    nothing at the sense pin. It clears everything, and a pack that
//           appears starts at OK and has to earn LOW or CUTOFF like any
//           other: with no reading there is nothing to act on, and a robot
//           without the sense wired must still drive.
// The hysteresis and the sustain times are what stop a pack sagging under
// load, or sitting on a threshold, from flapping between states.
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

typedef enum { BATT_NONE = 0, BATT_OK = 1, BATT_LOW = 2, BATT_CUTOFF = 3 } batt_state_t;

typedef struct { float v; uint8_t pct; } batt_point_t;

typedef struct {
    const char *name;    // the batt_pack value, "li5s"
    const char *label;   // for people and hints, "5S Li-ion"
    uint8_t cells;
    float warn_v, cut_v, hyst_v;             // the profile's own thresholds
    float min_cut_v, max_cut_v, max_warn_v;  // what an override may use
    const batt_point_t *table;               // resting volts ascending, 0% .. 100%
    size_t n;
} batt_pack_t;

extern const batt_pack_t BATT_LI5S, BATT_LFP4S;

// Sustain times of the rules above, in 1 Hz samples.
enum {
    BATT_LOW_S = 10,        // below warn before LOW
    BATT_LOW_CLEAR_S = 10,  // at or above warn + hyst before LOW clears
    BATT_CUT_S = 20,        // below cut before CUTOFF
    BATT_COLLAPSE_S = 5,    // raw more than BATT_COLLAPSE_V below cut before CUTOFF
    BATT_CUT_CLEAR_S = 10,  // in cutoff, at or above cut + hyst before it clears
};
#define BATT_COLLAPSE_V 1.0f

// By batt_pack name, exactly as stored ("li5s", "lfp4s"); NULL if unknown.
const batt_pack_t *batt_pack_find(const char *name);
// Every profile in turn, NULL past the last.
const batt_pack_t *batt_pack_at(size_t i);

// 0..100 from the profile's table, interpolated and clamped at both ends; NaN
// reads 0. -1 without a profile.
int batt_percent(const batt_pack_t *p, float volts);

// A warn/cut pair this profile accepts: cut within min_cut_v..max_cut_v, warn
// at most max_warn_v and above cut. NaN and infinities fail.
bool batt_thresholds_valid(const batt_pack_t *p, float warn_v, float cut_v);

// The pair in force given the stored overrides (NULL when not stored). An
// override outside its own range is ignored; if what is left puts warn at or
// below cut, both overrides are ignored and the profile's pair applies, since
// which one is wrong would be a guess. The flags say what was ignored, for
// the caller to log.
typedef struct { float warn_v, cut_v; bool warn_ignored, cut_ignored; } batt_thresholds_t;
batt_thresholds_t batt_thresholds_resolve(const batt_pack_t *p, const float *warn_v, const float *cut_v);

// The monitor. Zero it to start (BATT_NONE); it needs nothing else.
typedef struct {
    batt_state_t state;   // what the last step returned
    bool low, cut;        // the two latches; cut outranks low
    bool collapsed;       // the cut latched on the raw rule, not the sustained one
    uint16_t below_warn, over_warn;  // consecutive samples < warn, >= warn + hyst
    uint16_t below_cut, over_cut;    // < cut, and >= cut + hyst since the cut latched
    uint16_t collapsing;             // raw < cut - BATT_COLLAPSE_V
} batt_monitor_t;

// One 1 Hz sample: presence, the filtered voltage, that second's unfiltered
// reading, and the thresholds in force (which may change between calls; each
// sample is judged against the ones it is given).
batt_state_t batt_monitor_step(batt_monitor_t *m, bool present, float filtered_v, float raw_v,
                               float warn_v, float cut_v, float hyst_v);

// "none", "ok", "low", "cutoff"; "?" for anything else.
const char *batt_state_name(int state);

// A reading that makes no sense for the configured pack names the likely fix:
// below its cutoff (`cut_v` is the one in force) where another profile's pack
// would read it, or above a full one. For example "13.1 V is below the li5s
// cutoff; if this is a 4S LiFePO4 pack: set batt_pack lfp4s". A voltage no
// profile explains points at the divider instead. A merely flat pack of the
// configured kind gets no hint; its state says it. Returns whether there is a
// hint, writes it (or "") into buf like snprintf, and takes a NULL pack as
// nothing to judge.
bool batt_hint(char *buf, size_t n, const batt_pack_t *p, float volts, float cut_v);

#ifdef __cplusplus
}
#endif
