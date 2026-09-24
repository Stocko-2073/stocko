import AgentCamCore
import ARKit
import AVFoundation

/// Torch, focus, exposure and white balance on the camera ARKit is using
/// (ARConfiguration.configurableCaptureDeviceForPrimaryCamera), so these
/// options work without leaving AR. Apple warns that extreme settings can hurt
/// tracking, so everything returns to automatic between requests.
enum CameraControls {
    static var device: AVCaptureDevice? { ARWorldTrackingConfiguration.configurableCaptureDeviceForPrimaryCamera }

    /// Settings held while guiding to a request: the torch and any custom
    /// exposure or white-balance gains. Locks happen just before the shot.
    static func applyWhileGuiding(_ options: CaptureOptions?) {
        guard let device, (try? device.lockForConfiguration()) != nil else { return }
        defer { device.unlockForConfiguration() }
        let torch = options?.torch ?? 0
        if device.hasTorch {
            if torch > 0 {
                // ARKit turns the torch off if it's set as the session starts; callers
                // reapply this about once a second.
                try? device.setTorchModeOn(level: Float(min(torch, Double(AVCaptureDevice.maxAvailableTorchLevel))))
            } else if device.torchMode != .off {
                device.torchMode = .off
            }
        }
        if let e = options?.exposure, e.mode == .custom, let duration = e.durationS, let iso = e.iso {
            let format = device.activeFormat
            let d = CMTime(seconds: min(max(duration, format.minExposureDuration.seconds), format.maxExposureDuration.seconds),
                           preferredTimescale: 1_000_000)
            device.setExposureModeCustom(duration: d, iso: Float(min(max(iso, Double(format.minISO)), Double(format.maxISO))))
        } else if device.isExposureModeSupported(.continuousAutoExposure) {
            device.exposureMode = .continuousAutoExposure
            device.setExposureTargetBias(Float(options?.exposure.biasEv ?? 0))
        }
        if let wb = options?.whiteBalance, wb.mode == .gains, let g = wb.gains, g.count == 3 {
            let maxGain = device.maxWhiteBalanceGain
            let gains = AVCaptureDevice.WhiteBalanceGains(redGain: min(max(Float(g[0]), 1), maxGain),
                                                          greenGain: min(max(Float(g[1]), 1), maxGain),
                                                          blueGain: min(max(Float(g[2]), 1), maxGain))
            device.setWhiteBalanceModeLocked(with: gains)
        } else if device.isWhiteBalanceModeSupported(.continuousAutoWhiteBalance) {
            device.whiteBalanceMode = .continuousAutoWhiteBalance
        }
        if let f = options?.focus, f.mode == .lensPosition, let p = f.lensPosition,
           device.isLockingFocusWithCustomLensPositionSupported {
            device.setFocusModeLocked(lensPosition: Float(p))
        } else if device.isFocusModeSupported(.continuousAutoFocus) {
            device.focusMode = .continuousAutoFocus
        }
    }

    /// Just before the shot: lock whatever the request asks to be locked where
    /// automatic control has settled.
    static func lockForShot(_ options: CaptureOptions) {
        guard let device, (try? device.lockForConfiguration()) != nil else { return }
        defer { device.unlockForConfiguration() }
        if options.focus.mode == .locked, device.isFocusModeSupported(.locked) { device.focusMode = .locked }
        if options.exposure.mode == .locked, device.isExposureModeSupported(.locked) { device.exposureMode = .locked }
        if options.whiteBalance.mode == .locked, device.isWhiteBalanceModeSupported(.locked) { device.whiteBalanceMode = .locked }
    }

    /// What the camera was doing, for meta.json.
    static func describe(torch: Double) -> (CaptureMetadata.Lens, CaptureMetadata.Exposure) {
        guard let device else { return (CaptureMetadata.Lens(id: .wide), CaptureMetadata.Exposure(torch: torch)) }
        let g = device.deviceWhiteBalanceGains
        let focus: String = switch device.focusMode {
        case .locked: "locked"
        case .autoFocus: "auto"
        case .continuousAutoFocus: "continuous"
        @unknown default: "unknown"
        }
        return (CaptureMetadata.Lens(id: .wide, deviceType: device.deviceType.rawValue, lensPosition: Double(device.lensPosition),
                                     focusMode: focus, distortionCorrection: nil),
                CaptureMetadata.Exposure(durationS: device.exposureDuration.seconds, iso: Double(device.iso),
                                         biasEv: Double(device.exposureTargetBias),
                                         wbGains: [Double(g.redGain), Double(g.greenGain), Double(g.blueGain)],
                                         flashFired: false, torch: device.torchMode == .on ? Double(device.torchLevel) : 0))
    }
}
