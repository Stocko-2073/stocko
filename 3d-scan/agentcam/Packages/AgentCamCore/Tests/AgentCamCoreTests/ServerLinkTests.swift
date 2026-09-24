import Foundation
import Testing
@testable import AgentCamCore

final class FakeSocket: ServerWebSocket, @unchecked Sendable {
    var sent: [String] = []
    var closed = false
    var pendingReceive: ((Result<String, Error>) -> Void)?
    var pendingSend: ((Error?) -> Void)?
    var holdSends = false

    func send(_ text: String, completion: @escaping (Error?) -> Void) {
        sent.append(text)
        if holdSends { pendingSend = completion } else { completion(nil) }
    }
    func receive(_ completion: @escaping (Result<String, Error>) -> Void) { pendingReceive = completion }
    func close() { closed = true }

    func deliver(_ text: String) {
        let c = pendingReceive
        pendingReceive = nil
        c?(.success(text))
    }
    func drop(_ error: Error = URLError(.networkConnectionLost)) {
        let c = pendingReceive
        pendingReceive = nil
        c?(.failure(error))
    }
    func types() -> [String] { sent.compactMap { Wire.messageType(Data($0.utf8)) } }
}

final class Box<T>: @unchecked Sendable {
    var value: T
    init(_ value: T) { self.value = value }
}

final class Harness: @unchecked Sendable {
    var clock: TimeInterval = 100
    var sockets: [FakeSocket] = []
    var events: [ServerLinkEvent] = []
    var endpoint: URL? = URL(string: "http://Honeypot.local:47815")
    let lock = NSLock()
    lazy var link: ServerLink = {
        let l = ServerLink(endpoint: { [unowned self] in self.endpoint },
                           hello: { Hello(device: .init(model: "test", ios: "0", app: "0"), lenses: [], lidar: false) },
                           makeSocket: { [unowned self] _ in let s = FakeSocket(); self.sockets.append(s); return s },
                           now: { [unowned self] in self.clock })
        l.onEvent = { [unowned self] e in self.lock.lock(); self.events.append(e); self.lock.unlock() }
        return l
    }()
    var socket: FakeSocket { sockets.last! }
    func states() -> [ServerLinkState] {
        lock.lock(); defer { lock.unlock() }
        return events.compactMap { if case .state(let s) = $0 { s } else { nil } }
    }
    func welcome() {
        socket.deliver(#"{"t":"welcome","v":1,"server_id":"abc","mat":{"dictionary":"DICT_4X4_100","print_scale":[1,1]}}"#)
        link.synchronize()
    }
}

@Suite struct ServerLinkTests {
    @Test func saysHelloFirstAndConnectsOnWelcome() throws {
        let h = Harness()
        h.link.start(); h.link.synchronize()
        #expect(h.socket.types() == ["hello"])
        h.link.send(update: RequestUpdate(id: "r0001", reason: "no"))
        h.link.synchronize()
        #expect(h.socket.types() == ["hello"])                   // nothing else before welcome
        h.welcome()
        #expect(h.socket.types() == ["hello", "request_update"])
        #expect(h.states().last == .connected(host: "Honeypot.local"))
    }

    @Test func deliversRequestSnapshots() throws {
        let h = Harness()
        h.link.start(); h.link.synchronize(); h.welcome()
        h.socket.deliver(String(decoding: try example("requests.json"), as: UTF8.self))
        h.link.synchronize()
        let snaps = h.events.compactMap { if case .requests(let s) = $0 { s } else { nil } }
        #expect(snaps.first?.items.count == 3)
    }

    @Test func silenceMeansReconnect() {
        let h = Harness()
        h.link.start(); h.link.synchronize(); h.welcome()
        h.clock += ServerLink.silenceLimit - 1
        h.link.checkTimers()
        #expect(h.sockets.count == 1)
        h.clock += 2
        h.link.checkTimers()
        #expect(h.sockets[0].closed)
        if case .reconnecting(_, let reason) = h.states().last { #expect(reason.contains("stopped answering")) }
        else { Issue.record("expected reconnecting, got \(h.states())") }
    }

    @Test func aSkipMadeWhileOfflineIsSentAfterReconnecting() async throws {
        let h = Harness()
        h.link.start(); h.link.synchronize(); h.welcome()
        h.socket.drop()
        h.link.synchronize()
        h.link.send(update: RequestUpdate(id: "r0002", reason: "can't reach"))
        h.link.synchronize()
        h.link.kick(); h.link.synchronize()                       // reconnect now instead of after backoff
        #expect(h.sockets.count == 2)
        h.welcome()
        #expect(h.socket.types() == ["hello", "request_update"])
    }

    @Test func lateCallbacksFromAReplacedSocketAreIgnored() {
        let h = Harness()
        h.link.start(); h.link.synchronize(); h.welcome()
        let old = h.socket
        old.drop()
        h.link.synchronize()
        h.link.kick(); h.link.synchronize()
        old.deliver(#"{"t":"requests","v":1,"rev":9,"items":[]}"#)
        h.link.synchronize()
        #expect(!h.events.contains { if case .requests = $0 { true } else { false } })
    }

    @Test func onlyTheNewestStatusIsSent() {
        let h = Harness()
        h.link.start(); h.link.synchronize(); h.welcome()
        h.socket.holdSends = true
        func status(_ ts: Double) -> PhoneStatus {
            PhoneStatus(ts: ts, app: "foreground", thermal: "nominal", battery: nil,
                        tracking: .init(arkit: "normal", mat: nil), cameraToMat: nil, active: nil,
                        outbox: .init(pending: 0, bytes: 0))
        }
        h.link.send(status: status(1)); h.link.send(status: status(2)); h.link.send(status: status(3))
        h.link.synchronize()
        h.socket.pendingSend?(nil); h.link.synchronize()
        let statuses = h.socket.sent.filter { $0.contains("\"t\":\"status\"") }
        #expect(statuses.count == 2 && statuses.last!.contains("\"ts\":3"))
    }

    @Test func waitsForAnAddress() {
        let h = Harness()
        h.endpoint = nil
        h.link.start(); h.link.synchronize()
        #expect(h.sockets.isEmpty && h.states().last == .searching)
        h.endpoint = URL(string: "http://10.0.0.2:47815")
        h.link.kick(); h.link.synchronize()
        #expect(h.sockets.count == 1)
    }
}
