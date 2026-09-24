import Foundation
import simd

/// The printed marker page (work/marker_border.py) in the page frame.
public struct BoardLayout: Sendable {
    public let dictionary: String
    public let markerMm: Double
    public let pageMm: SIMD2<Double>
    public let printScale: SIMD2<Double>
    /// id -> corners TL, TR, BR, BL as printed, page-frame mm on z = 0.
    public let corners: [Int: [SIMD2<Double>]]

    public static let layoutFiles = [
        "DICT_4X4_100": "border_letter_aruco_4x4_10mm",
        "DICT_APRILTAG_36h11": "border_letter_apriltag_36h11_10mm",
    ]

    struct File: Decodable {
        struct Marker: Decodable {
            let id: Int
            let corners: [[Double]]
        }
        let dictionary: String
        let markerMm: Double
        let pageMm: [Double]
        let markers: [Marker]
    }

    /// The bundled layout for a dictionary, scaled by the measured print scale.
    public static func bundled(_ info: BoardInfo = BoardInfo()) throws -> BoardLayout {
        guard let name = layoutFiles[info.dictionary],
              let url = Bundle.module.url(forResource: name, withExtension: "json", subdirectory: "boards")
        else { throw CocoaError(.fileNoSuchFile) }
        let scale = info.printScale.count == 2 ? SIMD2(info.printScale[0], info.printScale[1]) : SIMD2(1, 1)
        return try BoardLayout(json: Data(contentsOf: url), printScale: scale)
    }

    public init(json: Data, printScale: SIMD2<Double> = SIMD2(1, 1)) throws {
        let file = try Wire.decoder.decode(File.self, from: json)
        let (w, h) = (file.pageMm[0], file.pageMm[1])
        dictionary = file.dictionary
        markerMm = file.markerMm
        pageMm = SIMD2(w, h)
        self.printScale = printScale
        // Layout frame (origin top-left, y down) -> page frame (origin centre, y up).
        func toPage(_ p: [Double]) -> SIMD2<Double> {
            SIMD2((p[0] - w / 2) * printScale.x, (h / 2 - p[1]) * printScale.y)
        }
        var corners: [Int: [SIMD2<Double>]] = [:]
        for m in file.markers { corners[m.id] = m.corners.map(toPage) }
        self.corners = corners
    }

    public var markerIds: [Int] { corners.keys.sorted() }

    /// The page's outline in the page frame, for drawing.
    public var outline: [SIMD3<Double>] {
        let (x, y) = (pageMm.x / 2 * printScale.x, pageMm.y / 2 * printScale.y)
        return [SIMD3(-x, y, 0), SIMD3(x, y, 0), SIMD3(x, -y, 0), SIMD3(-x, -y, 0)]
    }
}
