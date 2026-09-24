import Foundation
import Observation

/// User settings, kept in UserDefaults.
@MainActor @Observable
final class Settings {
    /// Overrides Bonjour: "host", "host:port" or a URL. Empty means discover.
    var manualServer: String {
        didSet { UserDefaults.standard.set(manualServer, forKey: "manualServer") }
    }
    var showDebug: Bool {
        didSet { UserDefaults.standard.set(showDebug, forKey: "showDebug") }
    }

    init() {
        manualServer = UserDefaults.standard.string(forKey: "manualServer") ?? ""
        showDebug = UserDefaults.standard.bool(forKey: "showDebug")
    }
}
