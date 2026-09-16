#pragma once
#include <cstdint>
#include <cstddef>
#include <cstdarg>
#include <cstdio>
#include <string>
#include <deque>
#include <algorithm>
#include <vector>
using std::min;
#define ARDUINO_ISR_ATTR
using portMUX_TYPE = int;
#define portMUX_INITIALIZER_UNLOCKED 0
inline void portENTER_CRITICAL(portMUX_TYPE *) {}
inline void portEXIT_CRITICAL(portMUX_TYPE *) {}
inline void portENTER_CRITICAL_ISR(portMUX_TYPE *) {}
inline void portEXIT_CRITICAL_ISR(portMUX_TYPE *) {}
constexpr uint8_t D0=0, D1=1, D2=2, D3=21, D4=22, D5=23, D8=19, D9=20, D10=18;
constexpr int HIGH=1, LOW=0, OUTPUT=1;
inline uint32_t clockUs=0;
inline int levels[24]={};
inline int rises[24]={};
inline std::vector<uint32_t> riseTimes[24];
inline void digitalWrite(int p, int value) {
  if (value && !levels[p]) { ++rises[p]; riseTimes[p].push_back(clockUs); }
  levels[p]=value;
}
inline void pinMode(int, int) {}
inline uint32_t micros() { return clockUs; }
inline uint32_t millis() { return clockUs / 1000; }
inline uint64_t simulatedUs = 0;
struct hw_timer_t {
  bool running=false, alarmEnabled=false;
  uint64_t base=0, started=0, alarm=0;
  void (*callback)()=nullptr;
} inline fakeTimer;
inline hw_timer_t *timerBegin(uint32_t) { fakeTimer = {}; return &fakeTimer; }
inline uint64_t timerRead(hw_timer_t *t) { return t->base + (t->running ? simulatedUs-t->started : 0); }
inline void timerStop(hw_timer_t *t) { t->base=timerRead(t); t->running=false; }
inline void timerStart(hw_timer_t *t) { t->started=simulatedUs; t->running=true; }
inline void timerWrite(hw_timer_t *t, uint64_t v) { t->base=v; t->started=simulatedUs; }
inline void timerAttachInterrupt(hw_timer_t *t, void (*f)()) { t->callback=f; }
inline void timerAlarm(hw_timer_t *t, uint64_t value, bool repeat, uint64_t) {
  if (repeat) std::abort(); // Firmware uses one-shot alarms only.
  t->alarm=value; t->alarmEnabled=true;
}
inline void advanceRaw(uint64_t n) { simulatedUs += n; clockUs += uint32_t(n); }
inline void delayMicroseconds(uint32_t n) {
  const uint64_t target=simulatedUs+n;
  while (fakeTimer.running && fakeTimer.alarmEnabled) {
    const uint64_t now=timerRead(&fakeTimer);
    const uint64_t wait=fakeTimer.alarm > now ? fakeTimer.alarm-now : 0;
    if (simulatedUs+wait > target) break;
    advanceRaw(wait);
    fakeTimer.alarmEnabled=false;
    fakeTimer.callback();
  }
  if (simulatedUs < target) advanceRaw(target-simulatedUs);
}
inline void delay(uint32_t n) { delayMicroseconds(n*1000); }
struct FakeSerial {
  bool connected=true;
  // Negative capacity means a host that continuously drains output. A finite
  // capacity models a connected host that leaves its USB output unread.
  int txFree=-1, blockedWrites=0;
  std::deque<char> input;
  std::string output;
  explicit operator bool() const { return connected; }
  void begin(int) {}
  int availableForWrite() { return txFree < 0 ? 4096 : txFree; }
  int available() { return input.size(); }
  char read() { char c=input.front(); input.pop_front(); return c; }
  void println(const char *s) {
    const int bytes=std::string(s).size()+2;
    if (txFree >= 0) {
      if (txFree < bytes) {
        ++blockedWrites;
        delay(2000); // Installed HWCDC retries a full ring 20 times at 100 ms.
        return;
      }
      txFree-=bytes;
    }
    output += std::string(s) + "\n";
  }
  void printf(const char *fmt, ...) {
    char buffer[256]; va_list args; va_start(args, fmt);
    vsnprintf(buffer, sizeof(buffer), fmt, args); va_end(args); output += buffer;
  }
} inline Serial;
