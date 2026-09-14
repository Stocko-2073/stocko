#pragma once
#include <string>
struct FakeMDNS {
  bool running = false, fail = false;
  std::string hostname;
  bool begin(const char *s) { hostname = s; running = !fail; return running; }
  void end() { running = false; }
} inline MDNS;
