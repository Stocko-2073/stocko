import Foundation
import simd

// Frames, as in the server's geometry.py:
//
// - Mat frame: mm, origin at the mat center, +x right, +y toward the marker-0
//   (top) edge, +z up out of the paper.
// - OpenCV camera frame: x right, y down, z forward, on the sensor-native
//   landscape pixel grid (the grid ARKit's capturedImage uses).
// - ARKit camera frame: x right, y up, z backward, same sensor orientation.
// - "World": ARKit's world, but in millimeters, so it composes with the mat.
//
// A transform named `aToB` or `b_from_a` maps points in frame a to frame b.

public typealias Pose = simd_double4x4

public extension simd_double4x4 {
    /// From the wire's row-major [[Double]].
    init?(rows m: Matrix) {
        guard m.count == 4, m.allSatisfy({ $0.count == 4 }) else { return nil }
        self.init(rows: m.map { SIMD4($0[0], $0[1], $0[2], $0[3]) })
    }

    init(rotation r: simd_double3x3, translation t: SIMD3<Double>) {
        self.init(columns: (SIMD4(r.columns.0, 0), SIMD4(r.columns.1, 0), SIMD4(r.columns.2, 0), SIMD4(t, 1)))
    }

    var rowMajor: Matrix {
        (0..<4).map { r in (0..<4).map { c in self[c][r] } }
    }

    var rotation: simd_double3x3 {
        simd_double3x3(columns: (columns.0.xyz, columns.1.xyz, columns.2.xyz))
    }

    var translation: SIMD3<Double> { columns.3.xyz }

    /// Inverse of a rigid transform, exact (no general 4x4 inversion).
    var rigidInverse: simd_double4x4 {
        let rt = rotation.transpose
        return simd_double4x4(rotation: rt, translation: -(rt * translation))
    }

    func transform(_ p: SIMD3<Double>) -> SIMD3<Double> { (self * SIMD4(p, 1)).xyz }
}

public extension SIMD4 where Scalar == Double {
    var xyz: SIMD3<Double> { SIMD3(x, y, z) }
}

public enum Frames {
    /// Maps OpenCV camera coordinates to ARKit camera coordinates: (x, -y, -z).
    public static let openCVToARKitCamera = simd_double4x4(diagonal: SIMD4(1, -1, -1, 1))

    /// ARKit's camera.transform (meters, ARKit camera axes) as the OpenCV
    /// camera's pose in the millimeter world.
    public static func worldFromOpenCVCamera(arkit transform: simd_float4x4) -> simd_double4x4 {
        var t = simd_double4x4(transform)
        t.columns.3 = SIMD4(t.columns.3.xyz * 1000, 1)
        return t * openCVToARKitCamera
    }

    /// World up (ARKit's +y) in the millimeter world.
    public static let worldUp = SIMD3<Double>(0, 1, 0)
}

public extension simd_double4x4 {
    init(_ m: simd_float4x4) {
        self.init(columns: (SIMD4<Double>(m.columns.0), SIMD4<Double>(m.columns.1),
                            SIMD4<Double>(m.columns.2), SIMD4<Double>(m.columns.3)))
    }
}

/// Translation (mm) and rotation (degrees) between two poses. The rotation uses
/// the chord |Ra - Rb| = 2*sqrt(2)*sin(angle/2), which stays exact near zero.
public func poseDifference(_ a: Pose, _ b: Pose) -> (mm: Double, deg: Double) {
    let d = a.rotation - b.rotation
    let fro = sqrt([d.columns.0, d.columns.1, d.columns.2].map { simd_length_squared($0) }.reduce(0, +))
    let chord = min(1, fro / (2 * 2.0.squareRoot()))
    return (simd_distance(a.translation, b.translation), 2 * asin(chord) * 180 / .pi)
}

/// Clockwise quarter turn (0/90/180/270) that shows a sensor-grid image
/// upright: world up, or the mat's top edge when looking straight down.
/// Same rule as the server's geometry.upright_rotation_cw_deg.
public func uprightRotationCwDeg(cameraToMat t: Pose) -> Int {
    let r = t.rotation
    let matUp = SIMD3<Double>(0, 0, 1), matTop = SIMD3<Double>(0, 1, 0)
    let up = abs(simd_dot(r.columns.2, matUp)) > nearVertical ? matTop : matUp
    let u = r.transpose * up                       // up in camera axes
    if abs(u.y) >= abs(u.x) { return u.y < 0 ? 0 : 180 }
    return u.x < 0 ? 90 : 270
}

/// Above this |forward . up| the view is within ~14 degrees of vertical.
public let nearVertical = 0.97
