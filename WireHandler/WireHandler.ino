#include <ESP32Servo.h>

Servo cutter;

const int enPin = D0;
const int stepPin = D1;
const int dirPin = D2;
const float stepsPerMm = 500.0f/82.0f;

// --- trapezoidal motion profile (tune these to your motor/load) ---
const unsigned long minStepDelayUs   = 7000;   // step interval at cruise (fastest)
const unsigned long startStepDelayUs = 9000;  // step interval at start/stop (slowest)
const long accelSteps                = 200;   // steps spent ramping up (and down)

const int openPos  = 90;   // blade retracted, clear of the wire (TUNE THIS)
const int stripPos = 170;   // partial cut to score insulation
const int pullPos = 140;    // position the cutter to pull insulation from the wire
const int cutPos   = 180;   // full cut to sever the wire
const int cutDwellMs = 400; // time for the servo/blade to reach position

String cmdBuffer = "";

void enableMotor() {
  digitalWrite(enPin,LOW);
  delay(1500);             // let the driver wake up before stepping
}

void disableMotor() {
  delay(500);              // let the last step settle before cutting power
  digitalWrite(enPin,HIGH);
}

// step the motor; caller must enable the driver first (see enableMotor)
void move(float mm,bool forward) {
  long steps = (long)roundf(stepsPerMm*mm);
  if (steps <= 0) return;

  digitalWrite(dirPin, forward?LOW:HIGH);

  // ramp over accelSteps at each end; for short moves the ramp is
  // clamped to half the move so it stays triangular (no cruise phase)
  long ramp = accelSteps;
  if (ramp > steps/2) ramp = steps/2;
  unsigned long delta = startStepDelayUs - minStepDelayUs;

  for(long x = 0; x < steps; x++) {
    unsigned long d;
    if (x < ramp) {
      d = startStepDelayUs - (delta * x) / ramp;            // accelerating
    } else if (x >= steps - ramp) {
      long k = steps - 1 - x;                               // steps remaining
      d = startStepDelayUs - (delta * k) / ramp;            // decelerating
    } else {
      d = minStepDelayUs;                                   // cruising
    }

    digitalWrite(stepPin, HIGH);
    delayMicroseconds(5);
    digitalWrite(stepPin, LOW);
    delayMicroseconds(d);
  }
}

// drive the cutter to a position, then retract to open
void cut(int pos) {
  delay(cutDwellMs);
  cutter.write(pos);
  delay(cutDwellMs);
  cutter.write(openPos);
  delay(cutDwellMs);
}

void strip(float mm) {
  delay(cutDwellMs);
  cutter.write(stripPos);
  delay(cutDwellMs);
  cutter.write(openPos);
  delay(cutDwellMs);
  move(mm,false);
  delay(cutDwellMs);
  move(mm,true);
  delay(cutDwellMs);
  cutter.write(pullPos);
  delay(cutDwellMs);
  move(mm,false);
  cutter.write(openPos);
  delay(cutDwellMs);
}

void printHelp() {
  Serial.println();
  Serial.println(F("WireHandler serial console"));
  Serial.println(F("Commands:"));
  Serial.println(F("  mm <n>     move <n> millimetres"));
  Serial.println(F("  in <n>     move <n> inches"));
  Serial.println(F("  j <len>    feed a breadboard jumper of <len>"));
  Serial.println(F("  c <deg>    set cutter servo position 0-240"));
  Serial.println(F("  help / ?   show this help"));
  Serial.print(F("> "));
}

void handleCommand(String cmd) {
  cmd.trim();
  if (cmd.length() == 0) { Serial.print(F("> ")); return; }

  if (cmd.equalsIgnoreCase("help") || cmd == "?") {
    printHelp();
    return;
  }

  if (cmd.startsWith("c")) {
    // cutter servo absolute position, 0-240 degrees
    String arg = cmd.substring(1);
    arg.trim();
    char *end;
    long pos = strtol(arg.c_str(), &end, 10);
    if (end == arg.c_str()) {
      Serial.println(F("? expected an angle 0-240, e.g. 'c 90'"));
      Serial.print(F("> "));
      return;
    }
    pos = constrain(pos, 0, 240);
    cutter.write(pos);
    Serial.print(F("cutter -> "));
    Serial.print(pos);
    Serial.println(F(" deg"));
    Serial.print(F("> "));
    return;
  }

  if (cmd.startsWith("j")) {
    // jumper: feed a 0.25" leg, strip, feed the body (len positions at
    // 0.1" pitch), strip, feed another 0.25" leg, then sever
    String arg = cmd.substring(1);
    arg.trim();
    char *end;
    long len = strtol(arg.c_str(), &end, 10);
    if (end == arg.c_str()) {
      Serial.println(F("? expected an integer length, e.g. 'j 10'"));
      Serial.print(F("> "));
      return;
    }
    float legMm  = 0.25f * 25.4f;         // 0.25" leg at each end
    float bodyMm = len * 0.1f * 25.4f;    // len positions at 0.1" pitch

    Serial.print(F("jumper: "));
    Serial.print(len);
    Serial.println(F(" positions"));

    enableMotor();        // hold the driver enabled for the whole sequence
    /*
    move(legMm,true);    // first leg
    cut(stripPos);        // strip near end
    move(bodyMm,true);   // jumper body
    cut(stripPos);        // strip far end
    move(legMm,true);    // second leg
    cut(cutPos);          // sever the finished jumper
    */
    move(legMm*2,true);    // first leg
    strip(legMm*2);
    move(1,true);
    cut(cutPos);
    move(legMm*2+bodyMm-1,true);   // jumper body
    strip(legMm);
    move(legMm,true);    // second leg
    cut(cutPos);          // sever the finished jumper

    disableMotor();

    Serial.println(F("jumper done (motor disabled)"));
    Serial.print(F("> "));
    return;
  }

  float mm;

  if (cmd.startsWith("mm") || cmd.startsWith("in")) {
    // distance in millimetres ("mm") or inches ("in"); sign selects direction
    float scale = cmd.startsWith("in") ? 25.4f : 1.0f;
    String arg = cmd.substring(2);
    arg.trim();
    char *end;
    float value = strtof(arg.c_str(), &end);
    if (end == arg.c_str()) {
      Serial.println(F("? expected a distance, e.g. 'mm 50' or 'in 2'"));
      Serial.print(F("> "));
      return;
    }
    mm = value * scale;
  } else {
    Serial.print(F("? unknown command: "));
    Serial.println(cmd);
    Serial.print(F("> "));
    return;
  }

  bool forward = mm >= 0;
  float dist = fabsf(mm);

  Serial.print(F("moving "));
  Serial.print(dist);
  Serial.print(F(" mm "));
  Serial.println(forward ? F("forward") : F("backward"));

  enableMotor();
  move(dist, forward);
  disableMotor();

  Serial.println(F("done (motor disabled)"));
  Serial.print(F("> "));
}

void setup() {
  pinMode(enPin,OUTPUT);
  pinMode(stepPin,OUTPUT);
  pinMode(dirPin,OUTPUT);

  digitalWrite(enPin,HIGH);             // start with the driver disabled

	ESP32PWM::allocateTimer(0);
	ESP32PWM::allocateTimer(1);
	ESP32PWM::allocateTimer(2);
	ESP32PWM::allocateTimer(3);
	cutter.setPeriodHertz(50);    // standard 50 hz servo
	cutter.attach(D5, 500, 2600); // attaches the servo on pin 18 to the servo object
	cutter.write(openPos);        // start with the blade retracted

  Serial.begin(115200);
  delay(500);                           // give the USB serial port time to come up
  printHelp();
}

void loop() {
  while (Serial.available()) {
    char c = Serial.read();
    if (c == '\n' || c == '\r') {
      if (cmdBuffer.length() > 0) {
        handleCommand(cmdBuffer);
        cmdBuffer = "";
      }
    } else {
      cmdBuffer += c;
    }
  }
}
