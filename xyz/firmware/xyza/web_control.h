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
// Boards run A1 to Z34: 34 columns along +X and 26 rows along -Y at a nominal
// 2.54 mm pitch, 254 pulses at the provisional 100 pulses/mm.
constexpr long holePitch = 254, boardColumns = 34, boardRows = 26;
constexpr long maxHoleX = (boardColumns-1)*holePitch, maxHoleY = (boardRows-1)*holePitch;
constexpr long holeRate = 4000; // Hole-to-hole travel; clamped to the X/Y motor rate caps.
constexpr int64_t travelLift = 100; // Hole travel first raises the drill this far: 1 mm at 100 pulses/mm.
constexpr long maxHoleJog = 3; // Arrow steps in whole holes.
// Saving Z34 more than this far from its nominal place is treated as a
// mistake (wrong hole, or the drill never moved), not as calibration.
constexpr int64_t spanTolerancePercent = 10;

// Rounds a/b to the nearest integer, halves up, for b > 0. The page uses
// Math.round for the same grid, so both agree on every hole and offset.
int64_t roundDiv(int64_t a, int64_t b) {
  const int64_t n = 2*a + b, d = 2*b;
  return n/d - ((n%d != 0) && (n < 0));
}
// The XY offset of Z34 from A1, measured or nominal. A stored span with the
// wrong sign or a zero axis can only be corruption; the nominal grid is safer.
void span(int64_t &x, int64_t &y) {
  const auto &s = Positions::saved;
  const bool usable = s.spanSet && s.span[0] > 0 && s.span[1] < 0;
  x = usable ? s.span[0] : maxHoleX;
  y = usable ? s.span[1] : -maxHoleY;
}
// Raw offset from A1 of column col (1..34) and row (0 = A .. 25 = Z). The
// grid is interpolated per axis between A1 and Z34, and extrapolated for
// off-board indices, so a hole step near the edge stays consistent.
void holeOffset(long col, long row, int64_t &x, int64_t &y) {
  int64_t sx, sy; span(sx, sy);
  x = roundDiv(sx*(col-1), boardColumns-1);
  y = roundDiv(sy*row, boardRows-1);
}
// The nearest column (X) or row (Y) index to a raw offset from A1.
long nearestIndex(int axis, int64_t offset) {
  int64_t sx, sy; span(sx, sy);
  // Both spans are positive in their counting direction: columns run along
  // +X, rows along -Y.
  return axis == 0 ? long(roundDiv(offset*(boardColumns-1), sx)) + 1
                   : long(roundDiv(-offset*(boardRows-1), -sy));
}
// "D12": one row letter A-Z, then a column number 1-34.
bool parseHole(const char *s, long &col, long &row) {
  if (!s || !*s) return false;
  const char letter = *s >= 'a' && *s <= 'z' ? char(*s-'a'+'A') : *s;
  if (letter < 'A' || letter > 'Z' || s[1] < '0' || s[1] > '9' || !number(s+1, 1, boardColumns, col)) return false;
  row = letter-'A';
  return true;
}

void reply(int code, const char *message) { server.send(code, "text/plain", message); }
bool idle() { return activeMotor < 0 && !presetRunning; }
void runCommand(const char *text) {
  char buffer[96]; snprintf(buffer, sizeof(buffer), "%s", text); command(buffer);
}
void state() {
  int64_t p[4]; Positions::snapshot(p);
  char body[768];
  const auto &s = Positions::saved;
  snprintf(body, sizeof(body),
    "{\"armed\":%s,\"webArmed\":%s,\"busy\":%s,\"known\":%s,\"recoverable\":%s,"
    "\"homeSet\":%s,\"replaceSet\":%s,\"spanSet\":%s,\"commissioned\":%s,\"position\":[%lld,%lld,%lld],"
    "\"replace\":[%lld,%lld,%lld],\"span\":[%lld,%lld],\"disableReason\":\"%s\",\"uptime\":%lu}",
    armed ? "true":"false", (webArmed && ownsControl()) ? "true":"false", idle() ? "false":"true",
    Positions::known ? "true":"false", s.clean ? "true":"false",
    s.homeSet ? "true":"false", s.replaceSet ? "true":"false", s.spanSet ? "true":"false",
    Positions::commissioned() ? "true":"false",
    (long long)(p[0]-s.home[0]), (long long)(p[1]-s.home[1]), (long long)(p[3]-s.home[3]),
    (long long)(s.replace[0]-s.home[0]), (long long)(s.replace[1]-s.home[1]), (long long)(s.replace[3]-s.home[3]),
    (long long)s.span[0], (long long)s.span[1], disableReason,
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
  if (op == "hidden") { reply(200, "OK"); return; } // Kept for older pages; no longer stops anything.
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
  if (op == "span") {
    // The drill is above Z34. Its XY offset from A1 calibrates the hole grid.
    if (!Positions::known || !Positions::saved.homeSet) { reply(409, "Set A1 and confirm the position first."); return; }
    int64_t current[4]; Positions::snapshot(current);
    const int64_t x = current[0]-Positions::saved.home[0], y = current[1]-Positions::saved.home[1];
    const int64_t dx = x-maxHoleX, dy = y+maxHoleY;
    if ((dx < 0 ? -dx : dx) > maxHoleX*spanTolerancePercent/100 || (dy < 0 ? -dy : dy) > maxHoleY*spanTolerancePercent/100) {
      char text[192];
      snprintf(text, sizeof(text), "Not saved: Z34 should be about %ld mm left and %ld mm forward of A1, but the drill is %lld.%02lld mm left and %lld.%02lld mm forward. Check the hole.",
        long((maxHoleX+50)/100), long((maxHoleY+50)/100), (long long)(x/100), (long long)((x < 0 ? -x : x)%100), (long long)(-y/100), (long long)((y < 0 ? -y : y)%100));
      reply(409, text); return;
    }
    const bool ok = Positions::saveSpan(x, y);
    reply(ok ? 200:409, ok ? "Z34 saved. Hole positions now interpolate between A1 and Z34." : "Cannot save: position storage failed."); return;
  }
  if (!armed || !webArmed) { reply(409, "Turn on the motors in this page first."); return; }
  if (op == "jog") {
    const auto axis = server.arg("axis"), pulses = server.arg("pulses"), holes = server.arg("holes");
    int a = axisIndex(axis.c_str()); long steps = 0, count;
    if (a < 0 || a > 2) { reply(400, "Invalid XYZ jog or pulse count."); return; }
    if (holes.length()) {
      // Whole holes along X or Y, signed like raw pulses: +X is more columns
      // and -Y more rows. The distance runs from the nearest hole to the one
      // `count` further on, so an on-grid start lands on the grid and an
      // off-grid start keeps its offset. Unknown positions count from A1.
      if (a > 1 || !number(holes.c_str(), -maxHoleJog, maxHoleJog, count) || !count) { reply(400, "Invalid hole step."); return; }
      int64_t offset = 0;
      if (Positions::known && Positions::saved.homeSet) {
        int64_t current[4]; Positions::snapshot(current);
        offset = current[a]-Positions::saved.home[a];
      }
      const long index = nearestIndex(a, offset), next = a == 0 ? index+count : index-count;
      int64_t fromX, fromY, toX, toY;
      holeOffset(a == 0 ? index : 1, a == 1 ? index : 0, fromX, fromY);
      holeOffset(a == 0 ? next : 1, a == 1 ? next : 0, toX, toY);
      const int64_t delta = a == 0 ? toX-fromX : toY-fromY;
      if (!delta || delta > Config::maxJogSteps[axisMotor[a]] || delta < -Config::maxJogSteps[axisMotor[a]]) { reply(400, "Invalid hole step."); return; }
      steps = long(delta);
    } else if (!number(pulses.c_str(), -Config::maxJogSteps[axisMotor[a]], Config::maxJogSteps[axisMotor[a]], steps) || !steps) {
      reply(400, "Invalid XYZ jog or pulse count."); return;
    }
    char text[64]; snprintf(text, sizeof(text), "JOG %s %ld 1000", axis.c_str(), steps);
    runCommand(text);
    reply(activeMotor >= 0 ? 200:503, activeMotor >= 0 ? "Moving.":"Unable to start the move; check position storage."); return;
  }
  if (op == "goto") {
    // A hole name such as D12, placed on the grid interpolated between A1
    // and Z34. The drill first rises travelLift clear of the cut it may be
    // in, then crosses in one straight XY line and stays at that height.
    long col, row;
    if (!parseHole(server.arg("hole").c_str(), col, row)) {
      reply(400, "That hole is off the board. Holes run A1 to Z34."); return;
    }
    if (!Positions::known || !Positions::saved.homeSet) { reply(409, "Set A1 and confirm the position first."); return; }
    int64_t x, y; holeOffset(col, row, x, y);
    int64_t current[4]; Positions::snapshot(current);
    if (Positions::saved.home[0] + x == current[0] && Positions::saved.home[1] + y == current[1]) { reply(200, "Already at that hole."); return; }
    for (int i = 0; i < 4; ++i) target[i] = current[i];
    target[0] = Positions::saved.home[0] + x; target[1] = Positions::saved.home[1] + y;
    target[3] = current[3] + travelLift;
    clearance = target[3]; stage = 0; presetRunning = true;
    reply(200, "Raising the drill 1 mm, then moving to the hole."); return;
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
  // The machine has its own emergency stop; this page is not a dead-man's
  // handle. Every move is bounded and planned before it starts, so motion
  // always completes even if the link drops. Idle motors are released after
  // webIdleMs without a poll from the controlling page, so a closed laptop
  // cannot leave the drivers energised indefinitely.
  if (webArmed && idle() && uint32_t(millis()-webHeartbeat) > Config::webIdleMs) {
    disableMotors(); disableReason = "Control page away for 60 s";
  }
}
void service() {
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
