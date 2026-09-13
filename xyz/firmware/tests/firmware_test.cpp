#include <cassert>
#include <iostream>
#include "../xyza/xyza.ino"

void send(const std::string &s) {
  for (char c : s) Serial.input.push_back(c);
  while (Serial.available()) loop();
}
void runMotion() {
  for (int i=0; activeMotor >= 0 && i<10000; ++i) loop();
  assert(activeMotor == -1);
}
int main() {
  setup();
  assert(!armed && levels[D10] == HIGH);
  for (int i=0; i<4; ++i) assert(axisMotor[i] == Config::axisMotor[i] && rises[Config::stepPins[i]] == 0);
  assert(axisMotor[0] == 0 && axisMotor[1] == 1 && axisMotor[2] == 3 && axisMotor[3] == -1);
  send("JOG M0 10\n"); assert(activeMotor == -1);
  send("ARM\n"); assert(armed && levels[D10] == LOW);
  for (const char *bad : {"JOG M0 0\n", "JOG M0 1001\n", "JOG M0 -1001\n",
                         "JOG M3 501\n", "JOG Z -501\n", "JOG M2 201\n",
                         "JOG M1 2001\n", "JOG Y -2001\n",
                         "JOG M0 10 0\n", "JOG M0 10 3001\n", "JOG Z 10 2001\n", "JOG M4 1\n",
                         "JOG A 1\n", "JOG M0 1junk\n", "JOG M0 999999999999999999999\n"}) {
    send(bad); assert(activeMotor == -1);
  }
  send("MAP X M1\n"); assert(axisMotor[0] == 0);
  send("JOG M0 10 200\n");
  send("JOG M1 1\n"); assert(activeMotor == 0);
  runMotion(); assert(emitted[0] == 10 && rises[D1] == 10 && rises[D3] == 0);
  send("JOG M0 -10 200\n"); runMotion(); assert(emitted[0] == 0 && rises[D1] == 20);
  send("OFF\nMAP X M0\nMAP Y M0\nINVERT M0 1\n");
  assert(axisMotor[0] == -1 && axisMotor[1] == 0 && inverted[0]);
  send("ARM\nJOG Y 5 200\n"); assert(levels[D0] == LOW);
  runMotion(); assert(emitted[0] == 5);
  send("JOG M0 200\n!ARM\n"); assert(!armed && activeMotor == -1);
  int stoppedCount = rises[D1];
  for (int i=0; i<100; ++i) loop();
  assert(rises[D1] == stoppedCount);
  send("ARM\n" + std::string(100, 'x') + "ARM\n"); assert(!armed);
  send(std::string("ARM\nJOG M0 ") + '\0' + "10\n"); assert(!armed);
  send("ARM\n"); clockUs += 30000000; loop(); assert(!armed);
  send("ARM\nJOG M0 200\n"); Serial.connected = false; loop();
  assert(!armed && activeMotor == -1 && levels[D10] == HIGH);
  Serial.connected = true;
  // Scheduling must continue across the micros() rollover.
  clockUs = UINT32_MAX - 2000;
  send("ARM\nJOG M1 2 200\n"); runMotion(); assert(emitted[1] == 2);
  send("JOG Z 2 200\n"); runMotion(); assert(emitted[3] == 2 && rises[D9] == 2);
  send("STOP\n"); assert(!armed);
  send("ARM\nJOG M0 1000 200\n"); runMotion(); assert(emitted[0] == 1005);
  send("JOG M1 -1000 200\n"); runMotion(); assert(emitted[1] == -998);
  send("OFF\nMAP X M3\nARM\nJOG X 501\n");
  assert(activeMotor == -1 && emitted[3] == 2); // Mapping cannot bypass Z motor cap.
  send("STOP\n");
  // The 1000-pulse 500/s trapezoid lasts 2.1 s, instead of the old ~11 s jog.
  uint32_t profile[1000];
  buildProfile(profile, 1000, 500, 5000);
  uint64_t total=0;
  for (uint32_t interval : profile) { assert(interval >= 2000); total += interval; }
  assert(total >= 2100000 && total < 2101000);
  assert(profile[0] > profile[1] && profile[998] < profile[999]);
  // Short triangular move never reaches its requested 3000/s cruise rate.
  buildProfile(profile, 10, 3000, 5000);
  total=0;
  for (int i=0; i<10; ++i) { assert(profile[i] >= 333); total += profile[i]; }
  assert(total >= 89442 && total < 89460);
  // Hardware timer mock emits pulses even with no main-loop service.
  send("ARM\nJOG M0 1000 500\n");
  const int before=rises[D1];
  delay(2200);
  assert(rises[D1]-before == 1000 && remaining == 0 && motionComplete);
  finishMotion(); assert(activeMotor == -1);
  // Stop during the faster move suppresses all further scheduled pulses.
  send("JOG M0 1000 3000\n"); delay(50);
  assert(remaining > 0 && remaining < 1000);
  disableMotors();
  const int afterStop=rises[D1]; delay(1000); assert(rises[D1] == afterStop);
  // Simulate a delayed interrupt: next pulse is a full interval later, no burst.
  send("ARM\nJOG M0 1000 3000\n");
  advanceRaw(100000); delayMicroseconds(0);
  const uint32_t delayedRise=riseTimes[D1].back();
  delay(100);
  const auto &times=riseTimes[D1];
  auto delayed=std::find(times.begin(), times.end(), delayedRise);
  assert(delayed != times.end() && delayed+1 != times.end());
  assert(uint32_t(*(delayed+1)-*delayed) >= stepIntervals[1]);
  send("STOP\n");
  // Verify the complete demo geometry, not only its endpoint.
  const size_t events = buildDemo(demoEvents);
  assert(events > 15000 && events <= demoCapacity);
  int x=0, y=0;
  uint64_t demoUs=0;
  for (size_t i=0; i<events; ++i) {
    const auto &e=demoEvents[i];
    assert(std::abs(e.dx)<=1 && std::abs(e.dy)<=1 && (e.dx || e.dy));
    assert(e.interval >= 350 && e.interval <= 100000);
    demoUs += e.interval;
    x += e.dx; y += e.dy;
    assert(x>=0 && x<=2000 && y>=0 && y<=2000);
    if (i==1999) assert(x==2000 && y==0);
    if (i==3999) assert(x==2000 && y==2000);
    if (i==5999) assert(x==0 && y==2000);
    if (i==7999) assert(x==0 && y==0);
    if (i>=9000 && i<events-1000)
      assert(std::abs(std::hypot(x-1000,y-1000)-1000)<2);
  }
  assert(x==0 && y==0 && demoUs>9600000 && demoUs<9800000);
  assert(std::hypot(demoCircleAccel, demoRate*demoRate/demoRadius) <= Config::acceleration[0]);
  assert(Config::acceleration[0] == 10000 && Config::acceleration[1] == 10000);
  buildProfile(profile, 1000, 2000, Config::acceleration[0]);
  total=0;
  for (uint32_t interval : profile) { assert(interval>=500); total+=interval; }
  assert(total>=700000 && total<701000);
  send("DEMO\n"); assert(!demoRunning); // Cannot start while disabled.
  send("ARM\nDEMO\n"); assert(!demoRunning); // Reject earlier remapped/inverted axes.
  send("OFF\nMAP X M0\nMAP Y M1\nINVERT M0 0\nARM\nDEMO\n");
  assert(demoRunning && remaining>0);
  const int64_t startX=emitted[0], startY=emitted[1];
  const int startZ=rises[D9], startA=rises[D5];
  const int startXPulses=rises[D1], startYPulses=rises[D3];
  delay(40000); finishMotion();
  assert(!armed && !demoRunning && activeMotor==-1);
  assert(emitted[0]==startX && emitted[1]==startY);
  int expectedX=0, expectedY=0;
  for (size_t i=0; i<events; ++i) {
    expectedX += std::abs(demoEvents[i].dx);
    expectedY += std::abs(demoEvents[i].dy);
  }
  assert(rises[D1]-startXPulses == expectedX*3);
  assert(rises[D3]-startYPulses == expectedY*3);
  assert(rises[D9]==startZ && rises[D5]==startA);
  send("ARM\nDEMO\n"); delay(100); send("!\n");
  const int stoppedX=rises[D1], stoppedY=rises[D3]; delay(40000);
  assert(!armed && !demoRunning && rises[D1]==stoppedX && rises[D3]==stoppedY);
  send("ARM\nDEMO\n"); delay(100); Serial.connected=false; loop();
  assert(!armed && !demoRunning);
  Serial.connected=true;
  uint32_t longProfile[2000];
  buildProfile(longProfile, 2000, 2000, 5000);
  uint64_t longUs=0;
  for (uint32_t interval : longProfile) { assert(interval >= 500); longUs += interval; }
  assert(longUs >= 1400000 && longUs < 1402000);
  const int64_t previousY=emitted[1];
  send("ARM\nJOG Y -2000 2000\n"); runMotion();
  assert(emitted[1] == previousY-2000);
  send("STOP\n");
  uint32_t zProfile[200];
  buildProfile(zProfile, 200, Config::maxRate[3], Config::acceleration[3]);
  uint64_t zUs=0;
  for (uint32_t interval : zProfile) { assert(interval>=707); zUs+=interval; }
  assert(zUs>=282842 && zUs<283043);
  const int64_t previousZ=emitted[3];
  const int xBeforeZ=rises[D1], yBeforeZ=rises[D3], aBeforeZ=rises[D5];
  send("MAP Z M3\nARM\nJOG Z -200 2000\n"); runMotion();
  assert(emitted[3]==previousZ-200);
  assert(rises[D1]==xBeforeZ && rises[D3]==yBeforeZ && rises[D5]==aBeforeZ);
  send("STOP\n");
  uint32_t zLongProfile[500];
  buildProfile(zLongProfile, 500, 2000, Config::acceleration[3]);
  zUs=0;
  for (uint32_t interval : zLongProfile) { assert(interval>=500); zUs+=interval; }
  assert(zUs>=450000 && zUs<450500);
  const int64_t patternZ=emitted[3];
  send("ARM\nJOG Z 500 2000\n"); runMotion();
  assert(emitted[3]==patternZ+500);
  delay(500);
  send("JOG Z -500 2000\n"); runMotion();
  assert(emitted[3]==patternZ);
  assert(rises[D1]==xBeforeZ && rises[D3]==yBeforeZ && rises[D5]==aBeforeZ);
  send("STOP\n");
  std::cout << "Firmware control tests passed; demo cycle " << demoUs/1000000.0 << " s\n";
}
