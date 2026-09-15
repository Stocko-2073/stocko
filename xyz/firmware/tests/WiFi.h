#pragma once
#include <string>
constexpr int WIFI_STA = 1, WL_CONNECTED = 3;
struct FakeIP { std::string toString() { return "192.0.2.1"; } };
struct FakeWiFi {
  int state = 0, attempts = 0;
  std::string hostname, ssid, password;
  void persistent(bool) {}
  void setHostname(const char *s) { hostname = s; }
  void mode(int) {}
  void setAutoReconnect(bool) {}
  bool sleep=true; void setSleep(bool on) { sleep=on; }
  void begin(const char *s, const char *p) { ssid = s; password = p; ++attempts; }
  void disconnect(bool, bool) { state = 0; }
  void reconnect() { ++attempts; }
  int status() { return state; }
  FakeIP localIP() { return {}; }
} inline WiFi;
