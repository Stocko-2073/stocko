#pragma once
#include <stdint.h>
#include <stddef.h>

#include "driver/i2c_master.h"

// Two ways to reach an AS5600, behind one interface.
//
// The AS5600's address is fixed at 0x36 with no address pins, so two of them
// cannot share a bus. The C6 has two I2C controllers but the second is LP_I2C,
// which is IO-MUX only on GPIO6/7 -- pins the XIAO does not break out. So wheel
// A rides the hardware controller and wheel B a bit-banged bus. Both cost about
// the same per read (~135 us vs ~200 us), well inside the 5 ms control tick.
class I2cBus {
  public:
    virtual ~I2cBus() {}
    virtual bool begin() = 0;
    // Write `wn` bytes then read `rn` bytes from `addr`, repeated start between.
    virtual bool writeRead(uint8_t addr, const uint8_t *w, size_t wn, uint8_t *r, size_t rn) = 0;
    virtual bool write(uint8_t addr, const uint8_t *w, size_t wn) = 0;
    virtual bool probe(uint8_t addr) = 0;
    virtual const char *kind() const = 0;
};

// The ESP-IDF i2c_master driver. One device handle per address, created on
// first use.
class HwI2c : public I2cBus {
  public:
    HwI2c(int port, int sdaPin, int sclPin, uint32_t hz = 400000)
        : port_(port), sda_(sdaPin), scl_(sclPin), hz_(hz) {}
    bool begin() override;
    bool writeRead(uint8_t addr, const uint8_t *w, size_t wn, uint8_t *r, size_t rn) override;
    bool write(uint8_t addr, const uint8_t *w, size_t wn) override;
    bool probe(uint8_t addr) override;
    const char *kind() const override { return "hardware"; }

  private:
    i2c_master_dev_handle_t dev(uint8_t addr);

    int port_, sda_, scl_;
    uint32_t hz_;
    i2c_master_bus_handle_t bus_ = nullptr;
    static const int MAXDEV = 2;
    uint8_t devAddr_[MAXDEV] = {0, 0};
    i2c_master_dev_handle_t devH_[MAXDEV] = {nullptr, nullptr};
};

// A bit-banged master on two open-drain GPIOs. Every bus condition leaves SCL
// low on exit so they compose in any order, and every SCL release is checked
// so a shorted line fails cleanly instead of returning garbage.
//
// Interrupts are harmless: I2C is fully static, and a clock held high or low
// for an extra microsecond is legal. Treat the nominal rate as a ceiling.
//
// Wiring: SDA and SCL each need a pull-up to 3V3 (4.7k). Most AS5600 breakouts
// carry their own -- check you have not ended up with three in parallel.
class SoftI2c : public I2cBus {
  public:
    // Half a bit period, microseconds. 2 is ~250 kHz and leaves margin for the
    // pull-up to charge a slightly long cable. A bit-bang that is slightly too
    // fast fails intermittently and is miserable to debug, so this is the
    // conservative choice.
    static const uint32_t DEFAULT_HALF_US = 2;
    // How long to wait for SCL to come up before calling the bus wedged. The
    // AS5600 never stretches, so this only fires on a short or a slave left
    // mid-byte.
    static const uint32_t STRETCH_US = 1000;

    SoftI2c(int sdaPin, int sclPin, uint32_t halfUs = DEFAULT_HALF_US)
        : sda_(sdaPin), scl_(sclPin), halfUs_(halfUs) {}
    bool begin() override;
    bool writeRead(uint8_t addr, const uint8_t *w, size_t wn, uint8_t *r, size_t rn) override;
    bool write(uint8_t addr, const uint8_t *w, size_t wn) override;
    bool probe(uint8_t addr) override;
    const char *kind() const override { return "bit-banged"; }

    // If we reset partway through a read, the slave can be left driving SDA low
    // waiting for the rest of its byte. Nine clocks walk it to the end of that
    // byte and a stop resets its state machine.
    void recoverBus();

  private:
    bool start();
    void stop();
    bool writeByte(uint8_t b);
    bool readByte(uint8_t &out, bool ack);
    bool sendBit(bool bit);
    bool sclHigh();
    inline void driveLow(int pin);
    inline void release(int pin);
    inline bool readPin(int pin) const;
    inline void hold() const;

    int sda_, scl_;
    uint32_t halfUs_;
};
