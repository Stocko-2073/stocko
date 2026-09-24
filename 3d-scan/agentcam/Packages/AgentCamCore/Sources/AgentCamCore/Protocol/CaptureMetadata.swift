import Foundation

/// The body of POST /v1/requests/{rid}/captures/{cid}/commit, stored beside the
/// photo as meta.json. The agent reads this, so every number says its frame:
/// K and poses are for the stored (sensor-native) pixel grid, OpenCV camera axes.
public struct CaptureMetadata: Codable, Sendable, Equatable {
    public struct File: Codable, Sendable, Equatable {
        public var name: String
        public var sha256: String
        public var bytes: Int
        public init(name: String, sha256: String, bytes: Int) {
            self.name = name
            self.sha256 = sha256
            self.bytes = bytes
        }
    }
    public struct Image: Codable, Sendable, Equatable {
        public var file: String
        public var w: Int
        public var h: Int
        public var grid = "sensor"
        public var uprightRotationCwDeg: Int
        public init(file: String, w: Int, h: Int, uprightRotationCwDeg: Int) {
            self.file = file
            self.w = w
            self.h = h
            self.uprightRotationCwDeg = uprightRotationCwDeg
        }
    }
    public struct Intrinsics: Codable, Sendable, Equatable {
        public struct Distortion: Codable, Sendable, Equatable {
            public var model: String
            public init(model: String) { self.model = model }
        }
        public var K: Matrix
        public var source: String
        public var refDims: [Int]
        public var distortion: Distortion
        public init(K: Matrix, source: String, refDims: [Int], distortion: Distortion) {
            self.K = K
            self.source = source
            self.refDims = refDims
            self.distortion = distortion
        }
    }
    public struct Pose: Codable, Sendable, Equatable {
        public var cameraToPage: Matrix?
        /// arkit_live: the frame's own tracked pose; arkit_held: the last pose
        /// before leaving AR for a full-path shot; none: no page lock.
        public var source: String
        public var targetError: AlignmentReport?
        /// Full path only: tracked poses just before and after the shot.
        public var bracket: Bracket?
        public init(cameraToPage: Matrix?, source: String, targetError: AlignmentReport? = nil, bracket: Bracket? = nil) {
            self.cameraToPage = cameraToPage
            self.source = source
            self.targetError = targetError
            self.bracket = bracket
        }
    }
    public struct Bracket: Codable, Sendable, Equatable {
        public var before: Matrix?
        public var after: Matrix?
        public var deltaMm: Double?
        public var deltaDeg: Double?
        public init(before: Matrix?, after: Matrix?, deltaMm: Double?, deltaDeg: Double?) {
            self.before = before
            self.after = after
            self.deltaMm = deltaMm
            self.deltaDeg = deltaDeg
        }
    }
    public struct Lens: Codable, Sendable, Equatable {
        public var id: CaptureOptions.Lens
        public var deviceType: String?
        public var lensPosition: Double?
        public var focusMode: String?
        public var distortionCorrection: Bool?
        public init(id: CaptureOptions.Lens, deviceType: String? = nil, lensPosition: Double? = nil,
                    focusMode: String? = nil, distortionCorrection: Bool? = nil) {
            self.id = id
            self.deviceType = deviceType
            self.lensPosition = lensPosition
            self.focusMode = focusMode
            self.distortionCorrection = distortionCorrection
        }
    }
    public struct Exposure: Codable, Sendable, Equatable {
        public var durationS: Double?
        public var iso: Double?
        public var biasEv: Double?
        public var wbGains: [Double]?
        public var flashFired: Bool?
        public var torch: Double?
        public init(durationS: Double? = nil, iso: Double? = nil, biasEv: Double? = nil, wbGains: [Double]? = nil,
                    flashFired: Bool? = nil, torch: Double? = nil) {
            self.durationS = durationS
            self.iso = iso
            self.biasEv = biasEv
            self.wbGains = wbGains
            self.flashFired = flashFired
            self.torch = torch
        }
    }
    public struct Tracking: Codable, Sendable, Equatable {
        public var arkit: String
        public var boardAgeS: Double?
        public var boardGeneration: Int?
        public var tiltDeg: Double?
        public var speedMmS: Double?
        public var angSpeedDegS: Double?
        /// ARKit's own world pose of the camera (metres, ARKit axes), for debugging.
        public var arkitCameraTransform: Matrix?
        public init(arkit: String, boardAgeS: Double? = nil, boardGeneration: Int? = nil, tiltDeg: Double? = nil,
                    speedMmS: Double? = nil, angSpeedDegS: Double? = nil, arkitCameraTransform: Matrix? = nil) {
            self.arkit = arkit
            self.boardAgeS = boardAgeS
            self.boardGeneration = boardGeneration
            self.tiltDeg = tiltDeg
            self.speedMmS = speedMmS
            self.angSpeedDegS = angSpeedDegS
            self.arkitCameraTransform = arkitCameraTransform
        }
    }
    public struct Depth: Codable, Sendable, Equatable {
        public var file: String
        public var format: String
        public var confidence: String?
        public var w: Int
        public var h: Int
        public var K: Matrix
        public var source: String
        public init(file: String, format: String, confidence: String?, w: Int, h: Int, K: Matrix, source: String) {
            self.file = file
            self.format = format
            self.confidence = confidence
            self.w = w
            self.h = h
            self.K = K
            self.source = source
        }
    }

    public var captureId: String
    public var requestId: String
    public var capturedAt: String
    public var path: String
    public var files: [File]
    public var image: Image
    public var intrinsics: Intrinsics
    public var pose: Pose
    public var lens: Lens?
    public var exposure: Exposure?
    public var tracking: Tracking?
    public var depth: Depth?
    public var placement: String?
    public var warnings: [String]

    public init(captureId: String, requestId: String, capturedAt: String, path: String, files: [File], image: Image,
                intrinsics: Intrinsics, pose: Pose, lens: Lens? = nil, exposure: Exposure? = nil,
                tracking: Tracking? = nil, depth: Depth? = nil, placement: String? = nil, warnings: [String] = []) {
        self.captureId = captureId
        self.requestId = requestId
        self.capturedAt = capturedAt
        self.path = path
        self.files = files
        self.image = image
        self.intrinsics = intrinsics
        self.pose = pose
        self.lens = lens
        self.exposure = exposure
        self.tracking = tracking
        self.depth = depth
        self.placement = placement
        self.warnings = warnings
    }
}
