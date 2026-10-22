#include "Arduino.h"
#include <cassert>
#include <iostream>
unsigned long clockMs = 0;
unsigned long echoDuration = 0;
SerialStub Serial;
#include "../../arduino/casa/casa.ino"

void sample(unsigned long duration, int count) {
  echoDuration = duration;
  for (int i = 0; i < count; ++i) {
    clockMs += 80;
    loop();
  }
}
void command(const char *id) {
  Serial.feed(std::string("OPEN ") + id + "\n");
  loop();
}

int main() {
  setup();
  assert(door.pin == 7 && door.angle == 0);
  sample(875, 3); // 15 cm ya no debe activar el panel.
  assert(!personPresent && !doorOpened);
  sample(600, 3); // 10,29 cm: fuera del rango, sin truncar a 10.
  assert(!personPresent);
  sample(580, 2); // 9,95 cm: dentro del rango.
  assert(personPresent && !doorOpened && door.angle == 0);
  sample(640, 3); // 10,98 cm: conserva presencia por histéresis.
  assert(personPresent);
  sample(710, 3); // 12,17 cm: libera presencia.
  assert(!personPresent);
  sample(292, 2); // Aproximadamente 5 cm.
  Serial.feed("OPEN basura\n"); loop();
  assert(!doorOpened);
  command("0123456789abcdef");
  assert(doorOpened && door.angle == 90 && needsClear);
  auto start = openedAt;
  command("0123456789abcdef"); // Duplicado no prolonga el tiempo.
  assert(openedAt == start);
  clockMs = start + 4999; loop();
  assert(doorOpened && door.angle == 90);
  clockMs = start + 5000; loop(); // Cierra sin órdenes del PC.
  assert(!doorOpened && door.angle == 0 && needsClear);
  command("1111111111111111");
  assert(!doorOpened); // Sigue presente: requiere alejarse.
  sample(0, 3); // Tres lecturas sin eco retiran presencia.
  assert(!personPresent && !needsClear);
  command("2222222222222222");
  assert(!doorOpened); // No abrir sin presencia.
  sample(292, 2);
  command("3333333333333333");
  assert(doorOpened);
  start = openedAt;
  sample(5800, 3); // La persona se aleja durante la apertura.
  assert(!personPresent && doorOpened && needsClear);
  clockMs = start + 5000; loop();
  assert(!doorOpened && door.angle == 0);
  // Una línea enorme no puede convertirse en una orden OPEN válida.
  sample(292, 2);
  Serial.feed(std::string(100, 'x') + "OPEN 4444444444444444\n");
  loop(); loop(); loop();
  assert(!doorOpened);
  assert(Serial.output.str().find("\"accepted\":true") != std::string::npos);
  assert(Serial.output.str().find("\"accepted\":false") != std::string::npos);
  std::cout << "Firmware OK: deteccion, autorizacion, rechazo, cierre 5s, rearme y entrada malformada\n";
}
