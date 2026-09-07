// swift-tools-version: 5.10
// Swift 5 language mode on purpose. Xcode 26 defaults new projects to Swift 6
// with MainActor default isolation, which is right for the SwiftUI layer and
// wrong for BLERobotLink and DriveTicker -- those live on their own serial
// queue and must never hop to the main actor. Migrate deliberately later.

import PackageDescription

let package = Package(
    name: "UBotCore",
    platforms: [.iOS(.v17), .macOS(.v14)],
    products: [
        .library(name: "UBotCore", targets: ["UBotCore"]),
        .executable(name: "ubotctl", targets: ["ubotctl"]),
    ],
    targets: [
        // The protocol and transport. No UIKit, no SwiftUI -- which is what
        // lets the same code drive the robot from a Mac command line and from
        // the phone, and what makes the codec testable with no simulator.
        .target(name: "UBotCore"),

        // The bench harness. Scans, connects, streams status, drives. This is
        // how the GATT contract gets verified against real hardware before the
        // iOS app exists.
        .executableTarget(name: "ubotctl", dependencies: ["UBotCore"]),

        .testTarget(name: "UBotCoreTests", dependencies: ["UBotCore"]),
    ]
)
