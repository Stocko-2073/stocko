import AVFoundation
import SwiftUI

/// A `UIView` whose backing layer *is* the preview layer. No frame observers,
/// no layout code, no `CATransaction` glitching when the safe area changes.
final class CameraPreviewUIView: UIView {
    override class var layerClass: AnyClass { AVCaptureVideoPreviewLayer.self }
    var previewLayer: AVCaptureVideoPreviewLayer { layer as! AVCaptureVideoPreviewLayer }
}

struct CameraPreview: UIViewRepresentable {
    let session: AVCaptureSession

    func makeUIView(context: Context) -> CameraPreviewUIView {
        let view = CameraPreviewUIView()
        view.previewLayer.session = session
        view.previewLayer.videoGravity = .resizeAspectFill   // full-bleed 19.5:9
        view.backgroundColor = .black

        // The app is portrait-locked, so the preview never needs to rotate and
        // 90 degrees is upright for a back camera.
        //
        // This is the iOS 17 API. `videoOrientation` is deprecated and its
        // enum-to-physical mapping is the classic source of sideways previews.
        // If a rotating, horizon-levelled preview is ever wanted, the modern
        // answer is AVCaptureDevice.RotationCoordinator -- not this.
        if let c = view.previewLayer.connection, c.isVideoRotationAngleSupported(90) {
            c.videoRotationAngle = 90
        }
        return view
    }

    func updateUIView(_ view: CameraPreviewUIView, context: Context) {}
}
