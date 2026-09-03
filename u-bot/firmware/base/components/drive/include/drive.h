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

// Mirrors StepperServo::Fault.
typedef enum {
    DRIVE_FAULT_NONE = 0,
    DRIVE_FAULT_SLIP,      // shaft did not follow the commanded velocity
    DRIVE_FAULT_ENCODER,   // encoder stopped answering on the bus
    DRIVE_FAULT_MAGNET,    // encoder says there is no magnet
    DRIVE_FAULT_PEER,      // stopped because the other wheel faulted
} drive_fault_t;

typedef struct {
    bool driver_ok;        // TMC2209 answered on the bus
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
} drive_wheel_status_t;

typedef struct {
    bool enabled;          // drivers energised
    bool faulted;          // a fault is latched; motion refused until cleared
    bool cal_busy;
    bool demo_running;
    bool cmd_active;       // a timed robot-frame command is in force
    uint8_t fault_wheel;   // which wheel faulted first
    float v_mps, w_radps;  // robot-frame command in force (0 when none)
    float vmax_mps, wmax_radps;  // current limits
    float track_m, wheel_circ_m;
    int8_t sign_a, sign_b; // robot-forward -> wheel-positive
    bool a_is_left;
    drive_wheel_status_t wheel[DRIVE_NWHEELS];
    uint32_t tick_worst_us, tick_count, bus_writes, bus_echo_faults;
    const char *demo_caption;
} drive_status_t;

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

// --- power -------------------------------------------------------------------

// Energise both drivers (VACTUAL zeroed on each BEFORE the shared EN drops) or
// cut both. Refuses to enable while a driver is not answering or a calibration
// is running. Enabling also clears any latched fault.
esp_err_t drive_enable(bool on);
bool drive_enabled(void);

// Ramp every wheel to zero and cancel any timed command. Drivers stay on.
void drive_stop(void);

// Emergency stop: EN high immediately, from any task, without taking any lock.
// Everything else is tidied up on the next control tick.
void drive_estop(void);

// --- motion --------------------------------------------------------------------

// Robot-frame velocity, held for `hold_ms` (0 = until told otherwise; only the
// console should ever use 0). Scaled down proportionally if either wheel would
// exceed its ceiling. Refused while disabled or faulted.
esp_err_t drive_set_velocity(float v_mps, float w_radps, uint32_t hold_ms);

// The same, from a joystick: v and w in -1..1 of the current limits.
esp_err_t drive_set_normalized(float v, float w, uint32_t hold_ms);

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

esp_err_t drive_clear_faults(void);
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
// track_m, vmax_tps, accel_tps2. Applied immediately.
esp_err_t drive_setting_set(const char *name, float value);
esp_err_t drive_setting_get(const char *name, float *value);
const char *const *drive_setting_names(size_t *n);

// Force a wheel's shaft polarity (normally calibration decides). Persisted.
esp_err_t drive_wheel_set_invert(drive_wheel_t w, bool inv);

// Read a TMC2209 register on a wheel's driver. Returns false if it did not answer.
bool drive_wheel_read_reg(drive_wheel_t w, uint8_t reg, uint32_t *value);

// --- observation ----------------------------------------------------------------------

// Lock-free snapshot, refreshed every control tick (and every ~50 ms during a
// calibration). Safe from any task.
void drive_get_status(drive_status_t *out);

// Zero the worst-tick and worst-encoder-read counters.
void drive_reset_stats(void);

// Telemetry, same columns as the bench sketch streamed so the existing scope
// can replay a capture.
const char *drive_csv_header(void);
int drive_csv_line(char *buf, size_t n);

#ifdef __cplusplus
}
#endif
