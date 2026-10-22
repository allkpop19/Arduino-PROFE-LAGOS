#pragma once
#include <cstdint>
#include <cstring>
#include <deque>
#include <sstream>
#include <string>
using byte = uint8_t;
#define F(value) value
const int LOW = 0, HIGH = 1, OUTPUT = 1, INPUT = 0;
extern unsigned long clockMs;
extern unsigned long echoDuration;
inline unsigned long millis() { return clockMs; }
inline void delay(unsigned long ms) { clockMs += ms; }
inline void pinMode(int, int) {}
inline void digitalWrite(int, int) {}
inline void delayMicroseconds(int) {}
inline unsigned long pulseIn(int, int, unsigned long) { return echoDuration; }
struct SerialStub {
  std::ostringstream output;
  std::deque<char> input;
  void begin(int) {}
  int available() { return input.size(); }
  char read() { char c = input.front(); input.pop_front(); return c; }
  template<class T> void print(T value) { output << value; }
  template<class T> void println(T value) { output << value << '\n'; }
  void feed(const std::string &s) { for (char c : s) input.push_back(c); }
};
extern SerialStub Serial;
