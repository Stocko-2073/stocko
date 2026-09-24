import AgentCamVision
import CoreGraphics
import Foundation
import ImageIO
import Testing
import simd

/// agentcam/protocol/fixtures, found from this file so no resource copy is needed.
let fixtures = URL(fileURLWithPath: #filePath)
    .deletingLastPathComponent().deletingLastPathComponent().deletingLastPathComponent()
    .deletingLastPathComponent().deletingLastPathComponent()
    .appendingPathComponent("protocol/fixtures")

/// Decodes a JPEG to 8-bit gray on its stored (sensor) pixel grid, ignoring the
/// EXIF orientation, which is how the server reads it (IMREAD_IGNORE_ORIENTATION).
func loadGray(_ url: URL) throws -> (pixels: [UInt8], width: Int, height: Int) {
    let source = try #require(CGImageSourceCreateWithURL(url as CFURL, nil))
    let image = try #require(CGImageSourceCreateImageAtIndex(source, 0, nil))
    let (w, h) = (image.width, image.height)
    var pixels = [UInt8](repeating: 0, count: w * h)
    let ok = pixels.withUnsafeMutableBytes { buffer -> Bool in
        guard let context = CGContext(data: buffer.baseAddress, width: w, height: h, bitsPerComponent: 8,
                                      bytesPerRow: w, space: CGColorSpaceCreateDeviceGray(),
                                      bitmapInfo: CGImageAlphaInfo.none.rawValue) else { return false }
        context.draw(image, in: CGRect(x: 0, y: 0, width: w, height: h))
        return true
    }
    try #require(ok)
    return (pixels, w, h)
}

@Suite struct FixturePhotoTests {
    @Test func detectsEveryMarkerOnThePrintedPage() throws {
        let (pixels, w, h) = try loadGray(fixtures.appendingPathComponent("aruco_border.jpeg"))
        #expect(w == 4032 && h == 3024)
        let detector = try #require(MarkerDetector(family: .aruco4x4))
        let start = Date()
        let markers = try #require(pixels.withUnsafeBytes {
            detector.detect(gray: $0.baseAddress!, width: w, height: h, bytesPerRow: w)
        })
        print("detected \(markers.count) in \(Int(Date().timeIntervalSince(start) * 1000)) ms")
        #expect(Set(markers.map(\.id)) == Set(0..<70))
    }

    @Test func planarPoseOfAKnownSquare() throws {
        // A 10 mm square 300 mm straight ahead, seen by f = 1000 px.
        let k = simd_double3x3(rows: [SIMD3(1000, 0, 960), SIMD3(0, 1000, 720), SIMD3(0, 0, 1)])
        let object: [SIMD2<Double>] = [[-5, -5], [5, -5], [5, 5], [-5, 5]]
        let image = object.map { SIMD2(960 + 1000 * $0.x / 300, 720 + 1000 * $0.y / 300) }
        let best = try #require(PlanarPnP.solve(object: object, image: image, k: k).first)
        #expect(abs(best.translation.z - 300) < 1e-6)
        #expect(best.rmsPx < 1e-6)
    }
}
