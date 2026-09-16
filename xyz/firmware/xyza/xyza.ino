#include <Arduino.h>
#include <errno.h>
#include <limits.h>
#include <stdlib.h>
#include <string.h>
#include <new>
#include "config.h"
#include "cut_settings.h"
#include "crash_log.h"
#include "wifi_provisioning.h"
#include "motion_profile.h"
#include "demo_path.h"

int8_t axisMotor[4];
bool inverted[4];
bool armed = false;
int activeMotor = -1;
volatile long remaining = 0;
int direction = 1;
int64_t emitted[4] = {}; // Commanded pulses; physical reference requires operator confirmation.
uint32_t idleSinceMs = 0;
hw_timer_t *stepTimer = nullptr;
portMUX_TYPE motionMux = portMUX_INITIALIZER_UNLOCKED;
uint32_t stepIntervals[Config::profileCapacity];
PresetProfile presetProfile;
bool presetProfileActive = false;
volatile size_t pulseIndex = 0;
volatile bool motionComplete = false;
// DEMO and cutting are mutually exclusive. Share their largest planning
// buffers so the 240 RPM spindle ramp doesn't consume another spindle ramp buffer.
constexpr uint32_t spindleRampCapacity=(Config::maxRate[2]*Config::maxRate[2]+2*Config::cutMinAccel-1)/(2*Config::cutMinAccel);
using SpindleProfile=CompactProfile<spindleRampCapacity>;
struct DemoWorkspace { DemoEvent events[demoCapacity]; };
static_assert(sizeof(SpindleProfile)<=sizeof(DemoWorkspace), "Spindle ramp fits the existing motion workspace");
union MotionWorkspace {
  DemoWorkspace demo;
  SpindleProfile spin;
} motionWorkspace = {{}};
auto &demoEvents=motionWorkspace.demo.events;
auto &cutSpinProfile=motionWorkspace.spin;
size_t demoCount = 0;
bool demoRunning = false;
bool demoDisarm = false; // DEMO ends disarmed.
// Straight XY line: the major axis steps every tick, the minor axis by integer
// Bresenham, both on one edge, with one compact profile in tick units.
bool lineRunning = false;
int lineMajor = 0, lineMinor = 1, lineMajorDir = 1, lineMinorDir = 1;
volatile int64_t lineN = 0, lineMinorCount = 0, lineAcc = 0;
char line[96];
size_t lineLength = 0;
bool discardLine = false;
bool previousCR = false;

volatile bool webArmed = false;
volatile uint32_t webHeartbeat = 0;
bool presetRunning = false;
bool batchRunning = false;
volatile int cutPhase = 0; // 0 idle, 1 plunge, 2 dwell, 3 retract, 4 spin down.
PresetProfile cutZProfile;
uint32_t cutZIndex=0, cutAIndex=0, cutDwell=0, cutDecel=0;
uint64_t cutNextZ=0, cutNextA=0;
const char *disableReason = "Startup";
// Web requests already receive their replies over HTTP. USB diagnostics must
// never hold up that reply (or the next poll) when a connected host stops
// reading. Only the loop task writes Serial, so room for the entire line,
// including println's CRLF, is sufficient without changing USB timeouts.
void diagnostic(const char *message) {
  if (Serial.availableForWrite() >= int(strlen(message) + 2)) Serial.println(message);
}
#include "positions.h"

void disableMotors() {
  disableReason = "Stopped";
  const bool interrupted = activeMotor >= 0 && remaining > 0;
  presetRunning = false;
  batchRunning = false;
  webArmed = false;
  portENTER_CRITICAL(&motionMux);
  digitalWrite(Config::enablePin, HIGH);
  for (uint8_t pin : Config::stepPins) digitalWrite(pin, LOW);
  armed = false;
  cutPhase = 0;
  activeMotor = -1;
  remaining = 0;
  motionComplete = false;
  demoRunning = false;
  lineRunning = false;
  presetProfileActive = false;
  portEXIT_CRITICAL(&motionMux);
  if (stepTimer) timerStop(stepTimer);
  if (interrupted) Positions::settled(true);
}

// Both axes share one timer but have independent step deadlines. All stage
// transitions happen in the interrupt: HTTP/flash/USB stalls cannot pause the
// spindle between plunge, the two-turn dwell, and retract.
void ARDUINO_ISR_ATTR stepCut(uint64_t now) {
  const bool spin=now>=cutNextA;
  const bool z=(cutPhase==1 || cutPhase==3) && now>=cutNextZ;
  const int phase=cutPhase;
  if (spin) digitalWrite(Config::stepPins[2], HIGH);
  if (z) digitalWrite(Config::stepPins[3], HIGH);
  delayMicroseconds(Config::pulseUs);
  if (spin) { digitalWrite(Config::stepPins[2], LOW); ++emitted[2]; ++cutAIndex; }
  if (z) {
    digitalWrite(Config::stepPins[3], LOW);
    emitted[3]+=phase==1 ? -1 : 1;
    if (++cutZIndex==cutZProfile.count) {
      if (phase==1) { cutPhase=2; cutDwell=Config::cutTurnsPulses; }
      else { cutPhase=4; cutDecel=min(cutAIndex,cutSpinProfile.rampCount); }
    } else cutNextZ=now+cutZProfile.interval(cutZIndex);
  }
  if (spin) {
    if (phase==2 && --cutDwell==0) {
      cutPhase=3; cutZIndex=0;
      digitalWrite(Config::dirPins[3], !inverted[3]);
      cutNextZ=now+cutZProfile.interval(0);
    }
    if (cutPhase==4) {
      if (!cutDecel) { remaining=0; motionComplete=true; return; }
      cutNextA=now+cutSpinProfile.ramp[--cutDecel];
    } else {
      cutNextA=now+(cutAIndex<cutSpinProfile.rampCount
        ? cutSpinProfile.ramp[cutAIndex] : cutSpinProfile.cruise);
    }
  }
  uint64_t next=cutNextA;
  if ((cutPhase==1 || cutPhase==3) && cutNextZ<next) next=cutNextZ;
  // Near-coincident deadlines may arrive during a pulse. Keep a full low
  // interval rather than arming an alarm in the past or emitting a burst.
  const uint64_t earliest=timerRead(stepTimer)+Config::pulseUs;
  timerAlarm(stepTimer,next<earliest ? earliest:next,false,0);
}

bool startCut(long depth, long rate, long feed, long accel) {
  if (!armed || !stepTimer || activeMotor>=0 || presetRunning ||
      !Positions::commissioned() || depth<10 || depth>Config::maxJogSteps[3] ||
      rate<1 || rate>Config::maxRate[2] || feed<10 || feed>Config::maxRate[3] ||
      accel<Config::cutMinAccel || accel>(Config::cutMaxAccelRpm*800+30)/60) return false;
  const uint32_t ramp=(rate*rate+2*accel-1)/(2*accel);
  new (&motionWorkspace.spin) SpindleProfile;
  if (!cutZProfile.build(depth,feed,Config::acceleration[3]) ||
      !cutSpinProfile.build(2*ramp+1,rate,accel) ||
      !Positions::beforeMove()) return false;
  timerStop(stepTimer); timerWrite(stepTimer,0);
  portENTER_CRITICAL(&motionMux);
  cutZIndex=cutAIndex=0; cutDwell=cutDecel=0;
  cutNextA=cutSpinProfile.interval(0);
  cutNextZ=std::max(cutNextA,uint64_t(cutZProfile.interval(0)));
  digitalWrite(Config::dirPins[2],!inverted[2]);
  digitalWrite(Config::dirPins[3],inverted[3]);
  cutPhase=1; presetRunning=true; activeMotor=3;
  remaining=1; motionComplete=false; // Nonzero until both axes finish.
  timerAlarm(stepTimer,min(cutNextA,cutNextZ),false,0);
  timerStart(stepTimer);
  portEXIT_CRITICAL(&motionMux);
  return true;
}

// Only precomputed integer intervals and pin operations in the interrupt.
// One-shot alarms avoid catch-up bursts after interrupt latency. The main loop
// can service USB or yield without adding a millisecond to every step.
void ARDUINO_ISR_ATTR onStep() {
  portENTER_CRITICAL_ISR(&motionMux);
  if (armed && activeMotor >= 0 && remaining > 0) {
    const uint64_t riseAt = timerRead(stepTimer);
    if (cutPhase) {
      stepCut(riseAt);
      portEXIT_CRITICAL_ISR(&motionMux);
      return;
    }
    if (demoRunning) {
      const DemoEvent &event = demoEvents[pulseIndex];
      if (event.dx) digitalWrite(Config::dirPins[0], event.dx > 0 ? HIGH : LOW);
      if (event.dy) digitalWrite(Config::dirPins[1], event.dy > 0 ? HIGH : LOW);
      delayMicroseconds(3); // DIR setup before either STEP rising edge.
      if (event.dx) digitalWrite(Config::stepPins[0], HIGH);
      if (event.dy) digitalWrite(Config::stepPins[1], HIGH);
      delayMicroseconds(Config::pulseUs);
      if (event.dx) digitalWrite(Config::stepPins[0], LOW);
      if (event.dy) digitalWrite(Config::stepPins[1], LOW);
      emitted[0] += event.dx;
      emitted[1] += event.dy;
      --remaining;
      pulseIndex = (pulseIndex + 1) % demoCount;
      if (remaining == 0) motionComplete = true;
      else timerAlarm(stepTimer, riseAt + demoEvents[pulseIndex].interval, false, 0);
      portEXIT_CRITICAL_ISR(&motionMux);
      return;
    }
    if (lineRunning) {
      lineAcc += lineMinorCount;
      const bool minor = 2*lineAcc >= lineN;
      if (minor) lineAcc -= lineN;
      digitalWrite(Config::stepPins[lineMajor], HIGH);
      if (minor) digitalWrite(Config::stepPins[lineMinor], HIGH);
      delayMicroseconds(Config::pulseUs);
      digitalWrite(Config::stepPins[lineMajor], LOW);
      if (minor) digitalWrite(Config::stepPins[lineMinor], LOW);
      emitted[lineMajor] += lineMajorDir;
      if (minor) emitted[lineMinor] += lineMinorDir;
      --remaining;
      ++pulseIndex;
      if (remaining == 0) motionComplete = true;
      else timerAlarm(stepTimer, riseAt + presetProfile.interval(pulseIndex), false, 0);
      portEXIT_CRITICAL_ISR(&motionMux);
      return;
    }
    const int m = activeMotor;
    digitalWrite(Config::stepPins[m], HIGH);
    delayMicroseconds(Config::pulseUs);
    digitalWrite(Config::stepPins[m], LOW);
    emitted[m] += direction;
    --remaining;
    ++pulseIndex;
    if (remaining == 0) motionComplete = true;
    else timerAlarm(stepTimer, riseAt + (presetProfileActive ? presetProfile.interval(pulseIndex) : stepIntervals[pulseIndex]), false, 0);
  }
  portEXIT_CRITICAL_ISR(&motionMux);
}

void finishMotion() {
  portENTER_CRITICAL(&motionMux);
  const bool done = motionComplete;
  const bool demoDone = done && demoRunning;
  const bool cutDone = done && cutPhase;
  if (done) { if (cutDone) { cutPhase=0; presetRunning=false; } motionComplete = false; activeMotor = -1; presetProfileActive = false; demoRunning = false; lineRunning = false; }
  portEXIT_CRITICAL(&motionMux);
  if (done) {
    timerStop(stepTimer);
    idleSinceMs = millis();
    Positions::settled(false);
    if (demoDone && demoDisarm) disableMotors();
    if (webArmed) diagnostic("DONE");
    else Serial.println("DONE");
  }
}

bool startProfiledAxis(int m, int64_t steps, long rate) {
  if (!armed || !stepTimer || activeMotor >= 0 || m < 0 || m > 3 ||
      !steps || steps > INT32_MAX || steps < -int64_t(INT32_MAX)) return false;
  const uint32_t pulses = uint32_t(steps > 0 ? steps : -steps);
  if (!presetProfile.build(pulses, min(rate, Config::maxRate[m]), Config::acceleration[m]) || !Positions::beforeMove()) return false;
  timerStop(stepTimer);
  timerWrite(stepTimer, 0);
  portENTER_CRITICAL(&motionMux);
  direction = steps > 0 ? 1 : -1;
  digitalWrite(Config::dirPins[m], (direction > 0) != inverted[m] ? HIGH : LOW);
  remaining = long(pulses);
  pulseIndex = 0;
  motionComplete = false;
  presetProfileActive = true;
  activeMotor = m;
  timerAlarm(stepTimer, presetProfile.interval(0), false, 0);
  timerStart(stepTimer);
  portEXIT_CRITICAL(&motionMux);
  return true;
}

bool startPresetAxis(int m, int64_t steps) {
  return m != 2 && startProfiledAxis(m, steps, 1000);
}

// Straight XY travel between holes. Planning stays cheap on a chip without
// floating-point hardware: only the acceleration ramp is computed, in tick
// units along the path, so a full-board move plans in milliseconds and the
// HTTP reply is never late. Neither axis exceeds the path rate. Requires the
// commissioned XY mapping, which the caller checks.
bool startXYLine(int64_t dx, int64_t dy, long rate) {
  const int64_t nx = dx < 0 ? -dx : dx, ny = dy < 0 ? -dy : dy;
  const int64_t n = nx > ny ? nx : ny, m = nx > ny ? ny : nx;
  if (!armed || !stepTimer || activeMotor >= 0 || !n || n > INT32_MAX ||
      axisMotor[0] != 0 || axisMotor[1] != 1) return false;
  rate = min(rate, min(Config::maxRate[0], Config::maxRate[1]));
  const long accel = min(Config::acceleration[0], Config::acceleration[1]);
  // Ticks per path pulse: on a diagonal each tick covers more than one pulse
  // of path, so per-tick rate and acceleration scale by n/length.
  const double scale = double(n)/std::hypot(double(dx), double(dy));
  if (!presetProfile.build(uint32_t(n), long(rate*scale), long(accel*scale)) || !Positions::beforeMove()) return false;
  timerStop(stepTimer);
  timerWrite(stepTimer, 0);
  portENTER_CRITICAL(&motionMux);
  lineMajor = nx > ny ? 0 : 1; lineMinor = 1-lineMajor;
  lineMajorDir = (lineMajor == 0 ? dx : dy) < 0 ? -1 : 1;
  lineMinorDir = (lineMinor == 0 ? dx : dy) < 0 ? -1 : 1;
  digitalWrite(Config::dirPins[lineMajor], (lineMajorDir > 0) != inverted[lineMajor] ? HIGH : LOW);
  digitalWrite(Config::dirPins[lineMinor], (lineMinorDir > 0) != inverted[lineMinor] ? HIGH : LOW);
  lineN = n; lineMinorCount = m; lineAcc = 0;
  remaining = long(n);
  pulseIndex = 0;
  motionComplete = false;
  presetProfileActive = true;
  lineRunning = true;
  activeMotor = lineMajor;
  timerAlarm(stepTimer, presetProfile.interval(0), false, 0);
  timerStart(stepTimer);
  portEXIT_CRITICAL(&motionMux);
  return true;
}

bool number(const char *s, long low, long high, long &out) {
  if (!s || !*s) return false;
  char *end;
  errno = 0;
  out = strtol(s, &end, 10);
  return !errno && !*end && out >= low && out <= high;
}

int axisIndex(const char *s) {
  if (!s || strlen(s) != 1) return -1;
  const char *axes = "XYZA";
  const char *p = strchr(axes, s[0]);
  return p ? int(p - axes) : -1;
}

int motorIndex(const char *s) {
  if (s && strlen(s) == 2 && s[0] == 'M' && s[1] >= '0' && s[1] <= '3')
    return s[1] - '0';
  return -1;
}

void status() {
  int64_t counts[4];
  portENTER_CRITICAL(&motionMux);
  const long pending = remaining;
  for (int i = 0; i < 4; ++i) counts[i] = emitted[i];
  portEXIT_CRITICAL(&motionMux);
  Serial.printf("STATUS armed=%d busy=%d remaining=%ld position=UNKNOWN\n",
                armed, activeMotor >= 0, pending);
  for (int m = 0; m < 4; ++m)
    Serial.printf("M%d dir_gpio=%u step_gpio=%u inverted=%d pulses=%lld\n",
                  m, Config::dirPins[m], Config::stepPins[m], inverted[m],
                  (long long)counts[m]);
  Serial.println("MOTION timer=hardware profile=rest-to-rest");
  for (int m = 0; m < 4; ++m)
    Serial.printf("M%d max_rate=%ld accel=%ld max_jog=%ld\n", m,
                  Config::maxRate[m], Config::acceleration[m], Config::maxJogSteps[m]);
  for (int a = 0; a < 4; ++a)
    Serial.printf("%c motor=%d\n", "XYZA"[a], axisMotor[a]);
}

void command(char *input, bool fromWeb = false) {
  const auto reply = [fromWeb](const char *message) {
    if (fromWeb) diagnostic(message);
    else Serial.println(message);
  };
  char *args[6];
  int count = 0;
  char *save;
  for (char *s = strtok_r(input, " \t", &save); s; s = strtok_r(nullptr, " \t", &save)) {
    if (count == 6) { reply("ERR too many arguments"); return; }
    args[count++] = s;
  }
  if (!count) return;
  if (!strcmp(args[0], "WIFI") && count == 2) { WifiProvisioning::command(args[1], armed); return; }
  if (!strcmp(args[0], "STOP") || !strcmp(args[0], "OFF")) {
    disableMotors(); reply("OK disabled"); return;
  }
  if (!strcmp(args[0], "STATUS") && count == 1) { status(); return; }
  if (!strcmp(args[0], "HELP") && count == 1) {
    reply("WIFI SET | WIFI STATUS | WIFI FORGET (SET/FORGET require OFF)");
    reply("HELP | STATUS | ARM | OFF | STOP | ! (immediate stop)");
    reply("DEMO: XY square + circle, 3 cycles, 20x20 mm positive envelope; ARM first");
    reply("MAP <X|Y|Z|A> <M0..M3> | INVERT <M0..M3> <0|1> (disabled only)");
    reply("JOG <M0..M3|X|Y|Z|A> <signed nonzero pulses> [cruise pulses/sec]");
    reply("Rate caps: M0/M1=4000, M2=3200, M3=2000; default 1000 (clamped)");
    reply("Per-jog caps: M0=1000, M1=2000, M2=6000, M3=1000 pulses; no travel limits");
    reply("Web manual home/presets: http://xyz.local; mapping is RAM-only.");
    reply("CRASH [INFO|DUMP|CLEAR]: stored crash log from the last panic (disabled only)");
    return;
  }
  if (!strcmp(args[0], "CRASH") && count <= 2) {
    if (armed) { reply("ERR disable first; CRASH [INFO|DUMP|CLEAR]"); return; }
    CrashLog::command(count == 2 ? args[1] : "INFO"); return;
  }
  if (activeMotor >= 0 || presetRunning || batchRunning) { reply("ERR busy; STOP or wait for DONE"); return; }
  if (!strcmp(args[0], "DEMO") && count == 1) {
    if (!armed) { reply("ERR disabled; ARM first"); return; }
    if (axisMotor[0] != 0 || axisMotor[1] != 1 || inverted[0] || inverted[1]) {
      reply("ERR DEMO requires commissioned X=M0 Y=M1, uninverted"); return;
    }
    new (&motionWorkspace.demo) DemoWorkspace;
    demoCount = buildDemo(demoEvents);
    if (!demoCount) { disableMotors(); reply("ERR demo profile"); return; }
    if (!Positions::beforeMove()) { reply("ERR saving motion state"); return; }
    timerStop(stepTimer);
    timerWrite(stepTimer, 0);
    portENTER_CRITICAL(&motionMux);
    demoRunning = true;
    demoDisarm = true;
    activeMotor = 0;
    remaining = demoCount * demoRepeats;
    pulseIndex = 0;
    motionComplete = false;
    timerAlarm(stepTimer, demoEvents[0].interval, false, 0);
    timerStart(stepTimer);
    portEXIT_CRITICAL(&motionMux);
    reply("OK demo: square/circle x3; XY only; auto-disable at end"); return;
  }
  if (!strcmp(args[0], "ARM") && count == 1) {
    if (!stepTimer) { reply("ERR motion timer unavailable"); return; }
    digitalWrite(Config::enablePin, LOW);
    armed = true;
    idleSinceMs = millis();
    reply("OK armed; all drivers enabled; idle timeout 30s");
    return;
  }
  if (!strcmp(args[0], "MAP") && count == 3) {
    int a = axisIndex(args[1]), m = motorIndex(args[2]);
    if (armed || a < 0 || m < 0) { reply("ERR disable first; MAP axis motor"); return; }
    for (int i = 0; i < 4; ++i) if (axisMotor[i] == m) axisMotor[i] = -1;
    axisMotor[a] = m;
    Positions::known = false;
    Positions::settled(false);
    reply("OK mapped (RAM only)"); return;
  }
  if (!strcmp(args[0], "INVERT") && count == 3) {
    int m = motorIndex(args[1]); long value;
    if (armed || m < 0 || !number(args[2], 0, 1, value)) {
      reply("ERR disable first; INVERT motor 0|1"); return;
    }
    inverted[m] = value;
    Positions::known = false;
    Positions::settled(false);
    reply("OK inverted (RAM only)"); return;
  }
  if (!strcmp(args[0], "JOG") && (count == 3 || count == 4)) {
    int m = motorIndex(args[1]);
    int a = axisIndex(args[1]);
    if (m < 0 && a >= 0) m = axisMotor[a];
    long steps, rate = m >= 0 ? min(Config::defaultRate, Config::maxRate[m]) : 0;
    if (m < 0 || !number(args[2], -Config::maxJogSteps[m], Config::maxJogSteps[m], steps)
        || steps == 0 || labs(steps) > long(Config::profileCapacity)
        || (count == 4 && !number(args[3], 1, Config::maxRate[m], rate))) {
      reply("ERR invalid jog, unmapped axis, or out of range"); return;
    }
    if (!armed) { reply("ERR disabled; ARM first"); return; }
    buildProfile(stepIntervals, labs(steps), rate, Config::acceleration[m]);
    if (!Positions::beforeMove()) { reply("ERR saving motion state"); return; }
    timerStop(stepTimer);
    timerWrite(stepTimer, 0);
    portENTER_CRITICAL(&motionMux);
    presetProfileActive = false;
    direction = steps > 0 ? 1 : -1;
    digitalWrite(Config::dirPins[m], (direction > 0) != inverted[m] ? HIGH : LOW);
    remaining = labs(steps);
    pulseIndex = 0;
    motionComplete = false;
    activeMotor = m;
    // From rest, the first interval also gives DIR/EN ample setup time.
    timerAlarm(stepTimer, stepIntervals[0], false, 0);
    timerStart(stepTimer);
    portEXIT_CRITICAL(&motionMux);
    reply("OK jogging"); return;
  }
  reply("ERR unknown command or arguments; HELP");
}

#include "web_control.h"

void serviceSerial() {
  // Bound work so a flooded serial link cannot starve stepping.
  for (int budget = 0; budget < 64 && Serial.available(); ++budget) {
    char c = Serial.read();
    if (c == '\n' && previousCR) { previousCR = false; continue; }
    previousCR = c == '\r';
    if (c == 3) {
      disableMotors(); WifiProvisioning::cancel(); memset(line, 0, sizeof(line));
      lineLength = 0; discardLine = false;
      Serial.println("OK cancelled; disabled");
    } else if (c == '!' && !WifiProvisioning::prompt) {
      disableMotors();
      lineLength = 0;
      discardLine = true; // Discard remainder through newline, preventing trailing ARM.
      Serial.println("OK stopped; send newline before next command");
    } else if (c == '\r' || c == '\n') {
      if (!discardLine) {
        line[lineLength] = 0;
        if (WifiProvisioning::prompt) WifiProvisioning::input(line); else command(line);
      }
      memset(line, 0, sizeof(line));
      lineLength = 0; discardLine = false;
    } else if (!discardLine) {
      if (c == '\b' || c == 127) { if (lineLength) line[--lineLength] = 0; continue; }
      if (c == '\0' || lineLength >= sizeof(line) - 1) {
        disableMotors(); WifiProvisioning::cancel(); memset(line, 0, sizeof(line)); lineLength = 0; discardLine = true;
        Serial.println("ERR invalid/overlong line; disabled");
      } else line[lineLength++] = c;
    }
  }
}

void setup() {
  digitalWrite(Config::enablePin, HIGH);
  pinMode(Config::enablePin, OUTPUT);
  for (int m = 0; m < 4; ++m) {
    digitalWrite(Config::stepPins[m], LOW);
    pinMode(Config::stepPins[m], OUTPUT);
    digitalWrite(Config::dirPins[m], LOW);
    pinMode(Config::dirPins[m], OUTPUT);
    axisMotor[m] = Config::axisMotor[m];
    inverted[m] = Config::inverted[m];
  }
  disableMotors();
  stepTimer = timerBegin(1000000);
  if (stepTimer) {
    timerStop(stepTimer);
    timerAttachInterrupt(stepTimer, &onStep);
  }
  Serial.begin(115200); // Native USB CDC; do not wait for a host.
  Serial.println("XYZA commissioning firmware v0.8; disabled; HELP");
  CrashLog::begin();
  disableReason = CrashLog::startupReason;
  Positions::begin();
  CutSettings::begin();
  WifiProvisioning::begin();
  WebControl::begin();
}

void loop() {
  // USB disconnect drops enable; no motion resumes on reconnection.
  if (!Serial && armed && !webArmed) { disableMotors(); disableReason = "USB disconnected"; }
  if (!Serial && WifiProvisioning::prompt) {
    WifiProvisioning::cancel(); memset(line, 0, sizeof(line)); lineLength = 0;
    discardLine = true;
  }
  finishMotion();
  serviceSerial();
  WifiProvisioning::service(armed);
  WebControl::service();
  if (armed && !webArmed && activeMotor < 0 && uint32_t(millis() - idleSinceMs) >= Config::armIdleMs) {
    disableMotors(); disableReason = "USB idle timeout"; Serial.println("OFF idle timeout");
  }
  delay(1);
}
