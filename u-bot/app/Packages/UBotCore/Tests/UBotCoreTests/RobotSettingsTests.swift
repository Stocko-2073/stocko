import Foundation
import Testing
@testable import UBotCore

private let settingsOutput = "stored in NVS:\n  accel_tps2 8\neffective drive settings: vmax_tps=1 accel_tps2=1 decel_tps2=2 run_ma=1200\n"
private final class ManagementResults: @unchecked Sendable {
    private let lock = NSLock()
    private var storage: [Result<String, RobotSettingsError>] = []
    var values: [Result<String, RobotSettingsError>] { lock.withLock { storage } }
    func append(_ value: Result<String, RobotSettingsError>) { lock.withLock { storage.append(value) } }
}
private func message(_ fields: [String: Any]) -> Data { try! JSONSerialization.data(withJSONObject: fields) }

@Suite("Robot settings")
struct RobotSettingsTests {
    @Test func effectiveValuesOverrideStoredValues() throws {
        let settings = try DriveSettings(output: settingsOutput)
        #expect(settings[.topSpeed] == 1)
        #expect(settings[.acceleration] == 1)
        #expect(settings[.braking] == 2)
    }

    @Test func rejectIncompleteOrInvalidReadbacks() {
        for output in ["accel_tps2=1", "effective drive settings: vmax_tps=1 accel_tps2=1",
                       "effective drive settings: vmax_tps=nan accel_tps2=1 decel_tps2=2",
                       "effective drive settings: vmax_tps=3 accel_tps2=1 decel_tps2=2",
                       "effective drive settings: vmax_tps=1 accel_tps2=1 decel_tps2=2 accel_tps2=8"] {
            #expect(throws: RobotSettingsError.invalidResponse) { try DriveSettings(output: output) }
        }
    }

    @Test func readbackAccountsForFirmwareTextPrecision() {
        #expect(DriveSetting.acceleration.matchesReadback(19.1235, requested: 19.123456))
        #expect(!DriveSetting.acceleration.matchesReadback(19.12, requested: 19.123456))
        #expect(!DriveSetting.acceleration.matchesReadback(8, requested: 1))
    }

    @Test func firmwareRanges() {
        for setting in DriveSetting.allCases {
            #expect(setting.accepts(setting.range.lowerBound))
            #expect(setting.accepts(setting.range.upperBound))
            #expect(!setting.accepts(setting.range.lowerBound - 0.01))
            #expect(!setting.accepts(setting.range.upperBound + 0.01))
            #expect(!setting.accepts(.nan))
            #expect(!setting.accepts(.infinity))
        }
    }

    @Test func fragmentsRoundTripAtSmallAndLargeMTUs() throws {
        let data = message(["text": String(repeating: "turns/s²", count: 30)])
        for mtu in [20, 185, 512] {
            let frames = try ManagementFragments.encode(data, id: 259, mtu: mtu)
            var receiver = ManagementFragments()
            var result: Data?
            for frame in frames { result = try receiver.receive(frame, now: 10) }
            #expect(result == data)
        }
    }

    @Test func rejectBrokenFragmentSequences() throws {
        let frames = try ManagementFragments.encode(Data(repeating: 65, count: 60), id: 1, mtu: 20)
        var receiver = ManagementFragments()
        #expect(throws: RobotSettingsError.invalidResponse) { try receiver.receive(frames[1], now: 1) }
        receiver = ManagementFragments()
        _ = try receiver.receive(frames[0], now: 1)
        #expect(throws: RobotSettingsError.invalidResponse) { try receiver.receive(frames[2], now: 2) }
        receiver = ManagementFragments()
        _ = try receiver.receive(frames[0], now: 1)
        #expect(throws: RobotSettingsError.invalidResponse) { try receiver.receive(frames[1], now: 7) }
        #expect(throws: RobotSettingsError.invalidResponse) {
            try ManagementFragments.encode(Data(repeating: 65, count: 768), id: 1, mtu: 20)
        }
    }

    @Test func waitsForHelloAndRequiresFinished() {
        let queue = DispatchQueue(label: "settings.test")
        let client = ManagementSession(queue: queue)
        let results = ManagementResults()
        var requests: [Data] = []
        queue.sync {
            client.send = { requests.append($0) }
            client.request(["set"]) { results.append($0) }
            #expect(requests.isEmpty)
            client.receive(message(["type": "hello", "protocol": 1, "session": 42]))
            let request = try! JSONSerialization.jsonObject(with: requests[0]) as! [String: Any]
            #expect(request["session"] as? Int == 42)
            #expect(request["args"] as? [String] == ["set"])
            client.receive(message(["type": "accepted", "id": 1, "job": 5]))
            client.receive(message(["type": "output", "id": 1, "offset": 0, "data": settingsOutput]))
            #expect(results.values.isEmpty)
            client.receive(message(["type": "finished", "id": 1, "code": 0, "truncated": 0]))
            #expect(results.values == [.success(settingsOutput)])
        }
    }

    @Test func outputOffsetsAreUTF8BytesAndOtherRequestsAreIgnored() {
        let queue = DispatchQueue(label: "settings.test")
        let client = ManagementSession(queue: queue)
        let results = ManagementResults()
        queue.sync {
            client.receive(message(["type": "hello", "protocol": 1, "session": 1]))
            client.request(["set"]) { results.append($0) }
            client.receive(message(["type": "finished", "id": 99, "code": 0]))
            client.receive(message(["type": "output", "id": 1, "offset": 0, "data": "²"]))
            client.receive(message(["type": "output", "id": 1, "offset": 2, "data": "test"]))
            client.receive(message(["type": "finished", "id": 1, "code": 0]))
            #expect(results.values == [.success("²test")])
        }
    }

    @Test func incompleteOrRefusedResponsesCannotSucceed() {
        let failures: [[String: Any]] = [
            ["type": "output", "id": 1, "offset": 10, "data": "missing prefix"],
            ["type": "finished", "id": 1, "code": 0, "truncated": 1],
            ["type": "finished", "id": 1, "code": 0, "dropped": 1],
            ["type": "finished", "id": 1, "code": 1, "error": "Robot is busy"],
            ["type": "error", "id": 1, "error": "invalid session"],
        ]
        for failure in failures {
            let queue = DispatchQueue(label: "settings.test")
            let client = ManagementSession(queue: queue)
            let results = ManagementResults()
            queue.sync {
                client.receive(message(["type": "hello", "protocol": 1, "session": 1]))
                client.request(["set"]) { results.append($0) }
                client.receive(message(failure))
                client.receive(message(["type": "finished", "id": 1, "code": 0]))
                #expect(results.values.count == 1)
                if case .success = results.values.first { Issue.record("Invalid response accepted") }
            }
        }
    }

    @Test func disconnectDoesNotReplayPendingWrite() {
        let queue = DispatchQueue(label: "settings.test")
        let client = ManagementSession(queue: queue)
        let results = ManagementResults()
        var sent = 0
        queue.sync {
            client.send = { _ in sent += 1 }
            client.receive(message(["type": "hello", "protocol": 1, "session": 1]))
            client.request(["set", "accel_tps2", "1"]) { results.append($0) }
            client.reset()
            client.receive(message(["type": "hello", "protocol": 1, "session": 2]))
            client.receive(message(["type": "finished", "id": 1, "code": 0]))
            #expect(sent == 1)
            #expect(results.values == [.failure(.disconnected)])
        }
    }

    @Test func timeoutAndConcurrentRequests() async throws {
        let queue = DispatchQueue(label: "settings.test")
        let client = ManagementSession(queue: queue, timeout: 0.02)
        let first = ManagementResults(), second = ManagementResults()
        queue.sync {
            client.request(["set"]) { first.append($0) }
            client.request(["set"]) { second.append($0) }
        }
        try await Task.sleep(for: .milliseconds(60))
        queue.sync {
            #expect(first.values == [.failure(.timeout)])
            #expect(second.values == [.failure(.busy)])
            client.receive(message(["type": "hello", "protocol": 1, "session": 1]))
            #expect(first.values.count == 1)
        }
    }
}
