import AgentCamCore
import ArucoBridge
import simd

/// The mat's pose in one image, from its detected markers.
public struct MatFit: Sendable {
    public struct Solution: Sendable {
        public var cameraFromMat: Pose      // OpenCV camera axes, mm
        public var rmsPx: Double
    }
    public var markers: [DetectedMarker]
    /// Parallel to `markers`: used for the pose (false for rejected or unknown ids).
    public var inliers: [Bool]
    /// 0-2 IPPE solutions, lowest error first. A planar target seen from far
    /// away is ambiguous; MatPoseFusion picks with gravity and history.
    public var solutions: [Solution]

    public var usedCount: Int { inliers.filter { $0 }.count }
    public var rejectedIds: [Int] { zip(markers, inliers).filter { !$1 }.map(\.0.id).sorted() }
}

public enum MatSolver {
    /// RANSAC inlier threshold: 35% of the median marker side (3.5 mm on the
    /// paper): generous for a curled mat, far below a misplaced marker.
    public static func thresholdPx(_ markers: [DetectedMarker]) -> Double {
        let sides = markers.map { simd_distance($0.corners[0], $0.corners[1]) }.sorted()
        guard !sides.isEmpty else { return 4 }
        return max(4, 0.35 * sides[sides.count / 2])
    }

    /// Same algorithm as the server's analysis.solve_mat (see ac_solve_mat).
    public static func solve(_ markers: [DetectedMarker], layout: MatLayout, k: simd_double3x3) -> MatFit {
        var fit = MatFit(markers: markers, inliers: Array(repeating: false, count: markers.count), solutions: [])
        let known = markers.indices.filter { layout.corners[markers[$0].id] != nil }
        guard !known.isEmpty else { return fit }
        let ids = known.map { Int32(markers[$0].id) }
        let object = known.flatMap { layout.corners[markers[$0].id]!.flatMap { [$0.x, $0.y] } }
        let image = known.flatMap { markers[$0].corners.flatMap { [$0.x, $0.y] } }
        let kRowMajor = (0..<9).map { k[$0 % 3][$0 / 3] }
        var flags = [UInt8](repeating: 0, count: known.count)
        var out = [ACPlanarPose](repeating: ACPlanarPose(), count: 2)
        let n = ac_solve_mat(ids, object, image, Int32(known.count), kRowMajor,
                               thresholdPx(known.map { markers[$0] }), &flags, &out)
        for (j, i) in known.enumerated() { fit.inliers[i] = flags[j] != 0 }
        fit.solutions = out.prefix(Int(n)).map { p in
            let r = withUnsafeBytes(of: p.r) { Array($0.bindMemory(to: Double.self)) }
            let t = withUnsafeBytes(of: p.t) { Array($0.bindMemory(to: Double.self)) }
            let rotation = simd_double3x3(rows: [SIMD3(r[0], r[1], r[2]), SIMD3(r[3], r[4], r[5]), SIMD3(r[6], r[7], r[8])])
            return MatFit.Solution(cameraFromMat: Pose(rotation: rotation, translation: SIMD3(t[0], t[1], t[2])),
                                     rmsPx: p.rmsPx)
        }
        return fit
    }
}
