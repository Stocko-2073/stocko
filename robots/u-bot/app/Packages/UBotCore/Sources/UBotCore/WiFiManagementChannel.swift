import Foundation

/// Opened only when the user requests settings; separate from drive telemetry.
/// Shares the drive link's lifetime but never reconnects or replays a request.
final class WiFiManagementChannel {
    private let queue: DispatchQueue
    private let address: String
    private let makeSocket: (URL) -> RobotWebSocket
    private var socket: RobotWebSocket?
    private var generation = 0
    private lazy var session: ManagementSession = {
        let session = ManagementSession(queue: queue)
        session.send = { [weak self] data in self?.send(data) }
        return session
    }()

    init(queue: DispatchQueue, address: String, makeSocket: @escaping (URL) -> RobotWebSocket) {
        self.queue = queue; self.address = address; self.makeSocket = makeSocket
    }

    func request(_ args: [String], completion: @escaping ManagementCompletion) {
        if socket == nil {
            guard let driveURL = WiFiProtocol.endpoint(address),
                  var url = URLComponents(url: driveURL, resolvingAgainstBaseURL: false) else {
                completion(.failure(.unavailable)); return
            }
            url.path = "/manage"
            guard let endpoint = url.url else { completion(.failure(.unavailable)); return }
            socket = makeSocket(endpoint)
            receive(generation)
        }
        session.request(args, completion: completion)
    }

    func close(_ error: RobotSettingsError = .disconnected) {
        generation += 1
        socket?.close(); socket = nil
        session.reset(error)
    }

    private func send(_ data: Data) {
        let id = generation
        socket?.send(String(decoding: data, as: UTF8.self)) { [weak self] error in
            guard let self else { return }
            self.queue.async {
                guard self.generation == id, error != nil else { return }
                self.close()
            }
        }
    }

    private func receive(_ id: Int) {
        socket?.receive { [weak self] result in
            guard let self else { return }
            self.queue.async {
                guard self.generation == id else { return }
                switch result {
                case .failure: self.close(.unavailable)
                case .success(let text):
                    self.session.receive(Data(text.utf8))
                    if self.generation == id { self.receive(id) }
                }
            }
        }
    }
}
