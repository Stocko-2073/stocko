import SwiftUI
import UBotCore

@main
struct UBotApp: App {

    @State private var settings: AppSettings
    @State private var controller: RobotController
    @State private var recorder = ScreenRecorder()
    @State private var camera = CameraSession()

    @Environment(\.scenePhase) private var scenePhase

    @MainActor
    init() {
        let settings = AppSettings()
        // CoreBluetooth reports .unsupported in the Simulator and there is no
        // camera either, so the Simulator runs against a fake robot. That is
        // what makes the whole interface -- every lock reason, every fault
        // state -- buildable and screenshottable without carrying hardware to
        // the desk.
        #if targetEnvironment(simulator)
        let link: RobotLink = MockRobotLink()
        #else
        let link: RobotLink = BLERobotLink(nameFilter: settings.robotName)
        #endif
        _settings = State(initialValue: settings)
        _controller = State(initialValue: RobotController(link: link))
    }

    var body: some Scene {
        WindowGroup {
            RootView()
                .environment(controller)
                .environment(settings)
                .environment(recorder)
                .environment(camera)
        }
        .onChange(of: scenePhase) { _, phase in
            switch phase {
            case .active:
                // The phone must not auto-lock mid-drive: locking drops the BLE
                // link and kills any ReplayKit recording at the same moment.
                UIApplication.shared.isIdleTimerDisabled = true

            case .inactive:
                // A system alert -- including ReplayKit's own permission prompt
                // and Control Center being pulled down -- makes the scene
                // inactive without backgrounding it. Zeroing the drive is the
                // right response; a full stop would be needlessly disruptive at
                // the exact moment the operator presses Record.
                controller.emergencyRelease(alsoStop: false)

            case .background:
                // Actually leaving. Stop the robot explicitly, then let the
                // firmware's 500 ms deadman be the backstop it was built to be.
                controller.emergencyRelease(alsoStop: true)
                UIApplication.shared.isIdleTimerDisabled = false
                camera.stop()

            @unknown default:
                controller.emergencyRelease(alsoStop: false)
            }
        }
    }
}
