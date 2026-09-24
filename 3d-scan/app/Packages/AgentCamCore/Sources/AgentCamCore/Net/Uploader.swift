import Foundation

/// The HTTP calls the uploader makes; a seam for tests.
public protocol UploadTransport: AnyObject {
    /// PUT a file's contents; completes with the HTTP status or an error.
    func put(_ url: URL, file: URL, headers: [String: String], completion: @escaping (Result<Int, Error>) -> Void)
    /// POST a JSON body; completes with the HTTP status and body, or an error.
    func post(_ url: URL, json: Data, completion: @escaping (Result<(Int, Data), Error>) -> Void)
}

final class SessionTransport: UploadTransport {
    private let session: URLSession = {
        let config = URLSessionConfiguration.ephemeral
        config.timeoutIntervalForRequest = 30
        config.waitsForConnectivity = false
        return URLSession(configuration: config)
    }()

    func put(_ url: URL, file: URL, headers: [String: String], completion: @escaping (Result<Int, Error>) -> Void) {
        var request = URLRequest(url: url)
        request.httpMethod = "PUT"
        headers.forEach { request.setValue($1, forHTTPHeaderField: $0) }
        session.uploadTask(with: request, fromFile: file) { _, response, error in
            if let error { return completion(.failure(error)) }
            completion(.success((response as? HTTPURLResponse)?.statusCode ?? 0))
        }.resume()
    }

    func post(_ url: URL, json: Data, completion: @escaping (Result<(Int, Data), Error>) -> Void) {
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        session.uploadTask(with: request, from: json) { data, response, error in
            if let error { return completion(.failure(error)) }
            completion(.success(((response as? HTTPURLResponse)?.statusCode ?? 0, data ?? Data())))
        }.resume()
    }
}

public enum UploaderEvent: Sendable {
    case uploaded(requestId: String, captureId: String)
    /// The server will never take this capture; it was set aside.
    case rejected(requestId: String, captureId: String, reason: String)
    case pending(count: Int, bytes: Int)
}

/// Drains the outbox to the server, one capture at a time: PUT every file,
/// then commit. Every step is idempotent on the server, so after any failure
/// the whole capture is simply tried again later.
public final class Uploader: @unchecked Sendable {
    public var onEvent: (@Sendable (UploaderEvent) -> Void)?

    private let queue = DispatchQueue(label: "com.stocko.agentcam.upload")
    private let outbox: Outbox
    private let transport: UploadTransport
    private var base: URL?
    private var busy = false
    private var generation = 0
    private var retryWork: DispatchWorkItem?

    public convenience init(outbox: Outbox) {
        self.init(outbox: outbox, transport: SessionTransport())
    }

    init(outbox: Outbox, transport: UploadTransport) {
        self.outbox = outbox
        self.transport = transport
    }

    /// The server's base URL once connected, nil when not. Setting it starts a drain.
    public func setServer(_ url: URL?) {
        queue.async { [self] in
            guard url != base else { return }
            base = url
            generation += 1
            busy = false
            drain()
        }
    }

    /// Call after adding to the outbox.
    public func poke() { queue.async { [self] in drain() } }

    private func report() {
        let items = outbox.pending()
        onEvent?(.pending(count: items.count, bytes: items.reduce(0) { $0 + $1.bytes }))
    }

    private func drain() {
        report()
        guard !busy, let base, let item = outbox.pending().first else { return }
        busy = true
        let id = generation
        upload(item, to: base, files: item.meta.files[...]) { [weak self] outcome in
            guard let self else { return }
            self.queue.async {
                guard id == self.generation else { return }
                self.busy = false
                switch outcome {
                case .done:
                    self.outbox.remove(item)
                    self.onEvent?(.uploaded(requestId: item.meta.requestId, captureId: item.meta.captureId))
                    self.drain()
                case .rejected(let reason):
                    self.outbox.setAside(item)
                    self.onEvent?(.rejected(requestId: item.meta.requestId, captureId: item.meta.captureId, reason: reason))
                    self.drain()
                case .retryLater:
                    self.report()
                    self.retryWork?.cancel()
                    let work = DispatchWorkItem { [weak self] in self?.drain() }
                    self.retryWork = work
                    self.queue.asyncAfter(deadline: .now() + 3, execute: work)
                }
            }
        }
    }

    private enum Outcome { case done, rejected(String), retryLater }

    private func captureURL(_ base: URL, _ meta: CaptureMetadata) -> URL {
        base.appendingPathComponent("v1/requests/\(meta.requestId)/captures/\(meta.captureId)")
    }

    private func upload(_ item: Outbox.Item, to base: URL, files: ArraySlice<CaptureMetadata.File>,
                        completion: @escaping (Outcome) -> Void) {
        guard let file = files.first else { return commit(item, to: base, completion: completion) }
        let url = captureURL(base, item.meta).appendingPathComponent("files/\(file.name)")
        transport.put(url, file: item.folder.appendingPathComponent(file.name),
                      headers: ["X-AgentCam-SHA256": file.sha256]) { [weak self] result in
            switch result {
            case .success(200), .success(201): self?.upload(item, to: base, files: files.dropFirst(), completion: completion)
            case .success(404): completion(.rejected("The Mac no longer has request \(item.meta.requestId)."))
            case .success(409): completion(.rejected("\(file.name) doesn't match what the Mac already has."))
            case .success, .failure: completion(.retryLater)
            }
        }
    }

    private func commit(_ item: Outbox.Item, to base: URL, completion: @escaping (Outcome) -> Void) {
        guard let body = try? Wire.encoder.encode(item.meta) else { return completion(.rejected("unencodable metadata")) }
        transport.post(captureURL(base, item.meta).appendingPathComponent("commit"), json: body) { result in
            switch result {
            case .success((200, _)): completion(.done)
            case .success((let status, let data)) where (400..<500).contains(status) && status != 409:
                completion(.rejected(String(decoding: data.prefix(300), as: UTF8.self)))
            case .success, .failure: completion(.retryLater)     // 409: a file went missing; upload again
            }
        }
    }

    func synchronize() { queue.sync {} }
}
