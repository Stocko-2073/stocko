import Foundation

/// A robot that isn't there.
///
/// CoreBluetooth reports `.unsupported` in the iOS Simulator and there is no
/// camera either, so this is how the whole interface gets built and every state
/// screenshotted without carrying a robot to the desk. It emits status at the
/// same 5 Hz the firmware does and honours the control ops, so the lock model
/// and the state card can be exercised for real.
public final class MockRobotLink: RobotLink {

    public var onEvent: (@Sendable (LinkEvent) -> Void)?

    /// Force a particular condition from a debug drawer.
    public enum Scenario: String, CaseIterable, Sendable {
        case healthy
        case motorsOff
        case faultedSlip
        case faultedMagnet
        case foreignCommand
        case stalled
        case linkLost
    }

    public var scenario: Scenario = .motorsOff {
        didSet { if scenario != oldValue { applyScenario() } }
    }

    private let queue = DispatchQueue(label: "com.stocko.ubot.mock")
    private var timer: DispatchSourceTimer?
    private var enabled = false
    private var faulted = false
    private var fault: DriveFault = .none
    private var command: DriveCommand = .zero
    private var driving = false

    private var settings: [DriveSetting: Double] = [.topSpeed: 1, .acceleration: 1, .braking: 2]

    public init() {}

    public func executeManagement(_ args: [String], completion: @escaping ManagementCompletion) {
        queue.async { [self] in
            guard timer != nil, scenario != .stalled, scenario != .linkLost else {
                completion(.failure(.disconnected)); return
            }
            if args == ["set"] {
                let values = DriveSetting.allCases.map { "\($0.rawValue)=\(settings[$0]!)" }.joined(separator: " ")
                completion(.success("effective drive settings: " + values + "\n"))
            } else if args.count == 3, args[0] == "set",
                      let setting = DriveSetting(rawValue: args[1]), let value = Double(args[2]), setting.accepts(value) {
                guard !enabled else { completion(.failure(.motorsOn)); return }
                settings[setting] = value
                completion(.success("\(setting.rawValue) = \(value)\n"))
            } else { completion(.failure(.invalidValue)) }
        }
    }

    public func start() {
        queue.async { [self] in
            applyScenario()
            emit(.firmware("0.2.7"))
            emit(.model("U-BOT base"))
            guard timer == nil else { return }
            let t = DispatchSource.makeTimerSource(queue: queue)
            t.schedule(deadline: .now(), repeating: 0.2)
            t.setEventHandler { [weak self] in self?.tick() }
            timer = t
            t.resume()
        }
    }

    public func stop() {
        queue.async { [self] in timer?.cancel(); timer = nil; emit(.state(.idle)) }
    }

    public func engage(_ c: DriveCommand) { queue.async { [self] in driving = true; command = c } }
    public func update(_ c: DriveCommand) { queue.async { [self] in command = c } }
    public func releaseStick()            { queue.async { [self] in driving = false; command = .zero } }

    public func send(_ op: ControlOp) {
        queue.async { [self] in
            switch op {
            case .enable:
                // Mirrors drive_enable(): enabling also clears latched faults.
                if scenario == .faultedMagnet {
                    emit(.controlRefused(op, op.refusalText))
                    return
                }
                enabled = true; faulted = false; fault = .none
            case .disable:
                enabled = false
            case .stop:
                driving = false; command = .zero
            case .estop:
                enabled = false; driving = false; command = .zero
            case .clearFaults:
                faulted = false; fault = .none
            }
            emit(.controlAccepted(op))
        }
    }

    private func emit(_ e: LinkEvent) { onEvent?(e) }

    private func applyScenario() {
        switch scenario {
        case .healthy:        enabled = true;  faulted = false; fault = .none
        case .motorsOff:      enabled = false; faulted = false; fault = .none
        case .faultedSlip:    enabled = true;  faulted = true;  fault = .slip
        case .faultedMagnet:  enabled = false; faulted = true;  fault = .magnet
        case .foreignCommand: enabled = true;  faulted = false; fault = .none
        case .stalled, .linkLost: break
        }
        switch scenario {
        case .stalled:  emit(.state(.stalled(name: "ubot")))
        case .linkLost: emit(.state(.reconnecting(name: "ubot")))
        default:        emit(.state(.ready(name: "ubot")))
        }
    }

    private func tick() {
        guard scenario != .stalled, scenario != .linkLost else { return }

        var flags: UBotStatus.Flags = [.encoderAOK, .encoderBOK]
        if enabled { flags.insert(.enabled) }
        if faulted { flags.insert(.faulted) }
        // The magnet fault on this build is wheel B, so drop its encoder bit.
        if fault == .magnet { flags.remove(.encoderBOK) }

        let foreign = scenario == .foreignCommand
        let active = (driving && !command.isZero && enabled && !faulted) || foreign
        if active { flags.insert(.commandActive) }

        // Battery: the divider is not wired on the real robot, so the mock
        // reports "not sensed" too. That is the state the app must handle.
        let c = foreign ? DriveCommand(v: 0.3, w: 0.15) : command
        let vMps = active ? c.v * 0.675 : 0
        let wRad = active ? c.w * 5.14 : 0
        let turns = vMps / 0.6754

        emit(.status(UBotStatus(
            flags: flags,
            fault: fault,
            batteryMillivolts: 0,
            batteryPercent: 0,
            // A slip fault is exactly "commanded but not turning", so show it.
            wheelATurnsPerSec: fault == .slip ? 0 : turns,
            wheelBTurnsPerSec: fault == .slip ? 0 : turns,
            commandedMetersPerSec: vMps,
            commandedRadiansPerSec: wRad)))
    }
}
