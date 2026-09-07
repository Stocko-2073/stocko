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

    private(set) var command: DriveCommand = .zero
    private(set) var isEngaged = false

    var onEngage:  (DriveCommand) -> Void = { _ in }
    var onUpdate:  (DriveCommand) -> Void = { _ in }
    var onRelease: () -> Void = {}
    var onBlocked: (DriveLock) -> Void = { _ in }

    /// Finger down. A locked pad never moves its knob and never sends -- it
    /// toasts the reason instead, exactly as `pad.onpointerdown` does.
    func engage(_ c: DriveCommand) {
        if let lock {
            onBlocked(lock)
            return
        }
        isEngaged = true
        command = c
        onEngage(c)
    }

    func update(_ c: DriveCommand) {
        guard isEngaged else { return }
        command = c
        onUpdate(c)
    }

    func release() {
        guard isEngaged else { return }
        isEngaged = false
        command = .zero
        onRelease()
    }

    /// Release from outside the gesture: the lock engaged, or the app is
    /// leaving the foreground. A `DragGesture` that is cancelled rather than
    /// ended never calls `onEnded`, so this path has to exist.
    func forceRelease() {
        if isEngaged { release() } else { command = .zero }
    }
}
