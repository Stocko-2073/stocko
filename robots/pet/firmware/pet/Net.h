#pragma once
#include <Arduino.h>
#include <Preferences.h>
#include "Comms.h"
#include "src/pet_generated.h"

// WiFi + mDNS + websocket server lifecycle. Non-blocking: begin() kicks off an
// association attempt if credentials are stored, loop() runs the state machine
// (15 s connect timeout, retry every 10 s). When connected: mDNS as
// "bug" (bug.local) and a WebSocketsServer on port 81 carrying Packets.
namespace Net {

void begin(Preferences& prefs);  // reads "ssid"/"wifipass" from the prefs namespace
void loop();

// wifi {ssid} {pass} -> persist + reconnect; bare wifi -> WifiStatus reply.
void handleWifiCmd(const pet::wire::WifiCmd* cmd, const Comms::ReplyTarget& tgt);

// Outbound hooks used by Comms; no-ops until the server is up.
void wsSendTo(uint8_t client, const uint8_t* buf, size_t len);
void wsBroadcast(const uint8_t* buf, size_t len);

}  // namespace Net
