import AgentCamCore
import ARKit
import AVFoundation
import UIKit

/// What this phone can do, for the server's hello (and so the agent's
/// preflight checks use this phone's real lenses).
enum DeviceInfo {
    static var model: String {
        var info = utsname()
        uname(&info)
        return withUnsafeBytes(of: info.machine) { String(decoding: $0.prefix { $0 != 0 }, as: UTF8.self) }
    }

    static var appVersion: String { Bundle.main.object(forInfoDictionaryKey: "CFBundleShortVersionString") as? String ?? "?" }

    static let lensTypes: [(CaptureOptions.Lens, AVCaptureDevice.DeviceType)] = [
        (.wide, .builtInWideAngleCamera), (.ultrawide, .builtInUltraWideCamera), (.telephoto, .builtInTelephotoCamera),
    ]

    static func device(for lens: CaptureOptions.Lens) -> AVCaptureDevice? {
        guard let type = lensTypes.first(where: { $0.0 == lens })?.1 else { return nil }
        return AVCaptureDevice.default(type, for: .video, position: .back)
    }

    static let lenses: [LensInfo] = lensTypes.compactMap { lens, _ in
        guard let d = device(for: lens) else { return nil }
        let format = d.activeFormat
        let dims = CMVideoFormatDescriptionGetDimensions(format.formatDescription)
        let h = Double(format.videoFieldOfView)
        // The format's FOV is horizontal (the sensor's long side).
        let v = 2 * atan(tan(h / 2 * .pi / 180) * Double(dims.height) / Double(max(dims.width, 1))) * 180 / .pi
        return LensInfo(id: lens, fovDeg: [h, v], minFocusMm: d.minimumFocusDistance > 0 ? Double(d.minimumFocusDistance) : nil,
                        maxPhotoDims: format.supportedMaxPhotoDimensions.map { [Int($0.width), Int($0.height)] },
                        raw: nil, flash: d.hasFlash)
    }

    static var lidar: Bool { ARWorldTrackingConfiguration.supportsFrameSemantics(.sceneDepth) }

    static func hello(appState: String) -> Hello {
        Hello(appState: appState, device: .init(model: model, ios: UIDevice.current.systemVersion, app: appVersion),
              lenses: lenses, lidar: lidar)
    }
}
