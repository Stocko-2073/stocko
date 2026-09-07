import AVFoundation
import Foundation
import os

/// Owns the capture session.
///
/// Preview only: no `AVAssetWriter`, no `AVCaptureMovieFileOutput`, no video
/// data output. ReplayKit records the screen, so all this has to do is put live
/// pixels behind the HUD. That is the whole reason the recording path is as
/// small as it is.
@MainActor
@Observable
final class CameraSession {

    let session = AVCaptureSession()

    private(set) var isAuthorized = false
    private(set) var isRunning = false
    /// Set when the system takes the camera away -- a call, thermal shutdown,
    /// another app. Outdoors this is a real event, so it belongs on screen.
    private(set) var interruption: String?

    /// `startRunning()` and `stopRunning()` block. They must never touch the
    /// main thread or the joystick stutters every time the session changes
    /// state.
    private let queue = DispatchQueue(label: "com.stocko.ubot.camera")
    private let log = Logger(subsystem: "com.stocko.ubot", category: "camera")
    private var isConfigured = false

    init() { observeInterruptions() }

    @discardableResult
    func start() async -> Bool {
        let granted: Bool
        switch AVCaptureDevice.authorizationStatus(for: .video) {
        case .authorized:    granted = true
        case .notDetermined: granted = await AVCaptureDevice.requestAccess(for: .video)
        default:             granted = false
        }
        isAuthorized = granted
        guard granted else { return false }

        await withCheckedContinuation { (c: CheckedContinuation<Void, Never>) in
            queue.async { [self] in
                if !isConfigured { configure(); isConfigured = true }
                if !session.isRunning { session.startRunning() }
                c.resume()
            }
        }
        isRunning = session.isRunning
        return true
    }

    func stop() {
        queue.async { [self] in
            if session.isRunning { session.stopRunning() }
        }
        isRunning = false
    }

    private func configure() {
        session.beginConfiguration()
        defer { session.commitConfiguration() }

        // Preview-only, so this only affects how sharp the preview looks when
        // ReplayKit re-captures it off the screen. 1080p is plenty and runs
        // cooler than 4K, which matters in the sun with the radio up.
        session.sessionPreset = .hd1920x1080

        guard let device = AVCaptureDevice.default(.builtInWideAngleCamera,
                                                   for: .video, position: .back),
              let input = try? AVCaptureDeviceInput(device: device),
              session.canAddInput(input)
        else {
            log.error("no back camera available")
            return
        }
        session.addInput(input)

        // Deliberately no audio input. ReplayKit owns the microphone when the
        // operator switches it on; adding an AVCaptureDeviceInput for audio
        // here starts an audio-session fight over the same hardware.

        do {
            try device.lockForConfiguration()
            if device.isFocusModeSupported(.continuousAutoFocus) {
                device.focusMode = .continuousAutoFocus
            }
            if device.isExposureModeSupported(.continuousAutoExposure) {
                device.exposureMode = .continuousAutoExposure
            }
            device.unlockForConfiguration()
        } catch {
            log.error("camera configuration: \(error.localizedDescription, privacy: .public)")
        }
    }

    private func observeInterruptions() {
        let c = NotificationCenter.default
        c.addObserver(forName: .AVCaptureSessionWasInterrupted,
                      object: session, queue: .main) { [weak self] note in
            let reason = (note.userInfo?[AVCaptureSessionInterruptionReasonKey] as? Int)
                .flatMap(AVCaptureSession.InterruptionReason.init(rawValue:))
            self?.interruption = Self.describe(reason)
        }
        c.addObserver(forName: .AVCaptureSessionInterruptionEnded,
                      object: session, queue: .main) { [weak self] _ in
            self?.interruption = nil
        }
        c.addObserver(forName: .AVCaptureSessionRuntimeError,
                      object: session, queue: .main) { [weak self] _ in
            self?.interruption = "The camera stopped unexpectedly."
        }
    }

    private static func describe(_ reason: AVCaptureSession.InterruptionReason?) -> String {
        switch reason {
        case .videoDeviceNotAvailableInBackground: return "Camera paused in the background."
        case .videoDeviceNotAvailableDueToSystemPressure: return "Camera paused: the phone is too hot."
        case .videoDeviceInUseByAnotherClient: return "Another app is using the camera."
        case .audioDeviceInUseByAnotherClient: return "Another app is using the microphone."
        default: return "The camera was interrupted."
        }
    }
}
