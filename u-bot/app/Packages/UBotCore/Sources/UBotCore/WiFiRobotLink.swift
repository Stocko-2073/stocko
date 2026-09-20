import Foundation

/// Narrow seam for deterministic tests of loss, backpressure, and old callbacks.
protocol RobotWebSocket: AnyObject {
    func send(_ text: String, completion: @escaping (Error?) -> Void)
    func receive(_ completion: @escaping (Result<String, Error>) -> Void)
    func close()
}

private final class SessionWebSocket: RobotWebSocket {
    private let session: URLSession
    private let task: URLSessionWebSocketTask
    init(url: URL) {
        let config = URLSessionConfiguration.ephemeral
        config.waitsForConnectivity = true
        config.timeoutIntervalForRequest = 8
        session = URLSession(configuration: config)
        task = session.webSocketTask(with: url)
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

/// One serial queue owns connection state and writes. No motion survives a
/// connection generation, and only one frame can be in the send pipeline.
public final class WiFiRobotLink: RobotLink {
    public var onEvent: (@Sendable (LinkEvent) -> Void)?
    private let queue = DispatchQueue(label: "com.stocko.ubot.wifi")
    private let address: String
    private let makeSocket: (URL) -> RobotWebSocket
    private let now: () -> TimeInterval
    private var socket: RobotWebSocket?
    private var running = false
    private var generation = 0
    private var timer: DispatchSourceTimer?
    private var reconnect: DispatchWorkItem?
    private var retry = 0
    private var openedAt: TimeInterval = 0
    private var lastStatus: TimeInterval?
    private var ready = false
    private var sending = false
    private var sentAt: TimeInterval = 0
    private var command: DriveCommand = .zero
    private var driving = false
    private var zeros = 0
    private var controls: [ControlOp] = []
    private var pending: (op: ControlOp, time: TimeInterval)?
    private var robotName = "ubot"

    public convenience init(address: String = "ubot.local") {
        self.init(address: address, makeSocket: { SessionWebSocket(url: $0) })
    }
    init(address: String, makeSocket: @escaping (URL) -> RobotWebSocket,
         now: @escaping () -> TimeInterval = { ProcessInfo.processInfo.systemUptime }) {
        self.address = address
        self.makeSocket = makeSocket
        self.now = now
    }
    private func emit(_ event: LinkEvent) { onEvent?(event) }

    public func start() {
        queue.async { [self] in
            guard !running else { return }
            guard WiFiProtocol.endpoint(address) != nil else {
                emit(.state(.failed(reason: "Enter a valid robot hostname or IP address.")))
                return
            }
            running = true
            retry = 0
            let t = DispatchSource.makeTimerSource(queue: queue)
            t.schedule(deadline: .now() + 0.1, repeating: 0.1)
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

    private func retire() {
        generation += 1
        ready = false
        driving = false; command = .zero; zeros = 0
        controls.removeAll(); pending = nil; sending = false
        lastStatus = nil
        socket?.close(); socket = nil
    }

    private func connect() {
        guard running, let url = WiFiProtocol.endpoint(address) else { return }
        retire()
        openedAt = now()
        emit(.state(.connecting(name: address)))
        socket = makeSocket(url)
        receive(generation)
    }

    private func fail(_ explanation: String) {
        guard running, socket != nil else { return }
        if let pending { emit(.controlRefused(pending.op, "Connection lost before acknowledgement.")) }
        retire()
        emit(.message(explanation + " Check the robot address, local network access, and Wi-Fi connection."))
        emit(.state(.reconnecting(name: address)))
        let delay = min(8, pow(2, Double(retry)))
        retry = min(3, retry + 1)
        let work = DispatchWorkItem { [weak self] in self?.connect() }
        reconnect = work
        queue.asyncAfter(deadline: .now() + delay, execute: work)
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
        let data = Data(text.utf8)
        struct Header: Decodable { let t: String }
        guard let header = try? JSONDecoder().decode(Header.self, from: data) else { return }
        if header.t == "status" {
            guard let frame = try? JSONDecoder().decode(WiFiProtocol.Status.self, from: data),
                  let status = frame.model() else { return }
            lastStatus = now(); retry = 0; robotName = frame.name
            if !ready { ready = true; emit(.state(.ready(name: robotName))) }
            emit(.firmware(frame.fw)); emit(.status(status))
            if !status.isEnabled || status.isFaulted || status.busyReason != nil {
                driving = false; command = .zero; zeros = 0
            }
        } else if header.t == "ack" {
            guard let envelope = try? JSONDecoder().decode(WiFiProtocol.Envelope.self, from: data) else { return }
            if envelope.cmd == "drive", envelope.ok == false {
                driving = false; command = .zero; zeros = 0
                emit(.message("Drive refused: " + (envelope.err ?? "Robot refused the command.")))
            } else if let p = pending, envelope.cmd == WiFiProtocol.command(p.op), let ok = envelope.ok {
                pending = nil
                emit(ok ? .controlAccepted(p.op) : .controlRefused(p.op, envelope.err ?? "Robot refused the command."))
                pump()
            }
        }
    }

    public func engage(_ command: DriveCommand) {
        queue.async { [self] in
            guard ready else { return }
            self.command = command; driving = true; zeros = 0
            pump()
        }
    }
    public func update(_ command: DriveCommand) {
        queue.async { [self] in if driving { self.command = command } }
    }
    public func releaseStick() {
        queue.async { [self] in
            driving = false; command = .zero
            guard ready else { return }
            zeros = 3
            pump()
        }
    }
    public func send(_ op: ControlOp) {
        queue.async { [self] in
            guard ready else { emit(.controlRefused(op, "Not connected to the robot.")); return }
            if op == .stop || op == .disable || op == .estop {
                driving = false; command = .zero; zeros = 0
            }
            if op == .estop {
                controls.removeAll()
                // Different command names let us prioritize E-STOP even while
                // a prior acknowledgement is outstanding; its late ack is ignored.
                if pending?.op != .estop { pending = nil; controls.append(op) }
            } else if !controls.contains(op), pending?.op != op {
                controls.append(op)
            }
            pump()
        }
    }

    private func tick() {
        guard running, socket != nil else { return }
        let time = now()
        if let lastStatus, time - lastStatus > 1.5 {
            driving = false; command = .zero; zeros = 1
            pump()
            emit(.state(.stalled(name: robotName)))
            fail("Robot telemetry stopped.")
            return
        }
        if lastStatus == nil, time - openedAt > 8 { fail("No status received from the robot."); return }
        if sending, time - sentAt > 0.5 { fail("The connection cannot keep up with commands."); return }
        if let pending, time - pending.time > 2 { fail("The robot did not acknowledge the command."); return }
        pump()
    }

    private func pump() {
        guard ready, !sending, let socket else { return }
        let text: String
        if pending == nil, !controls.isEmpty {
            let op = controls.removeFirst()
            pending = (op, now())
            text = "{\"t\":\"\(WiFiProtocol.command(op))\"}"
        } else if zeros > 0 {
            zeros -= 1
            text = WiFiProtocol.drive(.zero)
        } else if driving {
            text = WiFiProtocol.drive(command)
        } else { return }
        sending = true; sentAt = now()
        let id = generation
        socket.send(text) { [weak self] error in
            guard let self else { return }
            self.queue.async {
                guard self.running, id == self.generation else { return }
                self.sending = false
                if let error { self.fail(error.localizedDescription) }
                // Urgent controls need not wait for the next tick. Drive and
                // zero-tail frames stay limited to the 10 Hz timer.
                else if !self.controls.isEmpty && self.pending == nil {
                    self.pump()
                }
            }
        }
    }

    // Allows tests to drain asynchronous API calls without sleeping.
    func synchronize() { queue.sync {} }
    func checkTimers() { queue.sync { tick() } }
}
