import Foundation

/// A robot that isn't there.
///
/// CoreBluetooth reports `.unsupported` in the iOS Simulator and there is no
/// camera either, so this is how the whole interface gets built and every state
/// screenshotted without carrying a robot to the desk. It emits status at the
/// same 5 Hz the firmware does and honours the control ops, so the lock model
/// and the state card can be exercised for real.
///
/// It reports firmware 0.3.0 -- boost, heat and derate included -- unless the
/// scenario is `oldFirmware`.
public final class MockRobotLink: RobotLink {

    public var onEvent: (@Sendable (LinkEvent) -> Void)?

    /// Force a particular condition from a debug drawer, or in the Simulator
    /// with the `-mockScenario <name>` launch argument.
    public enum Scenario: String, CaseIterable, Sendable {
        case healthy
        case motorsOff
        case faultedSlip
        case faultedMagnet
        case foreignCommand
        case stalled
        case linkLost
        /// The firmware's own boost is on without the operator asking, as it
        /// is for a moment after every standstill.
        case boosting
        /// Wheel A's driver is at OTPW derate level 2 of 3.
        case derated
        /// The thermal model has paused boost until the motors cool.
        case motorsHot
        case batteryLow
        /// Below the cutoff: stopped and holding, battery fault latched, and
        /// enable and clear refused, as the firmware does.
        case batteryCutoff
        /// 0.2.9: battery state, no boost.
        case oldFirmware
    }

    public var scenario: Scenario {
        didSet { if scenario != oldValue { applyScenario() } }
    }

    private let queue = DispatchQueue(label: "com.stocko.ubot.mock")
    private var timer: DispatchSourceTimer?
    private var enabled = false
    private var faulted = false
    private var fault: DriveFault = .none
    private var command: DriveCommand = .zero
    private var driving = false
    private var boostHeld = false

    private var settings: [DriveSetting: Double] = [.topSpeed: 1, .acceleration: 1, .braking: 2]

    public init(scenario: Scenario = .motorsOff) {
        self.scenario = scenario
    }

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
            emit(.firmware(scenario == .oldFirmware ? "0.2.9" : "0.3.0"))
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
    public func setBoost(_ on: Bool)      { queue.async { [self] in boostHeld = on } }

    public func send(_ op: ControlOp) {
        queue.async { [self] in
            switch op {
            case .enable:
                // Mirrors drive_enable(): enabling also clears latched faults,
                // except below the battery cutoff, where it is refused.
                if scenario == .faultedMagnet || scenario == .batteryCutoff {
                    emit(.controlRefused(op, op.refusalText))
                    return
                }
                enabled = true; faulted = false; fault = .none
            case .disable:
                enabled = false; boostHeld = false
            case .stop:
                driving = false; command = .zero; boostHeld = false
            case .estop:
                enabled = false; driving = false; command = .zero; boostHeld = false
            case .clearFaults:
                if scenario == .batteryCutoff {
                    emit(.controlRefused(op, op.refusalText))
                    return
                }
                faulted = false; fault = .none
            }
            emit(.controlAccepted(op))
        }
    }

    private func emit(_ e: LinkEvent) { onEvent?(e) }

    private func applyScenario() {
        switch scenario {
        case .healthy, .foreignCommand, .boosting, .derated, .motorsHot, .batteryLow, .oldFirmware:
            enabled = true;  faulted = false; fault = .none
        case .motorsOff:      enabled = false; faulted = false; fault = .none
        case .faultedSlip:    enabled = true;  faulted = true;  fault = .slip
        case .faultedMagnet:  enabled = false; faulted = true;  fault = .magnet
        // The firmware ramps to zero and holds with the drivers energised,
        // so it never freewheels down a hill: enabled, and faulted.
        case .batteryCutoff:  enabled = true;  faulted = true;  fault = .battery
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

        // Battery: most scenarios report "not sensed", as a build without the
        // divider does -- a state the app must handle. The battery scenarios
        // need a reading, on the 5S pack's scale.
        var millivolts: UInt16 = 0
        var percent: UInt8 = 0
        var battery: BatteryState = .none
        switch scenario {
        case .batteryLow:    millivolts = 16_300; percent = 22; battery = .low
        case .batteryCutoff: millivolts = 15_200; percent = 3;  battery = .cutoff
        default:             break
        }
        if battery != .none { flags.insert(.batteryPresent) }

        let c = foreign ? DriveCommand(v: 0.3, w: 0.15) : command
        let vMps = active ? c.v * 0.675 : 0
        let wRad = active ? c.w * 5.14 : 0
        let turns = vMps / 0.6754

        var s = UBotStatus(
            flags: flags,
            fault: fault,
            batteryMillivolts: millivolts,
            batteryPercent: percent,
            // A slip fault is exactly "commanded but not turning", so show it.
            wheelATurnsPerSec: fault == .slip ? 0 : turns,
            wheelBTurnsPerSec: fault == .slip ? 0 : turns,
            commandedMetersPerSec: vMps,
            commandedRadiansPerSec: wRad)
        s.batteryState = battery
        if scenario != .oldFirmware { addTorque(to: &s) }
        emit(.status(s))
    }

    /// What 0.3.0 adds: the capability, heat, derate, and boost as the
    /// firmware's BoostPolicy grants it.
    private func addTorque(to s: inout UBotStatus) {
        s.flags2 = [.acceptsBoost]
        s.heatA = 0.82
        s.heatB = 0.79
        s.derateA = 0
        s.derateB = 0
        s.recoveryCount = 0
        switch scenario {
        case .boosting:
            s.flags2.insert(.boostActive)
        case .derated:
            s.flags2.formUnion([.derated, .otpw])
            s.derateA = 2
        case .motorsHot:
            s.flags2.insert(.heatLimited)
            s.heatA = 1.12
            s.heatB = 1.06
        default:
            break
        }
        // The operator's boost is requested while held, and granted only
        // where the firmware would grant it.
        if boostHeld && enabled && !faulted {
            s.flags2.insert(.boostRequested)
            if !s.isDerated && !s.isHeatLimited { s.flags2.insert(.boostActive) }
        }
    }
}
