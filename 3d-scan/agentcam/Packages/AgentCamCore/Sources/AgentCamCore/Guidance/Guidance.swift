import Foundation
import simd

// Guiding the phone to a requested camera pose. Poses here are camera_to_mat
// (OpenCV camera axes, mat-frame mm) unless named otherwise.

/// The angle between two vectors, exact near zero (unlike acos of the dot).
public func angleDeg(_ a: SIMD3<Double>, _ b: SIMD3<Double>) -> Double {
    atan2(simd_length(simd_cross(a, b)), simd_dot(a, b)) * 180 / .pi
}

public enum Alignment {
    /// Where the phone is relative to the target, in the target camera's axes:
    /// positive rightMm means the phone is to the target's right (so move left).
    public static func report(current: Pose, target: Pose) -> AlignmentReport {
        let rt = target.rotation
        let d = rt.transpose * (current.translation - target.translation)
        let zc = current.rotation.columns.2, zt = rt.columns.2
        let pointing = angleDeg(zc, zt)
        // Roll: the angle between the x axes once projected across the target's view axis.
        let xc = current.rotation.columns.0
        let xp = xc - simd_dot(xc, zt) * zt
        let xt = rt.columns.0
        let roll = atan2(simd_dot(simd_cross(xt, xp), zt), simd_dot(xt, xp)) * 180 / .pi
        return AlignmentReport(rightMm: d.x, downMm: d.y, forwardMm: d.z, pointingDeg: pointing, rollDeg: roll)
    }

    public static func isAligned(_ r: AlignmentReport, positionMm: Double, pointingDeg: Double, rollDeg: Double) -> Bool {
        simd_length(SIMD3(r.rightMm, r.downMm, r.forwardMm)) <= positionMm && r.pointingDeg <= pointingDeg
            && abs(r.rollDeg) <= rollDeg
    }

    /// What to do, largest correction first, for the HUD: "← 23 mm",
    /// "Closer 40 mm", "Aim ↑ 3°", "Twist ↺ 6°". Directions are the phone's own
    /// as the user holds it for this target, so they match the screen.
    public static func hints(_ r: AlignmentReport, hold: PoseSpec.Hold, positionMm: Double,
                             current: Pose? = nil, target: Pose? = nil) -> [String] {
        let (right, down) = screen(r.rightMm, r.downMm, hold)
        var moves: [(Double, String)] = []
        let threshold = positionMm / 2
        if abs(right) > threshold { moves.append((abs(right), String(format: "%@ %.0f mm", right > 0 ? "←" : "→", abs(right)))) }
        if abs(down) > threshold { moves.append((abs(down), String(format: "%@ %.0f mm", down > 0 ? "↑" : "↓", abs(down)))) }
        if abs(r.forwardMm) > threshold {
            moves.append((abs(r.forwardMm), String(format: "%@ %.0f mm", r.forwardMm > 0 ? "Back" : "Closer", abs(r.forwardMm))))
        }
        var out = moves.sorted { $0.0 > $1.0 }.map(\.1)
        if r.pointingDeg > 1.5 {
            var aim = ""
            if let current, let target {
                // Which way the target's view axis lies, seen from this camera.
                let z = current.rotation.transpose * target.rotation.columns.2
                let (x, y) = screen(z.x, z.y, hold)
                aim = abs(x) > abs(y) ? (x > 0 ? "→ " : "← ") : (y > 0 ? "↓ " : "↑ ")
            }
            out.append(String(format: "Aim %@%.0f°", aim, r.pointingDeg))
        }
        if abs(r.rollDeg) > 5 { out.append(String(format: "Twist %@ %.0f°", r.rollDeg > 0 ? "↺" : "↻", abs(r.rollDeg))) }
        return out
    }

    /// Camera x/y components -> the screen's right/down as the phone is held.
    /// Landscape holds keep the sensor grid upright; held portrait, the
    /// screen's right is the camera's -y and its down is the camera's +x.
    static func screen(_ x: Double, _ y: Double, _ hold: PoseSpec.Hold) -> (right: Double, down: Double) {
        hold == .landscape ? (x, y) : (-y, x)
    }
}

/// Getting to views the user can't reach, e.g. with the desk against a wall.
public enum Reach {
    /// How far to turn the mat (degrees, counterclockwise seen from above;
    /// negative is clockwise), object and all, so the target's side of the mat
    /// faces where the user is now. nil when it already roughly does, or when
    /// the view is nearly straight down (reachable from anywhere).
    public static func matTurnDeg(targetEye: SIMD3<Double>, user: SIMD3<Double>) -> Double? {
        let horizontal = simd_length(SIMD2(targetEye.x, targetEye.y))
        guard horizontal > 0.5 * max(targetEye.z, 1), simd_length(SIMD2(user.x, user.y)) > 1 else { return nil }
        let a = atan2(targetEye.y, targetEye.x) * 180 / .pi
        let u = atan2(user.y, user.x) * 180 / .pi
        // Turning the mat by t carries the target around by t; the user stays put.
        var t = u - a
        while t > 180 { t -= 360 }
        while t <= -180 { t += 360 }
        guard abs(t) >= 60 else { return nil }
        return (t / 45).rounded() * 45
    }

    public static func describe(matTurnDeg t: Double) -> String {
        String(format: "Turn the mat %.0f° %@, object and all", abs(t), t > 0 ? "↺" : "↻")
    }
}

/// Is the phone being held still? Over the last `window` seconds, the range of
/// its position and orientation must fit what the speed limits allow.
public final class SteadinessDetector {
    private var samples: [(time: TimeInterval, pose: Pose)] = []

    public init() {}

    public func add(time: TimeInterval, pose: Pose) {
        samples.append((time, pose))
        samples.removeAll { time - $0.time > 2 }
    }

    public func reset() { samples.removeAll() }

    /// (mm/s, deg/s) over the window, or nil until the window is full.
    public func speeds(window: TimeInterval, now: TimeInterval) -> (mmPerS: Double, degPerS: Double)? {
        let recent = samples.filter { now - $0.time <= window + 1e-9 }
        guard let first = recent.first, now - first.time >= window * 0.9, recent.count >= 3 else { return nil }
        var maxMm = 0.0, maxDeg = 0.0
        for a in recent {
            for b in recent where b.time > a.time {
                let d = poseDifference(a.pose, b.pose)
                maxMm = max(maxMm, d.mm)
                maxDeg = max(maxDeg, d.deg)
            }
        }
        return (maxMm / window, maxDeg / window)
    }

    public func isSteady(window: TimeInterval, now: TimeInterval, maxMmPerS: Double, maxDegPerS: Double) -> Bool {
        guard let s = speeds(window: window, now: now) else { return false }
        return s.mmPerS <= maxMmPerS && s.degPerS <= maxDegPerS
    }
}

public enum GuidanceGeometry {
    /// How far in front of the camera both cubes float.
    public static func cursorDistanceMm(targetDistanceMm d: Double) -> Double { min(200, max(60, 0.5 * d)) }

    /// A cube side spanning a third of the view's width at `distance`. The
    /// view shows the whole sensor image in portrait, so its width is the
    /// sensor image's height.
    public static func cubeSideMm(distanceMm d: Double, imageHeightPx: Double, fyPx: Double) -> Double {
        d * imageHeightPx / fyPx / 3
    }

    /// Corners of the cube in a camera's frame (OpenCV axes), centered on the
    /// optical axis at `distance`. Index bit 0: +x, bit 1: +y, bit 2: +z.
    public static func cubeCorners(sideMm s: Double, distanceMm d: Double) -> [SIMD3<Double>] {
        (0..<8).map { i in
            SIMD3((i & 1 == 0 ? -0.5 : 0.5) * s, (i & 2 == 0 ? -0.5 : 0.5) * s, d + (i & 4 == 0 ? -0.5 : 0.5) * s)
        }
    }

    public static let cubeEdges: [(Int, Int)] = [
        (0, 1), (2, 3), (4, 5), (6, 7),       // along x
        (0, 2), (1, 3), (4, 6), (5, 7),       // along y
        (0, 4), (1, 5), (2, 6), (3, 7),       // along z
    ]

    /// Edges on the camera's -x face: the top of the screen as the app is held
    /// (portrait), so a matching colored face means matching roll.
    public static let topEdges: Set<Int> = [4, 6, 8, 10]
}

/// Freeform requests have no target: they're taken as soon as the whole mat is in view (and the phone is steady).
public enum MatFraming {
    public enum Fit: Equatable, Sendable {
        /// Every corner of the mat is in the image.
        case whole
        /// Some of the mat is out of the image (or behind the camera).
        case partly
        /// The mat is in front of the camera but bigger than the image: back up.
        case tooBig
    }

    /// Where the mat's outline (mat frame) falls in an image with intrinsics
    /// `k` and `imageSize` (sensor pixels), for a camera at `cameraToMat`.
    /// A corner counts as in the image when it's at least `marginPx` from the edges.
    public static func fit(outline: [SIMD3<Double>], cameraToMat: Pose, k: simd_double3x3, imageSize: SIMD2<Double>,
                           marginPx: Double) -> Fit {
        let cameraFromMat = cameraToMat.rigidInverse
        let fx = k[0][0], fy = k[1][1], cx = k[2][0], cy = k[2][1]
        var pixels: [SIMD2<Double>] = []
        for corner in outline {
            let p = cameraFromMat.transform(corner)
            guard p.z > 1 else { return .partly }
            pixels.append(SIMD2(fx * p.x / p.z + cx, fy * p.y / p.z + cy))
        }
        guard let first = pixels.first else { return .partly }
        let lo = SIMD2(repeating: marginPx), hi = imageSize - marginPx
        if pixels.allSatisfy({ all($0 .>= lo) && all($0 .<= hi) }) { return .whole }
        let span = pixels.reduce(first, simd_max) - pixels.reduce(first, simd_min)
        return all(span .<= hi - lo) ? .partly : .tooBig
    }
}

/// The 2D direction on screen toward something off screen.
public enum OffscreenArrow {
    /// Sensor pixel direction -> the portrait view's direction. The portrait
    /// view shows the sensor image turned 90 degrees clockwise: sensor +x is
    /// view down, sensor +y is view left.
    public static func viewDirection(sensor d: SIMD2<Double>) -> SIMD2<Double> { SIMD2(-d.y, d.x) }

    /// nil when `p` (a point in the OpenCV camera frame) is within the image,
    /// else the unit direction toward it in view coordinates (x right, y down).
    public static func direction(toCameraPoint p: SIMD3<Double>, k: simd_double3x3, imageSize: SIMD2<Double>,
                                 marginPx: Double = 0) -> SIMD2<Double>? {
        let fx = k[0][0], fy = k[1][1], cx = k[2][0], cy = k[2][1]
        if p.z > 1e-6 {
            let u = SIMD2(fx * p.x / p.z + cx, fy * p.y / p.z + cy)
            if u.x >= marginPx, u.y >= marginPx, u.x <= imageSize.x - marginPx, u.y <= imageSize.y - marginPx {
                return nil
            }
            return simd_normalize(viewDirection(sensor: u - SIMD2(cx, cy)))
        }
        // Behind the camera: turn toward its side; straight behind, turn around (down).
        let lateral = SIMD2(p.x, p.y)
        if simd_length(lateral) < 1e-6 * max(1, abs(p.z)) { return SIMD2(0, 1) }
        return simd_normalize(viewDirection(sensor: lateral))
    }
}
