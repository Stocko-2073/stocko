// Bench check for the TMC2209's single-wire UART, before any of it goes into
// the servo sketch. Answers one question: is the XIAO talking to the driver?
//
// Wiring under test, XIAO ESP32-C6:
//   D6 / GPIO16 (TX) --[1k]--+-- TMC2209 PDN_UART
//   D7 / GPIO17 (RX) --------+
//   D0 / GPIO0 -> EN, common GND, common 3V3 to VIO
//
// The link is half duplex, so every byte the XIAO sends comes back on RX ahead
// of the driver's answer. That echo is the useful part of the diagnosis -- it
// splits a wiring fault from a driver that will not answer:
//
//   no echo          the 1k between D6 and D7 isn't there, or a pin is wrong
//   echo, no reply   XIAO side is fine, driver isn't talking back. Motor power
//                    is the first suspect: the TMC2209 runs its digital core
//                    off VS, not VIO, so with VMOT dead it is deaf on UART even
//                    though its logic pins still look alive
//   echo + reply     link is up, and VERSION should read 0x21
//
// EN is parked high throughout, so the driver stays disabled and nothing can
// move. Reads have no side effects; the one write is a GSTAT flag clear.

#include "Tmc2209Uart.h"

static const uint8_t PIN_EN = D0;
static const uint8_t PIN_TX = D6;  // GPIO16
static const uint8_t PIN_RX = D7;  // GPIO17

static const uint32_t BAUDS[] = {57600, 115200, 250000, 500000};
static const uint8_t  NBAUDS  = sizeof(BAUDS) / sizeof(BAUDS[0]);

static Tmc2209Uart tmc(Serial1, PIN_RX, PIN_TX);

static void hex32(uint32_t v) {
  Serial.print(F("0x"));
  for (int8_t s = 28; s >= 0; s -= 4) Serial.print((int)((v >> s) & 0xF), HEX);
}

static void hexDump(const Tmc2209Uart::Result &r) {
  Serial.print(F("        raw:"));
  for (uint8_t i = 0; i < r.n; i++) {
    Serial.print(i == 4 ? F("  |  ") : F(" "));
    if (r.buf[i] < 0x10) Serial.print('0');
    Serial.print(r.buf[i], HEX);
  }
  if (r.n == 0) Serial.print(F(" (nothing)"));
  Serial.println();
}

// What is actually out there on the line? The echo only proves the 1k between
// D6 and D7, which loops back locally -- a wire dangling in mid air echoes just
// as well as one landing on PDN_UART. These tests reach past the resistor.
static void lineCheck() {
  tmc.end();
  delay(5);

  // 1. DC continuity of the D6--1k--D7 path itself.
  pinMode(PIN_RX, INPUT);
  pinMode(PIN_TX, OUTPUT);
  digitalWrite(PIN_TX, HIGH);
  delayMicroseconds(500);
  bool hi = digitalRead(PIN_RX);
  digitalWrite(PIN_TX, LOW);
  delayMicroseconds(500);
  bool lo = digitalRead(PIN_RX);
  digitalWrite(PIN_TX, HIGH);

  Serial.print(F("  1k path:  D6 high -> D7 "));
  Serial.print(hi ? F("HIGH") : F("LOW"));
  Serial.print(F(",  D6 low -> D7 "));
  Serial.print(lo ? F("HIGH") : F("LOW"));
  Serial.println((hi && !lo) ? F("   [ok]") : F("   [BROKEN]"));

  // 2. Tri-state D6 so the 1k dangles, then lean on the line with the XIAO's
  //    own ~45k pulls. A powered CMOS pin at the far end usually has a pull of
  //    its own and will win; an unconnected wire just follows whichever pull
  //    we apply.
  pinMode(PIN_TX, INPUT);
  pinMode(PIN_RX, INPUT_PULLDOWN);
  delayMicroseconds(2000);
  bool withPd = digitalRead(PIN_RX);
  pinMode(PIN_RX, INPUT_PULLUP);
  delayMicroseconds(2000);
  bool withPu = digitalRead(PIN_RX);
  pinMode(PIN_RX, INPUT);

  Serial.print(F("  far end:  D7 with pulldown reads "));
  Serial.print(withPd ? F("HIGH") : F("LOW"));
  Serial.print(F(", with pullup reads "));
  Serial.println(withPu ? F("HIGH") : F("LOW"));
  if (withPd && !withPu) {
    Serial.println(F("            -> line is being driven both ways?? unexpected"));
  } else if (withPd) {
    Serial.println(F("            -> something out there pulls UP: the wire"));
    Serial.println(F("               reaches a powered pin."));
  } else if (!withPu) {
    Serial.println(F("            -> something out there pulls DOWN."));
  } else {
    Serial.println(F("            -> line floats: nothing external is holding it."));
    Serial.println(F("               Either the wire is not connected, or PDN is"));
    Serial.println(F("               a true high-Z input."));
  }

  // 3. Charge the line through the 1k and time the edge. Bare wire is a few pF
  //    and follows within a microsecond or two; a real trace with a bypass cap
  //    on it takes tens of microseconds. Capacitance means something is there.
  pinMode(PIN_TX, OUTPUT);
  uint32_t rise = 0, fall = 0;
  for (uint8_t i = 0; i < 8; i++) {
    digitalWrite(PIN_TX, LOW);
    delayMicroseconds(3000);
    uint32_t t0 = micros();
    digitalWrite(PIN_TX, HIGH);
    while (digitalRead(PIN_RX) == LOW && (micros() - t0) < 20000) {}
    rise += micros() - t0;

    delayMicroseconds(3000);
    t0 = micros();
    digitalWrite(PIN_TX, LOW);
    while (digitalRead(PIN_RX) == HIGH && (micros() - t0) < 20000) {}
    fall += micros() - t0;
  }
  digitalWrite(PIN_TX, HIGH);
  Serial.print(F("  edge time: rise "));
  Serial.print(rise / 8);
  Serial.print(F(" us, fall "));
  Serial.print(fall / 8);
  Serial.println(F(" us  (a bare wire is ~1-3 us)"));
}

static void decodeIOIN(uint32_t v) {
  uint8_t ms = (uint8_t)((((v >> 3) & 1) << 1) | ((v >> 2) & 1));
  Serial.print(F("    IOIN     = ")); hex32(v);
  Serial.print(F("   VERSION=0x")); Serial.print((int)((v >> 24) & 0xFF), HEX);
  Serial.println(((v >> 24) & 0xFF) == 0x21 ? F("  (TMC2209)") : F("  (expected 0x21!)"));
  Serial.print(F("               ENN="));  Serial.print((int)(v & 1));
  Serial.print(F(" MS1="));  Serial.print((int)((v >> 2) & 1));
  Serial.print(F(" MS2="));  Serial.print((int)((v >> 3) & 1));
  Serial.print(F(" DIAG=")); Serial.print((int)((v >> 4) & 1));
  Serial.print(F(" PDN="));  Serial.print((int)((v >> 6) & 1));
  Serial.print(F(" STEP=")); Serial.print((int)((v >> 7) & 1));
  Serial.print(F(" DIR="));  Serial.println((int)((v >> 9) & 1));
  Serial.print(F("               MS2:MS1 gives UART address "));
  Serial.print(ms);
  Serial.print(F(", microstep "));
  switch (ms) {
    case 0:  Serial.println(F("1/8"));  break;
    case 1:  Serial.println(F("1/2"));  break;
    case 2:  Serial.println(F("1/4"));  break;
    default: Serial.println(F("1/16")); break;
  }
}

static void tryWrite(uint8_t addr, uint8_t reg, uint32_t val, const char *what) {
  Tmc2209Uart::Result before = tmc.read(addr, Tmc2209Uart::IFCNT);
  delay(5);                                   // rule out bus turnaround
  Tmc2209Uart::Result echo = tmc.write(addr, reg, val);
  delay(2);
  Tmc2209Uart::Result after = tmc.read(addr, Tmc2209Uart::IFCNT);

  Serial.print(F("    write ")); Serial.print(what); Serial.print(F(": sent"));
  for (uint8_t i = 8; i < 16; i++) {
    Serial.print(' ');
    if (echo.buf[i] < 0x10) Serial.print('0');
    Serial.print(echo.buf[i], HEX);
  }
  Serial.print(F("  echo"));
  if (echo.n == 0) {
    Serial.print(F(" (none)"));
  } else {
    for (uint8_t i = 0; i < echo.n; i++) {
      Serial.print(' ');
      if (echo.buf[i] < 0x10) Serial.print('0');
      Serial.print(echo.buf[i], HEX);
    }
  }
  Serial.println(echo.st == Tmc2209Uart::OK ? F("  [line ok]") : F("  [ECHO MISMATCH]"));

  Serial.print(F("      IFCNT "));
  if (before.st == Tmc2209Uart::OK && after.st == Tmc2209Uart::OK) {
    Serial.print((int)(before.value & 0xFF));
    Serial.print(F(" -> "));
    Serial.print((int)(after.value & 0xFF));
    Serial.println((uint8_t)(after.value - before.value) ? F("   accepted")
                                                         : F("   REJECTED"));
  } else {
    Serial.println(F("unreadable"));
  }
}

static void detail(uint8_t addr) {
  Serial.println();
  Serial.print(F("--- driver at address ")); Serial.print(addr);
  Serial.println(F(" ---"));

  Tmc2209Uart::Result r = tmc.read(addr, Tmc2209Uart::IOIN);
  if (r.st == Tmc2209Uart::OK) decodeIOIN(r.value);

  r = tmc.read(addr, Tmc2209Uart::GCONF);
  if (r.st == Tmc2209Uart::OK) {
    Serial.print(F("    GCONF    = ")); hex32(r.value);
    Serial.print(F("   pdn_disable=")); Serial.print((int)((r.value >> 6) & 1));
    Serial.print(F(" mstep_reg_select=")); Serial.println((int)((r.value >> 7) & 1));
  }

  r = tmc.read(addr, Tmc2209Uart::GSTAT);
  if (r.st == Tmc2209Uart::OK) {
    Serial.print(F("    GSTAT    = ")); hex32(r.value);
    Serial.print(F("   reset=")); Serial.print((int)(r.value & 1));
    Serial.print(F(" drv_err=")); Serial.print((int)((r.value >> 1) & 1));
    Serial.print(F(" uv_cp=")); Serial.println((int)((r.value >> 2) & 1));
  }

  r = tmc.read(addr, Tmc2209Uart::CHOPCONF);
  if (r.st == Tmc2209Uart::OK) {
    Serial.print(F("    CHOPCONF = ")); hex32(r.value);
    Serial.print(F("   toff=")); Serial.println((int)(r.value & 0xF));
  }

  r = tmc.read(addr, Tmc2209Uart::DRVSTATUS);
  if (r.st == Tmc2209Uart::OK) {
    Serial.print(F("    DRVSTATUS= ")); hex32(r.value);
    Serial.print(F("   stst=")); Serial.print((int)((r.value >> 31) & 1));
    Serial.print(F(" otpw=")); Serial.print((int)(r.value & 1));
    Serial.print(F(" ot=")); Serial.println((int)((r.value >> 1) & 1));
  }

  // Does the driver accept writes? IFCNT counts every one it takes, so it is
  // the ground truth -- writes get no acknowledgement of their own.
  delay(2);
  tryWrite(addr, Tmc2209Uart::GSTAT, 0x00000007, "GSTAT clear");
  delay(2);
  tryWrite(addr, Tmc2209Uart::GCONF, 0x00000141, "GCONF pdn_disable");
  delay(2);

  Tmc2209Uart::Result g2 = tmc.read(addr, Tmc2209Uart::GCONF);
  if (g2.st == Tmc2209Uart::OK) {
    Serial.print(F("    GCONF now = ")); hex32(g2.value);
    Serial.println(((g2.value >> 6) & 1) ? F("   pdn_disable took")
                                         : F("   unchanged"));
  }
}

static void scanMode(bool openDrain, int8_t &foundAddr,
                     uint32_t &foundBaud, bool &foundOD) {
  Serial.println();
  Serial.print(F("  -- "));
  Serial.print(openDrain ? F("open drain TX (pull-ups on)") : F("push-pull TX"));
  Serial.println(F(" --"));

  for (uint8_t b = 0; b < NBAUDS; b++) {
    tmc.begin(BAUDS[b], openDrain);
    Serial.print(F("  "));
    Serial.print(BAUDS[b]);
    Serial.print(F(" baud:"));

    Tmc2209Uart::Result worst;
    worst.n = 0;
    for (uint8_t a = 0; a < 4; a++) {
      Tmc2209Uart::Result r = tmc.read(a, Tmc2209Uart::IOIN);
      Serial.print(F(" addr")); Serial.print(a); Serial.print(':');
      if (r.st == Tmc2209Uart::OK) {
        Serial.print(F(" IOIN=")); hex32(r.value);
        if (foundAddr < 0) { foundAddr = (int8_t)a; foundBaud = BAUDS[b]; foundOD = openDrain; }
      } else {
        Serial.print(r.st == Tmc2209Uart::NO_REPLY ? F("no-reply") : F("ECHO-FAIL"));
        worst = r;
      }
    }
    Serial.println();
    if (worst.n && worst.st != Tmc2209Uart::NO_REPLY) hexDump(worst);

    if (foundAddr >= 0 && foundBaud == BAUDS[b]) detail((uint8_t)foundAddr);
  }

}

// Two questions the servo actually needs answered: does a write survive with no
// pacing at all, and what does one cost the control loop. The loop will not
// wait for an echo, so the cost that matters is the blocking time of handing
// eight bytes to the TX FIFO with a millisecond of quiet either side.
static void timingTest(uint8_t addr) {
  static const uint32_t BR[] = {57600, 115200, 250000, 500000};
  static const uint8_t  NBR  = sizeof(BR) / sizeof(BR[0]);
  static const uint8_t  TRIES = 20;

  Serial.println();
  Serial.println(F("--- write pacing, no gap between datagrams ---"));
  Serial.println(F("    baud   read->write   fire+forget   cost/write"));

  for (uint8_t i = 0; i < NBR; i++) {
    tmc.begin(BR[i], false);
    tmc.read(addr, Tmc2209Uart::IOIN);   // first one after begin() is lost
    delay(5);

    // A write issued the instant a read reply lands.
    uint8_t ok = 0;
    for (uint8_t t = 0; t < TRIES; t++) {
      Tmc2209Uart::Result b = tmc.read(addr, Tmc2209Uart::IFCNT);
      if (b.st != Tmc2209Uart::OK) continue;
      tmc.write(addr, Tmc2209Uart::VACTUAL, 0);
      delay(2);
      Tmc2209Uart::Result a = tmc.read(addr, Tmc2209Uart::IFCNT);
      if (a.st == Tmc2209Uart::OK && (uint8_t)(a.value - b.value)) ok++;
      delay(2);
    }

    // The servo pattern: one write per millisecond, echo ignored.
    Tmc2209Uart::Result b0 = tmc.read(addr, Tmc2209Uart::IFCNT);
    delay(5);
    uint32_t cost = 0;
    for (uint8_t t = 0; t < TRIES; t++) {
      uint32_t t0 = micros();
      tmc.writeFast(addr, Tmc2209Uart::VACTUAL, 0);
      cost += micros() - t0;
      delay(1);
    }
    delay(5);
    Tmc2209Uart::Result a0 = tmc.read(addr, Tmc2209Uart::IFCNT);

    Serial.print(F("  "));
    Serial.print(BR[i]);
    Serial.print(F("        "));
    Serial.print(ok); Serial.print('/'); Serial.print(TRIES);
    Serial.print(F("        "));
    if (b0.st == Tmc2209Uart::OK && a0.st == Tmc2209Uart::OK) {
      Serial.print((int)(uint8_t)(a0.value - b0.value));
    } else {
      Serial.print('?');
    }
    Serial.print('/'); Serial.print(TRIES);
    Serial.print(F("        "));
    Serial.print(cost / TRIES);
    Serial.println(F(" us"));
  }
}

// The killswitch question: EN is only a killswitch if the driver actually sees
// a high while the MCU is not driving the pin. During reset the XIAO releases
// GPIO0, so what matters is where the line sits with nothing holding it. IOIN
// reports the pin as the driver sees it, which is the honest way to ask.
//
// The chopper is turned off first, so nothing energises whatever EN does here.
static void enPinTest(uint8_t addr) {
  Tmc2209Uart::Result c = tmc.read(addr, Tmc2209Uart::CHOPCONF);
  uint32_t chop = (c.st == Tmc2209Uart::OK) ? c.value : 0x15010053UL;
  delay(2);
  tmc.write(addr, Tmc2209Uart::VACTUAL, 0);
  delay(2);
  tmc.write(addr, Tmc2209Uart::CHOPCONF, chop & ~0xFUL);   // toff=0, coils idle
  delay(2);

  Serial.println();
  Serial.println(F("--- EN as a hardware killswitch ---"));

  int8_t driven = -1, released = -1, low = -1;

  pinMode(PIN_EN, OUTPUT);
  digitalWrite(PIN_EN, HIGH);
  delay(2);
  Tmc2209Uart::Result r = tmc.read(addr, Tmc2209Uart::IOIN);
  if (r.st == Tmc2209Uart::OK) driven = (int8_t)(r.value & 1);
  delay(2);

  digitalWrite(PIN_EN, LOW);
  delay(2);
  r = tmc.read(addr, Tmc2209Uart::IOIN);
  if (r.st == Tmc2209Uart::OK) low = (int8_t)(r.value & 1);
  delay(2);

  // Released, exactly as the pin sits while the XIAO is in reset.
  pinMode(PIN_EN, INPUT);
  delay(10);
  r = tmc.read(addr, Tmc2209Uart::IOIN);
  if (r.st == Tmc2209Uart::OK) released = (int8_t)(r.value & 1);

  pinMode(PIN_EN, OUTPUT);       // park it safe again before anything else
  digitalWrite(PIN_EN, HIGH);
  delay(2);
  tmc.write(addr, Tmc2209Uart::CHOPCONF, chop);
  delay(2);

  Serial.print(F("  D0 driven HIGH -> driver reads ENN="));
  Serial.print((int)driven); Serial.println(F("  (disabled)"));
  Serial.print(F("  D0 driven LOW  -> driver reads ENN="));
  Serial.print((int)low); Serial.println(F("  (enabled)"));
  Serial.print(F("  D0 released    -> driver reads ENN="));
  Serial.println((int)released);
  if (released == 1) {
    Serial.println(F("  -> floats HIGH: the driver disables itself while the MCU"));
    Serial.println(F("     is in reset. The killswitch is fail-safe as wired."));
  } else if (released == 0) {
    Serial.println(F("  -> floats LOW: the driver stays ENABLED while the MCU is"));
    Serial.println(F("     in reset, and VACTUAL keeps stepping. Needs a pull-up"));
    Serial.println(F("     to VIO on EN to be fail-safe."));
  } else {
    Serial.println(F("  -> could not read it back."));
  }
}

static void scan() {
  Serial.println();
  Serial.println(F("=== TMC2209 UART probe ==="));
  Serial.println(F("D6/GPIO16 TX, D7/GPIO17 RX, EN parked HIGH"));
  Serial.println();

  lineCheck();

  int8_t   foundAddr = -1;
  uint32_t foundBaud = 0;
  bool     foundOD   = false;

  scanMode(false, foundAddr, foundBaud, foundOD);
  scanMode(true,  foundAddr, foundBaud, foundOD);

  if (foundAddr >= 0) {
    timingTest((uint8_t)foundAddr);
    enPinTest((uint8_t)foundAddr);
  }

  Serial.println();
  if (foundAddr >= 0) {
    Serial.print(F("RESULT: talking to a TMC2209 at address "));
    Serial.print(foundAddr);
    Serial.print(F(", "));
    Serial.print(foundBaud);
    Serial.print(F(" baud, "));
    Serial.println(foundOD ? F("open drain TX.") : F("push-pull TX."));
  } else {
    Serial.println(F("RESULT: no answer from the driver, either drive mode."));
    Serial.println(F("  Wire should be on module pin 4 (RX), not pin 5 -- pin 5"));
    Serial.println(F("  is an unpopulated alternate on the V1.3."));
  }
  Serial.println(F("=== end ==="));
}

void setup() {
  // EN first, before anything else: the driver boots disabled.
  pinMode(PIN_EN, OUTPUT);
  digitalWrite(PIN_EN, HIGH);

  Serial.begin(115200);
  uint32_t start = millis();
  while (!Serial && (millis() - start) < 2000) delay(10);
}

void loop() {
  scan();
  delay(3000);
}
