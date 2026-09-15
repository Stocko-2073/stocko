#pragma once
#include <functional>
#include <map>
#include <string>
#define PROGMEM
constexpr int HTTP_GET=0, HTTP_POST=1;
enum HTTPClientStatus { HC_NONE, HC_WAIT_READ, HC_WAIT_CLOSE };
struct NetworkClient { int avail=0; bool stopped=false; int available() { return avail; } void stop() { stopped=true; } };
struct WebServer {
  NetworkClient _currentClient; HTTPClientStatus _currentStatus=HC_NONE; unsigned long _statusChange=0;
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
