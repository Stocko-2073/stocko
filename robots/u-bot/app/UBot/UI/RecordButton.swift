import SwiftUI

/// The record control. It is inside the frame it records, so it is small,
/// parked out of thumb reach, and shaped like something that belongs on a
/// camera.
struct RecordButton: View {
    let recorder: ScreenRecorder
    let onTap: () -> Void

    var body: some View {
        Button(action: onTap) {
            ZStack {
                Circle()
                    .stroke(.white.opacity(0.9), lineWidth: 3)
                    .frame(width: 46, height: 46)

                if recorder.isRecording {
                    RoundedRectangle(cornerRadius: 4)
                        .fill(UBotPalette.bad)
                        .frame(width: 19, height: 19)
                } else {
                    Circle()
                        .fill(UBotPalette.bad)
                        .frame(width: 34, height: 34)
                }
            }
            .contentShape(Circle())
        }
        .buttonStyle(.plain)
        .disabled(isBusy)
        .opacity(isBusy ? 0.5 : 1)
        .animation(.easeInOut(duration: 0.15), value: recorder.isRecording)
    }

    private var isBusy: Bool {
        switch recorder.state {
        case .starting, .saving: return true
        default: return false
        }
    }
}
