import Foundation

/// Where the connection is. Everything the operator sees about connectivity is
/// derived from this one value.
public enum LinkState: Equatable, Sendable {
    case idle
    case failed(reason: String)
    case unsupported
    case unauthorized
    case bluetoothOff
    case scanning
    case connecting(name: String)
    case discovering(name: String)
    case ready(name: String)
    /// Connected, but the 5 Hz status has gone quiet. Usually the
    /// `s_status_subscribed` quirk; sometimes a wedged robot.
    case stalled(name: String)
    case reconnecting(name: String)

    public var isReady: Bool { if case .ready = self { return true }; return false }

    public var robotName: String? {
        switch self {
        case .connecting(let n), .discovering(let n),
             .ready(let n), .stalled(let n), .reconnecting(let n):
            return n
        default:
            return nil
        }
    }

    /// What the connection pill says.
    public var summary: String {
        switch self {
        case .failed:       return "Connection failed"
        case .idle:         return "Not connected"
        case .unsupported:  return "No Bluetooth LE"
        case .unauthorized: return "Bluetooth not allowed"
        case .bluetoothOff: return "Bluetooth off"
        case .scanning:     return "Looking\u{2026}"
        case .connecting:   return "Connecting\u{2026}"
        case .discovering:  return "Connecting\u{2026}"
        case .ready:        return "Connected"
        case .stalled:      return "No data"
        case .reconnecting: return "Link lost"
        }
    }
}

/// Everything the transport tells the app. One stream, so ordering is obvious.
public enum LinkEvent: Sendable {
    case state(LinkState)
    case status(UBotStatus)
    case batteryLevel(UInt8)
    case firmware(String)
    case model(String)
    case controlAccepted(ControlOp)
    case controlRefused(ControlOp, String)
    case message(String)
    /// Emitted once a second while driving: written, dropped for backpressure,
    /// escalated to an acknowledged write. The early warning that the
    /// connection interval has gone bad.
    case linkQuality(written: Int, dropped: Int, escalated: Int)
}

/// The seam between the UI and the radio. `BLERobotLink` talks to a real robot;
/// `MockRobotLink` fakes one so the whole interface can be built and every
/// state screenshotted in the Simulator, where CoreBluetooth reports
/// `.unsupported`.
public protocol RobotLink: AnyObject {
    /// Called on an arbitrary queue. The app hops to the main actor itself.
    var onEvent: (@Sendable (LinkEvent) -> Void)? { get set }

    func start()
    func stop()

    /// Finger down on the stick.
    func engage(_ command: DriveCommand)
    /// Finger moved. Coalesced -- the next tick sends the newest value.
    func update(_ command: DriveCommand)
    /// Finger up, lock engaged, app resigned active, telemetry went stale.
    /// Sends a zero immediately plus a short tail.
    func releaseStick()

    func send(_ op: ControlOp)
    func executeManagement(_ args: [String], completion: @escaping ManagementCompletion)
}

public extension RobotLink {
    func executeManagement(_ args: [String], completion: @escaping ManagementCompletion) {
        completion(.failure(.unavailable))
    }
}
