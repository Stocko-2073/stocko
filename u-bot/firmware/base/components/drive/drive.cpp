// The drive layer: two wheels, one control task, one C API.
//
// The control task owns every servo object. Other tasks reach the drive
// through the functions at the bottom of this file, which take the servo
// mutex briefly to change a setpoint and read the lock-free status snapshot
// the control task refreshes every tick. Two things deliberately bypass the
// mutex: drive_estop() writes the EN pin directly, and drive_get_status()
// copies the snapshot under a spinlock -- neither can ever be stuck behind a
// calibration that is holding the mutex for ten seconds.
#include "drive.h"

#include <math.h>
#include <string.h>

#include "AS5600.h"
#include "Demo.h"
#include "I2cBus.h"
#include "StepperServo.h"
#include "Tmc2209Uart.h"
#include "VelGen.h"
#include "driver/gpio.h"
#include "esp_log.h"
#include "esp_task_wdt.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/semphr.h"
#include "freertos/task.h"
#include "platform.h"
#include "sdkconfig.h"
#include "settings.h"

static const char *TAG = "drive";

namespace {

// ---------------------------------------------------------------- drivetrain
//
// From DRIVE_MECHANISM.md, all exact: 200 full steps x 1/8 microstep x 40/12
// bevel = 5333.333 microsteps per output turn against 4096 encoder counts.
constexpr float MOTOR_FULL_STEPS = 200.0f;
constexpr float GEAR_MOTOR_TEETH = 12.0f;
constexpr float GEAR_OUT_TEETH   = 40.0f;
constexpr float GEAR_RATIO       = GEAR_OUT_TEETH / GEAR_MOTOR_TEETH;
constexpr uint16_t MICROSTEPS_DEFAULT = 8;

// 215 mm on the tread tips. Good to a millimetre, which is far better than a
// robot on grass deserves -- do not sharpen this constant, earn odometry from
// the encoders and an IMU instead.
constexpr float WHEEL_DIAMETER_M = 0.215f;
constexpr float WHEEL_CIRC_M     = 3.14159265f * WHEEL_DIAMETER_M;

// Measured ceiling: clean to 1.0 turns/s, marginal by 2.0, sheds steps at 2.76.
constexpr float VMAX_LIMIT  = 2.0f;    // output turns/s
constexpr float ACCEL_LIMIT = 20.0f;   // output turns/s^2

constexpr int   CAL_OUT_REVS = 3;      // whole output turns, so encoder INL cancels
constexpr float CAL_SPS      = 1500.0f;

constexpr uint32_t CONTROL_US       = 1000000UL / CONFIG_UBOT_CONTROL_HZ;
constexpr uint32_t HEALTH_MS        = 250;   // alternating wheels: each every 500 ms
constexpr uint32_t ENCODER_FAULT_MS = 250;   // encoder silent this long with the loop closed
constexpr uint32_t LOCK_MS          = 200;   // how long an API call waits for the servo mutex
constexpr gpio_num_t PIN_EN         = (gpio_num_t)CONFIG_UBOT_PIN_EN;

float stepsPerOutRev(uint16_t micro) { return MOTOR_FULL_STEPS * micro * GEAR_RATIO; }
float nominalStepsPerCount(uint16_t micro) { return stepsPerOutRev(micro) / StepperServo::COUNTS_PER_REV; }

// ------------------------------------------------------------------ hardware

Tmc2209Uart tmc(UART_NUM_1, CONFIG_UBOT_PIN_TMC_RX, CONFIG_UBOT_PIN_TMC_TX);
HwI2c busA(0, CONFIG_UBOT_PIN_ENC_A_SDA, CONFIG_UBOT_PIN_ENC_A_SCL);
SoftI2c busB(CONFIG_UBOT_PIN_ENC_B_SDA, CONFIG_UBOT_PIN_ENC_B_SCL);
AS5600 encA(busA);
AS5600 encB(busB);

// One drive axis: a driver on the shared bus, the encoder on its output shaft,
// and the loop between them. The two differ only in address, shaft polarity and
// the clock gain measured for that individual chip -- everything else about
// them is the same mechanism built twice.
struct Wheel {
    const char *name;
    const char *gainKey;
    const char *invKey;
    VelGen gen;
    StepperServo servo;
    AS5600 &enc;
    uint16_t microsteps = MICROSTEPS_DEFAULT;
    uint8_t agc = 0;
    uint8_t status = 0;
    bool statusOk = false;
    uint32_t encDownSince = 0;

    Wheel(const char *n, const char *gk, const char *ik, uint8_t addr, AS5600 &e)
        : name(n), gainKey(gk), invKey(ik), gen(tmc, addr), servo(e, gen), enc(e) {}
};

Wheel wheelA("A", "gain_a", "inv_a", CONFIG_UBOT_TMC_ADDR_A, encA);
Wheel wheelB("B", "gain_b", "inv_b", CONFIG_UBOT_TMC_ADDR_B, encB);
Wheel *const wheels[DRIVE_NWHEELS] = {&wheelA, &wheelB};

Demo demo;

// --------------------------------------------------------------------- state

struct State {
    SemaphoreHandle_t mtx = nullptr;
    TaskHandle_t task = nullptr;
    esp_timer_handle_t ticker = nullptr;

    bool driversOn = false;
    bool faultLatched = false;
    uint8_t faultWheel = 0;
    volatile bool pendingEstop = false;

    // The robot-frame command in force and when it lapses (0 = never).
    bool cmdActive = false;
    int64_t cmdExpires = 0;
    float cmdV = 0, cmdW = 0;

    // Bench per-wheel velocity holds.
    bool whActive[DRIVE_NWHEELS] = {false, false};
    int64_t whExpires[DRIVE_NWHEELS] = {0, 0};

    // Calibration request, executed on the control task.
    volatile int calReq = -1;
    volatile bool calAbort = false;
    bool calBusy = false;
    bool calHave = false;
    drive_cal_result_t calLast = {};

    // Robot frame. Wheel A defines forward by fiat (sign_a = +1); wheel B is
    // the mirror image so the mechanism predicts sign_b = -1. Which side A is
    // on decides the sign of a turn. See DRIVE_MECHANISM.md.
    int8_t signA = +1;
    int8_t signB = -1;
    bool aIsLeft = true;
    float trackM = 0.263f;   // wheel centre to wheel centre, from u-bot.scad; measure it

    uint32_t tickWorst = 0;
    uint32_t tickCount = 0;
    uint32_t lastHealth = 0;
    uint8_t healthIdx = 0;

    const char *refusal = "";
} S;

portMUX_TYPE snapMux = portMUX_INITIALIZER_UNLOCKED;
drive_status_t snap = {};

// ------------------------------------------------------------------- helpers

bool lock(uint32_t ms = LOCK_MS) {
    return S.mtx && xSemaphoreTake(S.mtx, pdMS_TO_TICKS(ms)) == pdTRUE;
}
void unlock() { xSemaphoreGive(S.mtx); }

esp_err_t refuse(const char *why) {
    S.refusal = why;
    ESP_LOGW(TAG, "refused: %s", why);
    return ESP_ERR_INVALID_STATE;
}

void cancelCommands() {
    S.cmdActive = false;
    S.cmdV = S.cmdW = 0;
    for (int i = 0; i < DRIVE_NWHEELS; i++) S.whActive[i] = false;
}

// EN is one pin for both drivers, so energising is all-or-nothing in hardware.
// Every driver's VACTUAL is zeroed BEFORE the pin drops: the register survives
// an MCU reset even though the power stage was off, and one live velocity would
// lurch the whole robot the instant it is energised. Disabling runs the other
// way round -- cut the power stage first, tidy up after.
void enableDrivers(bool on) {
    if (on) {
        for (Wheel *w : wheels) w->gen.setEnabled(true);
        gpio_set_level(PIN_EN, 0);
        S.driversOn = true;
        delayMs(20);   // let the TMC2209s come out of standby
        for (Wheel *w : wheels) w->servo.resyncSlip();
    } else {
        gpio_set_level(PIN_EN, 1);
        for (Wheel *w : wheels) w->servo.enableDriver(false);
        S.driversOn = false;
        cancelCommands();
    }
}

void setWheelVelocity(Wheel &w, float tps) {
    if (!w.gen.enabled()) return;
    if (w.servo.fault() != StepperServo::FAULT_NONE) return;
    if (!w.servo.servoOn()) w.servo.servoOn(true);
    w.servo.setVelocityTps(tps);
}

// Robot frame to wheels. Left = v - w*L/2, right = v + w*L/2 with w positive
// anticlockwise from above; then each wheel's own sign maps "forward" onto
// "encoder counts up".
void wheelTpsFor(float v, float w, float &tpsA, float &tpsB) {
    float half = S.trackM * 0.5f;
    float vLeft = v - w * half;
    float vRight = v + w * half;
    float vA = S.aIsLeft ? vLeft : vRight;
    float vB = S.aIsLeft ? vRight : vLeft;
    tpsA = vA / WHEEL_CIRC_M * (float)S.signA;
    tpsB = vB / WHEEL_CIRC_M * (float)S.signB;
}

void applyRobotVelocity(float v, float w) {
    float a, b;
    wheelTpsFor(v, w, a, b);
    setWheelVelocity(wheelA, a);
    setWheelVelocity(wheelB, b);
}

// Never ask a wheel for more than its ceiling. Scaling v and w together keeps
// the arc the joystick asked for; clipping one wheel would bend it.
void limitRobotVelocity(float &v, float &w) {
    float a, b;
    wheelTpsFor(v, w, a, b);
    float peak = fmaxf(fabsf(a), fabsf(b));
    float vmax = wheelA.servo.vmaxTps;
    if (peak > vmax && peak > 0) {
        float k = vmax / peak;
        v *= k;
        w *= k;
    }
}

float vmaxMps() { return wheelA.servo.vmaxTps * WHEEL_CIRC_M; }
float wmaxRadps() { return 2.0f * vmaxMps() / fmaxf(S.trackM, 0.05f); }

void pollHealth(Wheel &w) {
    uint8_t st = w.enc.readStatus();
    if (w.enc.lastError() != AS5600::OK) {
        w.statusOk = false;
        return;
    }
    w.status = st;
    w.statusOk = true;
    w.agc = w.enc.readAGC();
    // The encoder declaring it does not know where it is. Only while the loop
    // is closed -- a bench with the magnet off is not a fault, it is a bench.
    if (S.driversOn && w.servo.servoOn() && !(st & AS5600::MAGNET_DETECT)) {
        w.servo.raiseFault(StepperServo::FAULT_MAGNET);
    }
}

void latchFault(uint8_t idx) {
    Wheel &w = *wheels[idx];
    S.faultLatched = true;
    S.faultWheel = idx;
    ESP_LOGE(TAG, "FAULT wheel %s: %s (slip %ld steps) -- both wheels stopped, 'faults clear' to resume",
             w.name, w.servo.faultName(), (long)w.servo.slipSteps());
    // One wheel holding while the other drives pivots a differential drive
    // rather than stopping it, so the healthy wheel is stopped too.
    for (int j = 0; j < DRIVE_NWHEELS; j++) {
        if (j == idx) continue;
        Wheel &o = *wheels[j];
        if (o.servo.servoOn()) o.servo.raiseFault(StepperServo::FAULT_PEER);
        else o.servo.spin(0);
    }
    cancelCommands();
}

void checkFaults() {
    for (int i = 0; i < DRIVE_NWHEELS; i++) {
        Wheel &w = *wheels[i];
        if (S.driversOn && w.servo.servoOn() && !w.servo.encoderOk()) {
            if (!w.encDownSince) w.encDownSince = millis();
            else if (millis() - w.encDownSince > ENCODER_FAULT_MS) {
                w.servo.raiseFault(StepperServo::FAULT_ENCODER);
            }
        } else {
            w.encDownSince = 0;
        }
    }
    if (S.faultLatched) return;
    for (int i = 0; i < DRIVE_NWHEELS; i++) {
        uint8_t f = wheels[i]->servo.fault();
        if (f != StepperServo::FAULT_NONE && f != StepperServo::FAULT_PEER) {
            latchFault((uint8_t)i);
            return;
        }
    }
}

void updateSnapshot() {
    drive_status_t s = {};
    s.enabled = S.driversOn;
    s.faulted = S.faultLatched;
    s.fault_wheel = S.faultWheel;
    s.cal_busy = S.calBusy;
    s.demo_running = demo.running();
    s.demo_caption = demo.caption();
    s.cmd_active = S.cmdActive;
    s.v_mps = S.cmdV;
    s.w_radps = S.cmdW;
    s.vmax_mps = vmaxMps();
    s.wmax_radps = wmaxRadps();
    s.track_m = S.trackM;
    s.wheel_circ_m = WHEEL_CIRC_M;
    s.sign_a = S.signA;
    s.sign_b = S.signB;
    s.a_is_left = S.aIsLeft;
    s.tick_worst_us = S.tickWorst;
    s.tick_count = S.tickCount;
    s.bus_writes = tmc.writes();
    s.bus_echo_faults = tmc.echoFaults();
    for (int i = 0; i < DRIVE_NWHEELS; i++) {
        Wheel &w = *wheels[i];
        drive_wheel_status_t &d = s.wheel[i];
        d.driver_ok = w.gen.ok();
        d.enabled = w.gen.enabled();
        d.loop_closed = w.servo.servoOn();
        d.velocity_mode = w.servo.velocityMode();
        d.encoder_ok = w.servo.encoderOk();
        d.calibrated = w.gen.calibrated();
        d.inverted = w.gen.inverted();
        d.at_target = w.servo.atTarget();
        d.fault = w.servo.fault();
        d.agc = w.agc;
        d.magnet_status = w.status;
        d.raw_angle = w.servo.rawAngle();
        d.pos_counts = w.servo.positionCounts();
        d.target_counts = w.servo.targetCounts();
        d.err_counts = w.servo.errorCounts();
        d.slip_steps = w.servo.slipSteps();
        d.cmd_steps = (long)llround(w.gen.position());
        d.pos_turns = w.servo.positionTurns();
        d.target_turns = w.servo.targetTurns();
        d.vel_tps = w.servo.velocityTps();
        d.cmd_tps = w.servo.commandedTps();
        d.rate_sps = w.gen.rate();
        d.clock_gain = w.gen.clockGain();
        d.kp = w.servo.kp;
        d.vmax_tps = w.servo.vmaxTps;
        d.accel_tps2 = w.servo.accelTps2;
        d.worst_read_us = w.servo.worstReadUs();
    }
    portENTER_CRITICAL(&snapMux);
    snap = s;
    portEXIT_CRITICAL(&snapMux);
}

// Polled by the blocking calibration at ~1 kHz. Doubles as the snapshot
// refresher while the tick loop is suspended.
bool calAbortFn() {
    static uint32_t n = 0;
    if ((++n % 50) == 0) updateSnapshot();
    return S.calAbort || S.pendingEstop;
}

void runCalibration() {
    int idx = S.calReq;
    Wheel &w = *wheels[idx];
    xSemaphoreTake(S.mtx, portMAX_DELAY);
    S.calBusy = true;
    S.calAbort = false;
    updateSnapshot();
    ESP_LOGI(TAG, "calibrating wheel %s: %d output turns out and back at %.0f steps/s, ~%.0f s",
             w.name, CAL_OUT_REVS, CAL_SPS,
             2.0f * stepsPerOutRev(w.microsteps) * CAL_OUT_REVS / CAL_SPS + 1.5f);

    StepperServo::CalResult r = w.servo.calibrate(CAL_OUT_REVS, CAL_SPS, calAbortFn);

    drive_cal_result_t out = {};
    out.ok = r.ok;
    out.flipped = r.flipped;
    out.counts = r.counts;
    out.back = r.back;
    out.residual = r.residual;
    out.seconds = r.seconds;
    out.sps = r.sps;
    out.clock_gain = r.clockGain;
    out.note = r.note;
    out.wheel = (drive_wheel_t)idx;
    S.calLast = out;
    S.calHave = true;

    if (!r.ok) {
        ESP_LOGE(TAG, "calibrate wheel %s FAILED: %s", w.name, r.note);
    } else {
        ESP_LOGI(TAG, "calibrate wheel %s: %+ld counts in %.3f s at %.0f steps/s, shaft polarity %s%s",
                 w.name, (long)r.counts, r.seconds, r.sps,
                 w.gen.inverted() ? "INVERTED" : "normal",
                 r.flipped ? " (flipped)" : " (unchanged)");
        ESP_LOGI(TAG, "  clock gain %.4f: asked %.0f steps/s, got %.0f -- %+.1f%%, the TMC2209's oscillator",
                 r.clockGain, r.sps, r.sps * r.clockGain, 100.0f * (r.clockGain - 1.0f));
        ESP_LOGI(TAG, "  return leg %+ld counts against %+ld out, residual %+ld%s",
                 (long)r.back, (long)r.counts, (long)r.residual,
                 labs((long)r.residual) > 8 ? " -- steps were lost, check current and speed"
                                            : " (no steps lost)");
        esp_err_t e1 = settings_set_f32(w.gainKey, r.clockGain);
        esp_err_t e2 = settings_set_i32(w.invKey, w.gen.inverted() ? 1 : 0);
        if (e1 == ESP_OK && e2 == ESP_OK) {
            ESP_LOGI(TAG, "  stored: %s=%.4f %s=%d", w.gainKey, r.clockGain, w.invKey,
                     w.gen.inverted() ? 1 : 0);
        } else {
            ESP_LOGE(TAG, "  could not store calibration in NVS");
        }
    }
    S.calBusy = false;
    S.calReq = -1;
    updateSnapshot();
    xSemaphoreGive(S.mtx);
}

void controlTask(void *) {
    esp_task_wdt_add(nullptr);
    uint32_t last = micros();
    for (;;) {
        // The ticker notifies every CONTROL_US; the timeout is only a guard so
        // a lost notification cannot stall the loop (and the watchdog) forever.
        ulTaskNotifyTake(pdTRUE, pdMS_TO_TICKS(50));
        esp_task_wdt_reset();

        if (S.calReq >= 0) {
            runCalibration();
            last = micros();
            continue;
        }

        uint32_t t0 = micros();
        float dt = (float)(t0 - last) * 1e-6f;
        last = t0;
        if (dt > 0.05f) dt = 0.05f;

        xSemaphoreTake(S.mtx, portMAX_DELAY);

        if (S.pendingEstop) {
            S.pendingEstop = false;
            demo.stop();
            enableDrivers(false);
            ESP_LOGW(TAG, "emergency stop: both drivers disabled");
        }

        int64_t now = esp_timer_get_time();
        if (S.cmdActive && S.cmdExpires && now > S.cmdExpires) {
            bool moving = S.cmdV != 0 || S.cmdW != 0;
            S.cmdActive = false;
            S.cmdV = S.cmdW = 0;
            applyRobotVelocity(0, 0);
            if (moving) ESP_LOGW(TAG, "deadman: no fresh drive command, ramping to a stop");
        }
        for (int i = 0; i < DRIVE_NWHEELS; i++) {
            if (S.whActive[i] && S.whExpires[i] && now > S.whExpires[i]) {
                S.whActive[i] = false;
                setWheelVelocity(*wheels[i], 0);
                ESP_LOGW(TAG, "deadman: wheel %s velocity hold expired, stopping", wheels[i]->name);
            }
        }

        for (Wheel *w : wheels) w->servo.update(dt);
        checkFaults();
        demo.update();

        if (millis() - S.lastHealth >= HEALTH_MS) {
            S.lastHealth = millis();
            pollHealth(*wheels[S.healthIdx]);
            S.healthIdx ^= 1;
        }

        updateSnapshot();
        xSemaphoreGive(S.mtx);

        uint32_t took = micros() - t0;
        if (took > S.tickWorst) S.tickWorst = took;
        S.tickCount++;
    }
}

void tickerCb(void *) {
    if (S.task) xTaskNotifyGive(S.task);
}

void loadSettings() {
    S.signA = settings_get_i32("sign_a", +1) < 0 ? -1 : +1;
    S.signB = settings_get_i32("sign_b", -1) < 0 ? -1 : +1;
    S.aIsLeft = settings_get_i32("a_left", 1) != 0;
    S.trackM = settings_get_f32("track_m", 0.263f);
    float vmax = constrain(settings_get_f32("vmax_tps", 1.0f), 0.05f, VMAX_LIMIT);
    float accel = constrain(settings_get_f32("accel_tps2", 8.0f), 0.5f, ACCEL_LIMIT);
    // Measured 2026-08-30/31 on the two drivers this robot was built with.
    // Calibration overwrites these per chip; they are only the starting point.
    float gainA = settings_get_f32(wheelA.gainKey, 1.0158f);
    float gainB = settings_get_f32(wheelB.gainKey, 1.0091f);
    bool invA = settings_get_i32(wheelA.invKey, 0) != 0;
    bool invB = settings_get_i32(wheelB.invKey, 1) != 0;
    for (Wheel *w : wheels) {
        w->servo.vmaxTps = vmax;
        w->servo.accelTps2 = accel;
    }
    wheelA.gen.setInvert(invA);
    wheelB.gen.setInvert(invB);
    wheelA.gen.presetClockGain(gainA);
    wheelB.gen.presetClockGain(gainB);
}

Wheel *wheelArg(drive_wheel_t w) {
    return (w == DRIVE_WHEEL_A || w == DRIVE_WHEEL_B) ? wheels[w] : nullptr;
}

const char *const PARAM_NAMES[] = {"kp", "vmax", "accel", "vmin", "tol", "maxslip", "ratio", "gain", "micro"};
const char *const SETTING_NAMES[] = {"sign_a", "sign_b", "a_left", "track_m", "vmax_tps", "accel_tps2"};

}  // namespace

// ================================================================== C API

extern "C" {

void drive_park_en(void) {
    // Level first, then direction, so the pin never presents a low on its way
    // to being an output. Whatever state it was in, it is high from here on.
    static bool configured = false;
    gpio_set_level(PIN_EN, 1);
    if (configured) return;
    configured = true;
    gpio_config_t io = {};
    io.pin_bit_mask = 1ULL << CONFIG_UBOT_PIN_EN;
    io.mode = GPIO_MODE_OUTPUT;
    io.pull_up_en = GPIO_PULLUP_ENABLE;
    io.pull_down_en = GPIO_PULLDOWN_DISABLE;
    io.intr_type = GPIO_INTR_DISABLE;
    gpio_config(&io);
    gpio_set_level(PIN_EN, 1);
}

esp_err_t drive_init(void) {
    drive_park_en();
    if (!S.mtx) S.mtx = xSemaphoreCreateMutex();
    if (!S.mtx) return ESP_ERR_NO_MEM;

    loadSettings();

    if (!tmc.begin(CONFIG_UBOT_TMC_BAUD)) {
        ESP_LOGE(TAG, "UART%d on TX=GPIO%d RX=GPIO%d failed to start", (int)UART_NUM_1,
                 CONFIG_UBOT_PIN_TMC_TX, CONFIG_UBOT_PIN_TMC_RX);
    }
    for (Wheel *w : wheels) {
        if (w->gen.begin(w->microsteps)) {
            ESP_LOGI(TAG, "wheel %s: TMC2209 at address %u answered, VERSION 0x%02X, shaft %s, clock gain %.4f",
                     w->name, w->gen.address(), w->gen.version(),
                     w->gen.inverted() ? "inverted" : "normal", w->gen.clockGain());
        } else {
            ESP_LOGE(TAG, "wheel %s: TMC2209 at address %u did not answer (%s)", w->name,
                     w->gen.address(), Tmc2209Uart::statusName(w->gen.lastStatus()));
        }
    }
    if (!wheelA.gen.ok() || !wheelB.gen.ok()) {
        ESP_LOGW(TAG, "check: wire on module pin 4 (RX), 1k between TX and RX, motor power on "
                      "(the TMC2209 is deaf on UART without VMOT), VIO to 3V3");
    }

    for (Wheel *w : wheels) {
        bool ok = w->enc.begin();
        uint8_t st = ok ? w->enc.readStatus() : 0;
        if (ok) {
            ESP_LOGI(TAG, "wheel %s: AS5600 on %s I2C, magnet %s, agc %u (0..128, aim ~64)",
                     w->name, w->enc.busKind(), AS5600::magnetText(st), w->enc.readAGC());
        } else {
            ESP_LOGE(TAG, "wheel %s: no AS5600 answering on the %s bus", w->name, w->enc.busKind());
        }
        w->servo.stepsPerCount = nominalStepsPerCount(w->microsteps);
        w->servo.begin();
        pollHealth(*w);
    }

    ESP_LOGI(TAG, "EN=GPIO%d shared, UART %d baud, control %d Hz, %.1f steps/out-rev, %.6f steps/count",
             CONFIG_UBOT_PIN_EN, CONFIG_UBOT_TMC_BAUD, CONFIG_UBOT_CONTROL_HZ,
             stepsPerOutRev(MICROSTEPS_DEFAULT), nominalStepsPerCount(MICROSTEPS_DEFAULT));
    ESP_LOGI(TAG, "robot frame: sign_a %+d sign_b %+d, wheel A is %s, track %.3f m, vmax %.2f m/s",
             S.signA, S.signB, S.aIsLeft ? "left" : "right", S.trackM, vmaxMps());
    ESP_LOGI(TAG, "drivers start disabled -- 'enable' energises both, 'cal A' / 'cal B' measure the clocks");

    updateSnapshot();

    if (xTaskCreate(controlTask, "drive", 6144, nullptr, 20, &S.task) != pdPASS) {
        return ESP_ERR_NO_MEM;
    }
    esp_timer_create_args_t targs = {};
    targs.callback = tickerCb;
    targs.name = "drive_tick";
    targs.dispatch_method = ESP_TIMER_TASK;
    esp_err_t err = esp_timer_create(&targs, &S.ticker);
    if (err == ESP_OK) err = esp_timer_start_periodic(S.ticker, CONTROL_US);
    return err;
}

// --- power ---

esp_err_t drive_enable(bool on) {
    if (!lock()) return refuse("drive is busy (calibrating)");
    if (on) {
        bool allOk = true;
        for (Wheel *w : wheels) {
            if (!w->gen.ok()) w->gen.begin(w->microsteps);   // maybe motor power arrived since boot
            if (!w->gen.ok()) allOk = false;
        }
        if (!allOk) {
            unlock();
            return refuse("a driver is not answering on the UART bus -- not energising");
        }
        for (Wheel *w : wheels) w->servo.clearFault();
        S.faultLatched = false;
        enableDrivers(true);
        ESP_LOGI(TAG, "both drivers ENABLED (EN is one shared pin)");
    } else {
        demo.stop();
        enableDrivers(false);
        ESP_LOGI(TAG, "both drivers disabled");
    }
    updateSnapshot();
    unlock();
    return ESP_OK;
}

bool drive_enabled(void) { return S.driversOn; }

void drive_stop(void) {
    if (!lock()) {
        S.calAbort = true;   // a calibration is the only thing that holds the mutex this long
        return;
    }
    cancelCommands();
    demo.stop();
    for (Wheel *w : wheels) {
        if (w->servo.velocityMode()) w->servo.setVelocityTps(0);   // ramps down
        else if (w->servo.servoOn()) w->servo.servoOn(false);        // instant
        else w->servo.spin(0);                                       // open-loop spin
    }
    unlock();
}

void drive_estop(void) {
    gpio_set_level(PIN_EN, 1);   // the only line that matters; everything else is bookkeeping
    S.pendingEstop = true;
    S.calAbort = true;
}

// --- motion ---

static esp_err_t motionPrecheck() {
    if (!S.driversOn) return refuse("drivers are disabled -- 'enable' first");
    if (S.faultLatched) return refuse("a fault is latched -- 'faults clear' first");
    if (demo.running()) return refuse("a demo is running -- 'demo stop' first");
    return ESP_OK;
}

esp_err_t drive_set_velocity(float v_mps, float w_radps, uint32_t hold_ms) {
    if (!(fabsf(v_mps) < 100.0f) || !(fabsf(w_radps) < 100.0f)) return ESP_ERR_INVALID_ARG;
    if (!lock()) return refuse("drive is busy (calibrating)");
    esp_err_t err = motionPrecheck();
    if (err != ESP_OK) { unlock(); return err; }
    limitRobotVelocity(v_mps, w_radps);
    applyRobotVelocity(v_mps, w_radps);
    S.cmdV = v_mps;
    S.cmdW = w_radps;
    S.cmdActive = (v_mps != 0 || w_radps != 0);
    S.cmdExpires = hold_ms ? esp_timer_get_time() + (int64_t)hold_ms * 1000 : 0;
    for (int i = 0; i < DRIVE_NWHEELS; i++) S.whActive[i] = false;
    unlock();
    return ESP_OK;
}

esp_err_t drive_set_normalized(float v, float w, uint32_t hold_ms) {
    if (!(fabsf(v) <= 1.5f) || !(fabsf(w) <= 1.5f)) return ESP_ERR_INVALID_ARG;
    v = constrain(v, -1.0f, 1.0f);
    w = constrain(w, -1.0f, 1.0f);
    return drive_set_velocity(v * vmaxMps(), w * wmaxRadps(), hold_ms);
}

esp_err_t drive_wheel_velocity(drive_wheel_t wi, float tps, uint32_t hold_ms) {
    Wheel *w = wheelArg(wi);
    if (!w) return ESP_ERR_INVALID_ARG;
    if (!lock()) return refuse("drive is busy (calibrating)");
    esp_err_t err = motionPrecheck();
    if (err != ESP_OK) { unlock(); return err; }
    tps = constrain(tps, -w->servo.vmaxTps, w->servo.vmaxTps);
    setWheelVelocity(*w, tps);
    S.cmdActive = false;
    S.whActive[wi] = tps != 0;
    S.whExpires[wi] = hold_ms ? esp_timer_get_time() + (int64_t)hold_ms * 1000 : 0;
    unlock();
    return ESP_OK;
}

esp_err_t drive_wheel_goto(drive_wheel_t wi, float turns) {
    Wheel *w = wheelArg(wi);
    if (!w) return ESP_ERR_INVALID_ARG;
    if (!lock()) return refuse("drive is busy (calibrating)");
    esp_err_t err = motionPrecheck();
    if (err != ESP_OK) { unlock(); return err; }
    if (!w->servo.servoOn()) w->servo.servoOn(true);
    w->servo.moveToTurns(turns);
    S.whActive[wi] = false;
    unlock();
    return ESP_OK;
}

esp_err_t drive_wheel_move(drive_wheel_t wi, float dturns) {
    Wheel *w = wheelArg(wi);
    if (!w) return ESP_ERR_INVALID_ARG;
    if (!lock()) return refuse("drive is busy (calibrating)");
    esp_err_t err = motionPrecheck();
    if (err != ESP_OK) { unlock(); return err; }
    if (!w->servo.servoOn()) w->servo.servoOn(true);
    w->servo.moveByTurns(dturns);
    S.whActive[wi] = false;
    unlock();
    return ESP_OK;
}

esp_err_t drive_wheel_spin(drive_wheel_t wi, float sps) {
    Wheel *w = wheelArg(wi);
    if (!w) return ESP_ERR_INVALID_ARG;
    if (!lock()) return refuse("drive is busy (calibrating)");
    if (!S.driversOn) { unlock(); return refuse("drivers are disabled -- 'enable' first"); }
    if (demo.running()) { unlock(); return refuse("a demo is running -- 'demo stop' first"); }
    w->servo.spin(sps);
    S.whActive[wi] = false;
    unlock();
    return ESP_OK;
}

esp_err_t drive_wheel_loop(drive_wheel_t wi, bool closed) {
    Wheel *w = wheelArg(wi);
    if (!w) return ESP_ERR_INVALID_ARG;
    if (!lock()) return refuse("drive is busy (calibrating)");
    if (closed && !w->gen.enabled()) { unlock(); return refuse("drivers are disabled -- 'enable' first"); }
    w->servo.servoOn(closed);
    unlock();
    return ESP_OK;
}

esp_err_t drive_wheel_zero(drive_wheel_t wi) {
    if (!lock()) return refuse("drive is busy (calibrating)");
    for (int i = 0; i < DRIVE_NWHEELS; i++) {
        if (wi == DRIVE_WHEEL_BOTH || wi == i) wheels[i]->servo.zeroHere();
    }
    unlock();
    return ESP_OK;
}

const char *drive_refusal(void) { return S.refusal; }

// --- faults ---

esp_err_t drive_clear_faults(void) {
    if (!lock()) return refuse("drive is busy (calibrating)");
    for (Wheel *w : wheels) {
        w->servo.clearFault();
        w->servo.resyncSlip();
    }
    S.faultLatched = false;
    updateSnapshot();
    unlock();
    ESP_LOGI(TAG, "faults cleared");
    return ESP_OK;
}

const char *drive_fault_name(uint8_t fault) {
    return StepperServo::faultName((StepperServo::Fault)fault);
}

// --- calibration ---

esp_err_t drive_calibrate(drive_wheel_t wi) {
    Wheel *w = wheelArg(wi);
    if (!w) return ESP_ERR_INVALID_ARG;
    if (!lock()) return refuse("drive is busy (calibrating)");
    if (S.calBusy || S.calReq >= 0) { unlock(); return refuse("a calibration is already running"); }
    if (!S.driversOn) { unlock(); return refuse("drivers are disabled -- 'enable' first"); }
    if (!w->gen.ok()) { unlock(); return refuse("that wheel's driver is not answering"); }
    uint8_t st = w->enc.readStatus();
    if (w->enc.lastError() != AS5600::OK) { unlock(); return refuse("that wheel's encoder is not answering"); }
    if (!(st & AS5600::MAGNET_DETECT)) { unlock(); return refuse("no magnet detected -- fix the encoder first"); }
    if (st & (AS5600::MAGNET_LOW | AS5600::MAGNET_HIGH)) {
        ESP_LOGW(TAG, "wheel %s magnet %s (agc %u) -- result may be off", w->name,
                 AS5600::magnetText(st), w->enc.readAGC());
    }
    demo.stop();
    cancelCommands();
    S.calAbort = false;
    S.calReq = wi;
    unlock();
    return ESP_OK;
}

void drive_calibrate_abort(void) { S.calAbort = true; }
bool drive_calibrate_busy(void) { return S.calBusy || S.calReq >= 0; }

bool drive_calibrate_last(drive_cal_result_t *out) {
    if (!S.calHave || !out) return false;
    *out = S.calLast;
    return true;
}

// --- demo ---

esp_err_t drive_demo_start(const char *name, drive_wheel_t solo) {
    if (!name) return ESP_ERR_INVALID_ARG;
    if (!lock()) return refuse("drive is busy (calibrating)");
    esp_err_t err = motionPrecheck();
    if (err != ESP_OK) { unlock(); return err; }
    cancelCommands();
    bool ok = false;
    if (strcmp(name, "short") == 0) {
        for (Wheel *w : wheels) {
            if (!w->gen.ok()) { unlock(); return refuse("the short needs both drivers answering"); }
            if (!(w->status & AS5600::MAGNET_DETECT)) { unlock(); return refuse("the short needs both magnets detected"); }
            if (w->status & (AS5600::MAGNET_LOW | AS5600::MAGNET_HIGH)) {
                ESP_LOGW(TAG, "wheel %s magnet %s (agc %u) -- it will hold, expect a worse residual",
                         w->name, AS5600::magnetText(w->status), w->agc);
            }
            if (!w->gen.calibrated()) {
                ESP_LOGW(TAG, "wheel %s is on its stored clock gain %.4f, not measured this boot",
                         w->name, w->gen.clockGain());
            }
        }
        ok = demo.start(Demo::SHORT, {&wheelA.servo, wheelA.name, S.signA},
                                     {&wheelB.servo, wheelB.name, S.signB});
    } else if (strcmp(name, "bench") == 0) {
        Wheel *w = wheelArg(solo);
        if (!w) { unlock(); return ESP_ERR_INVALID_ARG; }
        ok = demo.start(Demo::BENCH, {&w->servo, w->name, +1});
    } else {
        unlock();
        return ESP_ERR_NOT_FOUND;
    }
    unlock();
    return ok ? ESP_OK : refuse("demo would not start -- see the log");
}

void drive_demo_stop(void) {
    if (!lock()) return;
    demo.stop();
    unlock();
}

// --- tuning ---

const char *const *drive_param_names(size_t *n) {
    if (n) *n = sizeof(PARAM_NAMES) / sizeof(PARAM_NAMES[0]);
    return PARAM_NAMES;
}

static esp_err_t paramSetOne(Wheel &w, const char *name, float v) {
    if (!strcmp(name, "kp")) { w.servo.kp = v; }
    else if (!strcmp(name, "vmax")) {
        if (v > VMAX_LIMIT) ESP_LOGW(TAG, "vmax clamped to the measured limit %.2f turns/s", VMAX_LIMIT);
        w.servo.vmaxTps = constrain(v, 0.01f, VMAX_LIMIT);
    }
    else if (!strcmp(name, "accel")) {
        if (v > ACCEL_LIMIT) ESP_LOGW(TAG, "accel clamped to the measured limit %.1f turns/s^2", ACCEL_LIMIT);
        w.servo.accelTps2 = constrain(v, 0.1f, ACCEL_LIMIT);
    }
    else if (!strcmp(name, "vmin")) { w.servo.vminSps = fabsf(v); }
    else if (!strcmp(name, "tol")) { w.servo.tolCounts = (int32_t)fabsf(v); }
    else if (!strcmp(name, "maxslip")) { w.servo.slipLimit = (int32_t)fabsf(v); }
    else if (!strcmp(name, "ratio")) { w.servo.stepsPerCount = v; w.servo.resyncSlip(); }
    else if (!strcmp(name, "gain")) { w.gen.setClockGain(v); w.servo.resyncSlip(); }
    else if (!strcmp(name, "micro")) {
        if (!w.gen.setMicrosteps((uint16_t)v)) return ESP_ERR_INVALID_ARG;
        w.microsteps = (uint16_t)v;
        w.servo.stepsPerCount = nominalStepsPerCount(w.microsteps);
        w.servo.resyncSlip();
    }
    else return ESP_ERR_NOT_FOUND;
    return ESP_OK;
}

esp_err_t drive_param_set(drive_wheel_t wi, const char *name, float value) {
    if (!name) return ESP_ERR_INVALID_ARG;
    if (!lock()) return refuse("drive is busy (calibrating)");
    esp_err_t err = ESP_OK;
    for (int i = 0; i < DRIVE_NWHEELS && err == ESP_OK; i++) {
        if (wi == DRIVE_WHEEL_BOTH || wi == i) err = paramSetOne(*wheels[i], name, value);
    }
    updateSnapshot();
    unlock();
    return err;
}

esp_err_t drive_param_get(drive_wheel_t wi, const char *name, float *value) {
    Wheel *w = wheelArg(wi);
    if (!w || !name || !value) return ESP_ERR_INVALID_ARG;
    if (!strcmp(name, "kp")) *value = w->servo.kp;
    else if (!strcmp(name, "vmax")) *value = w->servo.vmaxTps;
    else if (!strcmp(name, "accel")) *value = w->servo.accelTps2;
    else if (!strcmp(name, "vmin")) *value = w->servo.vminSps;
    else if (!strcmp(name, "tol")) *value = (float)w->servo.tolCounts;
    else if (!strcmp(name, "maxslip")) *value = (float)w->servo.slipLimit;
    else if (!strcmp(name, "ratio")) *value = w->servo.stepsPerCount;
    else if (!strcmp(name, "gain")) *value = w->gen.clockGain();
    else if (!strcmp(name, "micro")) *value = (float)w->microsteps;
    else return ESP_ERR_NOT_FOUND;
    return ESP_OK;
}

const char *const *drive_setting_names(size_t *n) {
    if (n) *n = sizeof(SETTING_NAMES) / sizeof(SETTING_NAMES[0]);
    return SETTING_NAMES;
}

esp_err_t drive_setting_set(const char *name, float value) {
    if (!name) return ESP_ERR_INVALID_ARG;
    if (!lock()) return refuse("drive is busy (calibrating)");
    esp_err_t err = ESP_OK;
    if (!strcmp(name, "sign_a") || !strcmp(name, "sign_b")) {
        if (value != 1.0f && value != -1.0f) err = ESP_ERR_INVALID_ARG;
        else {
            int8_t s = value < 0 ? -1 : +1;
            if (name[5] == 'a') S.signA = s; else S.signB = s;
            err = settings_set_i32(name, s);
        }
    } else if (!strcmp(name, "a_left")) {
        S.aIsLeft = value != 0;
        err = settings_set_i32(name, S.aIsLeft ? 1 : 0);
    } else if (!strcmp(name, "track_m")) {
        if (value < 0.05f || value > 2.0f) err = ESP_ERR_INVALID_ARG;
        else { S.trackM = value; err = settings_set_f32(name, value); }
    } else if (!strcmp(name, "vmax_tps")) {
        float v = constrain(value, 0.05f, VMAX_LIMIT);
        for (Wheel *w : wheels) w->servo.vmaxTps = v;
        err = settings_set_f32(name, v);
    } else if (!strcmp(name, "accel_tps2")) {
        float v = constrain(value, 0.5f, ACCEL_LIMIT);
        for (Wheel *w : wheels) w->servo.accelTps2 = v;
        err = settings_set_f32(name, v);
    } else {
        err = ESP_ERR_NOT_FOUND;
    }
    updateSnapshot();
    unlock();
    return err;
}

esp_err_t drive_setting_get(const char *name, float *value) {
    if (!name || !value) return ESP_ERR_INVALID_ARG;
    if (!strcmp(name, "sign_a")) *value = S.signA;
    else if (!strcmp(name, "sign_b")) *value = S.signB;
    else if (!strcmp(name, "a_left")) *value = S.aIsLeft ? 1 : 0;
    else if (!strcmp(name, "track_m")) *value = S.trackM;
    else if (!strcmp(name, "vmax_tps")) *value = wheelA.servo.vmaxTps;
    else if (!strcmp(name, "accel_tps2")) *value = wheelA.servo.accelTps2;
    else return ESP_ERR_NOT_FOUND;
    return ESP_OK;
}

esp_err_t drive_wheel_set_invert(drive_wheel_t wi, bool inv) {
    Wheel *w = wheelArg(wi);
    if (!w) return ESP_ERR_INVALID_ARG;
    if (!lock()) return refuse("drive is busy (calibrating)");
    w->servo.servoOn(false);
    w->gen.setInvert(inv);
    w->servo.resyncSlip();
    esp_err_t err = settings_set_i32(w->invKey, inv ? 1 : 0);
    updateSnapshot();
    unlock();
    ESP_LOGW(TAG, "wheel %s shaft polarity forced %s -- its stored clock gain was measured with the other setting",
             w->name, inv ? "INVERTED" : "normal");
    return err;
}

bool drive_wheel_read_reg(drive_wheel_t wi, uint8_t reg, uint32_t *value) {
    Wheel *w = wheelArg(wi);
    if (!w || !value) return false;
    bool ok = false;
    *value = w->gen.readReg(reg, &ok);   // the bus has its own mutex
    return ok;
}

// --- observation ---

void drive_get_status(drive_status_t *out) {
    if (!out) return;
    portENTER_CRITICAL(&snapMux);
    *out = snap;
    portEXIT_CRITICAL(&snapMux);
}

void drive_reset_stats(void) {
    S.tickWorst = 0;
    for (Wheel *w : wheels) w->servo.resetWorstRead();
}

const char *drive_csv_header(void) {
    return "t_ms,pos,target,err,vel,steps,rate,slip,enc,agc,status,flags,"
           "bpos,btarget,berr,bvel,bsteps,brate,bslip,benc,bagc,bstatus,busus";
}

int drive_csv_line(char *buf, size_t n) {
    drive_status_t s;
    drive_get_status(&s);
    const drive_wheel_status_t &a = s.wheel[0];
    const drive_wheel_status_t &b = s.wheel[1];
    // flags as the bench sketch defined them, so plot.py shades the same way.
    uint8_t flags = 0;
    if (s.enabled) flags |= 0x01;
    if (a.loop_closed) flags |= 0x02;
    if (a.at_target) flags |= 0x04;
    if (a.fault != DRIVE_FAULT_NONE) flags |= 0x08;
    if (b.encoder_ok) flags |= 0x20;
    if (s.demo_running) flags |= 0x40;
    if (b.fault != DRIVE_FAULT_NONE) flags |= 0x80;
    return snprintf(buf, n,
                    "%lu,%.4f,%.4f,%ld,%.3f,%ld,%.1f,%ld,%u,%u,0x%02X,0x%02X,"
                    "%.4f,%.4f,%ld,%.3f,%ld,%.1f,%ld,%u,%u,0x%02X,%lu",
                    (unsigned long)millis(),
                    a.pos_turns, a.target_turns, (long)a.err_counts, a.vel_tps, a.cmd_steps,
                    a.rate_sps, (long)a.slip_steps, a.raw_angle, a.agc, a.magnet_status, flags,
                    b.pos_turns, b.target_turns, (long)b.err_counts, b.vel_tps, b.cmd_steps,
                    b.rate_sps, (long)b.slip_steps, b.raw_angle, b.agc, b.magnet_status,
                    (unsigned long)b.worst_read_us);
}

}  // extern "C"
