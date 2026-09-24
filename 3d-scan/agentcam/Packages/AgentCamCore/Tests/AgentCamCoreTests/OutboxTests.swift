import Foundation
import Testing
@testable import AgentCamCore

final class FakeTransport: UploadTransport, @unchecked Sendable {
    var putStatus: (URL) -> Int = { _ in 201 }
    var commitStatus = 200
    var failNetwork = false
    var puts: [String] = []
    var commits = 0

    func put(_ url: URL, file: URL, headers: [String: String], completion: @escaping (Result<Int, Error>) -> Void) {
        if failNetwork { return completion(.failure(URLError(.notConnectedToInternet))) }
        puts.append(url.lastPathComponent)
        completion(.success(putStatus(url)))
    }
    func post(_ url: URL, json: Data, completion: @escaping (Result<(Int, Data), Error>) -> Void) {
        if failNetwork { return completion(.failure(URLError(.notConnectedToInternet))) }
        commits += 1
        completion(.success((commitStatus, Data())))
    }
}

func tempDir() -> URL {
    let url = FileManager.default.temporaryDirectory.appendingPathComponent("agentcam-\(UUID().uuidString)")
    try! FileManager.default.createDirectory(at: url, withIntermediateDirectories: true)
    return url
}

func sampleMeta(_ capture: String, request: String = "r0001", at: String = "2026-09-23T22:00:00Z") -> CaptureMetadata {
    CaptureMetadata(captureId: capture, requestId: request, capturedAt: at, path: "fast", files: [],
                    image: .init(file: "image.jpg", w: 4, h: 3, uprightRotationCwDeg: 0),
                    intrinsics: .init(K: [[1, 0, 2], [0, 1, 1.5], [0, 0, 1]], source: "test", refDims: [4, 3],
                                      distortion: .init(model: "none")),
                    pose: .init(cameraToMat: nil, source: "none"))
}

@Suite struct OutboxTests {
    @Test func capturesSurviveARestartUntilAcknowledged() throws {
        let root = tempDir()
        let outbox = try Outbox(root: root)
        try outbox.add(sampleMeta("b", at: "2026-09-23T22:00:02Z"), files: [("image.jpg", Data("two".utf8))])
        try outbox.add(sampleMeta("a", at: "2026-09-23T22:00:01Z"), files: [("image.jpg", Data("one".utf8))])
        // A crash mid-write leaves a temp folder behind; it isn't a capture.
        try FileManager.default.createDirectory(at: root.appendingPathComponent(".tmp-c"), withIntermediateDirectories: true)
        let reopened = try Outbox(root: root)
        let items = reopened.pending()
        #expect(items.map(\.meta.captureId) == ["a", "b"])                   // oldest first
        #expect(items[0].meta.files.first?.sha256 == Outbox.sha256(Data("one".utf8)))
        reopened.remove(items[0])
        #expect(reopened.pending().map(\.meta.captureId) == ["b"])
        #expect(!FileManager.default.fileExists(atPath: root.appendingPathComponent(".tmp-c").path))
    }

    @Test func uploadsFilesThenCommitsThenForgets() throws {
        let outbox = try Outbox(root: tempDir())
        try outbox.add(sampleMeta("c1"), files: [("image.jpg", Data("jpg".utf8)), ("depth.png", Data("png".utf8))])
        let transport = FakeTransport()
        let uploader = Uploader(outbox: outbox, transport: transport)
        let events = Box<[UploaderEvent]>([])
        uploader.onEvent = { e in events.value.append(e) }
        uploader.setServer(URL(string: "http://mac:47815"))
        uploader.synchronize(); uploader.synchronize()
        #expect(transport.puts == ["image.jpg", "depth.png"] && transport.commits == 1)
        #expect(outbox.pending().isEmpty)
        #expect(events.value.contains { if case .uploaded("r0001", "c1") = $0 { true } else { false } })
    }

    @Test func networkFailureKeepsTheCaptureForLater() throws {
        let outbox = try Outbox(root: tempDir())
        try outbox.add(sampleMeta("c1"), files: [("image.jpg", Data("jpg".utf8))])
        let transport = FakeTransport()
        transport.failNetwork = true
        let uploader = Uploader(outbox: outbox, transport: transport)
        uploader.setServer(URL(string: "http://mac:47815"))
        uploader.synchronize(); uploader.synchronize()
        #expect(outbox.pending().count == 1)
    }

    @Test func aCaptureTheServerWillNeverTakeIsSetAside() throws {
        let outbox = try Outbox(root: tempDir())
        try outbox.add(sampleMeta("gone", request: "r0099"), files: [("image.jpg", Data("jpg".utf8))])
        try outbox.add(sampleMeta("next", at: "2026-09-23T23:00:00Z"), files: [("image.jpg", Data("jpg".utf8))])
        let transport = FakeTransport()
        let uploader = Uploader(outbox: outbox, transport: transport)
        transport.putStatus = { $0.path.contains("/r0099/") ? 404 : 201 }   // the Mac lost r0099
        uploader.setServer(URL(string: "http://mac:47815"))
        for _ in 0..<4 { uploader.synchronize() }
        #expect(outbox.pending().isEmpty)                                     // "next" still went through
        #expect(transport.commits == 1)
        #expect(FileManager.default.fileExists(atPath: outbox.root.appendingPathComponent("failed/gone").path))
    }

    @Test func noServerNoUpload() throws {
        let outbox = try Outbox(root: tempDir())
        try outbox.add(sampleMeta("c1"), files: [("image.jpg", Data("jpg".utf8))])
        let transport = FakeTransport()
        let uploader = Uploader(outbox: outbox, transport: transport)
        uploader.poke(); uploader.synchronize()
        #expect(transport.puts.isEmpty)
    }
}
