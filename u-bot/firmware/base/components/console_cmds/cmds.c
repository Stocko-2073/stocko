#include "console_cmds.h"

#include <stdio.h>
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
    if (end == s || *end) return false;
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

static const char *onoff(bool b) { return b ? "on" : "off"; }

static int report(esp_err_t err) {
    if (err == ESP_OK) return 0;
    if (err == ESP_ERR_INVALID_STATE) printf("refused: %s\n", drive_refusal());
    else printf("error: %s\n", esp_err_to_name(err));
    return 1;
}

static const char *magnet_text(uint8_t st) {
    if (!(st & 0x20)) return "none";
    if (st & 0x10) return "WEAK";
    if (st & 0x08) return "STRONG";
    return "ok";
}

// ------------------------------------------------------------------- status

static void print_wheel(const drive_status_t *s, int i) {
    const drive_wheel_status_t *w = &s->wheel[i];
    printf("  wheel %s: driver %s, %s, loop %s%s, fault %s\n", wheel_name(i),
           w->driver_ok ? "ok" : "NOT ANSWERING",
           w->enabled ? "enabled" : "disabled",
           w->loop_closed ? "closed" : "open",
           w->velocity_mode ? " (velocity)" : w->loop_closed ? " (position)" : "",
           drive_fault_name(w->fault));
    printf("    pos %.4f turns  target %.4f  err %ld counts  slip %ld steps  vel %.3f turns/s  rate %.0f sps\n",
           w->pos_turns, w->target_turns, (long)w->err_counts, (long)w->slip_steps, w->vel_tps, w->rate_sps);
    printf("    encoder %s, raw %u, magnet %s, agc %u (aim ~64), worst read %lu us\n",
           w->encoder_ok ? "ok" : "NOT RESPONDING", w->raw_angle, magnet_text(w->magnet_status),
           w->agc, (unsigned long)w->worst_read_us);
    printf("    shaft %s, clock gain %.4f (%s), kp %.1f vmax %.2f turns/s accel %.1f turns/s^2\n",
           w->inverted ? "INVERTED" : "normal", w->clock_gain,
           w->calibrated ? "measured this boot" : "stored", w->kp, w->vmax_tps, w->accel_tps2);
}

static void print_drive(void) {
    drive_status_t s;
    drive_get_status(&s);
    printf("drive: drivers %s, faults %s%s%s, control worst %lu us of %d us, bus writes %lu, echo faults %lu\n",
           s.enabled ? "ENABLED" : "disabled",
           s.faulted ? "LATCHED on wheel " : "none",
           s.faulted ? wheel_name(s.fault_wheel) : "",
           s.cal_busy ? ", CALIBRATING" : s.demo_running ? ", demo running" : "",
           (unsigned long)s.tick_worst_us, 1000000 / CONFIG_UBOT_CONTROL_HZ,
           (unsigned long)s.bus_writes, (unsigned long)s.bus_echo_faults);
    printf("  command: %s v %.3f m/s w %.3f rad/s; limits %.3f m/s, %.2f rad/s\n",
           s.cmd_active ? "active" : "idle", s.v_mps, s.w_radps, s.vmax_mps, s.wmax_radps);
    printf("  frame: sign_a %+d sign_b %+d, wheel A is %s, track %.3f m, wheel %.4f m/turn\n",
           s.sign_a, s.sign_b, s.a_is_left ? "left" : "right", s.track_m, s.wheel_circ_m);
    if (s.demo_running) printf("  demo: %s\n", s.demo_caption);
    for (int i = 0; i < DRIVE_NWHEELS; i++) print_wheel(&s, i);
}

static void print_batt(void) {
    if (!battery_present()) printf("battery: no sense (pin at %d mV)\n", battery_pin_mv());
    else printf("battery: %.2f V, %d%% (pin %d mV)\n", battery_voltage(), battery_percent(), battery_pin_mv());
}

static void print_net(void) {
    net_status_t n;
    net_get_status(&n);
    if (!n.configured) printf("wifi: not configured -- 'wifi set <ssid> <password>'\n");
    else if (n.connected) printf("wifi: connected to \"%s\", ip %s, rssi %d dBm, http://%s.local/ ws://%s.local/ws\n",
                                 n.ssid, n.ip, n.rssi, n.hostname, n.hostname);
    else printf("wifi: \"%s\" configured, not connected%s\n", n.ssid, n.started ? " (retrying)" : "");
    printf("websocket: %s, %d client%s\n", n.server_up ? "serving" : "down", n.ws_clients, n.ws_clients == 1 ? "" : "s");
    printf("ota: %s\n", net_ota_status());
}

static void print_ble(void) {
    ble_status_t b;
    ble_get_status(&b);
    printf("ble: %s as \"%s\", addr %s, %d connection%s\n",
           b.advertising ? "advertising" : "not advertising", sysinfo_name(), b.addr,
           b.connected, b.connected == 1 ? "" : "s");
}

static int cmd_version(int argc, char **argv) {
    printf("%s %s, built %s, IDF %s\n", sysinfo_project(), sysinfo_fw_version(), sysinfo_build(), sysinfo_idf());
    printf("hardware rev %s, serial %s, mac %s, name %s\n", sysinfo_hw_rev(), sysinfo_serial(), sysinfo_mac(), sysinfo_name());
    printf("running %s (%s), reset: %s, up %lu s\n", sysinfo_partition(), sysinfo_ota_state(),
           sysinfo_reset_reason(), (unsigned long)sysinfo_uptime_s());
    return 0;
}

static int cmd_status(int argc, char **argv) {
    cmd_version(argc, argv);
    print_drive();
    print_batt();
    print_net();
    print_ble();
    return 0;
}

// -------------------------------------------------------------------- power

static int cmd_enable(int argc, char **argv) { return report(drive_enable(true)); }
static int cmd_disable(int argc, char **argv) { return report(drive_enable(false)); }
static int cmd_stop(int argc, char **argv) { drive_stop(); printf("stopping\n"); return 0; }
static int cmd_estop(int argc, char **argv) { drive_estop(); printf("EN high -- both drivers cut\n"); return 0; }

// ------------------------------------------------------------------- motion

static int cmd_drive(int argc, char **argv) {
    float v, w, secs = 2.0f;
    if (argc < 3 || !parse_f(argv[1], &v) || !parse_f(argv[2], &w) ||
        (argc > 3 && !parse_f(argv[3], &secs))) {
        printf("usage: drive <v m/s> <w rad/s> [seconds, default 2, 0 = until stopped]\n");
        return 1;
    }
    uint32_t hold = secs <= 0 ? 0 : (uint32_t)(secs * 1000.0f);
    int rc = report(drive_set_velocity(v, w, hold));
    if (rc == 0) {
        vTaskDelay(pdMS_TO_TICKS(15));   // let a control tick apply it before reading back
        drive_status_t s;
        drive_get_status(&s);
        printf("driving v %.3f m/s w %.3f rad/s%s\n", s.v_mps, s.w_radps,
               hold ? "" : " until 'stop'");
    }
    return rc;
}

static void print_params(int w) {
    size_t n;
    const char *const *names = drive_param_names(&n);
    printf("wheel %s:", wheel_name(w));
    for (size_t i = 0; i < n; i++) {
        float v;
        if (drive_param_get((drive_wheel_t)w, names[i], &v) == ESP_OK) printf(" %s=%g", names[i], v);
    }
    printf("\n");
}

static int cmd_wheel(int argc, char **argv) {
    int w = argc >= 2 ? wheel_arg(argv[1]) : -1;
    if (w < 0) {
        printf("usage: wheel <A|B> [goto T | move T | vel TPS [secs] | spin SPS | zero | loop on|off |\n"
               "       invert on|off | reg HEX | kp|vmax|accel|vmin|tol|maxslip|ratio|gain|micro [value]]\n");
        return 1;
    }
    if (argc == 2) { print_params(w); return 0; }
    const char *sub = argv[2];
    float v = 0;
    bool has = argc >= 4 && parse_f(argv[3], &v);

    if (!strcmp(sub, "goto")) { if (!has) { printf("goto needs turns\n"); return 1; } return report(drive_wheel_goto(w, v)); }
    if (!strcmp(sub, "move")) { if (!has) { printf("move needs turns\n"); return 1; } return report(drive_wheel_move(w, v)); }
    if (!strcmp(sub, "spin")) { if (!has) { printf("spin needs steps/s\n"); return 1; } return report(drive_wheel_spin(w, v)); }
    if (!strcmp(sub, "vel")) {
        if (!has) { printf("vel needs turns/s\n"); return 1; }
        float secs = 2.0f;
        if (argc > 4 && !parse_f(argv[4], &secs)) { printf("bad seconds\n"); return 1; }
        return report(drive_wheel_velocity(w, v, secs <= 0 ? 0 : (uint32_t)(secs * 1000)));
    }
    if (!strcmp(sub, "zero")) return report(drive_wheel_zero(w));
    if (!strcmp(sub, "loop")) {
        if (argc < 4) { printf("loop on|off\n"); return 1; }
        return report(drive_wheel_loop(w, !strcmp(argv[3], "on")));
    }
    if (!strcmp(sub, "invert")) {
        if (argc < 4) { printf("invert on|off  (normally 'cal' decides this)\n"); return 1; }
        return report(drive_wheel_set_invert(w, !strcmp(argv[3], "on")));
    }
    if (!strcmp(sub, "reg")) {
        if (argc < 4) { printf("reg <hex register>, e.g. reg 6F for DRV_STATUS\n"); return 1; }
        uint8_t reg = (uint8_t)strtoul(argv[3], NULL, 16);
        uint32_t val;
        if (!drive_wheel_read_reg(w, reg, &val)) { printf("driver did not answer\n"); return 1; }
        printf("wheel %s reg 0x%02X = 0x%08lX\n", wheel_name(w), reg, (unsigned long)val);
        return 0;
    }
    // Tuning parameter: show or set.
    float cur;
    if (drive_param_get(w, sub, &cur) != ESP_OK) { printf("unknown subcommand '%s'\n", sub); return 1; }
    if (has) {
        esp_err_t err = drive_param_set(w, sub, v);
        if (err != ESP_OK) return report(err);
        drive_param_get(w, sub, &cur);
    }
    printf("wheel %s %s = %g\n", wheel_name(w), sub, cur);
    return 0;
}

static int cmd_zero(int argc, char **argv) {
    int rc = report(drive_wheel_zero(DRIVE_WHEEL_BOTH));
    if (!rc) printf("both wheels zeroed here\n");
    return rc;
}

static int cmd_faults(int argc, char **argv) {
    if (argc >= 2 && !strcmp(argv[1], "clear")) return report(drive_clear_faults());
    drive_status_t s;
    drive_get_status(&s);
    printf("faults: %s\n", s.faulted ? "LATCHED" : "none");
    for (int i = 0; i < DRIVE_NWHEELS; i++) {
        printf("  wheel %s: %s\n", wheel_name(i), drive_fault_name(s.wheel[i].fault));
    }
    if (s.faulted) printf("'faults clear' to resume\n");
    return 0;
}

static int cmd_cal(int argc, char **argv) {
    if (argc < 2) {
        printf("usage: cal <A|B> | cal abort | cal show\n"
               "measures shaft polarity and the driver's clock gain: 3 turns out and back, ~11 s.\n"
               "the wheel must be free to turn. results are logged and stored in NVS.\n");
        return 1;
    }
    if (!strcmp(argv[1], "abort")) { drive_calibrate_abort(); printf("aborting\n"); return 0; }
    if (!strcmp(argv[1], "show")) {
        drive_cal_result_t r;
        if (!drive_calibrate_last(&r)) { printf("no calibration run yet this boot\n"); return 0; }
        printf("last: wheel %s %s -- %+ld counts in %.3f s at %.0f sps, gain %.4f, back %+ld, residual %+ld%s (%s)\n",
               wheel_name(r.wheel), r.ok ? "ok" : "FAILED", (long)r.counts, r.seconds, r.sps,
               r.clock_gain, (long)r.back, (long)r.residual, r.flipped ? ", polarity flipped" : "", r.note);
        return 0;
    }
    int w = wheel_arg(argv[1]);
    if (w < 0) { printf("which wheel, A or B?\n"); return 1; }
    int rc = report(drive_calibrate(w));
    if (!rc) printf("calibrating wheel %s -- results follow in the log\n", wheel_name(w));
    return rc;
}

static int cmd_demo(int argc, char **argv) {
    if (argc < 2) { printf("usage: demo short | demo bench <A|B> | demo stop\n"); return 1; }
    if (!strcmp(argv[1], "stop")) { drive_demo_stop(); return 0; }
    int solo = argc >= 3 ? wheel_arg(argv[2]) : DRIVE_WHEEL_A;
    if (!strcmp(argv[1], "bench") && solo < 0) { printf("bench needs a wheel, A or B\n"); return 1; }
    esp_err_t err = drive_demo_start(argv[1], solo);
    if (err == ESP_ERR_NOT_FOUND) { printf("no script called '%s'\n", argv[1]); return 1; }
    return report(err);
}

// ------------------------------------------------------------------- stream

static TaskHandle_t s_stream = NULL;
static volatile bool s_stream_run = false;
static uint32_t s_stream_ms = 50;

static void stream_task(void *arg) {
    char line[256];
    printf("# %s\n", drive_csv_header());
    while (s_stream_run) {
        drive_csv_line(line, sizeof line);
        printf("%s\n", line);
        vTaskDelay(pdMS_TO_TICKS(s_stream_ms));
    }
    s_stream = NULL;
    vTaskDelete(NULL);
}

static int cmd_stream(int argc, char **argv) {
    if (argc < 2) { printf("stream %s; usage: stream on [hz] | stream off\n", onoff(s_stream_run)); return 0; }
    if (!strcmp(argv[1], "off")) { s_stream_run = false; return 0; }
    if (!strcmp(argv[1], "on")) {
        float hz = 20;
        if (argc > 2 && (!parse_f(argv[2], &hz) || hz < 0.5f || hz > 200)) { printf("hz 0.5..200\n"); return 1; }
        s_stream_ms = (uint32_t)(1000.0f / hz);
        if (!s_stream_run) {
            s_stream_run = true;
            xTaskCreate(stream_task, "stream", 3072, NULL, 3, &s_stream);
        }
        return 0;
    }
    printf("stream on|off\n");
    return 1;
}

// ----------------------------------------------------------------- settings

static void dump_visit(const char *key, char type, const char *value, void *arg) {
    if (!strcmp(key, "wifi_pass")) value = "********";
    printf("  %-12s %s\n", key, value);
}

static int cmd_set(int argc, char **argv) {
    if (argc == 1) {
        printf("stored in NVS:\n");
        settings_dump(dump_visit, NULL);
        printf("effective drive settings:");
        size_t n;
        const char *const *names = drive_setting_names(&n);
        for (size_t i = 0; i < n; i++) {
            float v;
            if (drive_setting_get(names[i], &v) == ESP_OK) printf(" %s=%g", names[i], v);
        }
        printf("\nothers: name hw_rev ota_url ota_auto batt_div batt_vmin batt_vmax\n");
        return 0;
    }
    if (argc < 3) { printf("usage: set <key> <value>   (set alone lists)\n"); return 1; }
    const char *key = argv[1], *val = argv[2];
    float f;
    esp_err_t err;
    if (!strcmp(key, "name")) err = sysinfo_set_name(val);
    else if (!strcmp(key, "hw_rev")) err = sysinfo_set_hw_rev(val);
    else if (!strcmp(key, "ota_url")) err = net_ota_set_url(val);
    else if (!strcmp(key, "ota_auto")) err = settings_set_i32(key, atoi(val) != 0);
    else if (!strcmp(key, "batt_div") || !strcmp(key, "batt_vmin") || !strcmp(key, "batt_vmax")) {
        if (!parse_f(val, &f)) { printf("needs a number\n"); return 1; }
        err = settings_set_f32(key, f);
        battery_reload_settings();
    } else {
        if (!parse_f(val, &f)) { printf("needs a number\n"); return 1; }
        err = drive_setting_set(key, f);
        if (err == ESP_ERR_NOT_FOUND) { printf("unknown setting '%s'\n", key); return 1; }
    }
    if (err != ESP_OK) return report(err);
    printf("%s = %s\n", key, val);
    if (!strcmp(key, "name")) printf("takes effect for mDNS and BLE after a reboot\n");
    return 0;
}

static int cmd_unset(int argc, char **argv) {
    if (argc < 2) { printf("usage: unset <key>\n"); return 1; }
    esp_err_t err = settings_erase(argv[1]);
    if (err != ESP_OK) return report(err);
    printf("%s erased -- the default applies after a reboot\n", argv[1]);
    return 0;
}

static int cmd_hw(int argc, char **argv) {
    if (argc >= 3 && !strcmp(argv[1], "set")) {
        int rc = report(sysinfo_set_hw_rev(argv[2]));
        if (!rc) printf("hardware revision now %s\n", sysinfo_hw_rev());
        return rc;
    }
    printf("hardware revision %s  (hw set <rev> to change)\n", sysinfo_hw_rev());
    return 0;
}

// --------------------------------------------------------------------- wifi

static void scan_emit(const char *ssid, int rssi, const char *auth, void *arg) {
    printf("  %-32s %4d dBm  %s\n", ssid, rssi, auth);
}

static int cmd_wifi(int argc, char **argv) {
    if (argc == 1) { print_net(); return 0; }
    if (!strcmp(argv[1], "set")) {
        if (argc < 3) { printf("usage: wifi set <ssid> [password]\n"); return 1; }
        int rc = report(net_wifi_set(argv[2], argc > 3 ? argv[3] : ""));
        if (!rc) printf("stored; connecting to \"%s\"\n", argv[2]);
        return rc;
    }
    if (!strcmp(argv[1], "clear")) { int rc = report(net_wifi_clear()); if (!rc) printf("credentials erased\n"); return rc; }
    if (!strcmp(argv[1], "reconnect")) return report(net_wifi_reconnect());
    if (!strcmp(argv[1], "scan")) {
        printf("scanning...\n");
        return report(net_wifi_scan(scan_emit, NULL));
    }
    printf("usage: wifi | wifi set <ssid> [password] | wifi clear | wifi scan | wifi reconnect\n");
    return 1;
}

static int cmd_ota(int argc, char **argv) {
    if (argc == 1) {
        char url[200];
        printf("ota: %s\n", net_ota_status());
        if (net_ota_available()[0]) printf("available: %s (running %s)\n", net_ota_available(), sysinfo_fw_version());
        printf("stored url: %s\n", net_ota_get_url(url, sizeof url) ? url : "(none)");
        printf("running %s (%s)\n", sysinfo_partition(), sysinfo_ota_state());
        return 0;
    }
    if (!strcmp(argv[1], "url")) {
        if (argc < 3) { printf("usage: ota url <https://bucket-base-url>\n"); return 1; }
        return report(net_ota_set_url(argv[2]));
    }
    if (!strcmp(argv[1], "confirm")) { int rc = report(net_ota_confirm()); if (!rc) printf("this image is marked valid\n"); return rc; }
    if (!strcmp(argv[1], "start")) return report(net_ota_start(argc > 2 ? argv[2] : NULL));
    if (!strcmp(argv[1], "check")) {
        int rc = report(net_ota_check(true));
        if (!rc) printf("checking version.txt in the bucket -- result in the log\n");
        return rc;
    }
    if (!strncmp(argv[1], "http", 4)) return report(net_ota_start(argv[1]));
    printf("usage: ota | ota check | ota start [url] | ota <https://x.bin> | ota url <bucket> | ota confirm\n"
           "  set ota_auto 1 to check on every WiFi connect\n");
    return 1;
}

static int cmd_batt(int argc, char **argv) { print_batt(); return 0; }
static int cmd_ble(int argc, char **argv) { print_ble(); return 0; }

static int cmd_log(int argc, char **argv) {
    if (argc < 3) {
        printf("usage: log <tag|*> <none|error|warn|info|debug|verbose>\n"
               "tags: drive demo wifi ws ota ble batt console settings ...\n");
        return 1;
    }
    esp_err_t err = ulog_set_level(argv[1], argv[2]);
    if (err != ESP_OK) { printf("bad level '%s'\n", argv[2]); return 1; }
    printf("log %s -> %s\n", argv[1], argv[2]);
    return 0;
}

static int cmd_stats(int argc, char **argv) {
    if (argc >= 2 && !strcmp(argv[1], "reset")) { drive_reset_stats(); printf("stats reset\n"); return 0; }
    drive_status_t s;
    drive_get_status(&s);
    printf("control: worst tick %lu us of %d us over %lu ticks; bus writes %lu, echo faults %lu\n",
           (unsigned long)s.tick_worst_us, 1000000 / CONFIG_UBOT_CONTROL_HZ, (unsigned long)s.tick_count,
           (unsigned long)s.bus_writes, (unsigned long)s.bus_echo_faults);
    for (int i = 0; i < DRIVE_NWHEELS; i++) {
        printf("wheel %s: worst encoder read %lu us\n", wheel_name(i), (unsigned long)s.wheel[i].worst_read_us);
    }
    printf("log lines dropped (host not reading): %u\n", ulog_dropped());
    return 0;
}

static int cmd_free(int argc, char **argv) {
    printf("heap free %u, min ever %u, largest block %u\n",
           (unsigned)heap_caps_get_free_size(MALLOC_CAP_DEFAULT),
           (unsigned)heap_caps_get_minimum_free_size(MALLOC_CAP_DEFAULT),
           (unsigned)heap_caps_get_largest_free_block(MALLOC_CAP_DEFAULT));
    return 0;
}

static int cmd_reboot(int argc, char **argv) {
    drive_estop();
    printf("rebooting\n");
    vTaskDelay(pdMS_TO_TICKS(100));
    esp_restart();
    return 0;
}

// ------------------------------------------------------------------- setup

static void reg(const char *cmd, const char *help, const char *hint, esp_console_cmd_func_t fn) {
    const esp_console_cmd_t c = { .command = cmd, .help = help, .hint = hint, .func = fn };
    ESP_ERROR_CHECK(esp_console_cmd_register(&c));
}

esp_err_t console_start(void) {
    esp_console_repl_t *repl = NULL;
    esp_console_repl_config_t rc = ESP_CONSOLE_REPL_CONFIG_DEFAULT();
    rc.prompt = "ubot> ";
    rc.max_cmdline_length = 256;
    rc.task_stack_size = 6144;

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
    printf("\nU-BOT base %s -- 'help' for commands, 'status' for the picture\n", sysinfo_fw_version());
    return esp_console_start_repl(repl);
}
