#include <ESP32MX1508.h>
#include <Wire.h>
#include <AS5600.h>
#include "MultiTurnServo.h"

TwoWire I2C_0 = TwoWire(0);
TwoWire I2C_1 = TwoWire(1);
// Buses are swapped vs. the original wiring assumption so that encoderN sits on
// motorN's crank (cross-wiring found by pulse test, 2026-06-03).
AS5600 encoder1(&I2C_1); // motor1's crank, bus on D9/D8
AS5600 encoder2(&I2C_0); // motor2's crank, bus on default SDA/SCL

MX1508 motor1(D0, D1, 0, 1);
MX1508 motor2(D2, D3, 2, 3);

// Signs measured with `o`: encoder1 raw decreases on motor1-forward,
// encoder2 raw increases on motor2-forward.
MultiTurnServo servo1(encoder1, motor1, -1);
MultiTurnServo servo2(encoder2, motor2, +1);
MultiTurnServo* servos[2] = { &servo1, &servo2 };
MX1508* motors[2] = { &motor1, &motor2 };

const uint32_t LOOP_HZ = 1000;
bool streamStatus = false;
bool printRaw = false;

void controlTask(void*) {
    const TickType_t period = pdMS_TO_TICKS(1000 / LOOP_HZ);
    const float dt = 1.0f / LOOP_HZ;
    TickType_t wake = xTaskGetTickCount();
    for (;;) {
        servo1.update(dt);
        servo2.update(dt);
        vTaskDelayUntil(&wake, period);
    }
}

void printHelp() {
    Serial.println("commands:");
    Serial.println("  g <1|2> <turns>     go to absolute position (multiturn ok, e.g. g 1 2500.25)");
    Serial.println("  r <1|2> <turns>     move relative");
    Serial.println("  o <1|2> <pwm> <ms>  open-loop pulse (-255..255, <=1000ms), reports encoder delta");
    Serial.println("  v <turns/sec>       max speed for moves (0 = unlimited)");
    Serial.println("  pwm <val>           max PWM cap, both servos (default 255)");
    Serial.println("  minpwm <val>        stiction feedforward PWM, both servos (default 40)");
    Serial.println("  dir <1|2> <-1|1>    set encoder feedback sign");
    Serial.println("  z                   zero both position counters here");
    Serial.println("  x                   stop/disable both");
    Serial.println("  kp|ki|kd <val>      set PID gains (both servos)");
    Serial.println("  enc                 encoder health (magnet detect, AGC, magnitude)");
    Serial.println("  s                   print status once");
    Serial.println("  watch               toggle status stream");
    Serial.println("  raw                 toggle raw encoder angle stream");
    Serial.println("  reset               restart MCU (returns to off state)");
}

void printStatusLine() {
    const char* state[2];
    for (int i = 0; i < 2; i++) {
        state[i] = servos[i]->fault() ? "FAULT" : (servos[i]->enabled() ? "on" : "off");
    }
    Serial.printf("1[%s]: pos %.3f tgt %.3f vel %.2f pwm %d | 2[%s]: pos %.3f tgt %.3f vel %.2f pwm %d\n",
                  state[0], servo1.positionTurns(), servo1.targetTurns(), servo1.velocityTps(), servo1.lastPwm(),
                  state[1], servo2.positionTurns(), servo2.targetTurns(), servo2.velocityTps(), servo2.lastPwm());
}

// AS5600 health: the chip reports whether it sees a magnet at all, and whether
// the field is in range. AGC mid-scale (~64 at 3.3V) = ideal air gap; pegged at
// 0 = magnet too close/strong, pegged at 128 = too far/weak. A frozen angle with
// "magnet NO" or AGC pegged high means the magnet isn't over the chip.
void printEncoderHealth() {
    AS5600* encs[2] = { &encoder1, &encoder2 };
    for (int i = 0; i < 2; i++) {
        AS5600& e = *encs[i];
        if (!e.isConnected()) {
            Serial.printf("encoder%d: NOT RESPONDING on I2C\n", i + 1);
            continue;
        }
        Serial.printf("encoder%d: magnet %s%s%s  agc %u  magnitude %u  angle %.2f deg\n",
                      i + 1,
                      e.detectMagnet() ? "YES" : "NO",
                      e.magnetTooWeak() ? " (too weak/far)" : "",
                      e.magnetTooStrong() ? " (too strong/close)" : "",
                      e.readAGC(), e.readMagnitude(),
                      e.readAngle() * 360.0 / 4096.0);
    }
}

// Open-loop pulse: drive one motor for a capped time, then report how BOTH
// encoders moved — this catches cross-wired encoders, not just direction signs.
// Servos are disabled first so the control task won't fight us, but its update()
// keeps accumulating position, including coast-down after the motor stops.
void pulseTest(int idx, int pwm, int ms) {
    pwm = constrain(pwm, -255, 255);
    ms = constrain(ms, 1, 1000);
    MX1508& m = *motors[idx - 1];
    servo1.disable();
    servo2.disable();
    int64_t before[2] = { servo1.positionCounts(), servo2.positionCounts() };
    if (pwm >= 0) m.motorGo(pwm);
    else m.motorRev(-pwm);
    delay(ms);
    m.motorStop();
    delay(500);  // let inertia coast down so the deltas include the whole motion
    int64_t d[2];
    for (int i = 0; i < 2; i++) d[i] = servos[i]->positionCounts() - before[i];
    Serial.printf("pulse motor%d pwm %d for %dms: enc1 delta %lld counts (%.3f turns), enc2 delta %lld counts (%.3f turns)\n",
                  idx, pwm, ms,
                  (long long)d[0], (float)d[0] / MultiTurnServo::COUNTS_PER_REV,
                  (long long)d[1], (float)d[1] / MultiTurnServo::COUNTS_PER_REV);
    int other = (idx == 1) ? 1 : 0;  // array index of the other encoder
    if (llabs(d[other]) > 4 * llabs(d[idx - 1]) && llabs(d[other]) > 100) {
        Serial.printf("  note: encoder%d responded to motor%d — encoders look CROSS-WIRED\n", other + 1, idx);
    }
}

void handleCommand(char* line) {
    int idx, iv, ms;
    float val;
    if (sscanf(line, "g %d %f", &idx, &val) == 2 && idx >= 1 && idx <= 2) {
        servos[idx - 1]->moveToTurns(val);
        Serial.printf("servo%d -> %.3f turns\n", idx, val);
    } else if (sscanf(line, "r %d %f", &idx, &val) == 2 && idx >= 1 && idx <= 2) {
        servos[idx - 1]->moveByTurns(val);
        Serial.printf("servo%d -> %.3f turns\n", idx, servos[idx - 1]->targetTurns());
    } else if (sscanf(line, "o %d %d %d", &idx, &iv, &ms) == 3 && idx >= 1 && idx <= 2) {
        pulseTest(idx, iv, ms);
    } else if (sscanf(line, "v %f", &val) == 1) {
        servo1.maxSpeedTps = servo2.maxSpeedTps = val;
        Serial.printf("max speed %.2f turns/s\n", val);
    } else if (sscanf(line, "pwm %d", &iv) == 1) {
        servo1.maxPwm = servo2.maxPwm = constrain(iv, 0, 255);
        Serial.printf("max pwm %d\n", servo1.maxPwm);
    } else if (sscanf(line, "minpwm %d", &iv) == 1) {
        servo1.minPwm = servo2.minPwm = constrain(iv, 0, 255);
        Serial.printf("min pwm %d\n", servo1.minPwm);
    } else if (sscanf(line, "dir %d %d", &idx, &iv) == 2 && idx >= 1 && idx <= 2) {
        servos[idx - 1]->setDirection(iv);
        Serial.printf("servo%d direction %+d (disabled)\n", idx, servos[idx - 1]->direction());
    } else if (strcmp(line, "z") == 0) {
        servo1.zeroHere();
        servo2.zeroHere();
        Serial.println("zeroed");
    } else if (strcmp(line, "x") == 0) {
        servo1.disable();
        servo2.disable();
        Serial.println("disabled");
    } else if (sscanf(line, "kp %f", &val) == 1) {
        servo1.kp = servo2.kp = val;
        Serial.printf("kp=%.4f\n", val);
    } else if (sscanf(line, "ki %f", &val) == 1) {
        servo1.ki = servo2.ki = val;
        Serial.printf("ki=%.4f\n", val);
    } else if (sscanf(line, "kd %f", &val) == 1) {
        servo1.kd = servo2.kd = val;
        Serial.printf("kd=%.4f\n", val);
    } else if (strcmp(line, "enc") == 0) {
        printEncoderHealth();
    } else if (strcmp(line, "s") == 0) {
        printStatusLine();
    } else if (strcmp(line, "watch") == 0) {
        streamStatus = !streamStatus;
    } else if (strcmp(line, "raw") == 0) {
        printRaw = !printRaw;
    } else if (strcmp(line, "reset") == 0) {
        servo1.disable();
        servo2.disable();
        Serial.println("resetting...");
        Serial.flush();
        delay(50);
        ESP.restart();
    } else {
        printHelp();
    }
}

void pollSerial() {
    static char buf[64];
    static size_t len = 0;
    while (Serial.available()) {
        char c = Serial.read();
        if (c == '\n' || c == '\r') {
            if (len > 0) {
                buf[len] = '\0';
                handleCommand(buf);
                len = 0;
            }
        } else if (len < sizeof(buf) - 1) {
            buf[len++] = c;
        }
    }
}

void setup() {
    Serial.begin(115200);
    // One bus per encoder: the AS5600 has a fixed I2C address (0x36).
    // 400 kHz keeps each angle read ~150 us so the 1 kHz loop has headroom.
    I2C_0.begin(SDA, SCL, 400000);
    I2C_1.begin(D9, D8, 400000);

    if (!encoder1.begin()) Serial.println("Encoder1 not detected!");
    if (!encoder2.begin()) Serial.println("Encoder2 not detected!");

    servo1.begin();
    servo2.begin();

    // Control loop on core 0; loop()/Serial stay on core 1 and can't stall it.
    xTaskCreatePinnedToCore(controlTask, "servo", 4096, nullptr, configMAX_PRIORITIES - 2, nullptr, 0);

    Serial.println("pet servo console ready");
    printHelp();
}

void loop() {
    pollSerial();

    // Announce faults as they happen (servo auto-disables itself).
    static uint8_t lastFault[2] = { 0, 0 };
    for (int i = 0; i < 2; i++) {
        uint8_t f = servos[i]->fault();
        if (f != lastFault[i]) {
            lastFault[i] = f;
            if (f) Serial.printf("servo%d FAULT: %s — motor disabled\n", i + 1, servos[i]->faultName());
        }
    }

    static uint32_t lastPrint = 0;
    if (millis() - lastPrint >= 200) {
        lastPrint = millis();
        if (streamStatus) printStatusLine();
        if (printRaw) {
            Serial.printf("Encoder 1 angle: %.2f deg\tEncoder 2 angle: %.2f deg\n",
                          encoder1.readAngle() * 360.0 / 4096.0,
                          encoder2.readAngle() * 360.0 / 4096.0);
        }
    }
    delay(2);
}
