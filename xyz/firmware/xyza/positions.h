#pragma once
#include <cstddef>

// Pulse coordinates use the commissioned motor directions. A is a spindle,
// so presets only contain XYZ (M0, M1, M3).
namespace Positions {
struct Record {
  uint32_t version = 2;
  bool homeSet = false, replaceSet = false, clean = false;
  int64_t home[4] = {}, replace[4] = {}, checkpoint[4] = {};
  // Version 2: where hole Z34 was found, as an XY offset from A1. Boards are
  // not exactly on a 2.54 mm pitch at the provisional 100 pulses/mm, so the
  // grid is interpolated between the two corners. An offset, not a raw
  // position: it describes the board and machine scale, so moving A1 keeps it.
  bool spanSet = false;
  int64_t span[2] = {};
};
// A version 1 record is this struct without the span fields.
constexpr size_t legacySize = offsetof(Record, spanSet);
static_assert(legacySize == 104, "version 1 record layout");
Record saved;
Preferences preferences;
bool ready = false, known = false;

bool commissioned() {
  for (int i = 0; i < 4; ++i)
    if (axisMotor[i] != Config::axisMotor[i] || inverted[i] != Config::inverted[i]) return false;
  return true;
}
void snapshot(int64_t *p) {
  portENTER_CRITICAL(&motionMux);
  for (int i = 0; i < 4; ++i) p[i] = emitted[i];
  portEXIT_CRITICAL(&motionMux);
}
bool write(const Record &next) {
  if (!ready || preferences.putBytes("positions", &next, sizeof(next)) != sizeof(next)) return false;
  saved = next;
  return true;
}
void begin() {
  saved = {}; known = false;
  ready = preferences.begin("xyz-position", false);
  Record loaded;
  const size_t length = ready ? preferences.getBytesLength("positions") : 0;
  bool valid = false;
  if (length == sizeof(loaded)) {
    valid = preferences.getBytes("positions", &loaded, sizeof(loaded)) == sizeof(loaded) && loaded.version == 2;
  } else if (length == legacySize) {
    // Upgrade in RAM only; the next write stores version 2. Nothing moves.
    valid = preferences.getBytes("positions", &loaded, legacySize) == legacySize && loaded.version == 1;
    loaded.version = 2; loaded.spanSet = false; loaded.span[0] = loaded.span[1] = 0;
  }
  if (valid) {
    saved = loaded;
    if (saved.clean) for (int i = 0; i < 4; ++i) emitted[i] = saved.checkpoint[i];
  }
}
// Commit the dirty marker before enabling the timer. A reset midway through
// a move must never restore an obsolete checkpoint as a recoverable position.
bool beforeMove() {
  if (!saved.homeSet) return true;
  Record next = saved; next.clean = false;
  return write(next);
}
void settled(bool interrupted) {
  if (interrupted) known = false;
  if (!saved.homeSet) return;
  Record next = saved;
  snapshot(next.checkpoint);
  next.clean = known && commissioned();
  if (!write(next)) { known = false; Serial.println("ERR saving position checkpoint"); }
}
bool save(bool home) {
  if (!commissioned() || (!home && (!known || !saved.homeSet))) return false;
  Record next = saved;
  snapshot(next.checkpoint);
  if (home) {
    // With no reference, old replacement coordinates cannot be related to the
    // new origin. Re-referencing the existing home preserves them instead.
    if (!known) next.replaceSet = false;
    snapshot(next.home); next.homeSet = true;
  } else { snapshot(next.replace); next.replaceSet = true; }
  next.clean = true;
  if (!write(next)) return false;
  known = true; return true;
}
// The drill is above Z34: record its XY offset from A1. The caller checks
// the offset is plausible before asking.
bool saveSpan(int64_t x, int64_t y) {
  if (!known || !saved.homeSet || !commissioned()) return false;
  Record next = saved;
  snapshot(next.checkpoint);
  next.span[0] = x; next.span[1] = y; next.spanSet = true;
  next.clean = true;
  return write(next);
}
bool reference(bool atHome) {
  if (!saved.homeSet || !commissioned() || (!atHome && !saved.clean)) return false;
  Record next = saved;
  if (atHome) for (int i = 0; i < 4; ++i) next.checkpoint[i] = next.home[i];
  next.clean = true;
  if (!write(next)) return false;
  for (int i = 0; i < 4; ++i) emitted[i] = saved.checkpoint[i];
  known = true; return true;
}
}
