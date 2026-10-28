// SG90 test bench on a Seeed XIAO RP2040.
//
// Core 1 owns timing: the 2 kHz sample tick (AS5600 angle, INA219 current and
// voltage, means of the ADC taps) and the servo PWM wrap interrupt that plays
// pulse schedules frame by frame. Core 0 owns USB: it parses host commands,
// polls the HX711 and drains the message ring to the host. The wire format is
// in Protocol.h; the host side is yaam.bench.
//
// Pins (XIAO silkscreen):
//   D0 A0  GP26  motor tap A          D6  GP0  TMC2209 UART TX (M4)
//   D1 A1  GP27  motor tap B          D7  GP1  TMC2209 UART RX (M4)
//   D2 A2  GP28  pot wiper tap        D8  GP2  HX711 SCK
//   D3     GP29  TMC2209 EN, held high (driver off) until M4
//   D4/D5  GP6/7 I2C1: AS5600 0x36, INA219 0x40
//   D9     GP4   servo signal (PWM slice 2 A)
//   D10    GP3   HX711 DT

#include <Arduino.h>
#include <Wire.h>

#include "Hx711.h"
#include "Link.h"
#include "Protocol.h"
#include "Sensors.h"
#include "ServoPwm.h"
#include "TapAdc.h"

#ifndef FW_GIT
#define FW_GIT "dev"
#endif

static const uint PIN_SERVO = 4;    // D9
static const uint PIN_TMC_EN = 29;  // D3
static const uint PIN_HX_SCK = 2;   // D8
static const uint PIN_HX_DT = 3;    // D10
static const uint32_t TICK_US = 500;
static const uint16_t BOOT_FRAME_US = 20000;

const Crc16 crc16;
static TxRing ring;
static RxParser rx;
static ServoPwm pwm;
static TapAdc taps;
static As5600 enc;
static Ina219 ina;
static Hx711 hx;

static volatile bool core0Ready = false;
static volatile bool streaming = false;
static volatile bool rawTaps = false;
static volatile bool rawRestart = false;
static volatile bool loadcellOn = false;
static volatile bool selftestRequest = false;
static volatile int32_t hxValue = 0;
static volatile uint32_t hxSeenMs = 0;

// Core 1 counters.
static volatile uint32_t overruns = 0;
static uint16_t angleErrors = 0, inaErrors = 0;

static void reply(uint8_t cmd, uint8_t code) {
    proto::Reply r = {cmd, code};
    ring.put(proto::REPLY, &r, sizeof r);
}

static void sendHello() {
    proto::Hello h = {};
    h.version = proto::VERSION;
    snprintf(h.firmware, sizeof h.firmware, "sg90_bench %s %s", FW_GIT, __DATE__);
    h.sys_hz = clock_get_hz(clk_sys);
    h.tick_hz = 1000000 / TICK_US;
    h.adc_hz = TapAdc::RATE_HZ;
    h.sched_capacity = ServoPwm::CAPACITY;
    h.frame_us = pwm.frameUs();
    h.idle_us = pwm.idleUs();
    ring.put(proto::HELLO, &h, sizeof h);
}

static uint16_t u16(const uint8_t *p) { return (uint16_t)(p[0] | (p[1] << 8)); }
static uint32_t u32(const uint8_t *p) { return (uint32_t)p[0] | ((uint32_t)p[1] << 8) | ((uint32_t)p[2] << 16) | ((uint32_t)p[3] << 24); }

static void handle(uint8_t type, const uint8_t *p, uint16_t n) {
    using namespace proto;
    switch (type) {
        case CMD_PING:
            sendHello();
            reply(type, OK);
            break;
        case CMD_SET_FRAME:
            reply(type, n == 2 ? pwm.setFrame(u16(p)) : ERR_LENGTH);
            break;
        case CMD_SCHED_CLEAR:
            reply(type, pwm.clearSchedule());
            break;
        case CMD_SCHED_DATA: {
            if (n < 6 || n != 6 + 2 * u16(p + 4)) {
                reply(type, ERR_LENGTH);
                break;
            }
            uint16_t count = u16(p + 4);
            static uint16_t w[(MAX_PAYLOAD - 6) / 2];
            memcpy(w, p + 6, count * 2);
            reply(type, pwm.loadSchedule(u32(p), w, count));
            break;
        }
        case CMD_RUN:
            reply(type, n == 6 ? pwm.run(u32(p), u16(p + 4)) : ERR_LENGTH);
            break;
        case CMD_STOP:
            pwm.stop();
            reply(type, OK);
            break;
        case CMD_SELFTEST:
            selftestRequest = true;
            reply(type, OK);
            break;
        case CMD_SET_IDLE:
            reply(type, n == 2 ? pwm.setIdle(u16(p)) : ERR_LENGTH);
            break;
        case CMD_LOADCELL:
            if (n != 1) { reply(type, ERR_LENGTH); break; }
            loadcellOn = p[0];
            reply(type, OK);
            break;
        case CMD_RAW_TAPS:
            if (n != 1) { reply(type, ERR_LENGTH); break; }
            rawTaps = p[0];
            rawRestart = true;
            reply(type, OK);
            break;
        case CMD_STREAM:
            if (n != 1) { reply(type, ERR_LENGTH); break; }
            streaming = p[0];
            pwm.setStreaming(p[0]);
            if (p[0]) rawRestart = true;
            reply(type, OK);
            break;
        default:
            reply(type, ERR_UNKNOWN);
    }
}

// XIAO RP2040 RGB LED, active low: green while a run plays, blue while streaming.
static void leds() {
    digitalWrite(PIN_LED_G, pwm.running() ? LOW : HIGH);
    digitalWrite(PIN_LED_B, streaming ? LOW : HIGH);
}

void setup() {
    // Keep the stepper driver off until its code exists (M4).
    pinMode(PIN_TMC_EN, OUTPUT);
    digitalWrite(PIN_TMC_EN, HIGH);
    const uint leds[] = {PIN_LED_R, PIN_LED_G, PIN_LED_B};
    for (uint pin : leds) {
        pinMode(pin, OUTPUT);
        digitalWrite(pin, HIGH);
    }
    Serial.begin(115200);
    ring.begin();
    pwm.begin(ring, PIN_SERVO, BOOT_FRAME_US);
    hx.begin(PIN_HX_SCK, PIN_HX_DT);
    core0Ready = true;
}

void loop() {
    while (Serial.available() > 0) {
        if (rx.feed((uint8_t)Serial.read())) handle(rx.type(), rx.payload(), rx.length());
    }
    if (!Serial && streaming) {
        // The host closed the port mid-stream: stop, and don't greet the next
        // one with a backlog of stale samples.
        streaming = false;
        pwm.setStreaming(false);
        ring.flush();
    }
    if (loadcellOn && hx.ready()) {
        proto::Load l = {time_us_32(), hx.read()};
        hxValue = l.value;
        hxSeenMs = millis();
        if (streaming) ring.put(proto::LOAD, &l, sizeof l);
    }
    ring.drain(Serial);
    leds();
}

// --- core 1 ---

static uint32_t nextTick = 0;
static uint32_t tickCount = 0;
static bool inaBusNext = false;
static uint8_t asStatus = 0, asAgc = 0;
static uint16_t asMagnitude = 0;
static uint32_t adcAvgSum[4] = {0, 0, 0, 0};
static uint16_t adcAvg[4] = {0, 0, 0, 0};

// The pin's input buffer still sees what the PWM slice drives, so the pulse
// on the wire can be timed without a loopback wire. The wrap interrupt fires
// on the rising edge and would make the measurement short, so interrupts stay
// off for up to two frames; between runs that only delays one wrap.
static uint16_t measurePulse() {
    if (pwm.running()) return 0xFFFF;
    uint32_t irq = save_and_disable_interrupts();
    uint32_t t0 = time_us_32(), limit = 2u * pwm.frameUs() + 1000u;
    auto waitFor = [&](bool level) {
        while (gpio_get(PIN_SERVO) != level)
            if (time_us_32() - t0 > limit) return false;
        return true;
    };
    uint16_t us = 0;
    if (!waitFor(false)) {
        us = 0xFFFF;   // stuck high
    } else if (waitFor(true)) {
        uint32_t rise = time_us_32();
        us = waitFor(false) ? (uint16_t)(time_us_32() - rise) : 0xFFFF;
    }
    restore_interrupts(irq);
    return us;
}

static void selftest() {
    proto::SelfTest s = {};
    s.frame_us = pwm.measuredFrameUs();   // before measurePulse() delays a wrap
    s.pulse_us = measurePulse();
    s.as_present = enc.begin();
    s.as_status = enc.status();
    s.as_agc = enc.agc();
    s.as_magnitude = enc.magnitude();
    s.as_conf = enc.conf();
    enc.rawAngle(s.as_raw);
    s.ina_present = ina.present() || ina.begin();
    s.ina_config = ina.config();
    ina.shunt(s.ina_shunt);
    int16_t bus = 0;
    ina.bus(bus);
    s.ina_bus = (uint16_t)bus;
    memcpy(s.adc, adcAvg, sizeof s.adc);
    s.sys_hz = clock_get_hz(clk_sys);
    s.overruns = overruns;
    s.drops = ring.drops();
    s.hx_present = millis() - hxSeenMs < 500;
    s.hx_value = hxValue;
    ring.put(proto::SELFTEST, &s, sizeof s);
}

void setup1() {
    while (!core0Ready) tight_loop_contents();
    i2c::recover(SDA, SCL);
    Wire.setClock(400000);
    Wire.setTimeout(2);
    Wire.begin();
    enc.begin();
    ina.begin();
    taps.begin();
    pwm.start();
    nextTick = time_us_32() + TICK_US;
}

void loop1() {
    uint32_t now = time_us_32();
    if ((int32_t)(now - nextTick) < 0) return;

    proto::Tick t = {};
    if ((int32_t)(now - nextTick) >= (int32_t)TICK_US) {
        overruns++;
        t.flags |= proto::TICK_OVERRUN;
        nextTick = now;
    }
    nextTick += TICK_US;
    t.t_us = now;
    t.adc_idx = taps.index();

    if (enc.rawAngle(t.angle)) t.flags |= proto::TICK_ANGLE_OK;
    else angleErrors++;

    // Ten times a second the AS5600's status, AGC and magnitude replace the
    // INA219 read, one register per tick, to keep every tick under 500 us.
    uint32_t phase = tickCount % 200;
    if (phase == 100) asStatus = enc.status();
    else if (phase == 101) asAgc = enc.agc();
    else if (phase == 102) asMagnitude = enc.magnitude();
    else {
        bool ok = inaBusNext ? ina.bus(t.ina) : ina.shunt(t.ina);
        if (ok) t.flags |= proto::TICK_INA_OK;
        else inaErrors++;
        if (inaBusNext) t.flags |= proto::TICK_INA_BUS;
        inaBusNext = !inaBusNext;
    }

    taps.means(t.adc, t.n);
    for (int k = 0; k < 4; k++) adcAvgSum[k] += t.adc[k];
    if (phase == 199) {
        for (int k = 0; k < 4; k++) {
            adcAvg[k] = (uint16_t)(adcAvgSum[k] / 200);
            adcAvgSum[k] = 0;
        }
    }

    if (streaming) {
        ring.put(proto::TICK, &t, sizeof t);
        if (rawRestart) {
            taps.skipRaw();
            rawRestart = false;
        }
        if (rawTaps) taps.streamRaw(ring);
        if (phase == 102) {
            proto::Status s = {now, asStatus, asAgc, asMagnitude, overruns, ring.drops(), angleErrors, inaErrors};
            ring.put(proto::STATUS, &s, sizeof s);
        }
    }
    if (selftestRequest) {
        selftestRequest = false;
        selftest();
        nextTick = time_us_32() + TICK_US;
    }
    tickCount++;
}
