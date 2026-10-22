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
    private(set) var driveSettings: DriveSettings?
    private(set) var settingsBusy = false
    private(set) var settingsError: String?
    private(set) var settingsNotice: String?
    private var settingsRevision = 0

    /// True between engage and release. Distinguishes "this phone is driving"
    /// from "someone else is driving", which the status flag alone cannot.
    private(set) var isDriving = false

    /// True while the operator holds Boost and the link carries the flag.
    /// Independent of `isDriving`: Boost held with the stick released braces
    /// the robot where it stands, which is the point of it on a hill.
    private(set) var isBoosting = false

    /// Non-nil while the drive characteristic is being pushed harder than the
    /// link can carry. The early warning that the connection interval went bad.
    private(set) var linkCongested = false

    private var link: RobotLink
    private var generation = 0
    private(set) var transport: ConnectionTransport = .ble
    private var linkFactory: ((ConnectionTransport, String) -> RobotLink)?
    private var toastTask: Task<Void, Never>?

    /// Stall recovery reporting: the counter as last seen, whether an episode
    /// is waiting to be reported, and the wheels it has involved so far.
    private var recoveryBaseline: UInt8?
    private var recoveryPending = false
    private var recoveryWheels: UInt8 = 0

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
        invalidateSettings()
        resetRecoveryTracking()
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
    func stop() { invalidateSettings(); link.stop() }

    // MARK: Derived

    /// nil means the stick is live. Exactly `lockMsg` in joystick.html.
    var lock: DriveLock? { DriveLock.derive(linkState: linkState, status: status) }

    /// The robot is executing a command that did not come from this phone.
    var foreignCommandActive: Bool {
        (status?.isCommandActive ?? false) && !isDriving
    }

    /// The firmware takes the boost flag: BLE flags2 bit 7, or "boost" in the
    /// Wi-Fi caps. False until the first status says otherwise.
    var boostSupported: Bool { status?.acceptsBoost ?? false }

    /// Why Boost cannot be held right now, or nil when it can. It is what the
    /// greyed button says when tapped, so each reason names what would change.
    var boostBlockReason: String? {
        // Firmware first once it is known: it is the one reason that no amount
        // of enabling or waiting will fix.
        if let s = status, !s.acceptsBoost { return "Boost needs robot firmware 0.3.0 or newer" }
        if let lock { return lock.reason }
        guard let s = status else { return "Waiting for status" }
        // The firmware would not grant it now anyway. Saying so beats a
        // button that shows held while nothing happens.
        if s.isDerated { return "Motor driver hot: boost is off until it cools" }
        if s.isHeatLimited { return "Motors warm: boost paused until they cool" }
        return nil
    }

    struct RobotChip: Equatable {
        enum Tone: Equatable { case active, warn, bad }
        let text: String
        let tone: Tone
    }

    /// At most one chip about the robot's torque and supply, the most pressing
    /// first. The HUD is one line over live camera and ends up in every clip;
    /// the state card carries the sentence. The phone's own heat chips are
    /// separate.
    var robotChip: RobotChip? {
        guard let s = status else { return nil }
        if s.isDerated            { return RobotChip(text: "Motor derate", tone: .bad) }
        if s.isHeatLimited        { return RobotChip(text: "Motor heat", tone: .warn) }
        // Any granted boost, the firmware's own start boost included, so
        // the chip explains the extra current whoever asked for it.
        if s.isBoosting           { return RobotChip(text: "Boost", tone: .active) }
        if s.batteryState == .low { return RobotChip(text: "Battery low", tone: .warn) }
        return nil
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
    /// BLE equivalent -- the BLE status frame does not carry them -- so a
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
        // Below the cutoff the robot refuses enable and clear alike, so there
        // is nothing to press: no action here, and so no Clear by the pad.
        if s.batteryState == .cutoff {
            return s.isFaulted
                ? StateCard(tone: .bad, title: "Fault: \(DriveFault.battery.title)",
                            detail: DriveFault.battery.detail, action: nil)
                : StateCard(tone: .bad, title: DriveFault.battery.title,
                            detail: "The battery is below its cutoff, so the motors stay off. "
                                  + "Charge or swap the pack.",
                            action: nil)
        }
        if let reason = s.busyReason {
            return StateCard(tone: .warn, title: reason, detail: "Driving is unavailable until it finishes.", action: nil)
        }
        if s.isFaulted {
            // Back above the cutoff, the battery fault is still latched and now
            // clears like any other. Firmware that reports no battery state
            // gets the generic card below.
            let recovered = s.fault == .battery && (s.batteryState == .ok || s.batteryState == .low)
            let detail = recovered ? "The battery is back above its cutoff." : s.fault.detail
            return StateCard(
                tone: .bad,
                title: "Fault: \(s.fault.title)",
                detail: s.isEnabled
                    ? (recovered ? detail + " Clear the fault to drive." : detail)
                    : detail + " Enabling the motors clears it.",
                action: s.isEnabled ? ("Clear fault", .clearFaults) : nil)
        }
        if s.isEnabled {
            if foreignCommandActive {
                return StateCard(tone: .warn, title: "Motors on",
                                 detail: "Moving on a command from another controller.",
                                 action: ("Stop", .stop))
            }
            if let condition = conditionText(s) {
                return StateCard(tone: .warn, title: "Motors on", detail: condition, action: nil)
            }
            return StateCard(tone: .ok, title: "Motors on",
                             detail: "Ready to drive.", action: nil)
        }
        // An encoder that stopped answering is the most useful thing to say
        // about a robot that will not enable.
        let down = [s.encoderAOK ? nil : "A", s.encoderBOK ? nil : "B"].compactMap { $0 }
        if down.isEmpty, s.batteryState == .low {
            return StateCard(tone: .warn, title: "Motors off",
                             detail: "Battery low: charge or swap the pack soon. Enable the motors to drive.",
                             action: nil)
        }
        return StateCard(
            tone: .neutral,
            title: "Motors off",
            detail: down.isEmpty
                ? "Enable the motors to drive."
                : "Encoder \(down.joined(separator: " and ")) not answering. Check the wiring.",
            action: nil)
    }

    /// The one sentence worth saying about a running robot's torque and supply,
    /// in the same order as the HUD chip.
    private func conditionText(_ s: UBotStatus) -> String? {
        if s.isDerated {
            let level = s.derateLevel.flatMap { $0 > 0 ? " (level \($0) of 3)" : nil } ?? ""
            return "Motor driver hot: current reduced\(level); boost off."
        }
        if s.isHeatLimited { return "Motors warm: boost paused until they cool." }
        if s.batteryState == .low { return "Battery low: charge or swap the pack soon." }
        return nil
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

    /// The same without the volts, for a HUD that is also showing a robot
    /// chip on a narrow phone: a whole percentage beats a truncated reading.
    /// "not sensed" does not fit beside the widest chip on a 375-390 pt
    /// phone, and it is a fixed property of the build rather than news, so
    /// it shortens to a dash.
    var batteryShortText: String {
        guard let s = status, s.batteryIsSensed else { return "\u{2014}" }
        return "\(s.batteryPercent)%"
    }

    var batteryTone: Color {
        guard let s = status else { return UBotPalette.mute }
        // The robot's own verdict -- its pack table, filtering and hysteresis
        // behind it -- outranks a percentage read off the frame.
        switch s.batteryState {
        case .cutoff?: return UBotPalette.bad
        case .low?:    return UBotPalette.warn
        default:       break
        }
        guard s.batteryIsSensed else { return UBotPalette.mute }
        if s.batteryPercent < 20 { return UBotPalette.bad }
        if s.batteryPercent < 50 { return UBotPalette.warn }
        return UBotPalette.ok
    }

    // MARK: Commands

    func engage(_ c: DriveCommand) { guard lock == nil else { return }; isDriving = true; link.engage(c) }
    func update(_ c: DriveCommand) { guard isDriving, lock == nil else { return }; link.update(c) }

    /// Finger up. Boost, if held, stays held: the robot braces where it is.
    func releaseStick() {
        isDriving = false
        link.releaseStick()
    }

    /// Boost pressed. Only while nothing blocks it -- no lock, firmware that
    /// takes the flag, no heat or derate holding it off.
    func engageBoost() {
        guard !isBoosting, boostBlockReason == nil else { return }
        isBoosting = true
        link.setBoost(true)
    }

    /// Boost let go, or taken away. Safe to call whether or not it is held.
    func releaseBoost() {
        guard isBoosting else { return }
        isBoosting = false
        link.setBoost(false)
    }

    /// Called from the scenePhase hook and whenever the lock engages, and on
    /// every other path that must leave nothing held: a transport switch,
    /// opening settings, a lost link. It lets go of Boost as well as the stick.
    ///
    /// `alsoStop` sends an explicit stop on top of the zero drive. Reserved for
    /// actually leaving the app: a system alert merely makes the scene
    /// inactive, and zeroing the drive is enough there.
    func emergencyRelease(alsoStop: Bool) {
        releaseStick()
        releaseBoost()
        if alsoStop { link.send(.stop) }
    }

    func send(_ op: ControlOp) {
        if op == .estop || op == .stop { releaseStick(); releaseBoost() }
        link.send(op)
    }

    /// Boost is only ever held while nothing blocks it. The status that blocks
    /// it -- a lock, heat, a derate -- ends it here, whatever the view is
    /// doing. RootView announces a lock; any other reason is announced here,
    /// or the hold would just stop without a word.
    private func dropBoostIfBlocked() {
        guard isBoosting, let reason = boostBlockReason else { return }
        releaseBoost()
        if lock == nil { show(reason, kind: .warning) }
    }

    // MARK: Robot settings

    func prepareSettings() {
        invalidateSettings()
        settingsError = nil
        emergencyRelease(alsoStop: true)
    }

    var canSaveSettings: Bool {
        linkState.isReady && status != nil && status?.isEnabled == false
            && status?.isCommandActive == false && status?.busyReason == nil
            && !isDriving && !settingsBusy && driveSettings != nil
    }

    private func invalidateSettings() {
        settingsRevision += 1
        driveSettings = nil
        settingsNotice = nil
    }

    private func executeSettings(_ args: [String], revision: Int) async throws -> String {
        try Task.checkCancellation()
        guard linkState.isReady, revision == settingsRevision else { throw RobotSettingsError.disconnected }
        let result: Result<String, RobotSettingsError> = await withCheckedContinuation { continuation in
            link.executeManagement(args) { continuation.resume(returning: $0) }
        }
        try Task.checkCancellation()
        guard linkState.isReady, revision == settingsRevision else { throw RobotSettingsError.disconnected }
        return try result.get()
    }

    func refreshDriveSettings() async {
        guard !settingsBusy else { return }
        settingsBusy = true; settingsError = nil; settingsNotice = nil
        driveSettings = nil
        defer { settingsBusy = false }
        do {
            let output = try await executeSettings(["set"], revision: settingsRevision)
            driveSettings = try DriveSettings(output: output)
        } catch {
            settingsError = error.localizedDescription
        }
    }

    @discardableResult
    func saveDriveSetting(_ setting: DriveSetting, value: Double) async -> Bool {
        guard !settingsBusy else { return false }
        settingsError = nil; settingsNotice = nil
        guard setting.accepts(value) else { settingsError = RobotSettingsError.invalidValue.localizedDescription; return false }
        guard linkState.isReady, status != nil else {
            settingsError = RobotSettingsError.disconnected.localizedDescription; return false
        }
        guard driveSettings != nil else {
            settingsError = RobotSettingsError.invalidResponse.localizedDescription; return false
        }
        guard canSaveSettings else {
            settingsError = RobotSettingsError.motorsOn.localizedDescription; return false
        }
        let revision = settingsRevision
        settingsBusy = true
        defer { settingsBusy = false }
        do {
            _ = try await executeSettings(["set", setting.rawValue, String(value)], revision: revision)
            // The ACK is insufficient: refresh the effective value before claiming success.
            driveSettings = nil
            let output = try await executeSettings(["set"], revision: revision)
            let verified = try DriveSettings(output: output)
            driveSettings = verified
            guard setting.matchesReadback(verified[setting], requested: value) else { throw RobotSettingsError.verificationFailed }
            settingsNotice = "Saved \(setting.title.lowercased()) to the robot: \(setting.display(verified[setting])) \(setting.unit)."
            return true
        } catch {
            driveSettings = nil
            settingsError = error.localizedDescription
            return false
        }
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
            if !s.isReady { status = nil; invalidateSettings(); resetRecoveryTracking() }
            dropBoostIfBlocked()

        case .status(let s):
            status = s
            noteRecovery(s)
            dropBoostIfBlocked()

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
            // BLE carries no reason, only ATT 0x0E, and the stock sentence
            // blames the drivers. Below the cutoff the reason is known.
            if status?.batteryState == .cutoff, op == .enable || op == .clearFaults {
                show("\(op.title) refused. The battery is below its cutoff: charge or swap the pack.",
                     kind: .bad)
            } else {
                show("\(op.title) refused. \(why)", kind: .bad)
            }

        case .linkQuality(let written, let dropped, let escalated):
            // Escalations mean the write-without-response queue stayed shut for
            // a quarter of the deadman. A few are normal; a steady stream is
            // the sign the connection interval has degraded.
            linkCongested = escalated > 2 || dropped > written
        }
    }

    // MARK: Stall recovery

    /// Says so when the robot has got itself out of a slip.
    ///
    /// The counter moves on every attempt, including the ones that end in a
    /// latched slip, so the toast waits for the episode to finish and stays
    /// quiet when it finished in a fault -- the fault card says that. The first
    /// sample after connecting is only a baseline: what the robot did before
    /// the phone was listening is not news.
    private func noteRecovery(_ s: UBotStatus) {
        guard let count = s.recoveryCount else { return }
        defer { recoveryBaseline = count }
        guard let baseline = recoveryBaseline else { return }
        if count != baseline { recoveryPending = true }
        guard recoveryPending else { return }
        recoveryWheels |= s.recoveryWheels ?? 0
        guard !s.isRecovering else { return }
        let wheels = recoveryWheels
        recoveryPending = false
        recoveryWheels = 0
        guard !s.isFaulted else { return }
        show(Self.recoveryText(wheels: wheels))
    }

    /// Only Wi-Fi says which wheel slipped; BLE gets the generic sentence.
    static func recoveryText(wheels: UInt8) -> String {
        switch wheels & 0b11 {
        case 0b01: return "Recovered a slip on wheel A"
        case 0b10: return "Recovered a slip on wheel B"
        case 0b11: return "Recovered a slip on both wheels"
        default:   return "Recovered a slip"
        }
    }

    private func resetRecoveryTracking() {
        recoveryBaseline = nil
        recoveryPending = false
        recoveryWheels = 0
    }
}
