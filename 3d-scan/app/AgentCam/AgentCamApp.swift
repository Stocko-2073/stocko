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
                // mounted across background and foreground (see u-bot).
                .onChange(of: scenePhase, initial: true) { _, phase in
                    model.setForeground(phase == .active)
                }
        }
    }
}
