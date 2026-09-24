// swift-tools-version: 5.10
// Swift 5 language mode on purpose, as in UBotCore: the detector runs on the
// tracking session's own queue and must never hop to the main actor.

import PackageDescription

let package = Package(
    name: "AgentCamVision",
    platforms: [.iOS("26.0"), .macOS("15.0")],
    products: [
        .library(name: "AgentCamVision", targets: ["AgentCamVision"]),
    ],
    dependencies: [
        // Prebuilt opencv2.xcframework (iOS, arm64 Simulator and macOS slices),
        // built in CI with OpenCV's own platforms/apple/build_xcframework.py.
        // Keep the version in step with opencv-python-headless in agentcam/mcp so
        // the phone and the Mac see the same detections.
        .package(url: "https://github.com/yeatse/opencv-spm", exact: "4.13.0"),
        .package(path: "../AgentCamCore"),
    ],
    targets: [
        // C++ shim over OpenCV. Its public header is plain C, so Swift never
        // sees a C++ type.
        .target(
            name: "ArucoBridge",
            dependencies: [.product(name: "OpenCV", package: "opencv-spm")]
        ),
        .target(name: "AgentCamVision", dependencies: ["ArucoBridge", "AgentCamCore"]),
        // Fixtures are read from agentcam/protocol/fixtures by path (#filePath).
        .testTarget(name: "AgentCamVisionTests", dependencies: ["AgentCamVision"]),
    ],
    cxxLanguageStandard: .cxx17
)
