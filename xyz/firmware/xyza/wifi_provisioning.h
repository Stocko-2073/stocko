#pragma once
#include <WiFi.h>
#include <ESPmDNS.h>
#include <Preferences.h>

namespace WifiProvisioning {
struct Credentials { char ssid[33]; char password[65]; };
Credentials saved = {}, pending = {};
Preferences preferences;
bool storageReady = false, mdns = false, connected = false;
uint8_t prompt = 0; // 1 = SSID, 2 = password; motors are disabled throughout.
uint32_t lastAttempt = 0, lastMdnsAttempt = 0;

bool valid(const Credentials &c) {
  if (!c.ssid[0] || !memchr(c.ssid, 0, sizeof(c.ssid)) ||
      !memchr(c.password, 0, sizeof(c.password))) return false;
  const size_t n = strlen(c.password);
  if (n == 64) {
    for (size_t i = 0; i < n; ++i)
      if (!((c.password[i] >= '0' && c.password[i] <= '9') ||
            (c.password[i] >= 'a' && c.password[i] <= 'f') ||
            (c.password[i] >= 'A' && c.password[i] <= 'F'))) return false;
    return true;
  }
  return n == 0 || (n >= 8 && n <= 63);
}
void stop() {
  if (mdns) MDNS.end();
  mdns = connected = false;
  WiFi.disconnect(true, true);
}
void connect() {
  stop();
  WiFi.setHostname("xyz");
  WiFi.mode(WIFI_STA);
  WiFi.setAutoReconnect(true);
  WiFi.begin(saved.ssid, saved.password);
  lastAttempt = millis();
  Serial.println("WIFI connecting; use WIFI STATUS (retries every 30s)");
}
void begin() {
  WiFi.persistent(false); // Credentials have one owner: our NVS blob.
  storageReady = preferences.begin("xyz-wifi", false);
  if (!storageReady) { Serial.println("ERR Wi-Fi storage unavailable"); return; }
  if (preferences.getBytesLength("credentials") == sizeof(saved))
    preferences.getBytes("credentials", &saved, sizeof(saved));
  if (valid(saved)) connect();
  else { saved = {}; Serial.println("WIFI unconfigured; use WIFI SET"); }
}
void status() {
  Serial.printf("WIFI configured=%d connected=%d mdns=%d host=xyz.local ip=%s\n",
                saved.ssid[0] != 0, WiFi.status() == WL_CONNECTED, mdns && WiFi.status() == WL_CONNECTED,
                WiFi.localIP().toString().c_str());
}
void cancel() { prompt = 0; pending = {}; }
void input(const char *value) {
  const size_t n = strlen(value);
  if (prompt == 1) {
    if (!n || n > 32) { Serial.println("ERR SSID must be 1..32 bytes; enter SSID:"); return; }
    memcpy(pending.ssid, value, n + 1);
    prompt = 2;
    Serial.println("Password (not echoed; empty for open network; Ctrl-C cancels):");
    return;
  }
  if (n > 64) { Serial.println("ERR password too long; enter password:"); return; }
  memset(pending.password, 0, sizeof(pending.password));
  memcpy(pending.password, value, n + 1);
  if (!valid(pending)) {
    Serial.println("ERR use 8..63 password bytes, 64 hex digits, or empty; enter password:"); return;
  }
  if (preferences.putBytes("credentials", &pending, sizeof(pending)) != sizeof(pending)) {
    cancel(); Serial.println("ERR saving Wi-Fi credentials"); return;
  }
  saved = pending;
  cancel();
  Serial.println("OK Wi-Fi credentials saved");
  connect();
}
void command(const char *action, bool armed) {
  if (!strcmp(action, "STATUS")) { status(); return; }
  if (armed) { Serial.println("ERR disable first with OFF"); return; }
  if (!storageReady) { Serial.println("ERR Wi-Fi storage unavailable"); return; }
  if (!strcmp(action, "SET")) {
    pending = {}; prompt = 1;
    Serial.println("SSID (not echoed; Ctrl-C cancels):");
  } else if (!strcmp(action, "FORGET")) {
    if (preferences.isKey("credentials") && !preferences.remove("credentials")) {
      Serial.println("ERR removing Wi-Fi credentials"); return;
    }
    saved = {}; stop(); Serial.println("OK Wi-Fi credentials forgotten");
  } else Serial.println("ERR WIFI SET | WIFI STATUS | WIFI FORGET");
}
void service(bool armed) {
  // Keep network management/flash operations out of armed motion periods.
  if (armed || !saved.ssid[0]) return;
  const bool up = WiFi.status() == WL_CONNECTED;
  if (!up) {
    if (mdns) MDNS.end();
    mdns = connected = false;
    if (uint32_t(millis() - lastAttempt) >= 30000) {
      lastAttempt = millis(); WiFi.reconnect();
    }
    return;
  }
  if (!connected) {
    connected = true; lastMdnsAttempt = millis() - 5000;
    Serial.println("WIFI connected");
  }
  if (!mdns && uint32_t(millis() - lastMdnsAttempt) >= 5000) {
    lastMdnsAttempt = millis(); mdns = MDNS.begin("xyz");
    Serial.println(mdns ? "MDNS ready: xyz.local" : "ERR mDNS start; retrying");
  }
}
} // namespace WifiProvisioning
