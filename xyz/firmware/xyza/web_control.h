#pragma once
#include <WebServer.h>
#include "web_page.h"
#include "bed_mesh.h"

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
long travelRate = 4000;
constexpr int order[] = {3, -1, 3}; // Z to clearance, one straight XY line, Z to target.
// Boards run A1 to Z34: 34 columns along +X and 26 rows along -Y at a nominal
// 2.54 mm pitch, 254 pulses at the provisional 100 pulses/mm.
constexpr long holePitch = 254, boardColumns = 34, boardRows = 26;
constexpr long maxHoleX = (boardColumns-1)*holePitch, maxHoleY = (boardRows-1)*holePitch;
constexpr long holeRate = 4000; // Hole-to-hole travel; clamped to the X/Y motor rate caps.
constexpr int64_t travelLift = 100; // Hole travel first raises the drill this far: 1 mm at 100 pulses/mm.
constexpr long maxHoleJog = 3; // Arrow steps in whole holes.
constexpr size_t maxBatchHoles=884, maxBatchText=8192;
struct BatchHole { uint8_t col, row; };
BatchHole batchHoles[maxBatchHoles];
size_t batchCount=0, batchIndex=0; // Index is the number of completed cuts.
bool batchCutting=false, batchReturning=false, batchReturned=false;
CutSettings::Record batchSettings;
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
// Raw XY offset from A1: mesh first, otherwise the legacy two-corner grid.
void holeOffset(long col, long row, int64_t &x, int64_t &y) {
  if (Positions::saved.meshSet) {
    double p[3]; BedMesh::sample(Positions::saved.mesh, col, row, p);
    x=BedMesh::rounded(p[0]); y=BedMesh::rounded(p[1]); return;
  }
  int64_t sx, sy; span(sx, sy);
  x = roundDiv(sx*(col-1), boardColumns-1);
  y = roundDiv(sy*row, boardRows-1);
}
int64_t bedHeight(int64_t x, int64_t y) {
  if (!Positions::saved.meshSet) return 0;
  double col,row,p[3];
  if (!BedMesh::locate(Positions::saved.mesh,x,y,col,row)) return 0;
  // Exact hole destinations are rounded in XY. Snap their inverse back to
  // the logical hole so XYZ all use the same interpolation coordinates.
  const long c=long(BedMesh::rounded(col)),r=long(BedMesh::rounded(row));
  int64_t hx,hy; holeOffset(c,r,hx,hy);
  if (hx==x && hy==y) { col=c; row=r; }
  // Outside the board, hold the nearest edge height; never extrapolate Z.
  col=std::fmax(1,std::fmin(34,col)); row=std::fmax(0,std::fmin(25,row));
  BedMesh::sample(Positions::saved.mesh,col,row,p);
  // Quantize the surface before taking differences: closed tours then keep
  // exactly the same depth instead of accumulating fractional-step drift.
  return BedMesh::rounded(p[2]);
}
void planHole(const int64_t current[4], int64_t x, int64_t y, bool calibration=false, long rate=holeRate) {
  const auto &s=Positions::saved;
  for (int i=0;i<4;++i) target[i]=current[i];
  target[0]=s.home[0]+x; target[1]=s.home[1]+y;
  clearance=current[3]+travelLift;
  if (s.meshSet) {
    const int64_t offset=current[3]-s.home[3]-bedHeight(current[0]-s.home[0],current[1]-s.home[1]);
    target[3]=s.home[3]+bedHeight(x,y)+offset;
    // All bilinear heights lie within their corner heights. The global
    // maximum clears even an interior hump along the straight XY crossing.
    int64_t highest=0;
    for (const auto &p:s.mesh) if (p[2]>highest) highest=p[2];
    const int64_t safe=s.home[3]+highest+offset+travelLift;
    if (safe>clearance) clearance=safe;
  }
  if (calibration) {
    for (int i=0;i<9;++i) if (s.draftMask & (1<<i)) {
      const int64_t safe=s.home[3]+s.draft[i][2]+travelLift;
      if (safe>clearance) clearance=safe;
    }
    target[3]=clearance; // Approach an unmeasured point from above.
  }
  travelRate=rate; stage=0; presetRunning=true;
}
void planSaved(const int64_t *p, bool lift=false) {
  for (int i = 0; i < 4; ++i) target[i] = p[i];
  int64_t current[4]; Positions::snapshot(current);
  clearance = current[3] > target[3] ? current[3] : target[3];
  if (Positions::saved.meshSet) {
    for (const auto &point:Positions::saved.mesh) {
      const int64_t safe=Positions::saved.home[3]+point[2]+travelLift;
      if (safe>clearance) clearance=safe;
    }
  }
  travelRate=holeRate; stage = 0; presetRunning = true;
  // After a cut, lift before crossing even without a mesh.
  if (lift && current[3]+travelLift>clearance) clearance=current[3]+travelLift;
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

bool listSpace(char c) { return c==' ' || c=='\t' || c=='\r' || c=='\n'; }
// Parse every entry before publishing the job. Empty entries, embedded NULs,
// and out-of-board coordinates reject the whole request, never a partial job.
bool parseBatch(const char *text, size_t length, BatchHole *parsed, size_t &count, char *error, size_t errorSize) {
  count=0;
  if (!length || length>maxBatchText || memchr(text,0,length)) {
    snprintf(error,errorSize,"Enter a comma-separated list, at most 8192 characters."); return false;
  }
  size_t begin=0;
  while (begin<=length) {
    size_t end=begin;
    while (end<length && text[end]!=',') ++end;
    size_t first=begin,last=end;
    while (first<last && listSpace(text[first])) ++first;
    while (last>first && listSpace(text[last-1])) --last;
    char token[4]={}; long col,row;
    if (last-first<2 || last-first>3) {
      snprintf(error,errorSize,"Invalid coordinate %u; use A1–Z34.",unsigned(count+1)); return false;
    }
    memcpy(token,text+first,last-first);
    if (!parseHole(token,col,row)) {
      snprintf(error,errorSize,"Invalid coordinate %u: %s. Use A1–Z34.",unsigned(count+1),token); return false;
    }
    if (count==maxBatchHoles) { snprintf(error,errorSize,"Use at most 884 coordinates."); return false; }
    parsed[count++]={uint8_t(col),uint8_t(row)};
    if (end==length) return true;
    begin=end+1;
  }
  return false;
}
void planBatchHole() {
  const auto h=batchHoles[batchIndex];
  int64_t current[4],x,y; Positions::snapshot(current);
  holeOffset(h.col,h.row,x,y);
  planHole(current,x,y);
  batchCutting=false;
}

void reply(int code, const char *message) { server.send(code, "text/plain", message); }
bool idle() { return activeMotor < 0 && !presetRunning && !batchRunning; }
void runCommand(const char *text) {
  char buffer[96]; snprintf(buffer, sizeof(buffer), "%s", text); command(buffer, true);
}
void state() {
  int64_t p[4]; Positions::snapshot(p);
  char body[3072];
  const auto &s = Positions::saved;
  snprintf(body, sizeof(body),
    "{\"cutPhase\":%d,\"armed\":%s,\"webArmed\":%s,\"busy\":%s,\"known\":%s,\"recoverable\":%s,"
    "\"homeSet\":%s,\"replaceSet\":%s,\"spanSet\":%s,\"commissioned\":%s,\"position\":[%lld,%lld,%lld],"
    "\"replace\":[%lld,%lld,%lld],\"span\":[%lld,%lld],\"disableReason\":\"%s\",\"uptime\":%lu,",
    cutPhase, armed ? "true":"false", (webArmed && ownsControl()) ? "true":"false", idle() ? "false":"true",
    Positions::known ? "true":"false", s.clean ? "true":"false",
    s.homeSet ? "true":"false", s.replaceSet ? "true":"false", s.spanSet ? "true":"false",
    Positions::commissioned() ? "true":"false",
    (long long)(p[0]-s.home[0]), (long long)(p[1]-s.home[1]), (long long)(p[3]-s.home[3]),
    (long long)(s.replace[0]-s.home[0]), (long long)(s.replace[1]-s.home[1]), (long long)(s.replace[3]-s.home[3]),
    (long long)s.span[0], (long long)s.span[1], disableReason,
    (unsigned long)(millis()/1000));
  size_t used=strlen(body);
  char batchHole[5]={};
  if (batchIndex<batchCount) snprintf(batchHole,sizeof(batchHole),"%c%u",'A'+batchHoles[batchIndex].row,unsigned(batchHoles[batchIndex].col));
  used+=snprintf(body+used,sizeof(body)-used,"\"batch\":{\"active\":%s,\"completed\":%u,\"total\":%u,\"hole\":\"%s\",\"returning\":%s,\"returned\":%s},",
    batchRunning?"true":"false",unsigned(batchIndex),unsigned(batchCount),batchHole,
    batchRunning&&batchReturning?"true":"false",batchReturned?"true":"false");
  const auto &c=CutSettings::saved;
  used+=snprintf(body+used,sizeof(body)-used,"\"cutSettings\":{\"depth\":%u.%u,\"rpm\":%u,\"feed\":%u.%u,\"accel\":%u},",
    unsigned(c.depth/100),unsigned(c.depth%100/10),unsigned(c.rpm),unsigned(c.feed/100),unsigned(c.feed%100/10),unsigned(c.accel));
  used+=snprintf(body+used,sizeof(body)-used,"\"meshSet\":%s,\"calibrating\":%s,\"draftMask\":%u,\"mesh\":[",
    s.meshSet?"true":"false",s.calibrating?"true":"false",unsigned(s.draftMask));
  for (int i=0;i<9;++i) used+=snprintf(body+used,sizeof(body)-used,"%s[%lld,%lld,%lld]",i?",":"",
    (long long)s.mesh[i][0],(long long)s.mesh[i][1],(long long)s.mesh[i][2]);
  snprintf(body+used,sizeof(body)-used,"]}");
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
  if (op == "mesh-start") {
    // The operator has aligned XYZ with the A1 surface. Re-anchor once;
    // the previous mesh stays usable until the complete draft is applied.
    auto next=Positions::saved;
    if (!Positions::known) next.replaceSet=false;
    Positions::snapshot(next.home); Positions::snapshot(next.checkpoint);
    next.homeSet=true; next.clean=true; next.calibrating=true; next.draftMask=1;
    for (auto &p:next.draft) for (auto &v:p) v=0;
    const bool ok=Positions::write(next);
    if (ok) Positions::known=true;
    reply(ok?200:503,ok?"A1 saved. Measure the remaining eight points.":"Calibration not saved."); return;
  }
  if (op == "mesh-cancel" || op == "mesh-clear" || op == "mesh-apply") {
    auto next=Positions::saved;
    if (op == "mesh-apply") {
      if (!Positions::known || !next.calibrating || next.draftMask!=BedMesh::complete || !BedMesh::valid(next.draft)) {
        reply(409,"Measure all nine points with a valid position first."); return;
      }
      memcpy(next.mesh,next.draft,sizeof(next.mesh)); next.meshSet=true;
    }
    if (op == "mesh-clear") next.meshSet=false;
    next.calibrating=false; next.draftMask=0;
    const bool ok=Positions::write(next);
    reply(ok?200:503,ok?"Calibration updated.":"Calibration not saved."); return;
  }
  if (op == "mesh-save" || op == "mesh-go") {
    long point;
    if (!number(server.arg("point").c_str(),0,8,point)) { reply(400,"Invalid calibration point."); return; }
    const auto &s=Positions::saved;
    if (!Positions::known || !s.homeSet || !s.calibrating) { reply(409,"Start calibration at A1 first."); return; }
    const long col=BedMesh::columns[point%3],row=BedMesh::rows[point/3];
    int64_t current[4]; Positions::snapshot(current);
    if (op == "mesh-go") {
      if (!armed || !webArmed) { reply(409,"Turn on the motors in this page first."); return; }
      int64_t x,y; holeOffset(col,row,x,y); planHole(current,x,y,true);
      reply(200,"Moving above calibration point; jog down to the surface."); return;
    }
    if (!point) { reply(409,"To change A1, restart calibration there."); return; }
    auto next=s;
    const int motors[]={0,1,3};
    for (int a=0;a<3;++a) next.draft[point][a]=current[motors[a]]-s.home[motors[a]];
    // Broad bounds catch a wrong region or height, not a neighbouring hole.
    if (std::abs(next.draft[point][0]-(col-1)*holePitch)>maxHoleX/10 ||
        std::abs(next.draft[point][1]+row*holePitch)>maxHoleY/10 || std::abs(next.draft[point][2])>1000) {
      reply(409,"Point too far from expected XY or over 10 mm from A1 height."); return;
    }
    next.draftMask|=uint16_t(1<<point);
    const bool ok=Positions::write(next);
    reply(ok?200:503,ok?"Point saved.":"Point not saved."); return;
  }
  if (op == "span") {
    if (Positions::saved.meshSet || Positions::saved.calibrating) { reply(409,"Clear the mesh before changing Z34 pitch."); return; }
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
  if (op == "cut" || op == "cut-all" || op == "cut-settings") {
    if ((op!="cut-settings" && (!armed || !webArmed)) || (armed && !webArmed)) {
      reply(409, "Turn on the motors in this page first."); return;
    }
    if (op!="cut-settings" && (!Positions::known || !Positions::saved.homeSet || Positions::saved.calibrating)) {
      reply(409, "Confirm position and finish calibration before cutting."); return;
    }
    const auto depthText=server.arg("depth");
    char *end=nullptr; errno=0;
    const double depth=strtod(depthText.c_str(), &end);
    long rpm;
    if (errno || end==depthText.c_str() || *end || !std::isfinite(depth) ||
        depth<0.1 || depth>10 || std::abs(depth*10-std::round(depth*10))>0.000001 ||
        !number(server.arg("rpm").c_str(),1,240,rpm)) {
      reply(400, "Use depth 0.1–10 mm in 0.1 mm steps and speed 1–240 RPM."); return;
    }
    const long pulses=long(std::lround(depth*100)), rate=(rpm*800+30)/60;
    const auto feedText=server.arg("feed"); errno=0;
    const double feed=strtod(feedText.c_str(), &end);
    if (errno || end==feedText.c_str() || *end || !std::isfinite(feed) ||
        feed<0.1 || feed>double(Config::maxRate[3])/100 ||
        std::abs(feed*10-std::round(feed*10))>0.000001) {
      reply(400, "Use plunge/retract speed 0.1–20 mm/s in 0.1 mm/s steps."); return;
    }
    long accel;
    if (!number(server.arg("accel").c_str(),Config::cutMinAccelRpm,Config::cutMaxAccelRpm,accel)) {
      reply(400, "Use drill acceleration 15–750 RPM/s, in whole numbers."); return;
    }
    const CutSettings::Record settings{2,uint32_t(pulses),uint32_t(rpm),uint32_t(std::lround(feed*100)),uint32_t(accel)};
    size_t count=0; BatchHole parsed[maxBatchHoles];
    if (op=="cut-all") {
      const auto holes=server.arg("holes"); char error[128];
      if (!parseBatch(holes.c_str(),holes.length(),parsed,count,error,sizeof(error))) { reply(400,error); return; }
    }
    if (!CutSettings::save(settings)) {
      reply(503, "Cut settings could not be saved. No cut started."); return;
    }
    if (op=="cut-settings") { reply(200, "Cut settings saved."); return; }
    if (op=="cut-all") {
      memcpy(batchHoles,parsed,count*sizeof(BatchHole));
      batchSettings=settings; batchCount=count; batchIndex=0; batchRunning=true; batchReturning=batchReturned=false;
      planBatchHole();
      reply(200, "List validated. Cutting holes in order."); return;
    }
    if (!startCut(pulses,rate,settings.feed,(accel*800+30)/60)) {
      reply(503, "Unable to start cut; check position storage."); return;
    }
    reply(200, "Cut started: spinning plunge, two turns at depth, spinning retract."); return;
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
      if (Positions::saved.meshSet) {
        if (!Positions::known || !Positions::saved.homeSet) { reply(409,"Confirm A1 before mesh moves."); return; }
        int64_t current[4]; Positions::snapshot(current);
        const auto &s=Positions::saved;
        const int64_t x=current[0]-s.home[0], y=current[1]-s.home[1];
        double c,r;
        if (!BedMesh::locate(s.mesh,x,y,c,r)) { reply(409,"Cannot locate drill on mesh."); return; }
        const long col=long(BedMesh::rounded(c)),row=long(BedMesh::rounded(r));
        const long nc=col+(a==0?count:0),nr=row-(a==1?count:0);
        if (nc<1 || nc>34 || nr<0 || nr>25 || col<1 || col>34 || row<0 || row>25) {
          reply(400,"Hole step is outside A1–Z34. Use mm jogs."); return;
        }
        int64_t fx,fy,tx,ty; holeOffset(col,row,fx,fy); holeOffset(nc,nr,tx,ty);
        planHole(current,x+tx-fx,y+ty-fy,false,1000);
        reply(200,"Moving by calibrated holes."); return;
      }
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
    // A named hole on the calibrated grid: lift, cross in a straight XY
    // line, then restore the starting bed-relative height (raw Z without mesh).
    long col, row;
    if (!parseHole(server.arg("hole").c_str(), col, row)) {
      reply(400, "That hole is off the board. Holes run A1 to Z34."); return;
    }
    if (!Positions::known || !Positions::saved.homeSet) { reply(409, "Set A1 and confirm the position first."); return; }
    int64_t x, y; holeOffset(col, row, x, y);
    int64_t current[4]; Positions::snapshot(current);
    if (Positions::saved.home[0] + x == current[0] && Positions::saved.home[1] + y == current[1]) { reply(200, "Already at that hole."); return; }
    planHole(current,x,y);
    reply(200, "Moving to hole with travel clearance."); return;
  }
  if (op == "go-home" || op == "go-replace") {
    if (!Positions::known || !Positions::saved.homeSet || (op == "go-replace" && !Positions::saved.replaceSet)) {
      reply(409, "Set A1 and confirm the position first."); return;
    }
    const int64_t *p = op == "go-home" ? Positions::saved.home : Positions::saved.replace;
    planSaved(p);
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
  if (batchRunning && activeMotor<0) {
    if (!armed || !Positions::known || !Positions::commissioned()) {
      disableMotors(); disableReason="Cut list aborted; check position"; return;
    }
    if (!presetRunning) {
      if (batchReturning) {
        batchReturned=true; batchReturning=false; batchRunning=false; return;
      }
      if (batchCutting) {
        if (++batchIndex==batchCount) {
          batchReturning=true; batchCutting=false;
          planSaved(Positions::saved.home,true); return;
        }
        planBatchHole();
      } else {
        const auto &c=batchSettings;
        if (!startCut(c.depth,(c.rpm*800+30)/60,c.feed,(c.accel*800+30)/60)) {
          disableMotors(); disableReason="Unable to start next cut"; return;
        }
        batchCutting=true;
      }
      return;
    }
  }
  if (!presetRunning || activeMotor >= 0) return;
  if (!armed || !Positions::known || !Positions::commissioned()) { disableMotors(); return; }
  int64_t current[4]; Positions::snapshot(current);
  while (stage < 3) {
    const int m = order[stage];
    if (m < 0) {
      // Both axes together at the hole-travel rate, like Go to hole.
      const int64_t dx = target[0]-current[0], dy = target[1]-current[1];
      if (!dx && !dy) { ++stage; continue; }
      if (!startXYLine(dx, dy, travelRate)) { disableMotors(); disableReason = "Unable to start saved move"; }
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
