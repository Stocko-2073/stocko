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

// A long preset needs only its acceleration ramp in RAM. The cruise interval
// repeats, and deceleration mirrors acceleration. No refills or floating-point
// work are needed in the step interrupt, regardless of travel distance.
struct PresetProfile {
  static constexpr uint32_t capacity = 1024; // 4,000 pulses/sec at 10,000 pulses/sec^2 ramps over 800.
  uint32_t ramp[capacity] = {}, count = 0, rampCount = 0, cruise = 0;

  bool build(uint32_t pulses, long rate, long accel) {
    if (!pulses || rate <= 0 || accel <= 0) return false;
    const double distance = pulses;
    const double rampDistance = std::fmin(distance/2.0, double(rate)*rate/(2.0*accel));
    const uint32_t needed = uint32_t(std::ceil(rampDistance));
    if (needed > capacity) return false;
    count = pulses; rampCount = needed;
    cruise = uint32_t(std::ceil(1000000.0/rate));
    double previous = 0;
    for (uint32_t i = 0; i < rampCount; ++i) {
      const double next = profileTime(i+1, distance, rate, accel);
      ramp[i] = uint32_t(std::ceil((next-previous)*1000000.0));
      previous = next;
    }
    return true;
  }
  uint32_t interval(uint32_t index) const {
    if (index < rampCount) return ramp[index];
    const uint32_t fromEnd = count-1-index;
    return fromEnd < rampCount ? ramp[fromEnd] : cruise;
  }
};
