// Bench test for the u-bot drive axis as a closed-loop servo: NEMA 17 -> TMC2209
// (UART velocity mode, 1/8 microstep) -> 12:40 bevel pair -> output shaft, with
// an AS5600 magnetic encoder on the output shaft.
//
// Ported off STEP/DIR on 2026-08-30. The driver now runs its own step generator
// from the VACTUAL register and the MCU only updates a setpoint, which changes
// three things worth knowing before reading the rest:
//
//   no pulse count   nothing counts steps any more. The `steps` column is the
//                    integral of what was COMMANDED, and `slip` is its gap from
//                    the encoder -- which now carries clock error as well as
//                    real slip. Run 'c' before trusting either at speed.
//   clock gain       the TMC2209's internal oscillator is only good to ~+/-10%,
//                    so commanded velocity is off by that much until measured.
//                    calibrate() pins it down; see DRIVE_MECHANISM.md.
//   200 Hz loop      1 kHz was needed to feed a pulse generator. It is not
//                    needed to update a velocity, and one UART write is ~118 us.
//
// Measured in velocity mode, 2026-08-30:
//
//   clock gain     1.0158 on wheel A's driver -- 1.6% fast, baked in below
//   round trip     3 turns out and back, residual +0 counts, no steps lost
//   step response  0.5 turn move settles in 740 ms, peak 5333 sps, |slip| 26
//
// Measured on this axis under STEP/DIR, 2026-08-21, and still the reference:
//
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
//   TMC2209 UART -> D6/D7          wheel A AS5600 SCL -> D5 / GPIO23
//   both AS5600  -> 3V3, GND       wheel B AS5600 SDA -> D9 / GPIO20
//                                  wheel B AS5600 SCL -> D8 / GPIO19
//
// The UART is one wire: D6 (TX) through a 1k to D7 (RX), and the junction to
// the driver's PDN_UART -- which on a BTT V1.3 module is the pin silkscreened
// RX, pin 4. Pin 5 (TX) is an unpopulated alternate and will not answer.
//
// EN is active low, parked high, and hardwired on purpose: it is the killswitch
// that still works when the bus is down or the MCU is in reset. That matters
// more here than it did under STEP/DIR, because VACTUAL keeps the driver
// stepping whether or not anyone is talking to it. Motor power is separate:
// nothing turns until it is connected.

#include <AS5600.h>
#include <Wire.h>

#include "AS5600Soft.h"
#include "VelGen.h"
#include "StepperServo.h"

static const uint32_t SERIAL_BAUD  = 115200;
static const uint32_t SAMPLE_HZ    = 50;
static const uint32_t SAMPLE_US    = 1000000UL / SAMPLE_HZ;
static const uint32_t CONTROL_HZ   = 200;
static const uint32_t CONTROL_US   = 1000000UL / CONTROL_HZ;

static const uint8_t PIN_EN = D0;   // active low; the hardwired killswitch
static const uint8_t PIN_TX = D6;   // GPIO16, through 1k to the shared node
static const uint8_t PIN_RX = D7;   // GPIO17, on the node itself

// 250k is comfortably clear of the floor: writes fail at 57600 and below,
// because an 8-byte datagram takes longer than the driver's receive window.
static const uint32_t UART_BAUD   = 250000;
static const uint8_t  DRIVER_ADDR = 0;   // MS1=MS2=0

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

// Whether the driver's shaft bit has to be inverted for +velocity to make the
// encoder count up. A wiring fact, not a preference: run 'c' once and set it to
// what it says. This lives in GCONF now rather than on a DIR pin, so it reads
// back -- 'i' prints what the driver actually thinks.
static const bool SHAFT_INVERT = false;

// The TMC2209's internal oscillator, as a multiplier on commanded velocity.
// Measured on wheel A's driver 2026-08-30: 1.0158, i.e. it runs 1.6% fast --
// well inside the +/-10% the part allows. This is a property of the individual
// chip, so wheel B's driver will need its own; 'c' measures it and prints the
// number to bake in here.
static const float CLOCK_GAIN = 1.0158f;

static float stepsPerMotorRev() { return MOTOR_FULL_STEPS * microsteps; }
// Calibration times whole output revolutions, or the encoder's angle-dependent
// nonlinearity warps the answer. Three turns is 12288 counts.
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
    if (dt > 0) vel += (dt / (0.01f + dt)) * ((float)d / dt - vel);  // ~16 Hz
  }

  void zero() { counts = 0; }
  float turns() const { return (float)counts / StepperServo::COUNTS_PER_REV; }
  float tps() const { return vel / StepperServo::COUNTS_PER_REV; }
  uint32_t takeRecent() { uint32_t v = recentUs; recentUs = 0; return v; }
};

AS5600 enc;
AS5600Soft encB(PIN_B_SDA, PIN_B_SCL);
Tmc2209Uart tmc(Serial1, PIN_RX, PIN_TX);
VelGen gen(tmc, DRIVER_ADDR);
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
  Serial.printf("# EN=GPIO%u (active low), TMC2209 UART TX=GPIO%u RX=GPIO%u"
                " at %lu baud, address %u, AS5600 on SDA=GPIO%u SCL=GPIO%u\n",
                PIN_EN, PIN_TX, PIN_RX, (unsigned long)UART_BAUD,
                gen.address(), SDA, SCL);
  if (!gen.ok()) {
    Serial.println(F("# DRIVER NOT ANSWERING on the UART -- nothing will move"));
  }
  Serial.printf("# driver %s, loop %s, fault %s\n",
                gen.enabled() ? "ENABLED" : "disabled",
                servo.servoOn() ? "CLOSED" : "open",
                servo.faultName());
  Serial.printf("# shaft polarity %s (positive = encoder counts up),"
                " driver's GCONF.shaft reads %d\n",
                gen.inverted() ? "INVERTED" : "normal", gen.shaftBit());
  Serial.printf("# %.0f full steps x 1/%.0f x %.0f/%.0f gear = %.1f steps/out-rev"
                " vs %ld encoder counts\n",
                MOTOR_FULL_STEPS, microsteps, GEAR_OUT_TEETH, GEAR_MOTOR_TEETH,
                stepsPerOutRev(), (long)StepperServo::COUNTS_PER_REV);
  Serial.printf("# steps/count nominal %.6f, in use %.6f (%.2f%% off)\n",
                nominalStepsPerCount(), servo.stepsPerCount,
                100.0f * (servo.stepsPerCount / nominalStepsPerCount() - 1.0f));
  Serial.printf("# clock gain %.4f %s -- VACTUAL LSB %.4f steps/s,"
                " quantisation %.4f out turns/s\n",
                gen.clockGain(),
                gen.calibrated() ? "(measured this session)"
                                 : "(preset -- 'c' measures this driver)",
                VelGen::VACTUAL_LSB, VelGen::VACTUAL_LSB / stepsPerOutRev());
  Serial.printf("# pos %.4f turns  target %.4f  err %ld counts  slip %ld steps\n",
                servo.positionTurns(), servo.targetTurns(),
                (long)servo.errorCounts(), (long)servo.slipSteps());
  Serial.printf("# kp %.2f  vmax %.3f turns/s  accel %.2f turns/s^2  vmin %.1f steps/s"
                "  tol %ld counts  maxslip %ld steps\n",
                servo.kp, servo.vmaxTps, servo.accelTps2, servo.vminSps,
                (long)servo.tolCounts, (long)servo.slipLimit);
  Serial.printf("# step rate ceiling %.0f steps/s = %.2f out turns/s (a guard,"
                " not a hardware limit)\n",
                gen.maxRate(), gen.maxRate() / stepsPerOutRev());
  bool drvOk = false;
  uint32_t drv = gen.readReg(Tmc2209Uart::DRVSTATUS, &drvOk);
  Serial.printf("# driver VERSION 0x%02X, DRV_STATUS %s0x%08lX"
                " (standstill %d, overtemp warn %d, overtemp %d)\n",
                gen.version(), drvOk ? "" : "unread ", (unsigned long)drv,
                (int)((drv >> 31) & 1), (int)(drv & 1), (int)((drv >> 1) & 1));
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
  printColumns();
}

// The stream's column names. Printed at boot and again by 'i': a scope that
// attaches to an already-running board never saw the banner, and it indexes the
// stream by name, so this line is how it finds out what it is reading.
static void printColumns() {
  Serial.println(F("# t_ms,pos,target,err,vel,steps,rate,slip,enc,agc,status,flags,"
                   "bpos,bvel,benc,bagc,bstatus,busus"));
}

static void printHelp() {
  Serial.println(F("# keys:  e driver on/off   l loop on/off   c calibrate   d flip DIR"));
  Serial.println(F("#        z zero here      f clear fault   x stop+disable"));
  Serial.println(F("#        , . nudge -/+0.05 turn   < > nudge -/+0.25 turn"));
  Serial.println(F("#        w wiggle demo    p pause stream   i info   h help"));
  Serial.println(F("# words: <turns>|goto T   move T    spin SPS   jog STEPS"));
  Serial.println(F("#        kp K  vmax T/s  vmin SPS  accel T/s2  tol N  maxslip N"));
  Serial.println(F("#        ratio STEPS/COUNT   micro N   gain G   amp TURNS   secs S"));
}

static void printCal(const StepperServo::CalResult &r) {
  if (!r.ok) {
    Serial.printf("# calibrate FAILED: %s\n", r.note);
    return;
  }
  Serial.printf("# calibrate: %+ld counts in %.3f s at %.0f steps/s commanded,"
                " shaft polarity %s%s\n",
                (long)r.counts, r.seconds, r.sps,
                gen.inverted() ? "INVERTED" : "normal",
                r.flipped ? " (flipped from the default)" : " (default was right)");
  Serial.printf("# clock gain %.4f: asked %.0f steps/s, got %.0f -- %+.1f%%,"
                " which is the TMC2209's oscillator, not the gearing\n",
                r.clockGain, r.sps, r.sps * r.clockGain,
                100.0f * (r.clockGain - 1.0f));
  Serial.printf("# return leg %+ld counts against %+ld out, residual %+ld%s\n",
                (long)r.back, (long)r.counts, (long)r.residual,
                labs((long)r.residual) > 8
                    ? " -- steps were lost, check current and speed"
                    : " (no steps lost)");
  Serial.printf("# ratio held at %.6f steps/count: the gearing is exact, so the"
                " whole error is attributed to the clock\n",
                servo.stepsPerCount);
  if (fabsf(r.clockGain - CLOCK_GAIN) > 0.002f) {
    Serial.printf("# bake it in: set CLOCK_GAIN = %.4ff in test_servo.ino\n",
                  r.clockGain);
  }
  if (gen.inverted() != SHAFT_INVERT) {
    Serial.printf("# bake it in: set SHAFT_INVERT = %s in test_servo.ino\n",
                  gen.inverted() ? "true" : "false");
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
                    2.0f * stepsPerOutRev() * CAL_OUT_REVS / CAL_SPS + 1.5f);
      printCal(servo.calibrate(CAL_OUT_REVS, CAL_SPS, abortRequested));
      break;
    }
    case 'd':
      gen.flipInvert();
      servo.servoOn(false);
      servo.resyncSlip();
      Serial.printf("# shaft polarity now %s, loop opened\n",
                    gen.inverted() ? "INVERTED" : "normal");
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
      Serial.printf("# open-loop jog %ld commanded steps: encoder %+ld counts,"
                    " expected %+ld (%.1f%%), now %.4f turns\n",
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
    // Real now, not just bookkeeping: mstep_reg_select is set, so MRES in
    // CHOPCONF overrides MS1/MS2 and this actually changes the driver.
    if (arg && v >= 1) {
      if (!gen.setMicrosteps((uint16_t)v)) {
        Serial.printf("# 1/%.0f is not a TMC2209 setting (1 2 4 8 16 32 64 128 256)\n", v);
      } else {
        microsteps = v;
        servo.stepsPerCount = nominalStepsPerCount();
        servo.resyncSlip();
      }
    }
    Serial.printf("# 1/%u microstep -> %.6f steps/count (driver's MRES, not the pins;"
                  " it interpolates to 256 either way)\n",
                  gen.microsteps(), servo.stepsPerCount);
  }
  else if (matches(tok, "gain")) {
    if (arg) { gen.setClockGain(v); servo.resyncSlip(); }
    Serial.printf("# clock gain %.4f%s\n", gen.clockGain(),
                  gen.calibrated() ? "" : " (default -- 'c' measures it)");
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

  // Driver first, so EN is parked high before the bus is even opened.
  if (!gen.begin(PIN_EN, UART_BAUD, (uint16_t)microsteps)) {
    Serial.println(F("# TMC2209 did not answer over UART. Check, in this order:"));
    Serial.println(F("#   the wire is on module pin 4 (RX) -- pin 5 is unpopulated"));
    Serial.println(F("#   1k between D6 and D7, motor power on, VIO to 3V3"));
    Serial.println(F("# carrying on so the encoders still stream, but nothing"));
    Serial.println(F("# will move until the driver answers."));
  }
  gen.setInvert(SHAFT_INVERT);
  gen.presetClockGain(CLOCK_GAIN);

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
  Serial.println(F("# 'c' is not optional here: it measures the driver's clock, and"));
  Serial.println(F("# until it has run, commanded speed can be 10% off and slip reads high"));
  printColumns();
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
                (long)llround(gen.position()), gen.rate(), (long)servo.slipSteps(),
                servo.rawAngle(), agcA, statusA, flags,
                trackB.turns(), trackB.tps(), trackB.raw, agcB, statusB,
                (unsigned long)trackB.takeRecent());
}
