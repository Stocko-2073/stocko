import Foundation

/// Queue-confined management protocol v1. One bounded request at a time; never
/// retries writes. `finished` plus contiguous output is required for success.
final class ManagementSession {
    private let queue: DispatchQueue
    private let timeout: TimeInterval
    var send: (Data) -> Void = { _ in }
    var onRequestFinished: () -> Void = {}
    private var session: Int?
    private var nextID = 0
    private var pending: (id: Int, args: [String], completion: ManagementCompletion)?
    private var sent = false
    private var output = Data()
    private var dropped = 0
    private var timer: DispatchWorkItem?

    init(queue: DispatchQueue, timeout: TimeInterval = 10) {
        self.queue = queue
        self.timeout = timeout
    }

    func request(_ args: [String], completion: @escaping ManagementCompletion) {
        guard pending == nil else { completion(.failure(.busy)); return }
        nextID += 1
        pending = (nextID, args, completion)
        sent = false; output = Data()
        let id = nextID
        let timer = DispatchWorkItem { [weak self] in
            guard let self, self.pending?.id == id else { return }
            self.finish(.failure(.timeout))
        }
        self.timer = timer
        queue.asyncAfter(deadline: .now() + timeout, execute: timer)
        sendPending()
    }

    func reset(_ error: RobotSettingsError = .disconnected) {
        session = nil
        dropped = 0
        finish(.failure(error))
    }

    private func sendPending() {
        guard let session, let pending, !sent else { return }
        let fields: [String: Any] = ["id": pending.id, "session": session,
                                    "op": "exec", "args": pending.args, "deadline_ms": 5000]
        guard let data = try? JSONSerialization.data(withJSONObject: fields), data.count < 768 else {
            finish(.failure(.invalidResponse)); return
        }
        sent = true
        send(data)
    }

    func receive(_ data: Data) {
        guard let message = (try? JSONSerialization.jsonObject(with: data)) as? [String: Any],
              let type = message["type"] as? String else {
            reset(.invalidResponse); return
        }
        if type == "hello" {
            guard message["protocol"] as? Int == 1, let token = message["session"] as? Int, token > 0 else {
                reset(.unavailable); return
            }
            if session != nil { reset() }
            session = token
            dropped = message["dropped"] as? Int ?? 0
            sendPending()
            return
        }
        let lost = message["dropped"] as? Int ?? dropped
        if lost > dropped {
            dropped = lost
            finish(.failure(.invalidResponse))
            return
        }
        guard let pending, sent, message["id"] as? Int == pending.id else { return }
        switch type {
        case "output":
            guard let text = message["data"] as? String,
                  message["offset"] as? Int == output.count,
                  output.count + text.utf8.count <= 16384 else {
                finish(.failure(.invalidResponse)); return
            }
            output.append(contentsOf: text.utf8)
        case "finished":
            guard let code = message["code"] as? Int,
                  (message["truncated"] as? Int ?? 0) == 0 else {
                finish(.failure(.invalidResponse)); return
            }
            let text = String(decoding: output, as: UTF8.self)
            if code == 0 { finish(.success(text)) }
            else {
                let reason = (message["error"] as? String) ?? text.trimmingCharacters(in: .whitespacesAndNewlines)
                finish(.failure(.refused(reason.isEmpty ? "The robot refused the settings request." : reason)))
            }
        case "error":
            finish(.failure(.refused(message["error"] as? String ?? "The robot refused the settings request.")))
        default: break // accepted and unrelated notifications are not completion
        }
    }

    private func finish(_ result: Result<String, RobotSettingsError>) {
        timer?.cancel(); timer = nil
        let callback = pending?.completion
        pending = nil; output = Data(); sent = false
        onRequestFinished()
        callback?(result)
    }
}

/// Five-byte BLE management header: flags, LE16 message ID, LE16 byte offset.
struct ManagementFragments {
    private var messageID: UInt16?
    private var buffer = Data()
    private var started: TimeInterval = 0

    static func encode(_ data: Data, id: UInt16, mtu: Int) throws -> [Data] {
        guard !data.isEmpty, data.count < 768, mtu > 5 else { throw RobotSettingsError.invalidResponse }
        let size = min(507, mtu) - 5
        return stride(from: 0, to: data.count, by: size).map { offset in
            let end = min(data.count, offset + size)
            var frame = Data([UInt8((offset == 0 ? 1 : 0) | (end == data.count ? 2 : 0)),
                              UInt8(truncatingIfNeeded: id), UInt8(id >> 8),
                              UInt8(truncatingIfNeeded: offset), UInt8(offset >> 8)])
            frame.append(data.subdata(in: offset..<end))
            return frame
        }
    }

    mutating func receive(_ data: Data, now: TimeInterval = ProcessInfo.processInfo.systemUptime) throws -> Data? {
        let bytes = [UInt8](data)
        guard bytes.count > 5, bytes[0] & 0xfc == 0 else { throw RobotSettingsError.invalidResponse }
        let id = UInt16(bytes[1]) | UInt16(bytes[2]) << 8
        let offset = Int(bytes[3]) | Int(bytes[4]) << 8
        if bytes[0] & 1 != 0 {
            guard offset == 0, messageID == nil else { throw RobotSettingsError.invalidResponse }
            messageID = id; buffer = Data(); started = now
        }
        guard messageID == id, offset == buffer.count, now - started <= 5,
              buffer.count + bytes.count - 5 < 768 else { throw RobotSettingsError.invalidResponse }
        buffer.append(contentsOf: bytes.dropFirst(5))
        if bytes[0] & 2 != 0 {
            let result = buffer
            self = ManagementFragments()
            return result
        }
        return nil
    }
}
