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
#include "Demo.h"
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
static const uint32_t UART_BAUD = 250000;

// Both drivers share the bus and are told apart by MS1/MS2, which UART mode
// frees up for exactly this: mstep_reg_select puts microstepping in CHOPCONF,
// so the pins carry nothing but the address. Wheel B's MS1 is jumpered to VIO
// and the driver confirms it -- IOIN reads MS1=1 at address 1.
//
// Address 1 answers at 250k and 500k but not at 115200 with two drivers on the
// line, which is a second reason to stay up here.
static const uint8_t ADDR_A = 0;   // MS1=0 MS2=0
static const uint8_t ADDR_B = 1;   // MS1=1 MS2=0

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
// Wheel B is the mirror image of A -- other side of the robot, so the bevel
// pair drives it the opposite way -- and its magnet went in at an unknown
// orientation. Both land as the same single bit, so 'c' settles them together
// without needing to know which one flipped.
static const bool SHAFT_INVERT_A = false;
static const bool SHAFT_INVERT_B = true;    // measured 2026-08-31: mirrored, as expected

// The TMC2209's internal oscillator, as a multiplier on commanded velocity.
// Measured on wheel A's driver 2026-08-30: 1.0158, i.e. it runs 1.6% fast --
// well inside the +/-10% the part allows. This is a property of the individual
// chip, so wheel B's driver will need its own; 'c' measures it and prints the
// number to bake in here.
static const float CLOCK_GAIN_A = 1.0158f;
static const float CLOCK_GAIN_B = 1.0091f;  // measured 2026-08-31, 0.9% fast

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
static const uint8_t F_DEMO   = 0x40;  // the scripted demo run is driving
static const uint8_t F_BFAULT = 0x80;  // wheel B faulted; the rest describe A

AS5600 encA;
AS5600Soft encB(PIN_B_SDA, PIN_B_SCL);
Tmc2209Uart tmc(Serial1, PIN_RX, PIN_TX);

// One drive axis: a driver on the shared bus, the encoder on its output shaft,
// and the loop between them. The two differ only in address, shaft polarity and
// the clock gain measured for that individual chip -- everything else about
// them is the same mechanism built twice.
//
// EN is deliberately not in here. It is one pin for both drivers, so the sketch
// owns it (enableDrivers below) and no Wheel can disagree with the other about
// what the hardware is doing.
struct Wheel {
  const char *name;
  VelGen gen;
  StepperServo servo;
  AS5600 &enc;
  uint8_t agc = 0;
  uint8_t status = 0;

  Wheel(const char *n, uint8_t addr, AS5600 &e)
      : name(n), gen(tmc, addr), servo(e, gen), enc(e) {}
};

Wheel wheelA("A", ADDR_A, encA);
Wheel wheelB("B", ADDR_B, encB);
Wheel *const wheels[] = {&wheelA, &wheelB};
static const uint8_t NWHEELS = sizeof(wheels) / sizeof(wheels[0]);

// Which wheel the single-axis commands act on. Bring-up is inherently one wheel
// at a time -- you cannot calibrate a polarity you are commanding in pairs.
Wheel *sel = &wheelA;

Demo demo;

// Magnet health is polled slowly and cached. It cannot change fast, and on the
// bit-banged bus each of these reads costs as much as an angle read does -- at
// the sample rate they would be the most expensive thing in the loop.
static const uint32_t HEALTH_US = 500000;
static uint32_t nextHealth  = 0;
// Magnet health lives on each Wheel now; this only paces the polling.

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
  for (uint8_t i = 0; i < NWHEELS; i++) {
    wheels[i]->status = wheels[i]->enc.readStatus();
    wheels[i]->agc = wheels[i]->enc.readAGC();
  }
}

// EN is one pin for both drivers, so energising is all-or-nothing in hardware.
// Every driver's VACTUAL is zeroed BEFORE the pin drops: the register survives
// an MCU reset even though the power stage was off, and one live velocity would
// lurch the whole robot the instant it is energised. Disabling runs the other
// way round -- cut the power stage first, tidy up after.
static void enableDrivers(bool on) {
  if (on) {
    for (uint8_t i = 0; i < NWHEELS; i++) wheels[i]->gen.setEnabled(true);
    digitalWrite(PIN_EN, LOW);
  } else {
    digitalWrite(PIN_EN, HIGH);
    for (uint8_t i = 0; i < NWHEELS; i++) wheels[i]->servo.enableDriver(false);
  }
}

static bool driversEnabled() { return wheelA.gen.enabled(); }

static const char *magnetText(uint8_t status) {
  if (!(status & MAGNET_DETECT)) return "none";
  if (status & MAGNET_LOW) return "too weak (magnet too far / off-axis)";
  if (status & MAGNET_HIGH) return "too strong (magnet too close)";
  return "ok";
}

static void printWheel(uint8_t idx) {
  Wheel *w = wheels[idx];
  Serial.printf("# --- wheel %s, driver address %u %s%s---\n",
                w->name, w->gen.address(),
                w->gen.ok() ? "" : "NOT ANSWERING ",
                w == sel ? "[selected] " : "");
  Serial.printf("#   loop %s, fault %s\n",
                w->servo.servoOn() ? "CLOSED" : "open", w->servo.faultName());
  Serial.printf("#   shaft polarity %s (positive = encoder counts up),"
                " GCONF.shaft reads %d\n",
                w->gen.inverted() ? "INVERTED" : "normal", w->gen.shaftBit());
  Serial.printf("#   clock gain %.4f %s\n", w->gen.clockGain(),
                w->gen.calibrated() ? "(measured this session)"
                                    : "(preset -- 'c' measures this driver)");
  Serial.printf("#   pos %.4f turns  target %.4f  err %ld counts  slip %ld steps\n",
                w->servo.positionTurns(), w->servo.targetTurns(),
                (long)w->servo.errorCounts(), (long)w->servo.slipSteps());
  Serial.printf("#   ratio %.6f steps/count  kp %.2f  vmax %.3f turns/s"
                "  accel %.2f turns/s^2  tol %ld  maxslip %ld\n",
                w->servo.stepsPerCount, w->servo.kp, w->servo.vmaxTps,
                w->servo.accelTps2, (long)w->servo.tolCounts,
                (long)w->servo.slipLimit);
  bool drvOk = false;
  uint32_t drv = w->gen.readReg(Tmc2209Uart::DRVSTATUS, &drvOk);
  Serial.printf("#   VERSION 0x%02X, DRV_STATUS %s0x%08lX"
                " (standstill %d, overtemp warn %d, overtemp %d)\n",
                w->gen.version(), drvOk ? "" : "unread ", (unsigned long)drv,
                (int)((drv >> 31) & 1), (int)(drv & 1), (int)((drv >> 1) & 1));
  Serial.printf("#   encoder %s, magnet %s, agc %u (0..128 on 3V3, aim for ~64)"
                ", worst read %lu us (%.0f%% of the %lu us tick)\n",
                w->servo.encoderOk() ? "responding" : "NOT RESPONDING",
                magnetText(w->status), w->agc,
                (unsigned long)w->servo.worstReadUs(),
                100.0f * w->servo.worstReadUs() / CONTROL_US,
                (unsigned long)CONTROL_US);
}

static void printInfo() {
  Serial.printf("# EN=GPIO%u (active low, shared by both drivers), TMC2209 UART"
                " TX=GPIO%u RX=GPIO%u at %lu baud, control %lu Hz\n",
                PIN_EN, PIN_TX, PIN_RX, (unsigned long)UART_BAUD,
                (unsigned long)CONTROL_HZ);
  Serial.printf("# drivers %s, commands go to wheel %s\n",
                driversEnabled() ? "ENABLED" : "disabled", sel->name);
  Serial.printf("# encoders: A on hardware I2C SDA=GPIO%u SCL=GPIO%u,"
                " B bit-banged SDA=GPIO%u SCL=GPIO%u\n",
                SDA, SCL, PIN_B_SDA, PIN_B_SCL);
  Serial.printf("# %.0f full steps x 1/%.0f x %.0f/%.0f gear = %.1f steps/out-rev"
                " vs %ld counts, %.6f steps/count nominal\n",
                MOTOR_FULL_STEPS, microsteps, GEAR_OUT_TEETH, GEAR_MOTOR_TEETH,
                stepsPerOutRev(), (long)StepperServo::COUNTS_PER_REV,
                nominalStepsPerCount());
  Serial.printf("# VACTUAL LSB %.4f steps/s = %.5f out turns/s; rate ceiling"
                " %.0f steps/s = %.2f out turns/s\n",
                VelGen::VACTUAL_LSB, VelGen::VACTUAL_LSB / stepsPerOutRev(),
                wheelA.gen.maxRate(), wheelA.gen.maxRate() / stepsPerOutRev());
  for (uint8_t i = 0; i < NWHEELS; i++) printWheel(i);
  printColumns();
}

// The stream's column names. Printed at boot and again by 'i': a scope that
// attaches to an already-running board never saw the banner, and it indexes the
// stream by name, so this line is how it finds out what it is reading.
static void printColumns() {
  // Wheel B grew the same servo columns A has. Every name that was here before
  // is still here, so a scope indexing by name keeps working and simply does
  // not plot what it does not know about yet.
  Serial.println(F("# t_ms,pos,target,err,vel,steps,rate,slip,enc,agc,status,flags,"
                   "bpos,btarget,berr,bvel,bsteps,brate,bslip,benc,bagc,bstatus,busus"));
}

static void printHelp() {
  Serial.println(F("# keys:  e driver on/off   l loop on/off   c calibrate   d flip DIR"));
  Serial.println(F("#        z zero here      f clear fault   x stop+disable"));
  Serial.println(F("#        , . nudge -/+0.05 turn   < > nudge -/+0.25 turn"));
  Serial.println(F("#        w wiggle demo    M scripted demo   p pause stream"));
  Serial.println(F("#        A / B select wheel    i info    h help"));
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
                sel->gen.inverted() ? "INVERTED" : "normal",
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
                sel->servo.stepsPerCount);
  bool isA = (sel == &wheelA);
  if (fabsf(r.clockGain - (isA ? CLOCK_GAIN_A : CLOCK_GAIN_B)) > 0.002f) {
    Serial.printf("# bake it in: set CLOCK_GAIN_%s = %.4ff in test_servo.ino\n",
                  sel->name, r.clockGain);
  }
  if (sel->gen.inverted() != (isA ? SHAFT_INVERT_A : SHAFT_INVERT_B)) {
    Serial.printf("# bake it in: set SHAFT_INVERT_%s = %s in test_servo.ino\n",
                  sel->name, sel->gen.inverted() ? "true" : "false");
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
  demo.stop(sel->servo);
  enableDrivers(false);          // one pin, so this stops both wheels
  Serial.println(F("# stopped, both drivers disabled"));
}

static void doImmediate(char c) {
  switch (c) {
    case 'e': {
      bool on = !driversEnabled();
      enableDrivers(on);
      if (on) delay(20);  // let the TMC2209s come out of standby
      for (uint8_t i = 0; i < NWHEELS; i++) wheels[i]->servo.resyncSlip();
      Serial.printf("# both drivers %s (EN is one shared pin)\n",
                    on ? "ENABLED" : "disabled");
      break;
    }
    case 'l': {
      if (!sel->gen.enabled()) { Serial.println(F("# enable the driver first (e)")); break; }
      bool on = !sel->servo.servoOn();
      sel->servo.servoOn(on);
      Serial.printf("# loop %s, holding %.4f turns\n",
                    on ? "CLOSED" : "open", sel->servo.targetTurns());
      break;
    }
    case 'c': {
      wiggle = false;
      uint8_t st = sel->enc.readStatus();
      if (!(st & MAGNET_DETECT)) {
        Serial.println(F("# no magnet detected -- fix the encoder before calibrating"));
        break;
      }
      if (st & (MAGNET_LOW | MAGNET_HIGH)) {
        Serial.printf("# WARNING magnet %s (agc %u) -- ratio may be off\n",
                      magnetText(st), sel->enc.readAGC());
      }
      Serial.printf("# calibrating: %d output turns out and back at %.0f steps/s,"
                    " ~%.0f s (any key aborts)...\n",
                    CAL_OUT_REVS, CAL_SPS,
                    2.0f * stepsPerOutRev() * CAL_OUT_REVS / CAL_SPS + 1.5f);
      printCal(sel->servo.calibrate(CAL_OUT_REVS, CAL_SPS, abortRequested));
      break;
    }
    case 'd':
      sel->gen.flipInvert();
      sel->servo.servoOn(false);
      sel->servo.resyncSlip();
      Serial.printf("# shaft polarity now %s, loop opened\n",
                    sel->gen.inverted() ? "INVERTED" : "normal");
      break;
    case 'z':
      for (uint8_t i = 0; i < NWHEELS; i++) wheels[i]->servo.zeroHere();
      wiggleBase = 0;
      Serial.println(F("# both wheels zeroed here"));
      break;
    case 'f':
      sel->servo.clearFault();
      sel->servo.resyncSlip();
      Serial.println(F("# fault cleared"));
      break;
    case 'x': panicStop(); break;
    case ',': sel->servo.moveByTurns(-0.05f); break;
    case '.': sel->servo.moveByTurns(+0.05f); break;
    case '<': sel->servo.moveByTurns(-0.25f); break;
    case '>': sel->servo.moveByTurns(+0.25f); break;
    case 'w':
      wiggle = !wiggle;
      if (wiggle) {
        demo.stop(sel->servo);
        wiggleBase = sel->servo.targetTurns();
        wiggleT0 = millis();
        wiggleHigh = false;
      }
      Serial.printf("# wiggle %s (%.3f turns every %.1f s from %.3f)\n",
                    wiggle ? "on" : "off", wiggleAmp, wiggleSecs, wiggleBase);
      break;
    case 'M':
      if (demo.running()) {
        demo.stop(sel->servo);
      } else if (!demo.start(sel->servo)) {
        Serial.println(F("# enable the driver first (e) -- the demo will not do it for you"));
      }
      break;
    case 'A':
    case 'B':
      sel = (c == 'A') ? &wheelA : &wheelB;
      Serial.printf("# commands now go to wheel %s (address %u)%s\n",
                    sel->name, sel->gen.address(),
                    sel->gen.ok() ? "" : " -- WHICH IS NOT ANSWERING");
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
    sel->servo.moveToTurns(strtof(tok, nullptr));
    Serial.printf("# goto %.4f turns\n", sel->servo.targetTurns());
    return;
  }
  if (matches(tok, "goto") || matches(tok, "move") || matches(tok, "spin") ||
      matches(tok, "jog")) {
    if (!arg) { Serial.printf("# %s needs a value\n", tok); return; }
    if (matches(tok, "goto")) sel->servo.moveToTurns(v);
    else if (matches(tok, "move")) sel->servo.moveByTurns(v);
    else if (matches(tok, "spin")) {
      if (!sel->gen.enabled()) { Serial.println(F("# enable the driver first (e)")); return; }
      wiggle = false;
      sel->servo.spin(v);
      Serial.printf("# open-loop spin %.1f steps/s = %.3f out turns/s\n",
                    v, v / stepsPerOutRev());
      return;
    } else {
      if (!sel->gen.enabled()) { Serial.println(F("# enable the driver first (e)")); return; }
      wiggle = false;
      int32_t n = (int32_t)v;
      int32_t before = sel->servo.positionCounts();
      const float jogSps = 500.0f;
      sel->servo.jogSteps(n, jogSps);
      sel->servo.pumpEncoder((uint32_t)(2000.0f * fabsf(v) / jogSps) + 1000, 150,
                        abortRequested);
      int32_t moved = sel->servo.positionCounts() - before;
      int32_t want = (int32_t)((float)n / sel->servo.stepsPerCount);
      Serial.printf("# open-loop jog %ld commanded steps: encoder %+ld counts,"
                    " expected %+ld (%.1f%%), now %.4f turns\n",
                    (long)n, (long)moved, (long)want,
                    want ? 100.0f * (float)moved / (float)want : 0.0f,
                    sel->servo.positionTurns());
      return;
    }
    Serial.printf("# target %.4f turns\n", sel->servo.targetTurns());
    return;
  }

  if (matches(tok, "kp")) { if (arg) sel->servo.kp = v; Serial.printf("# kp %.3f\n", sel->servo.kp); }
  else if (matches(tok, "vmax")) { if (arg) sel->servo.vmaxTps = clampTune(v, VMAX_LIMIT, "vmax", "turns/s"); Serial.printf("# vmax %.3f turns/s (%.0f steps/s)\n", sel->servo.vmaxTps, sel->servo.vmaxTps * stepsPerOutRev()); }
  else if (matches(tok, "vmin")) { if (arg) sel->servo.vminSps = v; Serial.printf("# vmin %.1f steps/s\n", sel->servo.vminSps); }
  else if (matches(tok, "accel")) { if (arg) sel->servo.accelTps2 = clampTune(v, ACCEL_LIMIT, "accel", "turns/s^2"); Serial.printf("# accel %.3f turns/s^2\n", sel->servo.accelTps2); }
  else if (matches(tok, "tol")) { if (arg) sel->servo.tolCounts = (int32_t)v; Serial.printf("# tol %ld counts (%.3f deg out)\n", (long)sel->servo.tolCounts, sel->servo.tolCounts * 360.0f / StepperServo::COUNTS_PER_REV); }
  else if (matches(tok, "maxslip")) { if (arg) sel->servo.slipLimit = (int32_t)v; Serial.printf("# maxslip %ld steps\n", (long)sel->servo.slipLimit); }
  else if (matches(tok, "ratio")) { if (arg) { sel->servo.stepsPerCount = v; sel->servo.resyncSlip(); } Serial.printf("# ratio %.6f steps/count\n", sel->servo.stepsPerCount); }
  else if (matches(tok, "micro")) {
    // Real now, not just bookkeeping: mstep_reg_select is set, so MRES in
    // CHOPCONF overrides MS1/MS2 and this actually changes the driver.
    if (arg && v >= 1) {
      if (!sel->gen.setMicrosteps((uint16_t)v)) {
        Serial.printf("# 1/%.0f is not a TMC2209 setting (1 2 4 8 16 32 64 128 256)\n", v);
      } else {
        microsteps = v;
        sel->servo.stepsPerCount = nominalStepsPerCount();
        sel->servo.resyncSlip();
      }
    }
    Serial.printf("# 1/%u microstep -> %.6f steps/count (driver's MRES, not the pins;"
                  " it interpolates to 256 either way)\n",
                  sel->gen.microsteps(), sel->servo.stepsPerCount);
  }
  else if (matches(tok, "gain")) {
    if (arg) { sel->gen.setClockGain(v); sel->servo.resyncSlip(); }
    Serial.printf("# clock gain %.4f%s\n", sel->gen.clockGain(),
                  sel->gen.calibrated() ? "" : " (default -- 'c' measures it)");
  }
  else if (matches(tok, "amp")) { if (arg) wiggleAmp = v; Serial.printf("# wiggle amplitude %.3f turns\n", wiggleAmp); }
  else if (matches(tok, "secs")) { if (arg) wiggleSecs = fmaxf(0.2f, v); Serial.printf("# wiggle period %.2f s\n", wiggleSecs); }
  else { Serial.printf("# unknown command '%s', h for help\n", tok); }
}

// A key acts the moment it arrives, but only when nothing is half-typed --
// otherwise it is a character of a word command and waits for the newline.
// Every letter here must be one that no word command starts with, or that word
// can never be typed: the first character fires the key and the remainder
// arrives as a truncated command. That is why the scripted demo moved to 'M'
// -- move, micro and maxslip all start with m -- and why wheel select is
// 'A'/'B', since amp and accel have the lowercase.
static const char *IMMEDIATE = "elcdzfxwMABpih?,.<>";

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
  pinMode(PIN_EN, OUTPUT);
  digitalWrite(PIN_EN, HIGH);   // both drivers disabled before the bus opens

  uint8_t answered = 0;
  for (uint8_t i = 0; i < NWHEELS; i++) {
    if (wheels[i]->gen.begin(UART_BAUD, (uint16_t)microsteps)) {
      answered++;
    } else {
      Serial.printf("# wheel %s driver (address %u) did not answer\n",
                    wheels[i]->name, wheels[i]->gen.address());
    }
  }
  if (answered < NWHEELS) {
    Serial.println(F("# TMC2209 did not answer over UART. Check, in this order:"));
    Serial.println(F("#   the wire is on module pin 4 (RX) -- pin 5 is unpopulated"));
    Serial.println(F("#   1k between D6 and D7, motor power on, VIO to 3V3"));
    Serial.println(F("# carrying on so the encoders still stream, but nothing"));
    Serial.println(F("# will move until the driver answers."));
  }
  wheelA.gen.setInvert(SHAFT_INVERT_A);
  wheelB.gen.setInvert(SHAFT_INVERT_B);
  wheelA.gen.presetClockGain(CLOCK_GAIN_A);
  wheelB.gen.presetClockGain(CLOCK_GAIN_B);

  Wire.begin(SDA, SCL);
  Wire.setClock(400000);
  encA.begin();
  encA.setDirection(AS5600_CLOCK_WISE);

  uint32_t waited = 0;
  while (!encA.isConnected()) {
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

  for (uint8_t i = 0; i < NWHEELS; i++) {
    wheels[i]->servo.stepsPerCount = nominalStepsPerCount();
    wheels[i]->servo.begin();
  }
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
  sel->servo.moveToTurns(wiggleBase + (wiggleHigh ? wiggleAmp : 0.0f));
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
    for (uint8_t i = 0; i < NWHEELS; i++) wheels[i]->servo.update(dt);
    demo.update(sel->servo);
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
  // Everything but F_ENCB and F_BFAULT describes wheel A, which is what the
  // scope has always shaded on. B's state reads out of its own columns.
  if (driversEnabled()) flags |= F_DRIVER;
  if (wheelA.servo.servoOn()) flags |= F_LOOP;
  if (wheelA.servo.atTarget()) flags |= F_AT;
  if (wheelA.servo.fault() != StepperServo::FAULT_NONE) flags |= F_FAULT;
  if (wiggle) flags |= F_WIGGLE;
  if (demo.running()) flags |= F_DEMO;
  if (wheelB.servo.encoderOk()) flags |= F_ENCB;
  if (wheelB.servo.fault() != StepperServo::FAULT_NONE) flags |= F_BFAULT;

  static uint8_t lastFault[NWHEELS] = {StepperServo::FAULT_NONE,
                                      StepperServo::FAULT_NONE};
  for (uint8_t i = 0; i < NWHEELS; i++) {
    if (wheels[i]->servo.fault() == lastFault[i]) continue;
    lastFault[i] = wheels[i]->servo.fault();
    if (lastFault[i] != StepperServo::FAULT_NONE) {
      Serial.printf("# FAULT wheel %s: %s (slip %ld steps) -- loop opened,"
                    " f to clear\n",
                    wheels[i]->name, wheels[i]->servo.faultName(),
                    (long)wheels[i]->servo.slipSteps());
    }
  }

  Serial.printf("%lu,%.4f,%.4f,%ld,%.3f,%ld,%.1f,%ld,%u,%u,0x%02X,0x%02X,"
                "%.4f,%.4f,%ld,%.3f,%ld,%.1f,%ld,%u,%u,0x%02X,%lu\n",
                millis(),
                wheelA.servo.positionTurns(), wheelA.servo.targetTurns(),
                (long)wheelA.servo.errorCounts(), wheelA.servo.velocityTps(),
                (long)llround(wheelA.gen.position()), wheelA.gen.rate(),
                (long)wheelA.servo.slipSteps(), wheelA.servo.rawAngle(),
                wheelA.agc, wheelA.status, flags,
                wheelB.servo.positionTurns(), wheelB.servo.targetTurns(),
                (long)wheelB.servo.errorCounts(), wheelB.servo.velocityTps(),
                (long)llround(wheelB.gen.position()), wheelB.gen.rate(),
                (long)wheelB.servo.slipSteps(), wheelB.servo.rawAngle(),
                wheelB.agc, wheelB.status,
                (unsigned long)wheelB.servo.takeRecentReadUs());
}
