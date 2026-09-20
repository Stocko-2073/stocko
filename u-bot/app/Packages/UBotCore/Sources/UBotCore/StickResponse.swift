import Foundation

/// How far the thumb moves versus how hard the robot drives.
///
/// `DriveCommand(stickX:stickY:)` is deliberately linear -- it is the geometry
/// from `joystick.html` and nothing else. Feel lives here instead, so the wire
/// mapping stays something `ubotctl` can assert against and this stays
/// something you can tune in a yard without touching the protocol.
///
/// The standard response is linear with full authority on both axes. Robot
/// speed limits live in the firmware's saved settings; the app does not reduce
/// them again. Custom responses can still opt into curvature or turn scaling.
public struct StickResponse: Sendable, Equatable {

    /// Curvature, 0...1. At 0 the stick is linear. At 1 it is a pure cube, so
    /// half deflection commands an eighth. In between it is the usual RC blend
    /// of the two, which keeps full deflection at exactly full output -- expo
    /// buys resolution near the centre, it never costs you top speed.
    public var expo: Double

    /// Fraction of the robot's turn authority at full deflection. Forward is
    /// never scaled. The standard response uses the full range on both axes.
    public var turnScale: Double

    /// What the pad uses: half travel commands half rate, and full travel
    /// reaches the robot's configured limit in every cardinal direction.
    public static let standard = StickResponse(expo: 0, turnScale: 1)

    /// Linear and unscaled -- the old behaviour, and what a bench script wants
    /// when it means the number it wrote.
    public static let raw = StickResponse(expo: 0, turnScale: 1)

    public init(expo: Double, turnScale: Double) {
        self.expo = min(max(expo, 0), 1)
        self.turnScale = min(max(turnScale, 0), 1)
    }

    /// Shape a stick offset measured from the pad centre, normalised so the pad
    /// radius is 1 and +y points DOWN, into one the same way up.
    ///
    /// Clamped to the unit disc *first*, so the curve is applied to the offset
    /// the operator can actually reach and a drag off the far corner cannot
    /// come back with more authority than the rim.
    public func shape(x: Double, y: Double) -> (x: Double, y: Double) {
        var x = x, y = y
        let d = (x * x + y * y).squareRoot()
        if d > 1 { x /= d; y /= d }
        return (curve(x) * turnScale, curve(y))
    }

    /// Odd, so it never changes a direction, and fixed at -1, 0 and +1.
    private func curve(_ t: Double) -> Double {
        expo * (t * t * t) + (1 - expo) * t
    }
}
