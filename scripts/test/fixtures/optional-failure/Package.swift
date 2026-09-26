// swift-tools-version: 6.0
import PackageDescription

let package = Package(
    name: "OptionalFailureFixture",
    platforms: [.macOS(.v13)],
    targets: [
        .target(name: "OptionalFailureFixture"),
        .testTarget(
            name: "OptionalFailureTests",
            dependencies: ["OptionalFailureFixture"]
        )
    ]
)
