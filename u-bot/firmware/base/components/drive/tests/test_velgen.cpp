#include <cassert>
#include <cstdio>
#include <initializer_list>
#include "VelGen.h"

// Driver simulator: accepted writes increment IFCNT, including wraparound.
static uint32_t regs[128];
static int dropReg = -1, failRead = -1, corruptReg = -1;
static bool badEcho = false;
static void resetChip(bool spreadPin = false) {
    memset(regs, 0, sizeof regs);
    regs[Tmc2209Uart::IOIN] = 0x21000001 | (spreadPin ? 256 : 0);
    regs[Tmc2209Uart::CHOPCONF] = 0x10000053 | (1UL << 17); // force vsense correction
    regs[Tmc2209Uart::GSTAT] = 1;
    regs[Tmc2209Uart::IFCNT] = 254;
    dropReg = failRead = corruptReg = -1;
    badEcho = false;
}
Tmc2209Uart::Result Tmc2209Uart::read(uint8_t, uint8_t reg, uint32_t) {
    Result r = {};
    r.st = reg == failRead ? NO_REPLY : OK;
    r.value = regs[reg] ^ (reg == corruptReg ? 1 : 0);
    return r;
}
Tmc2209Uart::Result Tmc2209Uart::write(uint8_t, uint8_t reg, uint32_t value) {
    Result r = {};
    r.st = badEcho ? BAD_ECHO : OK;
    if (reg != dropReg && !badEcho) {
        if (reg == GSTAT) regs[reg] &= ~value;
        else regs[reg] = value;
        regs[IFCNT] = (regs[IFCNT] + 1) & 255;
    }
    return r;
}
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
    puts("PASS: current limits/quantization, register verification, lost writes, reset recovery, thresholds, fault refusal");
}
