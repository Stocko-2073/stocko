#pragma once
#include <WebServer.h>
#include "web_page.h"

namespace WebControl {
// The stock server keeps a connected but silent client for HTTP_MAX_DATA_WAIT
// (5 s) and accepts nobody else meanwhile. Browsers open spare connections
// like that, and a 5 s freeze outlasts the 3 s motor lease: motors stop with
// "Browser connection timed out" although nothing failed. Drop silent clients
// early; a real request's first bytes follow the handshake within one RTT.
constexpr uint32_t silentClientMs = 400;
struct LeaseSafeServer : WebServer {
  using WebServer::WebServer;
  void service() {
    if (_currentStatus == HC_WAIT_READ && !_currentClient.available() && uint32_t(millis()-_statusChange) > silentClientMs) {
      _currentClient.stop();
      _currentStatus = HC_NONE;
    }
    handleClient();
  }
};
LeaseSafeServer server(80);
char owner[65] = {};
bool ownsControl() { return server.arg("client") == owner && owner[0]; }
int stage = 0;
int64_t target[4] = {}, clearance = 0;
constexpr int order[] = {3, -1, 3}; // Z to clearance, one straight XY line, Z to target.
// Boards run A1 to Z34: 34 columns along +X and 26 rows along -Y at a 2.54 mm
// pitch, 254 pulses at the provisional 100 pulses/mm.
constexpr long holePitch = 254, boardColumns = 34, boardRows = 26;
constexpr long maxHoleX = (boardColumns-1)*holePitch, maxHoleY = (boardRows-1)*holePitch;
constexpr long holeRate = 4000; // Hole-to-hole travel; clamped to the X/Y motor rate caps.

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
    "\"replace\":[%lld,%lld,%lld],\"disableReason\":\"%s\",\"uptime\":%lu}",
    armed ? "true":"false", (webArmed && ownsControl()) ? "true":"false", idle() ? "false":"true",
    Positions::known ? "true":"false", s.clean ? "true":"false",
    s.homeSet ? "true":"false", s.replaceSet ? "true":"false",
    Positions::commissioned() ? "true":"false",
    (long long)(p[0]-s.home[0]), (long long)(p[1]-s.home[1]), (long long)(p[3]-s.home[3]),
    (long long)(s.replace[0]-s.home[0]), (long long)(s.replace[1]-s.home[1]), (long long)(s.replace[3]-s.home[3]), disableReason,
    (unsigned long)(millis()/1000));
  server.sendHeader("Cache-Control", "no-store");
  server.send(200, "application/json", body);
}
void action() {
  // A custom header requires a CORS preflight for cross-origin browser calls.
  // No CORS permission is provided, so unrelated websites cannot jog the device.
  if (server.header("X-XYZ-Control") != "1") { reply(403, "Use the XYZ control page."); return; }
  const auto op = server.arg("op");
  if (op == "stop") { disableMotors(); reply(200, "Stopped. Motors off."); return; }
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
  if (webArmed && !ownsControl()) { reply(409, "Another page controls the motors; press STOP first."); return; }
  if (WifiProvisioning::prompt) { reply(409, "Finish USB Wi-Fi setup first."); return; }
  if (!Positions::commissioned()) { reply(409, "Restore the commissioned motor mapping and directions first."); return; }
  if (!idle()) { reply(409, "Still moving; stop or wait."); return; }
  if (op == "arm") {
    if (armed && !webArmed) { reply(409, "The USB console controls the motors; press STOP first."); return; }
    const auto client = server.arg("client");
    if (client.length() < 16 || client.length() >= sizeof(owner)) { reply(400, "Missing browser identifier."); return; }
    snprintf(owner, sizeof(owner), "%s", client.c_str());
    webHeartbeat = millis(); runCommand("ARM"); webArmed = armed;
    reply(armed ? 200:503, armed ? "Motors on.":"Motion timer unavailable."); return;
  }
  if (op == "home" || op == "replace" || op == "confirm" || op == "reference") {
    bool ok = (op == "home" || op == "replace") ? Positions::save(op == "home") : Positions::reference(op == "reference");
    reply(ok ? 200:409, ok ? "Position saved.":"Cannot save: set A1 first, or position storage failed."); return;
  }
  if (!armed || !webArmed) { reply(409, "Turn on the motors in this page first."); return; }
  if (op == "jog") {
    const auto axis = server.arg("axis"), pulses = server.arg("pulses");
    int a = axisIndex(axis.c_str()); long steps;
    if (a < 0 || a > 2 || !number(pulses.c_str(), -Config::maxJogSteps[axisMotor[a]], Config::maxJogSteps[axisMotor[a]], steps) || !steps) {
      reply(400, "Invalid XYZ jog or pulse count."); return;
    }
    char text[64]; snprintf(text, sizeof(text), "JOG %s %ld 1000", axis.c_str(), steps);
    runCommand(text);
    reply(activeMotor >= 0 ? 200:503, activeMotor >= 0 ? "Moving.":"Unable to start the move; check position storage."); return;
  }
  if (op == "goto") {
    // Hole offsets from A1 in raw pulses: columns run along +X, rows along -Y,
    // bounded to the board. Travel is one straight XY line at the current
    // drill height; the page tells the operator to raise the drill first.
    long x, y;
    if (!number(server.arg("x").c_str(), 0, maxHoleX, x) || !number(server.arg("y").c_str(), -maxHoleY, 0, y)) {
      reply(400, "That hole is off the board. Holes run A1 to Z34."); return;
    }
    if (!Positions::known || !Positions::saved.homeSet) { reply(409, "Set A1 and confirm the position first."); return; }
    int64_t current[4]; Positions::snapshot(current);
    const int64_t dx = Positions::saved.home[0] + x - current[0], dy = Positions::saved.home[1] + y - current[1];
    if (!dx && !dy) { reply(200, "Already at that hole."); return; }
    const bool started = startXYLine(dx, dy, holeRate);
    reply(started ? 200:503, started ? "Moving to the hole." : "Unable to start the move; check position storage."); return;
  }
  if (op == "go-home" || op == "go-replace") {
    if (!Positions::known || !Positions::saved.homeSet || (op == "go-replace" && !Positions::saved.replaceSet)) {
      reply(409, "Set A1 and confirm the position first."); return;
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
  server.service();
  checkConnection();
  if (!presetRunning || activeMotor >= 0) return;
  if (!armed || !Positions::known || !Positions::commissioned()) { disableMotors(); return; }
  int64_t current[4]; Positions::snapshot(current);
  while (stage < 3) {
    const int m = order[stage];
    if (m < 0) {
      // Both axes together at the hole-travel rate, like Go to hole.
      const int64_t dx = target[0]-current[0], dy = target[1]-current[1];
      if (!dx && !dy) { ++stage; continue; }
      if (!startXYLine(dx, dy, holeRate)) { disableMotors(); disableReason = "Unable to start saved move"; }
      return;
    }
    const int64_t destination = stage == 0 ? clearance : target[m];
    const int64_t delta = destination-current[m];
    if (!delta) { ++stage; continue; }
    // One profile covers the entire Z leg, independent of manual jog caps.
    if (!startPresetAxis(m, delta)) {
      disableMotors(); disableReason = "Unable to start saved move";
    }
    return;
  }
  presetRunning = false;
}
}
