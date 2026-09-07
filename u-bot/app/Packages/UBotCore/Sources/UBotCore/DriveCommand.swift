import Foundation

/// A drive command as the robot's `7B1A0001` characteristic wants it.
///
/// Both components are a fraction of the robot's *current* limits, not physical
/// units. With the default settings that is about 0.675 m/s and 5.14 rad/s, but
/// the app never needs to know: the status frame reports the command actually in
/// force in real units, which is what the readout shows.
public struct DriveCommand: Equatable, Sendable {

    public static let zero = DriveCommand(v: 0, w: 0)

    /// Forward, -1...1. Positive drives the robot forwards.
    public let v: Double

    /// Turn, -1...1. Positive is anticlockwise seen from above, i.e. a left
    /// turn -- matching `wheelTpsFor()` in drive.cpp.
    public let w: Double

    public init(v: Double, w: Double) {
        self.v = min(max(v, -1), 1)
        self.w = min(max(w, -1), 1)
    }

    /// Build from a stick offset measured from the pad centre, normalised so
    /// the pad radius is 1 and +y points DOWN -- which is what both a browser
    /// pointer event and a SwiftUI `DragGesture` give you.
    ///
    /// Clamped to the unit disc, then `v = -y` and `w = -x`, exactly as
    /// `joystick.html` does it. Keeping the negation here, in one place, is
    /// what stops it being re-derived (and re-inverted) in each control surface.
    public init(stickX x: Double, stickY y: Double) {
        var x = x, y = y
        let d = (x * x + y * y).squareRoot()
        if d > 1 { x /= d; y /= d }
        self.init(v: -y, w: -x)
    }

    /// `int16 v, int16 w`, little-endian, thousandths. Exactly 4 bytes -- the
    /// firmware returns `BLE_ATT_ERR_INVALID_ATTR_VALUE_LEN` for any other
    /// length.
    public var frame: Data {
        let vi = Int16(clamping: Int((v * 1000).rounded()))
        let wi = Int16(clamping: Int((w * 1000).rounded()))
        return Data([
            UInt8(truncatingIfNeeded: vi), UInt8(truncatingIfNeeded: vi >> 8),
            UInt8(truncatingIfNeeded: wi), UInt8(truncatingIfNeeded: wi >> 8),
        ])
    }

    public var isZero: Bool { v == 0 && w == 0 }

    /// Distance from centre, 0...1. Useful for the knob and for haptics.
    public var magnitude: Double { min(1, (v * v + w * w).squareRoot()) }
}
