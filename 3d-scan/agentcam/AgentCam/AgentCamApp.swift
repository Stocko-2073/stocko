import SwiftUI

@main
struct AgentCamApp: App {
    @State private var model = AppModel()
    @Environment(\.scenePhase) private var scenePhase

    var body: some Scene {
        WindowGroup {
            RootView()
                .environment(model)
                .environment(model.settings)
                // Start from scenePhase, not a view's one-time task: RootView stays
                // mounted across background and foreground (see u-bot). Only a real
                // background stops things: Control Center (e.g. to start a screen
                // recording) makes the app inactive, and must not interrupt AR.
                .onChange(of: scenePhase, initial: true) { _, phase in
                    model.setForeground(phase != .background)
                }
        }
    }
}
