import CoreGraphics
import XCTest
import simd
@testable import AgentCam

final class CaptureTests: XCTestCase {
    /// K for an image resampled from 1920x1440 to 4032x3024 keeps pixel centers
    /// at integers, so the principal point doesn't drift by half a pixel.
    func testScalingIntrinsics() {
        let k = simd_double3x3(rows: [SIMD3(1450, 0, 959.5), SIMD3(0, 1450, 719.5), SIMD3(0, 0, 1)])
        let s = CaptureCoordinator.scaled(k, from: CGSize(width: 1920, height: 1440), to: CGSize(width: 4032, height: 3024))
        XCTAssertEqual(s[0][0], 1450 * 2.1, accuracy: 1e-9)
        XCTAssertEqual(s[2][0], 2015.5, accuracy: 1e-9)       // the center of a 4032-wide image
        XCTAssertEqual(s[2][1], 1511.5, accuracy: 1e-9)
        XCTAssertEqual(s.rowMajor[0][2], 2015.5, accuracy: 1e-9)
    }
}
