import Foundation
import Testing
import simd
@testable import AgentCamCore

/// A world where the mat lies level on a table, as ARKit would report it.
struct SyntheticWorld {
    // ARKit's world is y-up; the mat's +z is up, so rotate mat -> world by
    // -90 deg about x (mat +y goes to world -z), then place it.
    let worldFromMat: Pose = {
        let r = simd_double3x3(simd_quatd(angle: -.pi / 2, axis: SIMD3(1, 0, 0)))
        let yaw = simd_double3x3(simd_quatd(angle: 0.4, axis: SIMD3(0, 1, 0)))
        return Pose(rotation: yaw * r, translation: SIMD3(120, -700, -350))
    }()
    let layout = try! MatLayout.bundled()

    /// A camera (OpenCV axes) at `eye` in the mat frame looking at `target`.
    func camera(eye: SIMD3<Double>, target: SIMD3<Double> = .zero) -> Pose {
        let z = simd_normalize(target - eye)
        let up = abs(simd_dot(z, SIMD3(0, 0, 1))) > 0.97 ? SIMD3<Double>(0, 1, 0) : SIMD3<Double>(0, 0, 1)
        let y = -simd_normalize(up - simd_dot(up, z) * z)
        let x = simd_cross(y, z)
        return worldFromMat * Pose(rotation: simd_double3x3(columns: (x, y, z)), translation: eye)
    }

    func observation(worldFromCamera: Pose, time: TimeInterval, noiseMm: Double = 0, noiseDeg: Double = 0,
                     rms: Double = 0.5, ids: [Int]? = nil, generation: Int = 1, flip: Bool = false,
                     mat: Pose? = nil, rng: inout SystemRandomNumberGenerator) -> MatObservation {
        // `mat`: where the mat really is now, if it has been moved.
        var cameraFromMat = worldFromCamera.rigidInverse * (mat ?? worldFromMat)
        let axis = simd_normalize(SIMD3(Double.random(in: -1...1, using: &rng), Double.random(in: -1...1, using: &rng), 1))
        let q = simd_quatd(angle: noiseDeg * .pi / 180, axis: axis)
        cameraFromMat = Pose(rotation: simd_double3x3(q) * cameraFromMat.rotation,
                              translation: cameraFromMat.translation + SIMD3(Double.random(in: -1...1, using: &rng),
                                                                              Double.random(in: -1...1, using: &rng),
                                                                              Double.random(in: -1...1, using: &rng)) * noiseMm)
        // IPPE's other solution: the mat tilted the other way about the view.
        let other = Pose(rotation: simd_double3x3(simd_quatd(angle: 0.6, axis: SIMD3(1, 0, 0))) * cameraFromMat.rotation,
                         translation: cameraFromMat.translation)
        let solutions = flip ? [(other, rms), (cameraFromMat, rms * 1.05)] : [(cameraFromMat, rms), (other, rms * 1.05)]
        return MatObservation(time: time, worldFromCamera: worldFromCamera, solutions: solutions,
                               markerIds: ids ?? Array(0..<70), trackingGeneration: generation)
    }
}

@Suite struct MatPoseFusionTests {
    @Test func locksOntoALevelMat() {
        let w = SyntheticWorld()
        let fusion = MatPoseFusion(layout: w.layout)
        var rng = SystemRandomNumberGenerator()
        for i in 0..<10 {
            let cam = w.camera(eye: SIMD3(Double(i) * 20 - 100, -250, 300))
            #expect(fusion.observe(w.observation(worldFromCamera: cam, time: Double(i) / 10, noiseMm: 0.5,
                                                 noiseDeg: 0.1, flip: i % 3 == 0, rng: &rng)) == .accepted)
        }
        let e = try! #require(fusion.estimate)
        #expect(e.locked)
        let (mm, deg) = poseDifference(e.worldFromMat, w.worldFromMat)
        #expect(mm < 1 && deg < 0.2, "\(mm) mm \(deg) deg")
        #expect(e.tiltDeg < 0.5)
        // The protocol's camera_to_mat for a camera we know.
        let eye = SIMD3<Double>(10, -200, 250)
        let c2p = try! #require(fusion.cameraToMat(worldFromCamera: w.camera(eye: eye)))
        #expect(simd_distance(c2p.translation, eye) < 1.5)
    }

    @Test func aTiltedEstimateIsRejected() {
        let w = SyntheticWorld()
        let fusion = MatPoseFusion(layout: w.layout)
        var rng = SystemRandomNumberGenerator()
        let cam = w.camera(eye: SIMD3(0, -250, 300))
        var o = w.observation(worldFromCamera: cam, time: 0, rng: &rng)
        let tilted = Pose(rotation: simd_double3x3(simd_quatd(angle: 0.6, axis: SIMD3(1, 0, 0))) * o.solutions[0].0.rotation,
                          translation: o.solutions[0].0.translation)
        o.solutions = [(tilted, 0.5)]
        if case .rejected(let why) = fusion.observe(o) { #expect(why.contains("tilted")) } else { Issue.record("accepted") }
    }

    @Test func aMovedMatIsFollowedAfterConsistentEvidence() {
        let w = SyntheticWorld()
        let fusion = MatPoseFusion(layout: w.layout)
        var rng = SystemRandomNumberGenerator()
        let cam = w.camera(eye: SIMD3(0, -250, 300))
        for i in 0..<5 { fusion.observe(w.observation(worldFromCamera: cam, time: Double(i) / 10, rng: &rng)) }
        // One wild estimate is an outlier...
        let moved = Pose(rotation: w.worldFromMat.rotation, translation: w.worldFromMat.translation + SIMD3(40, 0, 0))
        #expect(fusion.observe(w.observation(worldFromCamera: cam, time: 1, mat: moved, rng: &rng)) != .accepted)
        // ...five in a row (counting that one) mean the mat was moved 40 mm.
        var outcomes: [MatPoseFusion.Outcome] = []
        for i in 0..<5 {
            outcomes.append(fusion.observe(w.observation(worldFromCamera: cam, time: 1.1 + Double(i) / 10, mat: moved, rng: &rng)))
        }
        #expect(outcomes.filter { $0 == .matMoved }.count == 1)
        #expect(outcomes.last == .accepted)
        #expect(fusion.estimate?.matGeneration == 2)
        #expect(simd_distance(fusion.estimate!.worldFromMat.translation, w.worldFromMat.translation) > 30)
    }

    @Test func aTrackingResetStartsOverWithoutCallingItAMove() {
        let w = SyntheticWorld()
        let fusion = MatPoseFusion(layout: w.layout)
        var rng = SystemRandomNumberGenerator()
        let cam = w.camera(eye: SIMD3(0, -250, 300))
        for i in 0..<5 { fusion.observe(w.observation(worldFromCamera: cam, time: Double(i) / 10, rng: &rng)) }
        fusion.observe(w.observation(worldFromCamera: cam, time: 1, generation: 2, rng: &rng))
        #expect(fusion.estimate?.observations == 1 && fusion.estimate?.locked == false)
        #expect(fusion.estimate?.matGeneration == 1)
    }

    @Test func oneEdgeCountsForLittle() {
        let w = SyntheticWorld()
        let fusion = MatPoseFusion(layout: w.layout)
        var rng = SystemRandomNumberGenerator()
        let cam = w.camera(eye: SIMD3(0, -250, 300))
        // Good full-mat views, then one-edge views that are 3 mm off: the
        // estimate should stay with the full-mat ones.
        for i in 0..<5 { fusion.observe(w.observation(worldFromCamera: cam, time: Double(i) / 10, rng: &rng)) }
        let off = Pose(rotation: w.worldFromMat.rotation, translation: w.worldFromMat.translation + SIMD3(3, 0, 0))
        for i in 0..<5 {
            fusion.observe(w.observation(worldFromCamera: cam, time: 1 + Double(i) / 10, ids: Array(0..<16), mat: off,
                                         rng: &rng))
        }
        #expect(simd_distance(fusion.estimate!.worldFromMat.translation, w.worldFromMat.translation) < 1)
    }
}

@Suite struct GuidanceTests {
    let w = SyntheticWorld()

    func matCamera(eye: SIMD3<Double>) -> Pose { w.worldFromMat.rigidInverse * w.camera(eye: eye) }

    @Test func alignmentSaysWhichWayToMove() {
        let target = matCamera(eye: SIMD3(0, -250, 300))
        let right = Pose(rotation: target.rotation, translation: target.translation + target.rotation.columns.0 * 20)
        let r = Alignment.report(current: right, target: target)
        #expect(abs(r.rightMm - 20) < 1e-9 && abs(r.downMm) < 1e-9 && r.pointingDeg < 1e-6)
        #expect(Alignment.hints(r, hold: .landscape, positionMm: 8).first == "← 20 mm")
        #expect(!Alignment.isAligned(r, positionMm: 8, pointingDeg: 3, rollDeg: 10))
        #expect(Alignment.isAligned(Alignment.report(current: target, target: target), positionMm: 8, pointingDeg: 3, rollDeg: 10))
        // Held portrait, the camera's +x is the screen's down.
        #expect(Alignment.hints(r, hold: .portrait, positionMm: 8).first == "↑ 20 mm")
    }

    @Test func rollAndPointingAreSeparate() {
        let target = matCamera(eye: SIMD3(0, -250, 300))
        let rolled = Pose(rotation: target.rotation * simd_double3x3(simd_quatd(angle: 0.2, axis: SIMD3(0, 0, 1))),
                          translation: target.translation)
        let r = Alignment.report(current: rolled, target: target)
        #expect(abs(abs(r.rollDeg) - 11.459) < 0.01 && r.pointingDeg < 1e-6)
        let tipped = Pose(rotation: target.rotation * simd_double3x3(simd_quatd(angle: 0.05, axis: SIMD3(1, 0, 0))),
                          translation: target.translation)
        let t = Alignment.report(current: tipped, target: target)
        #expect(abs(t.pointingDeg - 2.865) < 0.01 && abs(t.rollDeg) < 0.01)
        // Pitched up (about +x), the target's axis is below: aim down.
        #expect(Alignment.hints(t, hold: .landscape, positionMm: 8, current: tipped, target: target) == ["Aim ↓ 3°"])
        // Rolled clockwise as the user sees it: twist back counterclockwise.
        #expect(Alignment.hints(r, hold: .portrait, positionMm: 8).last == "Twist ↺ 11°")
    }

    @Test func turningTheMatBringsAViewWithinReach() {
        let near = SIMD3<Double>(0, -300, 300)                 // the user, at the mat's bottom edge
        #expect(Reach.matTurnDeg(targetEye: SIMD3(212, 0, 212), user: near) == -90)       // right side: turn clockwise
        #expect(Reach.describe(matTurnDeg: -90) == "Turn the mat 90° ↻, object and all")
        #expect(Reach.matTurnDeg(targetEye: SIMD3(0, 250, 200), user: near) == 180)       // far side
        #expect(Reach.matTurnDeg(targetEye: SIMD3(-10, -250, 200), user: near) == nil)    // already this side
        #expect(Reach.matTurnDeg(targetEye: SIMD3(0, 20, 380), user: near) == nil)        // straight down
    }

    @Test func steadinessNeedsAFullStillWindow() {
        let s = SteadinessDetector()
        let p = matCamera(eye: SIMD3(0, -250, 300))
        for i in 0..<10 {       // tremor: +/-1 mm at 20 Hz
            let jiggle = Pose(rotation: p.rotation, translation: p.translation + SIMD3(i % 2 == 0 ? 1 : -1, 0, 0))
            s.add(time: Double(i) / 20, pose: jiggle)
        }
        #expect(s.isSteady(window: 0.4, now: 0.45, maxMmPerS: 10, maxDegPerS: 1.5))
        #expect(!s.isSteady(window: 1.0, now: 0.45, maxMmPerS: 10, maxDegPerS: 1.5))   // not enough history
        let moved = Pose(rotation: p.rotation, translation: p.translation + SIMD3(30, 0, 0))
        s.add(time: 0.5, pose: moved)
        #expect(!s.isSteady(window: 0.4, now: 0.5, maxMmPerS: 10, maxDegPerS: 1.5))
    }

    @Test func arrowPointsTowardOffscreenTargets() {
        let k = simd_double3x3(rows: [SIMD3(1450, 0, 960), SIMD3(0, 1450, 720), SIMD3(0, 0, 1)])
        let size = SIMD2<Double>(1920, 1440)
        #expect(OffscreenArrow.direction(toCameraPoint: SIMD3(0, 0, 300), k: k, imageSize: size) == nil)
        // Far to the sensor's +x: the portrait view's down.
        let d = OffscreenArrow.direction(toCameraPoint: SIMD3(900, 0, 300), k: k, imageSize: size)!
        #expect(simd_distance(d, SIMD2(0, 1)) < 1e-9)
        // Sensor +y is view left.
        let e = OffscreenArrow.direction(toCameraPoint: SIMD3(0, 900, 300), k: k, imageSize: size)!
        #expect(simd_distance(e, SIMD2(-1, 0)) < 1e-9)
        // Behind, off to the sensor's -x: view up.
        let b = OffscreenArrow.direction(toCameraPoint: SIMD3(-50, 0, -300), k: k, imageSize: size)!
        #expect(simd_distance(b, SIMD2(0, -1)) < 1e-9)
    }

    @Test func aFreeformShotNeedsTheWholeMatInView() {
        let k = simd_double3x3(rows: [SIMD3(1450, 0, 960), SIMD3(0, 1450, 720), SIMD3(0, 0, 1)])
        let size = SIMD2<Double>(1920, 1440)
        func fit(eye: SIMD3<Double>, looking target: SIMD3<Double>) -> MatFraming.Fit {
            MatFraming.fit(outline: w.layout.outline, cameraToMat: w.worldFromMat.rigidInverse * w.camera(eye: eye, target: target),
                            k: k, imageSize: size, marginPx: 20)
        }
        #expect(fit(eye: SIMD3(0, 0, 600), looking: .zero) == .whole)
        #expect(fit(eye: SIMD3(0, -350, 350), looking: .zero) == .whole)
        // Straight down from 200 mm, the mat's 279 mm length is ~2000 px: more than the image.
        #expect(fit(eye: SIMD3(0, 0, 200), looking: .zero) == .tooBig)
        // From 600 mm but over the mat's right edge: it would fit, it's just off to one side.
        #expect(fit(eye: SIMD3(300, 0, 600), looking: SIMD3(300, 0, 0)) == .partly)
        // Low across the paper, the near corners are behind the camera.
        #expect(fit(eye: SIMD3(0, 0, 50), looking: SIMD3(0, 300, 50)) == .partly)
    }

    @Test func cubesAreAThirdOfTheViewAcross() {
        let d = GuidanceGeometry.cursorDistanceMm(targetDistanceMm: 300)
        #expect(d == 150)
        #expect(GuidanceGeometry.cursorDistanceMm(targetDistanceMm: 40) == 60)
        let side = GuidanceGeometry.cubeSideMm(distanceMm: d, imageHeightPx: 1440, fyPx: 1450)
        #expect(abs(side * 3 - d * 1440 / 1450) < 1e-9)
        let corners = GuidanceGeometry.cubeCorners(sideMm: side, distanceMm: d)
        for e in GuidanceGeometry.cubeEdges { #expect(abs(simd_distance(corners[e.0], corners[e.1]) - side) < 1e-9) }
        for e in GuidanceGeometry.topEdges { #expect(corners[GuidanceGeometry.cubeEdges[e].0].x < 0 && corners[GuidanceGeometry.cubeEdges[e].1].x < 0) }
    }
}
