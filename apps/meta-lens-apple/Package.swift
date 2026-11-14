// swift-tools-version: 6.0
import PackageDescription

let package = Package(
    name: "ChibiLensApple",
    platforms: [.iOS(.v17), .macOS(.v14)],
    products: [
        .library(name: "ChibiLensCore", targets: ["ChibiLensCore"]),
        .library(name: "ChibiLensARKit", targets: ["ChibiLensARKit"]),
        .library(name: "ChibiLensUI", targets: ["ChibiLensUI"]),
        .executable(name: "chibi-lens-replay", targets: ["ChibiLensReplay"]),
        .executable(name: "ChibiLensDesktop", targets: ["ChibiLensDesktop"]),
    ],
    targets: [
        .target(name: "ChibiLensCore"),
        .target(name: "ChibiLensARKit", dependencies: ["ChibiLensCore"]),
        .target(name: "ChibiLensUI", dependencies: ["ChibiLensCore"]),
        .executableTarget(name: "ChibiLensReplay", dependencies: ["ChibiLensCore"]),
        .executableTarget(name: "ChibiLensDesktop", dependencies: ["ChibiLensUI"]),
        .testTarget(name: "ChibiLensCoreTests", dependencies: ["ChibiLensCore"]),
        .testTarget(name: "ChibiLensARKitTests", dependencies: ["ChibiLensARKit", "ChibiLensCore"]),
    ]
)
