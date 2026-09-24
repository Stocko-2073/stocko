import AgentCamCore
import ARKit
import Observation
import os
import RealityKit
import UIKit

/// The app: links the Mac, the camera and the screen. Main actor; the
/// tracking session, link and uploader run on their own queues and report here.
@MainActor @Observable
final class AppModel {
    struct PageUI: Equatable {
        var locked = false
        var markersSeen = 0
        var markersUsed = 0
        var tiltDeg: Double?
        var jitterMm: Double?
        var arkit = "not running"
        var rejection: String?
        var generation = 1
    }

    enum Readiness: Equatable {
        case idle, findingPage, aligning, holding, capturing
    }

    struct GuidanceUI: Equatable {
        var readiness = Readiness.idle
        /// The instruction that matters most now, shown large on the camera view.
        var primary: String?
        var secondary: [String] = []
        var aligned = false
        var holdProgress = 0.0
        /// Unit direction (view coordinates) toward an off-screen target.
        var arrow: SIMD2<Double>?
        /// "Turn the page 90° ↻, object and all" when the target is round the other side.
        var pageTurn: String?
    }

    // MARK: State the UI shows

    var linkState: ServerLinkState = .idle
    var serverName: String?
    var networkProblem: String?
    var pending: [PhotoRequest] = []
    var active: PhotoRequest?
    var placementPrompt: Placement?
    var page = PageUI()
    var guidance = GuidanceUI()
    var outboxPending = 0
    var toast: String?
    var lastThumbnail: CGImage?
    var capturing = false
    /// Set when the last queued request is done, until new ones arrive.
    var setComplete: (taken: Int, skipped: Int)?
    let arAvailable = ARTrackingSession.isSupported

    // MARK: Parts

    let settings = Settings()
    let arView: ARView
    let tracking: ARTrackingSession
    private let renderer: GuidanceRenderer
    private let outbox: Outbox
    private let uploader: Uploader
    private let capture: CaptureCoordinator
    private let link: ServerLink
    private let discovery = ServerDiscovery()
    private let endpoint = OSAllocatedUnfairLock<URL?>(initialState: nil)
    private var discovered: URL?
    private var connectedURL: URL?

    private var snapshot: RequestsSnapshot?
    private var locallyDone: Set<String> = []
    private var inOutbox: Set<String> = []
    private var confirmedPlacement: String?
    private var board = BoardInfo()
    private var layout: BoardLayout = try! BoardLayout.bundled()
    private let steadiness = SteadinessDetector()
    private var alignedSince: TimeInterval?
    private var activeSince: TimeInterval?
    private var timer: Timer?
    private var lastStatus: TimeInterval = 0
    private var lastControls: TimeInterval = 0
    private var controlsFor: String?
    private var foreground = false
    private var toastTask: Task<Void, Never>?

    init() {
        arView = ARView(frame: .zero, cameraMode: .ar, automaticallyConfigureSession: false)
        arView.renderOptions = [.disableMotionBlur, .disableDepthOfField, .disableCameraGrain, .disableHDR,
                                .disableGroundingShadows, .disableAREnvironmentLighting, .disablePersonOcclusion,
                                .disableFaceMesh]
        tracking = ARTrackingSession(session: arView.session)
        renderer = GuidanceRenderer(arView: arView, tracking: tracking)
        let docs = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask)[0]
        outbox = try! Outbox(root: docs.appendingPathComponent("Outbox", isDirectory: true))
        uploader = Uploader(outbox: outbox)
        capture = CaptureCoordinator(tracking: tracking, outbox: outbox, uploader: uploader)
        let endpoint = self.endpoint
        link = ServerLink(endpoint: { endpoint.withLock { $0 } },
                          hello: { DeviceInfo.hello(appState: "foreground") })
        inOutbox = Set(outbox.pending().map(\.meta.requestId))
        outboxPending = inOutbox.count
        renderer.scene.pageOutline = layout.outline

        link.onEvent = { [weak self] e in Task { @MainActor in self?.handle(e) } }
        uploader.onEvent = { [weak self] e in Task { @MainActor in self?.handle(e) } }
        discovery.onEvent = { [weak self] e in Task { @MainActor in self?.handle(e) } }
        updateEndpoint()
    }

    // MARK: Lifecycle

    func setForeground(_ isForeground: Bool) {
        guard isForeground != foreground else { return }
        foreground = isForeground
        if isForeground {
            UIApplication.shared.isIdleTimerDisabled = true
            tracking.run()
            discovery.start()
            link.start()
            link.kick()
            timer = Timer.scheduledTimer(withTimeInterval: 1.0 / 30, repeats: true) { [weak self] _ in
                MainActor.assumeIsolated { self?.tick() }
            }
        } else {
            UIApplication.shared.isIdleTimerDisabled = false
            timer?.invalidate()
            timer = nil
            link.sayBye("background")
            tracking.pause()
            discovery.stop()
            // Give the goodbye and any upload a moment before iOS suspends us;
            // the outbox keeps whatever doesn't make it.
            backgroundTask = UIApplication.shared.beginBackgroundTask { [weak self] in
                MainActor.assumeIsolated { self?.endBackgroundTask() }
            }
            Task { @MainActor [link] in
                try? await Task.sleep(for: .seconds(1))
                if !self.foreground { link.stop() }
                try? await Task.sleep(for: .seconds(8))
                self.endBackgroundTask()
            }
        }
    }

    private var backgroundTask = UIBackgroundTaskIdentifier.invalid

    private func endBackgroundTask() {
        guard backgroundTask != .invalid else { return }
        UIApplication.shared.endBackgroundTask(backgroundTask)
        backgroundTask = .invalid
    }

    func manualServerChanged() {
        updateEndpoint()
        link.kick()
    }

    private func updateEndpoint() {
        let url = ServerDiscovery.manualURL(settings.manualServer) ?? discovered
        endpoint.withLock { $0 = url }
    }

    // MARK: Events

    private func handle(_ e: ServerLinkEvent) {
        switch e {
        case .state(let s):
            linkState = s
            if case .connected = s {
                connectedURL = endpoint.withLock { $0 }
                uploader.setServer(connectedURL)
                networkProblem = nil
            } else {
                uploader.setServer(nil)
            }
        case .welcome(let w):
            if w.board != board {
                board = w.board
                if let l = try? BoardLayout.bundled(w.board) {
                    layout = l
                    renderer.scene.pageOutline = l.outline
                }
                tracking.setBoard(w.board)
            }
        case .requests(let s):
            snapshot = s
            let ids = Set(s.items.map(\.id))
            locallyDone.formIntersection(ids)            // the server has caught up on the rest
            refreshQueue()
        case .message(let m):
            show(m)
        }
    }

    private func handle(_ e: UploaderEvent) {
        switch e {
        case .pending(let count, _):
            outboxPending = count
            inOutbox = Set(outbox.pending().map(\.meta.requestId))
        case .uploaded(let rid, _):
            show("Sent \(rid) to the Mac.")
        case .rejected(let rid, _, let reason):
            show("The Mac refused \(rid): \(reason)")
        }
    }

    private func handle(_ e: ServerDiscovery.Event) {
        switch e {
        case .found(let url, let name):
            discovered = url
            serverName = name
            networkProblem = nil
            updateEndpoint()
            link.kick()
        case .lost:
            discovered = nil
            serverName = nil
            updateEndpoint()
        case .failed(let why):
            networkProblem = why
        }
    }

    // MARK: Queue

    private var setTaken = 0
    private var setSkipped = 0

    private func refreshQueue() {
        let items = snapshot?.items ?? []
        pending = items.filter { !locallyDone.contains($0.id) && !inOutbox.contains($0.id) }
        if pending.isEmpty, setTaken + setSkipped > 0 {
            setComplete = (setTaken, setSkipped)
        } else if !pending.isEmpty, setComplete != nil {
            setComplete = nil                                   // a new set has started
            setTaken = 0
            setSkipped = 0
        }
        if let a = active, pending.contains(where: { $0.id == a.id }) {
            active = pending.first { $0.id == a.id }           // keep guiding; pick up any edits
        } else {
            active = nextRequest()
            resetGuidance()
        }
        if let p = active?.placement, p.label != confirmedPlacement {
            placementPrompt = p
        } else {
            placementPrompt = nil
        }
    }

    /// Within the current placement, the nearest target first; placements in
    /// request order, so the object is turned over as few times as possible.
    private func nextRequest() -> PhotoRequest? {
        let samePlacement = pending.filter { $0.placement == nil || $0.placement?.label == confirmedPlacement }
        guard !samePlacement.isEmpty else { return pending.first }
        guard let here = tracking.snapshot.cameraToPage else { return samePlacement.first }
        return samePlacement.min { a, b in
            distance(here, a) < distance(here, b)
        }
    }

    private func distance(_ here: Pose, _ r: PhotoRequest) -> Double {
        if r.kind == .freeform { return 0 }                    // taken from wherever the page is in view
        guard let t = r.target.flatMap({ Pose(rows: $0.cameraToPage) }) else { return .infinity }
        return simd_distance(here.translation, t.translation)
    }

    func confirmPlacement() {
        confirmedPlacement = placementPrompt?.label
        placementPrompt = nil
        resetGuidance()
    }

    func skipActive(reason: String) {
        guard let a = active else { return }
        link.send(update: RequestUpdate(id: a.id, reason: reason))
        locallyDone.insert(a.id)
        setSkipped += 1
        active = nil
        refreshQueue()
    }

    private func resetGuidance() {
        steadiness.reset()
        alignedSince = nil
        activeSince = tracking.snapshot.time
        guidance = GuidanceUI()
    }

    // MARK: Capture

    private let alignedHaptic = UIImpactFeedbackGenerator(style: .light)
    private let captureHaptic = UINotificationFeedbackGenerator()

    private func take(_ request: PhotoRequest) {
        guard !capturing else { return }
        capturing = true
        let now = tracking.snapshot.time
        let window = request.kind == .freeform ? Self.freeformSteadyS : request.tolerance.steadyS
        let speeds = steadiness.speeds(window: window, now: now)
        capture.capture(request, placement: confirmedPlacement, speeds: speeds) { [weak self] result in
            guard let self else { return }
            capturing = false
            switch result {
            case .success(let r):
                captureHaptic.notificationOccurred(.success)
                lastThumbnail = r.thumbnail
                locallyDone.insert(r.requestId)
                inOutbox.insert(r.requestId)
                setTaken += 1
                show(r.hadPagePose ? "Captured \(r.requestId)." : "Captured \(r.requestId), without a page pose.")
                active = nil
                refreshQueue()
            case .failure(let e):
                captureHaptic.notificationOccurred(.error)
                show(e.localizedDescription)
                resetGuidance()
            }
        }
    }

    // MARK: The 30 Hz tick: guidance, auto-capture, status

    private func tick() {
        let snap = tracking.snapshot
        let newPage = PageUI(locked: snap.page?.locked ?? false, markersSeen: snap.markersSeen, markersUsed: snap.markersUsed,
                             tiltDeg: snap.page?.tiltDeg, jitterMm: snap.page?.jitterMm, arkit: snap.arkit,
                             rejection: snap.lastRejection, generation: snap.page?.boardGeneration ?? 1)
        if newPage != page { page = newPage }

        applyCameraControls(now: snap.time)
        updateGuidance(snap)

        if snap.time - lastStatus > 0.5 || snap.time < lastStatus {
            lastStatus = snap.time
            link.send(status: status(snap))
        }
    }

    private func applyCameraControls(now: TimeInterval) {
        let options = placementPrompt == nil ? active?.options : nil
        let key = active.map { "\($0.id)-\(placementPrompt == nil)" }
        // Reapply now and then: ARKit turns the torch off on its own.
        if key != controlsFor || (options?.torch ?? 0 > 0 && now - lastControls > 1) {
            controlsFor = key
            lastControls = now
            CameraControls.applyWhileGuiding(options)
        }
    }

    private func updateGuidance(_ snap: TrackingSnapshot) {
        guard let a = active, placementPrompt == nil else {
            renderer.scene.target = nil
            if guidance != GuidanceUI() { guidance = GuidanceUI() }
            return
        }
        if capturing {
            guidance.readiness = .capturing
            return
        }
        guard let here = snap.cameraToPage else {
            renderer.scene.target = nil
            renderer.scene.aligned = false
            alignedSince = nil
            guidance = GuidanceUI(readiness: .findingPage, primary: "Point at the page")
            return
        }
        steadiness.add(time: snap.time, pose: here)
        let tol = a.tolerance
        if a.options.needsFullPath {
            renderer.scene.target = nil
            guidance = GuidanceUI(readiness: .aligning, primary: "Can't do this one yet",
                                  secondary: ["It needs a lens or flash this build can't use: tap Can't reach"])
            return
        }
        if a.kind == .freeform { return wholePage(a, snap, here: here) }
        guard a.kind == .pose, let tgt = a.target, let target = Pose(rows: tgt.cameraToPage) else {
            freeFraming(a, snap)
            return
        }

        let cursorDistance = GuidanceGeometry.cursorDistanceMm(targetDistanceMm: tgt.distanceMm)
        renderer.scene.target = target
        renderer.scene.lookAt = SIMD3(tgt.lookAt[0], tgt.lookAt[1], tgt.lookAt[2])
        renderer.scene.cursorDistanceMm = cursorDistance
        guard let page = snap.page, let worldFromCamera = snap.worldFromCamera else { return }
        let report = Alignment.report(current: here, target: target)
        let positionTol = tgt.positionToleranceMm
        let aligned = Alignment.isAligned(report, positionMm: positionTol, pointingDeg: tol.pointingDeg, rollDeg: tol.rollDeg)
        let steady = steadiness.isSteady(window: tol.steadyS, now: snap.time, maxMmPerS: tol.maxSpeedMmS,
                                         maxDegPerS: tol.maxAngSpeedDegS)
        if aligned {
            if alignedSince == nil { alignedHaptic.impactOccurred() }
            alignedSince = alignedSince ?? snap.time
        } else {
            alignedSince = nil
        }
        let progress = alignedSince.map { min(1, (snap.time - $0) / max(tol.steadyS, 0.01)) } ?? 0

        // Where the target cube's centre is, relative to this camera.
        let cameraFromTargetCube = worldFromCamera.rigidInverse * page.worldFromPage * target
        let centre = cameraFromTargetCube.transform(SIMD3(0, 0, cursorDistance))
        let arrow = OffscreenArrow.direction(toCameraPoint: centre, k: snap.k, imageSize: snap.imageSize, marginPx: 60)
        let hints = Alignment.hints(report, hold: a.pose?.hold ?? .landscape, positionMm: positionTol,
                                    current: here, target: target)
        let turn = aligned ? nil : Reach.pageTurnDeg(targetEye: target.translation, user: here.translation)
        renderer.scene.aligned = aligned
        guidance = GuidanceUI(readiness: aligned ? .holding : .aligning,
                              primary: aligned ? (steady ? "Hold…" : "Hold still") : hints.first ?? "Line up the cubes",
                              secondary: aligned ? [] : Array(hints.dropFirst().prefix(2)),
                              aligned: aligned, holdProgress: progress, arrow: arrow,
                              pageTurn: turn.map(Reach.describe(pageTurnDeg:)))

        if aligned, steady, progress >= 1 {
            take(a)
        }
    }

    /// No target: the user frames the shot and holds still for a moment.
    private func freeFraming(_ a: PhotoRequest, _ snap: TrackingSnapshot) {
        renderer.scene.target = nil
        let tol = a.tolerance
        let hold = max(1.0, 2 * tol.steadyS)
        // Time to read the note before a still phone counts as "ready".
        let settled = snap.time - (activeSince ?? snap.time) > 1.5
        let steady = settled && steadiness.isSteady(window: tol.steadyS, now: snap.time, maxMmPerS: tol.maxSpeedMmS,
                                                    maxDegPerS: tol.maxAngSpeedDegS)
        if steady {
            if alignedSince == nil { alignedHaptic.impactOccurred() }
            alignedSince = alignedSince ?? snap.time
        } else {
            alignedSince = nil
        }
        let progress = alignedSince.map { min(1, (snap.time - $0) / hold) } ?? 0
        guidance = GuidanceUI(readiness: steady ? .holding : .aligning,
                              primary: steady ? "Hold…" : "Frame it, then hold still",
                              aligned: steady, holdProgress: progress)
        if steady, progress >= 1 { take(a) }
    }

    /// Long enough that hand shake doesn't read as movement, short enough not to feel like a hold.
    private static let freeformSteadyS: TimeInterval = 1.0 / 3

    /// Freeform: no target and no hold. Taken the moment the page is found
    /// (markers seen within the last half second) and wholly in view, once the
    /// phone is under the request's speed limits: a phone still moving into
    /// frame would blur the shot.
    private func wholePage(_ a: PhotoRequest, _ snap: TrackingSnapshot, here: Pose) {
        renderer.scene.target = nil
        guard let page = snap.page, snap.time - page.lastTime < 0.5 else {
            guidance = GuidanceUI(readiness: .findingPage, primary: "Point at the page")
            return
        }
        let fit = PageFraming.fit(outline: layout.outline, cameraToPage: here, k: snap.k, imageSize: snap.imageSize,
                                  marginPx: 0.02 * min(snap.imageSize.x, snap.imageSize.y))
        if fit == .whole {
            let tol = a.tolerance
            guard steadiness.isSteady(window: Self.freeformSteadyS, now: snap.time, maxMmPerS: tol.maxSpeedMmS,
                                      maxDegPerS: tol.maxAngSpeedDegS) else {
                guidance = GuidanceUI(readiness: .holding, primary: "Hold still", aligned: true)
                return
            }
            guidance = GuidanceUI(readiness: .capturing)
            take(a)
            return
        }
        let centre = here.rigidInverse.transform(.zero)
        guidance = GuidanceUI(readiness: .aligning, primary: "Get the whole page in view",
                              secondary: fit == .tooBig ? ["Back up"] : [],
                              arrow: OffscreenArrow.direction(toCameraPoint: centre, k: snap.k, imageSize: snap.imageSize,
                                                              marginPx: 60))
    }

    private func status(_ snap: TrackingSnapshot) -> PhoneStatus {
        let board = snap.page.map {
            PhoneStatus.Board(locked: $0.locked, ageS: snap.time - $0.lastTime, markers: snap.markersUsed, rmsPx: $0.rmsPx,
                              tiltDeg: $0.tiltDeg, jitterMm: $0.jitterMm, generation: $0.boardGeneration)
        }
        var active: PhoneStatus.Active?
        if let a = self.active {
            let phase = placementPrompt != nil ? "placement" : capturing ? "capturing"
                : guidance.aligned ? "holding" : snap.cameraToPage == nil ? "finding page" : "aligning"
            var err: AlignmentReport?
            if let here = snap.cameraToPage, let t = a.target.flatMap({ Pose(rows: $0.cameraToPage) }) {
                err = Alignment.report(current: here, target: t)
            }
            active = .init(requestId: a.id, phase: phase, err: err)
        }
        return PhoneStatus(ts: Date().timeIntervalSince1970, app: foreground ? "foreground" : "background",
                           thermal: Self.thermal, battery: Self.battery,
                           tracking: .init(arkit: snap.arkit, board: board), cameraToPage: snap.cameraToPage?.rowMajor,
                           active: active, outbox: .init(pending: outboxPending, bytes: 0))
    }

    private static var thermal: String {
        switch ProcessInfo.processInfo.thermalState {
        case .nominal: "nominal"
        case .fair: "fair"
        case .serious: "serious"
        case .critical: "critical"
        @unknown default: "unknown"
        }
    }

    private static var battery: Double? {
        UIDevice.current.isBatteryMonitoringEnabled = true
        let level = UIDevice.current.batteryLevel
        return level < 0 ? nil : Double(level)
    }

    func show(_ message: String) {
        toast = message
        toastTask?.cancel()
        toastTask = Task { @MainActor in
            try? await Task.sleep(for: .seconds(4))
            if !Task.isCancelled { toast = nil }
        }
    }
}
