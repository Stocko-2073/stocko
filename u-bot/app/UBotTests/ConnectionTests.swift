import XCTest
import UBotCore
@testable import UBot

private final class TestLink: RobotLink {
    var onEvent: (@Sendable (LinkEvent) -> Void)?
    var starts = 0
    var stops = 0
    var releases = 0
    var commands: [ControlOp] = []
    var drives: [DriveCommand] = []
    func start() { starts += 1 }
    func stop() { stops += 1 }
    func engage(_ command: DriveCommand) { drives.append(command) }
    func update(_ command: DriveCommand) { drives.append(command) }
    func releaseStick() { releases += 1 }
    func send(_ op: ControlOp) { commands.append(op) }
}

@MainActor
final class ConnectionTests: XCTestCase {
    func testSwitchStopsOldLinkAndRejectsOldEvents() async throws {
        let old = TestLink(), fresh = TestLink()
        let c = RobotController(link: old, factory: { _, _ in fresh })
        let lateCallback = old.onEvent
        old.onEvent?(.state(.ready(name: "old")))
        old.onEvent?(.status(UBotStatus(flags: [.enabled])))
        try await Task.sleep(for: .milliseconds(20))
        c.engage(.init(v: 0.5, w: 0))
        XCTAssertTrue(c.isDriving)
        c.selectTransport(.wifi, address: "ubot.local")
        XCTAssertFalse(c.isDriving)
        XCTAssertNil(c.status)
        XCTAssertTrue(old.commands.contains(.stop))
        lateCallback?(.status(UBotStatus(flags: [.enabled], batteryPercent: 99)))
        lateCallback?(.state(.ready(name: "old")))
        try await Task.sleep(for: .milliseconds(550))
        XCTAssertEqual(old.stops, 1)
        XCTAssertEqual(fresh.starts, 1)
        XCTAssertNil(c.status)
        XCTAssertFalse(c.linkState.isReady)
        fresh.onEvent?(.state(.ready(name: "new")))
        fresh.onEvent?(.status(UBotStatus(flags: [.enabled])))
        try await Task.sleep(for: .milliseconds(20))
        c.update(.init(v: 0.8, w: 0))
        XCTAssertTrue(fresh.drives.isEmpty)
        c.engage(.init(v: 0.2, w: 0))
        XCTAssertEqual(fresh.drives, [.init(v: 0.2, w: 0)])
    }

    func testRapidSwitchDoesNotStartRetiredLink() async throws {
        let original = TestLink(), intermediate = TestLink(), last = TestLink()
        var links = [intermediate, last]
        let c = RobotController(link: original, factory: { _, _ in links.removeFirst() })
        c.selectTransport(.wifi, address: "ubot.local")
        c.selectTransport(.ble, address: "ubot.local")
        try await Task.sleep(for: .milliseconds(550))
        XCTAssertEqual(intermediate.starts, 0)
        XCTAssertEqual(intermediate.stops, 1)
        XCTAssertEqual(last.starts, 1)
    }
}
