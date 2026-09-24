import Foundation

public enum DriveSetting: String, CaseIterable, Sendable, Identifiable {
    case topSpeed = "vmax_tps"
    case acceleration = "accel_tps2"
    case braking = "decel_tps2"

    public var id: String { rawValue }
    public var title: String {
        switch self {
        case .topSpeed: return "Top speed"
        case .acceleration: return "Acceleration"
        case .braking: return "Braking"
        }
    }
    public var unit: String { self == .topSpeed ? "turns/s" : "turns/s²" }
    // Matches drive_setting_set(), not the separate per-wheel tuning commands.
    public var range: ClosedRange<Double> {
        switch self {
        case .topSpeed: return 0.05...2
        case .acceleration: return 0.5...20
        case .braking: return 0.2...20
        }
    }
    public var detail: String {
        switch self {
        case .topSpeed: return "Maximum wheel speed at full stick."
        case .acceleration: return "How quickly wheel speed increases. Lower values give gentler starts."
        case .braking: return "How quickly wheel speed decreases. Higher values stop more quickly."
        }
    }
    public func accepts(_ value: Double) -> Bool { value.isFinite && range.contains(value) }
    public func display(_ value: Double) -> String {
        value.formatted(.number.precision(.significantDigits(1...6)).grouping(.never))
    }
    /// Firmware prints effective settings with %g (six significant digits).
    public func matchesReadback(_ reported: Double, requested: Double) -> Bool {
        accepts(reported) && accepts(requested)
            && abs(reported - requested) <= max(0.000001, abs(requested) * 0.000005)
    }
}

public struct DriveSettings: Equatable, Sendable {
    private let values: [DriveSetting: Double]
    public subscript(_ setting: DriveSetting) -> Double { values[setting]! }

    /// Read effective values, not NVS overrides (which may omit defaults).
    public init(output: String) throws {
        guard let line = output.split(separator: "\n").first(where: { $0.hasPrefix("effective drive settings:") }) else {
            throw RobotSettingsError.invalidResponse
        }
        var values: [DriveSetting: Double] = [:]
        for token in line.split(whereSeparator: { $0.isWhitespace }) {
            let pair = token.split(separator: "=", omittingEmptySubsequences: false)
            guard pair.count == 2, let setting = DriveSetting(rawValue: String(pair[0])) else { continue }
            guard values[setting] == nil, let value = Double(pair[1]), setting.accepts(value) else {
                throw RobotSettingsError.invalidResponse
            }
            values[setting] = value
        }
        guard values.count == DriveSetting.allCases.count else { throw RobotSettingsError.invalidResponse }
        self.values = values
    }
}

public enum RobotSettingsError: Error, LocalizedError, Equatable, Sendable {
    case unavailable, disconnected, busy, timeout, invalidResponse, motorsOn
    case invalidValue, verificationFailed
    case refused(String)

    public var errorDescription: String? {
        switch self {
        case .unavailable: return "Robot settings are unavailable. This requires firmware with the management interface."
        case .disconnected: return "The connection changed. Reconnect and refresh settings before trying again."
        case .busy: return "Another settings request is still running."
        case .timeout: return "The robot did not confirm the request. A save may have applied; refresh settings before trying again."
        case .invalidResponse: return "Could not read a complete settings response. Refresh settings before trying again."
        case .motorsOn: return "Turn the motors off before saving settings."
        case .invalidValue: return "Enter a number within the allowed range."
        case .verificationFailed: return "The robot's readback does not match the requested value. Refresh settings before trying again."
        case .refused(let reason): return reason
        }
    }
}

public typealias ManagementCompletion = @Sendable (Result<String, RobotSettingsError>) -> Void
