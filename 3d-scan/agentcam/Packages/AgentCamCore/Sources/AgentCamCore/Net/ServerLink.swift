import Foundation

/// Narrow seam for deterministic tests of loss, stalls and late callbacks.
public protocol ServerWebSocket: AnyObject {
    func send(_ text: String, completion: @escaping (Error?) -> Void)
    func receive(_ completion: @escaping (Result<String, Error>) -> Void)
    func close()
}

final class SessionWebSocket: ServerWebSocket {
    private let session: URLSession
    private let task: URLSessionWebSocketTask

    init(url: URL) {
        let config = URLSessionConfiguration.ephemeral
        config.waitsForConnectivity = true
        config.timeoutIntervalForRequest = 8
        session = URLSession(configuration: config)
        task = session.webSocketTask(with: url)
        task.maximumMessageSize = 8 << 20
        task.resume()
    }
    func send(_ text: String, completion: @escaping (Error?) -> Void) {
        task.send(.string(text), completionHandler: completion)
    }
    func receive(_ completion: @escaping (Result<String, Error>) -> Void) {
        task.receive { result in
            completion(result.flatMap { message in
                switch message {
                case .string(let text): return .success(text)
                case .data(let data): return .success(String(decoding: data, as: UTF8.self))
                @unknown default: return .failure(URLError(.cannotParseResponse))
                }
            })
        }
    }
    func close() {
        task.cancel(with: .goingAway, reason: nil)
        session.invalidateAndCancel()
    }
}

public enum ServerLinkState: Equatable, Sendable {
    case idle
    /// No server address yet (Bonjour hasn't found one and none is set).
    case searching
    case connecting(host: String)
    case connected(host: String)
    case reconnecting(host: String, reason: String)
}

public enum ServerLinkEvent: Sendable {
    case state(ServerLinkState)
    case welcome(Welcome)
    case requests(RequestsSnapshot)
    case message(String)
}

/// The control channel to the Mac. One serial queue owns all state; a
/// generation counter drops callbacks from a socket that has been replaced.
/// The server pings every 2 s, so silence means the connection is gone even
/// when the socket hasn't noticed (which is what a suspended app sees).
public final class ServerLink {
    public var onEvent: (@Sendable (ServerLinkEvent) -> Void)?

    public static let silenceLimit: TimeInterval = 6
    public static let welcomeLimit: TimeInterval = 8
    public static let sendLimit: TimeInterval = 5

    private let queue = DispatchQueue(label: "com.stocko.agentcam.link")
    private let endpoint: () -> URL?
    private let hello: () -> Hello
    private let makeSocket: (URL) -> ServerWebSocket
    private let now: () -> TimeInterval
    private var socket: ServerWebSocket?
    private var running = false
    private var generation = 0
    private var timer: DispatchSourceTimer?
    private var reconnect: DispatchWorkItem?
    private var retry = 0
    private var host = ""
    private var openedAt: TimeInterval = 0
    private var lastHeard: TimeInterval = 0
    private var ready = false
    private var sending = false
    private var sentAt: TimeInterval = 0
    private var helloPending = false
    private var latestStatus: String?
    /// Skips survive reconnects: the user's decision must reach the server.
    private var updates: [String] = []
    private var bye: String?

    /// `endpoint` gives the server's base URL (http://host:port) and is asked
    /// again on every connection attempt, so a newly discovered address is used.
    public convenience init(endpoint: @escaping () -> URL?, hello: @escaping () -> Hello) {
        self.init(endpoint: endpoint, hello: hello, makeSocket: { SessionWebSocket(url: $0) })
    }

    init(endpoint: @escaping () -> URL?, hello: @escaping () -> Hello,
         makeSocket: @escaping (URL) -> ServerWebSocket,
         now: @escaping () -> TimeInterval = { ProcessInfo.processInfo.systemUptime }) {
        self.endpoint = endpoint
        self.hello = hello
        self.makeSocket = makeSocket
        self.now = now
    }

    private func emit(_ event: ServerLinkEvent) { onEvent?(event) }

    public func start() {
        queue.async { [self] in
            guard !running else { return }
            running = true
            retry = 0
            let t = DispatchSource.makeTimerSource(queue: queue)
            t.schedule(deadline: .now() + 0.25, repeating: 0.25)
            t.setEventHandler { [weak self] in self?.tick() }
            timer = t
            t.resume()
            connect()
        }
    }

    public func stop() {
        queue.async { [self] in
            running = false
            reconnect?.cancel(); reconnect = nil
            timer?.cancel(); timer = nil
            retire()
            emit(.state(.idle))
        }
    }

    /// Reconnect now, e.g. when the app returns to the foreground or the
    /// server address changes. Cheap if already connected to the same place.
    public func kick() {
        queue.async { [self] in
            guard running else { return }
            if ready, let url = endpoint(), url.host == host { return }
            reconnect?.cancel(); reconnect = nil
            retry = 0
            connect()
        }
    }

    public func send(status: PhoneStatus) {
        guard let text = try? Wire.text(status) else { return }
        queue.async { [self] in latestStatus = text; pump() }   // only the newest matters
    }

    public func send(update: RequestUpdate) {
        guard let text = try? Wire.text(update) else { return }
        queue.async { [self] in updates.append(text); pump() }
    }

    /// Best effort, before the app is suspended: the server then knows the
    /// phone went to the background rather than dropped off the network.
    public func sayBye(_ reason: String) {
        guard let text = try? Wire.text(Bye(reason: reason)) else { return }
        queue.async { [self] in bye = text; pump() }
    }

    private func retire() {
        generation += 1
        ready = false
        sending = false
        helloPending = false
        latestStatus = nil
        bye = nil
        socket?.close(); socket = nil
    }

    private func connect() {
        guard running else { return }
        retire()
        guard let base = endpoint(), let url = Self.socketURL(base) else {
            emit(.state(.searching))
            schedule(after: 1)
            return
        }
        host = base.host ?? base.absoluteString
        openedAt = now()
        lastHeard = openedAt
        emit(.state(.connecting(host: host)))
        socket = makeSocket(url)
        helloPending = true
        receive(generation)
        pump()
    }

    static func socketURL(_ base: URL) -> URL? {
        guard var c = URLComponents(url: base, resolvingAgainstBaseURL: false) else { return nil }
        c.scheme = c.scheme == "https" ? "wss" : "ws"
        c.path = "/v1/ws"
        return c.url
    }

    private func schedule(after delay: TimeInterval) {
        let work = DispatchWorkItem { [weak self] in self?.connect() }
        reconnect = work
        queue.asyncAfter(deadline: .now() + delay, execute: work)
    }

    private func fail(_ explanation: String) {
        guard running, socket != nil else { return }
        retire()
        emit(.state(.reconnecting(host: host, reason: explanation)))
        let delay = min(8, pow(2, Double(retry)))
        retry = min(3, retry + 1)
        schedule(after: delay)
    }

    private func receive(_ id: Int) {
        socket?.receive { [weak self] result in
            guard let self else { return }
            self.queue.async {
                guard self.running, self.generation == id else { return }
                switch result {
                case .failure(let error): self.fail(error.localizedDescription)
                case .success(let text):
                    self.handle(text)
                    if self.generation == id { self.receive(id) }
                }
            }
        }
    }

    private func handle(_ text: String) {
        lastHeard = now()
        let data = Data(text.utf8)
        switch Wire.messageType(data) {
        case "welcome":
            guard let welcome = try? Wire.decoder.decode(Welcome.self, from: data) else { return }
            ready = true
            retry = 0
            emit(.state(.connected(host: host)))
            emit(.welcome(welcome))
            pump()
        case "requests":
            do {
                emit(.requests(try Wire.decoder.decode(RequestsSnapshot.self, from: data)))
            } catch {
                emit(.message("The Mac sent a request list this app can't read: \(error)"))
            }
        case "error":
            if let e = try? Wire.decoder.decode(ServerError.self, from: data) { emit(.message(e.message)) }
        default:
            break                                   // ping, and anything newer than this app
        }
    }

    private func tick() {
        guard running, socket != nil else { return }
        let time = now()
        if !ready, time - openedAt > Self.welcomeLimit { fail("No answer from the Mac."); return }
        if ready, time - lastHeard > Self.silenceLimit { fail("The Mac stopped answering."); return }
        if sending, time - sentAt > Self.sendLimit { fail("Sending to the Mac stalled."); return }
        pump()
    }

    private func pump() {
        guard !sending, let socket else { return }
        let text: String
        var sentUpdate = false
        if helloPending, let h = try? Wire.text(hello()) {
            helloPending = false
            text = h
        } else if !ready {
            return                                  // the server wants hello first, then welcome
        } else if let first = updates.first {
            text = first
            sentUpdate = true
        } else if let b = bye {
            bye = nil
            text = b
        } else if let s = latestStatus {
            latestStatus = nil
            text = s
        } else { return }
        sending = true
        sentAt = now()
        let id = generation
        socket.send(text) { [weak self] error in
            guard let self else { return }
            self.queue.async {
                guard self.running, id == self.generation else { return }
                self.sending = false
                if let error { self.fail(error.localizedDescription); return }
                if sentUpdate, !self.updates.isEmpty { self.updates.removeFirst() }
                self.pump()
            }
        }
    }

    // Lets tests drain asynchronous calls without sleeping.
    func synchronize() { queue.sync {} }
    func checkTimers() { queue.sync { tick() } }
}
