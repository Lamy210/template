// swift-tools-version: 6.0
import PackageDescription

let package = Package(
    name: "VisualDiff",
    platforms: [.macOS(.v14)],
    products: [
        .library(name: "VisualDiffCore", targets: ["VisualDiffCore"]),
    ],
    targets: [
        .target(name: "VisualDiffCore"),
        .testTarget(name: "VisualDiffCoreTests", dependencies: ["VisualDiffCore"]),
    ]
)
