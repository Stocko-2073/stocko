import Foundation

/// Why the stick is not live, and what the operator can do about it.
///
/// This is `lock(why)` from `joystick.html`: a single nullable reason. Non-nil
/// means grey the pad, show the reason, refuse to send, and toast the reason if
/// the operator grabs it anyway. The robot never receives a drive it would
/// refuse, which matters because a refused drive write still returns success
/// over BLE -- silence is not confirmation.
public struct DriveLock: Equatable, Sendable {

    public enum Remedy: Equatable, Sendable {
        case none
        case enable
        case clearFaults
        case openSettings
    }

    public let reason: String
    public let remedy: Remedy

    public init(reason: String, remedy: Remedy = .none) {
        self.reason = reason
        self.remedy = remedy
    }

    /// Derive the lock from the link state and the latest status frame.
    ///
    /// Adapted honestly to what BLE actually carries: the 13-byte frame has no
    /// `cal_busy`, no `demo_running`, no per-wheel `driver_ok` and no
    /// `fault_wheel`, all of which the WebSocket status has and the web page
    /// locks on. So a calibration or a demo cannot be locked out proactively
    /// here -- an `enable` during one comes back as ATT 0x0E instead, and the
    /// refusal is surfaced reactively.
    public static func derive(linkState: LinkState, status: UBotStatus?) -> DriveLock? {
        switch linkState {
        case .bluetoothOff:
            return .init(reason: "Bluetooth is off", remedy: .openSettings)
        case .unauthorized:
            return .init(reason: "U-BOT cannot use Bluetooth", remedy: .openSettings)
        case .unsupported:
            return .init(reason: "No Bluetooth LE on this device")
        case .idle:
            return .init(reason: "Not connected")
        case .scanning:
            return .init(reason: "Looking for the robot")
        case .connecting, .discovering:
            return .init(reason: "Connecting\u{2026}")
        case .reconnecting:
            return .init(reason: "Link lost, reconnecting\u{2026}")
        case .stalled:
            return .init(reason: "No data from the robot")
        case .ready:
            break
        }

        guard let s = status else {
            return .init(reason: "Waiting for status")
        }

        // A latched fault. `drive_enable` also clears faults, so when the
        // motors are off the single remedy is Enable -- same branch the web
        // page takes when it says "Enabling the motors clears it."
        if s.isFaulted {
            return s.isEnabled
                ? .init(reason: "Clear the fault to drive", remedy: .clearFaults)
                : .init(reason: "Enable the motors to drive", remedy: .enable)
        }
        if !s.isEnabled {
            return .init(reason: "Enable the motors to drive", remedy: .enable)
        }

        // Deliberately NOT locked when another controller holds a command.
        // joystick.html leaves the lock null there and offers a Stop button
        // instead; taking the stick should be allowed to override.
        return nil
    }
}
