// swift-tools-version: 6.0
import PackageDescription

let package = Package(
    name: "VisualDiff",
    platforms: [.macOS(.v14)],
    products: [
        .library(name: "VisualDiffCore", targets: ["VisualDiffCore"]),
        .executable(name: "visual-diff", targets: ["visual-diff"])
    ],
    targets: [
        .target(name: "VisualDiffCore"),
        .executableTarget(name: "visual-diff", dependencies: ["VisualDiffCore"]),
        .testTarget(name: "VisualDiffCoreTests", dependencies: ["VisualDiffCore"])
    ]
)
