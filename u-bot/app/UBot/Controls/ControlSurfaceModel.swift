import Foundation
import Observation
import UBotCore

/// The seam between whatever the operator pushes around and the drive path.
///
/// The transport never sees the difference between control surfaces: it gets a
/// `DriveCommand` in -1...1 and a release. Today there is one surface, the
/// single centred pad that matches the robot's own web joystick.
@MainActor
@Observable
final class ControlSurfaceModel {

    /// Non-nil greys the pad and refuses to send. Mirrors `lockMsg`.
    var lock: DriveLock?

    /// Unshaped stick position, in drive coordinates, for physical knob tracking.
    private(set) var stickPosition: DriveCommand = .zero
    /// Shaped command delivered to either transport.
    private(set) var command: DriveCommand = .zero
    private let response = StickResponse.standard
    private(set) var isEngaged = false

    var onEngage:  (DriveCommand) -> Void = { _ in }
    var onUpdate:  (DriveCommand) -> Void = { _ in }
    var onRelease: () -> Void = {}
    var onBlocked: (DriveLock) -> Void = { _ in }

    /// Finger down with an unshaped stick position. A locked pad never moves
    /// its knob or sends; it toasts the reason, as `pad.onpointerdown` does.
    func engage(_ c: DriveCommand) {
        if let lock {
            onBlocked(lock)
            return
        }
        isEngaged = true
        setStickPosition(c)
        onEngage(command)
    }

    /// Finger movement, still unshaped so the knob follows the physical input.
    func update(_ c: DriveCommand) {
        guard isEngaged else { return }
        setStickPosition(c)
        onUpdate(command)
    }

    private func setStickPosition(_ position: DriveCommand) {
        stickPosition = position
        let shaped = response.shape(x: -position.w, y: -position.v)
        command = DriveCommand(stickX: shaped.x, stickY: shaped.y)
    }

    func release() {
        guard isEngaged else { return }
        isEngaged = false
        stickPosition = .zero
        command = .zero
        onRelease()
    }

    /// Release from outside the gesture: the lock engaged, or the app is
    /// leaving the foreground. A `DragGesture` that is cancelled rather than
    /// ended never calls `onEnded`, so this path has to exist.
    func forceRelease() {
        if isEngaged {
            release()
        } else {
            stickPosition = .zero
            command = .zero
        }
    }
}
