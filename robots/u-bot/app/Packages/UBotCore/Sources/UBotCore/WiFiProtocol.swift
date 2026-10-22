import Foundation

public enum ConnectionTransport: String, CaseIterable, Sendable {
    case ble, wifi
    public var title: String { self == .ble ? "BLE" : "Wi-Fi" }
}

public enum WiFiProtocol {
    /// A local hostname/IP, optionally followed by a port. Paths and credentials
    /// are intentionally not accepted: the firmware endpoint is always /ws.
    public static func endpoint(_ address: String) -> URL? {
        let host = address.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !host.isEmpty, !host.contains(where: { $0.isWhitespace }),
              !host.contains("/"), !host.contains("?"), !host.contains("#"),
              !host.contains("@"),
              var c = URLComponents(string: "ws://" + host),
              let name = c.host, !name.isEmpty,
              c.port == nil || (1...65535).contains(c.port!) else { return nil }
        c.path = "/ws"
        return c.url
    }

    static func drive(_ command: DriveCommand, boost: Bool = false) -> String {
        // DriveCommand already clamps inputs; reject non-finite values as zero.
        let v = command.v.isFinite ? command.v : 0
        let w = command.w.isFinite ? command.w : 0
        // Firmware before 0.3.0 ignores keys it does not know, so unlike the
        // BLE frame this needs no capability check. The key is left out, not
        // sent as false, so that every frame without Boost stays exactly what
        // it always was.
        return "{\"t\":\"drive\",\"v\":\(v),\"w\":\(w),\"hold\":500" + (boost ? ",\"boost\":true}" : "}")
    }

    static func command(_ op: ControlOp) -> String {
        switch op {
        case .stop: return "stop"
        case .enable: return "enable"
        case .disable: return "disable"
        case .estop: return "estop"
        case .clearFaults: return "clear"
        }
    }

    /// The fields of `ws.c`'s status the app uses. Everything else in the
    /// frame is ignored, so the firmware can add fields freely.
    ///
    /// The fields up to `ota` are what every firmware sends and are required:
    /// without them the frame is dropped. The rest arrived with 0.2.9 and later
    /// and are `@Lenient`, so their absence -- or a firmware bug in one of them
    /// -- costs only that field, never the frame.
    struct Status: Decodable {
        struct Command: Decodable { let v: Double; let w: Double; let active: Bool }
        struct Battery: Decodable {
            let present: Bool; let v: Double; let pct: Int
            @Lenient var state: String?     // none | ok | low | cutoff (0.2.9)
            @Lenient var pack: String?      // li5s | lfp4s (0.2.9)
        }
        /// Per wheel, from 0.3.0. Current, hold and lag fields are not used.
        struct Torque: Decodable {
            let boost: Int?     // reasons: 1 manual, 2 start, 4 recovery, 8 load
            let act: Bool?      // boost granted
            let h: Double?      // normalised heat
            let hot: Bool?      // heat-limited
            let derate: Int?    // 0-3
            let otpw: Bool?
        }
        /// Stall recovery, from Phase 2. Only what the app acts on.
        struct Recovery: Decodable {
            let state: String?  // idle | lock | ramp
            let wheels: Int?    // bit 0 A, bit 1 B
            let n: Int?         // attempts, the same count as BLE byte 16
        }
        struct Wheel: Decodable {
            let name: String; let vel: Double; let enc: Bool; let fault: UInt8
            @Lenient var torque: Torque?
            @Lenient var load: Double?      // degrees; null until the estimate is trusted
        }
        struct OTA: Decodable { let busy: Bool }
        let t: String
        let name: String
        let fw: String
        let enabled: Bool
        let faulted: Bool
        let fault_wheel: String
        let cmd: Command
        let batt: Battery
        let wheels: [Wheel]
        let cal: Bool?
        let demo: String?
        let ota: OTA?
        @Lenient var fault_code: Int?
        @Lenient var caps: [String]?
        @Lenient var rec: Recovery?

        func model() -> UBotStatus? {
            guard t == "status", let a = wheels.first(where: { $0.name == "A" }),
                  let b = wheels.first(where: { $0.name == "B" }),
                  [a.vel, b.vel, cmd.v, cmd.w, batt.v].allSatisfy({ $0.isFinite }) else { return nil }
            var flags: UBotStatus.Flags = []
            if enabled { flags.insert(.enabled) }
            if faulted { flags.insert(.faulted) }
            if cmd.active { flags.insert(.commandActive) }
            if a.enc { flags.insert(.encoderAOK) }
            if b.enc { flags.insert(.encoderBOK) }
            if batt.present { flags.insert(.batteryPresent) }
            // A robot-level fault such as the battery belongs to no wheel
            // (`fault_wheel` is "-"), so newer firmware sends the code itself,
            // and it wins over looking the code up on a wheel.
            let code = fault_code.map { UInt8(clamping: $0) }
                ?? (fault_wheel == "A" ? a.fault : fault_wheel == "B" ? b.fault : 0)
            let fault: DriveFault = faulted ? (code == 0 ? .unknown : DriveFault(rawValue: code) ?? .unknown) : .none
            var result = UBotStatus(flags: flags, fault: fault,
                batteryMillivolts: UInt16(min(65535, max(0, batt.v * 1000))),
                batteryPercent: UInt8(clamping: max(0, min(100, batt.pct))),
                wheelATurnsPerSec: a.vel, wheelBTurnsPerSec: b.vel,
                commandedMetersPerSec: cmd.v, commandedRadiansPerSec: cmd.w)
            if ota?.busy == true { result.busyReason = "Firmware update in progress" }
            else if cal == true { result.busyReason = "Calibration in progress" }
            else if demo != nil { result.busyReason = "Demo in progress" }

            // Rebuild the BLE flags2 byte, so nothing downstream cares which
            // transport the status came from.
            let torque = [a.torque, b.torque].compactMap { $0 }
            var flags2: UBotStatus.Flags2 = []
            if caps?.contains("boost") == true             { flags2.insert(.acceptsBoost) }
            if torque.contains(where: { $0.act == true })  { flags2.insert(.boostActive) }
            if torque.contains(where: { ($0.boost ?? 0) & 1 != 0 }) { flags2.insert(.boostRequested) }
            if torque.contains(where: { ($0.derate ?? 0) > 0 })     { flags2.insert(.derated) }
            if torque.contains(where: { $0.hot == true })  { flags2.insert(.heatLimited) }
            if torque.contains(where: { $0.otpw == true }) { flags2.insert(.otpw) }
            if let state = rec?.state, state != "idle"     { flags2.insert(.recovering) }
            if a.load != nil || b.load != nil              { flags2.insert(.loadValid) }
            result.flags2 = flags2

            result.batteryState = batt.state.map(BatteryState.init(wireName:))
            result.batteryPack = batt.pack
            result.heatA = a.torque?.h
            result.heatB = b.torque?.h
            result.derateA = a.torque?.derate.map { min(3, max(0, $0)) }
            result.derateB = b.torque?.derate.map { min(3, max(0, $0)) }
            // Truncated to the BLE counter's width, so both wrap the same way.
            result.recoveryCount = rec?.n.map { UInt8(truncatingIfNeeded: $0) }
            result.recoveryWheels = rec?.wheels.map { UInt8(truncatingIfNeeded: $0) }
            return result
        }
    }

    struct Envelope: Decodable {
        let t: String
        let cmd: String?
        let ok: Bool?
        let err: String?
    }
}

/// A status field from newer firmware. Absent, null, or the wrong shape all
/// decode to nil rather than failing the frame. Status is what keeps the stick
/// live over Wi-Fi -- a frame that fails to decode is a frame that never
/// arrived, and 1.5 s of those drops the link -- so a firmware bug in a
/// telemetry field must never be able to make the robot undrivable.
@propertyWrapper
struct Lenient<Value: Decodable>: Decodable {
    var wrappedValue: Value?
    init(wrappedValue: Value?) { self.wrappedValue = wrappedValue }
    init(from decoder: Decoder) throws {
        wrappedValue = try? decoder.singleValueContainer().decode(Value.self)
    }
}

extension KeyedDecodingContainer {
    /// The synthesised `init(from:)` calls this for a `@Lenient` property. A
    /// missing key is nil here, where the generic overload would throw.
    func decode<Value>(_ type: Lenient<Value>.Type, forKey key: Key) throws -> Lenient<Value> {
        try decodeIfPresent(type, forKey: key) ?? Lenient(wrappedValue: nil)
    }
}
