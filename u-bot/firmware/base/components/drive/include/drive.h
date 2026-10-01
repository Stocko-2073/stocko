#pragma once
// The drive, as the rest of the firmware sees it: two wheels behind one C API.
//
// Everything that moves the robot goes through here -- console, WebSocket, BLE
// -- and every motion command carries a hold time. When it lapses without a
// fresh command the wheels ramp to a stop. That is the deadman: a phone app
// that loses its link, a console that goes quiet, a task that wedges, all end
// in a stationary robot rather than a runaway.
//
// Units: robot-frame velocity is metres per second and radians per second
// (positive = anticlockwise seen from above). Wheel units are output-shaft
// turns and turns per second, as in DRIVE_MECHANISM.md.
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#include "esp_err.h"

#ifdef __cplusplus
extern "C" {
#endif

typedef enum { DRIVE_WHEEL_A = 0, DRIVE_WHEEL_B = 1, DRIVE_NWHEELS = 2, DRIVE_WHEEL_BOTH = 2 } drive_wheel_t;

// Codes 1 to 5 mirror StepperServo::Fault: each wheel reports its own, and the
// first to fault is also the latched drive_status_t.fault. DRIVE_FAULT_BATTERY
// is robot-level: it belongs to no wheel, so it only ever appears as
// drive_status_t.fault, with every wheel's own fault left at NONE.
typedef enum {
    DRIVE_FAULT_NONE = 0,
    DRIVE_FAULT_SLIP,      // shaft did not follow the commanded velocity
    DRIVE_FAULT_ENCODER,   // encoder stopped answering on the bus
    DRIVE_FAULT_MAGNET,    // encoder says there is no magnet
    DRIVE_FAULT_PEER,      // stopped because the other wheel faulted
    DRIVE_FAULT_DRIVER,    // reset, UART, overtemperature shutdown, short or undervoltage
    DRIVE_FAULT_BATTERY = 6,  // robot-level: the pack is below its cutoff; both wheels hold, drivers on
} drive_fault_t;

// Flags for drive_set_velocity_ex() / drive_set_normalized_ex().
//
// DRIVE_CMD_BOOST asks for boost current on both wheels for as long as this
// command holds (a manual boost). Every accepted command without it ends a
// manual boost, so a joystick that stops sending the flag has let go of it.
#define DRIVE_CMD_BOOST 0x01u

// Why a wheel is boosting: drive_wheel_status_t.boost_reasons, WS torque.boost.
#define DRIVE_BOOST_MANUAL   1u   // the operator: DRIVE_CMD_BOOST or drive_boost_manual()
#define DRIVE_BOOST_START    2u   // leaving a standstill of 0.5 s or more, for boost_start_ms
#define DRIVE_BOOST_RECOVERY 4u   // stall recovery (from 0.3.1)
#define DRIVE_BOOST_LOAD     8u   // the load angle nearing pull-out (from 0.4.0)

// What refused a requested boost: drive_wheel_status_t.boost_limit.
#define DRIVE_BOOST_LIMIT_HEAT   1u   // the thermal model is in its limited band
#define DRIVE_BOOST_LIMIT_DERATE 2u   // the driver is derating for OTPW
#define DRIVE_BOOST_LIMIT_SUPPLY 4u   // the battery is low (or cut off)
#define DRIVE_BOOST_LIMIT_OFF    8u   // boost_ma is 0, or not above run_ma

// Stall recovery (0.3.1): drive_status_t.rec_state. Anything but IDLE is one
// episode, from the first trip until it recovers, is cancelled or gives up;
// it never passes through IDLE between its attempts.
typedef enum {
    DRIVE_REC_IDLE = 0,
    DRIVE_REC_LOCK,   // both wheels held: the tripped one at its rotor's speed, waiting for it to lock
    DRIVE_REC_RAMP,   // holds released, re-ramping toward the stick until it has made progress
} drive_rec_state_t;

// drive_status_t.rec_last_event: what the recovery did last, each logged on
// the "rec" tag as it happens.
typedef enum {
    DRIVE_REC_EV_NONE = 0,       // nothing yet since boot
    DRIVE_REC_EV_FAULT_DIRECT,   // a trip it may not handle (recover 0, no live stick, a lead): faulted
    DRIVE_REC_EV_ATTEMPT,        // froze both wheels and started an attempt
    DRIVE_REC_EV_JOINED,         // the partner slipped during the lock and joined the attempt
    DRIVE_REC_EV_LOCKED,         // the rotors matched their holds: ramping back to the stick
    DRIVE_REC_EV_LOCK_FAILED,    // a rotor did not lock: froze again, as the next attempt
    DRIVE_REC_EV_RECOVERED,      // every involved wheel made rec_prog: done, no fault
    DRIVE_REC_EV_CANCELLED,      // stick released, stopped or reversed, or a setting changed: no fault
    DRIVE_REC_EV_GAVE_UP,        // out of attempts, too many in a minute, or an encoder lost: FAULT_SLIP
} drive_rec_event_t;

typedef struct {
    bool driver_ok;        // configuration verified; invalidated by driver faults/settings
    bool driver_status_ok;
    uint32_t drv_status, gstat, driver_age_ms;
    bool fault_driver_status_ok;
    uint32_t fault_drv_status, fault_gstat, fault_driver_age_ms;
    float run_ma, hold_ma; // nominal quantized RMS current, not a measurement
    bool enabled;          // power stage on (shared EN low)
    bool loop_closed;      // servo armed (position or velocity mode)
    bool velocity_mode;
    bool encoder_ok;
    bool calibrated;       // clock gain measured this boot, not just loaded
    bool inverted;         // GCONF.shaft
    bool at_target;        // position mode: inside the tolerance band
    uint8_t fault;         // drive_fault_t
    uint8_t agc;           // AS5600 AGC, 0..128 on 3V3, aim for ~64
    uint8_t magnet_status; // AS5600 STATUS bits (0x20 detect, 0x10 low, 0x08 high)
    uint16_t raw_angle;
    int32_t pos_counts, target_counts, err_counts, slip_steps;
    long cmd_steps;        // integral of commanded rate, steps
    float pos_turns, target_turns, vel_tps, cmd_tps, rate_sps, clock_gain;
    float kp, vmax_tps, accel_tps2, decel_tps2;
    uint32_t worst_read_us;

    // --- torque (0.3.0) ---
    // run_ma/hold_ma above are the base pair begin() programs; these are what
    // the driver runs on now: boosted, on the way back down, or derated.
    float live_run_ma, live_hold_ma;
    uint8_t live_run_cs, live_hold_cs;   // the same as IRUN / IHOLD, 0..31
    float heat;                // thermal model: 1.0 is the steady state at the rated 1.5 A RMS
    uint8_t boost_reasons;     // DRIVE_BOOST_* active, granted or not
    uint8_t boost_limit;       // DRIVE_BOOST_LIMIT_* refusing them; 0 when granted or not asked
    bool boost_active;         // boost granted this tick
    bool heat_limited;         // from therm_lim until the heat is back at the resume point
    uint8_t derate;            // OTPW derate: 0 none, 1 no boost, 2 base at 75%, 3 base at 50%
    bool otpw;                 // the last DRV_STATUS sample says OTPW or t120 (injection included)
    bool otpw_injected;        // bench: debug otpw is feeding this wheel's samples
    uint32_t otpw_events;      // derate episodes since boot
    uint8_t cs_actual;         // CS_ACTUAL in the last DRV_STATUS sample
    uint32_t cs_mismatch;      // moving samples whose CS_ACTUAL was not the live IRUN, since stats reset

    // --- stall detection (0.3.1) ---
    // lag is the stall detector's: commanded minus encoder, in microsteps,
    // against a reference that leaks by distance, + with the rotor behind.
    // It trips past lag_trip (a lead past -lag_trip). 0 while not armed:
    // stopped, in position mode, or within lag_rev of a start or reversal.
    float lag_steps;           // this tick's
    float lag_worst;           // the largest |lag| while armed, since stats reset
    bool lag_armed;
    bool rec_held;             // stall recovery is holding this wheel's velocity command
    uint32_t stall_trips;      // detector trips since boot, lag and lead

    // Reserved for later phases, not fields yet: load_deg and limiter
    // (0.4.0, load-angle estimate and lead limiter).
} drive_wheel_status_t;

typedef struct {
    bool enabled;          // drivers energised
    bool faulted;          // a fault is latched; motion refused until cleared
    bool cal_busy;
    bool demo_running;
    bool cmd_active;       // a timed robot-frame command is in force
    uint8_t fault;         // the latched drive_fault_t, of any kind; 0 when none
    uint8_t fault_wheel;   // which wheel faulted first; stale for a robot-level fault
    float v_mps, w_radps;  // robot-frame command in force (0 when none)
    float vmax_mps, wmax_radps;  // current limits
    float track_m, wheel_circ_m;
    int8_t sign_a, sign_b; // robot-forward -> wheel-positive
    bool a_is_left;
    drive_wheel_status_t wheel[DRIVE_NWHEELS];
    uint32_t tick_worst_us, tick_count, bus_writes, bus_echo_faults;
    const char *demo_caption;

    // --- torque and bus timing (0.3.0), counters since stats reset ---
    uint32_t live_writes, live_write_failures, live_write_retries;
    uint32_t slot_worst_us;    // the tick's extra bus group (live write, health step), longest
    uint32_t slot_deferred;    // ticks the budget put off a due group
    uint32_t uart_read_worst_us, uart_write_worst_us;   // bus lock held, per transaction
    float heat_limit, heat_resume;   // therm_lim, and where boost comes back

    // --- stall recovery (0.3.1) ---
    bool rec_enabled;          // the recover setting
    uint8_t rec_state;         // drive_rec_state_t
    uint8_t rec_attempt;       // this episode's attempt, 1..rec_tries; 0 when idle
    uint8_t rec_wheels;        // wheels in this episode: bit 0 A, bit 1 B; 0 when idle
    uint8_t rec_last_event;    // drive_rec_event_t
    uint32_t rec_last_age_ms;  // since that event; 0 before the first
    uint32_t rec_attempts, rec_recoveries, rec_giveups;   // since boot; BLE byte 16 is rec_attempts' low byte
} drive_status_t;

// One duration, from a log histogram: p50 and p99 are the top of the bucket
// (at most 25% wide) they fall in, never above the maximum. Since stats reset.
typedef struct {
    uint32_t count;
    uint32_t p50_us, p99_us, max_us;
} drive_timing_t;

typedef struct {
    drive_timing_t tick;                  // the whole control tick
    drive_timing_t read[DRIVE_NWHEELS];   // one encoder read, per wheel
    drive_timing_t slot;                  // the tick's extra bus group, when one ran
} drive_timings_t;

typedef struct {
    bool ok, flipped;
    int32_t counts, back, residual;
    float seconds, sps, clock_gain;
    const char *note;
    drive_wheel_t wheel;
} drive_cal_result_t;

// --- boot -------------------------------------------------------------------

// Park EN high. Call this before anything else in app_main so both drivers are
// disabled from the first instruction; it is safe to call before drive_init().
void drive_park_en(void);

// Bring up the UART bus, both drivers, both encoders and the control task.
// Drivers start disabled. Returns ESP_OK even if a driver or encoder is absent
// -- the status says which -- so the console still comes up on a half-built
// bench. Fails only if the control task cannot be created.
esp_err_t drive_init(void);

// Claim under the motor mutex; only the command worker may mutate while owned.
esp_err_t drive_maintenance_claim(bool ota);
bool drive_maintenance_release(bool ota);
void drive_maintenance_cancel(void);

// --- power -------------------------------------------------------------------

// Energise both drivers (VACTUAL zeroed on each BEFORE the shared EN drops) or
// cut both. Refuses to enable while a driver is not answering, a calibration
// is running, or the battery is below its cutoff. Enabling also clears any
// latched fault.
esp_err_t drive_enable(bool on);
bool drive_enabled(void);

// Ramp every wheel to zero and cancel any timed command, and a stall recovery
// in progress. Drivers stay on.
void drive_stop(void);

// Emergency stop: EN high immediately, from any task, without taking any lock.
// Everything else is tidied up on the next control tick.
void drive_estop(void);

// --- motion --------------------------------------------------------------------

// Robot-frame velocity, held for `hold_ms` (0 = until told otherwise; only the
// console should ever use 0). Scaled down proportionally if either wheel would
// exceed its ceiling. Refused while disabled or faulted.
//
// `flags` is DRIVE_CMD_BOOST or 0. With the flag, both wheels get a manual
// boost for as long as the command holds (at most 60 s; renewed by each fresh
// command); an accepted command without it ends a manual boost. A zero
// command with the flag braces the robot where it stands.
esp_err_t drive_set_velocity_ex(float v_mps, float w_radps, uint32_t hold_ms, uint32_t flags);
esp_err_t drive_set_velocity(float v_mps, float w_radps, uint32_t hold_ms);   // flags 0

// The same, from a joystick: v and w in -1..1 of the current limits.
esp_err_t drive_set_normalized_ex(float v, float w, uint32_t hold_ms, uint32_t flags);
esp_err_t drive_set_normalized(float v, float w, uint32_t hold_ms);   // flags 0

// A manual boost on both wheels for `ms` (1..60000; a renewal can extend one
// but never shortens it), or 0 to end one. Refused while the drivers are
// disabled. Whether it is granted is the thermal model's, the OTPW derate's
// and the battery's to say: drive_wheel_status_t.boost_active / boost_limit.
esp_err_t drive_boost_manual(uint32_t ms);

// Bench: one wheel in velocity mode, output turns/s, with a hold.
esp_err_t drive_wheel_velocity(drive_wheel_t w, float tps, uint32_t hold_ms);
// Bench: position moves, absolute and relative, in output turns.
esp_err_t drive_wheel_goto(drive_wheel_t w, float turns);
esp_err_t drive_wheel_move(drive_wheel_t w, float dturns);
// Bench: open loop, steps/s, no encoder in the loop (slip still measured).
esp_err_t drive_wheel_spin(drive_wheel_t w, float sps);
// Bench: close or open the position loop by hand.
esp_err_t drive_wheel_loop(drive_wheel_t w, bool closed);
esp_err_t drive_wheel_zero(drive_wheel_t w);   // DRIVE_WHEEL_BOTH allowed

// Why the last motion/enable call was refused, as a sentence.
const char *drive_refusal(void);

// --- faults ---------------------------------------------------------------------

// A pack below its cutoff (battery.h) latches DRIVE_FAULT_BATTERY: both wheels
// ramp to a stop at decel_tps2 and hold there with the drivers still on, since
// cutting them would let the robot freewheel down a slope. Clearing, like
// enabling, is refused until the battery has left cutoff.
esp_err_t drive_clear_faults(void);
// "name (reason)", or just "none"; web clients split the two at " (".
const char *drive_fault_name(uint8_t fault);

// --- calibration ------------------------------------------------------------------

// Measure one wheel's shaft polarity and clock gain: 3 output turns out and
// back at 1500 steps/s, ~11 s. Runs on the control task; this returns at once.
// Results are logged and, when good, stored in NVS. Needs the drivers enabled
// and a magnet detected.
esp_err_t drive_calibrate(drive_wheel_t w);
void drive_calibrate_abort(void);
bool drive_calibrate_busy(void);
bool drive_calibrate_last(drive_cal_result_t *out);   // false if none yet

// --- demo scripts -----------------------------------------------------------------

// "short" drives both wheels (~9 s); "bench" drives `solo` alone (~40 s).
esp_err_t drive_demo_start(const char *name, drive_wheel_t solo);
void drive_demo_stop(void);

// --- tuning and settings ------------------------------------------------------------

// Per-wheel servo parameters by name: kp vmax accel vmin tol maxslip ratio
// gain micro. vmax and accel are clamped to the measured envelope. `w` may be
// DRIVE_WHEEL_BOTH for setting.
esp_err_t drive_param_set(drive_wheel_t w, const char *name, float value);
esp_err_t drive_param_get(drive_wheel_t w, const char *name, float *value);
const char *const *drive_param_names(size_t *n);

// Robot-frame settings, persisted: sign_a sign_b (+1/-1), a_left (0/1),
// track_m, vmax_tps, accel_tps2. Current/chopper settings run_ma, hold_ma,
// iholddly, spread, pwmthrs require disabled drivers and apply at next enable;
// run_ma above a nonzero boost_ma is refused. Torque settings apply at once,
// drivers on or off: boost_ma (0 = off, else run_ma..1768), boost_start_ms
// (0..5000, 0 = no start boost), therm_tau_s (60..3600), therm_lim (0.5..1.3).
// Stall settings apply at once too, and start the detectors over and cancel a
// recovery in progress: recover (1 retry a stall, 0 fault on the first trip),
// rec_tries (1..10), rec_lock_ms (50..2000), rec_prog (0.05..2 output turns),
// and in microsteps lag_trip (0 = detector off, else 16..0.8 x lag_leak),
// lag_leak (100..4000) and lag_rev (0..400).
esp_err_t drive_setting_set(const char *name, float value);
esp_err_t drive_setting_get(const char *name, float *value);
const char *const *drive_setting_names(size_t *n);

// "idle" "lock" "ramp", and "attempt", "gave up" and so on: the names the
// status reports and the "rec" log lines use.
const char *drive_rec_state_name(uint8_t state);
const char *drive_rec_event_name(uint8_t event);

// Force a wheel's shaft polarity (normally calibration decides). Persisted.
esp_err_t drive_wheel_set_invert(drive_wheel_t w, bool inv);

// Read a TMC2209 register on a wheel's driver. Returns false if it did not answer.
bool drive_wheel_read_reg(drive_wheel_t w, uint8_t reg, uint32_t *value);

// --- bench fault injection (CONFIG_UBOT_BENCH_FAULTS) ---------------------------------

// The next control tick busy-waits `ms` (1..10000) without feeding the task
// watchdog: proof that a wedged control loop resets the chip and EN floats
// high, instead of a driver stepping on at its last VACTUAL. Refused during an
// OTA or while another task's maintenance motion owns the robot.
// ESP_ERR_NOT_SUPPORTED in a build without CONFIG_UBOT_BENCH_FAULTS.
esp_err_t drive_debug_wedge(uint32_t ms);

// For the next `ms` (0..120000; 0 ends it early), wheel `w`'s DRV_STATUS
// samples read OTPW as well as whatever the chip says: the derate runs its
// levels exactly as for a hot driver, and nothing else changes. Refused like
// drive_debug_wedge(); ESP_ERR_NOT_SUPPORTED without CONFIG_UBOT_BENCH_FAULTS.
esp_err_t drive_debug_inject_otpw(drive_wheel_t w, uint32_t ms);

// --- observation ----------------------------------------------------------------------

// Lock-free snapshot, refreshed every control tick (and every ~50 ms during a
// calibration). Safe from any task.
void drive_get_status(drive_status_t *out);

// Start the statistics over: worst tick, worst encoder read, the timing
// histograms, slot and UART timing, live-write counts, CS_ACTUAL mismatches
// and each wheel's worst stall-detector lag. Bus write and echo-fault totals,
// detector trips and the recovery counters stay counts since boot.
void drive_reset_stats(void);

// p50/p99/max of the control tick, each wheel's encoder read and the slot's
// bus group, since stats reset. Safe from any task.
void drive_get_timings(drive_timings_t *out);

// Telemetry, same columns as the bench sketch streamed so the existing scope
// can replay a capture. New columns are only ever appended (batt_v, batt_st
// since 0.2.9; since 0.3.0 per wheel the live run/hold mA, boost reasons,
// heat, derate level and OTPW; since 0.3.1 each wheel's stall-detector lag
// and the recovery's state and attempt); the scope finds them by name from
// the header.
const char *drive_csv_header(void);
int drive_csv_line(char *buf, size_t n);

#ifdef __cplusplus
}
#endif
