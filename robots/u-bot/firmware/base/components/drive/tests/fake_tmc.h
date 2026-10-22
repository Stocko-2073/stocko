#pragma once
#include <stdint.h>
#include <string.h>

#include <functional>
#include <vector>

#include "Tmc2209Uart.h"
#include "fake_clock.h"

// TMC2209 register files behind the real Tmc2209Uart API, so VelGen and
// everything above it run unmodified on the host. This header defines
// Tmc2209Uart::read and ::write; Tmc2209Uart.cpp is never linked into a test.
//
// One register file per node address, because the robot's two drivers share
// one bus (addresses 0 and 1) and a fault on one must not show up on the other.
//
// What the chip does that VelGen depends on, and so is modelled:
//   - IFCNT counts accepted writes and wraps at 256. It is VelGen's only
//     acknowledgement, so a write that "echoes fine but never landed" has to
//     be expressible (dropReg).
//   - GSTAT is write-1-to-clear.
// Every transaction is instant on the fake clock; bus timing is not modelled.
//
// Failure injection stays armed until resetChip(). Setting the matching
// *Times field to n > 0 makes it fire n more times and then disarm instead,
// which is what a retry path needs to be tested against.
struct FakeTmc {
    static const int NODES = 4;   // MS1/MS2 select node addresses 0..3

    struct Node {
        uint32_t regs[128];
        bool present = true;      // false: nothing answers at this address

        int dropReg = -1;         // echo fine, chip rejects the datagram: no IFCNT, no change
        int dropTimes = 0;
        int failRead = -1;        // reads of this register get no reply
        int failTimes = 0;
        int corruptReg = -1;      // reads of this register come back with bit 0 flipped
        int corruptTimes = 0;
        bool badEcho = false;     // writes echo wrong and do not land
        int badEchoTimes = 0;

        // Where a plant attaches. onRead may supply the value of a register the
        // chip computes (MSCNT, DRV_STATUS's CS_ACTUAL); return true if it did.
        // onWrite sees every write the chip accepted, after it landed.
        std::function<bool(uint8_t reg, uint32_t &value)> onRead;
        std::function<void(uint8_t reg, uint32_t value)> onWrite;
    };

    // Every write attempt, landed or not, in order.
    struct Write {
        uint8_t addr;
        uint8_t reg;
        uint32_t value;
        int64_t timeUs;
        bool accepted;
    };

    static Node &node(uint8_t addr) {
        static Node nodes[NODES];
        return nodes[addr % NODES];
    }
    static std::vector<Write> &log() {
        static std::vector<Write> writes;
        return writes;
    }
    static void clearLog() { log().clear(); }

    // Power-on state, as after a VMOT cycle: all configuration lost. The values
    // that differ from zero are the ones VelGen::begin() looks at. Hooks stay
    // attached -- the motor is still there.
    static void resetChip(uint8_t addr, bool spreadPin = false) {
        Node &n = node(addr);
        memset(n.regs, 0, sizeof n.regs);
        n.regs[Tmc2209Uart::IOIN] = 0x21000001 | (spreadPin ? 256 : 0);   // VERSION 0x21, EN high
        n.regs[Tmc2209Uart::CHOPCONF] = 0x10000053 | (1UL << 17);         // force vsense correction
        n.regs[Tmc2209Uart::GSTAT] = 1;                                   // reset flag
        n.regs[Tmc2209Uart::IFCNT] = 254;                                 // wraps within begin()
        n.dropReg = n.failRead = n.corruptReg = -1;
        n.dropTimes = n.failTimes = n.corruptTimes = n.badEchoTimes = 0;
        n.badEcho = false;
    }

    // Whether an injection armed on `armed` fires for `reg`, using up one of
    // its counted uses if it has any.
    static bool fires(int &armed, int &times, int reg) {
        if (armed < 0 || armed != reg) return false;
        if (times > 0 && --times == 0) armed = -1;
        return true;
    }
    static bool firesEcho(Node &n) {
        if (!n.badEcho) return false;
        if (n.badEchoTimes > 0 && --n.badEchoTimes == 0) n.badEcho = false;
        return true;
    }
};

inline Tmc2209Uart::Result Tmc2209Uart::read(uint8_t addr, uint8_t reg, uint32_t) {
    Result r = {};
    reg &= 0x7F;
    if (addr >= FakeTmc::NODES) {   // no such node: the echo, then silence
        r.st = NO_REPLY;
        return r;
    }
    FakeTmc::Node &n = FakeTmc::node(addr);
    if (!n.present || FakeTmc::fires(n.failRead, n.failTimes, reg)) {
        r.st = NO_REPLY;
        return r;
    }
    uint32_t v = n.regs[reg];
    if (n.onRead) n.onRead(reg, v);
    if (FakeTmc::fires(n.corruptReg, n.corruptTimes, reg)) v ^= 1;
    r.st = OK;
    r.value = v;
    return r;
}

inline Tmc2209Uart::Result Tmc2209Uart::write(uint8_t addr, uint8_t reg, uint32_t value) {
    Result r = {};
    reg &= 0x7F;
    bool exists = addr < FakeTmc::NODES;
    FakeTmc::Node &n = FakeTmc::node(addr);
    writes_++;
    bool landed = false;
    if (exists && FakeTmc::firesEcho(n)) {
        r.st = BAD_ECHO;
        echoFaults_++;
    } else {
        // The echo is the wire, not the chip, so it is fine even when nothing
        // is listening or the chip throws the datagram away.
        r.st = OK;
        landed = exists && n.present && !FakeTmc::fires(n.dropReg, n.dropTimes, reg);
    }
    if (landed) {
        if (reg == GSTAT) n.regs[reg] &= ~value;
        else n.regs[reg] = value;
        n.regs[IFCNT] = (n.regs[IFCNT] + 1) & 255;
    }
    FakeTmc::log().push_back({addr, reg, value, FakeClock::now(), landed});
    if (landed && n.onWrite) n.onWrite(reg, value);
    return r;
}
