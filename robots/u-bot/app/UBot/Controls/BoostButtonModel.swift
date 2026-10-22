import Foundation
import Observation

/// Hold-to-boost, separated from its view the way `ControlSurfaceModel` is
/// from the pad, so the rules can be tested without a touch.
///
/// A hold, never a toggle: Boost is on only while a finger is on the button.
/// One touch is one press. After a forced release -- a lock, a stop, leaving
/// the app -- the finger still on the glass does nothing until it lifts and
/// presses again, so a hold that was taken away cannot come back by itself.
@MainActor
@Observable
final class BoostButtonModel {

    /// Non-nil greys the button. A press then explains instead of boosting,
    /// as a locked pad does.
    var blockReason: String?

    private(set) var isHeld = false

    /// Presses refused because of `blockReason`. A trigger for the haptic.
    private(set) var refusals = 0

    /// A finger is down, whether or not it is holding Boost.
    private var touching = false

    var onPress: () -> Void = {}
    var onRelease: () -> Void = {}
    var onBlocked: (String) -> Void = { _ in }

    /// Finger down. Repeats within the same touch are ignored.
    func press() {
        guard !touching else { return }
        touching = true
        if let blockReason {
            refusals += 1
            onBlocked(blockReason)
            return
        }
        isHeld = true
        onPress()
    }

    /// Finger up, or the touch was cancelled. Ends the touch as well as the
    /// hold, so the next press counts.
    func release() {
        touching = false
        endHold()
    }

    /// Release from outside the gesture: the lock engaged, a stop, the app
    /// is leaving the foreground. The touch, if any, stays spent.
    func forceRelease() {
        endHold()
    }

    private func endHold() {
        guard isHeld else { return }
        isHeld = false
        onRelease()
    }
}
