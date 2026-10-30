// phone_girl link, protocol version 1: frames between the phone app and the
// servo-bus MCU, over USB-C NCM (UDP) or BLE (GATT). Behaviour is in PROTOCOL.md.
// sim/src/phone_girl/protocol.py is the reference; its golden vectors are
// checked against this header.
// Little-endian and packed. Positions are servo ticks minus 2048.
#pragma once
#include <stdint.h>

#define PGL_VERSION 1
#define PGL_SERVOS 17
#define PGL_HOME_TICKS 2048
#define PGL_UNKNOWN_LATENCY 0xFFFF

#define PGL_SERVICE_UUID "a7470000-77c3-4dbd-b507-83058991dbc6"
#define PGL_STATE_UUID "a7470001-77c3-4dbd-b507-83058991dbc6"    // notify, every tick
#define PGL_COMMAND_UUID "a7470002-77c3-4dbd-b507-83058991dbc6"  // write without response
#define PGL_CONTROL_UUID "a7470003-77c3-4dbd-b507-83058991dbc6"  // write, replies by notify
#define PGL_INFO_UUID "a7470004-77c3-4dbd-b507-83058991dbc6"     // read, JSON
#define PGL_CAPTURE_UUID "a7470005-77c3-4dbd-b507-83058991dbc6"  // notify, system identification

// USB-C NCM: one UDP datagram per frame, on the port matching each characteristic.
#define PGL_STATE_PORT 47001    // MCU to phone, every tick
#define PGL_COMMAND_PORT 47002  // phone to MCU, every tick
#define PGL_CONTROL_PORT 47003  // requests, and their replies back to the sender
#define PGL_INFO_PORT 47004     // an empty datagram gets the JSON back
#define PGL_CAPTURE_PORT 47005  // MCU to phone, system identification

// State flags.
enum {
  PGL_TORQUE_ON = 1 << 0,
  PGL_COMMAND_FRESH = 1 << 1,  // a new command was applied since the last state
  PGL_HOLDING = 1 << 2,        // no command lately: holding the last goals
  PGL_DEADMAN = 1 << 3,        // held too long: in the safe behaviour
  PGL_SERVO_ERROR = 1 << 4,    // some servo reports a hardware error
  PGL_LOW_VOLTAGE = 1 << 5,
};

// Command flags.
enum { PGL_HOLD = 1 << 0 };  // keep the current goals: the app is pausing, not lost

// Control opcodes. A reply carries the opcode with the top bit set.
enum {
  PGL_TORQUE = 1,          // u32 slot mask; 0 turns every servo off
  PGL_GAIN = 2,            // u16 Position P Gain for every servo
  PGL_LIMITS = 3,          // u16 current limit mA, u16 PWM limit; torque must be off
  PGL_CALIBRATE_HOME = 4,  // torque off, robot in its home pose; replies with 17 i32 Homing Offsets
  PGL_SAFETY = 5,          // pgl_safety_t
  PGL_REBOOT = 6,          // u32 slot mask
  PGL_CAPTURE_START = 7,   // u32 slot mask, u16 rate Hz, u16 duration ms
  PGL_SOFT_LIMITS = 8,     // 17 x (i16 low, i16 high) ticks minus 2048
};
enum { PGL_OK, PGL_BAD_REQUEST, PGL_REFUSED, PGL_BUS_ERROR, PGL_BUSY };

typedef struct __attribute__((packed)) {
  int16_t position;  // ticks minus 2048
  int16_t velocity;  // Present Velocity, 0.229 rpm
  int16_t current;   // Present Current, mA, at the servo's power input
  int16_t pwm;       // Present PWM, 0.113 % (885 is full duty)
} pgl_servo_t;

typedef struct __attribute__((packed)) {
  uint8_t version;
  uint8_t flags;
  uint16_t seq;
  uint32_t read_us;          // MCU clock when the bus read began
  uint16_t command_seq;      // last command applied
  uint16_t command_latency;  // 0.1 ms from reading the state it answered to applying it
  uint16_t bus_mv;
  uint8_t slot;  // whose slow fields follow, round robin
  int8_t temperature_c;
  uint8_t hardware_error;  // Hardware Error Status of that servo
  uint8_t bus_errors;      // failed reads since the last state, saturating
  pgl_servo_t servos[PGL_SERVOS];
} pgl_state_t;

typedef struct __attribute__((packed)) {
  uint8_t version;
  uint8_t flags;
  uint16_t seq;
  uint16_t state_seq;  // the state the policy acted on
  int16_t goals[PGL_SERVOS];
} pgl_command_t;

typedef struct __attribute__((packed)) {
  uint8_t opcode;
  uint8_t request;  // echoed in the reply
} pgl_control_t;    // the opcode's payload follows

typedef struct __attribute__((packed)) {
  uint8_t opcode;  // request opcode | 0x80
  uint8_t request;
  uint8_t status;
} pgl_reply_t;  // the opcode's reply payload follows

typedef struct __attribute__((packed)) {
  uint16_t hold_ms;    // keep the last goals this long without commands
  uint8_t after;       // then 0: torque off, 1: freeze
  uint16_t freeze_ms;  // how long to freeze before torque off
} pgl_safety_t;

typedef struct __attribute__((packed)) {
  int16_t goal, position, velocity, current, pwm;
} pgl_sample_t;

typedef struct __attribute__((packed)) {
  uint8_t version;
  uint8_t slot;
  uint8_t count;
  uint16_t seq;
  uint32_t start_us;
  uint16_t period_us;
  pgl_sample_t samples[];
} pgl_capture_t;

_Static_assert(sizeof(pgl_state_t) == 154, "state is 154 bytes");
_Static_assert(sizeof(pgl_command_t) == 40, "command is 40 bytes");
_Static_assert(sizeof(pgl_capture_t) == 11, "capture header is 11 bytes");
