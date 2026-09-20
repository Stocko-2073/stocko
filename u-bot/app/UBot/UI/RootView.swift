import SwiftUI
import UBotCore

struct RootView: View {

    @Environment(RobotController.self) private var controller
    @Environment(AppSettings.self) private var settings
    @Environment(ScreenRecorder.self) private var recorder
    @Environment(CameraSession.self) private var camera

    @State private var surface = ControlSurfaceModel()
    @State private var thermal = ProcessInfo.processInfo.thermalState

    var body: some View {
        ZStack(alignment: .top) {
            cameraBackground
                .ignoresSafeArea()

            VStack(spacing: 10) {
                TopHUD(controller: controller, recorder: recorder, thermal: thermal)
                StateCardView(card: controller.stateCard) { controller.send($0) }

                Spacer(minLength: 0)

                HStack {
                    Spacer()
                    RecordButton(recorder: recorder, onTap: toggleRecording)
                }
                .padding(.horizontal, 22)
                .padding(.bottom, 2)

                controlBlock
            }
            .padding(.top, 6)

            ToastLayer(toast: controller.toast)
                .padding(.top, 60)
                .animation(.spring(duration: 0.3), value: controller.toast)
        }
        .background(UBotPalette.bg)
        .preferredColorScheme(.dark)
        .persistentSystemOverlays(.hidden)
        .statusBarHidden()
        .task { bootstrap() }
        .onChange(of: controller.lock) { old, new in
            // joystick.html does `if (why && timer) release(false)`. A fault or
            // a disable must not leave the last non-zero command on the wire.
            if old == nil, let new {
                surface.forceRelease()
                controller.emergencyRelease(alsoStop: false)
                controller.show(new.reason, kind: .warning)
            }
            surface.lock = new
        }
        .onReceive(NotificationCenter.default.publisher(
            for: ProcessInfo.thermalStateDidChangeNotification)) { _ in
            thermal = ProcessInfo.processInfo.thermalState
        }
        .sheet(isPresented: pendingPreviewBinding) {
            if let preview = recorder.pendingPreview {
                RecordingPreview(controller: preview) { recorder.clearPendingPreview() }
                    .ignoresSafeArea()
            }
        }
    }

    // MARK: Pieces

    @ViewBuilder
    private var cameraBackground: some View {
        if camera.isAuthorized {
            CameraPreview(session: camera.session)
                .accessibilityElement(children: .ignore)
                .accessibilityLabel("Live camera")
                .accessibilityValue(camera.isRunning && camera.interruption == nil ? "Running" : "Paused")
                .overlay(alignment: .top) {
                    if let interruption = camera.interruption {
                        Text(interruption)
                            .font(.system(size: 13))
                            .foregroundStyle(UBotPalette.mute)
                            .padding(.top, 140)
                    }
                }
        } else {
            // No camera in the Simulator, and the operator may have declined.
            // Either way the app still has to drive a robot.
            LinearGradient(colors: [Color(hex: 0x14171D), Color(hex: 0x0A0C0F)],
                           startPoint: .top, endPoint: .bottom)
                .overlay(alignment: .top) {
                    Text(cameraFallbackText)
                        .font(.system(size: 13))
                        .foregroundStyle(UBotPalette.mute)
                        .padding(.top, 140)
                }
        }
    }

    private var cameraFallbackText: String {
        #if targetEnvironment(simulator)
        return "No camera in the Simulator"
        #else
        return "Camera not available"
        #endif
    }

    private var controlBlock: some View {
        VStack(spacing: 10) {
            // The commanded/measured panel used to sit here. It was taking too
            // much of the screen over live camera, so it is out of the layout
            // -- TelemetryPanel.swift is kept, unreferenced, because the
            // measured wheel speeds are the only stall evidence the app has.
            Text(readout)
                .font(.system(size: 13))
                .telemetryDigits()
                .foregroundStyle(controller.lock == nil ? UBotPalette.fg : UBotPalette.mute)
                .frame(minHeight: 18)

            // Sized for thumb travel, not for looks. Every extra point of
            // radius is another point you have to move to add rate, which is
            // the cheapest sensitivity control there is -- and unlike a curve
            // it costs nothing at full deflection.
            JoystickPad(model: surface)
                .frame(maxWidth: 250)
                .padding(.vertical, 2)

            PowerBar(controller: controller)
        }
        .padding(.top, 12)
        .padding(.bottom, 10)
        .background {
            // The controls sit over live camera, which outdoors can be a bright
            // lawn. Without a scrim the whole lower third becomes unreadable in
            // exactly the conditions the robot is used in.
            LinearGradient(colors: [.clear, .black.opacity(0.55), .black.opacity(0.8)],
                           startPoint: .top, endPoint: .bottom)
                .ignoresSafeArea(edges: .bottom)
        }
    }

    /// Mirrors `#cmd`: the lock reason wins, then the live command, then the
    /// invitation.
    private var readout: String {
        if let lock = controller.lock { return lock.reason }
        guard let s = controller.status, s.isCommandActive else { return "Drag the stick to drive" }
        return String(format: "forward %.2f m/s \u{00B7} turn %.2f rad/s",
                      s.commandedMetersPerSec, s.commandedRadiansPerSec)
    }

    private var pendingPreviewBinding: Binding<Bool> {
        Binding(get: { recorder.pendingPreview != nil },
                set: { if !$0 { recorder.clearPendingPreview() } })
    }

    // MARK: Wiring

    private func bootstrap() {
        surface.lock = controller.lock
        surface.onEngage  = { controller.engage($0) }
        surface.onUpdate  = { controller.update($0) }
        surface.onRelease = { controller.releaseStick() }
        surface.onBlocked = { controller.show($0.reason, kind: .warning) }

        recorder.microphoneEnabled = settings.microphoneEnabled
        controller.start()
    }

    private func toggleRecording() {
        Task {
            if recorder.isRecording {
                await recorder.stopAndSave()
                if case .failed(let why) = recorder.state {
                    controller.show(why, kind: .bad)
                    recorder.dismissMessage()
                } else if case .savedNeedsShare = recorder.state {
                    controller.show("Saved, but Photos access was declined.", kind: .warning)
                } else {
                    controller.show("Saved to Photos.")
                }
            } else {
                recorder.microphoneEnabled = settings.microphoneEnabled
                await recorder.start()
                if case .failed(let why) = recorder.state {
                    controller.show(why, kind: .bad)
                    recorder.dismissMessage()
                }
            }
        }
    }
}
