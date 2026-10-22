#pragma once
#include <Arduino.h>
#include "driver/gpio.h"
#include "soc/gpio_struct.h"

// The TMC2209's single-wire UART, close to the metal: build a datagram, put it
// on the line, read the echo back off it, keep what follows.
//
// Half duplex is the whole character of this interface. TX reaches PDN_UART
// through a 1k, RX sits on the pin itself, so everything sent arrives back
// first. Rather than hide that echo, this keeps it -- when the link is broken
// the echo is what tells you which half is at fault.

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
    Status   st;
    uint32_t value;
    uint8_t  buf[16];  // echo and reply, as they arrived
    uint8_t  n;
  };

  static const uint8_t GCONF     = 0x00;
  static const uint8_t GSTAT     = 0x01;
  static const uint8_t IFCNT     = 0x02;
  static const uint8_t IOIN      = 0x06;
  static const uint8_t VACTUAL   = 0x22;
  static const uint8_t CHOPCONF  = 0x6C;
  static const uint8_t DRVSTATUS = 0x6F;

  Tmc2209Uart(HardwareSerial &port, uint8_t rxPin, uint8_t txPin)
      : port_(port), rx_(rxPin), tx_(txPin) {}

  // Two ways to drive the line. Push-pull is the textbook arrangement and wants
  // a series resistor between TX and PDN_UART. Open drain suits a stick that
  // already has that resistor onboard: TX only ever pulls down, so it cannot
  // fight the driver's reply, and a pull-up idles the line high. The cost is
  // rise time -- the internal pull-ups are ~45k, so keep the baud modest.
  void begin(uint32_t baud, bool openDrain) {
    port_.end();
    delay(5);
    port_.begin(baud, SERIAL_8N1, rx_, tx_);
    delay(5);
    // Poke the pad's open-drain bit directly. pinMode() here would re-point the
    // GPIO matrix and take the UART off the pin.
    GPIO.pin[tx_].pad_driver = openDrain ? 1 : 0;
    gpio_set_pull_mode((gpio_num_t)tx_, openDrain ? GPIO_PULLUP_ONLY : GPIO_FLOATING);
    gpio_set_pull_mode((gpio_num_t)rx_, openDrain ? GPIO_PULLUP_ONLY : GPIO_FLOATING);
    delay(5);
  }

  void end() { port_.end(); }

  Result read(uint8_t addr, uint8_t reg) {
    Result r;
    r.st = NO_ECHO;
    r.value = 0;
    r.n = 0;

    drain();
    uint8_t req[4] = {0x05, addr, reg, 0};
    req[3] = crc(req, 3);
    port_.write(req, 4);
    port_.flush();

    // 4 bytes of echo, then an 8 byte reply if the driver is listening.
    uint32_t t0 = millis();
    while (r.n < 12 && (millis() - t0) < 40) {
      if (port_.available()) r.buf[r.n++] = port_.read();
    }

    if (r.n == 0)                             { r.st = NO_ECHO;     return r; }
    if (r.n < 4 || memcmp(r.buf, req, 4) != 0){ r.st = BAD_ECHO;    return r; }
    if (r.n == 4)                             { r.st = NO_REPLY;    return r; }
    if (r.n < 12)                             { r.st = SHORT_REPLY; return r; }

    const uint8_t *p = r.buf + 4;
    if (p[0] != 0x05 || p[1] != 0xFF || p[2] != reg) { r.st = BAD_FRAME; return r; }
    if (crc(p, 7) != p[7])                           { r.st = BAD_CRC;   return r; }

    r.value = ((uint32_t)p[3] << 24) | ((uint32_t)p[4] << 16) |
              ((uint32_t)p[5] << 8)  |  (uint32_t)p[6];
    r.st = OK;
    return r;
  }

  // Writes are unacknowledged; IFCNT is how you find out one landed. The echo
  // is still worth keeping -- it says whether the line carried the datagram,
  // which separates "driver rejected it" from "it never arrived intact".
  Result write(uint8_t addr, uint8_t reg, uint32_t val) {
    uint8_t d[8] = {0x05, addr, (uint8_t)(reg | 0x80),
                    (uint8_t)(val >> 24), (uint8_t)(val >> 16),
                    (uint8_t)(val >> 8),  (uint8_t)val, 0};
    d[7] = crc(d, 7);
    drain();
    port_.write(d, 8);
    port_.flush();

    Result r;
    r.value = 0;
    r.n = 0;
    uint32_t t0 = millis();
    while (r.n < 8 && (millis() - t0) < 40) {
      if (port_.available()) r.buf[r.n++] = port_.read();
    }
    r.st = (r.n == 8 && memcmp(r.buf, d, 8) == 0) ? OK : BAD_ECHO;
    memcpy(r.buf + 8, d, 8);   // what we meant to send, for comparison
    return r;
  }

  // Fire and forget: hand the datagram to the TX FIFO and go. The servo loop
  // does not care about the echo, and waiting for it costs more than the write.
  // Whatever came back last time gets dropped on the way in.
  void writeFast(uint8_t addr, uint8_t reg, uint32_t val) {
    uint8_t d[8] = {0x05, addr, (uint8_t)(reg | 0x80),
                    (uint8_t)(val >> 24), (uint8_t)(val >> 16),
                    (uint8_t)(val >> 8),  (uint8_t)val, 0};
    d[7] = crc(d, 7);
    drain();
    port_.write(d, 8);
  }

  static const char *statusName(Status s) {
    switch (s) {
      case OK:          return "ok";
      case NO_ECHO:     return "NO ECHO -- nothing came back on RX at all";
      case BAD_ECHO:    return "BAD ECHO -- RX saw bytes, but not the ones sent";
      case NO_REPLY:    return "echo ok, NO REPLY from driver";
      case SHORT_REPLY: return "echo ok, reply truncated";
      case BAD_FRAME:   return "reply framing wrong";
      case BAD_CRC:     return "reply CRC bad -- link is noisy";
    }
    return "?";
  }

  // Datasheet's swuart_calcCRC: x^8 + x^2 + x + 1, fed LSB first.
  static uint8_t crc(const uint8_t *d, size_t n) {
    uint8_t c = 0;
    for (size_t i = 0; i < n; i++) {
      uint8_t b = d[i];
      for (uint8_t j = 0; j < 8; j++) {
        c = ((c >> 7) ^ (b & 0x01)) ? (uint8_t)((c << 1) ^ 0x07) : (uint8_t)(c << 1);
        b >>= 1;
      }
    }
    return c;
  }

 private:
  void drain() { while (port_.available()) port_.read(); }

  HardwareSerial &port_;
  uint8_t rx_, tx_;
};
