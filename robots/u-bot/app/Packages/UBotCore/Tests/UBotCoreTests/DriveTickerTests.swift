import Foundation
import Testing
@testable import UBotCore

/// Stands in for the drive characteristic of a connected robot.
private final class RecordingWriter: DriveWriter {
    var isConnected = true
    var canSendWriteWithoutResponse = true
    private(set) var frames: [Data] = []
    func write(_ frame: Data, acknowledged: Bool) { frames.append(frame) }
}

/// A ticker on its own queue, the way the BLE link runs one. The hour-long
/// interval means its real timer never fires; each test steps the cadence
/// with `ticks`, so every frame on the wire is one the test caused.
private final class Harness {
    let queue = DispatchQueue(label: "ticker.test")
    let ticker: DriveTicker
    let writer = RecordingWriter()

    init() {
        ticker = DriveTicker(queue: queue, interval: 3600)
        queue.sync { ticker.target = writer }
    }

    deinit { queue.sync { ticker.abandon() } }

    /// Runs `body` on the ticker's queue, as the link does.
    func on(_ body: (DriveTicker) -> Void) { queue.sync { body(ticker) } }
    func ticks(_ n: Int) { on { t in for _ in 0..<n { t.tick() } } }

    var frames: [Data] { queue.sync { writer.frames } }
    var running: Bool { queue.sync { ticker.isRunning } }
    var boosting: Bool { queue.sync { ticker.boost } }
    /// What went on the wire after the first `mark` frames.
    func since(_ mark: Int) -> [Data] { Array(frames.dropFirst(mark)) }
}

/// A status frame from a robot that does, or does not, take 5-byte frames.
private func status(acceptsBoost: Bool, enabled: Bool = true, faulted: Bool = false) -> UBotStatus {
    var flags: UBotStatus.Flags = enabled ? [.enabled] : []
    if faulted { flags.insert(.faulted) }
    var s = UBotStatus(flags: flags)
    if acceptsBoost { s.flags2 = [.acceptsBoost] }
    return s
}

private let forward = DriveCommand(v: 0.5, w: 0)
private let zeros = { (n: Int) in Array(repeating: DriveCommand.zero.frame, count: n) }
private let bracing = { (n: Int) in Array(repeating: DriveCommand.zero.frame(boost: true), count: n) }

@Suite("Drive ticker")
struct DriveTickerTests {

    @Test("never a 5-byte frame without the capability, whatever Boost does")
    func neverFiveBytesWithoutCapability() {
        let h = Harness()
        h.on { $0.setBoost(true); $0.engage(forward) }
        h.ticks(3)
        // A 0.2.9 frame: flags2 bit 7 clear.
        h.on { $0.statusReceived(status(acceptsBoost: false)) }
        h.ticks(3)
        h.on { $0.release() }
        h.ticks(3)
        h.on { $0.setBoost(false) }
        h.ticks(6)
        #expect(h.frames.count > 10)
        #expect(h.frames.allSatisfy { $0.count == 4 })
    }

    @Test("with the capability and Boost held, frames carry the stick command and the flag")
    func boostWithStick() {
        let h = Harness()
        h.on { $0.statusReceived(status(acceptsBoost: true)); $0.engage(forward) }
        #expect(h.frames == [forward.frame])            // no boost held: 4 bytes, as always
        h.on { $0.setBoost(true) }
        #expect(h.frames.last == forward.frame(boost: true))   // sent at once, not a tick later
        let turn = DriveCommand(v: 0.2, w: 0.4)
        h.on { $0.update(turn) }
        h.ticks(2)
        #expect(h.frames.suffix(2) == [turn.frame(boost: true), turn.frame(boost: true)])
        h.on { $0.setBoost(false) }
        h.ticks(1)
        #expect(h.frames.suffix(2) == [turn.frame, turn.frame])
        #expect(h.running)                              // the stick still holds it open
    }

    @Test("releasing the stick with Boost held keeps bracing: boosted zeros, no tail, no stop")
    func stickReleasedWhileBoosting() {
        let h = Harness()
        h.on { $0.statusReceived(status(acceptsBoost: true)); $0.setBoost(true); $0.engage(forward) }
        let mark = h.frames.count
        h.on { $0.release() }
        h.ticks(10)
        #expect(h.since(mark) == bracing(11))
        #expect(h.running)
    }

    @Test("Boost alone starts the ticker and holds the robot where it is")
    func boostWithoutStick() {
        let h = Harness()
        h.on { $0.statusReceived(status(acceptsBoost: true)) }
        #expect(!h.running)
        h.on { $0.setBoost(true) }
        h.ticks(3)
        #expect(h.frames == bracing(4))
        #expect(h.running)
    }

    @Test("letting go of Boost with no stick ends on the usual four-frame zero tail")
    func boostReleasedWithoutStick() {
        let h = Harness()
        h.on { $0.statusReceived(status(acceptsBoost: true)); $0.setBoost(true) }
        let mark = h.frames.count
        h.on { $0.setBoost(false) }
        h.ticks(4)
        #expect(h.since(mark) == zeros(5))
        #expect(!h.running)
    }

    @Test("a stick release without Boost is exactly what it always was")
    func stickReleaseUnchanged() {
        let h = Harness()
        h.on { $0.statusReceived(status(acceptsBoost: true)); $0.engage(forward) }
        h.on { $0.release() }
        h.ticks(4)
        #expect(h.frames == [forward.frame] + zeros(5))
        #expect(!h.running)
    }

    @Test("Boost pressed during a zero tail cancels the tail and braces")
    func boostDuringTail() {
        let h = Harness()
        h.on { $0.statusReceived(status(acceptsBoost: true)); $0.engage(forward); $0.release() }
        h.ticks(1)
        let mark = h.frames.count
        h.on { $0.setBoost(true) }
        h.ticks(6)
        #expect(h.since(mark) == bracing(7))
        #expect(h.running)
    }

    @Test("stop and E-STOP clear Boost along with the stick")
    func cancelClearsBoost() {
        let h = Harness()
        h.on { $0.statusReceived(status(acceptsBoost: true)); $0.setBoost(true); $0.engage(forward) }
        let mark = h.frames.count
        h.on { $0.cancel() }
        h.ticks(4)
        #expect(h.since(mark) == zeros(5))
        #expect(!h.boosting)
        #expect(!h.running)
    }

    @Test("a faulted or disabled status drops Boost at the transport")
    func faultDropsBoost() {
        for s in [status(acceptsBoost: true, faulted: true), status(acceptsBoost: true, enabled: false)] {
            let h = Harness()
            h.on { $0.statusReceived(status(acceptsBoost: true)); $0.setBoost(true) }
            let mark = h.frames.count
            h.on { $0.statusReceived(s) }
            h.ticks(4)
            #expect(h.since(mark) == zeros(5))
            #expect(!h.boosting)
            #expect(!h.running)
        }
    }

    @Test("a lost connection forgets Boost and the capability")
    func abandonForgets() {
        let h = Harness()
        h.on { $0.statusReceived(status(acceptsBoost: true)); $0.setBoost(true) }
        h.on { $0.abandon() }
        #expect(!h.running)
        #expect(!h.boosting)
        // Reconnected, and no status frame yet on this connection.
        h.on { $0.target = h.writer; $0.engage(forward); $0.setBoost(true) }
        #expect(h.frames.suffix(2) == [forward.frame, forward.frame])
    }

    @Test("an update after the finger is up cannot put motion back on the wire")
    func lateUpdateIgnored() {
        let h = Harness()
        h.on { $0.engage(forward); $0.release(); $0.update(DriveCommand(v: 0.9, w: 0)) }
        h.ticks(4)
        #expect(h.frames == [forward.frame] + zeros(5))
    }

    @Test("a tick dropped for backpressure is made good with the boosted frame")
    func resendKeepsBoost() {
        let h = Harness()
        h.on { $0.statusReceived(status(acceptsBoost: true)); $0.engage(forward) }
        h.writer.canSendWriteWithoutResponse = false
        h.on { $0.setBoost(true) }                  // the transmit queue is shut: dropped
        #expect(h.frames == [forward.frame])
        h.writer.canSendWriteWithoutResponse = true
        h.on { $0.peripheralIsReady() }
        #expect(h.frames == [forward.frame, forward.frame(boost: true)])
    }
}
