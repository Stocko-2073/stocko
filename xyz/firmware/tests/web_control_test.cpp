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
  WebControl::server.args={{"op","hidden"},{"client","observer-browser"}};
  WebControl::action(); assert(armed);
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
  WebControl::service(); assert(activeMotor==0); // Already at higher Z: X first.
  run(); assert(emitted[0]==100 && emitted[1]==0 && emitted[3]==0);
  assert(rises[D5]==spindle);
  assert(action("go-replace")==200);
  WebControl::service(); assert(activeMotor==3); // Raise Z before XY.
  run(); assert(emitted[0]==200 && emitted[1]==100 && emitted[3]==100);
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
  // The ISR enforces the browser lease even if HTTP blocks the main loop.
  WebControl::runCommand("JOG Y 2000 200");
  assert(activeMotor==1);
  delay(Config::webLeaseMs+100); assert(webExpired && levels[D10]==HIGH);
  const int stopped=rises[D3]; delay(1000); assert(rises[D3]==stopped);
  WebControl::service(); assert(!armed && !Positions::known && !presetRunning);
  assert(std::string(disableReason)=="Browser connection timed out");
  assert(action("reference")==200);
  action("arm"); action("go-replace"); WebControl::service();
  assert(action("stop")==200); assert(!presetRunning && !armed);
  // Network loss stops an active web move.
  action("reference"); action("arm"); action("jog","X","100");
  WiFi.state=0; WebControl::service(); assert(!armed && !Positions::known);
  assert(std::string(disableReason)=="Wi-Fi disconnected");
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
  action("stop");
  // Establishing a different, unknown home invalidates the old replacement.
  assert(action("home")==200 && !Positions::saved.replaceSet);
  Positions::begin(); assert(Positions::saved.homeSet && !Positions::saved.replaceSet);
  WebControl::state(); assert(WebControl::server.body.find("\"known\":false")!=std::string::npos);
  // Preset distances exceed both manual jog caps and the 6,000-entry jog
  // buffer. Verify every cruise gap across former chunk boundaries, XYZ in
  // both directions, with only one start/stop per axis leg.
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
      for (int i=51;i<travel-50;++i) {
        const uint32_t gap=times[starts[m]+i]-times[starts[m]+i-1];
        assert(gap>=1000 && gap<=1001);
      }
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
