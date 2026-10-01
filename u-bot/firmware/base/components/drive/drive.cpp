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
#include "BoostPolicy.h"
#include "Demo.h"
#include "I2cBus.h"
#include "StepperServo.h"
#include "ThermalModel.h"
#include "TimingHistogram.h"
#include "Tmc2209Uart.h"
#include "UartSlot.h"
#include "VelGen.h"
#include "battery.h"
#include "driver/gpio.h"
#include "esp_attr.h"
#include "esp_log.h"
#include "esp_system.h"
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

// Digital current profile: STEPPerOnline 17HS15-1504S-X1, BTT TMC2209 V1.3.
constexpr int32_t IHOLD_DELAY_DEFAULT = 8;

constexpr uint32_t CONTROL_US       = 1000000UL / CONFIG_UBOT_CONTROL_HZ;
constexpr uint32_t ENCODER_FAULT_MS = 250;   // encoder silent this long with the loop closed
constexpr uint32_t LOCK_MS          = 200;   // how long an API call waits for the servo mutex
constexpr gpio_num_t PIN_EN         = (gpio_num_t)CONFIG_UBOT_PIN_EN;

// Torque. Boost is at most IRUN 31 for at most a minute per request, and the
// thermal model decides whether it may run at all.
constexpr uint32_t BOOST_MANUAL_MAX_MS = 60000;   // one manual request, or one drive command's share
constexpr uint32_t OTPW_INJECT_MAX_MS  = 120000;  // bench: longest debug otpw
constexpr uint32_t CS_FRESH_MS   = 600;    // a DRV_STATUS sample this recent tells the thermal model CS_ACTUAL
constexpr uint32_t CS_SETTLE_MS  = 20;     // after a live write, before CS_ACTUAL has to agree with it
constexpr uint32_t CS_WARN_MS    = 10000;  // at most one CS_ACTUAL warning per wheel per this
constexpr uint32_t HEAT_SAVE_MS  = 1000;   // heat copied to RTC memory this often
constexpr float    INFER_MARGIN  = 1.1f;   // the thermal model believes in the higher current 10% longer
constexpr int      BOOST_START_DEFAULT_MS = 1500;
constexpr float    THERM_TAU_DEFAULT_S = 600.0f;
constexpr float    THERM_LIM_DEFAULT   = 1.10f;

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
    bool driverStatusOk = false;
    bool haveDriverSample = false;
    uint32_t drvStatus = 0, gstat = 0, driverSampleMs = 0;
    bool faultDriverStatusOk = false;
    uint32_t faultDrvStatus = 0, faultGstat = 0, faultDriverAgeMs = 0;

    // Torque: the motor's heat budget, what boost is asked for and granted,
    // and the driver's temperature derate. torqueUpdate() runs all three every
    // tick and leaves the pair they settle on in `torque`; uartSlot() writes it
    // to the driver when it differs from what the driver has.
    ThermalModel thermal;
    BoostPolicy boost;
    OtpwDerate derate;
    BoostPolicy::Output torque;   // this tick's
    bool livePending = false;     // `torque` is not what the driver holds
    uint32_t lastMovingMs = 0;    // the step generator last ran, for the standstill reduction
    uint32_t lastLiveWriteMs = 0;
    uint8_t csActual = 0;         // DRV_STATUS CS_ACTUAL, last good sample
    uint32_t csMismatch = 0;
    bool csWarned = false;
    uint32_t csWarnMs = 0;
    bool otpw = false;            // last good sample, injection included
    bool heatLimited = false;     // as last logged
    bool otpwInjecting = false;   // bench: drive_debug_inject_otpw()
    uint32_t otpwInjectUntil = 0;
    TimingHistogram readHist;     // encoder reads
    uint32_t readsSeen = 0;

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
    uint8_t faultCode = DRIVE_FAULT_NONE;   // what latched: the wheel's fault, or a robot-level one
    volatile bool pendingEstop = false;
#if CONFIG_UBOT_BENCH_FAULTS
    volatile uint32_t wedgeMs = 0;          // drive_debug_wedge(), taken by the next tick
#endif

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
    bool aIsLeft = false;   // on this build wheel A is on the right
    float trackM = 0.263f;   // wheel centre to wheel centre, from u-bot.scad; measure it
    int runMa = MotorCurrent::DEFAULT_RUN_MA;
    int holdMa = MotorCurrent::DEFAULT_HOLD_MA;

    // Torque settings (boost_ma, boost_start_ms, therm_tau_s, therm_lim).
    int boostMa = MotorCurrent::BOOST_MAX_MA;
    int boostStartMs = BOOST_START_DEFAULT_MS;
    float thermTauS = THERM_TAU_DEFAULT_S;
    float thermLim = THERM_LIM_DEFAULT;

    uint32_t tickWorst = 0;
    uint32_t tickCount = 0;
    uint8_t healthIdx = 0;
    TimingHistogram tickHist;

    // The tick's extra bus group, and what it has done.
    UartSlot slot;
    TimingHistogram slotHist;
    uint32_t slotWorst = 0;
    uint32_t liveWrites = 0, liveFailures = 0, liveRetries = 0;

    int64_t heatUs = 0;          // the thermal models last accumulated
    uint32_t heatSavedMs = 0;
    bool boosting = false;       // either wheel granted, as last logged
    uint32_t boostSinceMs = 0;

    const char *refusal = "";
} S;

// Both motors' heat, carried across a warm reset in memory the boot does not
// clear, as ulog carries its log. A reset is seconds, not the minutes the
// motors take to cool, so starting over from BOOT_H after one would undersell
// a hot motor. The check word catches a power-on's random contents and a copy
// the reset cut in half; either way the model starts from BOOT_H.
struct RetainedHeat {
    uint32_t magic;
    float h[DRIVE_NWHEELS];
    uint32_t check;
};
constexpr uint32_t HEAT_MAGIC = 0x48454154;   // "HEAT"

uint32_t heatCheck(const RetainedHeat &r) {
    uint32_t a, b;
    memcpy(&a, &r.h[0], sizeof a);
    memcpy(&b, &r.h[1], sizeof b);
    return ~(r.magic ^ a ^ ((b << 13) | (b >> 19)));
}

RTC_NOINIT_ATTR RetainedHeat retainedHeat;

// The same words wherever a flat pack is the reason: enable, clear and motion.
const char *const BATTERY_REFUSAL = "battery below its cutoff -- charge or swap the pack; clear once it recovers";

// drive.h's wheel codes are StepperServo's own, and the robot-level ones must
// never land on top of a wheel's.
static_assert(DRIVE_FAULT_DRIVER == (int)StepperServo::FAULT_DRIVER && DRIVE_FAULT_BATTERY > DRIVE_FAULT_DRIVER,
              "drive_fault_t no longer lines up with StepperServo::Fault");
// The status and the transports report BoostPolicy's bits as they are.
static_assert(DRIVE_BOOST_MANUAL == BoostPolicy::MANUAL && DRIVE_BOOST_START == BoostPolicy::START &&
                  DRIVE_BOOST_RECOVERY == BoostPolicy::RECOVERY && DRIVE_BOOST_LOAD == BoostPolicy::LOAD,
              "DRIVE_BOOST_* no longer lines up with BoostPolicy::Reason");
static_assert(DRIVE_BOOST_LIMIT_HEAT == BoostPolicy::LIMIT_HEAT && DRIVE_BOOST_LIMIT_DERATE == BoostPolicy::LIMIT_DERATE &&
                  DRIVE_BOOST_LIMIT_SUPPLY == BoostPolicy::LIMIT_SUPPLY && DRIVE_BOOST_LIMIT_OFF == BoostPolicy::LIMIT_OFF,
              "DRIVE_BOOST_LIMIT_* no longer lines up with BoostPolicy::Limit");
static_assert(DRIVE_NWHEELS == 2, "the retained heat and the slot scheduler are written for two wheels");

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

// A manual boost belongs to the command that asked for it, so it ends with
// every command: stop, a fault, a cutoff, a demo or a calibration starting.
void cancelCommands() {
    S.cmdActive = false;
    S.cmdV = S.cmdW = 0;
    for (int i = 0; i < DRIVE_NWHEELS; i++) S.whActive[i] = false;
    for (Wheel *w : wheels) w->boost.cancel(BoostPolicy::MANUAL);
}

// EN is one pin for both drivers, so energising is all-or-nothing in hardware.
// Every driver's VACTUAL is zeroed BEFORE the pin drops: the register survives
// an MCU reset even though the power stage was off, and one live velocity would
// lurch the whole robot the instant it is energised. Disabling runs the other
// way round -- cut the power stage first, tidy up after.
//
// The torque policies start over each time. begin() has just programmed the
// base pair; BoostPolicy starts there too, with the standstill it looks for
// already long enough, so the first move after an enable gets its START
// boost. The derate keeps its level -- a driver does not cool by being
// re-enabled -- and one still hot at begin() starts at level 2 at least.
bool enableDrivers(bool on) {
    if (on) {
        for (Wheel *w : wheels) w->gen.setEnabled(true);
        for (Wheel *w : wheels) {
            if (!w->gen.enabled() || !w->gen.ok() || S.pendingEstop) {
                enableDrivers(false);
                return false;
            }
        }
        gpio_set_level(PIN_EN, 0);
        S.driversOn = true;
        delayMs(20);   // let the TMC2209s come out of standby
        const uint32_t now = millis();
        for (Wheel *w : wheels) {
            w->servo.resyncSlip();
            w->boost.reset(now - BoostPolicy::START_STILL_MS);
            const uint8_t level = w->derate.level();
            w->derate.reset(w->gen.hot() && level < 2 ? 2 : level);
            w->lastMovingMs = now;   // as if just stopped: the thermal model errs hot
            w->livePending = false;
        }
    } else {
        gpio_set_level(PIN_EN, 1);
        for (Wheel *w : wheels) w->servo.enableDriver(false);
        S.driversOn = false;
        cancelCommands();
        for (Wheel *w : wheels) {
            w->boost.reset(millis());
            w->livePending = false;
        }
    }
    return true;
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

const char *const DERATE_TEXT[] = {"none", "no boost", "base current at 75%", "base current at 50%"};

// Bench: whether debug otpw is feeding this wheel's samples now. An injection
// ends by itself, and says so.
bool otpwInjected(Wheel &w, uint32_t now) {
    if (w.otpwInjecting && (int32_t)(w.otpwInjectUntil - now) <= 0) {
        w.otpwInjecting = false;
        ESP_LOGW(TAG, "BENCH: wheel %s OTPW injection over", w.name);
    }
    return w.otpwInjecting;
}

// CS_ACTUAL is the driver saying which current it is using, the only such
// word there is. While the wheel runs in SpreadCycle it must be IRUN: anything
// else is a live write that did not land as believed. Not at a standstill or
// in StealthChop (the driver reduces or regulates it there), and not in the
// first CS_SETTLE_MS after a write.
void checkCsActual(Wheel &w, uint32_t now) {
    const bool stealth = w.drvStatus & (1UL << 30), stst = w.drvStatus & (1UL << 31);
    if (!S.driversOn || !w.gen.enabled() || stealth || stst || w.gen.rate() == 0 ||
        now - w.lastLiveWriteMs <= CS_SETTLE_MS || w.csActual == w.gen.liveRun()) return;
    w.csMismatch++;
    if (w.csWarned && now - w.csWarnMs < CS_WARN_MS) return;
    w.csWarned = true;
    w.csWarnMs = now;
    ESP_LOGW(TAG, "wheel %s: CS_ACTUAL %u while moving, but IRUN %u was written (%lu so far) -- "
                  "a current write the driver did not take?",
             w.name, w.csActual, w.gen.liveRun(), (unsigned long)w.csMismatch);
}

void pollDriver(Wheel &w) {
    // Short timeout keeps an absent driver from blocking the 200 Hz loop for 40 ms.
    auto dr = tmc.read(w.gen.address(), Tmc2209Uart::DRVSTATUS, 3);
    auto gs = dr.st == Tmc2209Uart::OK
        ? tmc.read(w.gen.address(), Tmc2209Uart::GSTAT, 3) : dr;
    w.driverStatusOk = dr.st == Tmc2209Uart::OK && gs.st == Tmc2209Uart::OK;
    const uint32_t now = millis();
    if (w.driverStatusOk) {
        w.drvStatus = dr.value;
        w.gstat = gs.value;
        w.driverSampleMs = now;
        w.haveDriverSample = true;
        w.csActual = (uint8_t)((dr.value >> 16) & 31);

        // Soft: the ~120 C pre-warning lowers current (OtpwDerate) instead of
        // cutting EN, which would let the wheels freewheel down whatever hill
        // heated the driver. Only a sample that arrived counts; a failed read
        // is the hard path's.
        const uint32_t injected = otpwInjected(w, now) ? VelGen::DRV_OTPW : 0;
        w.otpw = ((w.drvStatus | injected) & VelGen::DRV_SOFT) != 0;
        const uint8_t before = w.derate.level();
        const uint8_t level = w.derate.sample(w.otpw, now);
        if (level > before) {
            ESP_LOGW(TAG, "wheel %s: driver %s (DRV_STATUS 0x%08lX%s) -- derate level %u: %s",
                     w.name, before ? "still at its temperature pre-warning" : "temperature pre-warning, ~120 C",
                     (unsigned long)w.drvStatus, injected ? ", OTPW injected" : "", level, DERATE_TEXT[level]);
        } else if (level < before) {
            ESP_LOGI(TAG, "wheel %s: driver pre-warning clear %lu s -- derate level %u: %s", w.name,
                     (unsigned long)(OtpwDerate::RESTORE_MS / 1000), level, DERATE_TEXT[level]);
        }
        checkCsActual(w, now);
    }
    // Hard: a failed read, a reset or driver error in GSTAT, overtemperature
    // shutdown, a short, or t143 and above disable both drivers. Open-load
    // flags are diagnostic only.
    if (!w.driverStatusOk || (w.gstat & 7) || (w.drvStatus & VelGen::DRV_HARD)) {
        w.gen.invalidate();
        if (S.driversOn) {
            ESP_LOGE(TAG, "driver %s: UART %s GSTAT 0x%02lX DRV_STATUS 0x%08lX -- disabling both",
                     w.name, w.driverStatusOk ? "ok" : "failed",
                     (unsigned long)w.gstat, (unsigned long)w.drvStatus);
            // Cut EN before any further UART I/O; a bus failure cannot stop VACTUAL.
            gpio_set_level(PIN_EN, 1);
            w.servo.raiseFault(StepperServo::FAULT_DRIVER);
            demo.stop();
            enableDrivers(false);
        }
    }
}

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

// Separate UART and encoder health transactions so they do not accumulate in
// one 5 ms servo tick: uartSlot() runs one step every UartSlot::HEALTH_MS, so
// each sensor/driver still gets checked every 500 ms.
void pollHealthStep() {
    Wheel &w = *wheels[S.healthIdx / 2];
    if (S.healthIdx & 1) pollDriver(w);
    else pollHealth(w);
    S.healthIdx = (S.healthIdx + 1) % 4;
}

// Freeze each driver's latest health sample as the fault-time copy the
// status reports show next to the live one.
void snapshotDriverSamples() {
    for (Wheel *o : wheels) {
        o->faultDriverStatusOk = o->driverStatusOk;
        o->faultDrvStatus = o->drvStatus;
        o->faultGstat = o->gstat;
        o->faultDriverAgeMs = millis() - o->driverSampleMs;
    }
}

void latchFault(uint8_t idx) {
    Wheel &w = *wheels[idx];
    S.faultLatched = true;
    S.faultWheel = idx;
    S.faultCode = w.servo.fault();
    snapshotDriverSamples();
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
        if (S.driversOn && !w.gen.ok()) {
            gpio_set_level(PIN_EN, 1);
            w.servo.raiseFault(StepperServo::FAULT_DRIVER);
            demo.stop();
            enableDrivers(false);
        }
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

// A pack below its cutoff latches a robot-level fault, and unlike a wheel
// fault it keeps the power stage on: both wheels ramp to a stop at decel_tps2
// and hold there with EN low. Cutting EN would let the robot freewheel down
// the slope that probably drained the pack. Holding costs ~5 W until the
// pack's own BMS acts, which is its job, not ours.
//
// Polled, not called back: battery_state() copies one field under the
// battery's spinlock, cheap enough for every tick (never from an ISR). Until
// battery_init() has run it says NONE, which never stops the robot.
void checkSupply() {
    if (S.faultLatched || battery_state() != BATT_CUTOFF) return;
    S.faultLatched = true;
    S.faultCode = DRIVE_FAULT_BATTERY;   // faultWheel keeps whatever it was: no wheel did this
    snapshotDriverSamples();
    demo.stop();
    cancelCommands();
    for (Wheel *w : wheels) {
        // A closed loop brakes through the servo's own velocity ramp and then
        // holds; an open-loop spin has no ramp to use and stops where it is.
        if (w->servo.servoOn()) w->servo.setVelocityTps(0);
        else w->servo.spin(0);
    }
    ESP_LOGE(TAG, "FAULT battery: %.2f V is below the %.2f V %s cutoff -- both wheels ramping to a stop and "
                  "holding with the drivers on; charge or swap the pack, 'faults clear' once it recovers",
             battery_voltage(), battery_cut_v(), battery_pack_name());
}

// -------------------------------------------------------------------- torque
//
// Every tick, drivers on or off, each wheel's thermal model learns what
// current its motor had since the last tick, its BoostPolicy says what the
// driver should have next (boosted, ramping back, derated or base), and a pair
// that differs from what the driver holds is left pending for uartSlot().
// Nothing here touches the bus.

// The driver's own standstill reduction, as ThermalModel::inferMa() wants it:
// 2^20 + TPOWERDOWN x 2^18 clocks of this chip's oscillator from the last step
// to the first reduction, then IHOLDDELAY x 2^18 clocks per CS step, both
// stretched by INFER_MARGIN so the model believes in the higher current a
// little longer than the driver delivers it. ~568 and ~192 ms on wheel A at
// IHOLDDELAY 8.
uint32_t standstillMs(const Wheel &w) {
    const float clocks = 1048576.0f + VelGen::TPOWERDOWN * 262144.0f;
    return (uint32_t)(clocks / (VelGen::FCLK * w.gen.clockGain()) * 1000.0f * INFER_MARGIN);
}
uint32_t reductionStepMs(const Wheel &w) {
    return (uint32_t)(w.gen.holdDelay() * 262144.0f / VelGen::FCLK * 1000.0f * INFER_MARGIN);
}

// What the motor has been getting, as well as the drive can tell: the model's
// inference from the pair last written and how long the step generator has
// been still, or CS_ACTUAL from a recent DRV_STATUS sample where that is
// higher.
float motorMa(Wheel &w, uint32_t now) {
    const bool energised = S.driversOn && w.gen.enabled();
    const bool moving = w.gen.rate() != 0;
    if (moving) w.lastMovingMs = now;
    float ma = ThermalModel::inferMa(energised, moving, moving ? 0 : now - w.lastMovingMs, w.gen.liveRun(),
                                     w.gen.liveHold(), standstillMs(w), reductionStepMs(w));
    if (energised && w.haveDriverSample && now - w.driverSampleMs < CS_FRESH_MS)
        ma = fmaxf(ma, MotorCurrent::milliamps(w.csActual));
    return ma;
}

// Heat for the real time since the last call, whatever filled it: one tick, a
// late one, or a whole calibration. Not the servos' dt, which stops at 50 ms.
void thermalStep() {
    const int64_t nowUs = esp_timer_get_time();
    const float dtS = (float)(nowUs - S.heatUs) * 1e-6f;
    S.heatUs = nowUs;
    const uint32_t now = millis();
    for (Wheel *w : wheels) w->thermal.accumulate(dtS, motorMa(*w, now));
}

void storeHeat() {
    retainedHeat.magic = HEAT_MAGIC;
    for (int i = 0; i < DRIVE_NWHEELS; i++) retainedHeat.h[i] = wheels[i]->thermal.heat();
    retainedHeat.check = heatCheck(retainedHeat);
}

void saveHeat(uint32_t now) {
    if (now - S.heatSavedMs < HEAT_SAVE_MS) return;
    S.heatSavedMs = now;
    storeHeat();
}

// At boot: the heat carried over a warm reset if there is a good copy, else
// ThermalModel::BOOT_H, the "most of the way to rated" guess for a motor whose
// history is unknown.
void restoreHeat() {
    const esp_reset_reason_t why = esp_reset_reason();
    bool ok = why != ESP_RST_POWERON && retainedHeat.magic == HEAT_MAGIC &&
              retainedHeat.check == heatCheck(retainedHeat);
    for (float h : retainedHeat.h) ok = ok && isfinite(h) && h >= 0 && h < 4;
    for (int i = 0; i < DRIVE_NWHEELS; i++) wheels[i]->thermal.reset(ok ? retainedHeat.h[i] : ThermalModel::BOOT_H);
    if (ok) {
        ESP_LOGI(TAG, "motor heat carried over the reset: A %.2f, B %.2f", wheelA.thermal.heat(), wheelB.thermal.heat());
    } else {
        ESP_LOGI(TAG, "motor heat assumed %.2f on both (%s)", ThermalModel::BOOT_H,
                 why == ESP_RST_POWERON ? "power-on" : "no good copy from before the reset");
    }
    S.heatUs = esp_timer_get_time();
    S.heatSavedMs = millis();
    storeHeat();   // a good copy from the first moment
}

// "manual+start", for the logs.
const char *reasonText(uint8_t r, char *buf, size_t n) {
    static const char *const NAMES[] = {"manual", "start", "recovery", "load"};
    size_t o = 0;
    buf[0] = 0;
    for (int i = 0; i < 4 && o < n; i++)
        if (r & (1u << i)) o += snprintf(buf + o, n - o, "%s%s", o ? "+" : "", NAMES[i]);
    return buf[0] ? buf : "none";
}

const char *limitText(uint8_t l) {
    if (l & BoostPolicy::LIMIT_OFF) return "boost_ma is off";
    if (l & BoostPolicy::LIMIT_DERATE) return "driver derating";
    if (l & BoostPolicy::LIMIT_HEAT) return "motor heat limit";
    if (l & BoostPolicy::LIMIT_SUPPLY) return "battery low";
    return "none";
}

// Robot-level: boost is on while either wheel has it granted.
void logBoost(uint32_t now) {
    bool on = false;
    uint8_t reasons = 0, limits = 0;
    for (Wheel *w : wheels) {
        on |= w->torque.boosting;
        reasons |= w->torque.reasons;
        limits |= w->torque.limitedBy;
    }
    if (on == S.boosting) return;
    S.boosting = on;
    char buf[40];
    if (on) {
        S.boostSinceMs = now;
        const char *who = !wheelB.torque.boosting ? "wheel A" : !wheelA.torque.boosting ? "wheel B" : "both wheels";
        ESP_LOGI(TAG, "boost on (%s), %s at %.0f mA", reasonText(reasons, buf, sizeof buf), who,
                 MotorCurrent::milliamps(wheelA.boost.config().boostCs));
    } else {
        ESP_LOGI(TAG, "boost off after %.1f s (%s)", (now - S.boostSinceMs) * 1e-3f,
                 !S.driversOn ? "drivers off" : limits ? limitText(limits) : "request over");
    }
}

// The thermal model's pause and resume, per wheel.
void logHeat(Wheel &w) {
    const bool limited = w.thermal.limited();
    if (limited == w.heatLimited) return;
    w.heatLimited = limited;
    const ThermalModel::Params &p = w.thermal.params();
    if (limited) {
        ESP_LOGW(TAG, "wheel %s: motor heat %.2f at the limit %.2f -- boost paused until it cools to %.2f",
                 w.name, w.thermal.heat(), p.limit, p.limit - p.hysteresis);
    } else {
        ESP_LOGI(TAG, "wheel %s: motor heat back down to %.2f -- boost available again", w.name, w.thermal.heat());
    }
}

void torqueUpdate() {
    thermalStep();
    const uint32_t now = millis();
    // Low is the warning before a cutoff: no extra draw from a pack that is
    // already sagging toward it.
    const bool inhibit = battery_state() >= BATT_LOW;
    for (Wheel *w : wheels) {
        BoostPolicy::Inputs in;
        in.nowMs = now;
        in.energised = S.driversOn && w->gen.enabled();
        in.moving = w->gen.rate() != 0;
        in.heatLimited = w->thermal.limited();
        in.supplyInhibit = inhibit;
        in.derate = w->derate.level();
        w->torque = w->boost.update(in);
        w->livePending = in.energised && w->gen.ok() &&
                         (w->torque.run != w->gen.liveRun() || w->torque.hold != w->gen.liveHold());
        logHeat(*w);
    }
    logBoost(now);
    saveHeat(now);
}

// BoostPolicy's settings follow the drive's: the base pair begin() programs,
// boost_ma and boost_start_ms. The thermal models take therm_tau_s and
// therm_lim, the rest at ThermalModel's defaults. Both apply at once.
void configureTorque() {
    BoostPolicy::Config bc;
    bc.boostCs = S.boostMa ? MotorCurrent::scale(S.boostMa) : 0;   // at or below base: off
    bc.startMs = (uint32_t)S.boostStartMs;
    ThermalModel::Params tp;
    tp.ratedMa = MotorCurrent::RATED_MA;
    tp.tauHeatS = S.thermTauS;
    tp.limit = S.thermLim;
    for (Wheel *w : wheels) {
        bc.baseRun = w->gen.runCurrent();
        bc.baseHold = w->gen.holdCurrent();
        w->boost.configure(bc);
        w->thermal.configure(tp);
    }
}

// A wheel's pending pair, onto the driver. setLiveCurrent() retries once; a
// pair that still does not land has invalidated the driver, and the
// checkFaults() right after the slot cuts EN, as for any driver fault.
void liveWrite(Wheel &w, uint32_t now) {
    const uint8_t run = w.torque.run, hold = w.torque.hold;
    const uint32_t retries = w.gen.liveRetries();
    w.lastLiveWriteMs = now;
    const bool ok = w.gen.setLiveCurrent(run, hold);
    S.liveRetries += w.gen.liveRetries() - retries;
    if (ok) {
        S.liveWrites++;
        ESP_LOGD(TAG, "wheel %s: IRUN %u IHOLD %u", w.name, run, hold);
        return;
    }
    S.liveFailures++;
    ESP_LOGE(TAG, "wheel %s: current write IRUN %u IHOLD %u not acknowledged, twice -- driver invalidated",
             w.name, run, hold);
}

// The tick's one extra bus group, UartSlot's choice: a pending live-current
// write, else a due health step, else (Phase 3) an MSCNT read. servoUs is how
// long the tick has run so far; past UartSlot::BUDGET_US the group waits.
void uartSlot(uint32_t servoUs) {
    const uint32_t now = millis();
    UartSlot::Request rq;
    for (int i = 0; i < DRIVE_NWHEELS; i++) {
        const Wheel &w = *wheels[i];
        rq.live[i] = w.livePending;
        rq.raise[i] = w.torque.run > w.gen.liveRun() || w.torque.hold > w.gen.liveHold();
    }
    // Phase 3 (0.4.0): rq.mscnt = the load-angle tracker wants its MSCNT read.
    const UartSlot::Choice c = S.slot.next(now, servoUs, rq);
    if (c.group == UartSlot::NONE) return;
    const uint32_t t0 = micros();
    switch (c.group) {
        case UartSlot::LIVE: liveWrite(*wheels[c.wheel], now); break;
        case UartSlot::HEALTH: pollHealthStep(); break;
        default: break;   // UartSlot::MSCNT: the Phase 3 read goes here
    }
    const uint32_t took = micros() - t0;
    S.slotHist.add(took);
    if (took > S.slotWorst) S.slotWorst = took;
    checkFaults();
}

void noteEncoderRead(Wheel &w) {
    if (w.servo.readCount() == w.readsSeen) return;
    w.readsSeen = w.servo.readCount();
    w.readHist.add(w.servo.lastReadUs());
}

void updateSnapshot() {
    drive_status_t s = {};
    s.enabled = S.driversOn;
    s.faulted = S.faultLatched;
    s.fault = S.faultLatched ? S.faultCode : (uint8_t)DRIVE_FAULT_NONE;
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
    s.live_writes = S.liveWrites;
    s.live_write_failures = S.liveFailures;
    s.live_write_retries = S.liveRetries;
    s.slot_worst_us = S.slotWorst;
    s.slot_deferred = S.slot.deferred();
    s.uart_read_worst_us = tmc.worstReadUs();
    s.uart_write_worst_us = tmc.worstWriteUs();
    s.heat_limit = wheelA.thermal.params().limit;
    s.heat_resume = wheelA.thermal.params().limit - wheelA.thermal.params().hysteresis;
    const uint32_t now = millis();
    for (int i = 0; i < DRIVE_NWHEELS; i++) {
        Wheel &w = *wheels[i];
        drive_wheel_status_t &d = s.wheel[i];
        d.driver_ok = w.gen.ok();
        d.driver_status_ok = w.driverStatusOk;
        d.drv_status = w.drvStatus;
        d.gstat = w.gstat;
        d.driver_age_ms = millis() - w.driverSampleMs;
        d.fault_driver_status_ok = w.faultDriverStatusOk;
        d.fault_drv_status = w.faultDrvStatus;
        d.fault_gstat = w.faultGstat;
        d.fault_driver_age_ms = w.faultDriverAgeMs;
        d.run_ma = w.gen.runMilliamps();
        d.hold_ma = w.gen.holdMilliamps();
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
        d.decel_tps2 = w.servo.decelTps2;
        d.worst_read_us = w.servo.worstReadUs();
        d.live_run_ma = w.gen.liveRunMilliamps();
        d.live_hold_ma = w.gen.liveHoldMilliamps();
        d.live_run_cs = w.gen.liveRun();
        d.live_hold_cs = w.gen.liveHold();
        d.heat = w.thermal.heat();
        d.boost_reasons = w.torque.reasons;
        d.boost_limit = w.torque.limitedBy;
        d.boost_active = w.torque.boosting;
        d.heat_limited = w.thermal.limited();
        d.derate = w.derate.level();
        d.otpw = w.otpw;
        d.otpw_injected = w.otpwInjecting && (int32_t)(w.otpwInjectUntil - now) > 0;
        d.otpw_events = w.derate.events();
        d.cs_actual = w.csActual;
        d.cs_mismatch = w.csMismatch;
    }
    portENTER_CRITICAL(&snapMux);
    snap = s;
    portEXIT_CRITICAL(&snapMux);
}

// Polled by the blocking calibration at ~1 kHz. Doubles as the snapshot
// refresher while the tick loop is suspended. The motor heats during a
// calibration like any other time, so the thermal models keep counting; the
// current does not change until the tick loop is back.
bool calAbortFn() {
    static uint32_t n = 0;
    if ((++n % 50) == 0) {
        if (S.slot.healthDue(millis())) {
            S.slot.healthRan(millis());
            pollHealthStep();
            checkFaults();
        }
        checkSupply();   // a cutoff latches here too, and the latch aborts the run
        thermalStep();
        updateSnapshot();
    }
    return S.calAbort || S.pendingEstop || S.faultLatched;
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

        // The order below is the robot's: stop first, then the deadman, then
        // the servos on fresh encoder reads, then everything that judges or
        // follows what they did, and the bus traffic that is left last, where
        // the tick can see how much time it has.

        if (S.pendingEstop) {
            S.pendingEstop = false;
            demo.stop();
            enableDrivers(false);
            ESP_LOGW(TAG, "emergency stop: both drivers disabled");
        }

#if CONFIG_UBOT_BENCH_FAULTS
        if (S.wedgeMs) {
            // A loop stuck in a computation or a bus spin: busy, holding the
            // mutex, not feeding the watchdog, and not yielding either. Past
            // CONFIG_ESP_TASK_WDT_TIMEOUT_S the watchdog panics and resets the
            // chip, and only that lets EN float high -- until then a driver
            // keeps stepping at its last VACTUAL.
            uint32_t ms = S.wedgeMs;
            S.wedgeMs = 0;
            ESP_LOGW(TAG, "BENCH: wedging the control loop for %lu ms, not feeding the task watchdog", (unsigned long)ms);
            int64_t until = esp_timer_get_time() + (int64_t)ms * 1000;
            while (esp_timer_get_time() < until) {
            }
        }
#endif

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

        for (Wheel *w : wheels) {
            w->servo.update(dt);
            noteEncoderRead(*w);
        }
        // Phase 2 (0.3.1): recoveryTick() goes here, after both servos and
        // before checkFaults(). It samples the stall detectors on this tick's
        // encoder reads; a trip it may not handle raises FAULT_SLIP for
        // checkFaults() to latch in the same tick. Its boost hook is
        //   wheels[i]->boost.request(BoostPolicy::RECOVERY, millis(), ms)
        // so torqueUpdate() and uartSlot() below raise the current in this
        // tick, before the servos' next update() writes the snapped VACTUAL.
        checkFaults();
        demo.update();
        checkSupply();
        torqueUpdate();
        uartSlot(micros() - t0);   // after the servos' own bus traffic, within what the tick has left

        updateSnapshot();
        xSemaphoreGive(S.mtx);

        uint32_t took = micros() - t0;
        if (took > S.tickWorst) S.tickWorst = took;
        S.tickHist.add(took);
        S.tickCount++;
    }
}

void tickerCb(void *) {
    if (S.task) xTaskNotifyGive(S.task);
}

void logCurrent() {
    ESP_LOGI(TAG, "digital current requested %d/%d mA run/hold; programmed %.0f/%.0f mA RMS "
                  "(IRUN %u IHOLD %u, R110, vsense=0), motor limit %d mA; %s",
             S.runMa, S.holdMa, wheelA.gen.runMilliamps(), wheelA.gen.holdMilliamps(),
             wheelA.gen.runCurrent(), wheelA.gen.holdCurrent(), MotorCurrent::MAX_MA,
             wheelA.gen.spreadCycle() ? "SpreadCycle" : "StealthChop with optional handover");
    const BoostPolicy::Config &bc = wheelA.boost.config();
    if (bc.boostCs > bc.baseRun) {
        ESP_LOGI(TAG, "boost to %.0f mA (IRUN %u) on request and for %d ms leaving a standstill; "
                      "motor heat limit %.2f, back from %.2f, tau %.0f s",
                 MotorCurrent::milliamps(bc.boostCs), bc.boostCs, S.boostStartMs, S.thermLim,
                 wheelA.thermal.params().limit - wheelA.thermal.params().hysteresis, S.thermTauS);
    } else {
        ESP_LOGI(TAG, "boost off (boost_ma %d)", S.boostMa);
    }
}

void loadSettings() {
    S.signA = settings_get_i32("sign_a", +1) < 0 ? -1 : +1;
    S.signB = settings_get_i32("sign_b", -1) < 0 ? -1 : +1;
    S.aIsLeft = settings_get_i32("a_left", 0) != 0;
    S.trackM = settings_get_f32("track_m", 0.263f);
    float vmax = constrain(settings_get_f32("vmax_tps", 0.3f), 0.05f, VMAX_LIMIT);
    float accel = settings_get_f32("accel_tps2", 1.0f);
    accel = accel > 0.0f ? fminf(accel, ACCEL_LIMIT) : 1.0f;  // also catches NaN
    float decel = constrain(settings_get_f32("decel_tps2", 2.0f), 0.2f, ACCEL_LIMIT);
    // Measured 2026-08-30/31 on the two drivers this robot was built with.
    // Calibration overwrites these per chip; they are only the starting point.
    float gainA = settings_get_f32(wheelA.gainKey, 1.0158f);
    float gainB = settings_get_f32(wheelB.gainKey, 1.0091f);
    bool invA = settings_get_i32(wheelA.invKey, 0) != 0;
    bool invB = settings_get_i32(wheelB.invKey, 1) != 0;
    // New keys deliberately supersede legacy irun/ihold/iscale/rsense. Those
    // raw settings cannot safely migrate to mA without knowing the old VREF.
    S.runMa = settings_get_i32("run_ma", MotorCurrent::DEFAULT_RUN_MA);
    S.holdMa = settings_get_i32("hold_ma", MotorCurrent::DEFAULT_HOLD_MA);
    if (!MotorCurrent::valid(S.runMa, S.holdMa)) {
        ESP_LOGW(TAG, "invalid stored current profile; using 1200/600 mA");
        S.runMa = MotorCurrent::DEFAULT_RUN_MA;
        S.holdMa = MotorCurrent::DEFAULT_HOLD_MA;
    }
    int32_t idelay = constrain(settings_get_i32("iholddly", IHOLD_DELAY_DEFAULT), (int32_t)0, (int32_t)15);
    bool spread = settings_get_i32("spread", 1) != 0;
    float pwmthrs = settings_get_f32("pwmthrs", 0.0f);
    if (!isfinite(pwmthrs) || pwmthrs < 0) pwmthrs = 0;
    // Torque. A stored value out of range falls back to its default, never to
    // a neighbour of the bad one.
    S.boostMa = settings_get_i32("boost_ma", MotorCurrent::BOOST_MAX_MA);
    if (!MotorCurrent::validBoost(S.runMa, S.boostMa)) {
        ESP_LOGW(TAG, "stored boost_ma %d does not fit run_ma %d; using %d", S.boostMa, S.runMa,
                 MotorCurrent::BOOST_MAX_MA);
        S.boostMa = MotorCurrent::BOOST_MAX_MA;
    }
    S.boostStartMs = settings_get_i32("boost_start_ms", BOOST_START_DEFAULT_MS);
    if (S.boostStartMs < 0 || S.boostStartMs > 5000) S.boostStartMs = BOOST_START_DEFAULT_MS;
    S.thermTauS = settings_get_f32("therm_tau_s", THERM_TAU_DEFAULT_S);
    if (!(S.thermTauS >= 60.0f && S.thermTauS <= 3600.0f)) S.thermTauS = THERM_TAU_DEFAULT_S;   // NaN too
    S.thermLim = settings_get_f32("therm_lim", THERM_LIM_DEFAULT);
    if (!(S.thermLim >= 0.5f && S.thermLim <= 1.30f)) S.thermLim = THERM_LIM_DEFAULT;
    for (Wheel *w : wheels) {
        w->servo.vmaxTps = vmax;
        w->servo.accelTps2 = accel;
        w->servo.decelTps2 = decel;
        w->gen.setCurrentMa(S.runMa, S.holdMa, idelay);
        w->gen.setSpreadCycle(spread);
        w->gen.setSpreadAboveRate(pwmthrs);
    }
    wheelA.gen.setInvert(invA);
    wheelB.gen.setInvert(invB);
    wheelA.gen.presetClockGain(gainA);
    wheelB.gen.presetClockGain(gainB);
    configureTorque();
}

Wheel *wheelArg(drive_wheel_t w) {
    return (w == DRIVE_WHEEL_A || w == DRIVE_WHEEL_B) ? wheels[w] : nullptr;
}

const char *const PARAM_NAMES[] = {"kp", "vmax", "accel", "decel", "vmin", "tol", "maxslip", "ratio", "gain", "micro"};
// Each is also its NVS key. constexpr so the check below runs at compile time:
// otherwise a key NVS cannot hold only fails on the robot, when someone first
// tries to store it, and until then its reads quietly come back empty (or,
// NVS comparing only 15 characters, with another key's value).
constexpr const char *SETTING_NAMES[] = {"sign_a", "sign_b", "a_left", "track_m", "vmax_tps", "accel_tps2",
                                         "decel_tps2", "run_ma", "hold_ma", "iholddly", "spread", "pwmthrs",
                                         "boost_ma", "boost_start_ms", "therm_tau_s", "therm_lim"};

constexpr size_t keyLength(const char *s) {
    size_t n = 0;
    while (s[n]) n++;
    return n;
}
constexpr bool settingKeysFit() {
    for (const char *k : SETTING_NAMES)
        if (keyLength(k) < 1 || keyLength(k) > SETTINGS_KEY_MAX) return false;
    return true;
}
static_assert(settingKeysFit(), "every SETTING_NAMES entry is an NVS key: 1 to 15 characters");

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
#if CONFIG_UBOT_BENCH_FAULTS
    ESP_LOGW(TAG, "BENCH FAULT INJECTION BUILD -- 'debug wedge' stalls the control loop and 'debug otpw' "
                  "fakes a hot driver, on purpose; never drive this build outdoors");
#endif
    if (!S.mtx) S.mtx = xSemaphoreCreateMutex();
    if (!S.mtx) return ESP_ERR_NO_MEM;

    loadSettings();
    restoreHeat();

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
            ESP_LOGE(TAG, "wheel %s: TMC2209 at address %u configuration/health verification failed (initial probe: %s)", w->name,
                     w->gen.address(), Tmc2209Uart::statusName(w->gen.lastStatus()));
        }
    }
    if (!wheelA.gen.ok() || !wheelB.gen.ok()) {
        ESP_LOGW(TAG, "check: wire on module pin 4 (RX), 1k between TX and RX, motor power on "
                      "(the TMC2209 is deaf on UART without VMOT), VIO to 3V3");
    }
    logCurrent();

    for (Wheel *w : wheels) {
        bool ok = w->enc.begin();
        uint8_t st = ok ? w->enc.readStatus() : 0;
        if (ok) {
            ESP_LOGI(TAG, "wheel %s: AS5600 on %s I2C, magnet %s, agc %u (0..128, aim ~64)",
                     w->name, w->enc.busKind(), AS5600::magnetText(st), w->enc.readAGC());
        } else {
            // Say which half is at fault where the bus can tell us. Idle high on
            // both wires means the pull-ups are fine and simply nothing answered,
            // so look at the device end -- power, connector, a broken wire. Either
            // line stuck low is a fault on the wire itself and retrying never
            // fixes it.
            int idle = w->enc.busIdleLevels();
            if (idle < 0) {
                ESP_LOGE(TAG, "wheel %s: no AS5600 answering on the %s bus", w->name,
                         w->enc.busKind());
            } else {
                ESP_LOGE(TAG, "wheel %s: no AS5600 answering on the %s bus -- idle SDA=%d SCL=%d (%s)",
                         w->name, w->enc.busKind(), (idle >> 1) & 1, idle & 1,
                         idle == 3 ? "wires are up, nothing answered: check the encoder's power and connector"
                                   : "a wire is held low: check for a short or a swapped connector");
            }
        }
        w->servo.stepsPerCount = nominalStepsPerCount(w->microsteps);
        w->servo.begin();
        pollDriver(*w);
        pollHealth(*w);
    }

    ESP_LOGI(TAG, "EN=GPIO%d shared, UART %d baud, control %d Hz, %.1f steps/out-rev, %.6f steps/count",
             CONFIG_UBOT_PIN_EN, CONFIG_UBOT_TMC_BAUD, CONFIG_UBOT_CONTROL_HZ,
             stepsPerOutRev(MICROSTEPS_DEFAULT), nominalStepsPerCount(MICROSTEPS_DEFAULT));
    ESP_LOGI(TAG, "robot frame: sign_a %+d sign_b %+d, wheel A is %s, track %.3f m, vmax %.2f m/s",
             S.signA, S.signB, S.aIsLeft ? "left" : "right", S.trackM, vmaxMps());
    ESP_LOGI(TAG, "drivers start disabled -- 'enable' energises both, 'cal A' / 'cal B' measure the clocks");

    S.slot.reset(millis());   // everything was polled just now
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

static TaskHandle_t maintenanceOwner;
static bool updating;
static volatile bool maintenanceCancelled;
static bool interlocked() { return updating || (maintenanceOwner && (maintenanceCancelled || maintenanceOwner != xTaskGetCurrentTaskHandle())); }
static esp_err_t interlockRefusal() { return refuse(updating ? "firmware update in progress" : "maintenance motion owns the robot"); }
esp_err_t drive_maintenance_claim(bool ota) {
    if (!lock()) return ESP_ERR_INVALID_STATE;
    bool moving = S.cmdActive || S.calBusy || S.calReq >= 0 || demo.running();
    drive_status_t status; drive_get_status(&status);
    for (auto &w : status.wheel) moving |= fabsf(w.rate_sps) > 0.5f || (w.loop_closed && !w.velocity_mode && !w.at_target);
    if (maintenanceOwner || updating || moving) { unlock(); return ESP_ERR_INVALID_STATE; }
    if (ota) { updating = true; enableDrivers(false); }
    else { maintenanceOwner = xTaskGetCurrentTaskHandle(); maintenanceCancelled = false; }
    unlock(); return ESP_OK;
}
bool drive_maintenance_release(bool ota) {
    if (!lock()) return false;
    if (ota) updating = false; else maintenanceOwner = NULL;
    unlock(); return true;
}
void drive_maintenance_cancel(void) { maintenanceCancelled = true; }

esp_err_t drive_enable(bool on) {
    if (!lock()) return refuse("drive is busy (calibrating)");
    if (on && interlocked()) { unlock(); return interlockRefusal(); }
    // Enabling clears a latched fault, so it has to wait for the pack as a
    // clear does. Disabling is never refused.
    if (on && battery_state() == BATT_CUTOFF) { unlock(); return refuse(BATTERY_REFUSAL); }
    if (on) {
        if (S.driversOn) { unlock(); return ESP_OK; }
        gpio_set_level(PIN_EN, 1);
        bool allOk = true;
        for (Wheel *w : wheels) {
            // Always reapply, even if the MCU missed a motor-power cycle.
            if (!w->gen.begin(w->microsteps)) allOk = false;
            pollDriver(*w);
            if (!w->gen.ok()) allOk = false;
        }
        if (!allOk) {
            unlock();
            return refuse("driver configuration or health could not be verified -- not energising");
        }
        for (Wheel *w : wheels) w->servo.clearFault();
        S.faultLatched = false;
        S.faultCode = DRIVE_FAULT_NONE;
        if (!enableDrivers(true)) {
            unlock();
            return refuse("could not verify zero velocity before enabling");
        }
        logCurrent();
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
    // While the pack is cut off, 'faults clear' is refused too; say what is.
    if (S.faultLatched)
        return refuse(battery_state() == BATT_CUTOFF ? BATTERY_REFUSAL : "a fault is latched -- 'faults clear' first");
    if (demo.running()) return refuse("a demo is running -- 'demo stop' first");
    return ESP_OK;
}

esp_err_t drive_set_velocity_ex(float v_mps, float w_radps, uint32_t hold_ms, uint32_t flags) {
    if (!(fabsf(v_mps) < 100.0f) || !(fabsf(w_radps) < 100.0f)) return ESP_ERR_INVALID_ARG;
    if (!lock()) return refuse("drive is busy (calibrating)");
    if (interlocked()) { unlock(); return interlockRefusal(); }
    esp_err_t err = motionPrecheck();
    if (err != ESP_OK) { unlock(); return err; }
    limitRobotVelocity(v_mps, w_radps);
    applyRobotVelocity(v_mps, w_radps);
    S.cmdV = v_mps;
    S.cmdW = w_radps;
    S.cmdActive = (v_mps != 0 || w_radps != 0);
    S.cmdExpires = hold_ms ? esp_timer_get_time() + (int64_t)hold_ms * 1000 : 0;
    for (int i = 0; i < DRIVE_NWHEELS; i++) S.whActive[i] = false;
    // A manual boost lasts as long as the command that carries it, which a
    // joystick renews with every frame, and the first frame without the flag
    // ends it. A console command held until 'stop' (hold 0) still gets no
    // more than a minute.
    const uint32_t now = millis();
    const uint32_t boostMs = hold_ms && hold_ms < BOOST_MANUAL_MAX_MS ? hold_ms : BOOST_MANUAL_MAX_MS;
    for (Wheel *w : wheels) {
        if (flags & DRIVE_CMD_BOOST) w->boost.request(BoostPolicy::MANUAL, now, boostMs);
        else w->boost.cancel(BoostPolicy::MANUAL);
    }
    unlock();
    return ESP_OK;
}

esp_err_t drive_set_velocity(float v_mps, float w_radps, uint32_t hold_ms) {
    return drive_set_velocity_ex(v_mps, w_radps, hold_ms, 0);
}

esp_err_t drive_set_normalized_ex(float v, float w, uint32_t hold_ms, uint32_t flags) {
    if (!(fabsf(v) <= 1.5f) || !(fabsf(w) <= 1.5f)) return ESP_ERR_INVALID_ARG;
    v = constrain(v, -1.0f, 1.0f);
    w = constrain(w, -1.0f, 1.0f);
    return drive_set_velocity_ex(v * vmaxMps(), w * wmaxRadps(), hold_ms, flags);
}

esp_err_t drive_set_normalized(float v, float w, uint32_t hold_ms) {
    return drive_set_normalized_ex(v, w, hold_ms, 0);
}

esp_err_t drive_boost_manual(uint32_t ms) {
    if (ms > BOOST_MANUAL_MAX_MS) return ESP_ERR_INVALID_ARG;
    if (!lock()) return refuse("drive is busy (calibrating)");
    // Ending one is never refused. Starting one is a mutation like any other,
    // and needs a power stage to boost.
    if (ms && interlocked()) { unlock(); return interlockRefusal(); }
    if (ms && !S.driversOn) { unlock(); return refuse("drivers are disabled -- 'enable' first"); }
    const uint32_t now = millis();
    for (Wheel *w : wheels) w->boost.request(BoostPolicy::MANUAL, now, ms);   // 0 cancels
    unlock();
    return ESP_OK;
}

esp_err_t drive_wheel_velocity(drive_wheel_t wi, float tps, uint32_t hold_ms) {
    Wheel *w = wheelArg(wi);
    if (!w) return ESP_ERR_INVALID_ARG;
    if (!lock()) return refuse("drive is busy (calibrating)");
    if (interlocked()) { unlock(); return interlockRefusal(); }
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
    if (interlocked()) { unlock(); return interlockRefusal(); }
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
    if (interlocked()) { unlock(); return interlockRefusal(); }
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
    if (interlocked()) { unlock(); return interlockRefusal(); }
    if (!S.driversOn) { unlock(); return refuse("drivers are disabled -- 'enable' first"); }
    if (demo.running()) { unlock(); return refuse("a demo is running -- 'demo stop' first"); }
    // The one motion path without motionPrecheck(), so the pack is checked
    // here: nothing moves on a pack below its cutoff.
    if (battery_state() == BATT_CUTOFF) { unlock(); return refuse(BATTERY_REFUSAL); }
    w->servo.spin(sps);
    S.whActive[wi] = false;
    unlock();
    return ESP_OK;
}

esp_err_t drive_wheel_loop(drive_wheel_t wi, bool closed) {
    Wheel *w = wheelArg(wi);
    if (!w) return ESP_ERR_INVALID_ARG;
    if (!lock()) return refuse("drive is busy (calibrating)");
    if (interlocked()) { unlock(); return interlockRefusal(); }
    if (closed && !w->gen.enabled()) { unlock(); return refuse("drivers are disabled -- 'enable' first"); }
    w->servo.servoOn(closed);
    unlock();
    return ESP_OK;
}

esp_err_t drive_wheel_zero(drive_wheel_t wi) {
    if (!lock()) return refuse("drive is busy (calibrating)");
    if (interlocked()) { unlock(); return interlockRefusal(); }
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
    if (interlocked()) { unlock(); return interlockRefusal(); }
    // Whatever latched, clearing now would hand a flat pack straight back to
    // the stick; checkSupply() would only latch it again a tick later.
    if (battery_state() == BATT_CUTOFF) { unlock(); return refuse(BATTERY_REFUSAL); }
    for (Wheel *w : wheels) {
        w->servo.clearFault();
        w->servo.resyncSlip();
    }
    S.faultLatched = false;
    S.faultCode = DRIVE_FAULT_NONE;
    updateSnapshot();
    unlock();
    ESP_LOGI(TAG, "faults cleared");
    return ESP_OK;
}

const char *drive_fault_name(uint8_t fault) {
    // Robot-level, so StepperServo has no name for it; same "name (reason)"
    // shape as the wheel faults.
    if (fault == DRIVE_FAULT_BATTERY)
        return "battery below cutoff (charge or swap the pack; clear it once the voltage recovers)";
    return StepperServo::faultName((StepperServo::Fault)fault);
}

// --- calibration ---

esp_err_t drive_calibrate(drive_wheel_t wi) {
    Wheel *w = wheelArg(wi);
    if (!w) return ESP_ERR_INVALID_ARG;
    if (!lock()) return refuse("drive is busy (calibrating)");
    if (interlocked()) { unlock(); return interlockRefusal(); }
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
    if (interlocked()) { unlock(); return interlockRefusal(); }
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
    else if (!strcmp(name, "decel")) {
        if (v > ACCEL_LIMIT) ESP_LOGW(TAG, "decel clamped to the measured limit %.1f turns/s^2", ACCEL_LIMIT);
        w.servo.decelTps2 = constrain(v, 0.1f, ACCEL_LIMIT);
    }
    else if (!strcmp(name, "vmin")) { w.servo.vminSps = fabsf(v); }
    else if (!strcmp(name, "tol")) { w.servo.tolCounts = (int32_t)fabsf(v); }
    else if (!strcmp(name, "maxslip")) { w.servo.slipLimit = (int32_t)fabsf(v); }
    else if (!strcmp(name, "ratio")) { w.servo.stepsPerCount = v; w.servo.resyncSlip(); }
    else if (!strcmp(name, "gain")) { w.gen.setClockGain(v); w.servo.resyncSlip(); }
    else if (!strcmp(name, "micro")) {
        if (S.driversOn) return refuse("disable drivers before changing microsteps");
        if (v < 1 || v > 256 || truncf(v) != v) return ESP_ERR_INVALID_ARG;
        if (!w.gen.setMicrosteps((uint16_t)v)) return ESP_ERR_INVALID_ARG;
        w.microsteps = (uint16_t)v;
        w.servo.stepsPerCount = nominalStepsPerCount(w.microsteps);
        w.servo.resyncSlip();
    }
    else return ESP_ERR_NOT_FOUND;
    return ESP_OK;
}

esp_err_t drive_param_set(drive_wheel_t wi, const char *name, float value) {
    if (!name || !isfinite(value)) return ESP_ERR_INVALID_ARG;
    if (!lock()) return refuse("drive is busy (calibrating)");
    if (interlocked()) { unlock(); return interlockRefusal(); }
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
    else if (!strcmp(name, "decel")) *value = w->servo.decelTps2;
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
    if (!name || !isfinite(value)) return ESP_ERR_INVALID_ARG;
    if (!lock()) return refuse("drive is busy (calibrating)");
    if (interlocked()) { unlock(); return interlockRefusal(); }
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
        // Any positive rate is usable, just slow; zero would never leave a standstill.
        if (value <= 0.0f) err = ESP_ERR_INVALID_ARG;
        else {
            float v = fminf(value, ACCEL_LIMIT);
            for (Wheel *w : wheels) w->servo.accelTps2 = v;
            err = settings_set_f32(name, v);
        }
    } else if (!strcmp(name, "decel_tps2")) {
        float v = constrain(value, 0.2f, ACCEL_LIMIT);
        for (Wheel *w : wheels) w->servo.decelTps2 = v;
        err = settings_set_f32(name, v);
    } else if (!strcmp(name, "run_ma") || !strcmp(name, "hold_ma") ||
               !strcmp(name, "iholddly") || !strcmp(name, "spread") || !strcmp(name, "pwmthrs")) {
        if (S.driversOn) {
            unlock();
            return refuse("disable drivers before changing current or chopper settings");
        }
        int run = S.runMa, hold = S.holdMa, delay = wheelA.gen.holdDelay();
        bool spread = wheelA.gen.spreadCycle();
        float threshold = wheelA.gen.spreadAboveRate();
        if (!strcmp(name, "run_ma") || !strcmp(name, "hold_ma")) {
            if (value < MotorCurrent::MIN_MA || value > MotorCurrent::MAX_MA || truncf(value) != value)
                err = ESP_ERR_INVALID_ARG;
            else if (!strcmp(name, "run_ma")) run = (int)value;
            else hold = (int)value;
        } else if (!strcmp(name, "iholddly")) {
            if (value < 0 || value > 15 || truncf(value) != value) err = ESP_ERR_INVALID_ARG;
            else delay = (int)value;
        } else if (!strcmp(name, "spread")) {
            if (value != 0 && value != 1) err = ESP_ERR_INVALID_ARG;
            else spread = value != 0;
        } else {
            if (value < 0 || value > VelGen::DEFAULT_MAX_RATE) err = ESP_ERR_INVALID_ARG;
            else threshold = value;
        }
        if (!MotorCurrent::valid(run, hold)) err = ESP_ERR_INVALID_ARG;
        // Boost is a current above run: a base current past it would make
        // boost a derate.
        if (err == ESP_OK && !MotorCurrent::validBoost(run, S.boostMa)) {
            unlock();
            return refuse("run_ma would be above boost_ma -- raise boost_ma first, or set it to 0 to turn boost off");
        }
        if (err == ESP_OK) {
            err = !strcmp(name, "pwmthrs") ? settings_set_f32(name, value)
                                          : settings_set_i32(name, (int32_t)value);
            if (err == ESP_OK) {
                S.runMa = run;
                S.holdMa = hold;
                for (Wheel *w : wheels) {
                    w->gen.setCurrentMa(run, hold, delay);
                    w->gen.setSpreadCycle(spread);
                    w->gen.setSpreadAboveRate(threshold);
                }
                configureTorque();
                logCurrent();
                ESP_LOGI(TAG, "stored; configuration will be verified at next enable");
            }
        }
    } else if (!strcmp(name, "boost_ma") || !strcmp(name, "boost_start_ms") ||
               !strcmp(name, "therm_tau_s") || !strcmp(name, "therm_lim")) {
        // Live, drivers on or off: the policies take a new setting at their
        // next update, up at once and down on the ramp.
        const char *range = nullptr;
        if (!strcmp(name, "boost_ma")) {
            if (truncf(value) != value || !MotorCurrent::validBoost(S.runMa, (int)value))
                range = "boost_ma takes 0 (boost off) or whole mA from run_ma up to 1768";
        } else if (!strcmp(name, "boost_start_ms")) {
            if (truncf(value) != value || value < 0 || value > 5000)
                range = "boost_start_ms takes 0 (no start boost) to 5000 ms";
        } else if (!strcmp(name, "therm_tau_s")) {
            if (value < 60.0f || value > 3600.0f) range = "therm_tau_s takes 60 to 3600 s";
        } else if (value < 0.5f || value > 1.30f) {
            range = "therm_lim takes 0.5 to 1.3 (1.0 = the motor's rated steady heat)";
        }
        if (range) {
            unlock();
            return refuse(range);
        }
        err = name[0] == 'b' ? settings_set_i32(name, (int32_t)value) : settings_set_f32(name, value);
        if (err == ESP_OK) {
            if (!strcmp(name, "boost_ma")) S.boostMa = (int)value;
            else if (!strcmp(name, "boost_start_ms")) S.boostStartMs = (int)value;
            else if (!strcmp(name, "therm_tau_s")) S.thermTauS = value;
            else S.thermLim = value;
            configureTorque();
            logCurrent();
        }
    } else if (!strcmp(name, "irun") || !strcmp(name, "ihold") ||
               !strcmp(name, "iscale") || !strcmp(name, "rsense")) {
        unlock();
        return refuse("legacy current settings are retired; use run_ma and hold_ma (100..1500, hold <= run)");
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
    else if (!strcmp(name, "decel_tps2")) *value = wheelA.servo.decelTps2;
    else if (!strcmp(name, "run_ma")) *value = S.runMa;
    else if (!strcmp(name, "hold_ma")) *value = S.holdMa;
    else if (!strcmp(name, "iholddly")) *value = wheelA.gen.holdDelay();
    else if (!strcmp(name, "spread")) *value = wheelA.gen.spreadCycle() ? 1 : 0;
    else if (!strcmp(name, "pwmthrs")) *value = wheelA.gen.spreadAboveRate();
    else if (!strcmp(name, "boost_ma")) *value = (float)S.boostMa;
    else if (!strcmp(name, "boost_start_ms")) *value = (float)S.boostStartMs;
    else if (!strcmp(name, "therm_tau_s")) *value = S.thermTauS;
    else if (!strcmp(name, "therm_lim")) *value = S.thermLim;
    else return ESP_ERR_NOT_FOUND;
    return ESP_OK;
}

esp_err_t drive_wheel_set_invert(drive_wheel_t wi, bool inv) {
    Wheel *w = wheelArg(wi);
    if (!w) return ESP_ERR_INVALID_ARG;
    if (!lock()) return refuse("drive is busy (calibrating)");
    if (interlocked()) { unlock(); return interlockRefusal(); }
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

// --- bench fault injection ---

esp_err_t drive_debug_wedge(uint32_t ms) {
#if CONFIG_UBOT_BENCH_FAULTS
    // Longer proves nothing more: the watchdog fires at 3 s.
    if (ms < 1 || ms > 10000) return ESP_ERR_INVALID_ARG;
    if (!lock()) return refuse("drive is busy (calibrating)");
    // Refused as any other mutation is: never during an update, where a
    // reset is the one thing that must not happen, and while a maintenance
    // job owns the robot, only from that job's own task.
    if (interlocked()) { unlock(); return interlockRefusal(); }
    S.wedgeMs = ms;
    unlock();
    return ESP_OK;
#else
    (void)ms;
    return ESP_ERR_NOT_SUPPORTED;
#endif
}

esp_err_t drive_debug_inject_otpw(drive_wheel_t wi, uint32_t ms) {
#if CONFIG_UBOT_BENCH_FAULTS
    Wheel *w = wheelArg(wi);
    if (!w || ms > OTPW_INJECT_MAX_MS) return ESP_ERR_INVALID_ARG;
    if (!lock()) return refuse("drive is busy (calibrating)");
    if (interlocked()) { unlock(); return interlockRefusal(); }
    // Only the samples lie; the chip is untouched, so the hard path and every
    // other flag still come from the real DRV_STATUS.
    w->otpwInjecting = ms != 0;
    w->otpwInjectUntil = millis() + ms;
    if (ms) ESP_LOGW(TAG, "BENCH: wheel %s DRV_STATUS samples read OTPW for the next %lu ms", w->name, (unsigned long)ms);
    else ESP_LOGW(TAG, "BENCH: wheel %s OTPW injection cancelled", w->name);
    unlock();
    return ESP_OK;
#else
    (void)wi;
    (void)ms;
    return ESP_ERR_NOT_SUPPORTED;
#endif
}

// --- observation ---

void drive_get_status(drive_status_t *out) {
    if (!out) return;
    portENTER_CRITICAL(&snapMux);
    *out = snap;
    portEXIT_CRITICAL(&snapMux);
}

void drive_reset_stats(void) {
    // Under the mutex when it can be had, so no tick is halfway through a
    // histogram; statistics are not worth waiting out a calibration for.
    bool locked = lock();
    S.tickWorst = 0;
    S.tickHist.reset();
    S.slotHist.reset();
    S.slotWorst = 0;
    S.slot.resetStats();
    S.liveWrites = S.liveFailures = S.liveRetries = 0;
    tmc.resetWorst();
    for (Wheel *w : wheels) {
        w->servo.resetWorstRead();
        w->readHist.reset();
        w->csMismatch = 0;
    }
    if (locked) unlock();
}

static void timingOf(const TimingHistogram &h, drive_timing_t *out) {
    out->count = h.count();
    out->p50_us = h.percentile(0.50);
    out->p99_us = h.percentile(0.99);
    out->max_us = h.max();
}

void drive_get_timings(drive_timings_t *out) {
    if (!out) return;
    timingOf(S.tickHist, &out->tick);
    for (int i = 0; i < DRIVE_NWHEELS; i++) timingOf(wheels[i]->readHist, &out->read[i]);
    timingOf(S.slotHist, &out->slot);
}

const char *drive_csv_header(void) {
    return "t_ms,pos,target,err,vel,steps,rate,slip,enc,agc,status,flags,"
           "bpos,btarget,berr,bvel,bsteps,brate,bslip,benc,bagc,bstatus,busus,"
           "batt_v,batt_st,"
           "arun,ahold,aboost,aheat,ader,aotpw,brun,bhold,bboost,bheat,bder,botpw";
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
    // batt_st is battery_state()'s number, 0 none .. 3 cutoff, so a capture
    // shows the sag that led up to a cutoff next to the wheels that caused it.
    // Then per wheel the live run/hold mA, the boost reasons (DRIVE_BOOST_*,
    // granted or not: the mA say whether), the heat, the derate level and OTPW.
    return snprintf(buf, n,
                    "%lu,%.4f,%.4f,%ld,%.3f,%ld,%.1f,%ld,%u,%u,0x%02X,0x%02X,"
                    "%.4f,%.4f,%ld,%.3f,%ld,%.1f,%ld,%u,%u,0x%02X,%lu,"
                    "%.2f,%d,"
                    "%.0f,%.0f,%u,%.3f,%u,%u,%.0f,%.0f,%u,%.3f,%u,%u",
                    (unsigned long)millis(),
                    a.pos_turns, a.target_turns, (long)a.err_counts, a.vel_tps, a.cmd_steps,
                    a.rate_sps, (long)a.slip_steps, a.raw_angle, a.agc, a.magnet_status, flags,
                    b.pos_turns, b.target_turns, (long)b.err_counts, b.vel_tps, b.cmd_steps,
                    b.rate_sps, (long)b.slip_steps, b.raw_angle, b.agc, b.magnet_status,
                    (unsigned long)b.worst_read_us,
                    battery_voltage(), battery_state(),
                    a.live_run_ma, a.live_hold_ma, a.boost_reasons, a.heat, a.derate, a.otpw ? 1u : 0u,
                    b.live_run_ma, b.live_hold_ma, b.boost_reasons, b.heat, b.derate, b.otpw ? 1u : 0u);
}

}  // extern "C"
