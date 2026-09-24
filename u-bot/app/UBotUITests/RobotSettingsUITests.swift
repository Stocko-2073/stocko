import XCTest

final class RobotSettingsUITests: XCTestCase {
    func testReadEditValidateAndSaveAcceleration() {
        let app = XCUIApplication()
        app.launchArguments = ["-connectionTransport", "ble"] // Simulator uses the mock, never the yard robot.
        app.launch()
        XCTAssertTrue(app.buttons["Settings"].waitForExistence(timeout: 10))
        app.buttons["Settings"].tap()
        app.buttons["Motion settings"].tap()
        let acceleration = app.buttons["setting-accel_tps2"]
        XCTAssertTrue(acceleration.waitForExistence(timeout: 5))
        acceleration.tap()
        let input = app.textFields["setting-value"]
        XCTAssertTrue(input.waitForExistence(timeout: 3))
        replace(input, with: "0.1")
        XCTAssertFalse(app.buttons["Save"].isEnabled)
        replace(input, with: "2")
        XCTAssertTrue(app.buttons["Save"].isEnabled)
        app.buttons["Save"].tap()
        XCTAssertTrue(acceleration.waitForExistence(timeout: 5))
        XCTAssertTrue(app.staticTexts["Saved acceleration to the robot: 2 turns/s²."].exists)
        let shot = XCTAttachment(screenshot: app.screenshot())
        shot.name = "Robot motion settings — verified save"
        shot.lifetime = .keepAlways
        add(shot)
    }

    private func replace(_ field: XCUIElement, with value: String) {
        field.tap()
        let text = field.value as? String ?? ""
        field.typeText(String(repeating: XCUIKeyboardKey.delete.rawValue, count: text.count) + value)
    }
}
