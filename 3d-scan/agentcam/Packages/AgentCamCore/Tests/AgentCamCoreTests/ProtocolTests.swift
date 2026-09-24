import Foundation
import Testing
import simd
@testable import AgentCamCore

/// agentcam/protocol, found from this file.
let protocolDir = URL(fileURLWithPath: #filePath)
    .deletingLastPathComponent().deletingLastPathComponent().deletingLastPathComponent()
    .deletingLastPathComponent().deletingLastPathComponent()
    .appendingPathComponent("protocol")

func example(_ name: String) throws -> Data {
    try Data(contentsOf: protocolDir.appendingPathComponent("examples/\(name)"))
}

@Suite struct ProtocolTests {
    @Test func everyServerExampleDecodes() throws {
        let hello = try Wire.decoder.decode(Hello.self, from: example("hello.json"))
        #expect(hello.lenses.map(\.id) == [.wide, .ultrawide, .telephoto])
        let welcome = try Wire.decoder.decode(Welcome.self, from: example("welcome.json"))
        #expect(welcome.board.dictionary == "DICT_4X4_100")
        let snapshot = try Wire.decoder.decode(RequestsSnapshot.self, from: example("requests.json"))
        #expect(snapshot.items.map(\.id) == ["r0001", "r0002", "r0003"])
        #expect(snapshot.items.map(\.options.needsFullPath) == [false, true, false])
        #expect(snapshot.items[1].placement?.label == "flipped")
        #expect(snapshot.items[2].kind == .free && snapshot.items[2].target == nil)
        #expect(Pose(rows: try #require(snapshot.items[0].target).cameraToPage) != nil)
        _ = try Wire.decoder.decode(PhoneStatus.self, from: example("status.json"))
        _ = try Wire.decoder.decode(RequestUpdate.self, from: example("request_update.json"))
        let meta = try Wire.decoder.decode(CaptureMetadata.self, from: example("capture_meta.json"))
        #expect(meta.intrinsics.K[0][0] == 2860.1)
    }

    @Test func encodingMatchesTheServersKeys() throws {
        let meta = try Wire.decoder.decode(CaptureMetadata.self, from: example("capture_meta.json"))
        let json = try #require(try JSONSerialization.jsonObject(with: Wire.encoder.encode(meta)) as? [String: Any])
        let intrinsics = try #require(json["intrinsics"] as? [String: Any])
        #expect(intrinsics["K"] != nil && intrinsics["ref_dims"] != nil)          // K stays K
        let image = try #require(json["image"] as? [String: Any])
        #expect(image["upright_rotation_cw_deg"] as? Int == 0)
        #expect((json["pose"] as? [String: Any])?["camera_to_page"] != nil)
        #expect(Wire.snake("sha256") == "sha256" && Wire.snake("maxSpeedMmS") == "max_speed_mm_s")
    }

    @Test func uprightRotationMatchesThePythonConventions() throws {
        struct Case: Decodable {
            let name: String
            let cameraToPage: Matrix
            let uprightRotationCwDeg: Int
        }
        let cases = try Wire.decoder.decode([Case].self, from: example("pose_specs.json"))
        #expect(cases.count >= 6)
        for c in cases {
            let pose = try #require(Pose(rows: c.cameraToPage))
            #expect(uprightRotationCwDeg(cameraToPage: pose) == c.uprightRotationCwDeg, "\(c.name)")
            #expect(Pose(rows: pose.rowMajor) == pose)
            // The examples are rounded to 9 decimals, so not exactly orthonormal.
            let (mm, deg) = poseDifference(pose.rigidInverse.rigidInverse, pose)
            #expect(mm < 1e-5 && deg < 1e-5)
        }
    }

    @Test func boardLayoutIsInThePageFrame() throws {
        let board = try BoardLayout.bundled()
        #expect(board.corners.count == 70)
        let tl = try #require(board.corners[0]?.first)
        #expect(abs(tl.x - -98.75) < 1e-9 && abs(tl.y - 130.0) < 1e-9)
        let scaled = try BoardLayout.bundled(BoardInfo(printScale: [0.99, 1.01]))
        #expect(abs(try #require(scaled.corners[0]?.first).y - 131.3) < 1e-9)
        #expect(try BoardLayout.bundled(BoardInfo(dictionary: "DICT_APRILTAG_36h11")).corners.count == 70)
    }

    @Test func bundledLayoutsAreTheProtocolCopies() throws {
        // SPM can't bundle a symlinked resource, so the package keeps copies.
        let bundled = URL(fileURLWithPath: #filePath).deletingLastPathComponent().deletingLastPathComponent()
            .deletingLastPathComponent().appendingPathComponent("Sources/AgentCamCore/Resources/boards")
        for name in BoardLayout.layoutFiles.values {
            let a = try Data(contentsOf: bundled.appendingPathComponent("\(name).json"))
            let b = try Data(contentsOf: protocolDir.appendingPathComponent("boards/\(name).json"))
            #expect(a == b, "copy agentcam/protocol/boards/\(name).json into Sources/AgentCamCore/Resources/boards")
        }
    }

    @Test func arkitCameraAxesBecomeOpenCVAxes() {
        // An ARKit camera at (0, 0.3, 0) m looking straight down (its -z along world -y).
        let lookingDown = simd_float4x4(columns: (SIMD4(1, 0, 0, 0), SIMD4(0, 0, -1, 0), SIMD4(0, 1, 0, 0),
                                                 SIMD4(0, 0.3, 0, 1)))
        let cv = Frames.worldFromOpenCVCamera(arkit: lookingDown)
        #expect(simd_distance(cv.translation, SIMD3(0, 300, 0)) < 1e-4)          // mm
        #expect(simd_distance(cv.rotation.columns.2, SIMD3(0, -1, 0)) < 1e-6)    // z forward = down
        #expect(simd_distance(cv.rotation.columns.1, SIMD3(0, 0, 1)) < 1e-6)     // y down in the image
    }

    @Test func manualAddresses() {
        #expect(ServerDiscovery.manualURL("Honeypot.local")?.absoluteString == "http://Honeypot.local:47815")
        #expect(ServerDiscovery.manualURL("192.168.1.175:9000")?.absoluteString == "http://192.168.1.175:9000")
        #expect(ServerDiscovery.manualURL("  ") == nil)
        #expect(ServerLink.socketURL(URL(string: "http://Honeypot.local:47815")!)?.absoluteString
                == "ws://Honeypot.local:47815/v1/ws")
    }
}
