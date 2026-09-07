import SwiftUI
import UBotCore

/// The circular pad, ported from `#pad` in joystick.html.
///
/// Geometry matches the web page so the two feel identical: the knob is 26% of
/// the pad and travels 37% of the pad's width, which puts its edge exactly on
/// the rim at full deflection.
struct JoystickPad: View {

    let model: ControlSurfaceModel

    private let knobFraction: CGFloat = 0.26
    private let travelFraction: CGFloat = 0.37

    /// Tuning lives here. The knob follows the shaped command rather than the
    /// finger, so what you see on the pad is what the robot was told.
    private let response = StickResponse.standard

    var body: some View {
        GeometryReader { geo in
            let size = min(geo.size.width, geo.size.height)
            let radius = size / 2
            let knob = size * knobFraction
            let travel = size * travelFraction

            // The knob shows the clamped command, not the raw finger position,
            // so it can never leave the rim.
            let offset = CGSize(width: -model.command.w * travel,
                                height: -model.command.v * travel)

            ZStack {
                Circle()
                    .fill(RadialGradient(colors: [Color(hex: 0x1D2129), Color(hex: 0x13161B)],
                                         center: .center, startRadius: 0, endRadius: radius))
                    .overlay(Circle().strokeBorder(UBotPalette.line, lineWidth: 2))

                // The crosshair from the web pad: it makes "straight forward"
                // findable without looking down.
                Path { p in
                    p.move(to: CGPoint(x: radius, y: size * 0.08))
                    p.addLine(to: CGPoint(x: radius, y: size * 0.92))
                    p.move(to: CGPoint(x: size * 0.08, y: radius))
                    p.addLine(to: CGPoint(x: size * 0.92, y: radius))
                }
                .stroke(UBotPalette.line, lineWidth: 1)

                Circle()
                    .fill(model.isEngaged ? UBotPalette.ok : UBotPalette.mute)
                    .frame(width: knob, height: knob)
                    .shadow(color: .black.opacity(0.5), radius: 4, y: 2)
                    .offset(offset)
                    .animation(model.isEngaged ? nil : .spring(duration: 0.25),
                               value: model.command)
            }
            .frame(width: size, height: size)
            .frame(maxWidth: .infinity, maxHeight: .infinity)
            // Always translucent, locked or not. The pad is over live camera
            // and ends up in every clip, so it stays out of the way; the lock
            // is carried by the state card and by the toast a locked pad
            // raises when you tap it, which is what the tap target below is
            // for.
            .opacity(0.4)
            .contentShape(Circle())      // a locked pad still takes the tap, to explain itself
            .gesture(
                DragGesture(minimumDistance: 0, coordinateSpace: .local)
                    .onChanged { value in
                        // Normalise to the unit disc: +y is down, matching both
                        // a browser pointer event and DragGesture. The curve
                        // that makes the centre usable lives in StickResponse,
                        // and the negation to (v, w) in DriveCommand -- each in
                        // one place.
                        let s = response.shape(
                            x: (value.location.x - radius) / radius,
                            y: (value.location.y - radius) / radius)
                        let c = DriveCommand(stickX: s.x, stickY: s.y)
                        model.isEngaged ? model.update(c) : model.engage(c)
                    }
                    .onEnded { _ in model.release() }
            )
            .sensoryFeedback(.impact(weight: .light), trigger: model.isEngaged)
        }
        .aspectRatio(1, contentMode: .fit)
    }
}
