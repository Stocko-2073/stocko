#pragma once
#include "motion_profile.h"

struct DemoEvent { uint32_t interval; int8_t dx, dy; };
constexpr size_t demoCapacity = 20000;
constexpr int demoSide = 2000; // 20 mm at commissioned scale.
constexpr int demoRadius = demoSide / 2;
constexpr int demoRepeats = 3;
constexpr double demoRate = 2000, demoAccel = 10000;
// Preserve the accepted circle ramp. At the larger radius, radial acceleration
// is lower: 4000 pulses/sec^2 at r=1000 and v=2000.
constexpr double demoCircleAccel = 6000;

// One cycle, replayed three times. Line segments use simultaneous X/Y pulses;
// the circle is a continuous 360-segment polygon, with one acceleration profile
// over the entire circumference (no stop at each segment).
inline size_t buildDemo(DemoEvent *events) {
  size_t count = 0;
  int x = 0, y = 0;
  bool valid = true;
  auto segment = [&](int tx, int ty, double &distance, double total, double &previousTime, double accel) {
    const int dx = tx-x, dy = ty-y;
    const int nx = std::abs(dx), ny = std::abs(dy);
    const int n = nx > ny ? nx : ny;
    const double length = std::hypot(dx, dy);
    const int sx = x, sy = y;
    for (int i = 1; i <= n; ++i) {
      const int px = sx + int(std::lround(double(dx)*i/n));
      const int py = sy + int(std::lround(double(dy)*i/n));
      const double pos = std::fmin(total, distance + length*i/n);
      const double t = profileTime(pos, total, demoRate, accel);
      if (count >= demoCapacity || px < 0 || px > demoSide || py < 0 || py > demoSide) {
        valid = false; return;
      }
      events[count++] = {uint32_t(std::ceil((t-previousTime)*1000000.0)),
                         int8_t(px-x), int8_t(py-y)};
      previousTime = t; x = px; y = py;
    }
    distance += length;
  };
  auto lineTo = [&](int tx, int ty) {
    double distance = 0, time = 0;
    segment(tx, ty, distance, std::hypot(tx-x, ty-y), time, demoAccel);
  };
  lineTo(demoSide, 0); lineTo(demoSide, demoSide); lineTo(0, demoSide); lineTo(0, 0);
  lineTo(demoRadius, 0); // Circle starts at the bottom of the same envelope.
  constexpr int segments = 360;
  int cx[segments+1], cy[segments+1];
  double total = 0;
  for (int i = 0; i <= segments; ++i) {
    const double angle = -1.5707963267948966 + i*6.283185307179586/segments;
    cx[i] = demoRadius + int(std::lround(demoRadius*std::cos(angle)));
    cy[i] = demoRadius + int(std::lround(demoRadius*std::sin(angle)));
    if (i) total += std::hypot(cx[i]-cx[i-1], cy[i]-cy[i-1]);
  }
  double distance = 0, time = 0;
  for (int i = 1; i <= segments; ++i) segment(cx[i], cy[i], distance, total, time, demoCircleAccel);
  lineTo(0, 0);
  return valid && x == 0 && y == 0 ? count : 0;
}
