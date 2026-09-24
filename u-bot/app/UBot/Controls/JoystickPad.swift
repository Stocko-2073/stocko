import SwiftUI
import UBotCore

/// The circular pad, ported from `#pad` in joystick.html.
///
/// The knob is 26% of the pad and travels 37% of its width, placing its edge
/// on the rim at full deflection. Input uses that same travel distance so the
/// knob follows the finger until it reaches the rim.
struct JoystickPad: View {

    let model: ControlSurfaceModel

    private let knobFraction: CGFloat = 0.26
    private let travelFraction: CGFloat = 0.37

    var body: some View {
        GeometryReader { geo in
            let size = min(geo.size.width, geo.size.height)
            let radius = size / 2
            let knob = size * knobFraction
            let travel = size * travelFraction

            // Draw from physical input; the transmitted command has a softer centre.
            let offset = CGSize(width: -model.stickPosition.w * travel,
                                height: -model.stickPosition.v * travel)

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
                               value: model.stickPosition)
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
                        // Normalise by knob travel so full output is reached
                        // where the knob touches the rim. +y points down;
                        // DriveCommand maps the signs to forward and turn.
                        let c = DriveCommand(
                            stickX: (value.location.x - radius) / travel,
                            stickY: (value.location.y - radius) / travel)
                        model.isEngaged ? model.update(c) : model.engage(c)
                    }
                    .onEnded { _ in model.release() }
            )
            .sensoryFeedback(.impact(weight: .light), trigger: model.isEngaged)
        }
        .aspectRatio(1, contentMode: .fit)
    }
}
