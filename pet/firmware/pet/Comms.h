#pragma once
#include <Arduino.h>
#include "src/pet_generated.h"

// Packet transport + routing. The wire protocol is binary-only FlatBuffer
// Packets (see pet.fbs). Serial frames are 0xBE 0xEF + u16 LE payload length +
// payload; websocket binary messages carry one bare Packet each.
//
// Replies go only to the requesting transport/client with the request's req_id
// echoed; async events (streams, faults, walk progress) broadcast to serial
// and every websocket client with req_id 0.
namespace Comms {

constexpr size_t MAX_PACKET = 512;

enum class Origin : uint8_t { SerialPort, Ws };

struct ReplyTarget {
    Origin origin;
    uint8_t wsClient = 0;  // valid when origin == Ws
    uint32_t reqId = 0;    // echoed in the reply
};

void pollSerial();  // call from loop(): deframe + verify + dispatch

// Entry point for complete packet buffers from any transport (Net's websocket
// event handler calls this with each binary message).
void onPacketBytes(const uint8_t* data, size_t len, Origin origin, uint8_t wsClient);

// Replay buffered boot/event logs to a websocket client that just attached.
void onWsClientConnected(uint8_t num);

// Wrap a finished union member in a Packet and route it.
void reply(const ReplyTarget& tgt, flatbuffers::FlatBufferBuilder& fbb,
           pet::wire::Msg type, flatbuffers::Offset<void> msg);
void broadcast(flatbuffers::FlatBufferBuilder& fbb,
               pet::wire::Msg type, flatbuffers::Offset<void> msg);

// Conveniences.
void replyAck(const ReplyTarget& tgt, const char* detail, bool ok = true);
void replyLog(const ReplyTarget& tgt, pet::wire::LogLevel level, const char* text);
void broadcastLog(pet::wire::LogLevel level, const char* text);
void logf(pet::wire::LogLevel level, const char* fmt, ...);  // broadcastLog, printf-style

}  // namespace Comms

// The command dispatch switch — implemented in pet.ino, where the servos live.
void dispatchPacket(const pet::wire::Packet* pkt, const Comms::ReplyTarget& tgt);
