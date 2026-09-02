// WebSocket drive server on port 80, path /ws, JSON both ways. Also serves a
// small joystick page at / so the protocol can be driven from a laptop before
// the phone app exists.
//
// Client -> robot (one object per frame):
//   {"t":"drive","v":0.5,"w":-0.2}          normalised, -1..1 of the limits
//   {"t":"drive","v_mps":0.3,"w_radps":0}   or in physical units
//       optional "hold": ms before the deadman stops the robot (default 500)
//   {"t":"stop"} {"t":"enable"} {"t":"disable"} {"t":"estop"} {"t":"clear"}
//   {"t":"status"}                          ask for a status frame now
//   {"t":"log","on":true}                   mirror the log to this client
//   {"t":"ota_check"}                        compare the bucket's version.txt; result in status.ota
//   {"t":"ota_update"}                       install the bucket's firmware.bin (disables drivers, reboots)
//
// Robot -> client:
//   {"t":"status", ...}                     on connect, on request, and at 5 Hz
//   {"t":"ack","cmd":"enable","ok":true}    for everything but "drive"
//   {"t":"ack","cmd":"drive","ok":false,"err":"..."}   only when a drive was refused
//   {"t":"log","m":"..."}                   when subscribed
#include <string.h>
#include <sys/socket.h>
#include <unistd.h>

#include "battery.h"
#include "cJSON.h"
#include "drive.h"
#include "esp_http_server.h"
#include "esp_log.h"
#include "esp_timer.h"
#include "net.h"
#include "net_internal.h"
#include "sdkconfig.h"
#include "sysinfo.h"
#include "ulog.h"

static const char *TAG = "ws";

extern const char joystick_html_start[] asm("_binary_joystick_html_start");

static httpd_handle_t s_httpd = NULL;
static esp_timer_handle_t s_timer;

#define MAX_CLIENTS 6
typedef struct { int fd; bool logs; } client_t;
static client_t s_clients[MAX_CLIENTS];
static portMUX_TYPE s_mux = portMUX_INITIALIZER_UNLOCKED;

static const uint32_t DEFAULT_HOLD_MS = 500;
static const uint32_t MAX_HOLD_MS = 5000;

// ------------------------------------------------------------------ clients

static client_t *client_find(int fd) {
    for (int i = 0; i < MAX_CLIENTS; i++) if (s_clients[i].fd == fd) return &s_clients[i];
    return NULL;
}

static void client_add(int fd) {
    portENTER_CRITICAL(&s_mux);
    if (!client_find(fd)) {
        for (int i = 0; i < MAX_CLIENTS; i++) {
            if (s_clients[i].fd < 0) { s_clients[i].fd = fd; s_clients[i].logs = false; break; }
        }
    }
    portEXIT_CRITICAL(&s_mux);
}

static bool any_logs(void) {
    for (int i = 0; i < MAX_CLIENTS; i++) if (s_clients[i].fd >= 0 && s_clients[i].logs) return true;
    return false;
}

static void client_remove(int fd) {
    portENTER_CRITICAL(&s_mux);
    client_t *c = client_find(fd);
    if (c) { c->fd = -1; c->logs = false; }
    portEXIT_CRITICAL(&s_mux);
    ulog_mirror(any_logs());
}

int ws_client_count(void) {
    if (!s_httpd) return 0;
    int n = 0;
    for (int i = 0; i < MAX_CLIENTS; i++) if (s_clients[i].fd >= 0) n++;
    return n;
}

bool ws_server_up(void) { return s_httpd != NULL; }

static void on_close(httpd_handle_t hd, int fd) {
    if (client_find(fd)) ESP_LOGI(TAG, "client fd %d gone", fd);
    client_remove(fd);
    close(fd);
}

// --------------------------------------------------------------------- json

static const char *magnet_text(uint8_t st) {
    if (!(st & 0x20)) return "none";
    if (st & 0x10) return "weak";
    if (st & 0x08) return "strong";
    return "ok";
}

static int status_json(char *buf, size_t n) {
    drive_status_t s;
    drive_get_status(&s);
    net_status_t ns;
    net_get_status(&ns);
    char ota_url[200];
    int len = snprintf(buf, n,
        "{\"t\":\"status\",\"fw\":\"%s\",\"hw\":\"%s\",\"name\":\"%s\",\"up\":%lu,"
        "\"enabled\":%s,\"faulted\":%s,\"fault\":%s%s%s,\"fault_wheel\":\"%s\","
        "\"cal\":%s,\"demo\":%s%s%s,"
        "\"cmd\":{\"v\":%.3f,\"w\":%.3f,\"active\":%s},"
        "\"limits\":{\"v\":%.3f,\"w\":%.3f},"
        "\"batt\":{\"present\":%s,\"v\":%.2f,\"pct\":%d},"
        "\"wifi\":{\"rssi\":%d},"
        "\"ota\":{\"busy\":%s,\"state\":\"%s\",\"available\":%s%s%s,\"configured\":%s},"
        "\"wheels\":[",
        sysinfo_fw_version(), sysinfo_hw_rev(), sysinfo_name(), (unsigned long)sysinfo_uptime_s(),
        s.enabled ? "true" : "false", s.faulted ? "true" : "false",
        s.faulted ? "\"" : "", s.faulted ? drive_fault_name(s.wheel[s.fault_wheel].fault) : "null", s.faulted ? "\"" : "",
        s.fault_wheel == 0 ? "A" : "B",
        s.cal_busy ? "true" : "false",
        s.demo_running ? "\"" : "", s.demo_running ? s.demo_caption : "null", s.demo_running ? "\"" : "",
        s.v_mps, s.w_radps, s.cmd_active ? "true" : "false",
        s.vmax_mps, s.wmax_radps,
        battery_present() ? "true" : "false", battery_voltage(), battery_percent(),
        ns.rssi,
        net_ota_busy() ? "true" : "false", net_ota_status(),
        net_ota_available()[0] ? "\"" : "", net_ota_available()[0] ? net_ota_available() : "null",
        net_ota_available()[0] ? "\"" : "",
        net_ota_get_url(ota_url, sizeof ota_url) ? "true" : "false");
    for (int i = 0; i < DRIVE_NWHEELS && len < (int)n; i++) {
        const drive_wheel_status_t *w = &s.wheel[i];
        len += snprintf(buf + len, n - len,
            "%s{\"name\":\"%s\",\"driver\":%s,\"pos\":%.4f,\"vel\":%.3f,\"slip\":%ld,"
            "\"enc\":%s,\"agc\":%u,\"magnet\":\"%s\",\"fault\":%u,\"gain\":%.4f,\"loop\":%s}",
            i ? "," : "", i == 0 ? "A" : "B", w->driver_ok ? "true" : "false",
            w->pos_turns, w->vel_tps, (long)w->slip_steps,
            w->encoder_ok ? "true" : "false", w->agc, magnet_text(w->magnet_status),
            w->fault, w->clock_gain, w->loop_closed ? "true" : "false");
    }
    if (len < (int)n) len += snprintf(buf + len, n - len, "]}");
    return len;
}

// Escape a log line into a JSON string body (no surrounding quotes).
static size_t json_escape(const char *in, char *out, size_t n) {
    size_t o = 0;
    for (const unsigned char *p = (const unsigned char *)in; *p && o + 6 < n; p++) {
        switch (*p) {
            case '"': out[o++] = '\\'; out[o++] = '"'; break;
            case '\\': out[o++] = '\\'; out[o++] = '\\'; break;
            case '\n': out[o++] = '\\'; out[o++] = 'n'; break;
            case '\r': break;
            case '\t': out[o++] = '\\'; out[o++] = 't'; break;
            default:
                if (*p < 0x20) o += snprintf(out + o, n - o, "\\u%04x", *p);
                else out[o++] = (char)*p;
        }
    }
    out[o] = 0;
    return o;
}

// ------------------------------------------------------------------- sending

static esp_err_t send_text(httpd_req_t *req, const char *text) {
    httpd_ws_frame_t f;
    memset(&f, 0, sizeof f);
    f.type = HTTPD_WS_TYPE_TEXT;
    f.payload = (uint8_t *)text;
    f.len = strlen(text);
    return httpd_ws_send_frame(req, &f);
}

static void send_text_async(int fd, const char *text) {
    httpd_ws_frame_t f;
    memset(&f, 0, sizeof f);
    f.type = HTTPD_WS_TYPE_TEXT;
    f.payload = (uint8_t *)text;
    f.len = strlen(text);
    httpd_ws_send_frame_async(s_httpd, fd, &f);
}

static void ack(httpd_req_t *req, const char *cmd, esp_err_t err) {
    char buf[200];
    if (err == ESP_OK) snprintf(buf, sizeof buf, "{\"t\":\"ack\",\"cmd\":\"%s\",\"ok\":true}", cmd);
    else {
        char esc[120];
        json_escape(err == ESP_ERR_INVALID_STATE ? drive_refusal() : esp_err_to_name(err), esc, sizeof esc);
        snprintf(buf, sizeof buf, "{\"t\":\"ack\",\"cmd\":\"%s\",\"ok\":false,\"err\":\"%s\"}", cmd, esc);
    }
    send_text(req, buf);
}

// Runs on the httpd task at 5 Hz: a status frame to every client, and the
// mirrored log to those that asked for it.
static void broadcast_work(void *arg) {
    static char status[900];
    status_json(status, sizeof status);
    int fds[MAX_CLIENTS];
    int n = 0;
    portENTER_CRITICAL(&s_mux);
    for (int i = 0; i < MAX_CLIENTS; i++) if (s_clients[i].fd >= 0) fds[n++] = s_clients[i].fd;
    portEXIT_CRITICAL(&s_mux);
    for (int i = 0; i < n; i++) {
        if (httpd_ws_get_fd_info(s_httpd, fds[i]) != HTTPD_WS_CLIENT_WEBSOCKET) continue;
        send_text_async(fds[i], status);
    }
    if (!ulog_mirrored()) return;
    char line[256], esc[300], frame[340];
    for (int k = 0; k < 20 && ulog_pop(line, sizeof line); k++) {
        json_escape(line, esc, sizeof esc);
        snprintf(frame, sizeof frame, "{\"t\":\"log\",\"m\":\"%s\"}", esc);
        for (int i = 0; i < n; i++) {
            client_t *c = client_find(fds[i]);
            if (!c || !c->logs) continue;
            if (httpd_ws_get_fd_info(s_httpd, fds[i]) != HTTPD_WS_CLIENT_WEBSOCKET) continue;
            send_text_async(fds[i], frame);
        }
    }
}

static void timer_cb(void *arg) {
    if (s_httpd && ws_client_count() > 0) httpd_queue_work(s_httpd, broadcast_work, NULL);
}

// ------------------------------------------------------------------ handlers

static void handle_message(httpd_req_t *req, const char *text) {
    cJSON *root = cJSON_Parse(text);
    if (!root) { send_text(req, "{\"t\":\"ack\",\"ok\":false,\"err\":\"not json\"}"); return; }
    const char *t = cJSON_GetStringValue(cJSON_GetObjectItem(root, "t"));
    if (!t) { send_text(req, "{\"t\":\"ack\",\"ok\":false,\"err\":\"missing t\"}"); cJSON_Delete(root); return; }

    if (!strcmp(t, "drive")) {
        cJSON *hold = cJSON_GetObjectItem(root, "hold");
        uint32_t hold_ms = DEFAULT_HOLD_MS;
        if (cJSON_IsNumber(hold)) {
            double h = hold->valuedouble;
            hold_ms = h < 100 ? 100 : h > MAX_HOLD_MS ? MAX_HOLD_MS : (uint32_t)h;
        }
        cJSON *v = cJSON_GetObjectItem(root, "v"), *w = cJSON_GetObjectItem(root, "w");
        cJSON *vm = cJSON_GetObjectItem(root, "v_mps"), *wm = cJSON_GetObjectItem(root, "w_radps");
        esp_err_t err;
        if (cJSON_IsNumber(vm) || cJSON_IsNumber(wm)) {
            err = drive_set_velocity(cJSON_IsNumber(vm) ? (float)vm->valuedouble : 0,
                                     cJSON_IsNumber(wm) ? (float)wm->valuedouble : 0, hold_ms);
        } else {
            err = drive_set_normalized(cJSON_IsNumber(v) ? (float)v->valuedouble : 0,
                                       cJSON_IsNumber(w) ? (float)w->valuedouble : 0, hold_ms);
        }
        if (err != ESP_OK) ack(req, "drive", err);   // silence on success keeps the joystick chatter one-way
    } else if (!strcmp(t, "stop")) { drive_stop(); ack(req, t, ESP_OK); }
    else if (!strcmp(t, "enable")) ack(req, t, drive_enable(true));
    else if (!strcmp(t, "disable")) ack(req, t, drive_enable(false));
    else if (!strcmp(t, "estop")) { drive_estop(); ack(req, t, ESP_OK); }
    else if (!strcmp(t, "clear")) ack(req, t, drive_clear_faults());
    else if (!strcmp(t, "ota_check")) ack(req, t, net_ota_check(false));   // compare only; status.ota says
    else if (!strcmp(t, "ota_update")) ack(req, t, net_ota_start(NULL));   // install <bucket>/firmware.bin
    else if (!strcmp(t, "status")) {
        static char buf[900];
        status_json(buf, sizeof buf);
        send_text(req, buf);
    } else if (!strcmp(t, "log")) {
        cJSON *on = cJSON_GetObjectItem(root, "on");
        client_t *c = client_find(httpd_req_to_sockfd(req));
        if (c) c->logs = cJSON_IsTrue(on);
        ulog_mirror(any_logs());
        ack(req, t, ESP_OK);
    } else {
        ack(req, t, ESP_ERR_NOT_SUPPORTED);
    }
    cJSON_Delete(root);
}

// Called once per client, right after the server has answered the handshake.
// ESP-IDF v6 deliberately does not invoke the URI handler for the handshake
// GET (older examples checked req->method == HTTP_GET for this); the
// post-handshake callback is the place to register the client and say hello.
static esp_err_t ws_open(httpd_req_t *req) {
    int fd = httpd_req_to_sockfd(req);
    client_add(fd);
    ESP_LOGI(TAG, "client fd %d connected (%d total)", fd, ws_client_count());
    static char buf[900];
    status_json(buf, sizeof buf);
    return send_text(req, buf);
}

// Called for every data frame after that.
static esp_err_t ws_handler(httpd_req_t *req) {
    if (req->method == HTTP_GET) return ESP_OK;   // not reached on v6.1; harmless if it ever is
    httpd_ws_frame_t f;
    memset(&f, 0, sizeof f);
    f.type = HTTPD_WS_TYPE_TEXT;
    esp_err_t err = httpd_ws_recv_frame(req, &f, 0);
    if (err != ESP_OK) return err;
    if (f.len == 0) return ESP_OK;
    if (f.len > 512) {
        ESP_LOGW(TAG, "frame of %d bytes dropped", (int)f.len);
        return ESP_FAIL;
    }
    uint8_t *buf = calloc(1, f.len + 1);
    if (!buf) return ESP_ERR_NO_MEM;
    f.payload = buf;
    err = httpd_ws_recv_frame(req, &f, f.len);
    if (err == ESP_OK && f.type == HTTPD_WS_TYPE_TEXT) handle_message(req, (const char *)buf);
    free(buf);
    return err;
}

static esp_err_t root_handler(httpd_req_t *req) {
#if CONFIG_UBOT_WEB_JOYSTICK
    httpd_resp_set_type(req, "text/html; charset=utf-8");
    return httpd_resp_send(req, joystick_html_start, HTTPD_RESP_USE_STRLEN);
#else
    httpd_resp_set_type(req, "text/plain");
    return httpd_resp_send(req, "U-BOT base: WebSocket at /ws", HTTPD_RESP_USE_STRLEN);
#endif
}

esp_err_t ws_server_start(void) {
    if (s_httpd) return ESP_OK;
    for (int i = 0; i < MAX_CLIENTS; i++) { s_clients[i].fd = -1; s_clients[i].logs = false; }

    httpd_config_t cfg = HTTPD_DEFAULT_CONFIG();
    cfg.server_port = 80;
    cfg.max_open_sockets = MAX_CLIENTS;
    cfg.lru_purge_enable = true;
    cfg.close_fn = on_close;
    cfg.stack_size = 6144;
    esp_err_t err = httpd_start(&s_httpd, &cfg);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "httpd_start: %s", esp_err_to_name(err));
        s_httpd = NULL;
        return err;
    }
    const httpd_uri_t ws = {
        .uri = "/ws", .method = HTTP_GET, .handler = ws_handler, .user_ctx = NULL,
        .is_websocket = true, .handle_ws_control_frames = false, .supported_subprotocol = NULL,
        .ws_post_handshake_cb = ws_open,   // needs CONFIG_HTTPD_WS_POST_HANDSHAKE_CB_SUPPORT
    };
    const httpd_uri_t root = { .uri = "/", .method = HTTP_GET, .handler = root_handler };
    httpd_register_uri_handler(s_httpd, &ws);
    httpd_register_uri_handler(s_httpd, &root);

    const esp_timer_create_args_t targs = { .callback = timer_cb, .name = "ws_status" };
    if (!s_timer) esp_timer_create(&targs, &s_timer);
    esp_timer_start_periodic(s_timer, 200000);
    ESP_LOGI(TAG, "serving http://%s.local/ and ws://%s.local/ws", sysinfo_name(), sysinfo_name());
    return ESP_OK;
}
