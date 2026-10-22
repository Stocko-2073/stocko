#include "battery.h"

#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "esp_adc/adc_cali.h"
#include "esp_adc/adc_cali_scheme.h"
#include "esp_adc/adc_oneshot.h"
#include "driver/gpio.h"
#include "esp_log.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "sdkconfig.h"
#include "settings.h"

static const char *TAG = "batt";

static adc_oneshot_unit_handle_t s_adc = NULL;
static adc_cali_handle_t s_cali = NULL;
static adc_channel_t s_chan;
static adc_unit_t s_unit;
static esp_timer_handle_t s_timer;

// Below this at the pin, nothing is connected (or the pack is flat beyond any
// chemistry's floor through any sane divider).
static const int PRESENT_MV = 150;

// Vpack / Vpin for 100k over 10k. A macro only because it initialises s_batt.
#define DIV_DEFAULT 11.0f
// What `set batt_div` accepts: 1 is a plain wire, and above 100 a full 5S pack
// puts barely 0.2 V on the pin, down among the 150 mV that means no pack.
static const float DIV_MIN = 1.0f, DIV_MAX = 100.0f;

// Everything the console and the transports share with the 1 Hz timer. s_mux
// guards all of it and is held only for copies and the monitor's arithmetic,
// never across NVS, the ADC or a log line.
typedef struct {
    const batt_pack_t *pack;   // configuration, from battery_reload_settings()
    float warn_v, cut_v, div;
    float volts;               // measurement, from sample(): filtered pack volts
    int pin_mv;
    bool present, first;
    batt_monitor_t mon;        // zeroed is BATT_NONE
} batt_t;

static portMUX_TYPE s_mux = portMUX_INITIALIZER_UNLOCKED;
static batt_t s_batt = {.pack = &BATT_LI5S, .div = DIV_DEFAULT, .first = true};

static batt_t snap(void) {
    portENTER_CRITICAL(&s_mux);
    batt_t b = s_batt;
    portEXIT_CRITICAL(&s_mux);
    return b;
}

// ----------------------------------------------------------------- settings

// "li5s lfp4s", for messages.
static void pack_names(char *out, size_t n) {
    size_t len = 0;
    out[0] = 0;
    for (size_t i = 0; batt_pack_at(i) && len < n; i++)
        len += snprintf(out + len, n - len, "%s%s", i ? " " : "", batt_pack_at(i)->name);
}

// The battery keys as NVS holds them, before the thresholds are judged
// against the pack and each other.
typedef struct {
    const batt_pack_t *pack;
    float div, warn_v, cut_v;
    bool has_warn, has_cut;
} stored_t;

static void load_stored(stored_t *st) {
    char name[32];
    if (!settings_get_str("batt_pack", name, sizeof name, BATT_LI5S.name) && settings_exists("batt_pack"))
        snprintf(name, sizeof name, "(unreadable)");
    st->pack = batt_pack_find(name);
    if (!st->pack) {
        char known[32];
        pack_names(known, sizeof known);
        ESP_LOGW(TAG, "batt_pack '%s' is not one of %s; using %s", name, known, BATT_LI5S.name);
        st->pack = &BATT_LI5S;
    }
    // NaN when a key exists but does not read as a float, so the resolver
    // rejects it out loud rather than it passing for absent.
    st->has_warn = settings_exists("batt_warn_v");
    st->warn_v = settings_get_f32("batt_warn_v", NAN);
    st->has_cut = settings_exists("batt_cut_v");
    st->cut_v = settings_get_f32("batt_cut_v", NAN);
    st->div = settings_get_f32("batt_div", DIV_DEFAULT);
    if (!isfinite(st->div)) {
        ESP_LOGW(TAG, "batt_div is not a number; using %.1f", DIV_DEFAULT);
        st->div = DIV_DEFAULT;
    }
    if (st->div < 1.0f) st->div = 1.0f;
}

static batt_thresholds_t resolve(const stored_t *st) {
    return batt_thresholds_resolve(st->pack, st->has_warn ? &st->warn_v : NULL, st->has_cut ? &st->cut_v : NULL);
}

void battery_reload_settings(void) {
    stored_t st;
    load_stored(&st);
    batt_thresholds_t t = resolve(&st);
    if (t.warn_ignored || t.cut_ignored) {
        char what[48] = "";
        if (t.warn_ignored) snprintf(what, sizeof what, "batt_warn_v %.2f", st.warn_v);
        if (t.cut_ignored)
            snprintf(what + strlen(what), sizeof what - strlen(what), "%sbatt_cut_v %.2f",
                     t.warn_ignored ? " and " : "", st.cut_v);
        ESP_LOGW(TAG, "ignoring %s: %s cuts within %.1f..%.1f V and warns at most %.1f V, above the cut; "
                 "using warn %.2f V, cut %.2f V", what, st.pack->name, st.pack->min_cut_v, st.pack->max_cut_v,
                 st.pack->max_warn_v, t.warn_v, t.cut_v);
    }
    portENTER_CRITICAL(&s_mux);
    s_batt.pack = st.pack;
    s_batt.warn_v = t.warn_v;
    s_batt.cut_v = t.cut_v;
    s_batt.div = st.div;
    portEXIT_CRITICAL(&s_mux);
}

static bool parse_f(const char *s, float *out) {
    if (!s || !*s) return false;
    char *end;
    float v = strtof(s, &end);
    if (end == s || *end || !isfinite(v)) return false;
    *out = v;
    return true;
}

static void log_settings(void) {
    char line[128];
    battery_settings_line(line, sizeof line);
    ESP_LOGI(TAG, "%s", line);
}

esp_err_t battery_setting_set(const char *key, const char *value) {
    if (!key) return ESP_ERR_INVALID_ARG;
    const char *text = value ? value : "";
    esp_err_t err;
    if (!strcmp(key, "batt_pack")) {
        const batt_pack_t *pack = batt_pack_find(value);
        if (!pack) {
            char known[32];
            pack_names(known, sizeof known);
            ESP_LOGW(TAG, "batt_pack '%s' refused: the packs are %s", text, known);
            return ESP_ERR_INVALID_ARG;
        }
        // Overrides chosen for another pack mean nothing for this one, and one
        // that happens to fit its ranges can still be dangerous -- a LiFePO4
        // cutoff is a deeply flat 5S -- so the new pack starts from its own.
        err = settings_set_str(key, pack->name);
        if (err == ESP_OK) err = settings_erase("batt_warn_v");
        if (err == ESP_OK) err = settings_erase("batt_cut_v");
    } else if (!strcmp(key, "batt_div")) {
        float f;
        if (!parse_f(value, &f) || f < DIV_MIN || f > DIV_MAX) {
            ESP_LOGW(TAG, "batt_div '%s' refused: needs a ratio %.0f..%.0f", text, DIV_MIN, DIV_MAX);
            return ESP_ERR_INVALID_ARG;
        }
        err = settings_set_f32(key, f);
    } else if (!strcmp(key, "batt_warn_v") || !strcmp(key, "batt_cut_v")) {
        float f;
        if (!parse_f(value, &f)) {
            ESP_LOGW(TAG, "%s '%s' refused: needs volts", key, text);
            return ESP_ERR_INVALID_ARG;
        }
        // Judged with whatever is stored for the other threshold, the way the
        // next load will judge it, so a set succeeds only if it takes effect.
        bool warn = !strcmp(key, "batt_warn_v");
        stored_t st;
        load_stored(&st);
        // The other threshold as stored, or the pack's: what a refusal is about.
        float other = warn ? (st.has_cut ? st.cut_v : st.pack->cut_v) : (st.has_warn ? st.warn_v : st.pack->warn_v);
        if (warn) { st.warn_v = f; st.has_warn = true; }
        else { st.cut_v = f; st.has_cut = true; }
        batt_thresholds_t t = resolve(&st);
        if (warn ? t.warn_ignored : t.cut_ignored) {
            if (warn)
                ESP_LOGW(TAG, "batt_warn_v %.2f refused: %s warns at most %.1f V, and above the cut (%.2f V)",
                         f, st.pack->name, st.pack->max_warn_v, other);
            else
                ESP_LOGW(TAG, "batt_cut_v %.2f refused: %s cuts within %.1f..%.1f V, and below the warning (%.2f V)",
                         f, st.pack->name, st.pack->min_cut_v, st.pack->max_cut_v, other);
            return ESP_ERR_INVALID_ARG;
        }
        err = settings_set_f32(key, f);
    } else {
        return ESP_ERR_NOT_FOUND;
    }
    // Even after a failed write, so what runs is what is stored.
    battery_reload_settings();
    if (err == ESP_OK) log_settings();
    return err;
}

esp_err_t battery_setting_unset(const char *key) {
    if (!key) return ESP_ERR_INVALID_ARG;
    esp_err_t err;
    if (!strcmp(key, "batt_pack")) {
        // Back to the default pack, without the old one's overrides, as a set.
        err = settings_erase(key);
        if (err == ESP_OK) err = settings_erase("batt_warn_v");
        if (err == ESP_OK) err = settings_erase("batt_cut_v");
    } else if (!strcmp(key, "batt_div") || !strcmp(key, "batt_warn_v") || !strcmp(key, "batt_cut_v")) {
        err = settings_erase(key);
    } else {
        return ESP_ERR_NOT_FOUND;
    }
    battery_reload_settings();
    if (err == ESP_OK) log_settings();
    return err;
}

int battery_settings_line(char *buf, size_t n) {
    batt_t b = snap();
    return snprintf(buf, n, "effective battery settings: batt_pack=%s batt_warn_v=%g batt_cut_v=%g batt_div=%g",
                    b.pack->name, b.warn_v, b.cut_v, b.div);
}

// ------------------------------------------------------------------- sample

// Runs on the esp_timer task, after the lock is released.
static void log_change(batt_state_t was, const batt_t *b, float raw_v) {
    int pct = batt_percent(b->pack, b->volts);
    switch (b->mon.state) {
        case BATT_NONE:
            ESP_LOGW(TAG, "battery sense lost (pin %d mV): no low or cutoff protection until it reads again",
                     b->pin_mv);
            break;
        case BATT_OK:
            if (was == BATT_NONE) ESP_LOGI(TAG, "battery connected: %.2f V, %d%% (%s)", b->volts, pct, b->pack->name);
            else ESP_LOGI(TAG, "battery ok again: %.2f V, %d%%", b->volts, pct);
            break;
        case BATT_LOW:
            if (was == BATT_CUTOFF)
                ESP_LOGI(TAG, "battery out of cutoff, still low: %.2f V, %d%%", b->volts, pct);
            else
                ESP_LOGW(TAG, "battery LOW: %.2f V, %d%%, under the %.2f V %s warning for %d s; charge or swap the pack soon",
                         b->volts, pct, b->warn_v, b->pack->name, BATT_LOW_S);
            break;
        case BATT_CUTOFF: {
            if (b->mon.collapsed)
                ESP_LOGW(TAG, "battery CUTOFF: readings more than %.1f V under the %.2f V %s cutoff for %d s "
                         "(last %.2f V, filtered %.2f V); charge or swap the pack",
                         BATT_COLLAPSE_V, b->cut_v, b->pack->name, BATT_COLLAPSE_S, raw_v, b->volts);
            else
                ESP_LOGW(TAG, "battery CUTOFF: %.2f V, under the %.2f V %s cutoff for %d s; charge or swap the pack",
                         b->volts, b->cut_v, b->pack->name, BATT_CUT_S);
            // A cutoff from the wrong batt_pack names its fix where it is seen.
            char hint[128];
            if (batt_hint(hint, sizeof hint, b->pack, b->volts, b->cut_v)) ESP_LOGW(TAG, "%s", hint);
            break;
        }
    }
}

static void sample(void *arg) {
    (void)arg;
    if (!s_adc) return;
    int sum = 0, n = 0;
    for (int i = 0; i < 16; i++) {
        int raw, mv;
        if (adc_oneshot_read(s_adc, s_chan, &raw) != ESP_OK) continue;
        if (s_cali && adc_cali_raw_to_voltage(s_cali, raw, &mv) == ESP_OK) sum += mv;
        else sum += raw * 3300 / 4095;   // uncalibrated fallback, 12-bit at 12 dB
        n++;
    }
    if (!n) return;
    int mv = sum / n;
    bool present = mv > PRESENT_MV;

    portENTER_CRITICAL(&s_mux);
    batt_t *b = &s_batt;
    float v = mv * 0.001f * b->div;
    // One-pole at ~5 s so a motor surge does not swing the percentage. It
    // starts from the reading itself at boot and whenever a pack appears, so
    // one fitted later reads its voltage at once instead of climbing from zero.
    b->volts = (b->first || (present && !b->present)) ? v : b->volts + 0.2f * (v - b->volts);
    bool first = b->first;
    b->first = false;
    b->pin_mv = mv;
    b->present = present;
    batt_state_t was = b->mon.state;
    batt_monitor_step(&b->mon, present, b->volts, v, b->warn_v, b->cut_v, b->pack->hyst_v);
    batt_t now = *b;
    portEXIT_CRITICAL(&s_mux);

    // The first sample is battery_init()'s, which reports the state itself.
    if (now.mon.state != was && !first) log_change(was, &now, v);
}

esp_err_t battery_init(void) {
    battery_reload_settings();

    esp_err_t err = adc_oneshot_io_to_channel(CONFIG_UBOT_PIN_BATT_ADC, &s_unit, &s_chan);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "GPIO%d is not an ADC pin", CONFIG_UBOT_PIN_BATT_ADC);
        return err;
    }
    adc_oneshot_unit_init_cfg_t ucfg = { .unit_id = s_unit };
    err = adc_oneshot_new_unit(&ucfg, &s_adc);
    if (err != ESP_OK) return err;
    adc_oneshot_chan_cfg_t ccfg = { .atten = ADC_ATTEN_DB_12, .bitwidth = ADC_BITWIDTH_DEFAULT };
    err = adc_oneshot_config_channel(s_adc, s_chan, &ccfg);
    if (err != ESP_OK) return err;
    // No internal pull-down. An earlier version enabled one so a pin with
    // nothing on it would read zero rather than float, on the assumption it was
    // the ~45k the ESP32 docs quote. Measured on this S3 it is nearer 19k,
    // which put it in parallel with the divider's 10k lower leg, made the
    // effective leg 6.5k, and turned a nominal 11.0 ratio into 16.3 -- the pack
    // read 8.9 V against a meter's 13.24 V, a 33% under-read that looked like a
    // flat battery.
    //
    // The divider does that job anyway: with no pack connected, R8 ties the pin
    // to ground through 10k, so it reads zero and `battery_present()` says no
    // sense. The pull-down only bought protection for a board built without the
    // divider fitted, and it cost accuracy on every board that has one.
    gpio_set_pull_mode((gpio_num_t)CONFIG_UBOT_PIN_BATT_ADC, GPIO_FLOATING);

    adc_cali_curve_fitting_config_t cal = {
        .unit_id = s_unit, .chan = s_chan, .atten = ADC_ATTEN_DB_12, .bitwidth = ADC_BITWIDTH_DEFAULT,
    };
    if (adc_cali_create_scheme_curve_fitting(&cal, &s_cali) != ESP_OK) {
        ESP_LOGW(TAG, "no ADC calibration data; readings are nominal");
        s_cali = NULL;
    }

    sample(NULL);
    const esp_timer_create_args_t targs = { .callback = sample, .name = "batt" };
    err = esp_timer_create(&targs, &s_timer);
    if (err == ESP_OK) err = esp_timer_start_periodic(s_timer, 1000000);

    batt_t b = snap();
    char reading[48];
    if (b.present)
        snprintf(reading, sizeof reading, "%.2f V, %d%%, %s", b.volts, batt_percent(b.pack, b.volts),
                 batt_state_name(b.mon.state));
    else snprintf(reading, sizeof reading, "nothing connected");
    ESP_LOGI(TAG, "sense on GPIO%d (ADC%d ch%d), divider %.3f, pack %s (%s, %.1f..%.1f V), warn %.2f V, cut %.2f V: %s",
             CONFIG_UBOT_PIN_BATT_ADC, (int)s_unit + 1, (int)s_chan, b.div, b.pack->name, b.pack->label,
             b.pack->table[0].v, b.pack->table[b.pack->n - 1].v, b.warn_v, b.cut_v, reading);
    const char *hint = battery_hint();
    if (*hint) ESP_LOGW(TAG, "%s", hint);
    return err;
}

// ------------------------------------------------------------------ getters

float battery_voltage(void) {
    batt_t b = snap();
    return b.present ? b.volts : 0.0f;
}

int battery_pin_mv(void) { return snap().pin_mv; }
bool battery_present(void) { return snap().present; }

int battery_percent(void) {
    batt_t b = snap();
    return b.present ? batt_percent(b.pack, b.volts) : -1;
}

int battery_state(void) {
    // The drive asks every control tick, so this copies the one field.
    portENTER_CRITICAL(&s_mux);
    int state = s_batt.mon.state;
    portEXIT_CRITICAL(&s_mux);
    return state;
}

const char *battery_state_name(int state) { return batt_state_name(state); }
const char *battery_pack_name(void) { return snap().pack->name; }
float battery_warn_v(void) { return snap().warn_v; }
float battery_cut_v(void) { return snap().cut_v; }

const char *battery_hint(void) {
    static char hint[128];
    batt_t b = snap();
    batt_hint(hint, sizeof hint, b.present ? b.pack : NULL, b.volts, b.cut_v);
    return hint;
}
