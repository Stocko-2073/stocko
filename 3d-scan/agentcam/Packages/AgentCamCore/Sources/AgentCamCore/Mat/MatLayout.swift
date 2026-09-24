import Foundation
import simd

/// The printed marker mat (3d-scan/workmat_aruco_4x4_10mm.pdf) in the mat frame.
public struct MatLayout: Sendable {
    public let dictionary: String
    public let markerMm: Double
    public let matMm: SIMD2<Double>
    public let printScale: SIMD2<Double>
    /// id -> corners TL, TR, BR, BL as printed, mat-frame mm on z = 0.
    public let corners: [Int: [SIMD2<Double>]]

    public static let layoutFiles = [
        "DICT_4X4_100": "workmat_aruco_4x4_10mm",
        "DICT_APRILTAG_36h11": "workmat_apriltag_36h11_10mm",
    ]

    struct File: Decodable {
        struct Marker: Decodable {
            let id: Int
            let corners: [[Double]]
        }
        let dictionary: String
        let markerMm: Double
        let matMm: [Double]
        let markers: [Marker]
    }

    /// The bundled layout for a dictionary, scaled by the measured print scale.
    public static func bundled(_ info: MatInfo = MatInfo()) throws -> MatLayout {
        guard let name = layoutFiles[info.dictionary],
              let url = Bundle.module.url(forResource: name, withExtension: "json", subdirectory: "mats")
        else { throw CocoaError(.fileNoSuchFile) }
        let scale = info.printScale.count == 2 ? SIMD2(info.printScale[0], info.printScale[1]) : SIMD2(1, 1)
        return try MatLayout(json: Data(contentsOf: url), printScale: scale)
    }

    public init(json: Data, printScale: SIMD2<Double> = SIMD2(1, 1)) throws {
        let file = try Wire.decoder.decode(File.self, from: json)
        let (w, h) = (file.matMm[0], file.matMm[1])
        dictionary = file.dictionary
        markerMm = file.markerMm
        matMm = SIMD2(w, h)
        self.printScale = printScale
        // Layout frame (origin top-left, y down) -> mat frame (origin center, y up).
        func toMat(_ p: [Double]) -> SIMD2<Double> {
            SIMD2((p[0] - w / 2) * printScale.x, (h / 2 - p[1]) * printScale.y)
        }
        var corners: [Int: [SIMD2<Double>]] = [:]
        for m in file.markers { corners[m.id] = m.corners.map(toMat) }
        self.corners = corners
    }

    public var markerIds: [Int] { corners.keys.sorted() }

    /// The mat's outline in the mat frame, for drawing.
    public var outline: [SIMD3<Double>] {
        let (x, y) = (matMm.x / 2 * printScale.x, matMm.y / 2 * printScale.y)
        return [SIMD3(-x, y, 0), SIMD3(x, y, 0), SIMD3(x, -y, 0), SIMD3(-x, -y, 0)]
    }
}
