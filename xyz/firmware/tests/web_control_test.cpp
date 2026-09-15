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
  // Go to a hole: travel X then Y at the current drill height, never Z.
  assert(action("goto")==400);
  WebControl::server.args={{"op","goto"},{"x","254"},{"y","10"},{"client","test-browser-0001"}};
  WebControl::action(); assert(WebControl::server.code==400); // Rows only run forward.
  WebControl::server.args={{"op","goto"},{"x","8383"},{"y","0"},{"client","test-browser-0001"}};
  WebControl::action(); assert(WebControl::server.code==400); // Past column 34.
  WebControl::server.args={{"op","goto"},{"x","0"},{"y","-6351"},{"client","test-browser-0001"}};
  WebControl::action(); assert(WebControl::server.code==400); // Past row Z.
  WebControl::server.args={{"op","goto"},{"x","254"},{"y","-508"},{"client","test-browser-0001"}};
  WebControl::action(); assert(WebControl::server.code==200);
  assert(activeMotor==1 && lineRunning && !demoRunning); // One straight line; Y is the longer axis.
  {
    const int zPulses=rises[D9]; const size_t y0=riseTimes[D3].size();
    run(); assert(rises[D9]==zPulses);
    assert(riseTimes[D1].back() > riseTimes[D3][y0]); // X and Y overlapped, not in turn.
    assert(armed && !lineRunning && WebControl::idle()); // Unlike DEMO, stays armed.
  }
  assert(emitted[0]==Positions::saved.home[0]+254 && emitted[1]==Positions::saved.home[1]-508);
  assert(emitted[3]==Positions::saved.replace[3]);
  // An axis-aligned hole move to row Z cruises at 4,000 pulses/sec.
  WebControl::server.args={{"op","goto"},{"x","254"},{"y","-6350"},{"client","test-browser-0001"}};
  { const size_t y0=riseTimes[D3].size(); const int xPulses=rises[D1];
    WebControl::action(); assert(WebControl::server.code==200); run();
    assert(rises[D1]==xPulses && emitted[1]==Positions::saved.home[1]-6350);
    const uint32_t gap=riseTimes[D3][y0+2001]-riseTimes[D3][y0+2000];
    assert(gap>=249 && gap<=251); }
  WebControl::action(); assert(WebControl::server.code==200 && WebControl::idle()); // Already there.
  WebControl::server.args={{"op","goto"},{"x","254"},{"y","0"},{"client","test-browser-0001"}};
  WebControl::action(); assert(WebControl::server.code==200); run();
  assert(action("go-replace")==200); run(); // Back where the reboot check expects.
  assert(emitted[0]==Positions::saved.replace[0] && emitted[1]==Positions::saved.replace[1]);
  action("stop");
  Positions::begin(); // Clean reboot restores counts but requires confirmation.
  assert(!Positions::known && Positions::saved.homeSet && Positions::saved.replaceSet);
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
  // Establishing a different, unknown home invalidates the old replacement.
  assert(action("home")==200 && !Positions::saved.replaceSet);
  Positions::begin(); assert(Positions::saved.homeSet && !Positions::saved.replaceSet);
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
