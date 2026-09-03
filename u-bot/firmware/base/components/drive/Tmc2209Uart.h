#pragma once
#include <stdint.h>
#include <string.h>

#include "driver/uart.h"
#include "freertos/FreeRTOS.h"
#include "freertos/semphr.h"

// The TMC2209's single-wire UART, close to the metal: build a datagram, put it
// on the line, read the echo back off it, keep what follows.
//
// Half duplex is the whole character of this interface. TX reaches PDN_UART
// through a 1k, RX sits on the pin itself, so everything sent arrives back
// first. Rather than hide that echo, this keeps it -- when the link is broken
// the echo is what tells you which half is at fault.
//
// Two drivers share the bus (addresses 0 and 1), and two tasks may want it --
// the control loop writing VACTUAL and the console reading a status register --
// so every transaction takes the bus mutex. Push-pull only: open-drain TX
// stopped working when the second driver joined (DRIVE_MECHANISM.md).
class Tmc2209Uart {
  public:
    enum Status {
        OK,
        NO_ECHO,      // nothing came back at all: TX and RX are not connected
        BAD_ECHO,     // bytes came back, but not the ones sent
        NO_REPLY,     // echo fine, driver said nothing
        SHORT_REPLY,
        BAD_FRAME,
        BAD_CRC
    };

    struct Result {
        Status st;
        uint32_t value;
        uint8_t buf[16];  // echo and reply, as they arrived
        uint8_t n;
    };

    static const uint8_t GCONF      = 0x00;
    static const uint8_t GSTAT      = 0x01;
    static const uint8_t IFCNT      = 0x02;
    static const uint8_t IOIN       = 0x06;
    static const uint8_t IHOLD_IRUN = 0x10;
    static const uint8_t TPOWERDOWN = 0x11;
    static const uint8_t TSTEP      = 0x12;
    static const uint8_t VACTUAL    = 0x22;
    static const uint8_t MSCNT      = 0x6A;
    static const uint8_t CHOPCONF   = 0x6C;
    static const uint8_t DRVSTATUS  = 0x6F;

    Tmc2209Uart(uart_port_t port, int rxPin, int txPin)
        : port_(port), rx_(rxPin), tx_(txPin) {}

    // Installs the UART driver and points it at the pins. Safe to call again
    // to change baud. The first datagram after this is always lost -- the pad
    // reconfiguration glitches the line -- so callers send a throwaway read.
    bool begin(uint32_t baud);
    void end();
    bool ready() const { return installed_; }

    Result read(uint8_t addr, uint8_t reg);

    // Writes are unacknowledged; IFCNT is how you find out one landed. The echo
    // is still worth keeping -- it says whether the line carried the datagram,
    // which separates "driver rejected it" from "it never arrived intact".
    Result write(uint8_t addr, uint8_t reg, uint32_t val);

    // How many writes came back with a wrong or missing echo since boot. A
    // steadily climbing number with the motors running is a bus problem.
    uint32_t echoFaults() const { return echoFaults_; }
    uint32_t writes() const { return writes_; }

    static const char *statusName(Status s);

    // Datasheet's swuart_calcCRC: x^8 + x^2 + x + 1, fed LSB first.
    static uint8_t crc(const uint8_t *d, size_t n);

  private:
    void drain();
    int readBytes(uint8_t *dst, int want, uint32_t timeoutMs);
    void lock();
    void unlock();

    uart_port_t port_;
    int rx_, tx_;
    bool installed_ = false;
    SemaphoreHandle_t mtx_ = nullptr;
    uint32_t echoFaults_ = 0;
    uint32_t writes_ = 0;
};
