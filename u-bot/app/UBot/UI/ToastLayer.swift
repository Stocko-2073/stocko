import SwiftUI

/// Transient messages: a refused control op, the reason a locked pad would not
/// move. Ported from `#toast`.
struct ToastLayer: View {
    let toast: RobotController.Toast?

    var body: some View {
        if let toast {
            Text(toast.text)
                .font(.system(size: 14))
                .foregroundStyle(UBotPalette.fg)
                .multilineTextAlignment(.center)
                .padding(.horizontal, 14)
                .padding(.vertical, 10)
                .background(Color(hex: 0x2A2E38), in: RoundedRectangle(cornerRadius: 10))
                .overlay(RoundedRectangle(cornerRadius: 10).stroke(border, lineWidth: 1))
                .shadow(color: .black.opacity(0.6), radius: 12, y: 4)
                .padding(.horizontal, 24)
                .transition(.move(edge: .top).combined(with: .opacity))
                .id(toast.id)
        }
    }

    private var border: Color {
        guard let kind = toast?.kind else { return UBotPalette.line }
        switch kind {
        case .bad:     return UBotPalette.bad
        case .warning: return UBotPalette.warn
        case .info:    return UBotPalette.line
        }
    }
}
