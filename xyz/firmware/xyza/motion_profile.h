#pragma once
#include <cmath>
#include <cstdint>

// Time at position x for a symmetric rest-to-rest trapezoid (triangle when
// the move is too short to reach requested speed). Units: pulses and seconds.
inline double profileTime(double x, double distance, double rate, double accel) {
  const double ramp = std::fmin(distance / 2.0, rate * rate / (2.0 * accel));
  const double peak = std::sqrt(2.0 * accel * ramp);
  const double rampTime = peak / accel;
  if (x <= ramp) return std::sqrt(2.0 * x / accel);
  if (x < distance - ramp) return rampTime + (x - ramp) / peak;
  const double total = 2.0 * rampTime + (distance - 2.0 * ramp) / peak;
  return total - std::sqrt(2.0 * (distance - x) / accel);
}

inline void buildProfile(uint32_t *intervals, long count, long rate, long accel) {
  double previous = 0;
  for (long i = 0; i < count; ++i) {
    const double next = profileTime(i + 1, count, rate, accel);
    intervals[i] = uint32_t(std::ceil((next - previous) * 1000000.0));
    previous = next;
  }
}
