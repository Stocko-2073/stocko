import Foundation
import Observation
import Photos
import ReplayKit
import SwiftUI
import os

/// ReplayKit in-app screen capture.
///
/// It films the whole screen, so the joystick, the telemetry and the camera
/// feed are burned into the clip with no compositing work at all -- which is
/// why the camera side of this app is preview-only.
///
/// Two properties to design around, both inherent to ReplayKit rather than
/// bugs: recording stops when the app backgrounds or the screen locks, and the
/// capture is at screen resolution rather than sensor resolution. For clips
/// destined for social, both are fine.
@MainActor
@Observable
final class ScreenRecorder: NSObject {

    enum State: Equatable {
        case idle
        case starting
        case recording(since: Date)
        case saving
        case failed(String)
        /// Photos said no, but the file exists. Offer a share sheet rather than
        /// throwing the take away.
        case savedNeedsShare(URL)
    }

    private(set) var state: State = .idle
    /// Handed over when the system stops a recording itself. Presenting it is
    /// what stops a phone call eating the take.
    private(set) var pendingPreview: RPPreviewViewController?

    var microphoneEnabled = false

    private let recorder = RPScreenRecorder.shared()
    private let log = Logger(subsystem: "com.stocko.ubot", category: "record")

    override init() {
        super.init()
        recorder.delegate = self
    }

    var isAvailable: Bool { recorder.isAvailable }

    var isRecording: Bool {
        if case .recording = state { return true }
        return false
    }

    func start() async {
        guard case .idle = state else { return }
        guard recorder.isAvailable else {
            // False during a call, while AirPlay or mirroring is active, while
            // another app is recording, and unreliably in the Simulator.
            state = .failed("Screen recording is not available right now.")
            return
        }
        state = .starting
        recorder.isMicrophoneEnabled = microphoneEnabled
        recorder.isCameraEnabled = false     // ReplayKit's own front-camera PiP, not ours

        do {
            try await withCheckedThrowingContinuation { (c: CheckedThrowingContinuation) in
                // The first call raises the system "would like to record your
                // screen" alert. That alert is not itself recorded -- capture
                // has not started when it appears.
                recorder.startRecording { error in
                    if let error { c.resume(throwing: error) } else { c.resume() }
                }
            }
            state = .recording(since: Date())
            log.notice("recording started")
        } catch {
            state = .failed(Self.describe(error))
        }
    }

    func stopAndSave() async {
        guard case .recording = state else { return }
        state = .saving

        let url = FileManager.default.temporaryDirectory
            .appendingPathComponent("ubot-\(Self.stamp()).mp4")
        // ReplayKit refuses to write to a path that already exists.
        try? FileManager.default.removeItem(at: url)

        do {
            try await recorder.stopRecording(withOutput: url)
            try await saveToPhotos(url)
            try? FileManager.default.removeItem(at: url)
            state = .idle
            log.notice("recording saved to Photos")
        } catch let denied as PhotosDenied {
            state = .savedNeedsShare(denied.url)
        } catch {
            state = .failed(Self.describe(error))
        }
    }

    func dismissMessage() {
        if case .failed = state { state = .idle }
        if case .savedNeedsShare = state { state = .idle }
    }

    func clearPendingPreview() { pendingPreview = nil }

    // MARK: Photos

    private struct PhotosDenied: Error { let url: URL }

    private func saveToPhotos(_ url: URL) async throws {
        // .addOnly, so the app never asks to read the user's library.
        let auth = await PHPhotoLibrary.requestAuthorization(for: .addOnly)
        guard auth == .authorized || auth == .limited else { throw PhotosDenied(url: url) }
        try await PHPhotoLibrary.shared().performChanges {
            PHAssetChangeRequest.creationRequestForAssetFromVideo(atFileURL: url)
        }
    }

    private typealias CheckedThrowingContinuation = CheckedContinuation<Void, Error>

    private static func stamp() -> String {
        let f = DateFormatter()
        f.dateFormat = "yyyyMMdd-HHmmss"
        return f.string(from: Date())
    }

    private static func describe(_ error: Error) -> String {
        let ns = error as NSError
        guard ns.domain == RPRecordingErrorDomain,
              let code = RPRecordingErrorCode(rawValue: ns.code)
        else { return ns.localizedDescription }

        switch code {
        case .userDeclined:
            return "Screen recording was not allowed."
        case .disabled:
            return "Screen recording is switched off in Screen Time \u{203A} Content & Privacy."
        case .failedToStart:
            return "Screen recording could not start. Try again."
        case .insufficientStorage:
            return "Not enough free space to record."
        default:
            return ns.localizedDescription
        }
    }
}

extension ScreenRecorder: RPScreenRecorderDelegate {

    /// The system pulled the plug: a phone call, the app backgrounding, the
    /// screen locking, AirPlay starting. Whatever was captured up to that
    /// moment arrives in `previewViewController`.
    nonisolated func screenRecorder(_ recorder: RPScreenRecorder,
                                    didStopRecordingWith previewViewController: RPPreviewViewController?,
                                    error: Error?) {
        Task { @MainActor [weak self] in
            guard let self else { return }
            self.pendingPreview = previewViewController
            self.state = .failed(error.map(Self.describe) ?? "Recording stopped.")
        }
    }
}

/// Presents the `RPPreviewViewController` ReplayKit hands back after a
/// system-initiated stop, so the partial clip can still be saved or shared.
struct RecordingPreview: UIViewControllerRepresentable {
    let controller: RPPreviewViewController
    let onFinish: () -> Void

    func makeUIViewController(context: Context) -> RPPreviewViewController {
        controller.previewControllerDelegate = context.coordinator
        return controller
    }

    func updateUIViewController(_ vc: RPPreviewViewController, context: Context) {}

    func makeCoordinator() -> Coordinator { Coordinator(onFinish: onFinish) }

    final class Coordinator: NSObject, RPPreviewViewControllerDelegate {
        let onFinish: () -> Void
        init(onFinish: @escaping () -> Void) { self.onFinish = onFinish }

        func previewControllerDidFinish(_ previewController: RPPreviewViewController) {
            onFinish()
        }
    }
}
