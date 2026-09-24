import AgentCamCore
import ARKit
import Combine
import RealityKit
import UIKit

/// What to draw this frame, set by the app model (main thread).
struct GuidanceScene {
    /// Target camera pose on the page and the cube distance for it.
    var target: Pose?
    var lookAt: SIMD3<Double>?
    var cursorDistanceMm: Double = 150
    var aligned = false
    var showPage = true
    /// The page's outline in the page frame (from the board layout in use).
    var pageOutline: [SIMD3<Double>] = []
}

/// Draws the page outline, the target cube, the camera-fixed cursor cube and
/// the target's sight line as thin unlit boxes in ARKit's world. Everything is
/// rebuilt from the displayed frame's own camera transform on each scene
/// update, so the cursor cube is exactly camera-fixed and nothing depends on
/// how RealityKit orients its camera for the portrait screen.
@MainActor
final class GuidanceRenderer {
    var scene = GuidanceScene()

    private let arView: ARView
    private let tracking: ARTrackingSession
    private let root = AnchorEntity(world: .zero)
    private var cursorEdges: [ModelEntity] = []
    private var targetEdges: [ModelEntity] = []
    private var pageEdges: [ModelEntity] = []
    private let sightLine: ModelEntity
    private let bead: ModelEntity
    private var subscription: Cancellable?

    private static let white = UnlitMaterial(color: .white)
    private static let orange = UnlitMaterial(color: .systemOrange)
    private static let yellow = UnlitMaterial(color: .systemYellow)
    private static let green = UnlitMaterial(color: .systemGreen)
    private static let cyan = UnlitMaterial(color: .systemTeal)
    private static let magenta = UnlitMaterial(color: .systemPink)
    private static let unitBox = MeshResource.generateBox(size: 1)

    init(arView: ARView, tracking: ARTrackingSession) {
        self.arView = arView
        self.tracking = tracking
        sightLine = ModelEntity(mesh: Self.unitBox, materials: [Self.magenta])
        bead = ModelEntity(mesh: .generateSphere(radius: 1), materials: [Self.magenta])
        arView.scene.addAnchor(root)
        cursorEdges = (0..<12).map { i in edge(GuidanceGeometry.topEdges.contains(i) ? Self.orange : Self.white) }
        targetEdges = (0..<12).map { _ in edge(Self.yellow) }
        pageEdges = (0..<4).map { _ in edge(Self.cyan) }
        root.addChild(sightLine)
        root.addChild(bead)
        subscription = arView.scene.subscribe(to: SceneEvents.Update.self) { [weak self] _ in
            MainActor.assumeIsolated { self?.update() }
        }
    }

    private func edge(_ material: UnlitMaterial) -> ModelEntity {
        let e = ModelEntity(mesh: Self.unitBox, materials: [material])
        e.isEnabled = false
        root.addChild(e)
        return e
    }

    private func update() {
        guard let frame = arView.session.currentFrame else { return hideAll() }
        let worldFromCamera = Frames.worldFromOpenCVCamera(arkit: frame.camera.transform)
        let cameraCentre = worldFromCamera.translation
        let snap = tracking.snapshot
        let k = simd_double3x3(frame.camera.intrinsics)
        let imageHeight = Double(frame.camera.imageResolution.height)
        let d = scene.cursorDistanceMm
        let side = GuidanceGeometry.cubeSideMm(distanceMm: d, imageHeightPx: imageHeight, fyPx: k[1][1])
        let cube = GuidanceGeometry.cubeCorners(sideMm: side, distanceMm: d)

        place(cursorEdges, corners: cube.map { worldFromCamera.transform($0) }, camera: cameraCentre)

        if let page = snap.page, page.locked {
            let worldFromPage = page.worldFromPage
            let outline = scene.pageOutline
            setEdges(pageEdges, segments: (0..<outline.count).map {
                (worldFromPage.transform(outline[$0]), worldFromPage.transform(outline[($0 + 1) % outline.count]))
            }, camera: cameraCentre, enabled: scene.showPage)
            if let target = scene.target {
                let worldFromTarget = worldFromPage * target
                place(targetEdges, corners: cube.map { worldFromTarget.transform($0) }, camera: cameraCentre)
                let material = scene.aligned ? Self.green : Self.yellow
                for (i, e) in targetEdges.enumerated() {
                    e.model?.materials = [GuidanceGeometry.topEdges.contains(i) ? Self.orange : material]
                }
                if let lookAt = scene.lookAt {
                    let a = worldFromTarget.translation, b = worldFromPage.transform(lookAt)
                    setSegment(sightLine, a, b, camera: cameraCentre)
                    bead.isEnabled = true
                    bead.position = SIMD3<Float>(b / 1000)
                    bead.scale = SIMD3(repeating: Float(max(1.5, 0.008 * simd_distance(b, cameraCentre)) / 1000))
                } else {
                    sightLine.isEnabled = false
                    bead.isEnabled = false
                }
            } else {
                targetEdges.forEach { $0.isEnabled = false }
                sightLine.isEnabled = false
                bead.isEnabled = false
            }
        } else {
            (pageEdges + targetEdges).forEach { $0.isEnabled = false }
            sightLine.isEnabled = false
            bead.isEnabled = false
        }
    }

    private func hideAll() {
        (cursorEdges + targetEdges + pageEdges).forEach { $0.isEnabled = false }
        sightLine.isEnabled = false
        bead.isEnabled = false
    }

    private func place(_ edges: [ModelEntity], corners: [SIMD3<Double>], camera: SIMD3<Double>) {
        setEdges(edges, segments: GuidanceGeometry.cubeEdges.map { (corners[$0.0], corners[$0.1]) }, camera: camera, enabled: true)
    }

    private func setEdges(_ edges: [ModelEntity], segments: [(SIMD3<Double>, SIMD3<Double>)], camera: SIMD3<Double>, enabled: Bool) {
        for (e, s) in zip(edges, segments) {
            if enabled { setSegment(e, s.0, s.1, camera: camera) } else { e.isEnabled = false }
        }
    }

    /// A thin box from a to b (world mm), its thickness growing with distance
    /// so every line is about the same width on screen.
    private func setSegment(_ e: ModelEntity, _ a: SIMD3<Double>, _ b: SIMD3<Double>, camera: SIMD3<Double>) {
        let length = simd_distance(a, b)
        guard length > 1e-6 else { e.isEnabled = false; return }
        let mid = (a + b) / 2
        let thickness = max(0.4, 0.004 * simd_distance(mid, camera))
        e.isEnabled = true
        e.position = SIMD3<Float>(mid / 1000)
        e.orientation = simd_quatf(from: SIMD3(0, 0, 1), to: SIMD3<Float>(simd_normalize(b - a)))
        e.scale = SIMD3(Float(thickness / 1000), Float(thickness / 1000), Float(length / 1000))
    }
}
