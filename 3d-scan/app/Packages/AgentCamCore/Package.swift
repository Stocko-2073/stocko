// swift-tools-version: 5.10
// Swift 5 language mode on purpose, as in UBotCore: ServerLink, the outbox and
// the uploader own serial queues and must never hop to the main actor.

import PackageDescription

let package = Package(
    name: "AgentCamCore",
    platforms: [.iOS("26.0"), .macOS("15.0")],
    products: [
        .library(name: "AgentCamCore", targets: ["AgentCamCore"]),
    ],
    targets: [
        // Protocol, geometry, tracking fusion, guidance and networking. No UIKit,
        // no ARKit, no OpenCV, so all of it is tested on the Mac with `swift test`.
        .target(name: "AgentCamCore", resources: [.copy("Resources/boards")]),
        // Shared examples and fixtures are read from app/protocol by path.
        .testTarget(name: "AgentCamCoreTests", dependencies: ["AgentCamCore"]),
    ]
)
