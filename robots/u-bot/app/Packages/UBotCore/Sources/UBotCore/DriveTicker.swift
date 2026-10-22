import CoreBluetooth
import Foundation

/// Where the ticker's frames go. In the app this is always
/// `PeripheralDriveWriter`; the seam exists so the cadence and the framing
/// rules can be tested without a radio.
protocol DriveWriter: AnyObject {
    var isConnected: Bool { get }
    var canSendWriteWithoutResponse: Bool { get }
    func write(_ frame: Data, acknowledged: Bool)
}

/// The drive characteristic on a connected peripheral. Holds the peripheral
/// strongly, as the ticker always has: CoreBluetooth does not retain one, and
/// a deallocated `CBPeripheral` silently stops delivering callbacks.
final class PeripheralDriveWriter: DriveWriter {
    private let peripheral: CBPeripheral
    private let characteristic: CBCharacteristic

    init(peripheral: CBPeripheral, characteristic: CBCharacteristic) {
        self.peripheral = peripheral
        self.characteristic = characteristic
    }

    var isConnected: Bool { peripheral.state == .connected }
    var canSendWriteWithoutResponse: Bool { peripheral.canSendWriteWithoutResponse }

    func write(_ frame: Data, acknowledged: Bool) {
        peripheral.writeValue(frame, for: characteristic,
                              type: acknowledged ? .withResponse : .withoutResponse)
    }
}

/// Keeps the robot's 500 ms deadman fed while the stick or Boost is held, and
/// guarantees a zero on the way out.
///
/// Everything here runs on the BLE serial queue -- the same queue as the
/// `CBCentralManager` delegate callbacks, so the ticker and the connection
/// state can never be observed inconsistently and no lock is needed anywhere.
/// `dispatchPrecondition` keeps that true as the code grows.
///
/// The ticker runs only while the stick or Boost is held, plus a short zero
/// tail. A permanently running tick would hold the robot's `cmd_active` flag
/// true forever, which would destroy the app's ability to notice that
/// *another* controller is driving.
///
/// Boost adds two rules. Held without the stick, it keeps the ticker sending
/// zero frames that carry the flag, so the robot holds its place at boost
/// current -- the stop on a hill. And the flag only exists in the 5-byte
/// frame, which firmware before 0.3.0 rejects outright, so that frame goes out
/// only while the latest status on this connection says the robot takes it.
/// Every other frame is the 4-byte one, byte for byte what it always was.
final class DriveTicker {

    private let queue: DispatchQueue
    private let interval: TimeInterval
    private var timer: DispatchSourceTimer?

    private var command: DriveCommand = .zero
    private var stickHeld = false
    private var zeroTailRemaining = 0
    private var lastWriteAt = Date.distantPast

    /// The operator is holding Boost.
    private(set) var boost = false

    /// The robot accepts 5-byte drive frames: status flags2 bit 7. Refreshed
    /// from every status frame and forgotten with the connection.
    private(set) var extendedFrames = false

    /// Set when a tick could not be sent because the queue was shut, cleared
    /// when it is made good. Without it, `peripheralIsReady` turns into a
    /// self-sustaining send loop -- each write refills the queue, which drains,
    /// which calls back, which writes again -- and the drive characteristic
    /// gets hammered at whatever rate the radio can absorb rather than at the
    /// 20 Hz the timer asks for. Measured at 158-224 writes/s on the bench
    /// before this flag existed.
    private var owesResend = false

    /// Set once the drive characteristic is discovered, cleared on disconnect.
    var target: DriveWriter?

    /// Rolling counters, drained once a second into a `.linkQuality` event.
    private(set) var written = 0
    private(set) var dropped = 0
    private(set) var escalated = 0

    /// `interval` is the tick period. Tests pass something long and call
    /// `tick()` themselves, so no real timer ever fires under them.
    init(queue: DispatchQueue, interval: TimeInterval = UBotGATT.tickInterval) {
        self.queue = queue
        self.interval = interval
    }

    // MARK: - BLE queue only

    /// Finger down. Sends immediately rather than waiting a whole tick.
    func engage(_ c: DriveCommand) {
        dispatchPrecondition(condition: .onQueue(queue))
        stickHeld = true
        command = c
        zeroTailRemaining = 0
        if timer == nil { startTimer() }
        send()
    }

    /// Finger moved. Coalesced: the next tick sends whatever the newest value
    /// is. A drive command is a latest-value signal, never a stream, so there
    /// is nothing to queue. Ignored once the finger is up, so a late update
    /// can never put motion back into a zero tail or a Boost brace.
    func update(_ c: DriveCommand) {
        dispatchPrecondition(condition: .onQueue(queue))
        guard stickHeld else { return }
        command = c
    }

    /// Finger up, lock engaged, app resigned active, or telemetry went stale.
    ///
    /// Sends a zero immediately plus a ~200 ms tail, so a single dropped packet
    /// cannot leave the robot coasting on the last non-zero command for a full
    /// deadman period. If every one of those is lost, the firmware's 500 ms
    /// deadman still stops it -- two independent mechanisms, neither relying on
    /// the other.
    ///
    /// With Boost held there is no tail: the boosted zeros that keep coming
    /// are the stop, and a tail would count down and end the brace.
    func release() {
        dispatchPrecondition(condition: .onQueue(queue))
        stickHeld = false
        command = .zero
        zeroTailRemaining = boost ? 0 : 4
        if timer == nil { startTimer() }
        send()
    }

    /// Boost pressed or let go. Sent at once, so the robot hears the change
    /// now rather than a tick later. Let go with no stick held, it ends with
    /// the same zero tail as a stick release.
    func setBoost(_ on: Bool) {
        dispatchPrecondition(condition: .onQueue(queue))
        guard on != boost else { return }
        boost = on
        if on {
            zeroTailRemaining = 0
        } else if !stickHeld {
            command = .zero
            zeroTailRemaining = 4
        }
        if timer == nil { startTimer() }
        send()
    }

    /// Stop or E-STOP. The operator's intent is void as a whole: the stick
    /// and Boost go together, with the usual zero tail.
    func cancel() {
        dispatchPrecondition(condition: .onQueue(queue))
        boost = false
        release()
    }

    /// Every decoded status frame, notified or polled.
    func statusReceived(_ s: UBotStatus) {
        dispatchPrecondition(condition: .onQueue(queue))
        extendedFrames = s.acceptsBoost
        // Motors off or a latched fault: there is nothing left to brace, and
        // the robot refuses the frames anyway. The app lets go of Boost for
        // the same reason from the same frame; this does not wait for it.
        if boost, !s.isEnabled || s.isFaulted { setBoost(false) }
    }

    /// The link is gone. There is nothing left to write and nothing to be done
    /// about it -- the robot's deadman handles it. This is exactly the case the
    /// deadman exists for. Boost and the capability go with the connection: a
    /// reconnect starts from 4-byte frames until a status says otherwise.
    func abandon() {
        dispatchPrecondition(condition: .onQueue(queue))
        command = .zero
        stickHeld = false
        boost = false
        extendedFrames = false
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

    /// True while the timer is feeding the deadman.
    var isRunning: Bool { timer != nil }

    /// One timer period. Internal so tests can step the cadence themselves.
    func tick() {
        dispatchPrecondition(condition: .onQueue(queue))
        send()
        if zeroTailRemaining > 0 {
            zeroTailRemaining -= 1
            if zeroTailRemaining == 0 { stopTimer() }
        }
    }

    // MARK: - Internals

    private func startTimer() {
        let t = DispatchSource.makeTimerSource(queue: queue)
        t.schedule(deadline: .now() + interval,
                   repeating: interval,
                   leeway: .milliseconds(5))
        t.setEventHandler { [weak self] in self?.tick() }
        timer = t
        t.resume()
    }

    private func stopTimer() {
        timer?.cancel()
        timer = nil
    }

    private func send() {
        guard let target, target.isConnected else { return }
        let frame = boost && extendedFrames ? command.frame(boost: true) : command.frame
        let now = Date()

        if target.canSendWriteWithoutResponse {
            target.write(frame, acknowledged: false)
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
            target.write(frame, acknowledged: true)
            lastWriteAt = now
            escalated += 1
            owesResend = false
        } else {
            dropped += 1
            owesResend = true
        }
    }
}
