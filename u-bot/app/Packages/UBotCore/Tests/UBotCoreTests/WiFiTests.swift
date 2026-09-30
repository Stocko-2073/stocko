import Foundation
import Testing
@testable import UBotCore

private let statusJSON = #"{"t":"status","name":"ubot","fw":"0.1.5","enabled":true,"faulted":false,"fault_wheel":"A","cmd":{"v":0.12,"w":-0.3,"active":true},"batt":{"present":true,"v":13.08,"pct":75},"wheels":[{"name":"B","vel":-0.2,"enc":true,"fault":0},{"name":"A","vel":0.2,"enc":true,"fault":0}]}"#

private final class FakeSocket: RobotWebSocket, @unchecked Sendable {
    let lock = NSLock()
    private var frames: [String] = []
    private var receiver: ((Result<String, Error>) -> Void)?
    private var completions: [(Error?) -> Void] = []
    private var closed = false
    var automatic = true
    var sent: [String] { lock.withLock { frames } }
    var isClosed: Bool { lock.withLock { closed } }
    func send(_ text: String, completion: @escaping (Error?) -> Void) {
        lock.withLock { frames.append(text); if !automatic { completions.append(completion) } }
        if automatic { completion(nil) }
    }
    func receive(_ completion: @escaping (Result<String, Error>) -> Void) {
        lock.withLock { receiver = completion }
    }
    func deliver(_ text: String) {
        let callback = lock.withLock { let c = receiver; receiver = nil; return c }
        callback?(.success(text))
    }
    func complete() {
        let callbacks = lock.withLock { let c = completions; completions = []; return c }
        callbacks.forEach { $0(nil) }
    }
    func close() { lock.withLock { closed = true } }
}
private final class Events: @unchecked Sendable {
    private let lock = NSLock()
    private var storage: [LinkEvent] = []
    var values: [LinkEvent] { lock.withLock { storage } }
    func append(_ value: LinkEvent) { lock.withLock { storage.append(value) } }
}
private final class Clock: @unchecked Sendable {
    private let lock = NSLock()
    private var value: TimeInterval = 0
    var time: TimeInterval { lock.withLock { value } }
    func advance(_ amount: TimeInterval) { lock.withLock { value += amount } }
}
private func flush(_ link: WiFiRobotLink) { link.synchronize(); link.synchronize() }

@Suite("Wi-Fi protocol")
struct WiFiProtocolTests {
    @Test func addresses() {
        #expect(WiFiProtocol.endpoint("ubot.local")?.absoluteString == "ws://ubot.local/ws")
        #expect(WiFiProtocol.endpoint(" 192.168.1.47:8080 ")?.absoluteString == "ws://192.168.1.47:8080/ws")
        #expect(WiFiProtocol.endpoint("[::1]:80") != nil)
        for value in ["", "http://ubot.local", "ubot.local/ws", "user@host", "host:0", "host:65536", "host name", "host?x"] {
            #expect(WiFiProtocol.endpoint(value) == nil)
        }
    }
    @Test func status() throws {
        let frame = try JSONDecoder().decode(WiFiProtocol.Status.self, from: Data(statusJSON.utf8))
        let s = try #require(frame.model())
        #expect(s.batteryMillivolts == 13080)
        #expect(s.batteryPercent == 75)
        #expect(s.wheelATurnsPerSec == 0.2)
        #expect(s.wheelBTurnsPerSec == -0.2)
        #expect(s.commandedMetersPerSec == 0.12)
        #expect(s.commandedRadiansPerSec == -0.3)
        #expect(s.isEnabled && s.encoderAOK && s.encoderBOK)
        #expect(s.busyReason == nil)
    }
    @Test func busyAndFaults() throws {
        let fault = statusJSON.replacingOccurrences(of: "\"faulted\":false", with: "\"faulted\":true")
            .replacingOccurrences(of: "\"fault\":0", with: "\"fault\":5")
        let data = Data(fault.utf8)
        #expect(try JSONDecoder().decode(WiFiProtocol.Status.self, from: data).model()?.fault == .driver)
        let unknown = fault.replacingOccurrences(of: "\"fault\":5", with: "\"fault\":99")
        #expect(try JSONDecoder().decode(WiFiProtocol.Status.self, from: Data(unknown.utf8)).model()?.fault == .unknown)
        for extra in ["\"cal\":true", "\"demo\":\"short\"", "\"ota\":{\"busy\":true}"] {
            let text = statusJSON.dropLast() + "," + extra + "}"
            let s = try #require(JSONDecoder().decode(WiFiProtocol.Status.self, from: Data(text.utf8)).model())
            #expect(s.busyReason != nil)
            #expect(DriveLock.derive(linkState: .ready(name: "ubot"), status: s) != nil)
        }
    }
    @Test func commands() throws {
        let json = try #require(JSONSerialization.jsonObject(with: Data(WiFiProtocol.drive(.init(v: 0.5, w: -0.2)).utf8)) as? [String: Any])
        #expect(json["v"] as? Double == 0.5)
        #expect(json["w"] as? Double == -0.2)
        #expect(json["hold"] as? Int == 500)
        #expect(ControlOp.allCases.map(WiFiProtocol.command) == ["stop", "enable", "disable", "estop", "clear"])
    }
}

@Suite("Wi-Fi connection lifecycle")
struct WiFiLinkTests {
    @Test func acknowledgementAndRefusal() {
        let socket = FakeSocket(); let events = Events()
        let link = WiFiRobotLink(address: "ubot.local", makeSocket: { _ in socket })
        link.onEvent = { events.append($0) }
        link.start(); flush(link)
        socket.deliver(statusJSON); flush(link)
        link.send(.enable); link.send(.clearFaults); flush(link)
        #expect(socket.sent == [#"{"t":"enable"}"#])
        #expect(!events.values.contains { if case .controlAccepted = $0 { return true }; return false })
        socket.deliver(#"{"t":"ack","cmd":"enable","ok":false,"err":"driver unavailable"}"#); flush(link)
        #expect(socket.sent.last == #"{"t":"clear"}"#)
        #expect(events.values.contains { if case .controlRefused(.enable, "driver unavailable") = $0 { return true }; return false })
        socket.deliver(#"{"t":"ack","cmd":"clear","ok":true}"#); flush(link)
        #expect(events.values.contains { if case .controlAccepted(.clearFaults) = $0 { return true }; return false })
        link.stop(); flush(link)
    }
    @Test func backpressureAndRelease() {
        let socket = FakeSocket(); socket.automatic = false
        let link = WiFiRobotLink(address: "ubot.local", makeSocket: { _ in socket })
        link.start(); flush(link); socket.deliver(statusJSON); flush(link)
        link.engage(.init(v: 0.3, w: 0)); flush(link)
        for _ in 0..<100 { link.update(.init(v: 0.9, w: 0)) }
        flush(link); link.checkTimers()
        #expect(socket.sent.count == 1)
        link.releaseStick(); flush(link)
        socket.complete(); flush(link); link.checkTimers()
        #expect(socket.sent.last == WiFiProtocol.drive(.zero))
        #expect(!socket.sent.contains(WiFiProtocol.drive(.init(v: 0.9, w: 0))))
        link.stop(); flush(link)
    }
    @Test func estopPrioritizesAndDoesNotReplay() {
        let socket = FakeSocket()
        let link = WiFiRobotLink(address: "ubot.local", makeSocket: { _ in socket })
        link.start(); flush(link); socket.deliver(statusJSON); flush(link)
        link.send(.enable); link.send(.clearFaults); link.send(.estop); flush(link)
        #expect(socket.sent.last == #"{"t":"estop"}"#)
        #expect(!socket.sent.contains(#"{"t":"clear"}"#))
        socket.deliver(#"{"t":"ack","cmd":"enable","ok":true}"#); flush(link)
        socket.deliver(#"{"t":"ack","cmd":"estop","ok":true}"#); flush(link)
        link.checkTimers()
        #expect(socket.sent.last == #"{"t":"estop"}"#)
        link.stop(); flush(link)
    }
    @Test func staleTelemetryAndRetiredCallbacks() {
        let socket = FakeSocket(); let clock = Clock(); let events = Events()
        let link = WiFiRobotLink(address: "ubot.local", makeSocket: { _ in socket }, now: { clock.time })
        link.onEvent = { events.append($0) }
        link.start(); flush(link); socket.deliver(statusJSON); flush(link)
        link.engage(.init(v: 0.3, w: 0)); flush(link)
        // Invalid JSON/status must not refresh the valid-telemetry watchdog.
        socket.deliver(#"{"t":"status","enabled":true}"#); flush(link)
        clock.advance(1.6); link.checkTimers(); flush(link)
        #expect(socket.isClosed)
        #expect(events.values.contains { if case .state(.reconnecting) = $0 { return true }; return false })
        let before = events.values.count
        socket.deliver(statusJSON); flush(link)
        #expect(events.values.count == before)
        link.stop(); flush(link)
        #expect(socket.sent.last == WiFiProtocol.drive(.zero))
    }
    @Test func noOldMotionAfterRestart() {
        let first = FakeSocket(); let second = FakeSocket()
        var sockets = [first, second]
        let link = WiFiRobotLink(address: "ubot.local", makeSocket: { _ in sockets.removeFirst() })
        link.start(); flush(link); first.deliver(statusJSON); flush(link)
        link.engage(.init(v: 0.8, w: 0)); flush(link)
        link.stop(); flush(link); link.start(); flush(link)
        first.deliver(statusJSON); flush(link)
        second.deliver(statusJSON); flush(link)
        link.update(.init(v: 0.7, w: 0)); flush(link); link.checkTimers()
        #expect(second.sent.isEmpty)
        link.engage(.init(v: 0.2, w: 0)); flush(link)
        #expect(second.sent.first == WiFiProtocol.drive(.init(v: 0.2, w: 0)))
        link.stop(); flush(link)
    }
    @Test func driveRefusalStopsTicker() {
        let socket = FakeSocket(); let events = Events()
        let link = WiFiRobotLink(address: "ubot.local", makeSocket: { _ in socket })
        link.onEvent = { events.append($0) }
        link.start(); flush(link); socket.deliver(statusJSON); flush(link)
        link.engage(.init(v: 0.2, w: 0)); flush(link)
        socket.deliver(#"{"t":"ack","cmd":"drive","ok":false,"err":"disabled"}"#); flush(link)
        let count = socket.sent.count
        link.checkTimers()
        #expect(socket.sent.count == count)
        #expect(events.values.contains { if case .message("Drive refused: disabled") = $0 { return true }; return false })
        link.stop(); flush(link)
    }
}

extension WiFiLinkTests {
    @Test func blockedSendClosesConnection() {
        let socket = FakeSocket(); socket.automatic = false
        let clock = Clock()
        let link = WiFiRobotLink(address: "ubot.local", makeSocket: { _ in socket }, now: { clock.time })
        link.start(); flush(link); socket.deliver(statusJSON); flush(link)
        link.engage(.init(v: 0.2, w: 0)); flush(link)
        clock.advance(0.6); link.checkTimers()
        #expect(socket.isClosed)
        socket.complete(); flush(link)
        #expect(socket.sent.count == 1)
        link.stop(); flush(link)
    }
    @Test func acknowledgementTimeout() {
        let socket = FakeSocket(); let clock = Clock(); let events = Events()
        let link = WiFiRobotLink(address: "ubot.local", makeSocket: { _ in socket }, now: { clock.time })
        link.onEvent = { events.append($0) }
        link.start(); flush(link); socket.deliver(statusJSON); flush(link)
        link.send(.enable); flush(link)
        clock.advance(2.1)
        socket.deliver(statusJSON); flush(link)
        link.checkTimers()
        #expect(socket.isClosed)
        #expect(events.values.contains { if case .controlRefused(.enable, _) = $0 { return true }; return false })
        link.stop(); flush(link)
    }
    @Test func automaticReconnectDoesNotResumeDrive() async throws {
        let first = FakeSocket(), second = FakeSocket(); let clock = Clock()
        var sockets = [first, second]
        let link = WiFiRobotLink(address: "ubot.local", makeSocket: { _ in sockets.removeFirst() }, now: { clock.time })
        link.start(); flush(link); first.deliver(statusJSON); flush(link)
        link.engage(.init(v: 0.2, w: 0)); flush(link)
        clock.advance(1.6); link.checkTimers()
        try await Task.sleep(for: .milliseconds(1150))
        flush(link); second.deliver(statusJSON); flush(link)
        link.checkTimers()
        #expect(second.sent.isEmpty)
        link.stop(); flush(link)
    }
    @Test func stopCancelsReconnect() async throws {
        let socket = FakeSocket(); let clock = Clock()
        let lock = NSLock()
        var connections = 0
        let link = WiFiRobotLink(address: "ubot.local", makeSocket: { _ in
            lock.withLock { connections += 1 }; return socket
        }, now: { clock.time })
        link.start(); flush(link); socket.deliver(statusJSON); flush(link)
        clock.advance(1.6); link.checkTimers()
        link.stop(); flush(link)
        try await Task.sleep(for: .milliseconds(1150))
        #expect(lock.withLock { connections } == 1)
    }
}

@Suite("Wi-Fi robot settings")
struct WiFiSettingsTests {
    @Test func settingsUseManagementSocketAndDoNotReplayAfterDisconnect() {
        let drive = FakeSocket(), management = FakeSocket()
        let results = SettingsResults()
        let link = WiFiRobotLink(address: "ubot.local", makeSocket: { url in
            url.path == "/manage" ? management : drive
        })
        link.start(); flush(link)
        drive.deliver(statusJSON); flush(link)
        link.executeManagement(["set", "accel_tps2", "1"]) { results.append($0) }
        flush(link)
        management.deliver(#"{"type":"hello","protocol":1,"session":42}"#); flush(link)
        #expect(management.sent.count == 1)
        #expect(drive.sent.isEmpty)
        let request = try! JSONSerialization.jsonObject(with: Data(management.sent[0].utf8)) as! [String: Any]
        #expect(request["args"] as? [String] == ["set", "accel_tps2", "1"])
        link.stop(); flush(link)
        management.deliver(#"{"type":"finished","id":1,"code":0}"#); flush(link)
        #expect(results.values == [.failure(.disconnected)])
        #expect(management.isClosed)
        #expect(management.sent.count == 1)
    }

    @Test func completeManagementResponseReachesCaller() {
        let drive = FakeSocket(), management = FakeSocket()
        let results = SettingsResults()
        let link = WiFiRobotLink(address: "ubot.local", makeSocket: { url in
            url.path == "/manage" ? management : drive
        })
        link.start(); flush(link)
        drive.deliver(statusJSON); flush(link)
        link.executeManagement(["set"]) { results.append($0) }; flush(link)
        management.deliver(#"{"type":"hello","protocol":1,"session":42}"#); flush(link)
        management.deliver(#"{"type":"output","id":1,"offset":0,"data":"settings"}"#); flush(link)
        #expect(results.values.isEmpty)
        management.deliver(#"{"type":"finished","id":1,"code":0}"#); flush(link)
        #expect(results.values == [.success("settings")])
        link.stop(); flush(link)
    }
}

private final class SettingsResults: @unchecked Sendable {
    private let lock = NSLock()
    private var storage: [Result<String, RobotSettingsError>] = []
    var values: [Result<String, RobotSettingsError>] { lock.withLock { storage } }
    func append(_ result: Result<String, RobotSettingsError>) { lock.withLock { storage.append(result) } }
}

// MARK: - 0.2.9 / 0.3.0 status fields and Boost

/// A 0.3.0-and-later status: capability, battery state, torque on both wheels,
/// a recovery in progress, and a load estimate on wheel B only.
private let torqueStatusJSON = #"{"t":"status","name":"ubot","fw":"0.3.1","enabled":true,"faulted":false,"fault":null,"fault_wheel":"A","fault_code":0,"caps":["boost"],"cmd":{"v":0,"w":0,"active":false},"batt":{"present":true,"v":19.97,"pct":79,"state":"ok","pack":"li5s"},"wheels":[{"name":"A","vel":0,"enc":true,"fault":0,"torque":{"run":1160,"hold":552,"boost":2,"act":true,"h":0.83,"hot":false,"derate":0,"otpw":false},"lag":3,"trips":0,"load":null,"lim":false},{"name":"B","vel":0,"enc":true,"fault":0,"torque":{"run":1160,"hold":552,"boost":0,"act":false,"h":1.12,"hot":true,"derate":2,"otpw":true},"lag":-2,"trips":1,"load":41.5,"lim":false}],"rec":{"on":true,"state":"ramp","try":2,"wheels":2,"n":9,"ok":6,"fail":1}}"#

private func decode(_ json: String) throws -> UBotStatus {
    try #require(JSONDecoder().decode(WiFiProtocol.Status.self, from: Data(json.utf8)).model())
}

@Suite("Wi-Fi status, newer fields")
struct WiFiStatusFieldTests {

    @Test("firmware without the new fields decodes exactly as before")
    func withoutNewFields() throws {
        let s = try decode(statusJSON)
        #expect(s.flags2 == [])
        #expect(!s.acceptsBoost)
        #expect(s.batteryState == nil && s.batteryPack == nil)
        #expect(s.heatA == nil && s.heatB == nil && s.derateLevel == nil)
        #expect(s.recoveryCount == nil && s.recoveryWheels == nil)
        #expect(s.frameLength == nil)
        #expect(s.fault == .none && s.batteryPercent == 75)
    }

    @Test("caps, battery, torque and recovery rebuild the BLE fields")
    func withNewFields() throws {
        let s = try decode(torqueStatusJSON)
        #expect(s.acceptsBoost)
        #expect(s.isBoosting)                                   // A granted a start boost
        #expect(!s.flags2.contains(.boostRequested))            // nobody asked: reason 2 is START
        #expect(s.isDerated && s.flags2.contains(.otpw))        // B at level 2
        #expect(s.isHeatLimited)                                // B is hot
        #expect(s.isRecovering)                                 // "ramp"
        #expect(s.flags2.contains(.loadValid))                  // B has an estimate
        #expect(s.heatA == 0.83 && s.heatB == 1.12)
        #expect(s.derateA == 0 && s.derateB == 2 && s.derateLevel == 2)
        #expect(s.recoveryCount == 9)
        #expect(s.recoveryWheels == 2)
        #expect(s.batteryState == .ok && s.batteryPack == "li5s")
        #expect(s.fault == .none)
    }

    @Test("manual boost shows as requested; an idle recovery is not recovering")
    func requestedAndIdle() throws {
        let json = torqueStatusJSON
            .replacingOccurrences(of: #""boost":0,"act":false"#, with: #""boost":9,"act":false"#)
            .replacingOccurrences(of: #""state":"ramp""#, with: #""state":"idle""#)
            .replacingOccurrences(of: #""load":41.5"#, with: #""load":null"#)
        let s = try decode(json)
        #expect(s.flags2.contains(.boostRequested))
        #expect(!s.isRecovering)
        #expect(!s.flags2.contains(.loadValid))
    }

    @Test(arguments: [("none", BatteryState.none), ("ok", .ok), ("low", .low),
                      ("cutoff", .cutoff), ("flat", .unknown)])
    func batteryStateNames(name: String, expected: BatteryState) throws {
        let s = try decode(torqueStatusJSON.replacingOccurrences(of: #""state":"ok""#, with: "\"state\":\"\(name)\""))
        #expect(s.batteryState == expected)
    }

    @Test("fault_code wins over the faulting wheel's own code")
    func faultCodeWins() throws {
        let faulted = torqueStatusJSON.replacingOccurrences(of: #""faulted":false"#, with: #""faulted":true"#)
        // Robot-level: no wheel to look up, and both wheels report 0.
        let battery = faulted
            .replacingOccurrences(of: #""fault_wheel":"A""#, with: #""fault_wheel":"-""#)
            .replacingOccurrences(of: #""fault_code":0"#, with: #""fault_code":6"#)
        #expect(try decode(battery).fault == .battery)
        // A wheel-level code that disagrees with the wheel: the code wins.
        let blocked = faulted
            .replacingOccurrences(of: #""fault_code":0"#, with: #""fault_code":7"#)
            .replacingOccurrences(of: #""enc":true,"fault":0,"torque":{"run":1160,"hold":552,"boost":2"#,
                                  with: #""enc":true,"fault":1,"torque":{"run":1160,"hold":552,"boost":2"#)
        #expect(try decode(blocked).fault == .blocked)
        // Not faulted means no fault, whatever the code says.
        #expect(try decode(battery.replacingOccurrences(of: #""faulted":true"#, with: #""faulted":false"#)).fault
                == .none)
    }

    @Test("without fault_code, a wheel is still looked up by name, and \"-\" names none")
    func faultWithoutCode() throws {
        let faulted = statusJSON.replacingOccurrences(of: #""faulted":false"#, with: #""faulted":true"#)
        let onB = faulted
            .replacingOccurrences(of: #""fault_wheel":"A""#, with: #""fault_wheel":"B""#)
            .replacingOccurrences(of: #""vel":-0.2,"enc":true,"fault":0"#, with: #""vel":-0.2,"enc":true,"fault":3"#)
        #expect(try decode(onB).fault == .magnet)
        let robot = faulted.replacingOccurrences(of: #""fault_wheel":"A""#, with: #""fault_wheel":"-""#)
        #expect(try decode(robot).fault == .unknown)
    }

    @Test("a malformed newer field costs that field, never the frame")
    func lenient() throws {
        let broken = torqueStatusJSON
            .replacingOccurrences(of: #""caps":["boost"]"#, with: #""caps":"boost""#)
            .replacingOccurrences(of: #""h":1.12"#, with: #""h":"warm""#)
            .replacingOccurrences(of: #""rec":{"on":true"#, with: #""rec":[1],"old":{"on":true"#)
            .replacingOccurrences(of: #""fault_code":0"#, with: #""fault_code":"none""#)
            .replacingOccurrences(of: #""state":"ok""#, with: #""state":2"#)
        let s = try decode(broken)
        #expect(!s.acceptsBoost)
        #expect(s.heatA == 0.83)                    // wheel A's torque object is intact
        #expect(s.heatB == nil && s.derateB == nil) // wheel B's is dropped whole
        #expect(s.recoveryCount == nil && !s.isRecovering)
        #expect(s.batteryState == nil)
        #expect(s.fault == .none)
        #expect(s.isEnabled && s.batteryPercent == 79)
    }

    @Test("drive frames: the boost key only while boosting, and zero byte-identical to before")
    func driveJSON() throws {
        #expect(WiFiProtocol.drive(.zero) == #"{"t":"drive","v":0.0,"w":0.0,"hold":500}"#)
        let c = DriveCommand(v: 0.5, w: -0.2)
        #expect(WiFiProtocol.drive(c, boost: false) == WiFiProtocol.drive(c))
        let plain = try #require(JSONSerialization.jsonObject(with: Data(WiFiProtocol.drive(c).utf8)) as? [String: Any])
        #expect(plain["boost"] == nil)
        let boosted = try #require(JSONSerialization.jsonObject(
            with: Data(WiFiProtocol.drive(c, boost: true).utf8)) as? [String: Any])
        #expect(boosted["boost"] as? Bool == true)
        #expect(boosted["v"] as? Double == 0.5 && boosted["w"] as? Double == -0.2)
        #expect(boosted["hold"] as? Int == 500)
    }
}

@Suite("Wi-Fi Boost")
struct WiFiBoostTests {
    private let boostedZero = WiFiProtocol.drive(.zero, boost: true)

    private func connected(_ socket: FakeSocket) -> WiFiRobotLink {
        let link = WiFiRobotLink(address: "ubot.local", makeSocket: { _ in socket })
        link.start(); flush(link)
        socket.deliver(torqueStatusJSON); flush(link)
        return link
    }

    @Test("with the stick, frames carry the command and the flag until Boost is let go")
    func withStick() {
        let socket = FakeSocket()
        let link = connected(socket)
        let c = DriveCommand(v: 0.3, w: 0)
        link.engage(c); link.setBoost(true); flush(link); link.checkTimers()
        #expect(socket.sent.last == WiFiProtocol.drive(c, boost: true))
        link.setBoost(false); flush(link); link.checkTimers()
        #expect(socket.sent.last == WiFiProtocol.drive(c))
        link.stop(); flush(link)
    }

    @Test("without the stick, Boost keeps zero frames with the flag flowing")
    func withoutStick() {
        let socket = FakeSocket()
        let link = connected(socket)
        link.setBoost(true); flush(link)
        for _ in 0..<4 { link.checkTimers(); flush(link) }
        #expect(socket.sent.count >= 4)
        #expect(socket.sent.allSatisfy { $0 == boostedZero })
        link.stop(); flush(link)
    }

    @Test("a stick release while boosting braces with no plain zeros; letting go then ends on the tail")
    func release() {
        let socket = FakeSocket()
        let link = connected(socket)
        let c = DriveCommand(v: 0.3, w: 0)
        link.engage(c); link.setBoost(true); flush(link); link.checkTimers()
        // The link's own 10 Hz timer may slip one more frame of the previous
        // kind in between reading a mark and the next call landing.
        let released = socket.sent.count
        link.releaseStick(); flush(link)
        for _ in 0..<4 { link.checkTimers(); flush(link) }
        let brace = Array(socket.sent.dropFirst(released).drop { $0 == WiFiProtocol.drive(c, boost: true) })
        #expect(!brace.isEmpty)
        #expect(brace.allSatisfy { $0 == boostedZero })
        let letGo = socket.sent.count
        link.setBoost(false); flush(link)
        for _ in 0..<6 { link.checkTimers(); flush(link) }
        let tail = Array(socket.sent.dropFirst(letGo).drop { $0 == boostedZero })
        #expect(tail == Array(repeating: WiFiProtocol.drive(.zero), count: 3))
        link.stop(); flush(link)
    }

    @Test("a faulted status stops the brace at once")
    func faultStops() {
        let socket = FakeSocket()
        let link = connected(socket)
        link.setBoost(true); flush(link); link.checkTimers()
        socket.deliver(torqueStatusJSON.replacingOccurrences(of: #""faulted":false"#, with: #""faulted":true"#))
        flush(link)
        let count = socket.sent.count
        for _ in 0..<3 { link.checkTimers(); flush(link) }
        #expect(socket.sent.count == count)
        link.stop(); flush(link)
    }

    @Test("stop, disable and E-STOP each clear Boost")
    func controlsClear() {
        for op in [ControlOp.stop, .disable, .estop] {
            let socket = FakeSocket()
            let link = connected(socket)
            link.setBoost(true); flush(link); link.checkTimers()
            link.send(op); flush(link)
            socket.deliver("{\"t\":\"ack\",\"cmd\":\"\(WiFiProtocol.command(op))\",\"ok\":true}"); flush(link)
            let count = socket.sent.count
            for _ in 0..<3 { link.checkTimers(); flush(link) }
            #expect(socket.sent.count == count, "\(op) left Boost running")
            link.stop(); flush(link)
        }
    }

    @Test("Boost needs a connection, and never survives a reconnect")
    func connectionBound() {
        let first = FakeSocket(), second = FakeSocket()
        var sockets = [first, second]
        let link = WiFiRobotLink(address: "ubot.local", makeSocket: { _ in sockets.removeFirst() })
        link.start(); flush(link)
        link.setBoost(true); flush(link)            // before any status: ignored
        first.deliver(torqueStatusJSON); flush(link); link.checkTimers()
        #expect(first.sent.isEmpty)
        link.setBoost(true); flush(link); link.checkTimers()
        #expect(first.sent.last == boostedZero)
        link.stop(); flush(link); link.start(); flush(link)
        second.deliver(torqueStatusJSON); flush(link)
        for _ in 0..<3 { link.checkTimers(); flush(link) }
        #expect(second.sent.isEmpty)
        link.stop(); flush(link)
    }
}
