import AgentCamCore
import AgentCamVision
import ARKit
import os

/// What the rest of the app reads about tracking. Copied out under a lock, so
/// the render loop and the UI never wait on the AR queue.
struct TrackingSnapshot {
    var time: TimeInterval = 0
    /// The OpenCV camera's pose in the millimeter world (ARKit's, scaled).
    var worldFromCamera: Pose?
    var arkit = "not running"
    var isNormal = false
    var k = matrix_identity_double3x3
    var imageSize = SIMD2<Double>(1920, 1440)
    var mat: MatPoseFusion.Estimate?
    var markersSeen = 0
    var markersUsed = 0
    var lastRejection: String?

    var cameraToMat: Pose? {
        guard let mat, mat.locked, let worldFromCamera else { return nil }
        return mat.worldFromMat.rigidInverse * worldFromCamera
    }
}

/// Owns the ARKit session and the mat lock. ARKit calls back on this
/// object's own serial queue; marker detection runs on a second queue so a
/// slow frame never stalls tracking (frames are dropped while it's busy).
final class ARTrackingSession: NSObject, ARSessionDelegate, @unchecked Sendable {
    let session: ARSession
    private let queue = DispatchQueue(label: "com.stocko.agentcam.ar", qos: .userInteractive)
    private let detectQueue = DispatchQueue(label: "com.stocko.agentcam.detect", qos: .userInitiated)
    private let lock = OSAllocatedUnfairLock(initialState: TrackingSnapshot())
    private var detector: MarkerDetector?
    private var fusion: MatPoseFusion?
    private var layout: MatLayout?
    private var detecting = false
    private var lastDetection: TimeInterval = 0
    private var trackingGeneration = 1
    private var wasRelocalizing = false
    static let detectionInterval: TimeInterval = 1.0 / 12

    static var isSupported: Bool { ARWorldTrackingConfiguration.isSupported }

    init(session: ARSession) {
        self.session = session
        super.init()
        session.delegate = self
        session.delegateQueue = queue
        setMat(MatInfo())
    }

    var snapshot: TrackingSnapshot { lock.withLock { $0 } }

    /// The mat to look for (from the server's welcome, including print scale).
    func setMat(_ info: MatInfo) {
        queue.async { [self] in
            guard let layout = try? MatLayout.bundled(info) else { return }
            let family: MarkerFamily = info.dictionary == MarkerFamily.apriltag36h11.rawValue ? .apriltag36h11 : .aruco4x4
            if detector?.family != family { detector = MarkerDetector(family: family) }
            self.layout = layout
            fusion = MatPoseFusion(layout: layout)
            lock.withLock { $0.mat = nil }
        }
    }

    func run() {
        guard Self.isSupported else { return }
        let config = ARWorldTrackingConfiguration()
        if let format = ARWorldTrackingConfiguration.recommendedVideoFormatForHighResolutionFrameCapturing {
            config.videoFormat = format
        }
        if ARWorldTrackingConfiguration.supportsFrameSemantics(.sceneDepth) {
            config.frameSemantics.insert(.sceneDepth)
        }
        config.isAutoFocusEnabled = true
        config.planeDetection = []
        // Always a fresh world. Resuming ARKit's old one means relocalizing,
        // which can wait forever if the phone isn't back where it was, and the
        // mat lock re-acquires from the markers within a second anyway.
        session.run(config, options: [.resetTracking, .removeExistingAnchors])
        queue.async { [self] in trackingGeneration += 1 }
    }

    func pause() {
        session.pause()
        lock.withLock { $0.isNormal = false; $0.arkit = "paused" }
    }

    // MARK: ARSessionDelegate (on `queue`)

    func session(_ session: ARSession, didUpdate frame: ARFrame) {
        let camera = frame.camera
        let worldFromCamera = Frames.worldFromOpenCVCamera(arkit: camera.transform)
        let k = simd_double3x3(camera.intrinsics)
        let size = SIMD2(Double(camera.imageResolution.width), Double(camera.imageResolution.height))
        let normal = camera.trackingState == .normal
        let mat = fusion?.estimate
        lock.withLock {
            $0.time = frame.timestamp
            $0.worldFromCamera = worldFromCamera
            $0.k = k
            $0.imageSize = size
            $0.isNormal = normal
            $0.arkit = Self.describe(camera.trackingState)
            $0.mat = mat
        }
        guard normal, !detecting, frame.timestamp - lastDetection >= Self.detectionInterval,
              let detector, let layout else { return }
        guard let gray = GrayImage(frame.capturedImage) else { return }
        detecting = true
        lastDetection = frame.timestamp
        let generation = trackingGeneration
        let time = frame.timestamp
        detectQueue.async { [weak self] in
            let markers = gray.withPixels { detector.detect(gray: $0, width: gray.width, height: gray.height, bytesPerRow: gray.width) } ?? []
            let fit = MatSolver.solve(markers, layout: layout, k: k)
            self?.queue.async { self?.finishDetection(fit, worldFromCamera: worldFromCamera, time: time, generation: generation) }
        }
    }

    private func finishDetection(_ fit: MatFit, worldFromCamera: Pose, time: TimeInterval, generation: Int) {
        detecting = false
        var rejection: String?
        if generation == trackingGeneration, let fusion, !fit.solutions.isEmpty {
            let used = zip(fit.markers, fit.inliers).filter(\.1).map(\.0.id)
            let outcome = fusion.observe(MatObservation(
                time: time, worldFromCamera: worldFromCamera,
                solutions: fit.solutions.map { ($0.cameraFromMat, $0.rmsPx) },
                markerIds: used, trackingGeneration: generation))
            if case .rejected(let why) = outcome { rejection = why }
        }
        let mat = fusion?.estimate
        let why = rejection
        lock.withLock {
            $0.markersSeen = fit.markers.count
            $0.markersUsed = fit.usedCount
            $0.lastRejection = why
            $0.mat = mat
        }
    }

    func session(_ session: ARSession, cameraDidChangeTrackingState camera: ARCamera) {
        if case .limited(.relocalizing) = camera.trackingState {
            wasRelocalizing = true
        } else if camera.trackingState == .normal, wasRelocalizing {
            // Relocalized: ARKit may have shifted its world under the mat.
            wasRelocalizing = false
            trackingGeneration += 1
        }
    }

    func sessionInterruptionEnded(_ session: ARSession) { trackingGeneration += 1 }

    /// No: after an interruption ARKit would otherwise sit in "relocalizing"
    /// until the phone returns to its old spot, and markers are only looked
    /// for while tracking is normal. A fresh start re-finds the mat at once.
    func sessionShouldAttemptRelocalization(_ session: ARSession) -> Bool { false }

    func session(_ session: ARSession, didFailWithError error: Error) {
        lock.withLock { $0.arkit = "failed: \(error.localizedDescription)"; $0.isNormal = false }
    }

    static func describe(_ state: ARCamera.TrackingState) -> String {
        switch state {
        case .normal: "normal"
        case .notAvailable: "not available"
        case .limited(.initializing): "initializing"
        case .limited(.relocalizing): "relocalizing"
        case .limited(.excessiveMotion): "moving too fast"
        case .limited(.insufficientFeatures): "too few features"
        case .limited: "limited"
        }
    }
}

/// A copy of a frame's luma plane, so the ARFrame is released at once (ARKit
/// stalls if frames are held) and detection can run on another queue.
struct GrayImage: @unchecked Sendable {
    let width: Int
    let height: Int
    private let pixels: [UInt8]

    init?(_ buffer: CVPixelBuffer) {
        CVPixelBufferLockBaseAddress(buffer, .readOnly)
        defer { CVPixelBufferUnlockBaseAddress(buffer, .readOnly) }
        guard CVPixelBufferGetPlaneCount(buffer) >= 1, let base = CVPixelBufferGetBaseAddressOfPlane(buffer, 0) else { return nil }
        let (w, h) = (CVPixelBufferGetWidthOfPlane(buffer, 0), CVPixelBufferGetHeightOfPlane(buffer, 0))
        let stride = CVPixelBufferGetBytesPerRowOfPlane(buffer, 0)
        var out = [UInt8](repeating: 0, count: w * h)
        out.withUnsafeMutableBytes { dst in
            for row in 0..<h {
                memcpy(dst.baseAddress! + row * w, base + row * stride, w)
            }
        }
        width = w
        height = h
        pixels = out
    }

    func withPixels<R>(_ body: (UnsafeRawPointer) -> R) -> R {
        pixels.withUnsafeBytes { body($0.baseAddress!) }
    }
}

extension simd_double3x3 {
    init(_ m: simd_float3x3) {
        self.init(columns: (SIMD3<Double>(m.columns.0), SIMD3<Double>(m.columns.1), SIMD3<Double>(m.columns.2)))
    }
}
