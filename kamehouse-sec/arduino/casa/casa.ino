#include <Servo.h>
#include <string.h>

void report(const char *requestId = NULL, bool accepted = false);

// Solo casa: no se utiliza el sistema del peaje.
const byte TRIG_PIN = 5;
const byte ECHO_PIN = 6;
const byte SERVO_PIN = 7;
const float DETECT_DISTANCE_CM = 10.0;
const float CLEAR_DISTANCE_CM = 12.0;
const unsigned long OPEN_TIME = 5000;
const unsigned long SAMPLE_TIME = 80;

// Cambia a true SOLO para comprobar si el servo se mueve al arrancar.
// Después de la prueba, vuelve a false y carga el programa nuevamente.
const bool PRUEBA_SERVO = false;

Servo door;
bool personPresent = false;
bool doorOpened = false;
bool needsClear = false;
byte nearSamples = 0;
byte farSamples = 0;
float distanceCm = -1;
unsigned long openedAt = 0;
unsigned long lastSample = 0;
unsigned long lastReport = 0;
char inputBuffer[64];
byte inputLength = 0;
bool inputOverflow = false;

void report(const char *requestId, bool accepted) {
  unsigned long remaining = 0;
  unsigned long elapsed = millis() - openedAt;
  if (doorOpened && elapsed < OPEN_TIME) remaining = OPEN_TIME - elapsed;
  Serial.print(F("{\"protocol\":\"casa-v1\",\"present\":"));
  Serial.print(personPresent ? F("true") : F("false"));
  Serial.print(F(",\"opened\":"));
  Serial.print(doorOpened ? F("true") : F("false"));
  Serial.print(F(",\"needs_clear\":"));
  Serial.print(needsClear ? F("true") : F("false"));
  Serial.print(F(",\"remaining_ms\":"));
  Serial.print(remaining);
  Serial.print(F(",\"distance_cm\":"));
  if (distanceCm < 0) Serial.print(F("null"));
  else Serial.print(distanceCm);
  if (requestId != NULL) {
    Serial.print(F(",\"request_id\":\""));
    Serial.print(requestId);
    Serial.print(F("\",\"accepted\":"));
    Serial.print(accepted ? F("true") : F("false"));
  }
  Serial.println(F("}"));
  lastReport = millis();
}

void closeIfDue() {
  if (doorOpened && millis() - openedAt >= OPEN_TIME) {
    door.write(0);
    doorOpened = false;
    report();
  }
}

void handleCommand() {
  // Solo se aceptan identificadores hexadecimales de longitud fija.
  if (strncmp(inputBuffer, "OPEN ", 5) != 0 || inputLength != 21) return;
  const char *id = inputBuffer + 5;
  for (byte i = 0; i < 16; ++i) {
    if (!((id[i] >= '0' && id[i] <= '9') || (id[i] >= 'a' && id[i] <= 'f'))) return;
  }
  bool allowed = personPresent && !doorOpened && !needsClear;
  if (allowed) {
    door.write(90);
    doorOpened = true;
    needsClear = true;
    openedAt = millis();
  }
  report(id, allowed);
}

void readCommands() {
  // Limitar bytes por vuelta para no interrumpir el cierre automático.
  for (byte count = 0; count < 64 && Serial.available(); ++count) {
    char c = Serial.read();
    if (c == '\n') {
      inputBuffer[inputLength] = '\0';
      if (!inputOverflow) handleCommand();
      inputLength = 0;
      inputOverflow = false;
    } else if (c != '\r') {
      if (inputLength < sizeof(inputBuffer) - 1) inputBuffer[inputLength++] = c;
      else inputOverflow = true;
    }
  }
}

void measure() {
  digitalWrite(TRIG_PIN, LOW);
  delayMicroseconds(2);
  digitalWrite(TRIG_PIN, HIGH);
  delayMicroseconds(10);
  digitalWrite(TRIG_PIN, LOW);
  unsigned long duration = pulseIn(ECHO_PIN, HIGH, 25000UL);
  distanceCm = duration ? duration * 0.0343 / 2.0 : -1;

  // Dos lecturas cercanas para detectar; tres lejanas para retirar presencia.
  // Detecta a 10 cm o menos; libera desde 12 cm para evitar parpadeos.
  if (distanceCm >= 2 && distanceCm <= DETECT_DISTANCE_CM) {
    if (nearSamples < 2) ++nearSamples;
    farSamples = 0;
    if (nearSamples >= 2) personPresent = true;
  } else if (distanceCm < 0 || distanceCm < 2 || distanceCm >= CLEAR_DISTANCE_CM) {
    nearSamples = 0;
    if (farSamples < 3) ++farSamples;
    if (farSamples >= 3) personPresent = false;
  } else {
    nearSamples = 0;
    farSamples = 0;
  }
  if (!personPresent && !doorOpened) needsClear = false;
}

void setup() {
  Serial.begin(115200);
  pinMode(TRIG_PIN, OUTPUT);
  pinMode(ECHO_PIN, INPUT);
  digitalWrite(TRIG_PIN, LOW);
  door.attach(SERVO_PIN);
  door.write(0);

  if (PRUEBA_SERVO) {
    delay(500);
    door.write(90);
    delay(1000);
    door.write(0);
    delay(500);
  }

  report();
}

void loop() {
  closeIfDue();
  if (millis() - lastSample >= SAMPLE_TIME) {
    lastSample = millis();
    measure();
  }
  closeIfDue();
  readCommands();
  if (millis() - lastReport >= 200) report();
}
