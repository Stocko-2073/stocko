import SwiftUI

/// Hold for extra motor current.
///
/// It sits at the pad's bottom-left corner, mirroring Clear on the right, so
/// one thumb can hold it while the other drives. Its gesture is its own, not
/// part of the pad's, which is what lets both be held at once.
///
/// Unavailable is greyed but still takes a touch, which toasts why -- the same
/// contract as the locked pad.
struct BoostButton: View {

    let model: BoostButtonModel

    /// True while a touch is down; resets by itself when the touch ends *or
    /// is cancelled*. A cancelled `DragGesture` never calls `onEnded`, and a
    /// Boost that outlived its finger would keep the robot at boost current
    /// with nobody asking. This reset is the backstop for that.
    @GestureState private var touching = false

    var body: some View {
        let available = model.blockReason == nil
        VStack(spacing: 3) {
            Image(systemName: "bolt.fill")
                .font(.system(size: 22, weight: .bold))
            Text("Boost")
                .font(.system(size: 11, weight: .semibold))
        }
        .foregroundStyle(foreground(available: available))
        .frame(width: 64, height: 64)
        .background(fill(available: available), in: Circle())
        .overlay(Circle().strokeBorder(.white.opacity(model.isHeld ? 0.9 : 0.25),
                                       lineWidth: model.isHeld ? 2 : 1))
        .shadow(color: .black.opacity(0.35), radius: 4, y: 2)
        .scaleEffect(model.isHeld ? 0.94 : 1)
        .animation(.easeOut(duration: 0.12), value: model.isHeld)
        .opacity(available || model.isHeld ? 1 : 0.55)
        .contentShape(Circle())         // greyed still takes the touch, to explain itself
        .gesture(
            // Zero distance, like the stick: the hold starts on touch-down.
            DragGesture(minimumDistance: 0, coordinateSpace: .local)
                .updating($touching) { _, touching, _ in touching = true }
                .onChanged { _ in model.press() }       // repeats in one touch are ignored
                .onEnded { _ in model.release() }
        )
        .onChange(of: touching) { _, down in
            if !down { model.release() }
        }
        .sensoryFeedback(.impact(weight: .medium), trigger: model.isHeld)
        .sensoryFeedback(.warning, trigger: model.refusals)
        .accessibilityElement(children: .ignore)
        .accessibilityLabel("Boost")
        .accessibilityValue(model.isHeld ? "Held" : available ? "Released" : "Unavailable")
        .accessibilityHint(model.blockReason ?? "Hold for extra motor torque. Let go to end it.")
        .accessibilityAddTraits(.isButton)
        .accessibilityIdentifier("boost")
    }

    /// Blue when it can be held, amber while held -- extra current is worth
    /// seeing at a glance, on camera too -- and card grey when it cannot.
    private func fill(available: Bool) -> Color {
        if model.isHeld { return UBotPalette.warn }
        return available ? UBotPalette.act : UBotPalette.card
    }

    private func foreground(available: Bool) -> Color {
        if model.isHeld { return UBotPalette.bg }
        return available ? .white : UBotPalette.mute
    }
}
