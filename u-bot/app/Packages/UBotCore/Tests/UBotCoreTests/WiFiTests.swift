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
