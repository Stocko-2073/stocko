#include <Arduino.h>
#include <errno.h>
#include <stdlib.h>
#include <string.h>
#include "config.h"
#include "motion_profile.h"
#include "demo_path.h"

int8_t axisMotor[4];
bool inverted[4];
bool armed = false;
int activeMotor = -1;
volatile long remaining = 0;
int direction = 1;
int64_t emitted[4] = {}; // Diagnostic pulse counts, never a machine position.
uint32_t idleSinceMs = 0;
hw_timer_t *stepTimer = nullptr;
portMUX_TYPE motionMux = portMUX_INITIALIZER_UNLOCKED;
uint32_t stepIntervals[Config::profileCapacity];
volatile size_t pulseIndex = 0;
volatile bool motionComplete = false;
DemoEvent demoEvents[demoCapacity];
size_t demoCount = 0;
bool demoRunning = false;
char line[96];
size_t lineLength = 0;
bool discardLine = false;

void disableMotors() {
  portENTER_CRITICAL(&motionMux);
  digitalWrite(Config::enablePin, HIGH);
  for (uint8_t pin : Config::stepPins) digitalWrite(pin, LOW);
  armed = false;
  activeMotor = -1;
  remaining = 0;
  motionComplete = false;
  demoRunning = false;
  portEXIT_CRITICAL(&motionMux);
  if (stepTimer) timerStop(stepTimer);
}

// Only precomputed integer intervals and pin operations in the interrupt.
// One-shot alarms avoid catch-up bursts after interrupt latency. The main loop
// can service USB or yield without adding a millisecond to every step.
void ARDUINO_ISR_ATTR onStep() {
  portENTER_CRITICAL_ISR(&motionMux);
  if (armed && activeMotor >= 0 && remaining > 0) {
    const uint64_t riseAt = timerRead(stepTimer);
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
    const int m = activeMotor;
    digitalWrite(Config::stepPins[m], HIGH);
    delayMicroseconds(Config::pulseUs);
    digitalWrite(Config::stepPins[m], LOW);
    emitted[m] += direction;
    --remaining;
    ++pulseIndex;
    if (remaining == 0) motionComplete = true;
    else timerAlarm(stepTimer, riseAt + stepIntervals[pulseIndex], false, 0);
  }
  portEXIT_CRITICAL_ISR(&motionMux);
}

void finishMotion() {
  portENTER_CRITICAL(&motionMux);
  const bool done = motionComplete;
  const bool demoDone = done && demoRunning;
  if (done) { motionComplete = false; activeMotor = -1; }
  portEXIT_CRITICAL(&motionMux);
  if (done) {
    timerStop(stepTimer);
    idleSinceMs = millis();
    if (demoDone) disableMotors();
    Serial.println("DONE");
  }
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

void command(char *input) {
  char *args[6];
  int count = 0;
  char *save;
  for (char *s = strtok_r(input, " \t", &save); s; s = strtok_r(nullptr, " \t", &save)) {
    if (count == 6) { Serial.println("ERR too many arguments"); return; }
    args[count++] = s;
  }
  if (!count) return;
  if (!strcmp(args[0], "STOP") || !strcmp(args[0], "OFF")) {
    disableMotors(); Serial.println("OK disabled"); return;
  }
  if (!strcmp(args[0], "STATUS") && count == 1) { status(); return; }
  if (!strcmp(args[0], "HELP") && count == 1) {
    Serial.println("HELP | STATUS | ARM | OFF | STOP | ! (immediate stop)");
    Serial.println("DEMO: XY square + circle, 3 cycles, 20x20 mm positive envelope; ARM first");
    Serial.println("MAP <X|Y|Z|A> <M0..M3> | INVERT <M0..M3> <0|1> (disabled only)");
    Serial.println("JOG <M0..M3|X|Y|Z|A> <signed nonzero pulses> [cruise pulses/sec]");
    Serial.println("Rate caps: M0/M1=3000, M2=1000, M3=2000; default 500 (clamped)");
    Serial.println("Per-jog caps: M0=1000, M1=2000, M2=6000, M3=500 pulses; no travel limits");
    Serial.println("No homing, physical coordinates, or cutting cycle. Mapping is RAM-only.");
    return;
  }
  if (activeMotor >= 0) { Serial.println("ERR busy; STOP or wait for DONE"); return; }
  if (!strcmp(args[0], "DEMO") && count == 1) {
    if (!armed) { Serial.println("ERR disabled; ARM first"); return; }
    if (axisMotor[0] != 0 || axisMotor[1] != 1 || inverted[0] || inverted[1]) {
      Serial.println("ERR DEMO requires commissioned X=M0 Y=M1, uninverted"); return;
    }
    demoCount = buildDemo(demoEvents);
    if (!demoCount) { disableMotors(); Serial.println("ERR demo profile"); return; }
    timerStop(stepTimer);
    timerWrite(stepTimer, 0);
    portENTER_CRITICAL(&motionMux);
    demoRunning = true;
    activeMotor = 0;
    remaining = demoCount * demoRepeats;
    pulseIndex = 0;
    motionComplete = false;
    timerAlarm(stepTimer, demoEvents[0].interval, false, 0);
    timerStart(stepTimer);
    portEXIT_CRITICAL(&motionMux);
    Serial.println("OK demo: square/circle x3; XY only; auto-disable at end"); return;
  }
  if (!strcmp(args[0], "ARM") && count == 1) {
    if (!stepTimer) { Serial.println("ERR motion timer unavailable"); return; }
    digitalWrite(Config::enablePin, LOW);
    armed = true;
    idleSinceMs = millis();
    Serial.println("OK armed; all drivers enabled; idle timeout 30s");
    return;
  }
  if (!strcmp(args[0], "MAP") && count == 3) {
    int a = axisIndex(args[1]), m = motorIndex(args[2]);
    if (armed || a < 0 || m < 0) { Serial.println("ERR disable first; MAP axis motor"); return; }
    for (int i = 0; i < 4; ++i) if (axisMotor[i] == m) axisMotor[i] = -1;
    axisMotor[a] = m;
    Serial.println("OK mapped (RAM only)"); return;
  }
  if (!strcmp(args[0], "INVERT") && count == 3) {
    int m = motorIndex(args[1]); long value;
    if (armed || m < 0 || !number(args[2], 0, 1, value)) {
      Serial.println("ERR disable first; INVERT motor 0|1"); return;
    }
    inverted[m] = value;
    Serial.println("OK inverted (RAM only)"); return;
  }
  if (!strcmp(args[0], "JOG") && (count == 3 || count == 4)) {
    int m = motorIndex(args[1]);
    int a = axisIndex(args[1]);
    if (m < 0 && a >= 0) m = axisMotor[a];
    long steps, rate = m >= 0 ? min(Config::defaultRate, Config::maxRate[m]) : 0;
    if (m < 0 || !number(args[2], -Config::maxJogSteps[m], Config::maxJogSteps[m], steps)
        || steps == 0 || labs(steps) > long(Config::profileCapacity)
        || (count == 4 && !number(args[3], 1, Config::maxRate[m], rate))) {
      Serial.println("ERR invalid jog, unmapped axis, or out of range"); return;
    }
    if (!armed) { Serial.println("ERR disabled; ARM first"); return; }
    buildProfile(stepIntervals, labs(steps), rate, Config::acceleration[m]);
    timerStop(stepTimer);
    timerWrite(stepTimer, 0);
    portENTER_CRITICAL(&motionMux);
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
    Serial.println("OK jogging"); return;
  }
  Serial.println("ERR unknown command or arguments; HELP");
}

void serviceSerial() {
  // Bound work so a flooded serial link cannot starve stepping.
  for (int budget = 0; budget < 64 && Serial.available(); ++budget) {
    char c = Serial.read();
    if (c == '!') {
      disableMotors();
      lineLength = 0;
      discardLine = true; // Discard remainder through newline, preventing trailing ARM.
      Serial.println("OK stopped; send newline before next command");
    } else if (c == '\r' || c == '\n') {
      if (!discardLine) { line[lineLength] = 0; command(line); }
      lineLength = 0; discardLine = false;
    } else if (!discardLine) {
      if (c == '\0' || lineLength >= sizeof(line) - 1) {
        disableMotors(); lineLength = 0; discardLine = true;
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
  Serial.println("XYZA commissioning firmware v0.3; disabled; HELP");
}

void loop() {
  // USB disconnect drops enable; no motion resumes on reconnection.
  if (!Serial && armed) disableMotors();
  finishMotion();
  serviceSerial();
  if (armed && activeMotor < 0 && uint32_t(millis() - idleSinceMs) >= Config::armIdleMs) {
    disableMotors(); Serial.println("OFF idle timeout");
  }
  delay(1);
}
