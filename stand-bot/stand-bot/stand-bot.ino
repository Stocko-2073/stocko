// Target board: Seeed XIAO RP2040 (arduino-pico core).
#include <Servo.h>
#include <MPU6050_tockn.h>
#include <Wire.h>

MPU6050 mpu6050(Wire);
Servo foot;
const float IMU_MOUNT_ANGLE = 90.0f-0.5f;//+3.5f;
const int   SERVO_MIN_US    = 544;
const int   SERVO_MAX_US    = 2500;
const int   SERVO_CENTER_US = (SERVO_MIN_US + SERVO_MAX_US) / 2;
const float US_PER_DEGREE   = (SERVO_MAX_US - SERVO_MIN_US) / 180.0f;

// CoM-shifter PD: foot tilt is a direct function of body tilt error.
// Output is foot angle (deg from neutral), not velocity.
const float Kp           = 2.5f;   // foot deg per body deg
const float Kd           = -0.02f;   // foot deg per (body deg / sec)
const float MAX_FOOT_DEG = 90.0f;  // clamp foot deflection
const int   SIGN         = 1;     // flip to -1 if foot corrects the wrong way

const bool  RUN_DIRECTION_TEST = false; // sweep at startup to verify servo direction
const int   STALE_RESET_THRESHOLD = 3;  // consecutive stalls before forcing IMU reset (0 = never)
// MPU6050_ADDR (0x68) is defined by the MPU6050_tockn library header — used in resetIMU().

// Battery monitor: 2S Li-ion (8.4 V full / 6.0 V damage) via 100K/47K divider on A0.
// Cutoff at 7.4 V (~30% SoC) — comfortable margin above the steep 20% knee. The
// timer ISR samples + EMA-filters; on threshold cross it detaches the servo and
// parks the core in __wfi() forever. Living in the ISR (not the control loop)
// means the protection survives any experimentation in loop() — short of
// disabling interrupts globally, you can't accidentally turn it off.
const float BATT_CUTOFF_V   = 7.4f;
const float BATT_DIVIDER    = 47.0f / (100.0f + 47.0f) * 0.953f;    // 0.3197
const float ADC_VREF        = 3.3f;
const int   ADC_MAX_COUNTS  = 4095;                        // 12-bit
const float BATT_PER_COUNT  = ADC_VREF / ADC_MAX_COUNTS / BATT_DIVIDER;
const float BATT_EMA_ALPHA  = 0.05f;
const int   BATT_SAMPLE_MS  = 100;
// Trim BATT_PER_COUNT empirically: log battEMA at a known pack voltage and scale.

volatile float battEMA = -1.0f;
struct repeating_timer battTimer;

float setPoint = 0.0f;

bool battMonitorISR(struct repeating_timer *t) {
  static bool led_on = false;
  float v = analogRead(A0) * BATT_PER_COUNT;
  battEMA = (battEMA < 0.0f) ? v
                             : (BATT_EMA_ALPHA * v + (1.0f - BATT_EMA_ALPHA) * battEMA);
  if (battEMA < BATT_CUTOFF_V) {
    led_on = !led_on;
    digitalWrite(16, led_on);
    digitalWrite(17, led_on);
    foot.detach();
  } else {
    digitalWrite(16, true);
    digitalWrite(17, true);
  }
  return true;
}

void setup() {
  pinMode(25, OUTPUT);
  digitalWrite(25, true);
  pinMode(16, OUTPUT);
  digitalWrite(16, true);
  pinMode(17, OUTPUT);
  digitalWrite(17, true);

  Serial.begin(115200);
  foot.attach(D2, SERVO_MIN_US, SERVO_MAX_US);
  foot.writeMicroseconds(SERVO_CENTER_US);

  // Start battery monitor before Wire.begin — if I2C hangs during resetIMU,
  // the hardware-timer ISR still ticks and can shut us down.
  analogReadResolution(12);
  battEMA = analogRead(A0) * BATT_PER_COUNT;
  add_repeating_timer_ms(-BATT_SAMPLE_MS, battMonitorISR, NULL, &battTimer);

  Wire.begin();
  delay(15);
  resetIMU(); // hard-reset on boot - the chip keeps state across MCU resets
  Serial.println("Calibrating gyro - keep bot still...");
  mpu6050.calcGyroOffsets(true);

  if (RUN_DIRECTION_TEST) {
    Serial.println("Direction test:");
    Serial.println("  sweeping to +20 deg");
    for (int d = 0;  d <=  20; d++) { writeFootTilt(d); delay(30); }
    delay(600);
    Serial.println("  sweeping to -20 deg");
    for (int d = 20; d >= -20; d--) { writeFootTilt(d); delay(30); }
    delay(600);
    Serial.println("  returning to neutral");
    for (int d = -20; d <= 0; d++) { writeFootTilt(d); delay(30); }
    Serial.println("Note which way was '+'. If foot pushes the WRONG way during balancing, set SIGN = -1.");
    delay(1500);
  }
}

float readAngle() {
  // getAngleY() = complementary-filtered angle (gyro + accel). Immune to the
  // translational acceleration spikes that foot motion induces in the body.
  return fmodf(mpu6050.getAngleY()+IMU_MOUNT_ANGLE+360.0f,360.0f)-180.0f;
}

void writeFootTilt(float deg) {
  deg = constrain(deg, -MAX_FOOT_DEG, MAX_FOOT_DEG);
  foot.writeMicroseconds(SERVO_CENTER_US + (int)(deg * US_PER_DEGREE));
}

void resetIMU() {
  Serial.println("Resetting IMU...");

  // 1. Bus recovery. If a slave is holding SDA low mid-transaction, no I2C
  //    master command can get through. Toggle SCL up to 9 times to clock
  //    the slave out of its hung state, then issue a STOP condition.
  Wire.end();
  pinMode(SDA, INPUT_PULLUP);
  pinMode(SCL, OUTPUT);
  for (int i = 0; i < 9 && digitalRead(SDA) == LOW; i++) {
    digitalWrite(SCL, LOW);  delayMicroseconds(5);
    digitalWrite(SCL, HIGH); delayMicroseconds(5);
  }
  // Manual STOP: SDA low->high while SCL is high.
  pinMode(SDA, OUTPUT);
  digitalWrite(SDA, LOW);  delayMicroseconds(5);
  digitalWrite(SCL, HIGH); delayMicroseconds(5);
  digitalWrite(SDA, HIGH); delayMicroseconds(5);

  // 2. Re-init Wire (reclaims the pins for I2C peripheral).
  Wire.begin();

  // 3. Software reset the chip via PWR_MGMT_1 (reg 0x6B), bit 7 = DEVICE_RESET.
  Wire.beginTransmission(MPU6050_ADDR);
  Wire.write(0x6B);
  Wire.write(0x80);
  Wire.endTransmission();
  delay(100); // datasheet: chip needs ~100 ms to come back

  // 4. Wake from sleep, clock source = PLL with X gyro reference.
  Wire.beginTransmission(MPU6050_ADDR);
  Wire.write(0x6B);
  Wire.write(0x01);
  Wire.endTransmission();

  // 5. Re-init the library state. Note: this does NOT re-run gyro calibration
  //    (that needs ~3 s of stillness, which we can't do mid-balance). The
  //    offsets stored from boot calibration remain in the library.
  mpu6050.begin();
}

void loop() {
  static float previousError  = 0.0f;
  static unsigned long lastUs = 0;
  static bool initialized     = false;
  static int  c               = 0;

  mpu6050.update();
  float angle = readAngle();

  if (!initialized) {
    lastUs        = micros();
    initialized   = true;
    delay(7);
    return;
  }

  unsigned long now = micros();
  float dt = (now - lastUs) * 1e-6f;
  lastUs = now;

  // Stale-iteration guard. If dt blows up (typically the Wire/I2C call hung
  // for ~2 s while the IMU was unreachable), the angle and previousError are
  // stale and the D-term would be a huge false kick. Re-anchor state, hold
  // the last servo command, and skip the control update. After
  // STALE_RESET_THRESHOLD consecutive stalls, force an IMU reset.
  const float MAX_DT = 0.05f; // 50 ms
  static int consecutiveStales = 0;
  if (dt > MAX_DT || dt <= 0.0f) {
    previousError = setPoint - angle;
    consecutiveStales++;
    Serial.print("STALE dt(ms):"); Serial.println(dt * 1000.0f);
    if (STALE_RESET_THRESHOLD > 0 && consecutiveStales >= STALE_RESET_THRESHOLD) {
      resetIMU();
      consecutiveStales = 0;
      lastUs = micros();
    }
    delay(7);
    return;
  }
  consecutiveStales = 0;

  float error      = setPoint - angle;
  float derivative = (error - previousError) / dt;
  previousError    = error;

  float footTilt = SIGN * (Kp * error + Kd * derivative);
  writeFootTilt(footTilt);

  if (c >= 10) {
    c = 0;
    Serial.print("err:");   Serial.print(error);
    Serial.print(" foot:"); Serial.print(footTilt);
    Serial.print(" dt:");   Serial.print(dt * 1000.0f);
    Serial.print(" batt:"); Serial.println(battEMA);
  }
  c++;
  delay(7);
}


