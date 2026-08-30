// Bench test for the u-bot drive axis as a closed-loop servo: NEMA 17 -> TMC2209
// (STEP/DIR, 1/8 microstep) -> 12:40 bevel pair -> output shaft, with an AS5600
// magnetic encoder on the output shaft.
//
// Follows on from test_encoder. Measured on this axis, 2026-08-21:
//
//   DIR polarity   LOW is the direction the encoder counts up (DIR_PLUS_LEVEL)
//   ratio          1.302083 steps/count, 0.000% off nominal over 3 output turns
//                  -- exactly 1/8 microstep and exactly 12:40, nothing to fudge
//   lost steps     none: 16000 steps out and back returned +0 counts
//   encoder        rock steady standing still (p-p 0 counts), but ~20 counts of
//                  angle-dependent nonlinearity around the turn, so calibration
//                  has to span whole output revolutions to be honest
//   speed ceiling  clean to 1.0 turns/s, marginal by 2.0, sheds steps at 2.76
//
// Wiring, XIAO ESP32-C6:
//   TMC2209 EN   -> D0 / GPIO0     wheel A AS5600 SDA -> D4 / GPIO22
//   TMC2209 STEP -> D1 / GPIO1     wheel A AS5600 SCL -> D5 / GPIO23
//   TMC2209 DIR  -> D2 / GPIO2     wheel B AS5600 SDA -> D9 / GPIO20
//   both AS5600  -> 3V3, GND       wheel B AS5600 SCL -> D8 / GPIO19
// EN is active low on the TMC2209, so the pin is parked high and the driver
// boots disabled. Motor power is separate: nothing turns until it is connected.
//
// Wheel B is an encoder only: there is one driver on the bench, so only wheel A
// is a servo. B rides a bit-banged I2C bus because the AS5600's address is fixed
// at 0x36 and the C6's second I2C controller is LP_I2C, which can only live on
// GPIO6/7 -- pins the XIAO does not break out. See AS5600Soft.h.
//
// Start here:
//   e        enable the driver
//   c        calibrate -- probes one motor turn and reports DIR polarity + ratio
//   l        close the loop
//   0.5      go to half an output turn (a bare number is a target in turns)
//
// One CSV sample per line at SAMPLE_HZ for plot.py; '#' lines are notes. The
// column header is printed once at boot and plot.py indexes by name, so adding
// a column here does not need a matching edit over there:
//   t_ms,pos,target,err,vel,steps,rate,slip,enc,agc,status,flags,
//   bpos,bvel,benc,bagc,bstatus,busus

#include <AS5600.h>
#include <Wire.h>

#include "AS5600Soft.h"
#include "StepGen.h"
#include "StepperServo.h"

static const uint32_t SERIAL_BAUD  = 115200;
static const uint32_t SAMPLE_HZ    = 50;
static const uint32_t SAMPLE_US    = 1000000UL / SAMPLE_HZ;
static const uint32_t CONTROL_HZ   = 1000;
static const uint32_t CONTROL_US   = 1000000UL / CONTROL_HZ;

static const uint8_t PIN_EN   = D0;
static const uint8_t PIN_STEP = D1;
static const uint8_t PIN_DIR  = D2;

// Wheel B's encoder, on the bit-banged bus.
static const uint8_t PIN_B_SDA = D9;  // GPIO20
static const uint8_t PIN_B_SCL = D8;  // GPIO19

// Drivetrain, from u-bot.scad: drive_teeth=12 on the motor, wheel_teeth=40 on
// the output shaft, so the motor turns 40/12 times per output turn.
static const float MOTOR_FULL_STEPS = 200.0f;  // 1.8 deg NEMA 17
static const float GEAR_MOTOR_TEETH = 12.0f;
static const float GEAR_OUT_TEETH   = 40.0f;
static const float GEAR_RATIO       = GEAR_OUT_TEETH / GEAR_MOTOR_TEETH;
static float microsteps = 8.0f;  // TMC2209 with MS1/MS2 low

// Which DIR level drives the output shaft the way the encoder counts up. This
// is a wiring fact, not a preference: run 'c' once and set it to what it says.
// Measured on this axis 2026-08-21: LOW, three calibration runs agreeing.
static const bool DIR_PLUS_LEVEL = false;

static float stepsPerMotorRev() { return MOTOR_FULL_STEPS * microsteps; }
// Calibration probes whole output revolutions, or the encoder's angle-dependent
// nonlinearity warps the ratio. At 1/8 and 12:40 that is exactly 16000 steps.
static const int CAL_OUT_REVS = 3;
static const float CAL_SPS = 1500.0f;

// Measured ceiling for this axis: clean to 1.0 turns/s, marginal by 2.0, and at
// 2.76 turns/s the motor sheds steps. Commands clamp here so a fat-fingered
// vmax cannot walk the axis off the end of its torque curve.
static const float VMAX_LIMIT = 2.0f;    // output turns/s
static const float ACCEL_LIMIT = 20.0f;  // output turns/s^2
static float stepsPerOutRev() { return stepsPerMotorRev() * GEAR_RATIO; }
static float nominalStepsPerCount() { return stepsPerOutRev() / StepperServo::COUNTS_PER_REV; }

// STATUS register bits, as in test_encoder.ino.
static const uint8_t MAGNET_HIGH   = 0x08;
static const uint8_t MAGNET_LOW    = 0x10;
static const uint8_t MAGNET_DETECT = 0x20;

// flags column, so plot.py can shade the run without parsing prose.
static const uint8_t F_DRIVER = 0x01;
static const uint8_t F_LOOP   = 0x02;
static const uint8_t F_AT     = 0x04;
static const uint8_t F_FAULT  = 0x08;
static const uint8_t F_WIGGLE = 0x10;
static const uint8_t F_ENCB   = 0x20;  // wheel B's encoder answered this tick

// Multiturn tracking for an encoder with no servo behind it yet: the same
// wrap-and-accumulate StepperServo::readEncoder does, without the control loop.
// Wheel B gets this until it has a driver of its own.
struct EncoderTrack {
  int32_t counts = 0;      // multiturn, output shaft
  float vel = 0;           // counts/s, filtered the same way the servo does
  uint16_t raw = 0;
  bool ok = false;
  uint32_t worstUs = 0;    // worst read since boot
  uint32_t recentUs = 0;   // worst since the last sample line, then reset
  uint32_t retryMs = 0;

  void begin(AS5600 &e) {
    raw = e.readAngle();
    ok = e.lastError() == AS5600_OK;
    counts = 0;
  }

  void update(AS5600 &e, float dt) {
    // A missing or miswired encoder must not cost the control loop a
    // millisecond every tick: with no pull-ups SCL never rises and each read
    // burns the full stretch timeout. Back off to 10 Hz until it answers.
    if (!ok && (int32_t)(millis() - retryMs) < 0) return;

    uint32_t t0 = micros();
    uint16_t r = e.readAngle();
    uint32_t took = micros() - t0;
    if (took > worstUs) worstUs = took;
    if (took > recentUs) recentUs = took;

    ok = e.lastError() == AS5600_OK;
    if (!ok) {
      retryMs = millis() + 100;
      return;  // hold position rather than jump on a dropped byte
    }
    int16_t d = (int16_t)((r - raw) & 0x0FFF);
    if (d > 2048) d -= 4096;
    raw = r;
    counts += d;
    if (dt > 0) vel += 0.1f * ((float)d / dt - vel);  // ~17 Hz at 1 kHz
  }

  void zero() { counts = 0; }
  float turns() const { return (float)counts / StepperServo::COUNTS_PER_REV; }
  float tps() const { return vel / StepperServo::COUNTS_PER_REV; }
  uint32_t takeRecent() { uint32_t v = recentUs; recentUs = 0; return v; }
};

AS5600 enc;
AS5600Soft encB(PIN_B_SDA, PIN_B_SCL);
StepGen gen;
StepperServo servo(enc, gen);
EncoderTrack trackB;

// Magnet health is polled slowly and cached. It cannot change fast, and on the
// bit-banged bus each of these reads costs as much as an angle read does -- at
// the sample rate they would be the most expensive thing in the loop.
static const uint32_t HEALTH_US = 500000;
static uint32_t nextHealth  = 0;
static uint8_t  agcA = 0, statusA = 0, agcB = 0, statusB = 0;

static bool     streaming   = true;
static uint32_t nextSample  = 0;
static uint32_t nextControl = 0;
static uint32_t lastControl = 0;

// Square-wave demo: the cleanest way to look at a step response.
static bool  wiggle     = false;
static float wiggleAmp  = 1.0f;   // output turns
static float wiggleSecs = 4.0f;   // full period
static uint32_t wiggleT0 = 0;
static bool  wiggleHigh = false;
static float wiggleBase = 0;

static char line[64];
static uint8_t lineLen = 0;

// ---------------------------------------------------------------- reporting

// Refresh the cached magnet health for both encoders.
static void pollHealth() {
  statusA = enc.readStatus();
  agcA = enc.readAGC();
  statusB = encB.readStatus();
  agcB = encB.readAGC();
}

static const char *magnetText(uint8_t status) {
  if (!(status & MAGNET_DETECT)) return "none";
  if (status & MAGNET_LOW) return "too weak (magnet too far / off-axis)";
  if (status & MAGNET_HIGH) return "too strong (magnet too close)";
  return "ok";
}

static void printInfo() {
  Serial.printf("# EN=GPIO%u STEP=GPIO%u DIR=GPIO%u (EN active low),"
                " AS5600 on SDA=GPIO%u SCL=GPIO%u\n",
                PIN_EN, PIN_STEP, PIN_DIR, SDA, SCL);
  Serial.printf("# driver %s, loop %s, fault %s\n",
                gen.enabled() ? "ENABLED" : "disabled",
                servo.servoOn() ? "CLOSED" : "open",
                servo.faultName());
  Serial.printf("# DIR positive level %s (positive = encoder counts up),"
                " pin is %s now\n",
                gen.dirPlusLevel() ? "HIGH" : "LOW",
                gen.dirPinLevel() ? "HIGH" : "LOW");
  Serial.printf("# %.0f full steps x 1/%.0f x %.0f/%.0f gear = %.1f steps/out-rev"
                " vs %ld encoder counts\n",
                MOTOR_FULL_STEPS, microsteps, GEAR_OUT_TEETH, GEAR_MOTOR_TEETH,
                stepsPerOutRev(), (long)StepperServo::COUNTS_PER_REV);
  Serial.printf("# steps/count nominal %.6f, in use %.6f (%.2f%% off)\n",
                nominalStepsPerCount(), servo.stepsPerCount,
                100.0f * (servo.stepsPerCount / nominalStepsPerCount() - 1.0f));
  Serial.printf("# pos %.4f turns  target %.4f  err %ld counts  slip %ld steps\n",
                servo.positionTurns(), servo.targetTurns(),
                (long)servo.errorCounts(), (long)servo.slipSteps());
  Serial.printf("# kp %.2f  vmax %.3f turns/s  accel %.2f turns/s^2  vmin %.1f steps/s"
                "  tol %ld counts  maxslip %ld steps\n",
                servo.kp, servo.vmaxTps, servo.accelTps2, servo.vminSps,
                (long)servo.tolCounts, (long)servo.slipLimit);
  Serial.printf("# step rate ceiling %.0f steps/s = %.2f out turns/s\n",
                gen.maxRate(), gen.maxRate() / stepsPerOutRev());
  Serial.printf("# wheel A magnet %s, agc %u (0..128 on 3V3, aim for ~64),"
                " magnitude %u\n",
                magnetText(statusA), agcA, enc.readMagnitude());
  Serial.printf("# wheel B on bit-banged I2C SDA=GPIO%u SCL=GPIO%u: %s,"
                " magnet %s, agc %u\n",
                PIN_B_SDA, PIN_B_SCL,
                trackB.ok ? "responding" : "NOT RESPONDING",
                magnetText(statusB), agcB);
  Serial.printf("# wheel B pos %.4f turns, worst soft-bus read %lu us"
                " (%.0f%% of the %lu us control tick)\n",
                trackB.turns(), (unsigned long)trackB.worstUs,
                100.0f * trackB.worstUs / CONTROL_US, (unsigned long)CONTROL_US);
}

static void printHelp() {
  Serial.println(F("# keys:  e driver on/off   l loop on/off   c calibrate   d flip DIR"));
  Serial.println(F("#        z zero here      f clear fault   x stop+disable"));
  Serial.println(F("#        , . nudge -/+0.05 turn   < > nudge -/+0.25 turn"));
  Serial.println(F("#        w wiggle demo    p pause stream   i info   h help"));
  Serial.println(F("# words: <turns>|goto T   move T    spin SPS   jog STEPS"));
  Serial.println(F("#        kp K  vmax T/s  vmin SPS  accel T/s2  tol N  maxslip N"));
  Serial.println(F("#        ratio STEPS/COUNT   micro N   amp TURNS   secs S"));
}

static void printCal(const StepperServo::CalResult &r) {
  if (!r.ok) {
    Serial.printf("# calibrate FAILED: %s\n", r.note);
    return;
  }
  Serial.printf("# calibrate: %ld steps -> %+ld counts, DIR positive level is %s%s\n",
                (long)r.steps, (long)r.counts,
                gen.dirPlusLevel() ? "HIGH" : "LOW",
                r.flipped ? " (flipped from the default)" : " (default was right)");
  float outRev = stepsPerOutRev();
  float measured = r.stepsPerCount * StepperServo::COUNTS_PER_REV;
  Serial.printf("# measured %.6f steps/count = %.1f steps/out-rev"
                " (nominal %.1f, %.3f%% off)\n",
                r.stepsPerCount, measured, outRev, 100.0f * (measured / outRev - 1.0f));
  Serial.printf("# round trip came back %+ld counts%s\n", (long)r.residual,
                labs((long)r.residual) > 8
                    ? " -- steps were lost, check current and speed"
                    : " (no steps lost)");
  Serial.printf("# implies %.2f microsteps at 12:40, or %.3f:1 gear at 1/%.0f\n",
                measured / (MOTOR_FULL_STEPS * GEAR_RATIO),
                measured / stepsPerMotorRev(), microsteps);
  if (gen.dirPlusLevel() != DIR_PLUS_LEVEL) {
    Serial.printf("# bake it in: set DIR_PLUS_LEVEL = %s in test_servo.ino\n",
                  gen.dirPlusLevel() ? "true" : "false");
  }
}

// ---------------------------------------------------------------- commands

// Polled by the blocking calibration/jog moves: any keystroke is an abort.
static bool abortRequested() {
  if (!Serial.available()) return false;
  Serial.read();
  return true;
}

static void panicStop() {
  wiggle = false;
  servo.enableDriver(false);
  Serial.println(F("# stopped, driver disabled"));
}

static void doImmediate(char c) {
  switch (c) {
    case 'e': {
      bool on = !gen.enabled();
      servo.enableDriver(on);
      if (on) delay(20);  // let the TMC2209 come out of standby before stepping
      servo.resyncSlip();
      Serial.printf("# driver %s\n", on ? "ENABLED" : "disabled");
      break;
    }
    case 'l': {
      if (!gen.enabled()) { Serial.println(F("# enable the driver first (e)")); break; }
      bool on = !servo.servoOn();
      servo.servoOn(on);
      Serial.printf("# loop %s, holding %.4f turns\n",
                    on ? "CLOSED" : "open", servo.targetTurns());
      break;
    }
    case 'c': {
      wiggle = false;
      uint8_t st = enc.readStatus();
      if (!(st & MAGNET_DETECT)) {
        Serial.println(F("# no magnet detected -- fix the encoder before calibrating"));
        break;
      }
      if (st & (MAGNET_LOW | MAGNET_HIGH)) {
        Serial.printf("# WARNING magnet %s (agc %u) -- ratio may be off\n",
                      magnetText(st), enc.readAGC());
      }
      Serial.printf("# calibrating: %d output turns out and back at %.0f steps/s,"
                    " ~%.0f s (any key aborts)...\n",
                    CAL_OUT_REVS, CAL_SPS,
                    2.0f * stepsPerOutRev() * CAL_OUT_REVS / CAL_SPS);
      printCal(servo.calibrate((int32_t)lroundf(stepsPerOutRev() * CAL_OUT_REVS),
                               CAL_SPS, abortRequested));
      break;
    }
    case 'd':
      gen.flipDirPlusLevel();
      servo.servoOn(false);
      servo.resyncSlip();
      Serial.printf("# DIR positive level now %s, loop opened\n",
                    gen.dirPlusLevel() ? "HIGH" : "LOW");
      break;
    case 'z':
      servo.zeroHere();
      trackB.zero();
      wiggleBase = 0;
      Serial.println(F("# both wheels zeroed here"));
      break;
    case 'f':
      servo.clearFault();
      servo.resyncSlip();
      Serial.println(F("# fault cleared"));
      break;
    case 'x': panicStop(); break;
    case ',': servo.moveByTurns(-0.05f); break;
    case '.': servo.moveByTurns(+0.05f); break;
    case '<': servo.moveByTurns(-0.25f); break;
    case '>': servo.moveByTurns(+0.25f); break;
    case 'w':
      wiggle = !wiggle;
      if (wiggle) {
        wiggleBase = servo.targetTurns();
        wiggleT0 = millis();
        wiggleHigh = false;
      }
      Serial.printf("# wiggle %s (%.3f turns every %.1f s from %.3f)\n",
                    wiggle ? "on" : "off", wiggleAmp, wiggleSecs, wiggleBase);
      break;
    case 'p':
      streaming = !streaming;
      Serial.printf("# %s\n", streaming ? "streaming" : "paused");
      if (streaming) nextSample = micros();
      break;
    case 'i':
      pollHealth();  // an explicit ask deserves a fresh read, not the cache
      printInfo();
      break;
    case 'h':
    case '?': printHelp(); break;
    default: Serial.printf("# unknown key '%c', h for help\n", c); break;
  }
}

static bool matches(const char *tok, const char *name) { return strcmp(tok, name) == 0; }

// Held to the measured envelope rather than trusted: past it the motor sheds
// steps, and the loop only finds out after the fact.
static float clampTune(float v, float limit, const char *name, const char *unit) {
  if (v <= limit) return v;
  Serial.printf("# %s clamped to the measured limit %.2f %s (asked %.2f)\n",
                name, limit, unit, v);
  return limit;
}

static void doWord(char *buf) {
  char *tok = strtok(buf, " \t");
  if (!tok) return;
  char *arg = strtok(nullptr, " \t");
  float v = arg ? strtof(arg, nullptr) : 0;

  if (isdigit((unsigned char)tok[0]) || tok[0] == '.') {
    servo.moveToTurns(strtof(tok, nullptr));
    Serial.printf("# goto %.4f turns\n", servo.targetTurns());
    return;
  }
  if (matches(tok, "goto") || matches(tok, "move") || matches(tok, "spin") ||
      matches(tok, "jog")) {
    if (!arg) { Serial.printf("# %s needs a value\n", tok); return; }
    if (matches(tok, "goto")) servo.moveToTurns(v);
    else if (matches(tok, "move")) servo.moveByTurns(v);
    else if (matches(tok, "spin")) {
      if (!gen.enabled()) { Serial.println(F("# enable the driver first (e)")); return; }
      wiggle = false;
      servo.spin(v);
      Serial.printf("# open-loop spin %.1f steps/s = %.3f out turns/s\n",
                    v, v / stepsPerOutRev());
      return;
    } else {
      if (!gen.enabled()) { Serial.println(F("# enable the driver first (e)")); return; }
      wiggle = false;
      int32_t n = (int32_t)v;
      int32_t before = servo.positionCounts();
      const float jogSps = 500.0f;
      servo.jogSteps(n, jogSps);
      servo.pumpEncoder((uint32_t)(2000.0f * fabsf(v) / jogSps) + 1000, 150,
                        abortRequested);
      int32_t moved = servo.positionCounts() - before;
      int32_t want = (int32_t)((float)n / servo.stepsPerCount);
      Serial.printf("# open-loop jog %ld steps: encoder %+ld counts, expected %+ld"
                    " (%.1f%%), now %.4f turns\n",
                    (long)n, (long)moved, (long)want,
                    want ? 100.0f * (float)moved / (float)want : 0.0f,
                    servo.positionTurns());
      return;
    }
    Serial.printf("# target %.4f turns\n", servo.targetTurns());
    return;
  }

  if (matches(tok, "kp")) { if (arg) servo.kp = v; Serial.printf("# kp %.3f\n", servo.kp); }
  else if (matches(tok, "vmax")) { if (arg) servo.vmaxTps = clampTune(v, VMAX_LIMIT, "vmax", "turns/s"); Serial.printf("# vmax %.3f turns/s (%.0f steps/s)\n", servo.vmaxTps, servo.vmaxTps * stepsPerOutRev()); }
  else if (matches(tok, "vmin")) { if (arg) servo.vminSps = v; Serial.printf("# vmin %.1f steps/s\n", servo.vminSps); }
  else if (matches(tok, "accel")) { if (arg) servo.accelTps2 = clampTune(v, ACCEL_LIMIT, "accel", "turns/s^2"); Serial.printf("# accel %.3f turns/s^2\n", servo.accelTps2); }
  else if (matches(tok, "tol")) { if (arg) servo.tolCounts = (int32_t)v; Serial.printf("# tol %ld counts (%.3f deg out)\n", (long)servo.tolCounts, servo.tolCounts * 360.0f / StepperServo::COUNTS_PER_REV); }
  else if (matches(tok, "maxslip")) { if (arg) servo.slipLimit = (int32_t)v; Serial.printf("# maxslip %ld steps\n", (long)servo.slipLimit); }
  else if (matches(tok, "ratio")) { if (arg) { servo.stepsPerCount = v; servo.resyncSlip(); } Serial.printf("# ratio %.6f steps/count\n", servo.stepsPerCount); }
  else if (matches(tok, "micro")) {
    if (arg && v >= 1) { microsteps = v; servo.stepsPerCount = nominalStepsPerCount(); servo.resyncSlip(); }
    Serial.printf("# 1/%.0f microstep -> %.6f steps/count nominal\n", microsteps, servo.stepsPerCount);
  }
  else if (matches(tok, "amp")) { if (arg) wiggleAmp = v; Serial.printf("# wiggle amplitude %.3f turns\n", wiggleAmp); }
  else if (matches(tok, "secs")) { if (arg) wiggleSecs = fmaxf(0.2f, v); Serial.printf("# wiggle period %.2f s\n", wiggleSecs); }
  else { Serial.printf("# unknown command '%s', h for help\n", tok); }
}

// A key acts the moment it arrives, but only when nothing is half-typed --
// otherwise it is a character of a word command and waits for the newline.
static const char *IMMEDIATE = "elcdzfxwpih?,.<>";

static void handleSerial() {
  while (Serial.available()) {
    int c = Serial.read();
    if (c == '\r' || c == '\n') {
      if (lineLen) {
        line[lineLen] = 0;
        doWord(line);
        lineLen = 0;
      }
      continue;
    }
    if (lineLen == 0 && c > ' ' && strchr(IMMEDIATE, c)) {
      doImmediate((char)c);
      continue;
    }
    if (lineLen == 0 && c == ' ') continue;
    if (lineLen < sizeof(line) - 1) line[lineLen++] = (char)c;
  }
}

// ---------------------------------------------------------------- main

void setup() {
  Serial.begin(SERIAL_BAUD);
  uint32_t start = millis();
  while (!Serial && (millis() - start) < 2000) delay(10);

  // Driver first, so EN is parked high before anything else runs.
  gen.begin(PIN_EN, PIN_STEP, PIN_DIR);
  gen.setDirPlusLevel(DIR_PLUS_LEVEL);

  Wire.begin(SDA, SCL);
  Wire.setClock(400000);
  enc.begin();
  enc.setDirection(AS5600_CLOCK_WISE);

  uint32_t waited = 0;
  while (!enc.isConnected()) {
    if (waited % 1000 == 0) {
      Serial.println(F("# no AS5600 at 0x36 -- check SDA/D4, SCL/D5, 3V3, GND"));
    }
    delay(100);
    waited += 100;
  }

  // Wheel B is not fatal: it has no driver yet, so the bench is still useful
  // without it. Say so once and carry on.
  bool bOk = encB.begin();
  encB.setDirection(AS5600_CLOCK_WISE);
  if (!bOk) {
    Serial.printf("# no AS5600 answering on the bit-banged bus (SDA=GPIO%u,"
                  " SCL=GPIO%u) -- check the wiring and the 4.7k pull-ups\n",
                  PIN_B_SDA, PIN_B_SCL);
  }

  servo.stepsPerCount = nominalStepsPerCount();
  servo.begin();
  trackB.begin(encB);
  pollHealth();

  printInfo();
  printHelp();
  Serial.println(F("# driver starts disabled -- 'e' to enable, then 'c' to calibrate"));
  Serial.println(F("# t_ms,pos,target,err,vel,steps,rate,slip,enc,agc,status,flags,"
                   "bpos,bvel,benc,bagc,bstatus,busus"));
  nextSample = micros();
  nextControl = lastControl = micros();
  nextHealth = micros() + HEALTH_US;
}

static void runWiggle() {
  if (!wiggle) return;
  if (millis() - wiggleT0 < (uint32_t)(wiggleSecs * 500.0f)) return;
  wiggleT0 = millis();
  wiggleHigh = !wiggleHigh;
  servo.moveToTurns(wiggleBase + (wiggleHigh ? wiggleAmp : 0.0f));
}

void loop() {
  handleSerial();

  // Control loop on its own clock, with the real elapsed time so a late tick
  // does not corrupt the velocity estimate or the slew limit.
  if ((int32_t)(micros() - nextControl) >= 0) {
    nextControl += CONTROL_US;
    if ((int32_t)(micros() - nextControl) > (int32_t)CONTROL_US) nextControl = micros() + CONTROL_US;
    uint32_t now = micros();
    float dt = (float)(now - lastControl) * 1e-6f;
    lastControl = now;
    if (dt > 0.05f) dt = 0.05f;  // resync after a USB stall
    servo.update(dt);
    trackB.update(encB, dt);
    runWiggle();
  }

  if ((int32_t)(micros() - nextHealth) >= 0) {
    nextHealth = micros() + HEALTH_US;
    pollHealth();
  }

  if (!streaming) return;
  if ((int32_t)(micros() - nextSample) < 0) return;
  nextSample += SAMPLE_US;
  if ((int32_t)(micros() - nextSample) > (int32_t)SAMPLE_US) nextSample = micros() + SAMPLE_US;

  uint8_t flags = 0;
  if (gen.enabled()) flags |= F_DRIVER;
  if (servo.servoOn()) flags |= F_LOOP;
  if (servo.atTarget()) flags |= F_AT;
  if (servo.fault() != StepperServo::FAULT_NONE) flags |= F_FAULT;
  if (wiggle) flags |= F_WIGGLE;
  if (trackB.ok) flags |= F_ENCB;

  static uint8_t lastFault = StepperServo::FAULT_NONE;
  if (servo.fault() != lastFault) {
    lastFault = servo.fault();
    if (lastFault != StepperServo::FAULT_NONE) {
      Serial.printf("# FAULT: %s (slip %ld steps) -- loop opened, f to clear\n",
                    servo.faultName(), (long)servo.slipSteps());
    }
  }

  Serial.printf("%lu,%.4f,%.4f,%ld,%.3f,%ld,%.1f,%ld,%u,%u,0x%02X,0x%02X,"
                "%.4f,%.3f,%u,%u,0x%02X,%lu\n",
                millis(), servo.positionTurns(), servo.targetTurns(),
                (long)servo.errorCounts(), servo.velocityTps(),
                (long)gen.position(), gen.rate(), (long)servo.slipSteps(),
                servo.rawAngle(), agcA, statusA, flags,
                trackB.turns(), trackB.tps(), trackB.raw, agcB, statusB,
                (unsigned long)trackB.takeRecent());
}
