#pragma once

// Pulse coordinates use the commissioned motor directions. A is a spindle,
// so presets only contain XYZ (M0, M1, M3).
namespace Positions {
struct Record {
  uint32_t version = 1;
  bool homeSet = false, replaceSet = false, clean = false;
  int64_t home[4] = {}, replace[4] = {}, checkpoint[4] = {};
};
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
  if (ready && preferences.getBytesLength("positions") == sizeof(loaded) &&
      preferences.getBytes("positions", &loaded, sizeof(loaded)) == sizeof(loaded) && loaded.version == 1) {
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
