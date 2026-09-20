import CoreBluetooth
import Foundation
import os

/// The real transport. CoreBluetooth central that finds the robot, subscribes
/// to its 5 Hz status, and carries drive and control writes.
///
/// This type compiles and runs on macOS as well as iOS, which is the point:
/// `ubotctl` drives a real robot from a Mac terminal using this exact class, so
/// the GATT contract is verified against hardware before any UI exists.
public final class BLERobotLink: NSObject, RobotLink {

    public var onEvent: (@Sendable (LinkEvent) -> Void)?

    /// The BLE serial queue. The CoreBluetooth delegate callbacks, the drive
    /// ticker, the status watchdog and the link-quality timer all run here, so
    /// none of this state needs a lock.
    private let queue = DispatchQueue(label: "com.stocko.ubot.ble", qos: .userInitiated)
    private let log = Logger(subsystem: "com.stocko.ubot", category: "ble")

    private var central: CBCentralManager!
    private var running = false

    /// Held strongly. CoreBluetooth does not retain peripherals you connect to,
    /// and a deallocated `CBPeripheral` silently stops delivering callbacks.
    private var peripheral: CBPeripheral?

    private var driveChr: CBCharacteristic?
    private var controlChr: CBCharacteristic?
    private var statusChr: CBCharacteristic?

    private lazy var ticker = DriveTicker(queue: queue)

    /// Control writes are acknowledged and CoreBluetooth completes them in
    /// issue order, so a FIFO is enough to pair a response with its op.
    private var pendingControl: [ControlOp] = []

    private var lastStatusAt = Date.distantPast
    private var watchdog: DispatchSourceTimer?
    private var qualityTimer: DispatchSourceTimer?

    private let nameFilter: String
    private static let lastPeripheralKey = "com.stocko.ubot.lastPeripheral"

    private var state: LinkState = .idle {
        didSet {
            guard state != oldValue else { return }
            log.notice("link \(String(describing: oldValue)) -> \(String(describing: self.state))")
            emit(.state(state))
        }
    }

    public init(nameFilter: String = UBotGATT.defaultName) {
        self.nameFilter = nameFilter
        super.init()
    }

    private func emit(_ e: LinkEvent) { onEvent?(e) }

    // MARK: - RobotLink

    public func start() {
        queue.async { [self] in
            guard !running else { return }
            running = true
            if let central {
                if central.state == .poweredOn { reconnectOrScan() }
                return
            }
            central = CBCentralManager(
                delegate: self,
                queue: queue,
                options: [CBCentralManagerOptionShowPowerAlertKey: true])
            // Deliberately NO CBCentralManagerOptionRestoreIdentifierKey. State
            // restoration exists so iOS can relaunch a backgrounded app for BLE
            // events; this app must never be relaunched into a position where
            // it could drive a robot nobody is looking at.
        }
    }

    public func stop() {
        queue.async { [self] in
            running = false
            teardownLink()
            peripheral?.delegate = nil
            if let p = peripheral, p.state != .disconnected { central?.cancelPeripheralConnection(p) }
            if central?.isScanning == true { central?.stopScan() }
            peripheral = nil
            state = .idle
        }
    }

    public func engage(_ c: DriveCommand) {
        queue.async { [self] in
            guard running, state.isReady else { return }
            ticker.engage(c)
            if qualityTimer == nil { startQualityTimer() }
        }
    }

    public func update(_ c: DriveCommand) {
        queue.async { [self] in ticker.update(c) }
    }

    public func releaseStick() {
        queue.async { [self] in ticker.release() }
    }

    public func send(_ op: ControlOp) {
        queue.async { [self] in
            guard running, let p = peripheral, let ch = controlChr, p.state == .connected else {
                emit(.controlRefused(op, "Not connected to the robot."))
                return
            }
            // An E-STOP also drops the stick: there is no sense in a zero-tail
            // fighting a hardware kill.
            if op == .estop || op == .stop { ticker.release() }
            pendingControl.append(op)
            p.writeValue(op.frame, for: ch, type: .withResponse)
        }
    }

    // MARK: - Discovery

    private func reconnectOrScan() {
        // A robot we have connected to before needs no scan at all:
        // CoreBluetooth keeps a per-app, per-device identifier for it.
        if let s = UserDefaults.standard.string(forKey: Self.lastPeripheralKey),
           let id = UUID(uuidString: s),
           let p = central.retrievePeripherals(withIdentifiers: [id]).first {
            log.notice("reconnecting to known peripheral \(id.uuidString, privacy: .public)")
            connect(p, rediscoverAfterTimeout: true)
            return
        }
        beginScan()
    }

    private func beginScan() {
        guard running, central.state == .poweredOn, !central.isScanning else { return }
        state = .scanning
        // Scan UNFILTERED and match ourselves.
        //
        // advertise() in ble.c puts the local name and the 16-bit 0x180A/0x180F
        // in the advertisement, and the 128-bit service UUID only in the SCAN
        // RESPONSE -- it does not fit in 31 bytes beside the name.
        // `scanForPeripherals(withServices:)` filters on the advertisement, and
        // whether a scan-response UUID satisfies that filter is not contractual.
        // Matching by hand costs nothing and cannot silently fail.
        central.scanForPeripherals(
            withServices: nil,
            options: [CBCentralManagerScanOptionAllowDuplicatesKey: false])
    }

    private func connect(_ p: CBPeripheral, rediscoverAfterTimeout: Bool = false) {
        peripheral = p
        p.delegate = self                       // before any discovery call
        state = .connecting(name: p.name ?? nameFilter)
        // iOS 17: CoreBluetooth re-establishes the link itself when the robot
        // comes back. A pending connect has no timeout and completes the moment
        // it advertises again -- exactly right when the robot is power-cycled
        // in a field.
        central.connect(p, options: [CBConnectPeripheralOptionEnableAutoReconnect: true])
        if rediscoverAfterTimeout {
            // A cached identifier can outlive the robot's BLE identity. Give
            // it a short chance, then discover the currently advertising robot.
            queue.asyncAfter(deadline: .now() + 8) { [weak self, weak p] in
                guard let self, let p, self.running, self.peripheral === p,
                      self.central.state == .poweredOn,
                      p.state != .connected else { return }
                switch self.state {
                case .connecting, .reconnecting: break
                default: return
                }
                self.log.notice("remembered peripheral unavailable; scanning again")
                UserDefaults.standard.removeObject(forKey: Self.lastPeripheralKey)
                self.peripheral = nil
                p.delegate = nil
                self.central.cancelPeripheralConnection(p)
                self.teardownLink()
                self.beginScan()
            }
        }
    }

    // MARK: - Watchdogs

    private func startWatchdog() {
        guard watchdog == nil else { return }
        let t = DispatchSource.makeTimerSource(queue: queue)
        t.schedule(deadline: .now() + 0.5, repeating: 0.5, leeway: .milliseconds(50))
        t.setEventHandler { [weak self] in self?.checkStatusFlow() }
        watchdog = t
        t.resume()
    }

    private func stopWatchdog() { watchdog?.cancel(); watchdog = nil }

    /// Detect telemetry loss on a link CoreBluetooth still calls healthy.
    ///
    /// `s_status_subscribed` in ble.c is a single global bool, set from
    /// whichever peer last touched a CCCD. If a laptop is also connected and
    /// unsubscribes, the firmware stops notifying *everyone* -- including this
    /// phone -- with the connection perfectly intact. CoreBluetooth will never
    /// report that. It can only be detected by absence.
    private func checkStatusFlow() {
        guard let p = peripheral, p.state == .connected, let ch = statusChr else { return }
        guard Date().timeIntervalSince(lastStatusAt) > UBotGATT.statusStaleAfter else { return }

        if case .stalled = state {} else {
            log.warning("status stale, re-arming CCCD and polling")
            state = .stalled(name: p.name ?? nameFilter)
        }
        ticker.release()                        // never drive on stale telemetry
        if !ch.isNotifying { p.setNotifyValue(true, for: ch) }
        p.readValue(for: ch)                    // the characteristic is READ | NOTIFY
    }

    private func startQualityTimer() {
        let t = DispatchSource.makeTimerSource(queue: queue)
        t.schedule(deadline: .now() + 1, repeating: 1, leeway: .milliseconds(100))
        t.setEventHandler { [weak self] in
            guard let self else { return }
            let c = self.ticker.drainCounters()
            if c.written + c.dropped + c.escalated > 0 {
                self.emit(.linkQuality(written: c.written,
                                       dropped: c.dropped,
                                       escalated: c.escalated))
            }
        }
        qualityTimer = t
        t.resume()
    }

    private func stopQualityTimer() { qualityTimer?.cancel(); qualityTimer = nil }

    private func teardownLink() {
        ticker.abandon()
        driveChr = nil
        controlChr = nil
        statusChr = nil
        pendingControl.removeAll()
        stopWatchdog()
        stopQualityTimer()
    }
}

// MARK: - CBCentralManagerDelegate

extension BLERobotLink: CBCentralManagerDelegate {

    public func centralManagerDidUpdateState(_ c: CBCentralManager) {
        guard running else { return }
        switch c.state {
        case .poweredOn:
            reconnectOrScan()
        case .poweredOff:
            teardownLink()
            state = .bluetoothOff
        case .unauthorized:
            teardownLink()
            state = .unauthorized
        case .unsupported:
            state = .unsupported
        default:
            state = .idle
        }
    }

    public func centralManager(_ c: CBCentralManager,
                               didDiscover p: CBPeripheral,
                               advertisementData ad: [String: Any],
                               rssi: NSNumber) {
        guard running else { return }
        let advertised = ad[CBAdvertisementDataServiceUUIDsKey]         as? [CBUUID] ?? []
        let overflow   = ad[CBAdvertisementDataOverflowServiceUUIDsKey] as? [CBUUID] ?? []
        let name       = ad[CBAdvertisementDataLocalNameKey] as? String ?? p.name ?? ""

        guard advertised.contains(UBotGATT.service)
                || overflow.contains(UBotGATT.service)
                || name.caseInsensitiveCompare(nameFilter) == .orderedSame
        else { return }

        log.notice("found \(name, privacy: .public) rssi \(rssi.intValue)")
        c.stopScan()
        connect(p)
    }

    public func centralManager(_ c: CBCentralManager, didConnect p: CBPeripheral) {
        guard running, peripheral === p else { return }
        UserDefaults.standard.set(p.identifier.uuidString, forKey: Self.lastPeripheralKey)
        state = .discovering(name: p.name ?? nameFilter)
        p.discoverServices([UBotGATT.service, UBotGATT.batteryService, UBotGATT.deviceInfo])
    }

    public func centralManager(_ c: CBCentralManager,
                               didFailToConnect p: CBPeripheral,
                               error: Error?) {
        guard running, peripheral === p else { return }
        log.error("connect failed: \(error?.localizedDescription ?? "unknown", privacy: .public)")
        state = .reconnecting(name: p.name ?? nameFilter)
        c.connect(p, options: [CBConnectPeripheralOptionEnableAutoReconnect: true])
    }

    /// The iOS 17 / macOS 14 form. When this is implemented the older
    /// two-argument `didDisconnectPeripheral:error:` is never called -- do not
    /// implement both.
    public func centralManager(_ c: CBCentralManager,
                               didDisconnectPeripheral p: CBPeripheral,
                               timestamp: CFAbsoluteTime,
                               isReconnecting: Bool,
                               error: Error?) {
        guard running, peripheral === p else { return }
        log.notice("disconnected, isReconnecting \(isReconnecting)")
        // Nothing left to write. The robot's 500 ms deadman ramps it to a stop
        // on its own -- that is precisely what the deadman is for.
        teardownLink()
        state = .reconnecting(name: p.name ?? nameFilter)
        if !isReconnecting {
            c.connect(p, options: [CBConnectPeripheralOptionEnableAutoReconnect: true])
        }
    }
}

// MARK: - CBPeripheralDelegate

extension BLERobotLink: CBPeripheralDelegate {

    public func peripheral(_ p: CBPeripheral, didDiscoverServices error: Error?) {
        guard running, peripheral === p else { return }
        if let error {
            log.error("service discovery: \(error.localizedDescription, privacy: .public)")
            return
        }
        for s in p.services ?? [] {
            switch s.uuid {
            case UBotGATT.service:
                p.discoverCharacteristics(
                    [UBotGATT.drive, UBotGATT.control, UBotGATT.status], for: s)
            case UBotGATT.batteryService:
                p.discoverCharacteristics([UBotGATT.batteryLevel], for: s)
            case UBotGATT.deviceInfo:
                p.discoverCharacteristics(
                    [UBotGATT.firmwareRevision, UBotGATT.modelNumber], for: s)
            default:
                break
            }
        }
    }

    public func peripheral(_ p: CBPeripheral,
                           didDiscoverCharacteristicsFor s: CBService,
                           error: Error?) {
        guard running, peripheral === p else { return }
        for ch in s.characteristics ?? [] {
            switch ch.uuid {
            case UBotGATT.drive:
                driveChr = ch
                ticker.target = (p, ch)
            case UBotGATT.control:
                controlChr = ch
            case UBotGATT.status:
                statusChr = ch
                p.setNotifyValue(true, for: ch)
                p.readValue(for: ch)            // paint the HUD before the first notify
            case UBotGATT.batteryLevel:
                p.setNotifyValue(true, for: ch)
                p.readValue(for: ch)
            case UBotGATT.firmwareRevision, UBotGATT.modelNumber:
                p.readValue(for: ch)
            default:
                break
            }
        }

        if driveChr != nil, controlChr != nil, statusChr != nil, !state.isReady {
            lastStatusAt = Date()
            state = .ready(name: p.name ?? nameFilter)
            startWatchdog()
        }
    }

    public func peripheral(_ p: CBPeripheral,
                           didUpdateValueFor ch: CBCharacteristic,
                           error: Error?) {
        guard running, peripheral === p, error == nil, let data = ch.value else { return }
        switch ch.uuid {
        case UBotGATT.status:
            guard let s = UBotStatus(data) else {
                log.error("status frame was \(data.count) bytes, expected \(UBotStatus.byteCount)")
                return
            }
            lastStatusAt = Date()
            if case .stalled = state { state = .ready(name: p.name ?? nameFilter) }
            emit(.status(s))
        case UBotGATT.batteryLevel:
            if let pct = data.first { emit(.batteryLevel(pct)) }
        case UBotGATT.firmwareRevision:
            emit(.firmware(String(decoding: data, as: UTF8.self)))
        case UBotGATT.modelNumber:
            emit(.model(String(decoding: data, as: UTF8.self)))
        default:
            break
        }
    }

    public func peripheral(_ p: CBPeripheral,
                           didWriteValueFor ch: CBCharacteristic,
                           error: Error?) {
        // Only control writes are acknowledged and tracked. A drive write that
        // was escalated to .withResponse under backpressure also lands here and
        // is deliberately ignored -- the firmware returns 0 for it regardless,
        // so it carries no information.
        guard ch.uuid == UBotGATT.control, !pendingControl.isEmpty else { return }
        let op = pendingControl.removeFirst()

        if let e = error as? CBATTError {
            switch e.code {
            case .unlikelyError:                    // 0x0E -- the drive layer said no
                emit(.controlRefused(op, op.refusalText))
            case .invalidAttributeValueLength:      // 0x0D -- our frame was malformed
                emit(.controlRefused(op, "The robot rejected the message length."))
            default:
                emit(.controlRefused(op, e.localizedDescription))
            }
        } else if let error {
            emit(.controlRefused(op, error.localizedDescription))
        } else {
            emit(.controlAccepted(op))
        }
    }

    public func peripheralIsReady(toSendWriteWithoutResponse p: CBPeripheral) {
        ticker.peripheralIsReady()
    }
}
