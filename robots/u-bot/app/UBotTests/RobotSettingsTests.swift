import XCTest
import UBotCore
@testable import UBot

private final class SettingsTestLink: RobotLink {
    var onEvent: (@Sendable (LinkEvent) -> Void)?
    var requests: [[String]] = []
    var operations: [ControlOp] = []
    var acceleration = 8.0
    var failure: RobotSettingsError?
    var holdWrite = false
    var ignoreWrite = false
    var pending: ManagementCompletion?
    func start() {}
    func stop() {}
    func engage(_ command: DriveCommand) {}
    func update(_ command: DriveCommand) {}
    func releaseStick() {}
    func send(_ op: ControlOp) { operations.append(op) }
    func executeManagement(_ args: [String], completion: @escaping ManagementCompletion) {
        requests.append(args)
        if args.count == 3 {
            if !ignoreWrite { acceleration = Double(args[2])! }
            if holdWrite { pending = completion; return }
            if let failure { completion(.failure(failure)); return }
            completion(.success("accel_tps2 = \(acceleration)\n"))
        } else {
            completion(.success("effective drive settings: vmax_tps=1 accel_tps2=\(acceleration) decel_tps2=2\n"))
        }
    }
}

@MainActor
final class RobotSettingsTests: XCTestCase {
    private func connected(enabled: Bool = false) async throws -> (RobotController, SettingsTestLink) {
        let link = SettingsTestLink()
        let controller = RobotController(link: link)
        link.onEvent?(.state(.ready(name: "ubot")))
        link.onEvent?(.status(UBotStatus(flags: enabled ? [.enabled] : [])))
        try await Task.sleep(for: .milliseconds(20))
        return (controller, link)
    }

    func testReadsCurrentValuesAndVerifiesSingleSettingSave() async throws {
        let (controller, link) = try await connected()
        await controller.refreshDriveSettings()
        XCTAssertEqual(controller.driveSettings?[.acceleration], 8)
        let saved = await controller.saveDriveSetting(.acceleration, value: 1)
        XCTAssertTrue(saved)
        XCTAssertEqual(controller.driveSettings?[.acceleration], 1)
        XCTAssertEqual(controller.driveSettings?[.topSpeed], 1)
        XCTAssertEqual(controller.driveSettings?[.braking], 2)
        XCTAssertEqual(link.requests, [["set"], ["set", "accel_tps2", "1.0"], ["set"]])
        XCTAssertNotNil(controller.settingsNotice)
        XCTAssertTrue(link.operations.isEmpty)
    }

    func testEnabledMotorsAndInvalidValuesPreventWrites() async throws {
        let (controller, link) = try await connected(enabled: true)
        await controller.refreshDriveSettings()
        let enabledSave = await controller.saveDriveSetting(.acceleration, value: 1)
        let invalidSave = await controller.saveDriveSetting(.acceleration, value: .nan)
        XCTAssertFalse(enabledSave)
        XCTAssertFalse(invalidSave)
        XCTAssertEqual(link.requests, [["set"]])
        XCTAssertTrue(link.operations.isEmpty)
    }

    func testLostAcknowledgementRequiresRefreshAndNeverRetries() async throws {
        let (controller, link) = try await connected()
        await controller.refreshDriveSettings()
        link.failure = .timeout
        let saved = await controller.saveDriveSetting(.acceleration, value: 1)
        XCTAssertFalse(saved)
        XCTAssertNil(controller.driveSettings)
        XCTAssertNil(controller.settingsNotice)
        XCTAssertFalse(controller.canSaveSettings)
        XCTAssertEqual(link.requests.count, 2)
        await controller.refreshDriveSettings()
        XCTAssertEqual(controller.driveSettings?[.acceleration], 1)
        XCTAssertTrue(controller.canSaveSettings)
    }

    func testReadbackMismatchDoesNotClaimSuccess() async throws {
        let (controller, link) = try await connected()
        await controller.refreshDriveSettings()
        link.ignoreWrite = true
        let saved = await controller.saveDriveSetting(.acceleration, value: 1)
        XCTAssertFalse(saved)
        XCTAssertNil(controller.settingsNotice)
        XCTAssertNil(controller.driveSettings)
        XCTAssertEqual(controller.settingsError, RobotSettingsError.verificationFailed.localizedDescription)
    }

    func testOldCompletionAfterReconnectCannotUpdateSettings() async throws {
        let (controller, link) = try await connected()
        await controller.refreshDriveSettings()
        link.holdWrite = true
        let save = Task { await controller.saveDriveSetting(.acceleration, value: 1) }
        try await Task.sleep(for: .milliseconds(20))
        XCTAssertTrue(controller.settingsBusy)
        let duplicate = await controller.saveDriveSetting(.acceleration, value: 2)
        XCTAssertFalse(duplicate)
        link.onEvent?(.state(.reconnecting(name: "ubot")))
        link.onEvent?(.state(.ready(name: "ubot")))
        link.onEvent?(.status(UBotStatus(flags: [])))
        try await Task.sleep(for: .milliseconds(20))
        link.pending?(.success("saved"))
        let saved = await save.value
        XCTAssertFalse(saved)
        XCTAssertNil(controller.driveSettings)
        XCTAssertNil(controller.settingsNotice)
        XCTAssertEqual(link.requests.count, 2)
        XCTAssertFalse(controller.settingsBusy)
    }
}
