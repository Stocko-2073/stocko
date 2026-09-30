import Foundation
import Testing
@testable import UBotCore

// Swift Testing, not XCTest. The Command Line Tools ship Testing.framework but
// not XCTest.framework, so `import XCTest` will not build until Xcode is
// installed -- and the whole point of this package is that it builds today.
//
// `ubotctl selftest` covers the same ground without any test framework at all,
// as a belt-and-braces path for a machine with an even barer toolchain.

/// The canonical frame: enabled | cmd active | encA | encB, no battery,
/// wheel A +1.000 turns/s, wheel B -1.000 turns/s, command -0.250 m/s.
private let sampleFrame = Data([
    0b0001_1101, 0x00, 0x00, 0x00, 0x00,
    0xE8, 0x03,
    0x18, 0xFC,
    0x06, 0xFF,
    0x00, 0x00,
])

@Suite("Status decode")
struct StatusDecodeTests {

    @Test("flags unpack to the bits ble.c sets")
    func flags() throws {
        let s = try #require(UBotStatus(sampleFrame))
        #expect(s.isEnabled)
        #expect(s.isCommandActive)
        #expect(s.encoderAOK)
        #expect(s.encoderBOK)
        #expect(!s.isFaulted)
        #expect(!s.batteryIsSensed)
    }

    @Test("signed little-endian fields survive the round trip")
    func signedFields() throws {
        let s = try #require(UBotStatus(sampleFrame))
        #expect(s.wheelATurnsPerSec == 1.0)
        #expect(s.wheelBTurnsPerSec == -1.0)
        #expect(s.commandedMetersPerSec == -0.250)
        #expect(s.commandedRadiansPerSec == 0.0)
    }

    @Test("a short frame is rejected rather than decoded as garbage")
    func shortFrame() {
        #expect(UBotStatus(Data([0x01, 0x00])) == nil)
        #expect(UBotStatus(Data()) == nil)
    }

    @Test("a longer frame is accepted, so widening the packet is not breaking")
    func longerFrame() throws {
        let s = try #require(UBotStatus(sampleFrame + Data([0xAA, 0xBB])))
        #expect(s.wheelATurnsPerSec == 1.0)
    }

    @Test("a sliced Data decodes without trapping on its parent's indices")
    func slicedData() throws {
        let sliced = (Data([0xFF, 0xFF]) + sampleFrame).dropFirst(2)
        let s = try #require(UBotStatus(sliced))
        #expect(s.wheelATurnsPerSec == 1.0)
    }

    @Test("an unknown fault byte remains visible instead of failing the frame")
    func unknownFault() throws {
        var bytes = [UInt8](sampleFrame)
        bytes[1] = 99
        let s = try #require(UBotStatus(Data(bytes)))
        #expect(s.fault == .unknown)
    }

    @Test(arguments: [(UInt8(0), DriveFault.none), (1, .slip), (2, .encoder),
                      (3, .magnet), (4, .peer), (5, .driver), (6, .battery), (7, .blocked)])
    func faultEnumMatchesDriveH(raw: UInt8, expected: DriveFault) {
        #expect(DriveFault(rawValue: raw) == expected)
    }

    @Test("the robot-level faults read as the firmware names them")
    func newFaultTitles() throws {
        #expect(DriveFault.battery.title == "Battery empty")
        #expect(DriveFault.battery.detail
                == "The battery is below its cutoff. Charge or swap the pack; clear once the voltage recovers.")
        #expect(DriveFault.blocked.title == "Wheel blocked")
        #expect(!DriveFault.blocked.detail.isEmpty)
        var bytes = [UInt8](sampleFrame)
        bytes[0] |= 0b10
        bytes[1] = 6
        #expect(try #require(UBotStatus(Data(bytes))).fault == .battery)
    }
}

/// Bytes 13-19 as 0.2.9 and 0.3.0 append them to `sampleFrame`.
private func extended(flags2: UInt8, heatA: UInt8 = 0, heatB: UInt8 = 0, recoveries: UInt8 = 0,
                      battery: UInt8 = 1, derate: UInt8? = nil) -> Data {
    var tail: [UInt8] = [flags2, heatA, heatB, recoveries, battery]
    if let derate { tail += [derate, 0] }
    return sampleFrame + Data(tail)
}

@Suite("Status decode, 0.2.9 and 0.3.0 extensions")
struct ExtendedStatusTests {

    @Test("13 bytes: every extension field is absent, not zero")
    func oldFrame() throws {
        let s = try #require(UBotStatus(sampleFrame))
        #expect(s.frameLength == 13)
        #expect(s.flags2 == [])
        #expect(s.batteryState == nil)
        #expect(s.heatA == nil && s.heatB == nil)
        #expect(s.derateA == nil && s.derateB == nil && s.derateLevel == nil)
        #expect(s.recoveryCount == nil)
        #expect(!s.acceptsBoost)
    }

    @Test("18 bytes without bit 7: battery state only; the heat bytes are ignored")
    func v029() throws {
        let s = try #require(UBotStatus(extended(flags2: 0, heatA: 110, heatB: 99, recoveries: 5, battery: 2)))
        #expect(s.frameLength == 18)
        #expect(s.batteryState == .low)
        #expect(!s.acceptsBoost)
        #expect(s.heatA == nil && s.heatB == nil)
        #expect(s.recoveryCount == nil)
        #expect(s.derateA == nil)
        // Bytes 0-12 are untouched by the extension.
        #expect(s.isEnabled && s.wheelATurnsPerSec == 1.0 && s.commandedMetersPerSec == -0.250)
    }

    @Test(arguments: [(UInt8(0), BatteryState.none), (1, .ok), (2, .low), (3, .cutoff), (9, .unknown)])
    func batteryByte(raw: UInt8, expected: BatteryState) throws {
        let s = try #require(UBotStatus(extended(flags2: 0, battery: raw)))
        #expect(s.batteryState == expected)
    }

    @Test("20 bytes with bit 7: heat, recovery counter and derate levels decode")
    func v030() throws {
        let s = try #require(UBotStatus(extended(flags2: 0x80, heatA: 110, heatB: 55, recoveries: 7,
                                                 battery: 1, derate: 0b1110)))
        #expect(s.frameLength == 20)
        #expect(s.acceptsBoost)
        #expect(s.heatA == 1.10 && s.heatB == 0.55)
        #expect(s.recoveryCount == 7)
        #expect(s.derateA == 2 && s.derateB == 3)
        #expect(s.derateLevel == 3)
        #expect(s.batteryState == .ok)
    }

    @Test("each flags2 bit lands on its own flag")
    func flags2Bits() throws {
        let bits: [(UInt8, UBotStatus.Flags2)] = [
            (1 << 0, .boostActive), (1 << 1, .boostRequested), (1 << 2, .derated),
            (1 << 3, .heatLimited), (1 << 4, .otpw), (1 << 5, .recovering),
            (1 << 6, .loadValid), (1 << 7, .acceptsBoost),
        ]
        for (raw, flag) in bits {
            let s = try #require(UBotStatus(extended(flags2: raw, derate: 0)))
            #expect(s.flags2 == flag)
        }
        let all = try #require(UBotStatus(extended(flags2: 0xFF, derate: 0)))
        #expect(all.isBoosting && all.isDerated && all.isHeatLimited && all.isRecovering && all.acceptsBoost)
    }

    @Test("heat saturates at 255, i.e. 2.55")
    func heatSaturates() throws {
        let s = try #require(UBotStatus(extended(flags2: 0x80, heatA: 255, heatB: 0, derate: 0)))
        #expect(s.heatA == 2.55)
        #expect(s.heatB == 0)
    }

    @Test("18 bytes with bit 7 set: heat decodes, derate is absent rather than read past the end")
    func bit7Without19() throws {
        let s = try #require(UBotStatus(extended(flags2: 0x80, heatA: 50, heatB: 60, recoveries: 1)))
        #expect(s.heatA == 0.5 && s.heatB == 0.6)
        #expect(s.recoveryCount == 1)
        #expect(s.derateA == nil && s.derateB == nil)
    }

    @Test("14-17 bytes are no known layout: the core decodes, the extension is left alone")
    func partialExtension() throws {
        for extra in 1...4 {
            let s = try #require(UBotStatus(sampleFrame + Data(repeating: 0xFF, count: extra)))
            #expect(s.flags2 == [])
            #expect(s.batteryState == nil)
            #expect(s.wheelATurnsPerSec == 1.0)
        }
    }

    @Test("a frame wider than 20 bytes still decodes, so the next widening is not breaking")
    func widerFrame() throws {
        let s = try #require(UBotStatus(extended(flags2: 0x80, heatA: 10, derate: 1) + Data([0xAA, 0xBB])))
        #expect(s.frameLength == 22)
        #expect(s.derateA == 1)
        #expect(s.heatA == 0.1)
    }

    @Test("a sliced 20-byte frame decodes without trapping on its parent's indices")
    func slicedExtended() throws {
        let sliced = (Data([0xFF, 0xFF]) + extended(flags2: 0x80, heatA: 110, derate: 0b0100)).dropFirst(2)
        let s = try #require(UBotStatus(sliced))
        #expect(s.heatA == 1.10)
        #expect(s.derateB == 1)
    }
}

@Suite("Drive command encode")
struct DriveEncodeTests {

    @Test("the frame is always exactly four bytes")
    func length() {
        for v in stride(from: -1.5, through: 1.5, by: 0.25) {
            #expect(DriveCommand(v: v, w: -v).frame.count == 4)
        }
    }

    @Test("thousandths, little-endian, two's complement")
    func encoding() {
        #expect(DriveCommand(v: 0, w: 0).frame == Data([0, 0, 0, 0]))
        #expect(DriveCommand(v: 1, w: 0).frame == Data([0xE8, 0x03, 0x00, 0x00]))
        #expect(DriveCommand(v: -1, w: 0).frame == Data([0x18, 0xFC, 0x00, 0x00]))
        #expect(DriveCommand(v: 0, w: 1).frame == Data([0x00, 0x00, 0xE8, 0x03]))
    }

    @Test("out-of-range input clamps instead of wrapping")
    func clamping() {
        #expect(DriveCommand(v: 5, w: -5).frame == Data([0xE8, 0x03, 0x18, 0xFC]))
        #expect(DriveCommand(v: .infinity, w: 0).v == 1)
    }

    @Test("the boost frame is the 4-byte frame plus a flags byte, bit 0")
    func boostFrame() {
        for v in stride(from: -1.0, through: 1.0, by: 0.25) {
            let c = DriveCommand(v: v, w: -v / 2)
            #expect(c.frame(boost: true) == c.frame + Data([0x01]))
            #expect(c.frame(boost: false) == c.frame + Data([0x00]))
        }
        #expect(DriveCommand(v: 1, w: 0).frame(boost: true) == Data([0xE8, 0x03, 0x00, 0x00, 0x01]))
    }

    @Test("zero is still four zero bytes, byte for byte what every firmware has always taken")
    func zeroUnchanged() {
        #expect(DriveCommand.zero.frame == Data([0, 0, 0, 0]))
        #expect(DriveCommand.zero.frame(boost: true) == Data([0, 0, 0, 0, 1]))
    }
}

@Suite("Stick math")
struct StickTests {

    @Test("up is forward and left is anticlockwise, per joystick.html")
    func orientation() {
        let up = DriveCommand(stickX: 0, stickY: -1)
        #expect(up.v == 1)
        #expect(up.w == 0)

        let left = DriveCommand(stickX: -1, stickY: 0)
        #expect(left.v == 0)
        #expect(left.w == 1)

        let down = DriveCommand(stickX: 0, stickY: 1)
        #expect(down.v == -1)
    }

    @Test("a corner drag clamps onto the unit circle")
    func unitDisc() {
        let corner = DriveCommand(stickX: 1, stickY: 1)
        #expect(abs(corner.magnitude - 1) < 1e-9)
        #expect(abs(corner.v + 0.70710678) < 1e-6)
        #expect(abs(corner.w + 0.70710678) < 1e-6)
    }

    @Test("inside the disc the input passes through untouched")
    func insideDisc() {
        let c = DriveCommand(stickX: 0.3, stickY: -0.4)
        #expect(abs(c.v - 0.4) < 1e-9)
        #expect(abs(c.w + 0.3) < 1e-9)
    }
}

@Suite("Stick response")
struct StickResponseTests {

    private let r = StickResponse.standard

    @Test("full travel reaches full command in all four directions")
    func endpointsFixed() {
        for (x, y, v, w) in [(0.0, -1.0, 1.0, 0.0),
                              (0.0, 1.0, -1.0, 0.0),
                              (-1.0, 0.0, 0.0, 1.0),
                              (1.0, 0.0, 0.0, -1.0)] {
            let s = r.shape(x: x, y: y)
            let command = DriveCommand(stickX: s.x, stickY: s.y)
            #expect(command.v == v)
            #expect(command.w == w)
        }
    }

    @Test("standard response softens both axes and keeps reverse symmetric")
    func softCenter() {
        for (input, expected) in [(0.0, 0.0), (0.25, 0.109375),
                                  (0.5, 0.275), (0.75, 0.553125), (1.0, 1.0)] {
            for sign in [-1.0, 1.0] {
                #expect(abs(r.shape(x: sign * input, y: 0).x - sign * expected) < 1e-9)
                #expect(abs(r.shape(x: 0, y: sign * input).y - sign * expected) < 1e-9)
            }
        }
        let s = r.shape(x: 0.3, y: -0.4)
        let command = DriveCommand(stickX: s.x, stickY: s.y)
        #expect(abs(command.v - 0.1984) < 1e-9)
        #expect(abs(command.w + 0.1362) < 1e-9)
    }

    @Test("standard response increases smoothly from centre to full travel")
    func monotonic() {
        var previous = 0.0
        for step in 1...100 {
            let input = Double(step) / 100
            let output = r.shape(x: input, y: 0).x
            #expect(output > previous)
            #expect(output <= input)
            previous = output
        }
    }

    @Test("custom responses can still opt into expo and turn scaling")
    func customResponse() {
        let custom = StickResponse(expo: 0.6, turnScale: 0.5)
        #expect(abs(custom.shape(x: 0, y: -0.5).y + 0.275) < 1e-9)
        #expect(custom.shape(x: -1, y: 0).x == -0.5)
        #expect(custom.shape(x: 0, y: -1).y == -1)
    }

    @Test("the curve is odd, so it never flips a direction")
    func signPreserved() {
        for t in [0.1, 0.33, 0.5, 0.9, 1.0] {
            #expect(r.shape(x: 0, y: t).y == -r.shape(x: 0, y: -t).y)
        }
        #expect(r.shape(x: 0, y: 0) == (x: 0, y: 0))
    }

    @Test("a corner drag is clamped to the reachable rim")
    func clampsFirst() {
        // Off the far corner: onto the rim first, so it can never come back
        // with more authority than the edge of the pad.
        let corner = r.shape(x: 3, y: 3)
        let onRim = r.shape(x: 0.70710678, y: 0.70710678)
        #expect(abs(corner.x - onRim.x) < 1e-6)
        #expect(abs(corner.y - onRim.y) < 1e-6)
    }

    @Test("raw is the old linear behaviour")
    func rawIsIdentity() {
        let raw = StickResponse.raw
        #expect(abs(raw.shape(x: 0.3, y: -0.4).x - 0.3) < 1e-9)
        #expect(abs(raw.shape(x: 0.3, y: -0.4).y + 0.4) < 1e-9)
    }
}

@Suite("Lock model")
struct LockTests {

    private let ready = LinkState.ready(name: "ubot")

    @Test("motors off offers Enable")
    func motorsOff() {
        let lock = DriveLock.derive(linkState: ready, status: UBotStatus(flags: []))
        #expect(lock?.remedy == .enable)
    }

    @Test("faulted while enabled offers Clear")
    func faultedEnabled() {
        let s = UBotStatus(flags: [.enabled, .faulted], fault: .slip)
        #expect(DriveLock.derive(linkState: ready, status: s)?.remedy == .clearFaults)
    }

    @Test("faulted while disabled offers Enable, because enabling clears faults")
    func faultedDisabled() {
        let s = UBotStatus(flags: [.faulted], fault: .magnet)
        #expect(DriveLock.derive(linkState: ready, status: s)?.remedy == .enable)
    }

    @Test("enabled and healthy is unlocked")
    func healthy() {
        #expect(DriveLock.derive(linkState: ready, status: UBotStatus(flags: [.enabled])) == nil)
    }

    @Test("another controller driving does not lock us out")
    func foreignCommand() {
        let s = UBotStatus(flags: [.enabled, .commandActive])
        #expect(DriveLock.derive(linkState: ready, status: s) == nil)
    }

    @Test("stale telemetry locks even when the last status looked fine")
    func stalled() {
        let s = UBotStatus(flags: [.enabled])
        #expect(DriveLock.derive(linkState: .stalled(name: "ubot"), status: s) != nil)
    }

    @Test("every non-ready link state locks the stick")
    func everyDisconnectedStateLocks() {
        let states: [LinkState] = [.idle, .unsupported, .unauthorized, .bluetoothOff,
                                   .scanning, .connecting(name: "ubot"),
                                   .discovering(name: "ubot"), .reconnecting(name: "ubot"),
                                   .stalled(name: "ubot")]
        for state in states {
            #expect(DriveLock.derive(linkState: state, status: UBotStatus(flags: [.enabled])) != nil,
                    "\(state) should lock the stick")
        }
    }

    @Test("a ready link with no status yet still locks")
    func noStatusYet() {
        #expect(DriveLock.derive(linkState: ready, status: nil) != nil)
    }

    private func battery(_ state: BatteryState?, flags: UBotStatus.Flags,
                         fault: DriveFault = .battery) -> UBotStatus {
        var s = UBotStatus(flags: flags.union(.batteryPresent), fault: fault)
        s.batteryState = state
        return s
    }

    @Test("below the cutoff there is no remedy to offer, only the reason")
    func batteryCutoff() throws {
        // The firmware holds the wheels with the drivers on, faulted.
        let lock = try #require(DriveLock.derive(linkState: ready,
                                                 status: battery(.cutoff, flags: [.enabled, .faulted])))
        #expect(lock.reason == "Battery empty: charge or swap the pack")
        #expect(lock.remedy == .none)
        // Motors off makes no difference: enable is refused below the cutoff too.
        #expect(DriveLock.derive(linkState: ready,
                                 status: battery(.cutoff, flags: [.faulted]))?.remedy == DriveLock.Remedy.none)
    }

    @Test("a cutoff locks even before the battery fault has latched")
    func cutoffWithoutFault() {
        let s = battery(.cutoff, flags: [.enabled], fault: .none)
        #expect(DriveLock.derive(linkState: ready, status: s)
                == DriveLock(reason: "Battery empty: charge or swap the pack"))
    }

    @Test("once the voltage recovers, the fault is cleared the usual way")
    func batteryRecovered() {
        for state in [BatteryState.low, .ok] {
            #expect(DriveLock.derive(linkState: ready, status: battery(state, flags: [.enabled, .faulted]))?.remedy
                    == .clearFaults)
            #expect(DriveLock.derive(linkState: ready, status: battery(state, flags: [.faulted]))?.remedy
                    == .enable)
        }
    }

    @Test("a battery fault from firmware that reports no state falls back to Clear")
    func batteryFaultWithoutState() {
        #expect(DriveLock.derive(linkState: ready, status: battery(nil, flags: [.enabled, .faulted]))?.remedy
                == .clearFaults)
    }

    @Test("a low battery is a warning, not a lock")
    func batteryLow() {
        #expect(DriveLock.derive(linkState: ready, status: battery(.low, flags: [.enabled], fault: .none)) == nil)
    }
}

@Suite("Control ops")
struct ControlOpTests {

    @Test("op bytes match ble.c")
    func rawValues() {
        #expect(ControlOp.stop.rawValue == 0)
        #expect(ControlOp.enable.rawValue == 1)
        #expect(ControlOp.disable.rawValue == 2)
        #expect(ControlOp.estop.rawValue == 3)
        #expect(ControlOp.clearFaults.rawValue == 4)
    }

    @Test("every op frames to exactly one byte")
    func frames() {
        for op in ControlOp.allCases {
            #expect(op.frame.count == 1)
            #expect(op.frame[0] == op.rawValue)
        }
    }
}
