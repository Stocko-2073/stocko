import SwiftUI
import UBotCore

/// One power button that says what pressing it will do, and an E-STOP that is
/// always in the same place. Same contract as the web page.
struct PowerBar: View {
    let controller: RobotController

    private var enabled: Bool { controller.status?.isEnabled ?? false }
    private var connected: Bool { controller.linkState.isReady }

    var body: some View {
        HStack(spacing: 10) {
            Button {
                controller.send(enabled ? .disable : .enable)
            } label: {
                Text(enabled ? "Disable motors" : "Enable motors")
                    .font(.system(size: 15, weight: .semibold))
                    .frame(maxWidth: .infinity)
                    .padding(.vertical, 13)
                    .background(enabled ? UBotPalette.card : UBotPalette.act,
                                in: RoundedRectangle(cornerRadius: 10))
                    .overlay(RoundedRectangle(cornerRadius: 10)
                        .stroke(enabled ? UBotPalette.line : UBotPalette.act, lineWidth: 1))
                    .foregroundStyle(UBotPalette.fg)
            }
            .buttonStyle(.plain)
            .disabled(!connected)
            .opacity(connected ? 1 : 0.4)

            Button {
                controller.send(.estop)
            } label: {
                Text("E-STOP")
                    .font(.system(size: 17, weight: .heavy))
                    .tracking(1.2)
                    .frame(maxWidth: .infinity)
                    .padding(.vertical, 13)
                    .background(UBotPalette.bad, in: RoundedRectangle(cornerRadius: 10))
                    .foregroundStyle(.white)
            }
            .buttonStyle(.plain)
            // E-STOP is never locked for any robot-side reason -- only when
            // there is no link to carry it. Same rule as joystick.html.
            .disabled(!connected)
            .opacity(connected ? 1 : 0.4)
        }
        .padding(.horizontal, 12)
    }
}
