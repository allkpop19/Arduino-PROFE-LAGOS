#pragma once
class Servo {
public:
  int pin = -1;
  int angle = -1;
  void attach(int value) { pin = value; }
  void write(int value) { angle = value; }
};
