import XCTest

/// The Simulator's mock robot, started in a scenario with `-mockScenario`.
/// BLE is selected explicitly, so these never reach for a real robot.
final class BoostUITests: XCTestCase {

    override func setUp() {
        continueAfterFailure = false
    }

    private func launch(_ scenario: String) -> XCUIApplication {
        let app = XCUIApplication()
        app.launchArguments = ["-connectionTransport", "ble", "-mockScenario", scenario]
        app.launch()
        return app
    }

    private func waitForValue(_ element: XCUIElement, _ value: String, file: StaticString = #filePath,
                              line: UInt = #line) {
        let predicate = NSPredicate(format: "value == %@", value)
        let expectation = XCTNSPredicateExpectation(predicate: predicate, object: element)
        XCTAssertEqual(XCTWaiter().wait(for: [expectation], timeout: 10), .completed,
                       "expected \(value), got \(String(describing: element.value))", file: file, line: line)
    }

    private func attach(_ app: XCUIApplication, _ name: String) {
        let shot = XCTAttachment(screenshot: app.screenshot())
        shot.name = name
        shot.lifetime = .keepAlways
        add(shot)
    }

    func testBoostIsUnavailableOnOldFirmwareAndSaysWhy() {
        let app = launch("oldFirmware")
        // Motors on and connected, so the only thing standing in the way is
        // the firmware -- which is what the tap has to say.
        XCTAssertTrue(app.staticTexts["Motors on"].waitForExistence(timeout: 10))
        let boost = app.buttons["boost"]
        XCTAssertTrue(boost.waitForExistence(timeout: 5))
        waitForValue(boost, "Unavailable")
        boost.tap()
        XCTAssertTrue(app.staticTexts["Boost needs robot firmware 0.3.0 or newer"].waitForExistence(timeout: 3))
        attach(app, "Boost unavailable on firmware 0.2.9")
    }

    func testBoostIsReadyWhenTheRobotTakesIt() {
        let app = launch("healthy")
        XCTAssertTrue(app.staticTexts["Motors on"].waitForExistence(timeout: 10))
        let boost = app.buttons["boost"]
        XCTAssertTrue(boost.waitForExistence(timeout: 5))
        waitForValue(boost, "Released")
        XCTAssertFalse(app.staticTexts["robot-chip"].exists)
    }

    func testOneRobotChipPerCondition() {
        for (scenario, chip) in [("boosting", "Boost"), ("derated", "Motor derate"),
                                 ("motorsHot", "Motor heat"), ("batteryLow", "Battery low")] {
            let app = launch(scenario)
            let element = app.staticTexts["robot-chip"]
            XCTAssertTrue(element.waitForExistence(timeout: 10), "\(scenario): no chip")
            XCTAssertEqual(element.label, chip, scenario)
            XCTAssertEqual(app.staticTexts.matching(identifier: "robot-chip").count, 1, scenario)
            if scenario == "derated" {
                XCTAssertTrue(app.staticTexts["Motor driver hot: current reduced (level 2 of 3); boost off."].exists)
                waitForValue(app.buttons["boost"], "Unavailable")
            }
            attach(app, "Robot chip: \(chip)")
            app.terminate()
        }
    }

    func testBatteryCutoffCardHasNoClearButton() {
        let app = launch("batteryCutoff")
        XCTAssertTrue(app.staticTexts["Fault: Battery empty"].waitForExistence(timeout: 10))
        XCTAssertTrue(app.staticTexts["Battery empty: charge or swap the pack"].exists)
        XCTAssertFalse(app.buttons["clear-fault"].exists)
        attach(app, "Battery cutoff")
        app.terminate()

        // The same query does find Clear on a fault that can be cleared, so
        // the absence above means something.
        let slip = launch("faultedSlip")
        XCTAssertTrue(slip.staticTexts["Fault: Slip"].waitForExistence(timeout: 10))
        XCTAssertTrue(slip.buttons["clear-fault"].waitForExistence(timeout: 3))
    }
}
