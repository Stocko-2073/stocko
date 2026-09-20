import Foundation

/// `drive_fault_t` from `components/drive/include/drive.h`. The sentences come
/// from `StepperServo::faultName()` so the phone says what the console says.
public enum DriveFault: UInt8, Sendable, CaseIterable {
    case none = 0
    case slip = 1
    case encoder = 2
    case magnet = 3
    case peer = 4
    case driver = 5
    case unknown = 255

    public var title: String {
        switch self {
        case .driver:  return "Motor driver"
        case .unknown: return "Unknown fault"
        case .none:    return "No fault"
        case .slip:    return "Slip"
        case .encoder: return "Encoder"
        case .magnet:  return "Magnet"
        case .peer:    return "Stopped with the other wheel"
        }
    }

    public var detail: String {
        switch self {
        case .driver:
            return "A motor driver reported a power, communication, or temperature fault."
        case .unknown:
            return "The robot reported a fault this app does not recognize."
        case .none:
            return ""
        case .slip:
            return "A wheel was commanded to move and the shaft did not follow. "
                 + "Stalled, pushed, current too low, or the shaft polarity is backwards."
        case .encoder:
            return "An encoder stopped answering on the bus."
        case .magnet:
            return "An encoder reports no magnet."
        case .peer:
            return "The other wheel faulted, so this one was stopped too."
        }
    }
}

/// The 13-byte status frame notified at 5 Hz on `7B1A0003`.
///
/// `status_packet_t` in ble.c is `__attribute__((packed))`, laid out
/// little-endian:
///
///     offset  type  field
///     0       u8    flags
///     1       u8    fault       drive_fault_t of the faulting wheel, else 0
///     2       u16   batt_mv
///     4       u8    batt_pct
///     5       i16   vel_a       MEASURED, output turns/s x1000
///     7       i16   vel_b       MEASURED, output turns/s x1000
///     9       i16   v_mmps      COMMAND IN FORCE, m/s x1000
///     11      i16   w_mradps    COMMAND IN FORCE, rad/s x1000
///
/// Note the asymmetry in the last four fields: `vel_a`/`vel_b` are what the
/// wheels are actually doing, `v_mmps`/`w_mradps` are what the robot has been
/// told to do. Showing both is the only way the operator can see "I asked for
/// 0.4 m/s and nothing is turning", which matters because a refused drive write
/// still returns success over BLE.
public struct UBotStatus: Equatable, Sendable {

    /// `vel_a` starts at byte 5 -- an odd offset. Loading an `Int16` from there
    /// through an unsafe pointer is undefined behaviour on a misaligned
    /// address, so this type is always decoded with explicit byte shifts.
    public static let byteCount = 13

    public struct Flags: OptionSet, Sendable, Equatable {
        public let rawValue: UInt8
        public init(rawValue: UInt8) { self.rawValue = rawValue }

        public static let enabled        = Flags(rawValue: 1 << 0)
        public static let faulted        = Flags(rawValue: 1 << 1)
        public static let commandActive  = Flags(rawValue: 1 << 2)
        public static let encoderAOK     = Flags(rawValue: 1 << 3)
        public static let encoderBOK     = Flags(rawValue: 1 << 4)
        public static let batteryPresent = Flags(rawValue: 1 << 5)
    }

    public var busyReason: String? = nil

    public let flags: Flags
    public let fault: DriveFault
    public let batteryMillivolts: UInt16
    public let batteryPercent: UInt8

    /// Measured output-shaft velocity, turns per second.
    public let wheelATurnsPerSec: Double
    public let wheelBTurnsPerSec: Double

    /// The command the robot is currently holding, in real units.
    public let commandedMetersPerSec: Double
    public let commandedRadiansPerSec: Double

    public var isEnabled: Bool       { flags.contains(.enabled) }
    public var isFaulted: Bool       { flags.contains(.faulted) }
    public var isCommandActive: Bool { flags.contains(.commandActive) }
    public var encoderAOK: Bool      { flags.contains(.encoderAOK) }
    public var encoderBOK: Bool      { flags.contains(.encoderBOK) }

    /// The 11:1 divider on GPIO1 is not wired on the current build, so this is
    /// `false` and the millivolts and percent below are meaningless. Never
    /// render them as a reading when this is false -- show "not sensed", the
    /// way the web joystick does.
    public var batteryIsSensed: Bool { flags.contains(.batteryPresent) }
    public var batteryVolts: Double  { Double(batteryMillivolts) / 1000 }

    public init?(_ data: Data) {
        guard data.count >= Self.byteCount else { return nil }

        // Normalise the indices. A `Data` produced by slicing keeps its
        // parent's `startIndex`, so `data[0]` on a slice traps at runtime --
        // and slices are exactly what parts of CoreBluetooth hand back.
        let b = [UInt8](data.prefix(Self.byteCount))

        func u16(_ i: Int) -> UInt16 { UInt16(b[i]) | (UInt16(b[i + 1]) << 8) }
        func i16(_ i: Int) -> Int16 { Int16(bitPattern: u16(i)) }

        flags                  = Flags(rawValue: b[0])
        fault                  = DriveFault(rawValue: b[1]) ?? .unknown
        batteryMillivolts      = u16(2)
        batteryPercent         = b[4]
        wheelATurnsPerSec      = Double(i16(5))  / 1000
        wheelBTurnsPerSec      = Double(i16(7))  / 1000
        commandedMetersPerSec  = Double(i16(9))  / 1000
        commandedRadiansPerSec = Double(i16(11)) / 1000
    }

    /// Used by the mock link and by tests.
    public init(flags: Flags,
                fault: DriveFault = .none,
                batteryMillivolts: UInt16 = 0,
                batteryPercent: UInt8 = 0,
                wheelATurnsPerSec: Double = 0,
                wheelBTurnsPerSec: Double = 0,
                commandedMetersPerSec: Double = 0,
                commandedRadiansPerSec: Double = 0) {
        self.flags = flags
        self.fault = fault
        self.batteryMillivolts = batteryMillivolts
        self.batteryPercent = batteryPercent
        self.wheelATurnsPerSec = wheelATurnsPerSec
        self.wheelBTurnsPerSec = wheelBTurnsPerSec
        self.commandedMetersPerSec = commandedMetersPerSec
        self.commandedRadiansPerSec = commandedRadiansPerSec
    }
}
