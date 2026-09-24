import AgentCamCore
import ARKit
import CoreGraphics
import Foundation

struct CaptureResult {
    var requestId: String
    var captureId: String
    var thumbnail: CGImage?
    var hadPagePose: Bool
}

enum CaptureError: LocalizedError {
    case busy
    case needsFullPath
    case arkit(String)
    case encoding

    var errorDescription: String? {
        switch self {
        case .busy: "Already taking a photo."
        case .needsFullPath: "This request needs a lens, flash or format that leaves AR, which this build can't do yet."
        case .arkit(let why): "The camera didn't take the photo: \(why)"
        case .encoding: "The photo couldn't be encoded."
        }
    }
}

/// Takes the photo for a request and puts it in the outbox. The fast path is
/// ARKit's own 12 MP still, so tracking (and the pose) carry on unbroken.
@MainActor
final class CaptureCoordinator {
    private let tracking: ARTrackingSession
    private let outbox: Outbox
    private let uploader: Uploader
    private let work = DispatchQueue(label: "com.stocko.agentcam.capture", qos: .userInitiated)
    private(set) var busy = false

    init(tracking: ARTrackingSession, outbox: Outbox, uploader: Uploader) {
        self.tracking = tracking
        self.outbox = outbox
        self.uploader = uploader
    }

    func capture(_ request: PhotoRequest, placement: String?, speeds: (mmPerS: Double, degPerS: Double)?,
                 completion: @escaping (Result<CaptureResult, Error>) -> Void) {
        guard !busy else { return completion(.failure(CaptureError.busy)) }
        guard !request.options.needsFullPath else { return completion(.failure(CaptureError.needsFullPath)) }
        busy = true
        CameraControls.lockForShot(request.options)
        let before = tracking.snapshot
        let (lens, exposure) = CameraControls.describe(torch: request.options.torch)
        tracking.session.captureHighResolutionFrame { [weak self] frame, error in
            guard let self else { return }
            guard let frame else {
                Task { @MainActor in
                    self.busy = false
                    completion(.failure(CaptureError.arkit(error?.localizedDescription ?? "no frame")))
                }
                return
            }
            self.work.async {
                let result = Result {
                    try Self.store(frame: frame, request: request, placement: placement, before: before, lens: lens,
                                   exposure: exposure, speeds: speeds, outbox: self.outbox)
                }
                Task { @MainActor in
                    self.busy = false
                    if case .success = result { self.uploader.poke() }
                    completion(result)
                }
            }
        }
    }

    nonisolated private static func store(frame: ARFrame, request: PhotoRequest, placement: String?, before: TrackingSnapshot,
                                          lens: CaptureMetadata.Lens, exposure: CaptureMetadata.Exposure,
                                          speeds: (mmPerS: Double, degPerS: Double)?, outbox: Outbox) throws -> CaptureResult {
        let buffer = frame.capturedImage
        guard let jpeg = Encoding.jpeg(buffer) else { throw CaptureError.encoding }
        let (w, h) = (CVPixelBufferGetWidth(buffer), CVPixelBufferGetHeight(buffer))
        let camera = frame.camera
        let k = scaled(simd_double3x3(camera.intrinsics), from: camera.imageResolution, to: CGSize(width: w, height: h))
        let worldFromCamera = Frames.worldFromOpenCVCamera(arkit: camera.transform)

        var cameraToPage: Pose?
        if let page = before.page, page.locked { cameraToPage = page.worldFromPage.rigidInverse * worldFromCamera }
        let rotation = uprightRotationCwDeg(cameraToPage: cameraToPage ?? levelFrame.rigidInverse * worldFromCamera)
        let target = request.target.flatMap { Pose(rows: $0.cameraToPage) }
        let targetError = cameraToPage.flatMap { c in target.map { Alignment.report(current: c, target: $0) } }

        var files: [(name: String, data: Data)] = [("image.jpg", jpeg)]
        var depth: CaptureMetadata.Depth?
        if request.options.depth == .arkit, let scene = frame.sceneDepth ?? frame.smoothedSceneDepth,
           let d = Encoding.depthPNG(scene.depthMap) {
            files.append(("depth.png", d.data))
            var confidence: String?
            if let c = scene.confidenceMap.flatMap(Encoding.confidencePNG) {
                files.append(("confidence.png", c))
                confidence = "confidence.png"
            }
            let kd = scaled(k, from: CGSize(width: w, height: h), to: CGSize(width: d.width, height: d.height))
            depth = .init(file: "depth.png", format: "uint16_mm", confidence: confidence, w: d.width, h: d.height,
                          K: kd.rowMajor, source: "arkit_scene_depth")
        }

        let captureId = UUID().uuidString.replacingOccurrences(of: "-", with: "").prefix(16).lowercased()
        var warnings: [String] = []
        if cameraToPage == nil { warnings.append("the page wasn't locked, so this photo has no page pose") }
        let meta = CaptureMetadata(
            captureId: String(captureId), requestId: request.id, capturedAt: Self.timestamp(), path: "fast", files: [],
            image: .init(file: "image.jpg", w: w, h: h, uprightRotationCwDeg: rotation),
            intrinsics: .init(K: k.rowMajor, source: "arkit", refDims: [w, h], distortion: .init(model: "none")),
            pose: .init(cameraToPage: cameraToPage?.rowMajor, source: cameraToPage == nil ? "none" : "arkit_live",
                        targetError: targetError),
            lens: lens, exposure: exposure,
            tracking: .init(arkit: ARTrackingSession.describe(camera.trackingState),
                            boardAgeS: before.page.map { before.time - $0.lastTime },
                            boardGeneration: before.page?.boardGeneration, tiltDeg: before.page?.tiltDeg,
                            speedMmS: speeds?.mmPerS, angSpeedDegS: speeds?.degPerS,
                            arkitCameraTransform: simd_double4x4(camera.transform).rowMajor),
            depth: depth, placement: placement, warnings: warnings)
        try outbox.add(meta, files: files)
        return CaptureResult(requestId: request.id, captureId: String(captureId),
                             thumbnail: Encoding.thumbnail(buffer, rotationCw: rotation), hadPagePose: cameraToPage != nil)
    }

    /// A level frame in ARKit's world (+z up), for "which way is up" when
    /// there's no page pose yet.
    nonisolated static let levelFrame = Pose(rotation: simd_double3x3(simd_quatd(angle: -.pi / 2, axis: SIMD3(1, 0, 0))),
                                             translation: .zero)

    /// K for an image resampled from `from` to `to` pixels (pixel centres at integers).
    nonisolated static func scaled(_ k: simd_double3x3, from: CGSize, to: CGSize) -> simd_double3x3 {
        let sx = Double(to.width / from.width), sy = Double(to.height / from.height)
        guard abs(sx - 1) > 1e-9 || abs(sy - 1) > 1e-9 else { return k }
        var out = k
        out[0][0] *= sx
        out[1][1] *= sy
        out[2][0] = (k[2][0] + 0.5) * sx - 0.5
        out[2][1] = (k[2][1] + 0.5) * sy - 0.5
        return out
    }

    nonisolated static func timestamp() -> String {
        let f = ISO8601DateFormatter()
        f.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        return f.string(from: Date())
    }
}

private func scaled(_ k: simd_double3x3, from: CGSize, to: CGSize) -> simd_double3x3 {
    CaptureCoordinator.scaled(k, from: from, to: to)
}

extension simd_double3x3 {
    var rowMajor: Matrix { (0..<3).map { r in (0..<3).map { c in self[c][r] } } }
}
