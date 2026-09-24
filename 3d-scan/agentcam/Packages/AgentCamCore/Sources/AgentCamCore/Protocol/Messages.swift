import Foundation

// Mirrors of the server's models (agentcam/mcp/src/agentcam/models.py). Every file in
// agentcam/protocol/examples decodes with these in AgentCamCoreTests. Matrices are
// row-major [[Double]] on the wire; see Geometry/Pose.swift for simd.

public typealias Matrix = [[Double]]

// MARK: - Requests (server -> phone)

public struct PoseSpec: Codable, Sendable, Equatable {
    public struct Orbit: Codable, Sendable, Equatable {
        public var azimuthDeg: Double
        public var elevationDeg: Double
        public var distanceMm: Double
    }
    public var lookAt: [Double]
    public var orbit: Orbit?
    public var eye: [Double]?
    public var hold: Hold
    public var rollDeg: Double
    public var upHint: [Double]?

    public enum Hold: String, Codable, Sendable { case landscape, portrait }
}

public struct CaptureOptions: Codable, Sendable, Equatable {
    public enum Lens: String, Codable, Sendable, CaseIterable { case wide, ultrawide, telephoto }
    public enum Resolution: String, Codable, Sendable { case mp12 = "12mp", mp48 = "48mp" }
    public enum Raw: String, Codable, Sendable { case none, bayer, proraw }
    public enum Flash: String, Codable, Sendable { case off, on }
    public enum Depth: String, Codable, Sendable { case none, arkit, lidarPhoto = "lidar_photo" }
    public enum Path: String, Codable, Sendable { case auto, fast, full }

    public struct Focus: Codable, Sendable, Equatable {
        public enum Mode: String, Codable, Sendable { case auto, locked, lensPosition = "lens_position" }
        public var mode: Mode
        public var lensPosition: Double?
    }
    public struct Exposure: Codable, Sendable, Equatable {
        public enum Mode: String, Codable, Sendable { case auto, locked, custom }
        public var mode: Mode
        public var durationS: Double?
        public var iso: Double?
        public var biasEv: Double
    }
    public struct WhiteBalance: Codable, Sendable, Equatable {
        public enum Mode: String, Codable, Sendable { case auto, locked, gains }
        public var mode: Mode
        public var gains: [Double]?
    }

    public var lens: Lens
    public var resolution: Resolution
    public var raw: Raw
    public var flash: Flash
    public var torch: Double
    public var depth: Depth
    public var focus: Focus
    public var exposure: Exposure
    public var whiteBalance: WhiteBalance
    public var distortionCorrection: Bool
    public var path: Path

    /// Anything the ARKit camera can't do means leaving AR for the shot
    /// (the same rule as the server's CaptureOptions.needs_full_path).
    public var needsFullPath: Bool {
        path == .full || lens != .wide || resolution == .mp48 || raw != .none || flash == .on || depth == .lidarPhoto
    }
}

public struct Tolerance: Codable, Sendable, Equatable {
    public var positionMm: Double?
    public var pointingDeg: Double
    public var rollDeg: Double
    public var steadyS: Double
    public var maxSpeedMmS: Double
    public var maxAngSpeedDegS: Double
}

public struct Placement: Codable, Sendable, Equatable {
    public var label: String
    public var instruction: String
}

public struct Target: Codable, Sendable, Equatable {
    public var cameraToPage: Matrix
    public var eye: [Double]
    public var lookAt: [Double]
    public var distanceMm: Double
    public var positionToleranceMm: Double
}

public struct PhotoRequest: Codable, Sendable, Equatable, Identifiable {
    /// free: no target; the user frames the shot, taken once the phone is held still.
    public enum Kind: String, Codable, Sendable { case pose, free }

    public var id: String
    public var seq: Int
    public var state: String
    public var kind: Kind
    public var pose: PoseSpec?
    public var options: CaptureOptions
    public var tolerance: Tolerance
    public var placement: Placement?
    public var note: String
    public var target: Target?
    public var preflight: [String]
}

public struct BoardInfo: Codable, Sendable, Equatable {
    public var dictionary: String
    public var printScale: [Double]

    public init(dictionary: String = "DICT_4X4_100", printScale: [Double] = [1, 1]) {
        self.dictionary = dictionary
        self.printScale = printScale
    }
}

public struct Welcome: Codable, Sendable, Equatable {
    public var t: String
    public var v: Int
    public var serverId: String
    public var board: BoardInfo
}

public struct RequestsSnapshot: Codable, Sendable, Equatable {
    public var t: String
    public var v: Int
    public var rev: Int
    public var items: [PhotoRequest]
}

public struct ServerError: Codable, Sendable, Equatable {
    public var t: String
    public var message: String
}

// MARK: - Phone -> server

public struct LensInfo: Codable, Sendable, Equatable {
    public var id: CaptureOptions.Lens
    /// Horizontal and vertical field of view on the sensor grid.
    public var fovDeg: [Double]?
    public var minFocusMm: Double?
    public var maxPhotoDims: [[Int]]?
    public var raw: [String]?
    public var flash: Bool?

    public init(id: CaptureOptions.Lens, fovDeg: [Double]? = nil, minFocusMm: Double? = nil,
                maxPhotoDims: [[Int]]? = nil, raw: [String]? = nil, flash: Bool? = nil) {
        self.id = id
        self.fovDeg = fovDeg
        self.minFocusMm = minFocusMm
        self.maxPhotoDims = maxPhotoDims
        self.raw = raw
        self.flash = flash
    }
}

public struct Hello: Codable, Sendable, Equatable {
    public struct Device: Codable, Sendable, Equatable {
        public var model: String
        public var ios: String
        public var app: String
        public init(model: String, ios: String, app: String) {
            self.model = model
            self.ios = ios
            self.app = app
        }
    }
    public var t = "hello"
    public var v = protocolVersion
    public var appState: String
    public var device: Device
    public var lenses: [LensInfo]
    public var lidar: Bool

    public init(appState: String = "foreground", device: Device, lenses: [LensInfo], lidar: Bool) {
        self.appState = appState
        self.device = device
        self.lenses = lenses
        self.lidar = lidar
    }
}

public struct RequestUpdate: Codable, Sendable, Equatable {
    public var t = "request_update"
    public var v = protocolVersion
    public var id: String
    public var state = "skipped"
    public var reason: String

    public init(id: String, reason: String) {
        self.id = id
        self.reason = reason
    }
}

public struct Bye: Codable, Sendable, Equatable {
    public var t = "bye"
    public var v = protocolVersion
    public var reason: String
    public init(reason: String) { self.reason = reason }
}

/// Sent about twice a second so the agent can see what the phone is doing.
public struct PhoneStatus: Codable, Sendable, Equatable {
    public struct Board: Codable, Sendable, Equatable {
        public var locked: Bool
        public var ageS: Double?
        public var markers: Int
        public var rmsPx: Double?
        public var tiltDeg: Double?
        public var jitterMm: Double?
        public var generation: Int
        public init(locked: Bool, ageS: Double?, markers: Int, rmsPx: Double?, tiltDeg: Double?,
                    jitterMm: Double?, generation: Int) {
            self.locked = locked
            self.ageS = ageS
            self.markers = markers
            self.rmsPx = rmsPx
            self.tiltDeg = tiltDeg
            self.jitterMm = jitterMm
            self.generation = generation
        }
    }
    public struct Tracking: Codable, Sendable, Equatable {
        public var arkit: String
        public var board: Board?
        public init(arkit: String, board: Board?) {
            self.arkit = arkit
            self.board = board
        }
    }
    public struct Active: Codable, Sendable, Equatable {
        public var requestId: String
        public var phase: String
        public var err: AlignmentReport?
        public init(requestId: String, phase: String, err: AlignmentReport?) {
            self.requestId = requestId
            self.phase = phase
            self.err = err
        }
    }
    public struct Outbox: Codable, Sendable, Equatable {
        public var pending: Int
        public var bytes: Int
        public init(pending: Int, bytes: Int) {
            self.pending = pending
            self.bytes = bytes
        }
    }

    public var t = "status"
    public var v = protocolVersion
    public var ts: Double
    public var app: String
    public var thermal: String
    public var battery: Double?
    public var tracking: Tracking
    public var cameraToPage: Matrix?
    public var active: Active?
    public var outbox: Outbox

    public init(ts: Double, app: String, thermal: String, battery: Double?, tracking: Tracking,
                cameraToPage: Matrix?, active: Active?, outbox: Outbox) {
        self.ts = ts
        self.app = app
        self.thermal = thermal
        self.battery = battery
        self.tracking = tracking
        self.cameraToPage = cameraToPage
        self.active = active
        self.outbox = outbox
    }
}

/// How far the phone is from a target, in the target camera's own axes
/// (OpenCV: right, down, forward) plus angles.
public struct AlignmentReport: Codable, Sendable, Equatable {
    public var rightMm: Double
    public var downMm: Double
    public var forwardMm: Double
    public var pointingDeg: Double
    public var rollDeg: Double
    public var steady: Bool?

    public init(rightMm: Double, downMm: Double, forwardMm: Double, pointingDeg: Double, rollDeg: Double,
                steady: Bool? = nil) {
        self.rightMm = rightMm
        self.downMm = downMm
        self.forwardMm = forwardMm
        self.pointingDeg = pointingDeg
        self.rollDeg = rollDeg
        self.steady = steady
    }
}
