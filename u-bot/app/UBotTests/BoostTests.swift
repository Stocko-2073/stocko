import SwiftUI
import XCTest
import UBotCore
@testable import UBot

@MainActor
final class BoostButtonModelTests: XCTestCase {
    func testOneTouchIsOnePressAndOneRelease() {
        let model = BoostButtonModel()
        var presses = 0, releases = 0
        model.onPress = { presses += 1 }
        model.onRelease = { releases += 1 }
        model.press(); model.press()            // onChanged fires all through a touch
        XCTAssertTrue(model.isHeld)
        XCTAssertEqual(presses, 1)
        model.release(); model.release()        // onEnded, then the gesture-state reset
        XCTAssertFalse(model.isHeld)
        XCTAssertEqual(releases, 1)
        model.press()
        XCTAssertTrue(model.isHeld)
        XCTAssertEqual(presses, 2)
    }

    func testForcedReleaseHoldsUntilTheFingerLifts() {
        let model = BoostButtonModel()
        var presses = 0, releases = 0
        model.onPress = { presses += 1 }
        model.onRelease = { releases += 1 }
        model.press()
        model.forceRelease()                    // a lock engaged under the thumb
        XCTAssertFalse(model.isHeld)
        XCTAssertEqual(releases, 1)
        model.press()                           // the same thumb, still down and moving
        XCTAssertFalse(model.isHeld)
        XCTAssertEqual(presses, 1)
        model.release()                         // lifts: nothing left to let go of
        XCTAssertEqual(releases, 1)
        model.press()                           // a fresh touch
        XCTAssertTrue(model.isHeld)
        XCTAssertEqual(presses, 2)
    }

    func testBlockedPressExplainsOncePerTouch() {
        let model = BoostButtonModel()
        var presses = 0
        var blocked: [String] = []
        model.onPress = { presses += 1 }
        model.onBlocked = { blocked.append($0) }
        model.blockReason = "Boost needs robot firmware 0.3.0 or newer"
        model.press(); model.press()
        XCTAssertFalse(model.isHeld)
        XCTAssertEqual(presses, 0)
        XCTAssertEqual(blocked, ["Boost needs robot firmware 0.3.0 or newer"])
        XCTAssertEqual(model.refusals, 1)
        model.release()
        model.blockReason = nil
        model.press()
        XCTAssertTrue(model.isHeld)
        XCTAssertEqual(presses, 1)
    }

    func testReleasingWhatIsNotHeldCallsNothing() {
        let model = BoostButtonModel()
        var releases = 0
        model.onRelease = { releases += 1 }
        model.forceRelease()
        model.release()
        XCTAssertEqual(releases, 0)
    }
}

/// A 0.3.0 robot with the motors on and nothing wrong, adjusted by `change`.
private func status(_ change: (inout UBotStatus) -> Void = { _ in }) -> UBotStatus {
    var s = UBotStatus(flags: [.enabled, .encoderAOK, .encoderBOK])
    s.flags2 = [.acceptsBoost]
    s.batteryState = UBotCore.BatteryState.none
    change(&s)
    return s
}

@MainActor
final class BoostControllerTests: XCTestCase {

    private func connected(_ s: UBotStatus = status(),
                           factory: ((ConnectionTransport, String) -> RobotLink)? = nil)
        async throws -> (RobotController, TestLink) {
        let link = TestLink()
        let controller = RobotController(link: link, factory: factory)
        link.onEvent?(.state(.ready(name: "ubot")))
        link.onEvent?(.status(s))
        try await settle()
        return (controller, link)
    }

    /// Each event reaches the controller in its own main-actor task.
    private func settle() async throws { try await Task.sleep(for: .milliseconds(20)) }

    private func deliver(_ link: TestLink, _ events: LinkEvent...) async throws {
        events.forEach { link.onEvent?($0) }
        try await settle()
    }

    // MARK: Engaging

    func testBoostEngagesOnlyWhenNothingBlocksIt() async throws {
        let blocked: [(UBotStatus, String)] = [
            (status { $0.flags2 = [] }, "Boost needs robot firmware 0.3.0 or newer"),
            (UBotStatus(flags: []), "Boost needs robot firmware 0.3.0 or newer"),
            (status { $0 = UBotStatus(flags: [.encoderAOK, .encoderBOK]); $0.flags2 = [.acceptsBoost] },
             "Enable the motors to drive"),
            (status { $0.flags2.insert(.derated) }, "Motor driver hot: boost is off until it cools"),
            (status { $0.flags2.insert(.heatLimited) }, "Motors warm: boost paused until they cool"),
        ]
        for (s, reason) in blocked {
            let (c, link) = try await connected(s)
            XCTAssertEqual(c.boostBlockReason, reason)
            c.engageBoost()
            XCTAssertFalse(c.isBoosting)
            XCTAssertEqual(link.boosts, [])
        }
        let (c, link) = try await connected()
        XCTAssertTrue(c.boostSupported)
        XCTAssertNil(c.boostBlockReason)
        c.engageBoost(); c.engageBoost()
        XCTAssertTrue(c.isBoosting)
        XCTAssertEqual(link.boosts, [true])
    }

    func testNoStatusMeansTheLockSpeaks() {
        let c = RobotController(link: TestLink())
        XCTAssertFalse(c.boostSupported)
        XCTAssertEqual(c.boostBlockReason, "Not connected")
    }

    // MARK: Letting go

    func testEveryReleasePathLetsGoOfBoost() async throws {
        let paths: [(String, @MainActor (RobotController, TestLink) async throws -> Void)] = [
            ("scene inactive", { c, _ in c.emergencyRelease(alsoStop: false) }),
            ("background", { c, _ in c.emergencyRelease(alsoStop: true) }),
            ("stop", { c, _ in c.send(.stop) }),
            ("E-STOP", { c, _ in c.send(.estop) }),
            ("settings", { c, _ in c.prepareSettings() }),
            ("Clear button", { c, _ in c.releaseBoost(); c.send(.clearFaults) }),
            ("transport switch", { c, _ in c.selectTransport(.wifi, address: "ubot.local") }),
            ("link lost", { _, link in try await self.deliver(link, .state(.reconnecting(name: "ubot"))) }),
            ("telemetry stalled", { _, link in try await self.deliver(link, .state(.stalled(name: "ubot"))) }),
            ("motors off", { _, link in
                try await self.deliver(link, .status(status { $0 = UBotStatus(flags: []); $0.flags2 = [.acceptsBoost] }))
            }),
            ("fault", { _, link in
                try await self.deliver(link, .status(status {
                    $0 = UBotStatus(flags: [.enabled, .faulted], fault: .slip); $0.flags2 = [.acceptsBoost]
                }))
            }),
        ]
        for (name, release) in paths {
            let (c, link) = try await connected(factory: { _, _ in TestLink() })
            c.engageBoost()
            try await release(c, link)
            XCTAssertFalse(c.isBoosting, name)
            XCTAssertEqual(link.boosts, [true, false], name)
        }
    }

    func testReleasingTheStickKeepsBoostSoTheRobotBraces() async throws {
        let (c, link) = try await connected()
        c.engage(.init(v: 0.4, w: 0))
        c.engageBoost()
        c.releaseStick()
        XCTAssertFalse(c.isDriving)
        XCTAssertTrue(c.isBoosting)
        XCTAssertEqual(link.boosts, [true])
        XCTAssertEqual(link.releases, 1)
    }

    func testHeatOrDerateWhileHeldLetsGoAndSaysWhy() async throws {
        for (flag, reason) in [(UBotStatus.Flags2.heatLimited, "Motors warm: boost paused until they cool"),
                               (.derated, "Motor driver hot: boost is off until it cools")] {
            let (c, link) = try await connected()
            c.engageBoost()
            try await deliver(link, .status(status { $0.flags2.insert(flag) }))
            XCTAssertFalse(c.isBoosting)
            XCTAssertEqual(link.boosts, [true, false])
            XCTAssertEqual(c.toast?.text, reason)
        }
    }

    func testALockLetsGoWithoutASecondToast() async throws {
        // RootView announces the lock itself; the controller must not add one.
        let (c, link) = try await connected()
        c.engageBoost()
        try await deliver(link, .status(status { $0 = UBotStatus(flags: []); $0.flags2 = [.acceptsBoost] }))
        XCTAssertFalse(c.isBoosting)
        XCTAssertNil(c.toast)
    }

    // MARK: State card

    func testDerateAndHeatCards() async throws {
        let (c, link) = try await connected(status { $0.flags2.formUnion([.derated, .heatLimited]); $0.derateA = 2 })
        XCTAssertEqual(c.stateCard.tone, .warn)
        XCTAssertEqual(c.stateCard.title, "Motors on")
        XCTAssertEqual(c.stateCard.detail, "Motor driver hot: current reduced (level 2 of 3); boost off.")
        try await deliver(link, .status(status { $0.flags2.insert(.heatLimited); $0.batteryState = .low }))
        XCTAssertEqual(c.stateCard.detail, "Motors warm: boost paused until they cool.")
        XCTAssertNil(c.stateCard.action)
    }

    func testBatteryLowCards() async throws {
        let (c, link) = try await connected(status { $0.batteryState = .low })
        XCTAssertEqual(c.stateCard.tone, .warn)
        XCTAssertEqual(c.stateCard.title, "Motors on")
        XCTAssertEqual(c.stateCard.detail, "Battery low: charge or swap the pack soon.")
        try await deliver(link, .status(status {
            $0 = UBotStatus(flags: [.encoderAOK, .encoderBOK]); $0.batteryState = .low
        }))
        XCTAssertEqual(c.stateCard.title, "Motors off")
        XCTAssertEqual(c.stateCard.detail, "Battery low: charge or swap the pack soon. Enable the motors to drive.")
    }

    func testBatteryCutoffCardOffersNothingToPress() async throws {
        let cutoff = status {
            $0 = UBotStatus(flags: [.enabled, .faulted, .batteryPresent], fault: .battery,
                            batteryMillivolts: 15_200, batteryPercent: 3)
            $0.batteryState = .cutoff
        }
        let (c, link) = try await connected(cutoff)
        XCTAssertEqual(c.stateCard.tone, .bad)
        XCTAssertEqual(c.stateCard.title, "Fault: Battery empty")
        XCTAssertEqual(c.stateCard.detail,
                       "The battery is below its cutoff. Charge or swap the pack; clear once the voltage recovers.")
        XCTAssertNil(c.stateCard.action)
        XCTAssertEqual(c.lock, DriveLock(reason: "Battery empty: charge or swap the pack"))
        // The same with the motors off and no fault latched yet.
        try await deliver(link, .status(status {
            $0 = UBotStatus(flags: [.batteryPresent]); $0.batteryState = .cutoff
        }))
        XCTAssertEqual(c.stateCard.title, "Battery empty")
        XCTAssertNil(c.stateCard.action)
    }

    func testRecoveredBatteryClearsLikeAnyFault() async throws {
        let (c, link) = try await connected(status {
            $0 = UBotStatus(flags: [.enabled, .faulted, .batteryPresent], fault: .battery)
            $0.batteryState = .low
        })
        XCTAssertEqual(c.stateCard.title, "Fault: Battery empty")
        XCTAssertEqual(c.stateCard.detail, "The battery is back above its cutoff. Clear the fault to drive.")
        XCTAssertEqual(c.stateCard.action?.op, .clearFaults)
        XCTAssertEqual(c.lock?.remedy, .clearFaults)
        try await deliver(link, .status(status {
            $0 = UBotStatus(flags: [.faulted, .batteryPresent], fault: .battery); $0.batteryState = .ok
        }))
        XCTAssertEqual(c.stateCard.detail, "The battery is back above its cutoff. Enabling the motors clears it.")
        XCTAssertNil(c.stateCard.action)
    }

    func testRefusalBelowCutoffNamesTheBattery() async throws {
        let (c, link) = try await connected(status {
            $0 = UBotStatus(flags: [.enabled, .faulted, .batteryPresent], fault: .battery); $0.batteryState = .cutoff
        })
        try await deliver(link, .controlRefused(.clearFaults, ControlOp.clearFaults.refusalText))
        XCTAssertEqual(c.toast?.text, "Clear fault refused. The battery is below its cutoff: charge or swap the pack.")
    }

    // MARK: Battery tone and chips

    func testBatteryToneFollowsTheRobotsVerdict() async throws {
        let cases: [(BatteryState?, UInt8, Color)] = [
            (.low, 90, UBotPalette.warn), (.cutoff, 90, UBotPalette.bad),
            (.ok, 90, UBotPalette.ok), (.ok, 30, UBotPalette.warn), (.ok, 10, UBotPalette.bad),
            (nil, 90, UBotPalette.ok),
        ]
        for (state, percent, tone) in cases {
            let (c, _) = try await connected(status {
                $0 = UBotStatus(flags: [.enabled, .batteryPresent], batteryMillivolts: 19_000, batteryPercent: percent)
                $0.batteryState = state
            })
            XCTAssertEqual(c.batteryTone, tone, "\(String(describing: state)) at \(percent)%")
        }
        let (c, _) = try await connected()
        XCTAssertEqual(c.batteryTone, UBotPalette.mute)
        XCTAssertEqual(c.batteryText, "not sensed")
        XCTAssertEqual(c.batteryShortText, "\u{2014}")
    }

    func testOneRobotChipInPriorityOrder() async throws {
        let cases: [(UBotStatus, RobotController.RobotChip?)] = [
            (status(), nil),
            (status { $0.batteryState = .low }, .init(text: "Battery low", tone: .warn)),
            (status { $0.batteryState = .low; $0.flags2.insert(.boostActive) }, .init(text: "Boost", tone: .active)),
            (status { $0.flags2.formUnion([.boostActive, .heatLimited]) }, .init(text: "Motor heat", tone: .warn)),
            (status { $0.flags2.formUnion([.boostActive, .heatLimited, .derated]); $0.batteryState = .low },
             .init(text: "Motor derate", tone: .bad)),
            (status { $0.batteryState = .cutoff }, nil),
        ]
        for (s, chip) in cases {
            let (c, _) = try await connected(s)
            XCTAssertEqual(c.robotChip, chip)
        }
        XCTAssertNil(RobotController(link: TestLink()).robotChip)
    }

    // MARK: Stall recovery

    func testRecoveredSlipIsToastedOnceTheEpisodeEnds() async throws {
        let (c, link) = try await connected(status { $0.recoveryCount = 41 })
        XCTAssertNil(c.toast)                   // the first sample is only a baseline
        try await deliver(link, .status(status { $0.recoveryCount = 42; $0.flags2.insert(.recovering) }))
        try await deliver(link, .status(status { $0.recoveryCount = 43; $0.flags2.insert(.recovering) }))
        XCTAssertNil(c.toast)                   // a second try in the same episode
        try await deliver(link, .status(status { $0.recoveryCount = 43 }))
        XCTAssertEqual(c.toast?.text, "Recovered a slip")
        XCTAssertEqual(c.toast?.kind, .info)
    }

    func testTheWheelIsNamedWhenTheLinkSaysWhich() async throws {
        let (c, link) = try await connected(status { $0.recoveryCount = 0; $0.recoveryWheels = 0 })
        try await deliver(link, .status(status {
            $0.recoveryCount = 1; $0.recoveryWheels = 0b01; $0.flags2.insert(.recovering)
        }))
        try await deliver(link, .status(status { $0.recoveryCount = 1; $0.recoveryWheels = 0 }))
        XCTAssertEqual(c.toast?.text, "Recovered a slip on wheel A")
        XCTAssertEqual(RobotController.recoveryText(wheels: 0b10), "Recovered a slip on wheel B")
        XCTAssertEqual(RobotController.recoveryText(wheels: 0b11), "Recovered a slip on both wheels")
    }

    func testAnEpisodeThatEndsInAFaultIsLeftToTheFaultCard() async throws {
        let (c, link) = try await connected(status { $0.recoveryCount = 7 })
        try await deliver(link, .status(status { $0.recoveryCount = 10; $0.flags2.insert(.recovering) }))
        try await deliver(link, .status(status {
            $0 = UBotStatus(flags: [.enabled, .faulted], fault: .slip)
            $0.flags2 = [.acceptsBoost]; $0.recoveryCount = 10
        }))
        XCTAssertNil(c.toast)
        XCTAssertEqual(c.stateCard.title, "Fault: Slip")
    }

    func testAReconnectTakesAFreshBaselineAndTheCounterWraps() async throws {
        let (c, link) = try await connected(status { $0.recoveryCount = 200 })
        try await deliver(link, .state(.reconnecting(name: "ubot")), .state(.ready(name: "ubot")),
                          .status(status { $0.recoveryCount = 255 }))
        XCTAssertNil(c.toast)                   // what happened unseen is not news
        try await deliver(link, .status(status { $0.recoveryCount = 0 }))
        XCTAssertEqual(c.toast?.text, "Recovered a slip")
    }
}
