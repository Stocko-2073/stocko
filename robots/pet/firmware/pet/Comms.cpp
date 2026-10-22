#include "Comms.h"
#include "Net.h"
#include <stdarg.h>

using namespace pet::wire;

namespace {

constexpr uint8_t MAGIC0 = 0xBE, MAGIC1 = 0xEF;
// A Packet smaller than this can't be a valid flatbuffer; reject early.
constexpr size_t MIN_PACKET = 12;

void writeFramed(const uint8_t* buf, size_t len) {
    uint8_t hdr[4] = { MAGIC0, MAGIC1, (uint8_t)(len & 0xFF), (uint8_t)(len >> 8) };
    Serial.write(hdr, 4);
    Serial.write(buf, len);
}

// --- boot/event log ring ---
// Logs broadcast before any client attaches (boot banner, calibration loaded)
// would otherwise vanish; keep the last few and replay them to late joiners.
constexpr int LOG_RING = 8;
struct LogEntry { LogLevel level; String text; };
LogEntry logRing[LOG_RING];
int ringHead = 0, ringCount = 0;
bool serialReplayed = false;

void ringPush(LogLevel level, const char* text) {
    logRing[ringHead] = { level, String(text) };
    ringHead = (ringHead + 1) % LOG_RING;
    if (ringCount < LOG_RING) ringCount++;
}

flatbuffers::DetachedBuffer buildLogPacket(uint32_t reqId, LogLevel level, const char* text) {
    flatbuffers::FlatBufferBuilder fbb(256);
    auto log = CreateLogDirect(fbb, level, text);
    auto pkt = CreatePacket(fbb, reqId, Msg::Log, log.Union());
    FinishPacketBuffer(fbb, pkt);
    return fbb.Release();
}

void sendTo(const Comms::ReplyTarget& tgt, const uint8_t* buf, size_t len) {
    if (tgt.origin == Comms::Origin::SerialPort) writeFramed(buf, len);
    else Net::wsSendTo(tgt.wsClient, buf, len);
}

void replayRingTo(const Comms::ReplyTarget& tgt) {
    for (int i = 0; i < ringCount; i++) {
        int idx = (ringHead - ringCount + i + LOG_RING) % LOG_RING;
        auto buf = buildLogPacket(0, logRing[idx].level, logRing[idx].text.c_str());
        sendTo(tgt, buf.data(), buf.size());
    }
}

}  // namespace

namespace Comms {

void reply(const ReplyTarget& tgt, flatbuffers::FlatBufferBuilder& fbb,
           Msg type, flatbuffers::Offset<void> msg) {
    auto pkt = CreatePacket(fbb, tgt.reqId, type, msg);
    FinishPacketBuffer(fbb, pkt);
    sendTo(tgt, fbb.GetBufferPointer(), fbb.GetSize());
}

void broadcast(flatbuffers::FlatBufferBuilder& fbb, Msg type, flatbuffers::Offset<void> msg) {
    auto pkt = CreatePacket(fbb, 0, type, msg);
    FinishPacketBuffer(fbb, pkt);
    writeFramed(fbb.GetBufferPointer(), fbb.GetSize());
    Net::wsBroadcast(fbb.GetBufferPointer(), fbb.GetSize());
}

void replyAck(const ReplyTarget& tgt, const char* detail, bool ok) {
    flatbuffers::FlatBufferBuilder fbb(256);
    auto ack = CreateAckDirect(fbb, ok, detail);
    reply(tgt, fbb, Msg::Ack, ack.Union());
}

void replyLog(const ReplyTarget& tgt, LogLevel level, const char* text) {
    flatbuffers::FlatBufferBuilder fbb(512);
    auto log = CreateLogDirect(fbb, level, text);
    reply(tgt, fbb, Msg::Log, log.Union());
}

void broadcastLog(LogLevel level, const char* text) {
    ringPush(level, text);
    auto buf = buildLogPacket(0, level, text);
    writeFramed(buf.data(), buf.size());
    Net::wsBroadcast(buf.data(), buf.size());
}

void logf(LogLevel level, const char* fmt, ...) {
    char buf[192];
    va_list ap;
    va_start(ap, fmt);
    vsnprintf(buf, sizeof(buf), fmt, ap);
    va_end(ap);
    broadcastLog(level, buf);
}

void onWsClientConnected(uint8_t num) {
    replayRingTo(ReplyTarget{ Origin::Ws, num, 0 });
}

void onPacketBytes(const uint8_t* data, size_t len, Origin origin, uint8_t wsClient) {
    flatbuffers::Verifier verifier(data, len);
    if (!VerifyPacketBuffer(verifier)) {
        // Can't trust req_id in a bad buffer; answer with an uncorrelated error.
        replyLog(ReplyTarget{ origin, wsClient, 0 }, LogLevel::ERROR, "bad packet");
        return;
    }
    const Packet* pkt = GetPacket(data);
    // First packet over serial after boot: replay buffered boot logs so a host
    // that attached late still sees them (mirrors ws connect replay).
    if (origin == Origin::SerialPort && !serialReplayed) {
        serialReplayed = true;
        replayRingTo(ReplyTarget{ origin, 0, 0 });
    }
    dispatchPacket(pkt, ReplyTarget{ origin, wsClient, pkt->req_id() });
}

void pollSerial() {
    enum class Rx : uint8_t { Magic0, Magic1, LenLo, LenHi, Payload };
    static Rx state = Rx::Magic0;
    static uint8_t frame[MAX_PACKET];
    static size_t frameLen = 0, framePos = 0;

    while (Serial.available()) {
        uint8_t c = Serial.read();
        switch (state) {
            case Rx::Magic0:
                if (c == MAGIC0) state = Rx::Magic1;
                break;
            case Rx::Magic1:
                if (c == MAGIC1) state = Rx::LenLo;
                else if (c != MAGIC0) state = Rx::Magic0;  // 0xBE 0xBE 0xEF still syncs
                break;
            case Rx::LenLo:
                frameLen = c;
                state = Rx::LenHi;
                break;
            case Rx::LenHi:
                frameLen |= (size_t)c << 8;
                if (frameLen < MIN_PACKET || frameLen > MAX_PACKET) {
                    state = Rx::Magic0;  // implausible length: resync on magic
                } else {
                    framePos = 0;
                    state = Rx::Payload;
                }
                break;
            case Rx::Payload:
                frame[framePos++] = c;
                if (framePos == frameLen) {
                    onPacketBytes(frame, frameLen, Origin::SerialPort, 0);
                    state = Rx::Magic0;
                }
                break;
        }
    }
}

}  // namespace Comms
