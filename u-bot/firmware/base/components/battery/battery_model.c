#include "battery_model.h"

#include <math.h>
#include <stdio.h>
#include <string.h>

// ------------------------------------------------------------------ profiles

// Five Li-ion cells in series, as in the Skil PWR CORE 20 the robot runs on
// since 2026-09-30 (or any "20 V max" power-tool pack), with the pack's own
// BMS. Resting voltage against state of charge for a typical NMC cell, 3.0 V
// (0%) to 4.2 V (100%) a cell: 19.97 V is 4.0 V a cell and reads 79%. Under
// motor load the pack sags and this reads low, which is the safe direction.
static const batt_point_t LI5S_TABLE[] = {
    {15.0f, 0}, {16.0f, 2}, {16.5f, 4}, {17.0f, 8}, {17.5f, 14}, {18.0f, 25},
    {18.5f, 42}, {19.0f, 57}, {19.5f, 69}, {20.0f, 80}, {20.5f, 90}, {21.0f, 100},
};

const batt_pack_t BATT_LI5S = {
    .name = "li5s", .label = "5S Li-ion", .cells = 5,
    // Warn at 3.3 V a cell, ~4% left. Cut at 3.1 V a cell, ~1%, which is
    // above the BMS's own cutoff: the robot should stop and hold under its
    // own control before the BMS drops power to everything, drivers
    // included, and lets it roll.
    .warn_v = 16.5f, .cut_v = 15.5f, .hyst_v = 0.5f,
    // Overrides may cut anywhere from 2.5 V a cell, the chemistry's floor, to
    // 4.0 V, and warn up to 4.1 V: high enough to force low and cutoff on the
    // bench with a charged pack.
    .min_cut_v = 12.5f, .max_cut_v = 20.0f, .max_warn_v = 20.5f,
    .table = LI5S_TABLE, .n = sizeof LI5S_TABLE / sizeof LI5S_TABLE[0],
};

// 12 V 8 Ah LiFePO4, four cells in series: the pack the robot was built
// with. Resting pack voltage against state of charge; the curve is flat from
// ~13.3 V down to ~12.9 V, so a linear window would call a nearly empty pack
// half full. Points above 13.6 V are the charger holding the pack, still
// 100%. Under motor load the pack sags and this reads low, which is the safe
// direction.
static const batt_point_t LFP4S_TABLE[] = {
    {10.0f, 0}, {12.0f, 9}, {12.5f, 14}, {12.8f, 17}, {12.9f, 20}, {13.0f, 30},
    {13.1f, 40}, {13.2f, 70}, {13.3f, 90}, {13.4f, 99}, {13.6f, 100},
};

const batt_pack_t BATT_LFP4S = {
    .name = "lfp4s", .label = "4S LiFePO4", .cells = 4,
    // Warn at 3.1 V a cell (~13%), cut at 2.9 V (~7%).
    .warn_v = 12.4f, .cut_v = 11.6f, .hyst_v = 0.4f,
    // Cut from 2.5 V a cell to 3.25 V, warn up to 3.35 V.
    .min_cut_v = 10.0f, .max_cut_v = 13.0f, .max_warn_v = 13.4f,
    .table = LFP4S_TABLE, .n = sizeof LFP4S_TABLE / sizeof LFP4S_TABLE[0],
};

static const batt_pack_t *const PACKS[] = {&BATT_LI5S, &BATT_LFP4S};
#define NPACKS (sizeof PACKS / sizeof PACKS[0])

const batt_pack_t *batt_pack_find(const char *name) {
    if (!name) return NULL;
    for (size_t i = 0; i < NPACKS; i++)
        if (!strcmp(PACKS[i]->name, name)) return PACKS[i];
    return NULL;
}

const batt_pack_t *batt_pack_at(size_t i) { return i < NPACKS ? PACKS[i] : NULL; }

// ---------------------------------------------------------------- percentage

int batt_percent(const batt_pack_t *p, float volts) {
    if (!p || !p->table || !p->n) return -1;
    const batt_point_t *t = p->table;
    const size_t n = p->n;
    // Negated so NaN takes this branch and reads empty, the safe direction.
    if (!(volts > t[0].v)) return t[0].pct;
    if (volts >= t[n - 1].v) return t[n - 1].pct;
    for (size_t i = 1; i < n; i++) {
        if (volts <= t[i].v) {
            float f = (volts - t[i - 1].v) / (t[i].v - t[i - 1].v);
            return (int)lroundf(t[i - 1].pct + f * (t[i].pct - t[i - 1].pct));
        }
    }
    return t[n - 1].pct;
}

// ---------------------------------------------------------------- thresholds

bool batt_thresholds_valid(const batt_pack_t *p, float warn_v, float cut_v) {
    // Every comparison is one that NaN fails.
    return p && cut_v >= p->min_cut_v && cut_v <= p->max_cut_v &&
           warn_v <= p->max_warn_v && warn_v > cut_v;
}

batt_thresholds_t batt_thresholds_resolve(const batt_pack_t *p, const float *warn_v, const float *cut_v) {
    batt_thresholds_t t = {0.0f, 0.0f, false, false};
    if (!p) return t;
    t.warn_v = p->warn_v;
    t.cut_v = p->cut_v;
    // Each override against its own range first. Warn's lower bound is the
    // lowest cut the profile allows, since it has to sit above one.
    if (cut_v) {
        if (*cut_v >= p->min_cut_v && *cut_v <= p->max_cut_v) t.cut_v = *cut_v;
        else t.cut_ignored = true;
    }
    if (warn_v) {
        if (*warn_v > p->min_cut_v && *warn_v <= p->max_warn_v) t.warn_v = *warn_v;
        else t.warn_ignored = true;
    }
    // Then as a pair. This fails only when an override meets the other's
    // default or a conflicting override -- a cut left behind by unsetting
    // the warn that allowed it, say -- and then neither is trusted.
    if (!batt_thresholds_valid(p, t.warn_v, t.cut_v)) {
        if (warn_v) t.warn_ignored = true;
        if (cut_v) t.cut_ignored = true;
        t.warn_v = p->warn_v;
        t.cut_v = p->cut_v;
    }
    return t;
}

// ------------------------------------------------------------------- monitor

// Length of a run of consecutive samples meeting `cond`; saturates, so a
// pack left for days on one side of a threshold cannot wrap it.
static uint16_t run(uint16_t n, bool cond) {
    if (!cond) return 0;
    return n < UINT16_MAX ? (uint16_t)(n + 1) : n;
}

batt_state_t batt_monitor_step(batt_monitor_t *m, bool present, float filtered_v, float raw_v,
                               float warn_v, float cut_v, float hyst_v) {
    if (!present) {
        memset(m, 0, sizeof *m);
        return m->state;   // BATT_NONE
    }
    m->below_warn = run(m->below_warn, filtered_v < warn_v);
    m->over_warn = run(m->over_warn, filtered_v >= warn_v + hyst_v);
    m->below_cut = run(m->below_cut, filtered_v < cut_v);
    m->over_cut = run(m->over_cut, filtered_v >= cut_v + hyst_v);
    m->collapsing = run(m->collapsing, raw_v < cut_v - BATT_COLLAPSE_V);

    if (m->low && m->over_warn >= BATT_LOW_CLEAR_S) m->low = false;
    if (!m->low && m->below_warn >= BATT_LOW_S) m->low = true;

    if (m->cut && m->over_cut >= BATT_CUT_CLEAR_S) m->cut = false;
    // Checked after the release, so a sample that meets both stays in cutoff.
    if (!m->cut && (m->below_cut >= BATT_CUT_S || m->collapsing >= BATT_COLLAPSE_S)) {
        m->cut = true;
        m->collapsed = m->below_cut < BATT_CUT_S;
        // The way out is counted from here. A pack that collapsed faster than
        // the filter can have a filtered voltage that never left the good
        // side, and it still owes ten good seconds.
        m->over_cut = 0;
    }
    m->state = m->cut ? BATT_CUTOFF : m->low ? BATT_LOW : BATT_OK;
    return m->state;
}

const char *batt_state_name(int state) {
    switch (state) {
        case BATT_NONE: return "none";
        case BATT_OK: return "ok";
        case BATT_LOW: return "low";
        case BATT_CUTOFF: return "cutoff";
        default: return "?";
    }
}

// ---------------------------------------------------------------------- hint

// The most a healthy pack of this kind reads: full at rest plus 0.3 V a cell,
// which covers LiFePO4 held on its 3.65 V/cell charger and a few percent of
// divider error on Li-ion.
static float ceiling_v(const batt_pack_t *p) { return p->table[p->n - 1].v + 0.3f * p->cells; }

bool batt_hint(char *buf, size_t n, const batt_pack_t *p, float volts, float cut_v) {
    if (buf && n) buf[0] = 0;
    if (!p || !p->table || !p->n) return false;
    bool below = volts < cut_v, above = volts > ceiling_v(p);
    if (!below && !above) return false;   // NaN too
    // Another kind of pack that shows this voltage somewhere between empty and
    // on its charger. Its empty point rather than its lowest cut, so a bench
    // cutoff forced high on one chemistry does not suggest the other.
    const batt_pack_t *other = NULL;
    for (size_t i = 0; i < NPACKS && !other; i++) {
        const batt_pack_t *q = PACKS[i];
        if (q != p && volts >= q->table[0].v && volts <= ceiling_v(q)) other = q;
    }
    // Nothing else fits, but a flat pack of the configured kind can read this
    // low: that is not a configuration problem.
    if (!other && below && volts >= p->min_cut_v) return false;
    if (buf && n) {
        const char *side = below ? "is below the" : "is above a full";
        const char *what = below ? "cutoff" : "pack";
        if (other)
            snprintf(buf, n, "%.1f V %s %s %s; if this is a %s pack: set batt_pack %s",
                     (double)volts, side, p->name, what, other->label, other->name);
        else
            snprintf(buf, n, "%.1f V %s %s %s; check batt_div against a meter",
                     (double)volts, side, p->name, what);
    }
    return true;
}
