// swift-tools-version: 6.0
import PackageDescription

let package = Package(
    name: "AdoptionCore",
    platforms: [.macOS(.v15)],
    products: [.library(name: "AdoptionCore", targets: ["AdoptionCore"])],
    targets: [
        .target(name: "AdoptionCore"),
        .testTarget(name: "AdoptionCoreTests", dependencies: ["AdoptionCore"]),
    ]
)
