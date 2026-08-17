// Bench test for an AS5600 magnetic encoder on a XIAO ESP32-C6.
//
// Library: RobTillaart/AS5600 (`arduino-cli lib install AS5600`) -- the same one
// the pet firmware's MultiTurnServo uses, so the calibration habits carry over.
//
// Wiring, XIAO ESP32-C6 default I2C:
//   AS5600 SDA -> D4 / GPIO22      VCC -> 3V3
//   AS5600 SCL -> D5 / GPIO23      GND -> GND
// DIR is left unwired; direction flips in software instead.
//
// One CSV sample per line at SAMPLE_HZ, for plot.py. Lines starting with '#' are
// human-readable notes, every other line is data:
//
//   t_ms,raw,deg,cum,dps,agc,magnitude,status
//
// Single-key commands over serial: z zero, d direction, p pause, i info, h help.

#include <Wire.h>
#include <AS5600.h>

static const uint32_t SERIAL_BAUD = 115200;
static const uint32_t SAMPLE_HZ   = 50;
static const uint32_t SAMPLE_US   = 1000000UL / SAMPLE_HZ;

// STATUS register bits. The library keeps its copies private to AS5600.cpp.
static const uint8_t MAGNET_HIGH   = 0x08;  // magnet too close
static const uint8_t MAGNET_LOW    = 0x10;  // magnet too far
static const uint8_t MAGNET_DETECT = 0x20;

AS5600 enc;  // &Wire, address 0x36 (fixed on the AS5600)

static bool     streaming  = true;
static uint32_t nextSample = 0;

static const char *magnetText(uint8_t status) {
  if (!(status & MAGNET_DETECT)) return "none";
  if (status & MAGNET_LOW) return "too weak (magnet too far / off-axis)";
  if (status & MAGNET_HIGH) return "too strong (magnet too close)";
  return "ok";
}

static void printInfo() {
  uint8_t  status = enc.readStatus();
  uint16_t raw    = enc.rawAngle();

  Serial.print(F("# AS5600 lib "));
  Serial.print(AS5600_LIB_VERSION);
  Serial.printf(", addr 0x%02X, SDA=%d SCL=%d @ 400kHz, %u Hz sampling\n",
                enc.getAddress(), SDA, SCL, SAMPLE_HZ);
  Serial.printf("# status 0x%02X  magnet %s\n", status, magnetText(status));
  // On 3V3 the AGC range is 0..128; mid-range means a healthy magnet gap.
  Serial.printf("# agc %u (0..128 on 3V3, aim for ~64)  magnitude %u\n",
                enc.readAGC(), enc.readMagnitude());
  Serial.printf("# raw %u = %.2f deg  direction %s  zmco %u  conf 0x%04X\n",
                raw, raw * AS5600_RAW_TO_DEGREES,
                enc.getDirection() == AS5600_CLOCK_WISE ? "CW" : "CCW",
                enc.getZMCO(), enc.getConfiguration());
  Serial.println(F("# 4096 counts/rev, 0.0879 deg/count"));
}

static void printHelp() {
  Serial.println(F("# commands: z=zero cumulative  d=flip direction  "
                   "p=pause/resume  i=info  h=help"));
}

static void handleCommands() {
  while (Serial.available()) {
    int c = Serial.read();
    switch (c) {
      case 'z':
        enc.resetCumulativePosition(0);
        Serial.println(F("# cumulative position zeroed"));
        break;
      case 'd': {
        bool cw = enc.getDirection() == AS5600_CLOCK_WISE;
        enc.setDirection(cw ? AS5600_COUNTERCLOCK_WISE : AS5600_CLOCK_WISE);
        // The angle mirrors, so the accumulated count is meaningless now.
        enc.resetCumulativePosition(0);
        Serial.printf("# direction %s, cumulative position zeroed\n", cw ? "CCW" : "CW");
        break;
      }
      case 'p':
        streaming = !streaming;
        Serial.printf("# %s\n", streaming ? "streaming" : "paused");
        if (streaming) nextSample = micros();
        break;
      case 'i': printInfo(); break;
      case 'h': printHelp(); break;
      case '\r':
      case '\n':
      case ' ': break;
      default: Serial.printf("# unknown command '%c', h for help\n", c); break;
    }
  }
}

void setup() {
  Serial.begin(SERIAL_BAUD);
  // USB CDC drops anything written before the host opens the port; wait briefly
  // so the startup banner actually lands.
  uint32_t start = millis();
  while (!Serial && (millis() - start) < 2000) delay(10);

  Wire.begin(SDA, SCL);
  Wire.setClock(400000);

  enc.begin();  // AS5600_SW_DIRECTION_PIN: no DIR pin wired
  enc.setDirection(AS5600_CLOCK_WISE);

  // Loop rather than bail out, so the sensor can be plugged in afterwards.
  uint32_t waited = 0;
  while (!enc.isConnected()) {
    if (waited % 1000 == 0) {
      Serial.println(F("# no AS5600 at 0x36 -- check SDA/D4, SCL/D5, 3V3, GND"));
    }
    delay(100);
    waited += 100;
  }

  printInfo();
  printHelp();
  Serial.println(F("# t_ms,raw,deg,cum,dps,agc,magnitude,status"));
  nextSample = micros();
}

void loop() {
  handleCommands();
  if (!streaming) return;

  if ((int32_t)(micros() - nextSample) < 0) return;
  nextSample += SAMPLE_US;
  // Fell more than a sample behind (USB stall)? Resync instead of burst-catching up.
  if ((int32_t)(micros() - nextSample) > (int32_t)SAMPLE_US) nextSample = micros() + SAMPLE_US;

  // One I2C read of the corrected angle; the cumulative count and the speed
  // both reuse that same sample rather than reading again.
  uint16_t raw = enc.readAngle();
  int err = enc.lastError();
  if (err != AS5600_OK) {
    Serial.printf("# i2c read error %d\n", err);
    return;
  }
  int32_t cum = enc.getCumulativePosition(false);
  float   dps = enc.getAngularSpeed(AS5600_MODE_DEGREES, false);

  Serial.printf("%lu,%u,%.2f,%ld,%.1f,%u,%u,0x%02X\n",
                millis(), raw, raw * AS5600_RAW_TO_DEGREES, cum, dps,
                enc.readAGC(), enc.readMagnitude(), enc.readStatus());
}
