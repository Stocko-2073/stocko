#pragma once
#include <functional>
#include <map>
#include <string>
#define PROGMEM
constexpr int HTTP_GET=0, HTTP_POST=1;
struct WebServer {
  std::map<std::string,std::function<void()>> routes;
  std::map<std::string,std::string> args, headers;
  int code=0; std::string body;
  explicit WebServer(int) {}
  void collectHeaders(const char **, size_t) {}
  void on(const char *path, int, std::function<void()> fn) { routes[path]=fn; }
  void onNotFound(std::function<void()>) {}
  void begin() {}
  void handleClient() {}
  std::string arg(const char *key) { return args[key]; }
  std::string header(const char *key) { return headers[key]; }
  void sendHeader(const char *, const char *) {}
  void send(int c, const char *, const char *b) { code=c;body=b; }
  void send_P(int c, const char *t, const char *b) { send(c,t,b); }
};
