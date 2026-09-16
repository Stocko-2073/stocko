#pragma once
#include <vector>
#include <cstring>
struct Preferences {
  std::vector<unsigned char> blob;
  bool failWrite = false;
  int writes=0;
  bool begin(const char *, bool) { return true; }
  size_t getBytesLength(const char *) { return blob.size(); }
  size_t getBytes(const char *, void *p, size_t n) {
    if (n != blob.size()) return 0;
    memcpy(p, blob.data(), n); return n;
  }
  size_t putBytes(const char *, const void *p, size_t n) {
    ++writes;
    if (failWrite) return 0;
    const auto *bytes = static_cast<const unsigned char *>(p);
    blob.assign(bytes, bytes + n); return n;
  }
  bool isKey(const char *) { return !blob.empty(); }
  bool remove(const char *) { blob.clear(); return true; }
};
