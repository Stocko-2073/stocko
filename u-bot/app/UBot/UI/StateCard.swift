import SwiftUI
import UBotCore

/// One line saying what the robot is doing, with the single action that makes
/// sense right now. Ported from the `#state` card in joystick.html.
struct StateCardView: View {
    let card: RobotController.StateCard
    let onAction: (ControlOp) -> Void

    var body: some View {
        HStack(alignment: .top, spacing: 10) {
            VStack(alignment: .leading, spacing: 3) {
                Text(card.title)
                    .font(.system(size: 15, weight: .semibold))
                    .foregroundStyle(UBotPalette.fg)
                if !card.detail.isEmpty {
                    Text(card.detail)
                        .font(.system(size: 12))
                        .foregroundStyle(UBotPalette.mute)
                        .fixedSize(horizontal: false, vertical: true)
                }
            }
            Spacer(minLength: 0)
            if let action = card.action {
                Button(action.label) { onAction(action.op) }
                    .font(.system(size: 13, weight: .semibold))
                    .buttonStyle(.plain)
                    .foregroundStyle(UBotPalette.fg)
                    .padding(.horizontal, 12)
                    .padding(.vertical, 7)
                    .background(UBotPalette.card, in: RoundedRectangle(cornerRadius: 8))
                    .overlay(RoundedRectangle(cornerRadius: 8)
                        .stroke(UBotPalette.line, lineWidth: 1))
            }
        }
        .padding(12)
        .background(UBotPalette.overlay, in: RoundedRectangle(cornerRadius: 10))
        .overlay(alignment: .leading) {
            // The web card carries its tone as a 4px left border. Same idea.
            RoundedRectangle(cornerRadius: 2)
                .fill(tone)
                .frame(width: 4)
                .padding(.vertical, 6)
                .padding(.leading, 2)
        }
        .padding(.horizontal, 12)
    }

    private var tone: Color {
        switch card.tone {
        case .ok:      return UBotPalette.ok
        case .warn:    return UBotPalette.warn
        case .bad:     return UBotPalette.bad
        case .neutral: return UBotPalette.mute
        }
    }
}
