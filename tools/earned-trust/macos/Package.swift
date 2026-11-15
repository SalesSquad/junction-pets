// swift-tools-version: 5.9
import PackageDescription

let package = Package(
    name: "EarnedTrust",
    platforms: [.macOS(.v14)],
    products: [
        .executable(name: "EarnedTrust", targets: ["EarnedTrust"]),
        .executable(name: "trust-inspect", targets: ["TrustInspect"]),
        .library(name: "TrustCore", targets: ["TrustCore"])
    ],
    targets: [
        .target(name: "TrustCore"),
        .executableTarget(name: "EarnedTrust", dependencies: ["TrustCore"],
                          resources: [.copy("Resources/Packets")]),
        .executableTarget(name: "TrustInspect", dependencies: ["TrustCore"]),
        .testTarget(name: "TrustCoreTests", dependencies: ["TrustCore"])
    ]
)
