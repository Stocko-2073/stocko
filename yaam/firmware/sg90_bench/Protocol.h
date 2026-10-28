#pragma once
#include <stdint.h>

// Wire format shared with src/yaam/bench/protocol.py. Every message, in either
// direction, is
//
//   0xA5, type, len (u16 LE), payload[len], crc (u16 LE)
//
// with CRC-16/CCITT-FALSE (poly 0x1021, init 0xFFFF) over type, len and
// payload -- what Python's binascii.crc_hqx(data, 0xFFFF) computes. A reader
// that loses its place drops one byte and looks for the next 0xA5.
//
// Times are the RP2040's microsecond timer, truncated to 32 bits; the host
// unwraps them (they wrap every 71.6 minutes).
namespace proto {

constexpr uint8_t SYNC = 0xA5;
constexpr uint8_t VERSION = 1;
constexpr uint16_t MAX_PAYLOAD = 1024;

// Device to host.
constexpr uint8_t HELLO = 0x01;
constexpr uint8_t TICK = 0x02;
constexpr uint8_t FRAME = 0x03;
constexpr uint8_t TAPS = 0x04;
constexpr uint8_t STATUS = 0x05;
constexpr uint8_t REPLY = 0x06;
constexpr uint8_t LOAD = 0x07;
constexpr uint8_t RUN_DONE = 0x08;
constexpr uint8_t SELFTEST = 0x09;
constexpr uint8_t TEXT = 0x7F;

// Host to device. Each gets a REPLY with the command's type and a code.
constexpr uint8_t CMD_PING = 0x81;         // -> HELLO as well
constexpr uint8_t CMD_SET_FRAME = 0x82;    // u16 frame period, us
constexpr uint8_t CMD_SCHED_CLEAR = 0x83;
constexpr uint8_t CMD_SCHED_DATA = 0x84;   // u32 offset, u16 n, u16 widths[n]
constexpr uint8_t CMD_RUN = 0x85;          // u32 frames, u16 width after the run
constexpr uint8_t CMD_STOP = 0x86;
constexpr uint8_t CMD_SELFTEST = 0x87;     // -> SELFTEST as well
constexpr uint8_t CMD_SET_IDLE = 0x88;     // u16 width between runs, 0 = no pulse
constexpr uint8_t CMD_LOADCELL = 0x89;     // u8 on/off
constexpr uint8_t CMD_RAW_TAPS = 0x8A;     // u8 on/off
constexpr uint8_t CMD_STREAM = 0x8B;       // u8 on/off: TICK, FRAME, TAPS, STATUS

// REPLY codes.
constexpr uint8_t OK = 0;
constexpr uint8_t ERR_BUSY = 1;      // not allowed while a run is going
constexpr uint8_t ERR_RANGE = 2;     // an argument is out of range
constexpr uint8_t ERR_LENGTH = 3;    // payload is the wrong size
constexpr uint8_t ERR_UNKNOWN = 4;   // unknown command
constexpr uint8_t ERR_EMPTY = 5;     // run with no schedule loaded

// TICK.flags
constexpr uint8_t TICK_INA_BUS = 0x01;    // ina holds the bus register, else the shunt
constexpr uint8_t TICK_INA_OK = 0x02;
constexpr uint8_t TICK_ANGLE_OK = 0x04;
constexpr uint8_t TICK_OVERRUN = 0x08;    // this tick started late

#pragma pack(push, 1)

struct Hello {
    uint8_t version;
    char firmware[32];
    uint32_t sys_hz;
    uint16_t tick_hz;
    uint32_t adc_hz;           // all four ADC channels together
    uint32_t sched_capacity;
    uint16_t frame_us;
    uint16_t idle_us;
};

// One per 500 us sample tick.
struct Tick {
    uint32_t t_us;             // when the tick started, before any reads
    uint32_t adc_idx;          // ADC samples taken since boot, at t_us
    uint16_t angle;            // AS5600 RAW ANGLE, 12 bit
    int16_t ina;               // raw INA219 register, see flags
    uint16_t adc[4];           // mean of each ADC channel since the last tick, x16
    uint8_t flags;
    uint8_t n;                 // samples per channel in those means
};

// One per servo frame, at the PWM wrap that starts it.
struct Frame {
    uint32_t frame;
    uint32_t t_us;
    uint16_t width_us;         // the pulse at the start of this frame, 0 = none
    int32_t sched_idx;         // position in the schedule, -1 between runs
};

// Raw ADC samples, round-robin over inputs 0, 1, 2 and 4 (temperature):
// sample i is input [0, 1, 2, 4][i % 4]. Followed by u16 samples[n].
struct TapsHead {
    uint32_t first_idx;
    uint16_t n;
};

struct Status {
    uint32_t t_us;
    uint8_t as_status;         // AS5600 STATUS: MD 0x20, ML 0x10, MH 0x08
    uint8_t as_agc;
    uint16_t as_magnitude;
    uint32_t overruns;
    uint32_t drops;            // records lost because the USB side fell behind
    uint16_t angle_errors;
    uint16_t ina_errors;
};

struct Load {
    uint32_t t_us;
    int32_t value;             // raw HX711 counts
};

struct RunDone {
    uint32_t t_us;
    uint32_t frames;           // schedule frames actually sent
    uint8_t stopped;           // 1 if a STOP cut it short
};

struct SelfTest {
    uint8_t as_present;
    uint8_t as_status;
    uint8_t as_agc;
    uint16_t as_magnitude;
    uint16_t as_conf;          // read back; should be 0x0300
    uint16_t as_raw;
    uint8_t ina_present;
    uint16_t ina_config;       // read back; should be 0x119F
    int16_t ina_shunt;
    uint16_t ina_bus;
    uint16_t adc[4];           // means over the last ~100 ms, x16
    uint32_t frame_us;         // measured from the last two frames
    uint32_t sys_hz;
    uint32_t overruns;
    uint32_t drops;
    uint8_t hx_present;
    int32_t hx_value;
    uint16_t pulse_us;         // timed on the servo pin itself; 0 = none, 0xFFFF = stuck high or busy
};

struct Reply {
    uint8_t cmd;
    uint8_t code;
};

#pragma pack(pop)

// The host decodes these with numpy dtypes of the same sizes.
static_assert(sizeof(Hello) == 51, "Hello");
static_assert(sizeof(Tick) == 22, "Tick");
static_assert(sizeof(Frame) == 14, "Frame");
static_assert(sizeof(TapsHead) == 6, "TapsHead");
static_assert(sizeof(Status) == 20, "Status");
static_assert(sizeof(Load) == 8, "Load");
static_assert(sizeof(RunDone) == 9, "RunDone");
static_assert(sizeof(SelfTest) == 47, "SelfTest");
static_assert(sizeof(Reply) == 2, "Reply");

}  // namespace proto
