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

    static func drive(_ command: DriveCommand) -> String {
        // DriveCommand already clamps inputs; reject non-finite values as zero.
        let v = command.v.isFinite ? command.v : 0
        let w = command.w.isFinite ? command.w : 0
        return "{\"t\":\"drive\",\"v\":\(v),\"w\":\(w),\"hold\":500}"
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

    struct Status: Decodable {
        struct Command: Decodable { let v: Double; let w: Double; let active: Bool }
        struct Battery: Decodable { let present: Bool; let v: Double; let pct: Int }
        struct Wheel: Decodable { let name: String; let vel: Double; let enc: Bool; let fault: UInt8 }
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
            let code = fault_wheel == "A" ? a.fault : b.fault
            let fault: DriveFault = faulted ? (code == 0 ? .unknown : DriveFault(rawValue: code) ?? .unknown) : .none
            var result = UBotStatus(flags: flags, fault: fault,
                batteryMillivolts: UInt16(min(65535, max(0, batt.v * 1000))),
                batteryPercent: UInt8(clamping: max(0, min(100, batt.pct))),
                wheelATurnsPerSec: a.vel, wheelBTurnsPerSec: b.vel,
                commandedMetersPerSec: cmd.v, commandedRadiansPerSec: cmd.w)
            if ota?.busy == true { result.busyReason = "Firmware update in progress" }
            else if cal == true { result.busyReason = "Calibration in progress" }
            else if demo != nil { result.busyReason = "Demo in progress" }
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
