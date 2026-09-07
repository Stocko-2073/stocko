import Foundation
import SwiftUI
import UBotCore

/// The handful of things worth remembering between sessions.
@Observable
final class AppSettings {

    /// The robot's advertised name. It is an NVS setting on the robot (`set
    /// name`), so it has to be adjustable here rather than hard-coded.
    var robotName: String {
        didSet { UserDefaults.standard.set(robotName, forKey: Keys.robotName) }
    }

    /// Off by default: outdoors it is mostly wind noise, and switching it on
    /// costs an extra permission prompt on the first recording.
    var microphoneEnabled: Bool {
        didSet { UserDefaults.standard.set(microphoneEnabled, forKey: Keys.mic) }
    }

    private enum Keys {
        static let robotName = "com.stocko.ubot.robotName"
        static let mic = "com.stocko.ubot.micEnabled"
    }

    init() {
        let d = UserDefaults.standard
        robotName = d.string(forKey: Keys.robotName) ?? UBotGATT.defaultName
        microphoneEnabled = d.bool(forKey: Keys.mic)
    }
}
