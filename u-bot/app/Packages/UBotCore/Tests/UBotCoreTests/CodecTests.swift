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

    @Test("an unknown fault byte degrades to none instead of failing the frame")
    func unknownFault() throws {
        var bytes = [UInt8](sampleFrame)
        bytes[1] = 99
        let s = try #require(UBotStatus(Data(bytes)))
        #expect(s.fault == .none)
    }

    @Test(arguments: [(UInt8(0), DriveFault.none), (1, .slip), (2, .encoder),
                      (3, .magnet), (4, .peer)])
    func faultEnumMatchesDriveH(raw: UInt8, expected: DriveFault) {
        #expect(DriveFault(rawValue: raw) == expected)
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

    @Test("expo keeps full deflection at full output")
    func endpointsFixed() {
        let up = r.shape(x: 0, y: -1)
        #expect(abs(up.y + 1) < 1e-9)
        #expect(DriveCommand(stickX: up.x, stickY: up.y).v == 1)
    }

    @Test("half a thumb commands well under half rate")
    func centreIsFiner() {
        // 0.6 * 0.125 + 0.4 * 0.5 -- the whole point of the curve.
        #expect(abs(r.shape(x: 0, y: -0.5).y + 0.275) < 1e-9)
    }

    @Test("turn authority is scaled but forward is not")
    func turnScaled() {
        #expect(abs(r.shape(x: -1, y: 0).x + 0.5) < 1e-9)
        #expect(abs(r.shape(x: 0, y: -1).y + 1) < 1e-9)
    }

    @Test("the curve is odd, so it never flips a direction")
    func signPreserved() {
        for t in [0.1, 0.33, 0.5, 0.9, 1.0] {
            #expect(r.shape(x: 0, y: t).y == -r.shape(x: 0, y: -t).y)
        }
        #expect(r.shape(x: 0, y: 0) == (x: 0, y: 0))
    }

    @Test("a corner drag is clamped before it is curved")
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
