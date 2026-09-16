#pragma once
#include <Preferences.h>
#include <cstddef>
#include "config.h"

namespace CutSettings {
struct Record {
  uint32_t version=2, depth=100, rpm=60, feed=200; // Pulses, RPM, pulses/s.
  uint32_t accel=75; // RPM/s; same 1000 pulses/s² as the previous firmware.
};
Preferences preferences;
Record saved;
bool ready=false, stored=false;
bool valid(const Record &r) {
  return r.version==2 && r.depth>=10 && r.depth<=1000 && r.depth%10==0 &&
    r.rpm>=1 && r.rpm<=240 && r.feed>=10 && r.feed<=uint32_t(Config::maxRate[3]) && r.feed%10==0 &&
    r.accel>=Config::cutMinAccelRpm && r.accel<=Config::cutMaxAccelRpm;
}
void begin() {
  saved={}; stored=false;
  ready=preferences.begin("xyz-cut",false);
  Record loaded;
  const size_t size=ready ? preferences.getBytesLength("settings"):0;
  const bool legacy=size==offsetof(Record,accel);
  if ((!legacy && size!=sizeof(loaded)) || !ready ||
      preferences.getBytes("settings",&loaded,size)!=size) return;
  if (legacy) {
    if (loaded.version!=1) return;
    loaded.version=2; // Keep the old values; add the previous fixed acceleration.
  }
  if (valid(loaded)) { saved=loaded; stored=!legacy; }
}
bool save(const Record &next) {
  if (!ready || !valid(next)) return false;
  if (stored && saved.depth==next.depth && saved.rpm==next.rpm && saved.feed==next.feed && saved.accel==next.accel) return true;
  if (preferences.putBytes("settings",&next,sizeof(next))!=sizeof(next)) return false;
  saved=next; stored=true; return true;
}
}
