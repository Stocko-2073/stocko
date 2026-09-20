import Foundation
import Observation
import SwiftUI
import UBotCore

/// The one object the views know about.
///
/// It consumes the `LinkEvent` stream from whatever `RobotLink` it was given,
/// holds the newest status, and derives everything on screen from it -- the
/// same shape as `render()` in joystick.html, where the robot's 5 Hz status
/// frame drives the whole page.
@MainActor
@Observable
final class RobotController {

    // MARK: Observed state

    private(set) var linkState: LinkState = .idle
    private(set) var status: UBotStatus?
    private(set) var firmware: String?
    private(set) var model: String?
    private(set) var toast: Toast?

    /// True between engage and release. Distinguishes "this phone is driving"
    /// from "someone else is driving", which the status flag alone cannot.
    private(set) var isDriving = false

    /// Non-nil while the drive characteristic is being pushed harder than the
    /// link can carry. The early warning that the connection interval went bad.
    private(set) var linkCongested = false

    private var link: RobotLink
    private var generation = 0
    private(set) var transport: ConnectionTransport = .ble
    private var linkFactory: ((ConnectionTransport, String) -> RobotLink)?
    private var toastTask: Task<Void, Never>?

    struct Toast: Equatable, Identifiable {
        enum Kind { case info, warning, bad }
        let id = UUID()
        let text: String
        let kind: Kind
    }

    init(link: RobotLink, transport: ConnectionTransport = .ble,
         factory: ((ConnectionTransport, String) -> RobotLink)? = nil) {
        self.link = link
        self.transport = transport
        self.linkFactory = factory
        attach()
    }

    private func attach() {
        let id = generation
        link.onEvent = { [weak self] event in
            Task { @MainActor [weak self] in
                guard let self, self.generation == id else { return }
                self.handle(event)
            }
        }
    }

    func selectTransport(_ transport: ConnectionTransport, address: String) {
        guard let factory = linkFactory else { return }
        emergencyRelease(alsoStop: true)
        let old = link
        old.onEvent = nil
        generation += 1
        // Give the explicit stop a bounded opportunity to leave the old link.
        // The firmware deadman remains the backstop if that link is broken.
        Task { @MainActor in
            try? await Task.sleep(for: .milliseconds(250))
            old.stop()
        }
        self.transport = transport
        linkState = .connecting(name: transport == .wifi ? address : "ubot")
        status = nil; firmware = nil; model = nil; linkCongested = false
        link = factory(transport, address)
        attach()
        let id = generation
        Task { @MainActor [weak self] in
            try? await Task.sleep(for: .milliseconds(500))
            guard let self, self.generation == id else { return }
            self.link.start()
        }
    }

    func start() { link.start() }
    func stop() { link.stop() }

    // MARK: Derived

    /// nil means the stick is live. Exactly `lockMsg` in joystick.html.
    var lock: DriveLock? { DriveLock.derive(linkState: linkState, status: status) }

    /// The robot is executing a command that did not come from this phone.
    var foreignCommandActive: Bool {
        (status?.isCommandActive ?? false) && !isDriving
    }

    struct StateCard {
        enum Tone { case ok, warn, bad, neutral }
        let tone: Tone
        let title: String
        let detail: String
        let action: (label: String, op: ControlOp)?
    }

    /// The "what is the robot doing" card, ported from joystick.html's
    /// `render()`. The web page's calibration, demo and OTA branches have no
    /// BLE equivalent -- the 13-byte status frame does not carry them -- so a
    /// refusal during one of those surfaces reactively, as an ATT 0x0E on the
    /// control write, instead of proactively as a lock.
    var stateCard: StateCard {
        guard linkState.isReady || isStalled else {
            return StateCard(tone: .bad,
                             title: linkState.summary,
                             detail: connectionDetail,
                             action: nil)
        }
        if isStalled {
            return StateCard(
                tone: .warn,
                title: "No data from the robot",
                detail: "Connected, but the status stream has gone quiet. Another "
                      + "client may have interrupted telemetry.",
                action: nil)
        }
        guard let s = status else {
            return StateCard(tone: .neutral, title: "Connected",
                             detail: "Waiting for the first status frame.", action: nil)
        }
        if let reason = s.busyReason {
            return StateCard(tone: .warn, title: reason, detail: "Driving is unavailable until it finishes.", action: nil)
        }
        if s.isFaulted {
            return StateCard(
                tone: .bad,
                title: "Fault: \(s.fault.title)",
                detail: s.isEnabled
                    ? s.fault.detail
                    : s.fault.detail + " Enabling the motors clears it.",
                action: s.isEnabled ? ("Clear fault", .clearFaults) : nil)
        }
        if s.isEnabled {
            if foreignCommandActive {
                return StateCard(tone: .warn, title: "Motors on",
                                 detail: "Moving on a command from another controller.",
                                 action: ("Stop", .stop))
            }
            return StateCard(tone: .ok, title: "Motors on",
                             detail: "Ready to drive.", action: nil)
        }
        // An encoder that stopped answering is the most useful thing to say
        // about a robot that will not enable.
        let down = [s.encoderAOK ? nil : "A", s.encoderBOK ? nil : "B"].compactMap { $0 }
        return StateCard(
            tone: .neutral,
            title: "Motors off",
            detail: down.isEmpty
                ? "Enable the motors to drive."
                : "Encoder \(down.joined(separator: " and ")) not answering. Check the wiring.",
            action: nil)
    }

    private var isStalled: Bool { if case .stalled = linkState { return true }; return false }

    private var connectionDetail: String {
        switch linkState {
        case .failed(let reason): return reason
        case .bluetoothOff:  return "Turn Bluetooth on to reach the robot."
        case .unauthorized:  return "Allow Bluetooth for U-BOT in Settings."
        case .unsupported:   return "This device has no Bluetooth LE."
        case .scanning:      return "Looking for the robot."
        case .reconnecting:  return "The robot stops itself after half a second. Reconnecting\u{2026}"
        default:             return transport == .wifi
            ? "Connecting over Wi-Fi. Check the address and allow Local Network access in Settings."
            : "Connecting to the robot."
        }
    }

    /// Battery, as a sentence. The divider is not wired on the current build,
    /// so "not sensed" is the expected reading, not an error.
    var batteryText: String {
        guard let s = status else { return "\u{2014}" }
        guard s.batteryIsSensed else { return "not sensed" }
        return "\(s.batteryPercent)% \u{00B7} \(String(format: "%.1f", s.batteryVolts)) V"
    }

    var batteryTone: Color {
        guard let s = status, s.batteryIsSensed else { return UBotPalette.mute }
        if s.batteryPercent < 20 { return UBotPalette.bad }
        if s.batteryPercent < 50 { return UBotPalette.warn }
        return UBotPalette.ok
    }

    // MARK: Commands

    func engage(_ c: DriveCommand) { guard lock == nil else { return }; isDriving = true; link.engage(c) }
    func update(_ c: DriveCommand) { guard isDriving, lock == nil else { return }; link.update(c) }

    func releaseStick() {
        isDriving = false
        link.releaseStick()
    }

    /// Called from the scenePhase hook and whenever the lock engages.
    ///
    /// `alsoStop` sends an explicit stop on top of the zero drive. Reserved for
    /// actually leaving the app: a system alert merely makes the scene
    /// inactive, and zeroing the drive is enough there.
    func emergencyRelease(alsoStop: Bool) {
        releaseStick()
        if alsoStop { link.send(.stop) }
    }

    func send(_ op: ControlOp) {
        if op == .estop || op == .stop { releaseStick() }
        link.send(op)
    }

    func show(_ text: String, kind: Toast.Kind = .info) {
        toast = Toast(text: text, kind: kind)
        toastTask?.cancel()
        toastTask = Task { [weak self] in
            try? await Task.sleep(for: .seconds(3.5))
            guard !Task.isCancelled else { return }
            self?.toast = nil
        }
    }

    // MARK: Events

    private func handle(_ event: LinkEvent) {
        switch event {
        case .state(let s):
            let wasReady = linkState.isReady
            linkState = s
            // A link that stops being usable must not leave the last non-zero
            // command sitting on the wire.
            if wasReady, !s.isReady { emergencyRelease(alsoStop: false) }
            if !s.isReady { status = nil }

        case .status(let s):
            status = s

        case .batteryLevel:
            // The status frame already carries millivolts and percent; the
            // standard Battery Service is redundant here and only kept
            // subscribed so a generic BLE tool sees something sensible.
            break

        case .firmware(let f):
            firmware = f

        case .model(let m):
            model = m

        case .controlAccepted(let op):
            if op == .estop { show("Emergency stop sent. Motors are cut.", kind: .bad) }

        case .message(let message):
            show(message, kind: .warning)

        case .controlRefused(let op, let why):
            show("\(op.title) refused. \(why)", kind: .bad)

        case .linkQuality(let written, let dropped, let escalated):
            // Escalations mean the write-without-response queue stayed shut for
            // a quarter of the deadman. A few are normal; a steady stream is
            // the sign the connection interval has degraded.
            linkCongested = escalated > 2 || dropped > written
        }
    }
}
