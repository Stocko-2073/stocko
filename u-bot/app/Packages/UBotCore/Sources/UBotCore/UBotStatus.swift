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
    /// Robot-level, not a wheel's: the battery went below its cutoff. The
    /// Wi-Fi status names no wheel for it (`fault_wheel` is "-").
    case battery = 6
    /// Phase 3: the load-angle limiter held a wheel back for 3 s. No steps
    /// were lost, which is what makes it a different fault from a slip.
    case blocked = 7
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
        case .battery: return "Battery empty"
        case .blocked: return "Wheel blocked"
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
        case .battery:
            return "The battery is below its cutoff. Charge or swap the pack; "
                 + "clear once the voltage recovers."
        case .blocked:
            return "A wheel was held back at its torque limit for 3 seconds without slipping. "
                 + "Clear the obstruction, then clear the fault."
        }
    }
}

/// `battery_state()` in the firmware's battery component, from 0.2.9.
///
/// Only the robot knows its pack and thresholds (`batt_pack`, `batt_warn_v`,
/// `batt_cut_v`), and it applies time filters and hysteresis the phone cannot
/// see, so the app never derives this from volts or percent itself.
public enum BatteryState: UInt8, Sendable, CaseIterable {
    /// No battery sense. Never stops the robot.
    case none = 0
    case ok = 1
    /// 10 s below the warning voltage. Still drivable.
    case low = 2
    /// Below the cutoff. The robot has stopped and refuses enable and clear
    /// until the voltage recovers.
    case cutoff = 3
    /// A value this app does not know. Shown, never acted on.
    case unknown = 255

    /// The Wi-Fi status spells it out: `batt.state`.
    public init(wireName: String) {
        switch wireName {
        case "none":   self = .none
        case "ok":     self = .ok
        case "low":    self = .low
        case "cutoff": self = .cutoff
        default:       self = .unknown
        }
    }

    public var name: String {
        switch self {
        case .none:    return "none"
        case .ok:      return "ok"
        case .low:     return "low"
        case .cutoff:  return "cutoff"
        case .unknown: return "unknown"
        }
    }
}

/// The status frame notified at 5 Hz on `7B1A0003`.
///
/// `status_packet_t` in ble.c is `__attribute__((packed))`, laid out
/// little-endian. Bytes 0-12 have never changed:
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
/// Firmware 0.2.9 appends five bytes (18 in all) and 0.3.0 two more (20, the
/// payload a default-MTU notification carries):
///
///     13      u8    flags2      see `Flags2`
///     14      u8    heat_a      round(h x 100), saturating at 255      (b7)
///     15      u8    heat_b                                              (b7)
///     16      u8    recoveries  wraps; +1 per stall recovery attempt    (b7)
///     17      u8    batt_state  `BatteryState`, whenever the frame has it
///     18      u8    derate      bits 0-1 wheel A, bits 2-3 wheel B      (b7)
///     19      u8    reserved
///
/// The fields marked (b7) are only meaningful when flags2 bit 7 is set, so
/// they decode to nil without it. Older firmware sends 13 bytes and every
/// extension field decodes to nil or empty.
///
/// Note the asymmetry in the last four core fields: `vel_a`/`vel_b` are what
/// the wheels are actually doing, `v_mmps`/`w_mradps` are what the robot has
/// been told to do. Showing both is the only way the operator can see "I asked
/// for 0.4 m/s and nothing is turning", which matters because a refused drive
/// write still returns success over BLE.
public struct UBotStatus: Equatable, Sendable {

    /// The shortest frame that decodes. `vel_a` starts at byte 5 -- an odd
    /// offset. Loading an `Int16` from there through an unsafe pointer is
    /// undefined behaviour on a misaligned address, so this type is always
    /// decoded with explicit byte shifts.
    public static let byteCount = 13

    /// 0.2.9's frame: flags2 through the battery state.
    public static let batteryStateByteCount = 18

    /// 0.3.0's frame: adds the derate levels and a reserved byte.
    public static let torqueByteCount = 20

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

    /// Byte 13. Over Wi-Fi the same bits are rebuilt from `caps` and the
    /// per-wheel `torque` and `rec` objects, so the app reads one shape.
    public struct Flags2: OptionSet, Sendable, Equatable {
        public let rawValue: UInt8
        public init(rawValue: UInt8) { self.rawValue = rawValue }

        /// Boost granted on either wheel, for any reason -- the operator's,
        /// or the firmware's own start or recovery boost.
        public static let boostActive    = Flags2(rawValue: 1 << 0)
        /// The operator's manual boost is being requested (drive frames carry
        /// the flag). Granted or not.
        public static let boostRequested = Flags2(rawValue: 1 << 1)
        /// Either wheel's driver is at a reduced current because of OTPW.
        public static let derated        = Flags2(rawValue: 1 << 2)
        /// The thermal model has paused boost until the motors cool.
        public static let heatLimited    = Flags2(rawValue: 1 << 3)
        /// A driver's 120 C pre-warning is set right now.
        public static let otpw           = Flags2(rawValue: 1 << 4)
        /// A stall recovery is in progress (Phase 2).
        public static let recovering     = Flags2(rawValue: 1 << 5)
        /// The load-angle estimate is trusted (Phase 3).
        public static let loadValid      = Flags2(rawValue: 1 << 6)
        /// The firmware accepts 5-byte drive frames, and bytes 14-16 and 18
        /// are valid. Nothing may send a 5-byte frame until this has been seen:
        /// older firmware rejects the length.
        public static let acceptsBoost   = Flags2(rawValue: 1 << 7)
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

    // MARK: Extension fields
    //
    // Each has a default so that the initialiser below, and every call to it,
    // stays exactly as it was before these existed.

    /// Bytes on the wire, or nil when this did not come from a BLE frame.
    public var frameLength: Int? = nil
    public var flags2: Flags2 = []
    /// nil when the firmware does not report it (before 0.2.9).
    public var batteryState: BatteryState? = nil
    /// `li5s` or `lfp4s`. Wi-Fi only.
    public var batteryPack: String? = nil
    /// Normalised motor heat from the firmware's thermal model: 1.0 is the
    /// steady state at rated current. BLE saturates at 2.55.
    public var heatA: Double? = nil
    public var heatB: Double? = nil
    /// OTPW derate level, 0 (none) to 3 (half current).
    public var derateA: Int? = nil
    public var derateB: Int? = nil
    /// Counts stall recovery attempts and wraps at 256. Only a change means
    /// anything; the absolute value is arbitrary.
    public var recoveryCount: UInt8? = nil
    /// The wheels in the current recovery, bit 0 A and bit 1 B. Wi-Fi only;
    /// BLE does not say which wheel slipped.
    public var recoveryWheels: UInt8? = nil

    public var isEnabled: Bool       { flags.contains(.enabled) }
    public var isFaulted: Bool       { flags.contains(.faulted) }
    public var isCommandActive: Bool { flags.contains(.commandActive) }
    public var encoderAOK: Bool      { flags.contains(.encoderAOK) }
    public var encoderBOK: Bool      { flags.contains(.encoderBOK) }

    /// Flags2 bit 7 over BLE, `"boost"` in the Wi-Fi caps. Firmware 0.3.0 on.
    public var acceptsBoost: Bool    { flags2.contains(.acceptsBoost) }
    public var isBoosting: Bool      { flags2.contains(.boostActive) }
    public var isDerated: Bool       { flags2.contains(.derated) }
    public var isHeatLimited: Bool   { flags2.contains(.heatLimited) }
    public var isRecovering: Bool    { flags2.contains(.recovering) }

    /// The worse of the two wheels, or nil when neither is reported.
    public var derateLevel: Int? {
        if derateA == nil && derateB == nil { return nil }
        return max(derateA ?? 0, derateB ?? 0)
    }

    /// The divider on GPIO1 is not wired on every build. When this is `false`
    /// the millivolts and percent below are meaningless. Never render them as
    /// a reading when this is false -- show "not sensed", the way the web
    /// joystick does.
    public var batteryIsSensed: Bool { flags.contains(.batteryPresent) }
    public var batteryVolts: Double  { Double(batteryMillivolts) / 1000 }

    public init?(_ data: Data) {
        guard data.count >= Self.byteCount else { return nil }

        // Normalise the indices. A `Data` produced by slicing keeps its
        // parent's `startIndex`, so `data[0]` on a slice traps at runtime --
        // and slices are exactly what parts of CoreBluetooth hand back.
        let b = [UInt8](data)

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
        frameLength            = b.count

        // The extension is trusted only when it is all there. No firmware
        // sends 14-17 bytes; a frame that does is not one this decoder knows.
        guard b.count >= Self.batteryStateByteCount else { return }
        flags2       = Flags2(rawValue: b[13])
        batteryState = BatteryState(rawValue: b[17]) ?? .unknown

        // 0.2.9 sends these bytes too, but with bit 7 clear they carry nothing.
        guard flags2.contains(.acceptsBoost) else { return }
        heatA         = Double(b[14]) / 100
        heatB         = Double(b[15]) / 100
        recoveryCount = b[16]
        if b.count > 18 {
            derateA = Int(b[18] & 0b11)
            derateB = Int((b[18] >> 2) & 0b11)
        }
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
