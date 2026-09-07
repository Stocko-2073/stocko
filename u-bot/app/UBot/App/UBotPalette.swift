import SwiftUI

/// The colours from `firmware/base/components/net/joystick.html`, so the phone
/// app and the robot's own web page read as one product.
enum UBotPalette {
    static let bg   = Color(hex: 0x0E1013)
    static let card = Color(hex: 0x171A20)
    static let line = Color(hex: 0x282D38)
    static let fg   = Color(hex: 0xE8EAEF)
    static let mute = Color(hex: 0x8E95A3)
    static let ok   = Color(hex: 0x2FB56D)
    static let warn = Color(hex: 0xE0A52C)
    static let bad  = Color(hex: 0xE04A44)
    static let act  = Color(hex: 0x4F8FF0)

    /// Everything sitting over the camera needs its own backing, or it
    /// disappears against a bright lawn. Ends up in the recording, so it is
    /// styled as intentional HUD rather than debug chrome.
    static let overlay = Color.black.opacity(0.55)
}

extension Color {
    init(hex: UInt32) {
        self.init(.sRGB,
                  red:   Double((hex >> 16) & 0xFF) / 255,
                  green: Double((hex >> 8) & 0xFF) / 255,
                  blue:  Double(hex & 0xFF) / 255,
                  opacity: 1)
    }
}

extension Text {
    /// Tabular figures everywhere a number changes at 5 Hz, so the HUD does not
    /// jitter while you are filming it.
    func telemetryDigits() -> Text { monospacedDigit() }
}
