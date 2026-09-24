import ArucoBridge
import simd

/// The marker dictionaries a mat can be printed with.
public enum MarkerFamily: String, Sendable, Codable, CaseIterable {
    case aruco4x4 = "DICT_4X4_100"
    case apriltag36h11 = "DICT_APRILTAG_36h11"

    var bridge: ACFamily {
        switch self {
        case .aruco4x4: ACFamilyAruco4x4_100
        case .apriltag36h11: ACFamilyAprilTag36h11
        }
    }
}

/// One marker as the detector saw it. Corners are TL, TR, BR, BL as printed, in
/// pixels, with (0, 0) at the center of the top-left pixel (OpenCV's convention,
/// used everywhere in AgentCam).
public struct DetectedMarker: Sendable, Equatable {
    public var id: Int
    public var corners: [SIMD2<Double>]

    public init(id: Int, corners: [SIMD2<Double>]) {
        self.id = id
        self.corners = corners
    }
}

/// OpenCV's ArucoDetector for one dictionary. Detection does not mutate the
/// detector, so one instance may be used from any single queue at a time.
public final class MarkerDetector: @unchecked Sendable {
    public let family: MarkerFamily
    private let handle: OpaquePointer

    public init?(family: MarkerFamily) {
        guard let handle = ac_detector_create(family.bridge) else { return nil }
        self.family = family
        self.handle = handle
    }

    deinit { ac_detector_destroy(handle) }

    /// Detects markers in an 8-bit grayscale image (for ARKit, the Y plane of
    /// `capturedImage`). Returns nil if OpenCV threw.
    public func detect(gray: UnsafeRawPointer, width: Int, height: Int, bytesPerRow: Int) -> [DetectedMarker]? {
        let pixels = gray.assumingMemoryBound(to: UInt8.self)
        var buffer = [ACMarker](repeating: ACMarker(), count: 128)
        var found = ac_detect(handle, pixels, Int32(width), Int32(height), bytesPerRow, &buffer, Int32(buffer.count))
        if found > buffer.count {       // a cluttered scene; retry with room for all of them
            buffer = [ACMarker](repeating: ACMarker(), count: Int(found))
            found = ac_detect(handle, pixels, Int32(width), Int32(height), bytesPerRow, &buffer, Int32(buffer.count))
        }
        guard found >= 0 else { return nil }
        return buffer.prefix(Int(found)).map { m in
            let x = [m.x.0, m.x.1, m.x.2, m.x.3], y = [m.y.0, m.y.1, m.y.2, m.y.3]
            return DetectedMarker(id: Int(m.id), corners: (0..<4).map { SIMD2(Double(x[$0]), Double(y[$0])) })
        }
    }
}

/// One solution of a planar PnP problem: the camera-from-object transform in
/// OpenCV's camera convention (x right, y down, z forward).
public struct PlanarPoseSolution: Sendable, Equatable {
    public var rotation: simd_double3x3
    public var translation: SIMD3<Double>
    public var rmsPx: Double
}

public enum PlanarPnP {
    /// IPPE plus Levenberg-Marquardt refinement for points on the object's z = 0
    /// plane. Returns both IPPE solutions, lowest reprojection error first; the
    /// caller picks between them with a prior (a planar target seen from far
    /// away is ambiguous). Assumes an undistorted pinhole camera `k`.
    public static func solve(object: [SIMD2<Double>], image: [SIMD2<Double>], k: simd_double3x3) -> [PlanarPoseSolution] {
        precondition(object.count == image.count)
        let objectFlat = object.flatMap { [$0.x, $0.y] }
        let imageFlat = image.flatMap { [$0.x, $0.y] }
        let kRowMajor = (0..<9).map { k[$0 % 3][$0 / 3] }
        var out = [ACPlanarPose](repeating: ACPlanarPose(), count: 2)
        let n = ac_solve_planar(objectFlat, imageFlat, Int32(object.count), kRowMajor, &out)
        return out.prefix(Int(n)).map { p in
            let r = withUnsafeBytes(of: p.r) { Array($0.bindMemory(to: Double.self)) }
            let t = withUnsafeBytes(of: p.t) { Array($0.bindMemory(to: Double.self)) }
            let rotation = simd_double3x3(rows: [
                SIMD3(r[0], r[1], r[2]), SIMD3(r[3], r[4], r[5]), SIMD3(r[6], r[7], r[8]),
            ])
            return PlanarPoseSolution(rotation: rotation, translation: SIMD3(t[0], t[1], t[2]), rmsPx: p.rmsPx)
        }
    }
}
