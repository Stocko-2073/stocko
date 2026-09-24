import Foundation
import simd

/// One detection frame's view of the page.
public struct PageObservation: Sendable {
    public var time: TimeInterval
    /// The OpenCV camera's pose in the millimetre world, from ARKit, at the
    /// moment of the image the markers were found in.
    public var worldFromCamera: Pose
    /// The planar PnP solutions (camera-from-page), lowest error first.
    public var solutions: [(cameraFromPage: Pose, rmsPx: Double)]
    /// Ids of the markers the solutions used.
    public var markerIds: [Int]
    /// ARKit's tracking generation: bumped whenever the world may have moved
    /// (session resumed, relocalized, reset).
    public var trackingGeneration: Int

    public init(time: TimeInterval, worldFromCamera: Pose, solutions: [(cameraFromPage: Pose, rmsPx: Double)],
                markerIds: [Int], trackingGeneration: Int) {
        self.time = time
        self.worldFromCamera = worldFromCamera
        self.solutions = solutions
        self.markerIds = markerIds
        self.trackingGeneration = trackingGeneration
    }
}

/// Where the page is in ARKit's world, fused over recent detections.
///
/// The page is assumed static on a flat table. Each detection frame gives one
/// estimate (camera pose from ARKit x page pose from PnP); a sliding window of
/// them is averaged with weights for marker count, fit quality and how much of
/// the page the markers cover, so the estimate keeps following ARKit's drift
/// while the markers are in view and holds when they aren't.
public final class BoardPoseFusion {
    public enum Outcome: Equatable, Sendable {
        case accepted
        case rejected(String)
        /// Five consistent estimates far from the old one: the page moved.
        case pageMoved
    }

    public struct Estimate: Sendable, Equatable {
        public var worldFromPage: Pose
        public var locked: Bool
        public var observations: Int
        public var jitterMm: Double
        public var tiltDeg: Double
        public var lastTime: TimeInterval
        public var markers: Int
        public var rmsPx: Double
        /// Bumped each time the page was seen to move; captures carry it.
        public var boardGeneration: Int
    }

    public static let window = 30
    public static let maxAge: TimeInterval = 10
    public static let gravityLimitDeg = 20.0
    public static let jumpMm = 10.0
    public static let jumpDeg = 3.0
    public static let jumpFrames = 5
    public static let lockObservations = 3
    public static let lockJitterMm = 2.0

    private struct Entry {
        let time: TimeInterval
        let worldFromPage: Pose
        let weight: Double
        let markers: Int
        let rmsPx: Double
    }

    private let layout: BoardLayout
    private var entries: [Entry] = []
    private var jumps: [Entry] = []
    private var trackingGeneration: Int?
    private var boardGeneration = 1
    public private(set) var estimate: Estimate?

    public init(layout: BoardLayout) {
        self.layout = layout
    }

    public func reset() {
        entries.removeAll()
        jumps.removeAll()
        estimate = nil
    }

    @discardableResult
    public func observe(_ o: PageObservation) -> Outcome {
        if o.trackingGeneration != trackingGeneration {
            // ARKit's world may have shifted: start over, same page.
            trackingGeneration = o.trackingGeneration
            reset()
        }
        guard !o.solutions.isEmpty else { return .rejected("no solution") }
        let candidates = o.solutions.map { (world: o.worldFromCamera * $0.cameraFromPage, rms: $0.rmsPx) }
        var pick = 0
        if candidates.count == 2, candidates[1].rms < 1.2 * candidates[0].rms {
            // Ambiguous (a small or distant page): trust history, else gravity.
            if let current = estimate?.worldFromPage {
                pick = poseDifference(candidates[1].world, current).deg < poseDifference(candidates[0].world, current).deg ? 1 : 0
            } else {
                pick = Self.tiltDeg(candidates[1].world) < Self.tiltDeg(candidates[0].world) ? 1 : 0
            }
        }
        let candidate = candidates[pick]
        let tilt = Self.tiltDeg(candidate.world)
        guard tilt < Self.gravityLimitDeg else {
            return .rejected(String(format: "page tilted %.0f deg from level", tilt))
        }
        let entry = Entry(time: o.time, worldFromPage: candidate.world,
                          weight: weight(markerIds: o.markerIds, rmsPx: candidate.rms),
                          markers: o.markerIds.count, rmsPx: candidate.rms)
        entries.removeAll { o.time - $0.time > Self.maxAge }

        var outcome = Outcome.accepted
        if let current = estimate, current.locked {
            let (mm, deg) = poseDifference(entry.worldFromPage, current.worldFromPage)
            if mm > Self.jumpMm || deg > Self.jumpDeg {
                jumps.append(entry)
                let latest = jumps.last!.worldFromPage
                jumps.removeAll { let d = poseDifference($0.worldFromPage, latest); return d.mm > Self.jumpMm / 2 || d.deg > Self.jumpDeg }
                guard jumps.count >= Self.jumpFrames else {
                    return .rejected(String(format: "%.0f mm / %.1f deg from the page estimate", mm, deg))
                }
                entries = jumps
                jumps.removeAll()
                boardGeneration += 1
                outcome = .pageMoved
            } else {
                jumps.removeAll()
                entries.append(entry)
            }
        } else {
            entries.append(entry)
        }
        if entries.count > Self.window { entries.removeFirst(entries.count - Self.window) }
        estimate = fuse(lastTime: o.time)
        return outcome
    }

    /// Markers, fit and coverage: one edge of the page pins the pose poorly
    /// about that edge, so a thin spread of markers counts for little.
    private func weight(markerIds: [Int], rmsPx: Double) -> Double {
        let centres = markerIds.compactMap { layout.corners[$0] }.map { $0.reduce(SIMD2<Double>(), +) / 4 }
        guard !centres.isEmpty else { return 0 }
        let mean = centres.reduce(SIMD2<Double>(), +) / Double(centres.count)
        var sxx = 0.0, syy = 0.0, sxy = 0.0
        for c in centres {
            let d = c - mean
            sxx += d.x * d.x; syy += d.y * d.y; sxy += d.x * d.y
        }
        let n = Double(centres.count)
        sxx /= n; syy /= n; sxy /= n
        // Smaller principal spread (mm): ~0 for one straight edge.
        let minor = sqrt(max(0, (sxx + syy) / 2 - sqrt(((sxx - syy) / 2) * ((sxx - syy) / 2) + sxy * sxy)))
        let spread = min(1, max(0.05, minor / 40))
        return Double(4 * centres.count) / pow(max(rmsPx, 0.3), 2) * spread
    }

    private func fuse(lastTime: TimeInterval) -> Estimate? {
        guard let last = entries.last else { return nil }
        let total = entries.reduce(0) { $0 + $1.weight }
        guard total > 0 else { return nil }
        let translation = SIMD3<Double>(
            weightedMedian(entries.map { ($0.worldFromPage.translation.x, $0.weight) }),
            weightedMedian(entries.map { ($0.worldFromPage.translation.y, $0.weight) }),
            weightedMedian(entries.map { ($0.worldFromPage.translation.z, $0.weight) }))
        let reference = simd_quatd(last.worldFromPage.rotation)
        var sum = simd_quatd(vector: SIMD4<Double>())
        for e in entries {
            var q = simd_quatd(e.worldFromPage.rotation)
            if simd_dot(q.vector, reference.vector) < 0 { q = simd_quatd(vector: -q.vector) }
            sum = simd_quatd(vector: sum.vector + e.weight * q.vector)
        }
        let rotation = simd_double3x3(simd_normalize(sum))
        let pose = Pose(rotation: rotation, translation: translation)
        let jitter = sqrt(entries.reduce(0) { $0 + $1.weight * simd_distance_squared($1.worldFromPage.translation, translation) } / total)
        return Estimate(worldFromPage: pose,
                        locked: entries.count >= Self.lockObservations && jitter < Self.lockJitterMm,
                        observations: entries.count, jitterMm: jitter, tiltDeg: Self.tiltDeg(pose),
                        lastTime: lastTime, markers: last.markers, rmsPx: last.rmsPx, boardGeneration: boardGeneration)
    }

    /// Angle between the page's +z and world up.
    public static func tiltDeg(_ worldFromPage: Pose) -> Double {
        angleDeg(worldFromPage.rotation.columns.2, Frames.worldUp)
    }

    /// The camera's pose on the page (the protocol's camera_to_page).
    public func cameraToPage(worldFromCamera: Pose) -> Pose? {
        estimate.map { $0.worldFromPage.rigidInverse * worldFromCamera }
    }
}

func weightedMedian(_ values: [(Double, Double)]) -> Double {
    let sorted = values.sorted { $0.0 < $1.0 }
    let half = sorted.reduce(0) { $0 + $1.1 } / 2
    var acc = 0.0
    for (v, w) in sorted {
        acc += w
        if acc >= half { return v }
    }
    return sorted.last?.0 ?? 0
}
