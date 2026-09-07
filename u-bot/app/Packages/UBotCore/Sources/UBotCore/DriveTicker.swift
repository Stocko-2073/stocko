import CoreBluetooth
import Foundation

/// Keeps the robot's 500 ms deadman fed while the stick is held, and guarantees
/// a zero on the way out.
///
/// Everything here runs on the BLE serial queue -- the same queue as the
/// `CBCentralManager` delegate callbacks, so the ticker and the connection
/// state can never be observed inconsistently and no lock is needed anywhere.
/// `dispatchPrecondition` keeps that true as the code grows.
///
/// The ticker runs only while the stick is held, plus a short zero tail. A
/// permanently running tick would hold the robot's `cmd_active` flag true
/// forever, which would destroy the app's ability to notice that *another*
/// controller is driving.
final class DriveTicker {

    private let queue: DispatchQueue
    private var timer: DispatchSourceTimer?

    private var command: DriveCommand = .zero
    private var zeroTailRemaining = 0
    private var lastWriteAt = Date.distantPast

    /// Set when a tick could not be sent because the queue was shut, cleared
    /// when it is made good. Without it, `peripheralIsReady` turns into a
    /// self-sustaining send loop -- each write refills the queue, which drains,
    /// which calls back, which writes again -- and the drive characteristic
    /// gets hammered at whatever rate the radio can absorb rather than at the
    /// 20 Hz the timer asks for. Measured at 158-224 writes/s on the bench
    /// before this flag existed.
    private var owesResend = false

    /// Set once the drive characteristic is discovered, cleared on disconnect.
    var target: (peripheral: CBPeripheral, characteristic: CBCharacteristic)?

    /// Rolling counters, drained once a second into a `.linkQuality` event.
    private(set) var written = 0
    private(set) var dropped = 0
    private(set) var escalated = 0

    init(queue: DispatchQueue) { self.queue = queue }

    // MARK: - BLE queue only

    /// Finger down. Sends immediately rather than waiting a whole tick.
    func engage(_ c: DriveCommand) {
        dispatchPrecondition(condition: .onQueue(queue))
        command = c
        zeroTailRemaining = 0
        if timer == nil { startTimer() }
        send()
    }

    /// Finger moved. Coalesced: the next tick sends whatever the newest value
    /// is. A drive command is a latest-value signal, never a stream, so there
    /// is nothing to queue.
    func update(_ c: DriveCommand) {
        dispatchPrecondition(condition: .onQueue(queue))
        command = c
    }

    /// Finger up, lock engaged, app resigned active, or telemetry went stale.
    ///
    /// Sends a zero immediately plus a ~200 ms tail, so a single dropped packet
    /// cannot leave the robot coasting on the last non-zero command for a full
    /// deadman period. If every one of those is lost, the firmware's 500 ms
    /// deadman still stops it -- two independent mechanisms, neither relying on
    /// the other.
    func release() {
        dispatchPrecondition(condition: .onQueue(queue))
        command = .zero
        zeroTailRemaining = 4
        if timer == nil { startTimer() }
        send()
    }

    /// The link is gone. There is nothing left to write and nothing to be done
    /// about it -- the robot's deadman handles it. This is exactly the case the
    /// deadman exists for.
    func abandon() {
        dispatchPrecondition(condition: .onQueue(queue))
        command = .zero
        zeroTailRemaining = 0
        owesResend = false
        target = nil
        stopTimer()
    }

    /// `peripheralIsReady(toSendWriteWithoutResponse:)`.
    ///
    /// Only makes good a tick that was actually dropped. The timer owns the
    /// cadence; this callback exists to recover a miss, not to add sends.
    func peripheralIsReady() {
        dispatchPrecondition(condition: .onQueue(queue))
        guard timer != nil, owesResend else { return }
        send()
    }

    func drainCounters() -> (written: Int, dropped: Int, escalated: Int) {
        dispatchPrecondition(condition: .onQueue(queue))
        defer { written = 0; dropped = 0; escalated = 0 }
        return (written, dropped, escalated)
    }

    // MARK: - Internals

    private func startTimer() {
        let t = DispatchSource.makeTimerSource(queue: queue)
        t.schedule(deadline: .now() + UBotGATT.tickInterval,
                   repeating: UBotGATT.tickInterval,
                   leeway: .milliseconds(5))
        t.setEventHandler { [weak self] in self?.tick() }
        timer = t
        t.resume()
    }

    private func stopTimer() {
        timer?.cancel()
        timer = nil
    }

    private func tick() {
        send()
        if zeroTailRemaining > 0 {
            zeroTailRemaining -= 1
            if zeroTailRemaining == 0 { stopTimer() }
        }
    }

    private func send() {
        guard let (p, ch) = target, p.state == .connected else { return }
        let frame = command.frame
        let now = Date()

        if p.canSendWriteWithoutResponse {
            p.writeValue(frame, for: ch, type: .withoutResponse)
            lastWriteAt = now
            written += 1
            owesResend = false
            return
        }

        // iOS is not ready to take an unacknowledged write. Since iOS 11 these
        // are silently dropped when the transmit queue is full, so dropping the
        // tick here is honest: `peripheralIsReady()` will fire and carry the
        // newest value, which is fresher than anything we could have queued.
        //
        // But the robot ramps to a stop after 500 ms of silence. If the queue
        // has been shut for a quarter of that, force the packet through as an
        // acknowledged write -- the characteristic is declared
        // WRITE_NO_RSP | WRITE in ble.c and the handler returns 0 either way.
        if now.timeIntervalSince(lastWriteAt) > UBotGATT.backpressureEscapeAfter {
            p.writeValue(frame, for: ch, type: .withResponse)
            lastWriteAt = now
            escalated += 1
            owesResend = false
        } else {
            dropped += 1
            owesResend = true
        }
    }
}
