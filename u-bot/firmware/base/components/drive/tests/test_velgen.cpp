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

static uint32_t ihr(uint8_t run, uint8_t hold, uint8_t delay = 8) {
    return (uint32_t)hold | ((uint32_t)run << 8) | ((uint32_t)delay << 16);
}
// IHOLD_IRUN writes in the log from `from` on: attempted, and accepted.
static int currentWrites(size_t from, int *accepted = nullptr) {
    int n = 0, ok = 0;
    const auto &log = FakeTmc::log();
    for (size_t i = from; i < log.size(); i++) {
        if (log[i].reg != Tmc2209Uart::IHOLD_IRUN) continue;
        n++;
        ok += log[i].accepted;
    }
    if (accepted) *accepted = ok;
    return n;
}

// The live current path: IHOLD_IRUN written with the power stage on, which is
// how boost, its ramp down and the OTPW derate reach the driver.
static void liveCurrent(Tmc2209Uart &bus) {
    FakeTmc::Node &n = FakeTmc::node(0);
    VelGen gen(bus, 0);
    assert(gen.setCurrentMa(1200, 600, 8));   // IRUN 20, IHOLD 9
    resetChip();
    assert(gen.begin());
    assert(gen.liveRun() == 20 && gen.liveHold() == 9);

    // Disabled: refused without a word on the bus, and nothing invalidated.
    size_t mark = FakeTmc::log().size();
    assert(!gen.setLiveCurrent(31, 31));
    assert(FakeTmc::log().size() == mark && gen.ok() && gen.liveRun() == 20);

    gen.setEnabled(true);
    assert(gen.enabled());
    // Bad pairs are refused the same way: past 31, or hold above run.
    mark = FakeTmc::log().size();
    assert(!gen.setLiveCurrent(32, 9));
    assert(!gen.setLiveCurrent(20, 21));
    assert(FakeTmc::log().size() == mark && gen.ok());

    // A verified write: IFCNT read, the write, IFCNT read; the chip has it.
    uint32_t ifcnt = n.regs[Tmc2209Uart::IFCNT];
    assert(gen.setLiveCurrent(31, 31));
    assert(n.regs[Tmc2209Uart::IHOLD_IRUN] == ihr(31, 31));
    assert(((n.regs[Tmc2209Uart::IFCNT] - ifcnt) & 255) == 1);
    assert(gen.liveRun() == 31 && gen.liveHold() == 31);
    assert(gen.liveRunMilliamps() == MotorCurrent::milliamps(31) && gen.liveRunMilliamps() <= 1768);
    // The base pair is untouched: begin() still programs 20/9.
    assert(gen.runCurrent() == 20 && gen.holdCurrent() == 9);

    // The same pair again costs nothing.
    mark = FakeTmc::log().size();
    assert(gen.setLiveCurrent(31, 31));
    assert(FakeTmc::log().size() == mark);

    // A write the chip throws away is sent once more, and that one lands.
    mark = FakeTmc::log().size();
    n.dropReg = Tmc2209Uart::IHOLD_IRUN;
    n.dropTimes = 1;
    int accepted = 0;
    assert(gen.setLiveCurrent(30, 30));
    assert(currentWrites(mark, &accepted) == 2 && accepted == 1);
    assert(gen.liveRetries() == 1 && gen.ok() && gen.liveRun() == 30);
    assert(n.regs[Tmc2209Uart::IHOLD_IRUN] == ihr(30, 30));
    // So does one that landed but whose acknowledgement was lost -- the IFCNT
    // read after it -- which writes the same pair twice, harmlessly.
    int ifcntReads = 0;
    n.onRead = [&](uint8_t reg, uint32_t &) {
        if (reg == Tmc2209Uart::IFCNT && ++ifcntReads == 1) {   // the read before: arm the one after
            n.failRead = Tmc2209Uart::IFCNT;
            n.failTimes = 1;
        }
        return false;
    };
    mark = FakeTmc::log().size();
    assert(gen.setLiveCurrent(29, 29));
    n.onRead = nullptr;
    assert(currentWrites(mark, &accepted) == 2 && accepted == 2);
    assert(gen.liveRetries() == 2 && gen.ok() && n.regs[Tmc2209Uart::IHOLD_IRUN] == ihr(29, 29));
    // And an IFCNT read that fails before anything was written.
    n.failRead = Tmc2209Uart::IFCNT;
    n.failTimes = 1;
    mark = FakeTmc::log().size();
    assert(gen.setLiveCurrent(29, 20));
    assert(currentWrites(mark, &accepted) == 1 && accepted == 1);
    assert(gen.liveRetries() == 3 && gen.ok() && gen.liveHold() == 20);
    // And a bad echo.
    n.badEcho = true;
    n.badEchoTimes = 1;
    assert(gen.setLiveCurrent(28, 28));
    assert(gen.liveRetries() == 4 && gen.ok());

    // Twice unacknowledged: the driver is invalidated (the drive then cuts
    // EN), the live pair still says what last landed, and nothing more is
    // written until begin() has been through it again.
    mark = FakeTmc::log().size();
    n.dropReg = Tmc2209Uart::IHOLD_IRUN;
    n.dropTimes = 2;
    assert(!gen.setLiveCurrent(20, 9));
    assert(currentWrites(mark, &accepted) == 2 && accepted == 0);
    assert(!gen.ok() && gen.liveRun() == 28 && gen.liveHold() == 28);
    assert(n.dropReg < 0);   // both drops used up
    mark = FakeTmc::log().size();
    assert(!gen.setLiveCurrent(20, 9));
    assert(FakeTmc::log().size() == mark);

    // begin() puts the base pair back, on the chip and as the live pair.
    gen.setEnabled(false);
    assert(gen.begin());
    assert(n.regs[Tmc2209Uart::IHOLD_IRUN] == ihr(20, 9) && gen.liveRun() == 20 && gen.liveHold() == 9);
    gen.setEnabled(true);
    assert(gen.setLiveCurrent(31, 31));
    gen.setEnabled(false);
    resetChip();   // a VMOT cycle as well
    assert(gen.begin());
    assert(n.regs[Tmc2209Uart::IHOLD_IRUN] == ihr(20, 9) && gen.liveRun() == 20 && gen.liveHold() == 9);

    // The pair keeps IHOLDDELAY: the driver's own step-down still paces the
    // standstill reduction.
    assert(gen.setCurrentMa(1500, 552, 3));
    assert(gen.begin());
    gen.setEnabled(true);
    assert(gen.setLiveCurrent(31, 31));
    assert(n.regs[Tmc2209Uart::IHOLD_IRUN] == ihr(31, 31, 3));
    gen.setEnabled(false);
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
    // Boost: IRUN 31 is 1767.8 mA, so 1768 is the smallest request that gets
    // it and 1767 rounds down to 30.
    assert(MotorCurrent::scale(MotorCurrent::BOOST_MAX_MA) == 31 && MotorCurrent::BOOST_MAX_MA == 1768);
    assert(MotorCurrent::scale(1767) == 30);
    assert(MotorCurrent::milliamps(31) <= 1768 && MotorCurrent::milliamps(31) > 1767);
    assert(MotorCurrent::scale(5000) == 31);
    assert(MotorCurrent::validBoost(1200, 0) && MotorCurrent::validBoost(1500, 0));   // off
    assert(MotorCurrent::validBoost(1200, 1200) && MotorCurrent::validBoost(1200, 1768));
    assert(MotorCurrent::validBoost(1500, 1768) && MotorCurrent::validBoost(1500, 1500));
    assert(!MotorCurrent::validBoost(1200, 1199) && !MotorCurrent::validBoost(1200, 1769));
    assert(!MotorCurrent::validBoost(1500, 1400) && !MotorCurrent::validBoost(1200, -1));
    assert(MotorCurrent::MAX_MA == 1500 && MotorCurrent::RATED_MA == 1500);   // run_ma stays capped
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
    // Hard flags refuse: overtemperature shutdown, the shorts, t143 and up.
    assert(VelGen::DRV_HARD == 0xE3E && VelGen::DRV_SOFT == 0x101 && !(VelGen::DRV_HARD & VelGen::DRV_SOFT));
    for (unsigned flag : {2u, 4u, 8u, 16u, 32u, 1u << 9, 1u << 10, 1u << 11}) {
        resetChip(); regs[Tmc2209Uart::DRVSTATUS] = flag;
        assert(!gen.begin());
        resetChip(); regs[Tmc2209Uart::DRVSTATUS] = flag | 1;   // hot as well changes nothing
        assert(!gen.begin());
    }
    // Soft flags don't: OTPW and t120 configure the driver and say it is hot.
    for (unsigned flag : {1u, 1u << 8, 1u | (1u << 8)}) {
        resetChip(); regs[Tmc2209Uart::DRVSTATUS] = flag;
        assert(gen.begin() && gen.ok() && gen.hot());
    }
    resetChip(); regs[Tmc2209Uart::DRVSTATUS] = 0xC0; // open load while disabled is not fatal
    assert(gen.begin() && !gen.hot());
    resetChip(); regs[Tmc2209Uart::DRVSTATUS] = 1;   // hot() is begin()'s: a cool begin() clears it
    assert(gen.begin() && gen.hot());
    resetChip();
    assert(gen.begin() && !gen.hot());
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
    liveCurrent(bus);
    puts("PASS: current limits/quantization, register verification, lost writes, reset recovery, thresholds, fault refusal, NODECONF, "
         "boost scale and validBoost, soft/hard DRV_STATUS at begin(), live current: refusals, verified write, no-op, "
         "one retry then invalidation, begin() restores base");
}
