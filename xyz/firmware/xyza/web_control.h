#pragma once
#include <WebServer.h>
#include "web_page.h"

namespace WebControl {
WebServer server(80);
char owner[65] = {};
bool ownsControl() { return server.arg("client") == owner && owner[0]; }
int stage = 0;
int64_t target[4] = {}, clearance = 0;
constexpr int order[] = {3, 0, 1, 3};

void reply(int code, const char *message) { server.send(code, "text/plain", message); }
bool idle() { return activeMotor < 0 && !presetRunning; }
void runCommand(const char *text) {
  char buffer[96]; snprintf(buffer, sizeof(buffer), "%s", text); command(buffer);
}
void state() {
  int64_t p[4]; Positions::snapshot(p);
  char body[640];
  const auto &s = Positions::saved;
  snprintf(body, sizeof(body),
    "{\"armed\":%s,\"webArmed\":%s,\"busy\":%s,\"known\":%s,\"recoverable\":%s,"
    "\"homeSet\":%s,\"replaceSet\":%s,\"commissioned\":%s,\"position\":[%lld,%lld,%lld],"
    "\"replace\":[%lld,%lld,%lld],\"disableReason\":\"%s\"}",
    armed ? "true":"false", (webArmed && ownsControl()) ? "true":"false", idle() ? "false":"true",
    Positions::known ? "true":"false", s.clean ? "true":"false",
    s.homeSet ? "true":"false", s.replaceSet ? "true":"false",
    Positions::commissioned() ? "true":"false",
    (long long)(p[0]-s.home[0]), (long long)(p[1]-s.home[1]), (long long)(p[3]-s.home[3]),
    (long long)(s.replace[0]-s.home[0]), (long long)(s.replace[1]-s.home[1]), (long long)(s.replace[3]-s.home[3]), disableReason);
  server.sendHeader("Cache-Control", "no-store");
  server.send(200, "application/json", body);
}
void action() {
  // A custom header requires a CORS preflight for cross-origin browser calls.
  // No CORS permission is provided, so unrelated websites cannot jog the device.
  if (server.header("X-XYZ-Control") != "1") { reply(403, "Use the XYZ control page."); return; }
  const auto op = server.arg("op");
  if (op == "stop") { disableMotors(); reply(200, "Stopped; motors disabled."); return; }
  if (op == "hidden") {
    if (webArmed && ownsControl()) { disableMotors(); disableReason = "Control page hidden"; }
    reply(200, "OK"); return;
  }
  if (op == "poll") {
    if (webArmed && ownsControl()) webHeartbeat = millis();
    state(); return;
  }
  if (op == "heartbeat") {
    if (!webArmed || !ownsControl()) { reply(409, "This page does not own motor control."); return; }
    webHeartbeat = millis(); reply(200, "OK"); return;
  }
  if (webArmed && !ownsControl()) { reply(409, "Another page controls the motors; stop first."); return; }
  if (WifiProvisioning::prompt) { reply(409, "Finish USB Wi-Fi setup first."); return; }
  if (!Positions::commissioned()) { reply(409, "Restore the commissioned motor mapping and directions first."); return; }
  if (!idle()) { reply(409, "Motion in progress; stop or wait."); return; }
  if (op == "arm") {
    if (armed && !webArmed) { reply(409, "Motors are controlled by USB; stop first."); return; }
    const auto client = server.arg("client");
    if (client.length() < 16 || client.length() >= sizeof(owner)) { reply(400, "Missing browser identifier."); return; }
    snprintf(owner, sizeof(owner), "%s", client.c_str());
    webHeartbeat = millis(); runCommand("ARM"); webArmed = armed;
    reply(armed ? 200:503, armed ? "Motors enabled.":"Motion timer unavailable."); return;
  }
  if (op == "home" || op == "replace" || op == "confirm" || op == "reference") {
    bool ok = (op == "home" || op == "replace") ? Positions::save(op == "home") : Positions::reference(op == "reference");
    reply(ok ? 200:409, ok ? "Position saved and referenced.":"Cannot save: check home/reference or position storage."); return;
  }
  if (!armed || !webArmed) { reply(409, "Enable motors in this page first."); return; }
  if (op == "jog") {
    const auto axis = server.arg("axis"), pulses = server.arg("pulses");
    int a = axisIndex(axis.c_str()); long steps;
    if (a < 0 || a > 2 || !number(pulses.c_str(), -Config::maxJogSteps[axisMotor[a]], Config::maxJogSteps[axisMotor[a]], steps) || !steps) {
      reply(400, "Invalid XYZ jog or pulse count."); return;
    }
    char text[64]; snprintf(text, sizeof(text), "JOG %s %ld 1000", axis.c_str(), steps);
    runCommand(text);
    reply(activeMotor >= 0 ? 200:503, activeMotor >= 0 ? "Jogging.":"Unable to start jog; check position storage."); return;
  }
  if (op == "go-home" || op == "go-replace") {
    if (!Positions::known || !Positions::saved.homeSet || (op == "go-replace" && !Positions::saved.replaceSet)) {
      reply(409, "Reference the machine and save the position first."); return;
    }
    const int64_t *p = op == "go-home" ? Positions::saved.home : Positions::saved.replace;
    for (int i = 0; i < 4; ++i) target[i] = p[i];
    int64_t current[4]; Positions::snapshot(current);
    clearance = current[3] > target[3] ? current[3] : target[3];
    stage = 0; presetRunning = true;
    reply(200, "Moving to saved position."); return;
  }
  reply(400, "Unknown action.");
}
void begin() {
  const char *headers[] = {"X-XYZ-Control"}; server.collectHeaders(headers, 1);
  server.on("/", HTTP_GET, []() { server.send_P(200, "text/html", webPage); });
  server.on("/api/state", HTTP_GET, state);
  server.on("/api/action", HTTP_POST, action);
  server.onNotFound([]() { reply(404, "Not found"); });
  server.begin();
}
void checkConnection() {
  if (webExpired || (webArmed && uint32_t(millis()-webHeartbeat) > Config::webLeaseMs)) {
    disableMotors(); disableReason = "Browser connection timed out";
  } else if (webArmed && WiFi.status() != WL_CONNECTED) {
    disableMotors(); disableReason = "Wi-Fi disconnected";
  }
}
void service() {
  // Check the lease both before and after HTTP processing. Timer stepping never
  // waits for the network, and each jog remains bounded by existing pulse caps.
  checkConnection();
  server.handleClient();
  checkConnection();
  if (!presetRunning || activeMotor >= 0) return;
  if (!armed || !Positions::known || !Positions::commissioned()) { disableMotors(); return; }
  int64_t current[4]; Positions::snapshot(current);
  while (stage < 4) {
    const int m = order[stage];
    const int64_t destination = stage == 0 ? clearance : target[m];
    const int64_t delta = destination-current[m];
    if (!delta) { ++stage; continue; }
    // One profile covers the entire axis leg, independent of manual jog caps.
    if (!startPresetAxis(m, delta)) {
      disableMotors(); disableReason = "Unable to start saved move";
    }
    return;
  }
  presetRunning = false;
}
}
