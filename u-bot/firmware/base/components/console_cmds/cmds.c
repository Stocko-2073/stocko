#include "console_cmds.h"
#include "management.h"
#include "cJSON.h"

#include <stdio.h>
#include <math.h>
#include <stdlib.h>
#include <string.h>
#include <strings.h>

#include "battery.h"
#include "ble.h"
#include "drive.h"
#include "esp_console.h"
#include "esp_heap_caps.h"
#include "esp_log.h"
#include "esp_system.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "net.h"
#include "sdkconfig.h"
#include "settings.h"
#include "sysinfo.h"
#include "ulog.h"

static const char *TAG = "console";

// ------------------------------------------------------------------ helpers

static bool parse_f(const char *s, float *out) {
    if (!s || !*s) return false;
    char *end;
    float v = strtof(s, &end);
    if (end == s || *end || !isfinite(v)) return false;
    *out = v;
    return true;
}

static int wheel_arg(const char *s) {
    if (!s) return -1;
    if (!strcasecmp(s, "a")) return DRIVE_WHEEL_A;
    if (!strcasecmp(s, "b")) return DRIVE_WHEEL_B;
    return -1;
}

static const char *wheel_name(int w) { return w == 0 ? "A" : w == 1 ? "B" : "?"; }


static int report(command_context_t *ctx, esp_err_t err) {
    if (err == ESP_OK) return 0;
    if (err == ESP_ERR_INVALID_STATE) command_printf(ctx, "refused: %s\n", drive_refusal());
    else command_printf(ctx, "error: %s\n", esp_err_to_name(err));
    return 1;
}

static const char *magnet_text(uint8_t st) {
    if (!(st & 0x20)) return "none";
    if (st & 0x10) return "WEAK";
    if (st & 0x08) return "STRONG";
    return "ok";
}

// ------------------------------------------------------------------- status

static void print_wheel(command_context_t *ctx, const drive_status_t *s, int i) {
    const drive_wheel_status_t *w = &s->wheel[i];
    command_printf(ctx, "  wheel %s: driver %s, %s, loop %s%s, fault %s\n", wheel_name(i),
           w->driver_ok ? "configured" : "NEEDS VERIFICATION",
           w->enabled ? "enabled" : "disabled",
           w->loop_closed ? "closed" : "open",
           w->velocity_mode ? " (velocity)" : w->loop_closed ? " (position)" : "",
           drive_fault_name(w->fault));
    command_printf(ctx, "    pos %.4f turns  target %.4f  err %ld counts  slip %ld steps  vel %.3f turns/s  rate %.0f sps\n",
           w->pos_turns, w->target_turns, (long)w->err_counts, (long)w->slip_steps, w->vel_tps, w->rate_sps);
    command_printf(ctx, "    current %.0f/%.0f mA RMS run/hold (nominal); driver sample %s age %lu ms, GSTAT 0x%02lX DRV_STATUS 0x%08lX\n",
           w->run_ma, w->hold_ma, w->driver_status_ok ? "ok" : "unavailable",
           (unsigned long)w->driver_age_ms, (unsigned long)w->gstat, (unsigned long)w->drv_status);
    if (s->faulted) command_printf(ctx, "    at fault: driver sample %s age %lu ms, GSTAT 0x%02lX DRV_STATUS 0x%08lX\n",
           w->fault_driver_status_ok ? "ok" : "unavailable", (unsigned long)w->fault_driver_age_ms,
           (unsigned long)w->fault_gstat, (unsigned long)w->fault_drv_status);
    command_printf(ctx, "    encoder %s, raw %u, magnet %s, agc %u (aim ~64), worst read %lu us\n",
           w->encoder_ok ? "ok" : "NOT RESPONDING", w->raw_angle, magnet_text(w->magnet_status),
           w->agc, (unsigned long)w->worst_read_us);
    command_printf(ctx, "    shaft %s, clock gain %.4f (%s), kp %.1f vmax %.2f turns/s accel %.1f decel %.1f turns/s^2\n",
           w->inverted ? "INVERTED" : "normal", w->clock_gain,
           w->calibrated ? "measured this boot" : "stored", w->kp, w->vmax_tps, w->accel_tps2, w->decel_tps2);
}

static void print_drive(command_context_t *ctx) {
    drive_status_t s;
    drive_get_status(&s);
    command_printf(ctx, "drive: drivers %s, faults %s%s%s, control worst %lu us of %d us, bus writes %lu, echo faults %lu\n",
           s.enabled ? "ENABLED" : "disabled",
           s.faulted ? "LATCHED on wheel " : "none",
           s.faulted ? wheel_name(s.fault_wheel) : "",
           s.cal_busy ? ", CALIBRATING" : s.demo_running ? ", demo running" : "",
           (unsigned long)s.tick_worst_us, 1000000 / CONFIG_UBOT_CONTROL_HZ,
           (unsigned long)s.bus_writes, (unsigned long)s.bus_echo_faults);
    command_printf(ctx, "  command: %s v %.3f m/s w %.3f rad/s; limits %.3f m/s, %.2f rad/s\n",
           s.cmd_active ? "active" : "idle", s.v_mps, s.w_radps, s.vmax_mps, s.wmax_radps);
    command_printf(ctx, "  frame: sign_a %+d sign_b %+d, wheel A is %s, track %.3f m, wheel %.4f m/turn\n",
           s.sign_a, s.sign_b, s.a_is_left ? "left" : "right", s.track_m, s.wheel_circ_m);
    if (s.demo_running) command_printf(ctx, "  demo: %s\n", s.demo_caption);
    for (int i = 0; i < DRIVE_NWHEELS; i++) print_wheel(ctx, &s, i);
}

static void print_batt(command_context_t *ctx) {
    if (!battery_present()) command_printf(ctx, "battery: no sense (pin at %d mV)\n", battery_pin_mv());
    else command_printf(ctx, "battery: %.2f V, %d%% (pin %d mV)\n", battery_voltage(), battery_percent(), battery_pin_mv());
}

static void print_net(command_context_t *ctx) {
    net_status_t n;
    net_get_status(&n);
    if (!n.configured) command_printf(ctx, "wifi: not configured -- 'wifi set <ssid> <password>'\n");
    else command_printf(ctx,"wifi: %s, ip %s, rssi %d dBm, credential trial %s\n", n.connected?"connected":"disconnected",n.ip,n.rssi,net_wifi_trial_busy()?"active":"idle");
    command_printf(ctx, "websocket: %s, %d client%s\n", n.server_up ? "serving" : "down", n.ws_clients, n.ws_clients == 1 ? "" : "s");
    command_printf(ctx, "ota: %s\n", net_ota_status());
}

static void print_ble(command_context_t *ctx) {
    ble_status_t b;
    ble_get_status(&b);
    command_printf(ctx, "ble: %s as \"%s\", addr %s, %d connection%s\n",
           b.advertising ? "advertising" : "not advertising", sysinfo_name(), b.addr,
           b.connected, b.connected == 1 ? "" : "s");
}

static int cmd_version(command_context_t *ctx, int argc, char **argv) {
    command_printf(ctx, "%s %s, built %s, IDF %s\n", sysinfo_project(), sysinfo_fw_version(), sysinfo_build(), sysinfo_idf());
    command_printf(ctx, "hardware rev %s, serial %s, mac %s, name %s\n", sysinfo_hw_rev(), sysinfo_serial(), sysinfo_mac(), sysinfo_name());
    command_printf(ctx, "running %s (%s), reset: %s, up %lu s\n", sysinfo_partition(), sysinfo_ota_state(),
           sysinfo_reset_reason(), (unsigned long)sysinfo_uptime_s());
    return 0;
}

static int cmd_status(command_context_t *ctx, int argc, char **argv) {
    cmd_version(ctx, argc, argv);
    print_drive(ctx);
    print_batt(ctx);
    print_net(ctx);
    print_ble(ctx);
    return 0;
}

// -------------------------------------------------------------------- power

static int cmd_enable(command_context_t *ctx, int argc, char **argv) { return report(ctx, drive_enable(true)); }
static int cmd_disable(command_context_t *ctx, int argc, char **argv) { return report(ctx, drive_enable(false)); }
static int cmd_stop(command_context_t *ctx, int argc, char **argv) { drive_stop(); command_printf(ctx, "stopping\n"); return 0; }
static int cmd_estop(command_context_t *ctx, int argc, char **argv) { drive_estop(); command_printf(ctx, "EN high -- both drivers cut\n"); return 0; }

// ------------------------------------------------------------------- motion

static int cmd_drive(command_context_t *ctx, int argc, char **argv) {
    float v, w, secs = 2.0f;
    if (argc < 3 || !parse_f(argv[1], &v) || !parse_f(argv[2], &w) ||
        (argc > 3 && !parse_f(argv[3], &secs))) {
        command_printf(ctx, "usage: drive <v m/s> <w rad/s> [seconds, default 2, 0 = until stopped]\n");
        return 1;
    }
    uint32_t hold = secs <= 0 ? 0 : (uint32_t)(secs * 1000.0f);
    int rc = report(ctx, drive_set_velocity(v, w, hold));
    if (rc == 0) {
        vTaskDelay(pdMS_TO_TICKS(15));   // let a control tick apply it before reading back
        drive_status_t s;
        drive_get_status(&s);
        command_printf(ctx, "driving v %.3f m/s w %.3f rad/s%s\n", s.v_mps, s.w_radps,
               hold ? "" : " until 'stop'");
    }
    return rc;
}

static void print_params(command_context_t *ctx, int w) {
    size_t n;
    const char *const *names = drive_param_names(&n);
    command_printf(ctx, "wheel %s:", wheel_name(w));
    for (size_t i = 0; i < n; i++) {
        float v;
        if (drive_param_get((drive_wheel_t)w, names[i], &v) == ESP_OK) command_printf(ctx, " %s=%g", names[i], v);
    }
    command_printf(ctx, "\n");
}

static int cmd_wheel(command_context_t *ctx, int argc, char **argv) {
    int w = argc >= 2 ? wheel_arg(argv[1]) : -1;
    if (w < 0) {
        command_printf(ctx, "usage: wheel <A|B> [goto T | move T | vel TPS [secs] | spin SPS | zero | loop on|off |\n"
               "       invert on|off | reg HEX | kp|vmax|accel|decel|vmin|tol|maxslip|ratio|gain|micro [value]]\n");
        return 1;
    }
    if (argc == 2) { print_params(ctx, w); return 0; }
    const char *sub = argv[2];
    float v = 0;
    bool has = argc >= 4 && parse_f(argv[3], &v);

    if (!strcmp(sub, "goto")) { if (!has) { command_printf(ctx, "goto needs turns\n"); return 1; } return report(ctx, drive_wheel_goto(w, v)); }
    if (!strcmp(sub, "move")) { if (!has) { command_printf(ctx, "move needs turns\n"); return 1; } return report(ctx, drive_wheel_move(w, v)); }
    if (!strcmp(sub, "spin")) { if (!has) { command_printf(ctx, "spin needs steps/s\n"); return 1; } return report(ctx, drive_wheel_spin(w, v)); }
    if (!strcmp(sub, "vel")) {
        if (!has) { command_printf(ctx, "vel needs turns/s\n"); return 1; }
        float secs = 2.0f;
        if (argc > 4 && !parse_f(argv[4], &secs)) { command_printf(ctx, "bad seconds\n"); return 1; }
        return report(ctx, drive_wheel_velocity(w, v, secs <= 0 ? 0 : (uint32_t)(secs * 1000)));
    }
    if (!strcmp(sub, "zero")) return report(ctx, drive_wheel_zero(w));
    if (!strcmp(sub, "loop")) {
        if (argc < 4) { command_printf(ctx, "loop on|off\n"); return 1; }
        return report(ctx, drive_wheel_loop(w, !strcmp(argv[3], "on")));
    }
    if (!strcmp(sub, "invert")) {
        if (argc < 4) { command_printf(ctx, "invert on|off  (normally 'cal' decides this)\n"); return 1; }
        return report(ctx, drive_wheel_set_invert(w, !strcmp(argv[3], "on")));
    }
    if (!strcmp(sub, "reg")) {
        if (argc < 4) { command_printf(ctx, "reg <hex register>, e.g. reg 6F for DRV_STATUS\n"); return 1; }
        uint8_t reg = (uint8_t)strtoul(argv[3], NULL, 16);
        uint32_t val;
        if (!drive_wheel_read_reg(w, reg, &val)) { command_printf(ctx, "driver did not answer\n"); return 1; }
        command_printf(ctx, "wheel %s reg 0x%02X = 0x%08lX\n", wheel_name(w), reg, (unsigned long)val);
        // DRV_STATUS is the one register worth reading by hand often enough to
        // spell out: it is the only place the driver says what current and
        // which chopper it is ACTUALLY using. Read it with the wheel driving --
        // standing still, CS_ACTUAL has decayed to the hold current.
        if (reg == 0x6F) {
            command_printf(ctx, "  CS_ACTUAL %lu/31 (current in use, hold current at a standstill)\n",
                   (unsigned long)((val >> 16) & 0x1F));
            command_printf(ctx, "  chopper   %s\n", (val & (1UL << 30)) ? "StealthChop" : "SpreadCycle");
            command_printf(ctx, "  standstill %s\n", (val & (1UL << 31)) ? "yes" : "no");
            if (val & 0x01) command_printf(ctx, "  OTPW: overtemperature prewarning -- temperature warning (firmware stops both drivers)\n");
            if (val & 0x02) command_printf(ctx, "  OT: overtemperature SHUTDOWN -- the power stage is off\n");
            if (val & 0x3C) command_printf(ctx, "  short to ground or supply flagged (bits 2..5)\n");
            if (val & 0xC0) command_printf(ctx, "  open load flagged (bits 6..7) -- normal at a standstill or very low speed\n");
        }
        return 0;
    }
    // Tuning parameter: show or set.
    float cur;
    if (drive_param_get(w, sub, &cur) != ESP_OK) { command_printf(ctx, "unknown subcommand '%s'\n", sub); return 1; }
    if (has) {
        esp_err_t err = drive_param_set(w, sub, v);
        if (err != ESP_OK) return report(ctx, err);
        drive_param_get(w, sub, &cur);
    }
    command_printf(ctx, "wheel %s %s = %g\n", wheel_name(w), sub, cur);
    return 0;
}

static int cmd_zero(command_context_t *ctx, int argc, char **argv) {
    int rc = report(ctx, drive_wheel_zero(DRIVE_WHEEL_BOTH));
    if (!rc) command_printf(ctx, "both wheels zeroed here\n");
    return rc;
}

static int cmd_faults(command_context_t *ctx, int argc, char **argv) {
    if (argc >= 2 && !strcmp(argv[1], "clear")) return report(ctx, drive_clear_faults());
    drive_status_t s;
    drive_get_status(&s);
    command_printf(ctx, "faults: %s\n", s.faulted ? "LATCHED" : "none");
    for (int i = 0; i < DRIVE_NWHEELS; i++) {
        command_printf(ctx, "  wheel %s: %s\n", wheel_name(i), drive_fault_name(s.wheel[i].fault));
    }
    if (s.faulted) command_printf(ctx, "'faults clear' to resume\n");
    return 0;
}

static int cmd_cal(command_context_t *ctx, int argc, char **argv) {
    if (argc < 2) {
        command_printf(ctx, "usage: cal <A|B> | cal abort | cal show\n"
               "measures shaft polarity and the driver's clock gain: 3 turns out and back, ~11 s.\n"
               "the wheel must be free to turn. results are logged and stored in NVS.\n");
        return 1;
    }
    if (!strcmp(argv[1], "abort")) { drive_calibrate_abort(); command_printf(ctx, "aborting\n"); return 0; }
    if (!strcmp(argv[1], "show")) {
        drive_cal_result_t r;
        if (!drive_calibrate_last(&r)) { command_printf(ctx, "no calibration run yet this boot\n"); return 0; }
        command_printf(ctx, "last: wheel %s %s -- %+ld counts in %.3f s at %.0f sps, gain %.4f, back %+ld, residual %+ld%s (%s)\n",
               wheel_name(r.wheel), r.ok ? "ok" : "FAILED", (long)r.counts, r.seconds, r.sps,
               r.clock_gain, (long)r.back, (long)r.residual, r.flipped ? ", polarity flipped" : "", r.note);
        return 0;
    }
    int w = wheel_arg(argv[1]);
    if (w < 0) { command_printf(ctx, "which wheel, A or B?\n"); return 1; }
    int rc = report(ctx, drive_calibrate(w));
    if (!rc) command_printf(ctx, "calibrating wheel %s -- results follow in the log\n", wheel_name(w));
    return rc;
}

static int cmd_demo(command_context_t *ctx, int argc, char **argv) {
    if (argc < 2) { command_printf(ctx, "usage: demo short | demo bench <A|B> | demo stop\n"); return 1; }
    if (!strcmp(argv[1], "stop")) { drive_demo_stop(); return 0; }
    int solo = argc >= 3 ? wheel_arg(argv[2]) : DRIVE_WHEEL_A;
    if (!strcmp(argv[1], "bench") && solo < 0) { command_printf(ctx, "bench needs a wheel, A or B\n"); return 1; }
    esp_err_t err = drive_demo_start(argv[1], solo);
    if (err == ESP_ERR_NOT_FOUND) { command_printf(ctx, "no script called '%s'\n", argv[1]); return 1; }
    return report(ctx, err);
}

// ------------------------------------------------------------------- stream

static int cmd_stream(command_context_t *ctx, int argc, char **argv) {
    float hz = 20;
    if (argc < 2) { command_printf(ctx, "stream on [hz] | off\n"); return 0; }
    if (!strcmp(argv[1], "off")) return management_stream(ctx->client, 0);
    if (strcmp(argv[1], "on") || (argc > 2 && !parse_f(argv[2], &hz))) return 2;
    return management_stream(ctx->client, hz);
}

// ----------------------------------------------------------------- settings

static void dump_visit(const char *key, char type, const char *value, void *arg) {
    command_context_t *ctx = arg;
    if ((!strcmp(key, "wifi_pass") || !strcmp(key, "wifi_ssid"))) value = "********";
    command_printf(ctx, "  %-12s %s\n", key, value);
}

static int cmd_set(command_context_t *ctx, int argc, char **argv) {
    if (argc == 1) {
        command_printf(ctx, "stored in NVS:\n");
        settings_dump(dump_visit, ctx);
        command_printf(ctx, "effective drive settings:");
        size_t n;
        const char *const *names = drive_setting_names(&n);
        for (size_t i = 0; i < n; i++) {
            float v;
            if (drive_setting_get(names[i], &v) == ESP_OK) command_printf(ctx, " %s=%g", names[i], v);
        }
        command_printf(ctx, "\nothers: name hw_rev ota_url ota_auto batt_div\n");
        return 0;
    }
    if (argc < 3) { command_printf(ctx, "usage: set <key> <value>   (set alone lists)\n"); return 1; }
    const char *key = argv[1], *val = argv[2];
    float f;
    esp_err_t err;
    if (!strcmp(key, "name")) err = sysinfo_set_name(val);
    else if (!strcmp(key, "hw_rev")) err = sysinfo_set_hw_rev(val);
    else if (!strcmp(key, "ota_url")) err = net_ota_set_url(val);
    else if (!strcmp(key, "ota_auto")) err = atoi(val) ? ESP_ERR_NOT_SUPPORTED : settings_set_i32(key, 0);
    else if (!strcmp(key, "batt_div")) {
        if (!parse_f(val, &f)) { command_printf(ctx, "needs a number\n"); return 1; }
        err = settings_set_f32(key, f);
        battery_reload_settings();
    } else {
        if (!parse_f(val, &f)) { command_printf(ctx, "needs a number\n"); return 1; }
        err = drive_setting_set(key, f);
        if (err == ESP_ERR_NOT_FOUND) { command_printf(ctx, "unknown setting '%s'\n", key); return 1; }
    }
    if (err != ESP_OK) return report(ctx, err);
    command_printf(ctx, "%s = %s\n", key, val);
    if (!strcmp(key, "name")) command_printf(ctx, "takes effect for mDNS and BLE after a reboot\n");
    return 0;
}

static int cmd_unset(command_context_t *ctx, int argc, char **argv) {
    if (argc < 2) { command_printf(ctx, "usage: unset <key>\n"); return 1; }
    esp_err_t err = settings_erase(argv[1]);
    if (err != ESP_OK) return report(ctx, err);
    command_printf(ctx, "%s erased -- the default applies after a reboot\n", argv[1]);
    return 0;
}

static int cmd_hw(command_context_t *ctx, int argc, char **argv) {
    if (argc >= 3 && !strcmp(argv[1], "set")) {
        int rc = report(ctx, sysinfo_set_hw_rev(argv[2]));
        if (!rc) command_printf(ctx, "hardware revision now %s\n", sysinfo_hw_rev());
        return rc;
    }
    command_printf(ctx, "hardware revision %s  (hw set <rev> to change)\n", sysinfo_hw_rev());
    return 0;
}

// --------------------------------------------------------------------- wifi

static void scan_emit(const char *ssid, int rssi, const char *auth, void *arg) {
    command_context_t *ctx = arg;
    command_printf(ctx, "  %-32s %4d dBm  %s\n", ssid, rssi, auth);
}

static int cmd_wifi(command_context_t *ctx, int argc, char **argv) {
    if (argc == 1) { print_net(ctx); return 0; }
    if (!strcmp(argv[1], "ps")) {
        if (argc != 3 || (strcmp(argv[2], "on") && strcmp(argv[2], "off"))) {
            command_printf(ctx, "usage: wifi ps on|off (runtime only; boot defaults off)\n");
            return 1;
        }
        return report(ctx, net_wifi_power_save(!strcmp(argv[2], "on")));
    }
    if (!strcmp(argv[1], "set")) {
        if (argc < 3) { command_printf(ctx, "usage: wifi set <ssid> [password]\n"); return 1; }
        int rc = report(ctx, net_wifi_set(argv[2], argc > 3 ? argv[3] : ""));
        if (!rc) command_printf(ctx, "credential trial started\n");
        return rc;
    }
    if (!strcmp(argv[1], "clear")) { int rc = report(ctx, net_wifi_clear()); if (!rc) command_printf(ctx, "credentials erased\n"); return rc; }
    if (!strcmp(argv[1], "reconnect")) return report(ctx, net_wifi_reconnect());
    if (!strcmp(argv[1], "scan")) {
        command_printf(ctx, "scanning...\n");
        return report(ctx, net_wifi_scan(scan_emit, ctx));
    }
    command_printf(ctx, "usage: wifi | wifi set <ssid> [password] | wifi clear | wifi scan | wifi reconnect | wifi ps on|off\n");
    return 1;
}

static int cmd_ota(command_context_t *ctx, int argc, char **argv) {
    if (argc == 1) {
        char url[200];
        command_printf(ctx, "ota: %s\n", net_ota_status());
        if (net_ota_available()[0]) command_printf(ctx, "available: %s (running %s)\n", net_ota_available(), sysinfo_fw_version());
        command_printf(ctx, "stored url: %s\n", net_ota_get_url(url, sizeof url) ? url : "(none)");
        command_printf(ctx, "running %s (%s); verified fallback %s\n", sysinfo_partition(), sysinfo_ota_state(),net_ota_can_rollback()?"available":"unavailable");
        return 0;
    }
    if (!strcmp(argv[1], "url")) {
        if (argc < 3) { command_printf(ctx, "usage: ota url <https://bucket-base-url>\n"); return 1; }
        return report(ctx, net_ota_set_url(argv[2]));
    }
    if (!strcmp(argv[1], "confirm")) { command_printf(ctx, "use management confirm with expected image identity\n"); return 2; }
    if (!strcmp(argv[1], "cancel")) { net_ota_cancel(); return 0; }
    if (!strcmp(argv[1], "start")) return report(ctx, net_ota_start(argc > 2 ? argv[2] : NULL));
    if (!strcmp(argv[1], "check")) {
        int rc = report(ctx, net_ota_check(false));
        if (!rc) command_printf(ctx, "checking release manifest -- completion is reported as a job\n");
        return rc;
    }
    if (!strncmp(argv[1], "http", 4)) return report(ctx, net_ota_start(argv[1]));
    command_printf(ctx, "usage: ota | ota check | ota start [manifest-url] | ota url <bucket>\n"
           "  automatic installation is disabled\n");
    return 1;
}

static int cmd_batt(command_context_t *ctx, int argc, char **argv) { print_batt(ctx); return 0; }
static int cmd_ble(command_context_t *ctx, int argc, char **argv) { print_ble(ctx); return 0; }

static int cmd_log(command_context_t *ctx, int argc, char **argv) {
    if (argc < 3) {
        command_printf(ctx, "usage: log <tag|*> <none|error|warn|info|debug|verbose>\n"
               "tags: drive demo wifi ws ota ble batt console settings ...\n");
        return 1;
    }
    esp_err_t err = ulog_set_level(argv[1], argv[2]);
    if (err != ESP_OK) { command_printf(ctx, "bad level '%s'\n", argv[2]); return 1; }
    command_printf(ctx, "log %s -> %s\n", argv[1], argv[2]);
    return 0;
}

static int cmd_stats(command_context_t *ctx, int argc, char **argv) {
    if (argc >= 2 && !strcmp(argv[1], "reset")) { drive_reset_stats(); command_printf(ctx, "stats reset\n"); return 0; }
    drive_status_t s;
    drive_get_status(&s);
    command_printf(ctx, "control: worst tick %lu us of %d us over %lu ticks; bus writes %lu, echo faults %lu\n",
           (unsigned long)s.tick_worst_us, 1000000 / CONFIG_UBOT_CONTROL_HZ, (unsigned long)s.tick_count,
           (unsigned long)s.bus_writes, (unsigned long)s.bus_echo_faults);
    for (int i = 0; i < DRIVE_NWHEELS; i++) {
        command_printf(ctx, "wheel %s: worst encoder read %lu us\n", wheel_name(i), (unsigned long)s.wheel[i].worst_read_us);
    }
    command_printf(ctx, "log lines dropped (host not reading): %u\n", ulog_dropped());
    return 0;
}

static int cmd_free(command_context_t *ctx, int argc, char **argv) {
    command_printf(ctx, "heap free %u, min ever %u, largest block %u\n",
           (unsigned)heap_caps_get_free_size(MALLOC_CAP_DEFAULT),
           (unsigned)heap_caps_get_minimum_free_size(MALLOC_CAP_DEFAULT),
           (unsigned)heap_caps_get_largest_free_block(MALLOC_CAP_DEFAULT));
    return 0;
}

static void reboot_task(void *arg) { vTaskDelay(pdMS_TO_TICKS(1000)); esp_restart(); }
static int cmd_reboot(command_context_t *ctx, int argc, char **argv) {
    drive_estop();
    command_printf(ctx, "rebooting\n");
    if(xTaskCreate(reboot_task,"reboot",2048,NULL,3,NULL)!=pdPASS)return 1;
    return 0;
}

// ------------------------------------------------------------------- setup

typedef struct { const char *name, *help; command_handler_t fn; } entry_t;
static entry_t entries[32];
static int entry_count;
static mgmt_client_t serial_client;
static unsigned serial_id;
static int serial_dispatch(int argc, char **argv) {
    cJSON *r = cJSON_CreateObject(), *args = cJSON_AddArrayToObject(r, "args");
    cJSON_AddStringToObject(r, "op", "exec");
    cJSON_AddNumberToObject(r, "id", ++serial_id);
    cJSON_AddNumberToObject(r, "session", serial_client);
    for (int i=0; i<argc; i++) cJSON_AddItemToArray(args, cJSON_CreateString(argv[i]));
    char *json = cJSON_PrintUnformatted(r);
    esp_err_t err = json ? management_receive(serial_client, json) : ESP_ERR_NO_MEM;
    free(json); cJSON_Delete(r);
    return err == ESP_OK ? 0 : 1;
}
static void serial_output(void *arg) {
    char frame[MGMT_FRAME];
    for (;;) {
        while (management_pop(serial_client, frame)) {
            cJSON *r = cJSON_Parse(frame);
            const char *data = cJSON_GetStringValue(cJSON_GetObjectItem(r, "data"));
            if (data) fputs(data, stdout);
            else printf("%s\n", frame);
            cJSON_Delete(r);
        }
        vTaskDelay(pdMS_TO_TICKS(20));
    }
}
static int execute(command_context_t *ctx, int argc, char **argv) {
    if (!argc) return 2;
    if (!strcmp(argv[0], "help")) {
        for (int i=0;i<entry_count;i++) command_printf(ctx, "%s: %s\n", entries[i].name, entries[i].help);
        return 0;
    }
    for (int i=0;i<entry_count;i++) if (!strcmp(entries[i].name, argv[0])) return entries[i].fn(ctx, argc, argv);
    command_printf(ctx, "unknown command\n");
    return 2;
}
static void reg(const char *cmd, const char *help, const char *hint, command_handler_t fn) {
    entries[entry_count++] = (entry_t){cmd, help, fn};
    const esp_console_cmd_t c = { .command = cmd, .help = help, .hint = hint, .func = serial_dispatch };
    ESP_ERROR_CHECK(esp_console_cmd_register(&c));
}

esp_err_t console_start(void) {
    esp_console_repl_t *repl = NULL;
    esp_console_repl_config_t rc = ESP_CONSOLE_REPL_CONFIG_DEFAULT();
    rc.prompt = "ubot> ";
    rc.max_cmdline_length = 256;
    rc.task_stack_size = 6144;

    ESP_ERROR_CHECK(management_init(execute));
    serial_client = management_open();
    esp_console_register_help_command();
    reg("status",  "everything: versions, drive, battery, wifi, ble", NULL, cmd_status);
    reg("version", "firmware and hardware revision", NULL, cmd_version);
    reg("hw",      "hardware revision: hw | hw set <rev>", NULL, cmd_hw);
    reg("enable",  "energise both drivers (EN low, VACTUAL zeroed first)", NULL, cmd_enable);
    reg("disable", "cut both drivers (EN high)", NULL, cmd_disable);
    reg("stop",    "ramp every wheel to zero, cancel timed commands", NULL, cmd_stop);
    reg("estop",   "emergency stop: EN high immediately", NULL, cmd_estop);
    reg("drive",   "robot-frame velocity: drive <v m/s> <w rad/s> [secs]", "<v> <w> [secs]", cmd_drive);
    reg("wheel",   "bench control of one wheel: wheel <A|B> [subcommand]", "<A|B> ...", cmd_wheel);
    reg("zero",    "define here as position zero on both wheels", NULL, cmd_zero);
    reg("faults",  "show faults | faults clear", NULL, cmd_faults);
    reg("cal",     "calibrate a wheel's shaft polarity and clock gain: cal <A|B>", "<A|B>|abort|show", cmd_cal);
    reg("demo",    "scripted runs: demo short | demo bench <A|B> | demo stop", NULL, cmd_demo);
    reg("stream",  "CSV telemetry: stream on [hz] | stream off", NULL, cmd_stream);
    reg("set",     "settings: set | set <key> <value>", NULL, cmd_set);
    reg("unset",   "erase a stored setting", "<key>", cmd_unset);
    reg("wifi",    "wifi | wifi set <ssid> [pass] | wifi clear | wifi scan | wifi reconnect", NULL, cmd_wifi);
    reg("ota",     "ota | ota check | ota start [url] | ota url <bucket> | ota confirm", NULL, cmd_ota);
    reg("batt",    "battery voltage and charge", NULL, cmd_batt);
    reg("ble",     "BLE state", NULL, cmd_ble);
    reg("log",     "log <tag|*> <level>", "<tag> <level>", cmd_log);
    reg("stats",   "control timing: stats | stats reset", NULL, cmd_stats);
    reg("free",    "heap", NULL, cmd_free);
    reg("reboot",  "cut the drivers and restart", NULL, cmd_reboot);

    esp_console_dev_usb_serial_jtag_config_t hw = ESP_CONSOLE_DEV_USB_SERIAL_JTAG_CONFIG_DEFAULT();
    esp_err_t err = esp_console_new_repl_usb_serial_jtag(&hw, &rc, &repl);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "console failed to start: %s", esp_err_to_name(err));
        return err;
    }
    xTaskCreate(serial_output, "serial_out", 4096, NULL, 2, NULL);
    printf("\nU-BOT base %s -- 'help' for commands, 'status' for the picture\n", sysinfo_fw_version());
    return esp_console_start_repl(repl);
}
