import SwiftUI
import UBotCore

/// The strip along the top. Everything here ends up in the recording, so it is
/// styled as deliberate on-camera HUD rather than developer chrome.
struct TopHUD: View {
    let controller: RobotController
    let recorder: ScreenRecorder
    let thermal: ProcessInfo.ThermalState

    var body: some View {
        HStack(spacing: 8) {
            pill
            Spacer(minLength: 4)
            if thermal == .serious || thermal == .critical {
                chip(thermal == .critical ? "Too hot" : "Warm",
                     tone: thermal == .critical ? UBotPalette.bad : UBotPalette.warn)
            }
            if controller.linkCongested {
                chip("Link busy", tone: UBotPalette.warn)
            }
            recordingIndicator
        }
        .font(.system(size: 13, weight: .medium))
        .padding(.horizontal, 12)
        .padding(.vertical, 8)
        .background(UBotPalette.overlay, in: Capsule())
        .padding(.horizontal, 12)
    }

    private var pill: some View {
        HStack(spacing: 7) {
            Circle()
                .fill(dotColor)
                .frame(width: 9, height: 9)
            Text(controller.linkState.robotName ?? controller.linkState.summary)
                .foregroundStyle(UBotPalette.fg)
            Text(controller.batteryText)
                .telemetryDigits()
                .foregroundStyle(controller.batteryTone)
            if let fw = controller.firmware {
                Text("fw \(fw)").foregroundStyle(UBotPalette.mute)
            }
        }
    }

    private var dotColor: Color {
        switch controller.linkState {
        case .ready:                        return UBotPalette.ok
        case .stalled, .scanning,
             .connecting, .discovering:     return UBotPalette.warn
        default:                            return UBotPalette.bad
        }
    }

    private func chip(_ text: String, tone: Color) -> some View {
        Text(text)
            .font(.system(size: 12, weight: .semibold))
            .foregroundStyle(tone)
            .padding(.horizontal, 8)
            .padding(.vertical, 3)
            .overlay(Capsule().stroke(tone, lineWidth: 1))
    }

    @ViewBuilder
    private var recordingIndicator: some View {
        if case .recording(let since) = recorder.state {
            HStack(spacing: 5) {
                Circle().fill(UBotPalette.bad).frame(width: 9, height: 9)
                TimelineView(.periodic(from: since, by: 1)) { context in
                    Text(Self.elapsed(from: since, to: context.date))
                        .telemetryDigits()
                        .foregroundStyle(UBotPalette.fg)
                }
            }
        }
    }

    private static func elapsed(from start: Date, to now: Date) -> String {
        let s = max(0, Int(now.timeIntervalSince(start)))
        return String(format: "%d:%02d", s / 60, s % 60)
    }
}
