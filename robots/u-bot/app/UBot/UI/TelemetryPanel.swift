import SwiftUI
import UBotCore

/// The full telemetry read-out, shown at all times because it ends up in the
/// recording and gives a build-log audience something to read.
///
/// Commanded and measured sit side by side on purpose. A refused drive still
/// returns success over BLE, so the app must never present the operator's
/// *intent* as the truth -- "asked for 0.20 m/s, wheels at 0.00 turns/s" is the
/// read-out that catches a stall, a disabled driver or a silently dropped write.
struct TelemetryPanel: View {
    let status: UBotStatus?

    var body: some View {
        HStack(alignment: .top, spacing: 0) {
            column(title: "COMMANDED") {
                row("v", value(status?.commandedMetersPerSec, "m/s"))
                row("w", value(status?.commandedRadiansPerSec, "rad/s"))
            }

            Rectangle()
                .fill(UBotPalette.line)
                .frame(width: 1)
                .padding(.vertical, 2)

            column(title: "MEASURED") {
                row("A", wheel(status?.wheelATurnsPerSec), tone: encoderTone(\.encoderAOK))
                row("B", wheel(status?.wheelBTurnsPerSec), tone: encoderTone(\.encoderBOK))
            }
        }
        .font(.system(size: 12))
        .padding(.horizontal, 14)
        .padding(.vertical, 9)
        .background(UBotPalette.overlay, in: RoundedRectangle(cornerRadius: 10))
        .padding(.horizontal, 12)
    }

    private func column<Content: View>(title: String,
                                       @ViewBuilder content: () -> Content) -> some View {
        VStack(alignment: .leading, spacing: 3) {
            Text(title)
                .font(.system(size: 10, weight: .semibold))
                .foregroundStyle(UBotPalette.mute)
                .tracking(0.6)
            content()
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(.horizontal, 10)
    }

    private func row(_ label: String, _ text: String,
                     tone: Color = UBotPalette.fg) -> some View {
        HStack(spacing: 6) {
            Text(label)
                .foregroundStyle(UBotPalette.mute)
                .frame(width: 12, alignment: .leading)
            Text(text)
                .telemetryDigits()
                .foregroundStyle(tone)
        }
    }

    private func value(_ v: Double?, _ unit: String) -> String {
        guard let v else { return "\u{2014}" }
        return String(format: "%.2f %@", v, unit)
    }

    private func wheel(_ v: Double?) -> String {
        guard let v else { return "\u{2014}" }
        return String(format: "%.2f turns/s", v)
    }

    /// An encoder that stopped answering is worth colouring: on this build the
    /// magnets read at maximum AGC and wheel B trips MAGNET_LOW, so this is a
    /// state that genuinely shows up on the bench.
    private func encoderTone(_ key: KeyPath<UBotStatus, Bool>) -> Color {
        guard let status else { return UBotPalette.mute }
        return status[keyPath: key] ? UBotPalette.fg : UBotPalette.bad
    }
}
