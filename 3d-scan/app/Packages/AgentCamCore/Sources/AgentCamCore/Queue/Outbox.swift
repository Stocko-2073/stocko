import CryptoKit
import Foundation

/// Captures waiting to reach the Mac. Each is a folder holding its files and
/// meta.json, written atomically (built under a temporary name, then renamed),
/// and deleted only once the server has acknowledged the commit. So a capture
/// survives losing Wi-Fi, the app being suspended or killed, and the Mac's
/// server restarting; the uploader retries from here on every connection.
public final class Outbox: @unchecked Sendable {
    public struct Item: Sendable, Equatable {
        public let folder: URL
        public let meta: CaptureMetadata
        public var bytes: Int { meta.files.reduce(0) { $0 + $1.bytes } }
    }

    public let root: URL
    private let failedRoot: URL
    private let lock = NSLock()

    public init(root: URL) throws {
        self.root = root
        failedRoot = root.appendingPathComponent("failed", isDirectory: true)
        try FileManager.default.createDirectory(at: failedRoot, withIntermediateDirectories: true)
        // A crash mid-write leaves a temporary folder; it was never a capture.
        for leftover in (try? FileManager.default.contentsOfDirectory(at: root, includingPropertiesForKeys: nil)) ?? []
        where leftover.lastPathComponent.hasPrefix(".tmp-") {
            try? FileManager.default.removeItem(at: leftover)
        }
    }

    /// Stores a capture. `files` are (name, contents); their sizes and hashes
    /// are filled into `meta.files`.
    @discardableResult
    public func add(_ meta: CaptureMetadata, files: [(name: String, data: Data)]) throws -> Item {
        var meta = meta
        meta.files = files.map { CaptureMetadata.File(name: $0.name, sha256: Self.sha256($0.data), bytes: $0.data.count) }
        let fm = FileManager.default
        let tmp = root.appendingPathComponent(".tmp-\(meta.captureId)", isDirectory: true)
        let folder = root.appendingPathComponent(meta.captureId, isDirectory: true)
        try? fm.removeItem(at: tmp)
        try fm.createDirectory(at: tmp, withIntermediateDirectories: true)
        for f in files { try f.data.write(to: tmp.appendingPathComponent(f.name)) }
        try Wire.encoder.encode(meta).write(to: tmp.appendingPathComponent("meta.json"))
        lock.lock(); defer { lock.unlock() }
        try fm.moveItem(at: tmp, to: folder)
        return Item(folder: folder, meta: meta)
    }

    /// Oldest first.
    public func pending() -> [Item] {
        lock.lock(); defer { lock.unlock() }
        let folders = (try? FileManager.default.contentsOfDirectory(at: root, includingPropertiesForKeys: nil)) ?? []
        return folders.compactMap { folder -> Item? in
            let name = folder.lastPathComponent
            guard !name.hasPrefix("."), name != "failed",
                  let data = try? Data(contentsOf: folder.appendingPathComponent("meta.json")),
                  let meta = try? Wire.decoder.decode(CaptureMetadata.self, from: data) else { return nil }
            return Item(folder: folder, meta: meta)
        }.sorted { $0.meta.capturedAt < $1.meta.capturedAt }
    }

    public func remove(_ item: Item) {
        lock.lock(); defer { lock.unlock() }
        try? FileManager.default.removeItem(at: item.folder)
    }

    /// Captures the server can never take (e.g. their request no longer
    /// exists) move aside rather than blocking the queue; they stay reachable
    /// through the Files app.
    public func setAside(_ item: Item) {
        lock.lock(); defer { lock.unlock() }
        let dest = failedRoot.appendingPathComponent(item.folder.lastPathComponent)
        try? FileManager.default.removeItem(at: dest)
        try? FileManager.default.moveItem(at: item.folder, to: dest)
    }

    public static func sha256(_ data: Data) -> String {
        SHA256.hash(data: data).map { String(format: "%02x", $0) }.joined()
    }
}
