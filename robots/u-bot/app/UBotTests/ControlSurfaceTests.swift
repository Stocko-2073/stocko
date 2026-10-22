import XCTest
import UBotCore
@testable import UBot

@MainActor
final class ControlSurfaceTests: XCTestCase {
    func testKnobTracksInputWhileCallbacksReceiveShapedCommands() {
        let model = ControlSurfaceModel()
        var engaged: DriveCommand?
        var updated: DriveCommand?
        model.onEngage = { engaged = $0 }
        model.onUpdate = { updated = $0 }

        let halfForward = DriveCommand(stickX: 0, stickY: -0.5)
        model.engage(halfForward)
        XCTAssertEqual(model.stickPosition, halfForward)
        XCTAssertEqual(model.command.v, 0.275, accuracy: 1e-9)
        XCTAssertEqual(engaged, model.command)

        let mixed = DriveCommand(stickX: 0.3, stickY: -0.4)
        model.update(mixed)
        XCTAssertEqual(model.stickPosition, mixed)
        XCTAssertEqual(model.command.v, 0.1984, accuracy: 1e-9)
        XCTAssertEqual(model.command.w, -0.1362, accuracy: 1e-9)
        XCTAssertEqual(updated, model.command)
    }

    func testRimTrackingAndFullAuthority() {
        let model = ControlSurfaceModel()
        model.engage(DriveCommand(stickX: 3, stickY: 3))
        XCTAssertEqual(model.stickPosition.magnitude, 1, accuracy: 1e-9)
        XCTAssertEqual(model.command.v, -0.4949747468, accuracy: 1e-9)
        XCTAssertEqual(model.command.w, -0.4949747468, accuracy: 1e-9)
        for (x, y) in [(0.0, -2.0), (0.0, 2.0), (-2.0, 0.0), (2.0, 0.0)] {
            let input = DriveCommand(stickX: x, stickY: y)
            model.update(input)
            XCTAssertEqual(model.stickPosition, input)
            XCTAssertEqual(model.command, input)
        }
    }

    func testReleaseAndCancellationCentreBothStatesExactlyOnce() {
        for forced in [false, true] {
            let model = ControlSurfaceModel()
            var releases = 0
            var updates = 0
            model.onRelease = { releases += 1 }
            model.onUpdate = { _ in updates += 1 }
            model.engage(DriveCommand(stickX: -0.5, stickY: 0))
            if forced { model.forceRelease() } else { model.release() }
            model.release()
            model.forceRelease()
            model.update(DriveCommand(stickX: 0, stickY: -1))
            XCTAssertFalse(model.isEngaged)
            XCTAssertEqual(model.stickPosition, .zero)
            XCTAssertEqual(model.command, .zero)
            XCTAssertEqual(releases, 1)
            XCTAssertEqual(updates, 0)
        }
    }

    func testLockCentresHeldStickAndBlocksFurtherInput() {
        let model = ControlSurfaceModel()
        var engagements = 0
        var blocked: DriveLock?
        model.onEngage = { _ in engagements += 1 }
        model.onBlocked = { blocked = $0 }
        model.engage(DriveCommand(stickX: 0, stickY: -0.75))
        // RootView forces a release when the controller becomes locked.
        model.forceRelease()
        model.lock = DriveLock(reason: "Motors disabled", remedy: .enable)
        model.engage(DriveCommand(stickX: 1, stickY: 0))
        model.update(DriveCommand(stickX: 0, stickY: -1))
        XCTAssertEqual(blocked, model.lock)
        XCTAssertEqual(engagements, 1)
        XCTAssertFalse(model.isEngaged)
        XCTAssertEqual(model.stickPosition, .zero)
        XCTAssertEqual(model.command, .zero)
    }
}
