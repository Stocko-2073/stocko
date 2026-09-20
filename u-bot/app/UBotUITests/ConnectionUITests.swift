import XCTest

final class ConnectionUITests: XCTestCase {
    func testSelectorAndAddressSettings() {
        let app = XCUIApplication()
        app.launchArguments = ["-connectionTransport", "ble"]
        app.launch()
        let selector = app.segmentedControls["Robot connection"]
        XCTAssertTrue(selector.waitForExistence(timeout: 10))
        XCTAssertTrue(selector.buttons["BLE"].isHittable)
        XCTAssertTrue(selector.buttons["Wi-Fi"].isHittable)
        app.buttons["Connection settings"].tap()
        let address = app.textFields["Robot address"]
        XCTAssertTrue(address.waitForExistence(timeout: 3))
        app.buttons["Reset to ubot.local"].tap()
        XCTAssertEqual(address.value as? String, "ubot.local")
        app.buttons["Save"].tap()
        XCTAssertTrue(selector.waitForExistence(timeout: 3))
        let shot = XCTAttachment(screenshot: app.screenshot())
        shot.name = "Small iPhone connection selector"
        shot.lifetime = .keepAlways
        add(shot)
    }
}
