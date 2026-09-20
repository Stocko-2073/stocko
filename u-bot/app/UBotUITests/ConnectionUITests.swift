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


final class CameraUITests: XCTestCase {
    func testCameraStartsAndResumesAfterBackground() throws {
        #if targetEnvironment(simulator)
        throw XCTSkip("Camera capture requires a physical iPhone.")
        #else
        let app = XCUIApplication()
        addUIInterruptionMonitor(withDescription: "Camera permission") { alert in
            let allow = alert.buttons["Allow"]
            if allow.exists { allow.tap(); return true }
            let ok = alert.buttons["OK"]
            if ok.exists { ok.tap(); return true }
            return false
        }
        app.launch()
        let camera = app.descendants(matching: .any)["Live camera"].firstMatch
        XCTAssertTrue(camera.waitForExistence(timeout: 10))
        let running = NSPredicate(format: "value == %@", "Running")
        expectation(for: running, evaluatedWith: camera)
        waitForExpectations(timeout: 10)
        attachCamera(app, name: "Camera on launch")

        XCUIDevice.shared.press(.home)
        XCTAssertTrue(app.wait(for: .runningBackground, timeout: 5))
        app.activate()
        XCTAssertTrue(camera.waitForExistence(timeout: 10))
        expectation(for: running, evaluatedWith: camera)
        waitForExpectations(timeout: 10)
        attachCamera(app, name: "Camera after reopening")
        #endif
    }

    private func attachCamera(_ app: XCUIApplication, name: String) {
        let shot = XCTAttachment(screenshot: app.screenshot())
        shot.name = name
        shot.lifetime = .keepAlways
        add(shot)
    }
}
