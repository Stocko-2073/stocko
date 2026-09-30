#include <cassert>
#include <cstdio>
#include <initializer_list>
#include "VelGen.h"
#include "fake_tmc.h"

// The driver at address 0, under the names the checks below were written
// against. Accepted writes increment IFCNT, including wraparound.
static uint32_t *const regs = FakeTmc::node(0).regs;
static int &dropReg = FakeTmc::node(0).dropReg;
static int &failRead = FakeTmc::node(0).failRead;
static int &corruptReg = FakeTmc::node(0).corruptReg;
static bool &badEcho = FakeTmc::node(0).badEcho;
static void resetChip(bool spreadPin = false) { FakeTmc::resetChip(0, spreadPin); }

int main() {
    for (int ma = 100; ma <= 1500; ++ma) {
        auto actual = MotorCurrent::milliamps(MotorCurrent::scale(ma));
        assert(actual <= ma);
        assert(ma - actual < MotorCurrent::MA_PER_SCALE + 0.001f);
    }
    assert(MotorCurrent::scale(1200) == 20);
    assert(MotorCurrent::scale(600) == 9);
    assert(MotorCurrent::scale(1500) == 26);
    assert(!MotorCurrent::valid(1501, 600));
    assert(!MotorCurrent::valid(600, 601));
    assert(!MotorCurrent::valid(1200, 0));
    Tmc2209Uart bus(1, 1, 2);
    resetChip();
    VelGen gen(bus, 0);
    assert(!gen.setCurrentMa(1501, 600, 8));
    assert(gen.setCurrentMa(1200, 600, 8));
    gen.setSpreadAboveRate(1500);
    assert(gen.begin());
    assert((regs[Tmc2209Uart::GCONF] & 7) == 4);
    assert(!(regs[Tmc2209Uart::CHOPCONF] & (1UL << 17)));
    assert(((regs[Tmc2209Uart::CHOPCONF] >> 24) & 15) == 5);
    assert(regs[Tmc2209Uart::IHOLD_IRUN] == (9 | (20 << 8) | (8 << 16)));
    assert(regs[Tmc2209Uart::TPWMTHRS] == 250);
    assert(gen.setMicrosteps(16));
    assert(regs[Tmc2209Uart::TPWMTHRS] == 500);
    gen.presetClockGain(1.1f);
    assert(regs[Tmc2209Uart::TPWMTHRS] == 550);
    gen.setEnabled(true);
    assert(gen.enabled());
    assert(!gen.setCurrentMa(1500, 600, 8));
    gen.setRate(1000);
    assert(regs[Tmc2209Uart::VACTUAL] != 0);
    gen.setEnabled(false);
    resetChip(true); // VMOT cycle: all configuration lost, SPREAD pin high
    assert(gen.begin(8));
    assert((regs[Tmc2209Uart::GCONF] & 7) == 0); // compensates hardware inversion
    assert(regs[Tmc2209Uart::IHOLD_IRUN] == (9 | (20 << 8) | (8 << 16)));
    assert(regs[Tmc2209Uart::VACTUAL] == 0);
    for (int reg : {0x22, 0x00, 0x6C, 0x10, 0x13, 0x11, 0x01}) {
        resetChip();
        dropReg = reg; // echo succeeds but chip rejects datagram
        assert(!gen.begin());
        assert(!gen.ok());
        gen.setEnabled(true);
        assert(!gen.enabled());
    }
    for (int reg : {0x06, 0x02, 0x6C, 0x00, 0x01, 0x6F}) {
        resetChip(); failRead = reg;
        assert(!gen.begin());
    }
    resetChip(); corruptReg = Tmc2209Uart::GCONF;
    assert(!gen.begin());
    for (unsigned flag : {1u, 2u, 4u, 8u, 16u, 32u}) {
        resetChip(); regs[Tmc2209Uart::DRVSTATUS] = flag;
        assert(!gen.begin());
    }
    resetChip(); regs[Tmc2209Uart::DRVSTATUS] = 0xC0; // open load while disabled is not fatal
    assert(gen.begin());
    dropReg = Tmc2209Uart::VACTUAL;
    gen.setEnabled(true);
    assert(!gen.enabled());
    resetChip(); regs[Tmc2209Uart::IOIN] &= ~1u;
    assert(!gen.begin()); // cannot configure an energized motor
    resetChip(); assert(gen.begin()); gen.setEnabled(true);
    badEcho = true; gen.setRate(1200);
    assert(!gen.ok());
    // NODECONF: SENDDELAY 2 (3 x 8 bit times), the minimum for two nodes on
    // one wire, written first after VACTUAL = 0. The chip never reads it back,
    // so a write it threw away is caught by IFCNT alone.
    resetChip(); FakeTmc::clearLog();
    assert(gen.begin());
    assert(regs[Tmc2209Uart::NODECONF] == 0x200);
    const auto &writes = FakeTmc::log();
    assert(writes.size() >= 2);
    assert(writes[0].reg == Tmc2209Uart::VACTUAL && writes[0].value == 0 && writes[0].accepted);
    assert(writes[1].reg == Tmc2209Uart::NODECONF && writes[1].value == 0x200 && writes[1].accepted);
    resetChip(); dropReg = Tmc2209Uart::NODECONF;
    assert(!gen.begin());
    assert(!gen.ok());
    puts("PASS: current limits/quantization, register verification, lost writes, reset recovery, thresholds, fault refusal, NODECONF");
}
