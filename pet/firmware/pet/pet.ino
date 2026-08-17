#include <ESP32MX1508.h>
#include <Wire.h>
#include <AS5600.h>
#include <Preferences.h>
#include "MultiTurnServo.h"
#include "src/pet_generated.h"
#include "Comms.h"
#include "Net.h"

namespace pw = pet::wire;

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
Preferences prefs;
const char* BOTTOM_KEYS[2] = { "bot1", "bot2" };
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

// Help describes the talk.py command syntax; talk.py encodes these to packets.
const char* HELP_TEXT =
    "commands:\n"
    "  g <1|2> <turns>     go to absolute position (multiturn ok, e.g. g 1 2500.25)\n"
    "  r <1|2> <turns>     move relative\n"
    "  o <1|2> <pwm> <ms>  open-loop pulse (-255..255, <=1000ms), reports encoder delta\n"
    "  v <turns/sec>       max speed for moves (0 = unlimited)\n"
    "  vg <turns/sec>      ground-segment speed, crank 0-180 deg from bottom (0 = use v)\n"
    "  va <turns/sec>      air-segment speed, crank 180-360 deg (0 = use v)\n"
    "  pwm <val>           max PWM cap, both servos (default 255)\n"
    "  minpwm <val>        stiction feedforward PWM, both servos (default 40)\n"
    "  dir <1|2> <-1|1>    set encoder feedback sign\n"
    "  cal [1|2]           record current pose as cycle bottom (saved to flash)\n"
    "  stand               move both legs to nearest cycle bottom\n"
    "  walk <n> [deg]      walk n half-turn steps, crank phase offset deg (default 180), ends standing\n"
    "  z                   zero both position counters here (debug; cal/stand preferred)\n"
    "  x                   stop/disable both\n"
    "  kp|ki|kd <val>      set PID gains (both servos)\n"
    "  enc                 encoder health (magnet detect, AGC, magnitude)\n"
    "  s                   print status once\n"
    "  watch               toggle status stream\n"
    "  raw                 toggle raw encoder angle stream\n"
    "  wifi [ssid pass]    connect to wifi (saved to flash); bare wifi shows status\n"
    "  reset               restart MCU (returns to off state)";

// -1 for BOTH (callers that need a specific servo treat that as an error).
int chanIndex(pw::Channel ch) {
    if (ch == pw::Channel::ONE) return 0;
    if (ch == pw::Channel::TWO) return 1;
    return -1;
}

flatbuffers::Offset<pw::Status> buildStatus(flatbuffers::FlatBufferBuilder& fbb) {
    flatbuffers::Offset<pw::ServoState> states[2];
    for (int i = 0; i < 2; i++) {
        MultiTurnServo& s = *servos[i];
        bool faulted = s.fault() != MultiTurnServo::FAULT_NONE;
        auto name = faulted ? fbb.CreateString(s.faultName())
                            : flatbuffers::Offset<flatbuffers::String>();
        states[i] = pw::CreateServoState(fbb, (pw::Channel)(i + 1), s.enabled(), faulted,
                                         name, s.positionTurns(), s.targetTurns(),
                                         s.velocityTps(), (int16_t)s.lastPwm());
    }
    return pw::CreateStatus(fbb, fbb.CreateVector(states, 2));
}

// AS5600 health: the chip reports whether it sees a magnet at all, and whether
// the field is in range. AGC mid-scale (~64 at 3.3V) = ideal air gap; pegged at
// 0 = magnet too close/strong, pegged at 128 = too far/weak. A frozen angle with
// no magnet or AGC pegged high means the magnet isn't over the chip.
flatbuffers::Offset<pw::EncoderHealth> buildEncoderHealth(flatbuffers::FlatBufferBuilder& fbb) {
    AS5600* encs[2] = { &encoder1, &encoder2 };
    flatbuffers::Offset<pw::EncoderInfo> infos[2];
    for (int i = 0; i < 2; i++) {
        AS5600& e = *encs[i];
        bool connected = e.isConnected();
        if (!connected) {
            infos[i] = pw::CreateEncoderInfo(fbb, (pw::Channel)(i + 1), false);
            continue;
        }
        infos[i] = pw::CreateEncoderInfo(fbb, (pw::Channel)(i + 1), true,
                                         e.detectMagnet(), e.magnetTooWeak(), e.magnetTooStrong(),
                                         e.readAGC(), e.readMagnitude(),
                                         e.readAngle() * 360.0f / 4096.0f);
    }
    return pw::CreateEncoderHealth(fbb, fbb.CreateVector(infos, 2));
}

// Open-loop pulse: drive one motor for a capped time, then report how BOTH
// encoders moved — this catches cross-wired encoders, not just direction signs.
// Servos are disabled first so the control task won't fight us, but its update()
// keeps accumulating position, including coast-down after the motor stops.
void pulseTest(int idx, int pwm, int ms, const Comms::ReplyTarget& tgt) {
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
    int other = (idx == 1) ? 1 : 0;  // array index of the other encoder
    bool crossWired = llabs(d[other]) > 4 * llabs(d[idx - 1]) && llabs(d[other]) > 100;
    flatbuffers::FlatBufferBuilder fbb(256);
    auto res = pw::CreatePulseResult(fbb, (pw::Channel)idx, (int16_t)pwm, (int16_t)ms,
                                     d[0], (float)d[0] / MultiTurnServo::COUNTS_PER_REV,
                                     d[1], (float)d[1] / MultiTurnServo::COUNTS_PER_REV,
                                     crossWired);
    Comms::reply(tgt, fbb, pw::Msg::PulseResult, res.Union());
}

// --- walk sequencer ---
// Walking runs the cranks a fixed phase apart (default 180 deg): the lead leg
// advances +phase while the other holds stance (lead-in), both legs then
// advance together half a turn per step (the PID keeps them phase-locked), and
// finally each leg advances forward to its own next whole turn (lead-out) so
// the walk ends standing. At 180 deg exactly one leg is at half phase after N
// steps; at other offsets both legs may have a remainder. The lead foot
// alternates between walks: the lead leg travels extra distance (a full turn
// at 180 deg / even N), and alternating cancels the sideways drift that
// asymmetry would build up over many walks.
enum WalkState { W_IDLE, W_STAND, W_LEADIN, W_STEPS, W_LEADOUT };
WalkState walkState = W_IDLE;
int walkLead = 0;  // index of the leg that starts the next walk
int walkSteps = 0;
float walkPhase = 0.5f;  // crank offset of the lead leg, turns in [0,1)

// Start the next phase while the legs are still ~0.1 turn from finishing the
// current one. Moves extend the target, and the slewed setpoint never
// decelerates at the boundary, so the gait flows through phase changes instead
// of braking, settling into the 8-count window, and lurching off again.
const int32_t WALK_BLEND = 410;  // counts

bool legsWithin(int32_t counts) {
    return llabs(servo1.targetCounts() - servo1.positionCounts()) <= counts &&
           llabs(servo2.targetCounts() - servo2.positionCounts()) <= counts;
}

// Broadcast walk progress; `servo` is the 1-based leg the phase concerns
// (lead-in/lead-out leg, or the next walk's lead for DONE).
void walkEvent(pw::WalkPhase phase, int servo) {
    flatbuffers::FlatBufferBuilder fbb(128);
    auto ev = pw::CreateWalkEvent(fbb, phase, walkSteps, (int8_t)servo);
    Comms::broadcast(fbb, pw::Msg::WalkEvent, ev.Union());
}

void startWalk(int steps, float phaseDeg) {
    // Cap keeps the big STEPS move within float-exact count range (and ~80 min).
    walkSteps = constrain(steps, 1, 8000);
    float t = phaseDeg / 360.0f;
    walkPhase = t - floorf(t);  // wrap to [0,1); negatives mean the lead lags
    walkState = W_STAND;
    servo1.standAtBottom();
    servo2.standAtBottom();
    walkEvent(pw::WalkPhase::START, walkLead + 1);
}

void walkSequencer() {
    if (walkState == W_IDLE) return;
    // Abort on fault or external disable (`x` mid-walk).
    if (!servo1.enabled() || !servo2.enabled() || servo1.fault() || servo2.fault()) {
        walkState = W_IDLE;
        walkEvent(pw::WalkPhase::ABORTED, walkLead + 1);
        return;
    }
    // Blend mid-walk transitions; only the final "done" requires a true settle.
    bool ready = (walkState == W_LEADOUT) ? (servo1.atTarget() && servo2.atTarget())
                                          : legsWithin(WALK_BLEND);
    if (!ready) return;
    switch (walkState) {
        case W_STAND:
            servos[walkLead]->moveByTurns(walkPhase);
            walkState = W_LEADIN;
            walkEvent(pw::WalkPhase::LEADIN, walkLead + 1);
            break;
        case W_LEADIN:
            servo1.moveByTurns(walkSteps * 0.5f);
            servo2.moveByTurns(walkSteps * 0.5f);
            walkState = W_STEPS;
            walkEvent(pw::WalkPhase::STEPPING, walkLead + 1);
            break;
        case W_STEPS: {
            // Targets are exact commanded counts, so integer modulo gives each
            // leg's remainder to its next whole turn (0 if already standing).
            const int32_t CPR = MultiTurnServo::COUNTS_PER_REV;
            int32_t rem[2];
            for (int i = 0; i < 2; i++) {
                int64_t t = servos[i]->targetCounts();
                rem[i] = (int32_t)((CPR - (((t % CPR) + CPR) % CPR)) % CPR);
                if (rem[i]) servos[i]->moveToCounts(t + rem[i]);
            }
            walkState = W_LEADOUT;
            // Report the leg with the longer lead-out move.
            walkEvent(pw::WalkPhase::LEADOUT, (rem[0] >= rem[1] ? 0 : 1) + 1);
            break;
        }
        case W_LEADOUT:
            walkState = W_IDLE;
            walkLead = 1 - walkLead;
            walkEvent(pw::WalkPhase::DONE, walkLead + 1);  // next walk's lead
            break;
        default:
            break;
    }
}

// Record the leg's current pose as the bottom of its gait cycle and persist the
// encoder's absolute angle to flash. Survives power cycles: the AS5600 is
// absolute within a turn, so phase is recoverable at every boot even though the
// turn count isn't.
void calibrateBottom(int idx, const Comms::ReplyTarget& tgt) {
    MultiTurnServo& s = *servos[idx - 1];
    s.disable();
    s.calibrateBottomHere();
    prefs.putUShort(BOTTOM_KEYS[idx - 1], s.bottomOffset);
    char buf[96];
    snprintf(buf, sizeof(buf), "servo%d: bottom = raw %u (%.2f deg), saved; position re-zeroed here",
             idx, s.bottomOffset, s.bottomOffset * 360.0 / 4096.0);
    Comms::replyLog(tgt, pw::LogLevel::INFO, buf);
}

// --- packet command handlers (replaces the old sscanf text parser) ---

void handleNumber(const pw::NumberCmd* c, const Comms::ReplyTarget& tgt) {
    float v = c->value();
    int idx = chanIndex(c->channel());
    char buf[96];
    switch (c->cmd()) {
        case pw::NumCmd::GOTO:
        case pw::NumCmd::MOVE_BY:
            if (idx < 0) { Comms::replyAck(tgt, "move needs servo 1 or 2", false); return; }
            if (c->cmd() == pw::NumCmd::GOTO) servos[idx]->moveToTurns(v);
            else servos[idx]->moveByTurns(v);
            snprintf(buf, sizeof(buf), "servo%d -> %.3f turns", idx + 1, servos[idx]->targetTurns());
            break;
        case pw::NumCmd::MAX_SPEED:
            servo1.maxSpeedTps = servo2.maxSpeedTps = v;
            snprintf(buf, sizeof(buf), "max speed %.2f turns/s", v);
            break;
        case pw::NumCmd::GROUND_SPEED:
            servo1.groundSpeedTps = servo2.groundSpeedTps = v;
            snprintf(buf, sizeof(buf), "ground speed %.2f turns/s%s", v, v > 0 ? "" : " (= v)");
            break;
        case pw::NumCmd::AIR_SPEED:
            servo1.airSpeedTps = servo2.airSpeedTps = v;
            snprintf(buf, sizeof(buf), "air speed %.2f turns/s%s", v, v > 0 ? "" : " (= v)");
            break;
        case pw::NumCmd::MAX_PWM:
            servo1.maxPwm = servo2.maxPwm = constrain((int)v, 0, 255);
            snprintf(buf, sizeof(buf), "max pwm %d", servo1.maxPwm);
            break;
        case pw::NumCmd::MIN_PWM:
            servo1.minPwm = servo2.minPwm = constrain((int)v, 0, 255);
            snprintf(buf, sizeof(buf), "min pwm %d", servo1.minPwm);
            break;
        case pw::NumCmd::KP:
            servo1.kp = servo2.kp = v;
            snprintf(buf, sizeof(buf), "kp=%.4f", v);
            break;
        case pw::NumCmd::KI:
            servo1.ki = servo2.ki = v;
            snprintf(buf, sizeof(buf), "ki=%.4f", v);
            break;
        case pw::NumCmd::KD:
            servo1.kd = servo2.kd = v;
            snprintf(buf, sizeof(buf), "kd=%.4f", v);
            break;
        case pw::NumCmd::SET_DIR:
            if (idx < 0) { Comms::replyAck(tgt, "dir needs servo 1 or 2", false); return; }
            servos[idx]->setDirection((int)v);
            snprintf(buf, sizeof(buf), "servo%d direction %+d (disabled)", idx + 1, servos[idx]->direction());
            break;
        default:
            Comms::replyAck(tgt, "unknown numeric command", false);
            return;
    }
    Comms::replyAck(tgt, buf);
}

void handleSimple(const pw::SimpleAction* c, const Comms::ReplyTarget& tgt) {
    char buf[96];
    switch (c->cmd()) {
        case pw::SimpleCmd::STAND: {
            for (int i = 0; i < 2; i++) {
                if (!servos[i]->hasBottom) {
                    Comms::logf(pw::LogLevel::WARN,
                                "servo%d: not calibrated (run `cal`) — using current zero", i + 1);
                }
                servos[i]->standAtBottom();
            }
            snprintf(buf, sizeof(buf), "standing: servo1 -> %.3f, servo2 -> %.3f turns",
                     servo1.targetTurns(), servo2.targetTurns());
            Comms::replyAck(tgt, buf);
            break;
        }
        case pw::SimpleCmd::ZERO:
            servo1.zeroHere();
            servo2.zeroHere();
            Comms::replyAck(tgt, "zeroed");
            break;
        case pw::SimpleCmd::STOP:
            servo1.disable();
            servo2.disable();
            Comms::replyAck(tgt, "disabled");
            break;
        case pw::SimpleCmd::ENC_HEALTH: {
            flatbuffers::FlatBufferBuilder fbb(512);
            auto h = buildEncoderHealth(fbb);
            Comms::reply(tgt, fbb, pw::Msg::EncoderHealth, h.Union());
            break;
        }
        case pw::SimpleCmd::STATUS: {
            flatbuffers::FlatBufferBuilder fbb(512);
            auto st = buildStatus(fbb);
            Comms::reply(tgt, fbb, pw::Msg::Status, st.Union());
            break;
        }
        case pw::SimpleCmd::RESET:
            servo1.disable();
            servo2.disable();
            Comms::replyAck(tgt, "resetting");
            Comms::broadcastLog(pw::LogLevel::WARN, "resetting...");
            Serial.flush();
            delay(50);
            ESP.restart();
            break;
        case pw::SimpleCmd::HELP:
        default:
            Comms::replyLog(tgt, pw::LogLevel::INFO, HELP_TEXT);
            break;
    }
}

void dispatchPacket(const pw::Packet* pkt, const Comms::ReplyTarget& tgt) {
    switch (pkt->msg_type()) {
        case pw::Msg::NumberCmd:
            handleNumber(pkt->msg_as_NumberCmd(), tgt);
            break;
        case pw::Msg::SimpleAction:
            handleSimple(pkt->msg_as_SimpleAction(), tgt);
            break;
        case pw::Msg::Calibrate: {
            int idx = chanIndex(pkt->msg_as_Calibrate()->channel());
            if (idx >= 0) {
                calibrateBottom(idx + 1, tgt);
            } else {
                calibrateBottom(1, tgt);
                calibrateBottom(2, tgt);
            }
            break;
        }
        case pw::Msg::PulseCmd: {
            const pw::PulseCmd* c = pkt->msg_as_PulseCmd();
            int idx = chanIndex(c->channel());
            if (idx < 0) { Comms::replyAck(tgt, "pulse needs servo 1 or 2", false); break; }
            pulseTest(idx + 1, c->pwm(), c->ms(), tgt);
            break;
        }
        case pw::Msg::ToggleCmd: {
            char buf[48];
            if (pkt->msg_as_ToggleCmd()->which() == pw::Toggle::STATUS_STREAM) {
                streamStatus = !streamStatus;
                snprintf(buf, sizeof(buf), "status stream %s", streamStatus ? "on" : "off");
            } else {
                printRaw = !printRaw;
                snprintf(buf, sizeof(buf), "raw stream %s", printRaw ? "on" : "off");
            }
            Comms::replyAck(tgt, buf);
            break;
        }
        case pw::Msg::WalkCmd: {
            char buf[80];
            const pw::WalkCmd* c = pkt->msg_as_WalkCmd();
            startWalk(c->steps(), c->phase_deg());
            snprintf(buf, sizeof(buf), "walk: %d steps, phase %.0f deg, servo%d leads",
                     walkSteps, walkPhase * 360.0f, walkLead + 1);
            Comms::replyAck(tgt, buf);
            break;
        }
        case pw::Msg::WifiCmd:
            Net::handleWifiCmd(pkt->msg_as_WifiCmd(), tgt);
            break;
        default:
            Comms::replyLog(tgt, pw::LogLevel::ERROR, "unsupported message type");
            break;
    }
}

void setup() {
    Serial.begin(115200);
    // One bus per encoder: the AS5600 has a fixed I2C address (0x36).
    // 400 kHz keeps each angle read ~150 us so the 1 kHz loop has headroom.
    I2C_0.begin(SDA, SCL, 400000);
    I2C_1.begin(D9, D8, 400000);

    if (!encoder1.begin()) Comms::broadcastLog(pw::LogLevel::ERROR, "Encoder1 not detected!");
    if (!encoder2.begin()) Comms::broadcastLog(pw::LogLevel::ERROR, "Encoder2 not detected!");

    servo1.begin();
    servo2.begin();

    // Restore cycle-bottom calibration and align zero to it: position 0 (and
    // every other integer turn) is then a standing pose, across power cycles.
    prefs.begin("pet", false);
    for (int i = 0; i < 2; i++) {
        if (prefs.isKey(BOTTOM_KEYS[i])) {
            servos[i]->bottomOffset = prefs.getUShort(BOTTOM_KEYS[i]);
            servos[i]->hasBottom = true;
            servos[i]->alignZeroToBottom();
            Comms::logf(pw::LogLevel::INFO,
                        "servo%d: bottom calibration loaded, phase %.3f turns from stance",
                        i + 1, servos[i]->positionTurns());
        } else {
            Comms::logf(pw::LogLevel::INFO,
                        "servo%d: no bottom calibration (run `cal` with leg at cycle bottom)", i + 1);
        }
    }

    // WiFi auto-connect if credentials are stored (non-blocking).
    Net::begin(prefs);

    // Control loop on core 0; loop()/comms stay on core 1 and can't stall it.
    xTaskCreatePinnedToCore(controlTask, "servo", 4096, nullptr, configMAX_PRIORITIES - 2, nullptr, 0);

    Comms::broadcastLog(pw::LogLevel::INFO, "pet servo console ready");
}

void loop() {
    Comms::pollSerial();
    Net::loop();
    walkSequencer();

    // Announce faults as they happen (servo auto-disables itself).
    static uint8_t lastFault[2] = { 0, 0 };
    for (int i = 0; i < 2; i++) {
        uint8_t f = servos[i]->fault();
        if (f != lastFault[i]) {
            lastFault[i] = f;
            if (f) Comms::logf(pw::LogLevel::ERROR, "servo%d FAULT: %s — motor disabled",
                               i + 1, servos[i]->faultName());
        }
    }

    static uint32_t lastPrint = 0;
    if (millis() - lastPrint >= 200) {
        lastPrint = millis();
        if (streamStatus) {
            flatbuffers::FlatBufferBuilder fbb(512);
            auto st = buildStatus(fbb);
            Comms::broadcast(fbb, pw::Msg::Status, st.Union());
        }
        if (printRaw) {
            // Built inline (not logf) so the stream doesn't flood the boot log ring.
            char buf[96];
            snprintf(buf, sizeof(buf), "Encoder 1 angle: %.2f deg\tEncoder 2 angle: %.2f deg",
                     encoder1.readAngle() * 360.0 / 4096.0,
                     encoder2.readAngle() * 360.0 / 4096.0);
            flatbuffers::FlatBufferBuilder fbb(256);
            auto log = pw::CreateLogDirect(fbb, pw::LogLevel::INFO, buf);
            Comms::broadcast(fbb, pw::Msg::Log, log.Union());
        }
    }
    delay(2);
}
