#include "Net.h"
#include <WiFi.h>
#include <ESPmDNS.h>
#include <WebSocketsServer.h>

using namespace pet::wire;

namespace {

const char* HOSTNAME = "bug";
constexpr uint16_t WS_PORT = 81;
constexpr uint32_t CONNECT_TIMEOUT_MS = 15000;
constexpr uint32_t RETRY_DELAY_MS = 10000;

WebSocketsServer ws(WS_PORT);
Preferences* prefsPtr = nullptr;

enum class State : uint8_t { Off, Connecting, Online, RetryWait };
State state = State::Off;
String ssid, password;
uint32_t connectStart = 0, retryAt = 0;
bool wsStarted = false;

WifiState wireState() {
    switch (state) {
        case State::Off:        return WifiState::UNCONFIGURED;
        case State::Connecting: return WifiState::CONNECTING;
        case State::Online:     return WifiState::CONNECTED;
        default:                return WifiState::FAILED;
    }
}

flatbuffers::Offset<WifiStatus> buildWifiStatus(flatbuffers::FlatBufferBuilder& fbb) {
    bool up = (state == State::Online);
    String ip = up ? WiFi.localIP().toString() : String();
    return CreateWifiStatusDirect(fbb, wireState(), ssid.c_str(),
                                  up ? ip.c_str() : nullptr, HOSTNAME,
                                  up ? (int16_t)WiFi.RSSI() : 0,
                                  (uint8_t)(wsStarted ? ws.connectedClients() : 0));
}

void broadcastWifiStatus() {
    flatbuffers::FlatBufferBuilder fbb(256);
    auto st = buildWifiStatus(fbb);
    Comms::broadcast(fbb, Msg::WifiStatus, st.Union());
}

void wsEvent(uint8_t num, WStype_t type, uint8_t* payload, size_t len) {
    switch (type) {
        case WStype_CONNECTED:
            Comms::onWsClientConnected(num);
            break;
        case WStype_BIN:
            Comms::onPacketBytes(payload, len, Comms::Origin::Ws, num);
            break;
        default:  // TEXT/PING/DISCONNECTED etc: nothing to do
            break;
    }
}

void startConnect() {
    WiFi.mode(WIFI_STA);
    WiFi.setHostname(HOSTNAME);
    WiFi.begin(ssid.c_str(), password.c_str());
    state = State::Connecting;
    connectStart = millis();
    Comms::logf(LogLevel::INFO, "wifi: connecting to %s", ssid.c_str());
}

void goOnline() {
    if (MDNS.begin(HOSTNAME)) {
        MDNS.addService("ws", "tcp", WS_PORT);
    } else {
        Comms::logf(LogLevel::WARN, "wifi: mDNS start failed");
    }
    ws.begin();
    ws.onEvent(wsEvent);
    wsStarted = true;
    state = State::Online;
    Comms::logf(LogLevel::INFO, "wifi: connected, ip %s, ws://%s.local:%u",
                WiFi.localIP().toString().c_str(), HOSTNAME, WS_PORT);
    broadcastWifiStatus();
}

void goOffline() {
    if (wsStarted) {
        ws.close();
        wsStarted = false;
    }
    MDNS.end();
}

}  // namespace

namespace Net {

void begin(Preferences& prefs) {
    prefsPtr = &prefs;
    ssid = prefs.getString("ssid", "");
    password = prefs.getString("wifipass", "");
    if (ssid.length()) startConnect();
}

void loop() {
    switch (state) {
        case State::Connecting:
            if (WiFi.status() == WL_CONNECTED) {
                goOnline();
            } else if (millis() - connectStart > CONNECT_TIMEOUT_MS) {
                state = State::RetryWait;
                retryAt = millis() + RETRY_DELAY_MS;
                Comms::logf(LogLevel::WARN, "wifi: connect to %s failed, retry in %lus",
                            ssid.c_str(), (unsigned long)(RETRY_DELAY_MS / 1000));
                broadcastWifiStatus();
            }
            break;
        case State::Online:
            ws.loop();
            if (WiFi.status() != WL_CONNECTED) {
                goOffline();
                state = State::RetryWait;
                retryAt = millis() + RETRY_DELAY_MS;
                Comms::logf(LogLevel::WARN, "wifi: connection lost, retrying");
            }
            break;
        case State::RetryWait:
            if ((int32_t)(millis() - retryAt) >= 0) startConnect();
            break;
        case State::Off:
            break;
    }
}

void handleWifiCmd(const WifiCmd* cmd, const Comms::ReplyTarget& tgt) {
    const char* s = (cmd && cmd->ssid()) ? cmd->ssid()->c_str() : "";
    if (*s) {  // new credentials: persist, then reconnect via the state machine
        ssid = s;
        password = (cmd->password()) ? cmd->password()->c_str() : "";
        prefsPtr->putString("ssid", ssid);
        prefsPtr->putString("wifipass", password);
        if (state == State::Online) goOffline();
        WiFi.disconnect();
        startConnect();
    }
    flatbuffers::FlatBufferBuilder fbb(256);
    auto st = buildWifiStatus(fbb);
    Comms::reply(tgt, fbb, Msg::WifiStatus, st.Union());
}

void wsSendTo(uint8_t client, const uint8_t* buf, size_t len) {
    if (wsStarted) ws.sendBIN(client, buf, len);
}

void wsBroadcast(const uint8_t* buf, size_t len) {
    if (wsStarted) ws.broadcastBIN(buf, len);
}

}  // namespace Net
