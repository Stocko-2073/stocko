import AgentCamCore
import AgentCamVision
import Foundation
import Testing
import simd

/// The server's reference solution for the real photo (mcp/tests/make_aruco_fixture.py).
struct PhotoFixture: Decodable {
    struct Detection: Decodable {
        let id: Int
        let corners: [[Double]]
    }
    let K: Matrix
    let detections: [Detection]
    let inliers: [Bool]
    let rejectedIds: [Int]
    let cameraToPage: Matrix
    let rmsPx: Double

    static func load() throws -> PhotoFixture {
        try Wire.decoder.decode(PhotoFixture.self, from: Data(contentsOf: fixtures.appendingPathComponent("aruco_border.json")))
    }
    var k: simd_double3x3 { simd_double3x3(rows: K.map { SIMD3($0[0], $0[1], $0[2]) }) }
    var markers: [DetectedMarker] { detections.map { DetectedMarker(id: $0.id, corners: $0.corners.map { SIMD2($0[0], $0[1]) }) } }
}

@Suite struct BoardSolverTests {
    @Test func agreesWithTheServerOnTheRealPhoto() throws {
        let ref = try PhotoFixture.load()
        let fit = BoardSolver.solve(ref.markers, layout: try BoardLayout.bundled(), k: ref.k)
        #expect(fit.inliers == ref.inliers)
        #expect(fit.rejectedIds == ref.rejectedIds)
        let best = try #require(fit.solutions.first)
        let (mm, deg) = poseDifference(best.cameraFromPage.rigidInverse, try #require(Pose(rows: ref.cameraToPage)))
        #expect(mm < 0.1 && deg < 0.05, "phone vs server: \(mm) mm, \(deg) deg")
        #expect(abs(best.rmsPx - ref.rmsPx) < 0.01 * ref.rmsPx)
    }

    @Test func detectsAndSolvesThePhotoItself() throws {
        let (pixels, w, h) = try loadGray(fixtures.appendingPathComponent("aruco_border.jpeg"))
        let markers = try #require(pixels.withUnsafeBytes {
            MarkerDetector(family: .aruco4x4)!.detect(gray: $0.baseAddress!, width: w, height: h, bytesPerRow: w)
        })
        let fit = BoardSolver.solve(markers, layout: try BoardLayout.bundled(), k: try PhotoFixture.load().k)
        #expect(fit.usedCount == 70 && fit.rejectedIds == [17])
        #expect(try #require(fit.solutions.first).rmsPx < 8)
    }

    @Test func oneMarkerStillGivesAPose() throws {
        let ref = try PhotoFixture.load()
        let one = ref.markers.filter { $0.id == 5 }
        let fit = BoardSolver.solve(one, layout: try BoardLayout.bundled(), k: ref.k)
        #expect(fit.inliers == [true] && fit.solutions.count == 2)
    }

    @Test func unknownIdsAreIgnored() throws {
        let ref = try PhotoFixture.load()
        var markers = ref.markers
        markers.append(DetectedMarker(id: 99, corners: markers[0].corners))
        let fit = BoardSolver.solve(markers, layout: try BoardLayout.bundled(), k: ref.k)
        #expect(fit.inliers.last == false && fit.usedCount == 70)
    }
}
