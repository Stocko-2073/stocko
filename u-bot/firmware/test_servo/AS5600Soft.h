#pragma once
#include <AS5600.h>
#include <Arduino.h>
#include <soc/gpio_reg.h>

// A second AS5600 on a bit-banged I2C bus.
//
// Why this exists: the AS5600's address is 0x36 and there are no address pins,
// so two of them cannot share a bus. The obvious fix -- put the second one on
// Wire1 -- does not work on this board. The C6's SOC_I2C_NUM is 2, so Wire1
// compiles and i2cInit() accepts it, but the second controller is LP_I2C, and
// LP_I2C is IO-MUX only: SDA can *only* be GPIO6 and SCL can *only* be GPIO7
// (hal/esp32c6/include/hal/i2c_ll.h). The XIAO breaks out GPIO 0,1,2,16..23 --
// not 6 or 7. So Wire1 looks available, builds clean, and fails at runtime.
//
// The library makes this cheap. readReg/readReg2/writeReg/writeReg2 are
// protected *and* virtual, so overriding those four leaves readAngle(),
// readStatus(), readAGC(), the direction handling and the offset masking all
// working untouched. This class is a bus, not a driver.
//
// Cost: about the same as the hardware bus, which is the surprising part. An
// angle read is ~40 bit periods either way, and arduino-esp32's Wire blocks for
// the whole transaction anyway -- so the hardware encoder is already costing
// ~135 us of stalled CPU per read. At halfUs=2 this costs ~200 us. Both fit
// inside the 1 kHz control tick with room to spare.
//
// Interrupts are harmless here. The 40 kHz StepGen ISR fires every 25 us and
// will stretch bit periods all over a transaction, and I2C does not care: it is
// a fully static protocol with no slave-side timeout, so a clock held high or
// low for an extra microsecond is legal. Treat the nominal bit rate as a
// ceiling, not a promise.
//
// Wiring: SDA and SCL each need a pull-up to 3V3 (4.7k). Most AS5600 breakouts
// carry their own -- check you have not ended up with three in parallel across
// the two boards, which drags the low level up.
//
// Usage mirrors the hardware one, but call begin()/isConnected() through this
// type, not through an AS5600& -- see the note on those methods.
//
//   AS5600Soft encB(D9 /* SDA */, D8 /* SCL */);
//   encB.begin();
//   encB.setDirection(AS5600_CLOCK_WISE);
//   uint16_t a = encB.readAngle();
class AS5600Soft : public AS5600 {
  public:
    // Half a bit period, microseconds. 2 is ~250 kHz and leaves margin for the
    // pull-up to charge a slightly long cable; 1 is ~400 kHz and matches the
    // hardware bus if you need the time back in the control loop. A bit-bang
    // that is slightly too fast fails intermittently and is miserable to debug,
    // so the default is the conservative one.
    static const uint32_t DEFAULT_HALF_US = 2;

    // How long to wait for SCL to come up before calling the bus wedged. Well
    // past anything the AS5600 does -- it never stretches -- so this only fires
    // on a shorted line or a slave left mid-byte.
    static const uint32_t STRETCH_US = 1000;

    // _wire is deliberately null: nothing in this class touches it, and a null
    // makes any non-virtual path that does crash loudly instead of quietly
    // probing 0x36 on the *hardware* bus and answering with the other encoder.
    AS5600Soft(uint8_t sdaPin, uint8_t sclPin,
               uint8_t address = AS5600_DEFAULT_ADDRESS)
        : AS5600(nullptr), _sdaPin(sdaPin), _sclPin(sclPin) {
        _sdaMask = 1UL << sdaPin;
        _sclMask = 1UL << sclPin;
        _address = address;
    }

    uint32_t halfUs = DEFAULT_HALF_US;

    // Shadows AS5600::begin(), which is not virtual and reaches _wire through
    // isConnected(). Call it on an AS5600Soft, not through a base reference.
    bool begin(uint8_t directionPin = AS5600_SW_DIRECTION_PIN) {
        // Open drain with the input buffer live: pinMode(OUTPUT_OPEN_DRAIN)
        // resolves to GPIO_MODE_INPUT_OUTPUT_OD, so GPIO_OUT drives low or
        // lets go, and GPIO_IN always reads what is actually on the wire.
        pinMode(_sdaPin, OUTPUT_OPEN_DRAIN);
        pinMode(_sclPin, OUTPUT_OPEN_DRAIN);
        release(_sdaMask);
        release(_sclMask);
        recoverBus();

        _directionPin = directionPin;
        if (_directionPin != AS5600_SW_DIRECTION_PIN) pinMode(_directionPin, OUTPUT);
        setDirection(AS5600_CLOCK_WISE);
        return isConnected();
    }

    // Shadows AS5600::isConnected() for the same reason as begin().
    bool isConnected() {
        if (!start()) return false;
        bool ack = writeByte((uint8_t)(_address << 1));
        stop();
        return ack;
    }

    // If we reset partway through a read, the slave can be left driving SDA low
    // waiting for the rest of its byte. Nine clocks walk it to the end of that
    // byte and a stop resets its state machine. Cheap, and it turns a dead bus
    // at power-up into a non-event.
    void recoverBus() {
        release(_sdaMask);
        for (uint8_t i = 0; i < 9; i++) {
            sclHigh();
            driveLow(_sclMask);
            hold();
        }
        stop();
    }

  protected:
    uint8_t readReg(uint8_t reg) override {
        uint8_t v = 0;
        _error = readInto(reg, &v, 1) ? AS5600_OK : AS5600_ERROR_I2C_READ_0;
        return _error == AS5600_OK ? v : 0;
    }

    uint16_t readReg2(uint8_t reg) override {
        uint8_t v[2] = {0, 0};
        _error = readInto(reg, v, 2) ? AS5600_OK : AS5600_ERROR_I2C_READ_2;
        if (_error != AS5600_OK) return 0;
        return ((uint16_t)v[0] << 8) | v[1];
    }

    uint8_t writeReg(uint8_t reg, uint8_t value) override {
        uint8_t v[1] = {value};
        _error = writeFrom(reg, v, 1) ? AS5600_OK : AS5600_ERROR_I2C_WRITE_0;
        return _error;
    }

    uint8_t writeReg2(uint8_t reg, uint16_t value) override {
        uint8_t v[2] = {(uint8_t)(value >> 8), (uint8_t)(value & 0xFF)};
        _error = writeFrom(reg, v, 2) ? AS5600_OK : AS5600_ERROR_I2C_WRITE_0;
        return _error;
    }

  private:
    // --- transactions ---

    bool readInto(uint8_t reg, uint8_t *dst, uint8_t n) {
        if (!start() || !writeByte((uint8_t)(_address << 1)) || !writeByte(reg)) {
            stop();
            return false;
        }
        // Repeated start: no stop in between, or another master (or a glitch)
        // could take the bus between setting the pointer and reading it.
        if (!start() || !writeByte((uint8_t)((_address << 1) | 1))) {
            stop();
            return false;
        }
        for (uint8_t i = 0; i < n; i++) {
            // ACK every byte but the last; the NACK is what tells the slave to
            // let go of SDA so the stop can happen.
            if (!readByte(dst[i], i + 1 < n)) {
                stop();
                return false;
            }
        }
        stop();
        return true;
    }

    bool writeFrom(uint8_t reg, const uint8_t *src, uint8_t n) {
        if (!start() || !writeByte((uint8_t)(_address << 1)) || !writeByte(reg)) {
            stop();
            return false;
        }
        for (uint8_t i = 0; i < n; i++) {
            if (!writeByte(src[i])) {
                stop();
                return false;
            }
        }
        stop();
        return true;
    }

    // --- bus conditions ---
    //
    // Every one of these leaves SCL low on exit, so they compose in any order
    // and start() doubles as a repeated start.

    bool start() {
        release(_sdaMask);
        hold();
        if (!sclHigh()) return false;
        driveLow(_sdaMask);  // SDA falls while SCL is high
        hold();
        driveLow(_sclMask);
        hold();
        return true;
    }

    void stop() {
        driveLow(_sdaMask);
        hold();
        sclHigh();
        release(_sdaMask);  // SDA rises while SCL is high
        hold();
    }

    // --- bytes ---

    // Returns true if the slave pulled SDA down on the ninth clock.
    bool writeByte(uint8_t b) {
        for (uint8_t i = 0; i < 8; i++) {
            if (!sendBit((b & 0x80) != 0)) return false;
            b <<= 1;
        }
        release(_sdaMask);  // ninth clock: the slave owns SDA
        hold();
        if (!sclHigh()) return false;
        bool ack = !readSda();
        driveLow(_sclMask);
        return ack;
    }

    bool readByte(uint8_t &out, bool ack) {
        uint8_t b = 0;
        release(_sdaMask);
        for (uint8_t i = 0; i < 8; i++) {
            hold();
            if (!sclHigh()) return false;
            b = (uint8_t)((b << 1) | (readSda() ? 1 : 0));  // sampled with SCL high
            driveLow(_sclMask);
        }
        out = b;
        return sendBit(!ack);  // ack = drive SDA low, nack = leave it released
    }

    // --- bits ---
    //
    // Two holds per bit: the first is the SCL low period and doubles as the
    // data setup time (SDA is set before it, so it has a full half period to
    // settle), the second is the high period inside sclHigh().
    bool sendBit(bool bit) {
        if (bit) release(_sdaMask); else driveLow(_sdaMask);
        hold();
        if (!sclHigh()) return false;
        driveLow(_sclMask);
        return true;
    }

    // Release SCL and make sure it actually came up. The pull-up has to charge
    // the bus capacitance, and a slave is allowed to hold it down -- the AS5600
    // never does, but checking costs one register read in the common case and
    // turns a shorted SCL into a clean failure instead of garbage data.
    bool sclHigh() {
        release(_sclMask);
        hold();
        if (readScl()) return true;
        uint32_t t0 = micros();
        while (!readScl()) {
            if (micros() - t0 > STRETCH_US) return false;
        }
        return true;
    }

    // --- pins ---
    //
    // Open drain, so "high" is a release and the pull-up does the work. Same
    // single 32-bit register StepGen uses -- the C6 tops out at GPIO30.
    inline void driveLow(uint32_t mask) { REG_WRITE(GPIO_OUT_W1TC_REG, mask); }
    inline void release(uint32_t mask) { REG_WRITE(GPIO_OUT_W1TS_REG, mask); }
    inline bool readSda() const { return (REG_READ(GPIO_IN_REG) & _sdaMask) != 0; }
    inline bool readScl() const { return (REG_READ(GPIO_IN_REG) & _sclMask) != 0; }
    inline void hold() const { delayMicroseconds(halfUs); }

    uint8_t _sdaPin;
    uint8_t _sclPin;
    uint32_t _sdaMask;
    uint32_t _sclMask;
};
