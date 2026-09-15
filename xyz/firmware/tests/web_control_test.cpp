#include <cassert>
#include <iostream>
#include "../xyza/xyza.ino"

int action(const char *op, const char *axis="", const char *pulses="") {
  WebControl::server.args={{"op",op},{"axis",axis},{"pulses",pulses},{"client","test-browser-0001"}};
  WebControl::action();
  return WebControl::server.code;
}
void run() {
  int iterations=0;
  while (!WebControl::idle() && iterations++ < 30000) {
    webHeartbeat=millis(); loop();
  }
  assert(WebControl::idle());
}
int main() {
  setup(); WiFi.state=WL_CONNECTED; Serial.connected=false;
  // A connected client that sends nothing is dropped after 400 ms, not the
  // stock 5 s that would starve the 3 s lease and stop the motors.
  WebControl::server._currentStatus=HC_WAIT_READ; WebControl::server._statusChange=millis();
  delay(300); WebControl::service();
  assert(WebControl::server._currentStatus==HC_WAIT_READ && !WebControl::server._currentClient.stopped);
  delay(200); WebControl::service();
  assert(WebControl::server._currentStatus==HC_NONE && WebControl::server._currentClient.stopped);
  WebControl::server._currentStatus=HC_WAIT_READ; WebControl::server._statusChange=millis();
  WebControl::server._currentClient={1,false}; delay(600); WebControl::service();
  assert(!WebControl::server._currentClient.stopped); // Data pending: not silent.
  WebControl::server._currentStatus=HC_NONE; WebControl::server._currentClient={};
  assert(action("arm")==403 && !armed);
  WebControl::server.headers["X-XYZ-Control"]="1";
  assert(action("replace")==409);
  assert(action("arm")==200 && armed && webArmed);
  WebControl::server.args={{"op","heartbeat"},{"client","different-browser"}};
  WebControl::action(); assert(WebControl::server.code==409);
  // An open controlling page must survive the former 30-second idle cutoff.
  for (int i=0;i<35;++i) { action("poll"); delay(1000); loop(); }
  assert(armed && webArmed);
  // A transient delay longer than the old lease still recovers.
  delay(1800); action("poll"); loop(); assert(armed);
  WebControl::server.args={{"op","hidden"},{"client","test-browser-0001"}};
  WebControl::action(); assert(armed); // A hidden page no longer stops anything.
  assert(action("jog","A","10")==400);
  assert(action("jog","Z","1001")==400);
  assert(action("jog","X","1junk")==400);
  assert(action("jog","X","100")==200);
  assert(action("home")==409); // No saving while moving.
  run(); assert(emitted[0]==100 && armed); // Works with USB disconnected.
  assert(action("home")==200 && Positions::known);
  assert(action("jog","Z","100")==200); run();
  assert(action("jog","X","100")==200); run();
  assert(action("jog","Y","100")==200); run();
  assert(action("replace")==200);
  const int spindle=rises[D5];
  assert(action("go-home")==200);
  WebControl::service(); assert(lineRunning && activeMotor>=0); // Already at higher Z: cross first.
  run(); assert(emitted[0]==100 && emitted[1]==0 && emitted[3]==0);
  assert(rises[D5]==spindle);
  assert(action("go-replace")==200);
  WebControl::service(); assert(activeMotor==3); // Raise Z before XY.
  run(); assert(emitted[0]==200 && emitted[1]==100 && emitted[3]==100);
  // Go to a hole by name: raise Z by 1 mm, then one straight XY line; the
  // drill stays raised.
  assert(action("goto")==400);
  for (const char *bad : {"A0", "A35", "AA1", " B2", "B 2", "B2 ", "B+2", "2B", "B", "B2x"}) {
    WebControl::server.args={{"op","goto"},{"hole",bad},{"client","test-browser-0001"}};
    WebControl::action(); assert(WebControl::server.code==400);
  }
  assert(WebControl::roundDiv(5,2)==3 && WebControl::roundDiv(-5,2)==-2); // Halves up, like Math.round.
  assert(WebControl::roundDiv(-7,2)==-3 && WebControl::roundDiv(7,3)==2 && WebControl::roundDiv(-7,3)==-2 && WebControl::roundDiv(-8,3)==-3);
  WebControl::server.args={{"op","goto"},{"hole","c2"},{"client","test-browser-0001"}};
  WebControl::action(); assert(WebControl::server.code==200);
  const int64_t zStart=emitted[3];
  WebControl::service(); assert(activeMotor==3 && !lineRunning); // Lift first.
  {
    const size_t x0=riseTimes[D1].size(), y0=riseTimes[D3].size();
    while (activeMotor==3) loop();
    assert(emitted[3]==zStart+100 && riseTimes[D1].size()==x0 && riseTimes[D3].size()==y0); // XY waited for the lift.
    WebControl::service(); assert(activeMotor==1 && lineRunning && !demoRunning); // One straight line; Y is the longer axis.
    run(); assert(emitted[3]==zStart+100); // No lowering afterwards.
    assert(riseTimes[D1].back() > riseTimes[D3][y0]); // X and Y overlapped, not in turn.
    assert(armed && !lineRunning && WebControl::idle()); // Unlike DEMO, stays armed.
  }
  assert(emitted[0]==Positions::saved.home[0]+254 && emitted[1]==Positions::saved.home[1]-508);
  assert(emitted[3]==Positions::saved.replace[3]+100);
  // An axis-aligned hole move to row Z cruises at 4,000 pulses/sec.
  WebControl::server.args={{"op","goto"},{"hole","Z2"},{"client","test-browser-0001"}};
  { const size_t y0=riseTimes[D3].size(); const int xPulses=rises[D1];
    WebControl::action(); assert(WebControl::server.code==200); run();
    assert(rises[D1]==xPulses && emitted[1]==Positions::saved.home[1]-6350);
    const uint32_t gap=riseTimes[D3][y0+2001]-riseTimes[D3][y0+2000];
    assert(gap>=249 && gap<=251); }
  { const int64_t z=emitted[3]; WebControl::action(); assert(WebControl::server.code==200 && WebControl::idle()); // Already there: no lift either.
    run(); assert(emitted[3]==z); }
  WebControl::server.args={{"op","goto"},{"hole","B1"},{"client","test-browser-0001"}};
  WebControl::action(); assert(WebControl::server.code==200); run();
  // Calibrate the grid: boards are not exactly on a 2.54 mm pitch. Saving
  // Z34 far from its nominal place is refused as a probable wrong hole.
  const int64_t *home=Positions::saved.home;
  assert(action("span")==409 && !Positions::saved.spanSet);
  WebControl::state(); assert(WebControl::server.body.find("\"spanSet\":false")!=std::string::npos);
  WebControl::server.args={{"op","goto"},{"hole","Z34"},{"client","test-browser-0001"}};
  WebControl::action(); assert(WebControl::server.code==200); run();
  assert(emitted[0]==home[0]+8382 && emitted[1]==home[1]-6350); // Nominal grid until Z34 is set.
  assert(action("jog","X","80")==200); run(); assert(action("jog","Y","-60")==200); run();
  assert(action("span")==200 && Positions::saved.spanSet);
  assert(Positions::saved.span[0]==8462 && Positions::saved.span[1]==-6410 && Positions::saved.clean);
  WebControl::state(); assert(WebControl::server.body.find("\"spanSet\":true")!=std::string::npos);
  assert(WebControl::server.body.find("\"span\":[8462,-6410]")!=std::string::npos);
  // Holes interpolate per axis between A1 and Z34, rounded to whole pulses.
  WebControl::server.args={{"op","goto"},{"hole","A34"},{"client","test-browser-0001"}};
  WebControl::action(); assert(WebControl::server.code==200); run();
  assert(emitted[0]==home[0]+8462 && emitted[1]==home[1]);
  WebControl::server.args={{"op","goto"},{"hole","M12"},{"client","test-browser-0001"}};
  WebControl::action(); assert(WebControl::server.code==200); run();
  assert(emitted[0]==home[0]+2821 && emitted[1]==home[1]-3077); // 8462*11/33, -6410*12/25.
  // Arrow steps in whole holes use the local calibrated pitch, so an on-grid
  // start lands on the grid and an off-grid start keeps its offset.
  WebControl::server.args={{"op","jog"},{"axis","X"},{"holes","1"},{"client","test-browser-0001"}};
  WebControl::action(); assert(WebControl::server.code==200); run();
  assert(emitted[0]==home[0]+3077); // Column 13: 8462*12/33.
  WebControl::server.args={{"op","jog"},{"axis","Y"},{"holes","-1"},{"client","test-browser-0001"}};
  WebControl::action(); assert(WebControl::server.code==200); run();
  assert(emitted[1]==home[1]-3333); // Row N: -6410*13/25.
  assert(action("jog","X","10")==200); run();
  WebControl::server.args={{"op","jog"},{"axis","X"},{"holes","-1"},{"client","test-browser-0001"}};
  WebControl::action(); assert(WebControl::server.code==200); run();
  assert(emitted[0]==home[0]+2821+10);
  WebControl::server.args={{"op","jog"},{"axis","Y"},{"holes","3"},{"client","test-browser-0001"}};
  WebControl::action(); assert(WebControl::server.code==200); run();
  assert(emitted[1]==home[1]-2564); // Row K: -6410*10/25.
  for (auto bad : {std::pair<const char*,const char*>{"X","4"}, {"Z","1"}, {"X","0"}, {"Y","-4"}, {"X","1.5"}}) {
    WebControl::server.args={{"op","jog"},{"axis",bad.first},{"holes",bad.second},{"client","test-browser-0001"}};
    WebControl::action(); assert(WebControl::server.code==400);
  }
  assert(WebControl::nearestIndex(0,8462)==34 && WebControl::nearestIndex(0,128)==1 && WebControl::nearestIndex(0,129)==2);
  assert(WebControl::nearestIndex(1,-6410)==25 && WebControl::nearestIndex(1,-128)==0 && WebControl::nearestIndex(1,-129)==1);
  assert(WebControl::nearestIndex(0,-300)==0 && WebControl::nearestIndex(1,300)==-1); // Off-board extrapolation.
  assert(action("go-replace")==200); run(); // Back where the reboot check expects.
  assert(emitted[0]==Positions::saved.replace[0] && emitted[1]==Positions::saved.replace[1]);
  action("stop");
  Positions::begin(); // Clean reboot restores counts but requires confirmation.
  assert(!Positions::known && Positions::saved.homeSet && Positions::saved.replaceSet && Positions::saved.spanSet);
  assert(Positions::saved.clean && emitted[0]==200);
  action("arm"); assert(action("go-home")==409);
  assert(action("confirm")==200 && Positions::known);
  // Power loss after motion starts leaves no recoverable checkpoint.
  assert(action("jog","X","500")==200);
  assert(!Positions::saved.clean);
  delay(100); timerStop(stepTimer); activeMotor=-1; remaining=0;
  disableMotors(); Positions::begin();
  assert(!Positions::saved.clean && !Positions::known);
  assert(action("confirm")==409);
  assert(action("reference")==200 && emitted[0]==100 && emitted[3]==0);
  assert(Positions::saved.replaceSet);
  // Storage failure rejects motion before the first pulse and preserves presets.
  Positions::preferences.failWrite=true;
  assert(action("home")==409);
  action("arm"); const int before=rises[D1];
  assert(action("jog","X","100")==503);
  delay(100); assert(rises[D1]==before);
  Positions::preferences.failWrite=false;
  // No dead-man's handle: a move completes with no polls at all and through
  // network loss. Idle motors are released after a minute without the page.
  WebControl::runCommand("JOG Y 2000 200");
  assert(activeMotor==1);
  const int64_t yBefore=emitted[1];
  WiFi.state=0;
  delay(Config::webIdleMs+100);
  WebControl::service(); assert(armed && activeMotor==1); // Still moving: not released.
  finishMotion(); assert(activeMotor==-1 && armed && emitted[1]==yBefore+2000 && Positions::known);
  WebControl::service(); // Idle and unheard-from for a minute: release.
  assert(!armed && std::string(disableReason)=="Control page away for 60 s");
  WiFi.state=WL_CONNECTED;
  action("arm");
  for (const char *axis : {"X", "Y", "Z"}) {
    const int m=axisMotor[axisIndex(axis)];
    const int64_t start=emitted[m];
    assert(action("jog",axis,"1000")==200);
    assert(stepIntervals[499]>=1000 && stepIntervals[499]<=1001); // 1,000 pulses/sec cruise.
    run(); assert(emitted[m]==start+1000);
    assert(action("jog",axis,"-1000")==200);
    run(); assert(emitted[m]==start);
  }
  // Stopping mid-move leaves the position unknown.
  assert(action("jog","X","1000")==200); delay(100); action("stop");
  assert(!armed && !Positions::known);
  // Establishing a different, unknown home invalidates the old replacement,
  // but the Z34 offset describes the board and scale, so it is kept.
  assert(action("home")==200 && !Positions::saved.replaceSet && Positions::saved.spanSet);
  Positions::begin(); assert(Positions::saved.homeSet && !Positions::saved.replaceSet && Positions::saved.spanSet);
  // A version 1 record (no Z34) loads with the nominal grid; the next write upgrades it.
  {
    auto &blob=Positions::preferences.blob; const auto keep=Positions::saved;
    assert(blob.size()==sizeof(Positions::Record));
    blob.resize(Positions::legacySize); const uint32_t v1=1; memcpy(blob.data(), &v1, sizeof(v1));
    Positions::begin();
    assert(Positions::saved.version==2 && Positions::saved.homeSet && !Positions::saved.spanSet && blob.size()==Positions::legacySize);
    int64_t x,y; WebControl::holeOffset(34,25,x,y); assert(x==8382 && y==-6350);
    assert(Positions::write(Positions::saved) && blob.size()==sizeof(Positions::Record));
    const uint32_t bad=3; memcpy(blob.data(), &bad, sizeof(bad));
    Positions::begin(); assert(!Positions::saved.homeSet); // Unknown versions are ignored.
    Positions::ready=true; assert(Positions::write(keep)); Positions::begin();
    assert(Positions::saved.homeSet && Positions::saved.spanSet);
  }
  WebControl::state(); assert(WebControl::server.body.find("\"known\":false")!=std::string::npos);
  // Preset distances exceed both manual jog caps and the 6,000-entry jog
  // buffer. Verify every cruise gap across former chunk boundaries, XYZ in
  // both directions, with only one start/stop per leg. X and Y share one
  // diagonal line at 4,000 pulses/sec along the path: 4000/sqrt(2) per axis.
  assert(action("confirm")==200);
  auto preset = Positions::saved;
  constexpr int travel=7001;
  for (int m : {0,1,3}) preset.replace[m]=preset.home[m]+travel;
  preset.replaceSet=true;
  assert(Positions::write(preset));
  action("arm");
  for (const char *op : {"go-replace","go-home"}) {
    size_t starts[4];
    for (int m : {0,1,3}) starts[m]=riseTimes[Config::stepPins[m]].size();
    const int spindleBefore=rises[D5];
    assert(action(op)==200);
    run();
    assert(rises[D5]==spindleBefore);
    for (int m : {0,1,3}) {
      const auto &times=riseTimes[Config::stepPins[m]];
      assert(times.size()-starts[m]==travel);
      const int margin = m==3 ? 51 : 600; // Diagonal ramp: 800 path pulses.
      for (int i=margin;i<travel-margin;++i) {
        const uint32_t gap=times[starts[m]+i]-times[starts[m]+i-1];
        if (m==3) assert(gap>=1000 && gap<=1001); else assert(gap>=353 && gap<=355);
      }
      if (m==0) assert(riseTimes[D1][starts[0]]==riseTimes[D3][starts[1]]); // Same tick.
      const int64_t expected=std::string(op)=="go-home" ? preset.home[m] : preset.replace[m];
      assert(emitted[m]==expected);
    }
  }
  assert(action("go-replace")==200); WebControl::service(); delay(100);
  assert(presetProfileActive && remaining>0);
  assert(action("stop")==200);
  const int stoppedZ=rises[D9]; delay(1000);
  assert(rises[D9]==stoppedZ && !presetRunning && !Positions::known);
  // Compare compressed and full profiles, including short triangular moves
  // and odd lengths. Mirrored floating-point rounding differs by at most 1 us.
  for (int count : {1,2,3,49,50,51,99,100,101,1000,6000}) {
    assert(presetProfile.build(count,1000,10000));
    buildProfile(stepIntervals,count,1000,10000);
    for (int i=0;i<count;++i)
      assert(std::abs(int64_t(presetProfile.interval(i))-stepIntervals[i])<=1);
  }
  std::cout << "Web control and position persistence tests passed\n";
}
