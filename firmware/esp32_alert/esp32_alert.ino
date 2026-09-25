/*
 * Lazy Lobsters — Fall-Detection physical alert unit
 * Board: ESP32 DevKit v1 (WROOM, 30-pin, micro-USB)
 *
 * The laptop's Python detector (src/run.py -> src/alerter.py) sends one short
 * command line over USB serial whenever the situation changes, plus a heartbeat
 * roughly once a second. This sketch maps each command to the LEDs + buzzer.
 *
 * Protocol (newline-terminated ASCII, 115200 baud):
 *   OK      normal / monitoring  -> BLUE solid,        buzzer off
 *   WARN    fallen / lying down  -> RED slow blink,    buzzer off   (heads-up)
 *   ALERT   FALL / DISTRESS      -> RED fast blink,    buzzer on    (emergency)
 *   ABSENT  no person in frame   -> BLUE slow blink,   buzzer off
 *
 * Safety watchdog: if no line arrives for LINK_TIMEOUT_MS (laptop crashed,
 * cable pulled, Python not running) the unit drops to a BLUE fast-blink
 * "link lost" state and silences the buzzer — it can never get stuck blaring.
 */

// ---- Wiring (GPIO -> component). All safe output pins on the 30-pin DevKit. ----
// NOTE: pins 34/35/36/39 are INPUT-ONLY on the ESP32 and cannot drive an output.
// These three (D19/D18/D21) are adjacent, output-capable, and avoid the UART pins.
const int PIN_RED    = 22;   // D22 -> [220-330 ohm resistor] -> RED LED  -> GND
const int PIN_BLUE   = 18;   // D18 -> [220-330 ohm resistor] -> BLUE LED -> GND
const int PIN_BUZZER = 25;   // D25 -> buzzer (+).  buzzer (-) -> GND

// ---- Buzzer type --------------------------------------------------------------
// true  = PASSIVE piezo (a bare disc / open PCB; needs a tone signal to sound)
// false = ACTIVE  piezo (sealed case with a sticker; sounds on plain DC)
// If you're unsure: leave true. A passive buzzer driven this way still works;
// an active buzzer driven this way may sound weak/odd -> then set this false.
const bool BUZZER_PASSIVE = true;
const int  BUZZER_FREQ    = 2300;   // Hz, only used for a passive buzzer

// ---- Timing -------------------------------------------------------------------
const unsigned long LINK_TIMEOUT_MS = 3000;  // no message this long -> link lost
const unsigned long SLOW_BLINK_MS   = 500;
const unsigned long FAST_BLINK_MS   = 150;

enum Mode { MODE_OK, MODE_WARN, MODE_ALERT, MODE_ABSENT, MODE_LINK_LOST };
Mode mode = MODE_LINK_LOST;            // start "link lost" until the laptop speaks
unsigned long lastRxMs = 0;
String line;

void buzzerOn() {
  if (BUZZER_PASSIVE) tone(PIN_BUZZER, BUZZER_FREQ);
  else                digitalWrite(PIN_BUZZER, HIGH);
}
void buzzerOff() {
  if (BUZZER_PASSIVE) noTone(PIN_BUZZER);
  else                digitalWrite(PIN_BUZZER, LOW);
}

void setup() {
  pinMode(PIN_RED, OUTPUT);
  pinMode(PIN_BLUE, OUTPUT);
  pinMode(PIN_BUZZER, OUTPUT);
  buzzerOff();
  Serial.begin(115200);
  lastRxMs = millis();
  // brief self-test so you can confirm wiring on power-up
  digitalWrite(PIN_BLUE, HIGH); delay(200); digitalWrite(PIN_BLUE, LOW);
  digitalWrite(PIN_RED, HIGH);  delay(200); digitalWrite(PIN_RED, LOW);
  Serial.println("READY");
}

void applyMode() {
  unsigned long t = millis();
  bool slow = ((t / SLOW_BLINK_MS) % 2) == 0;
  bool fast = ((t / FAST_BLINK_MS) % 2) == 0;
  switch (mode) {
    case MODE_OK:
      digitalWrite(PIN_BLUE, HIGH); digitalWrite(PIN_RED, LOW);  buzzerOff(); break;
    case MODE_WARN:
      digitalWrite(PIN_BLUE, LOW);  digitalWrite(PIN_RED, slow); buzzerOff(); break;
    case MODE_ALERT:
      digitalWrite(PIN_BLUE, LOW);  digitalWrite(PIN_RED, fast);
      if (fast) buzzerOn(); else buzzerOff();          // pulsing beep
      break;
    case MODE_ABSENT:
      digitalWrite(PIN_BLUE, slow); digitalWrite(PIN_RED, LOW);  buzzerOff(); break;
    case MODE_LINK_LOST:
      digitalWrite(PIN_BLUE, fast); digitalWrite(PIN_RED, LOW);  buzzerOff(); break;
  }
}

void handle(String cmd) {
  cmd.trim();
  if      (cmd == "OK")     mode = MODE_OK;
  else if (cmd == "WARN")   mode = MODE_WARN;
  else if (cmd == "ALERT")  mode = MODE_ALERT;
  else if (cmd == "ABSENT") mode = MODE_ABSENT;
  // unknown commands are ignored on purpose
  lastRxMs = millis();
}

void loop() {
  while (Serial.available()) {
    char c = (char)Serial.read();
    if (c == '\n') { handle(line); line = ""; }
    else if (c != '\r') line += c;
  }
  if (millis() - lastRxMs > LINK_TIMEOUT_MS) mode = MODE_LINK_LOST;
  applyMode();
}
