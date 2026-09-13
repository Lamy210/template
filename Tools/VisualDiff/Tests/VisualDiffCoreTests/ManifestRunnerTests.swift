import Foundation
import XCTest
@testable import VisualDiffCore

final class ManifestRunnerTests: XCTestCase {
    func testCurrentProfileMismatchFailsBeforeCaptureLookup() throws {
        let fixture = try Fixture()
        let manifest = try fixture.manifest(
            cases: [fixture.gitCase(id: "settings-light")]
        )
        try fixture.writeProfile(id: "different-profile", to: fixture.currentProfileURL)

        XCTAssertThrowsError(
            try ManifestRunner.run(
                manifest: manifest,
                configuration: fixture.configuration(bootstrapRolling: false)
            )
        ) { error in
            guard case ManifestRunnerError.profileMismatch(
                expected: "macos-26-arm64-xcode-26.6",
                actual: "different-profile"
            ) = error else {
                return XCTFail("Unexpected error: \(error)")
            }
        }
    }

    func testGitBaselineComparisonWritesReviewArtifacts() throws {
        let fixture = try Fixture()
        let testCase = fixture.gitCase(id: "settings-light")
        let manifest = try fixture.manifest(cases: [testCase])
        try fixture.writeProfile(id: manifest.profile, to: fixture.currentProfileURL)

        let expected = try TestImageFactory.solid(width: 2, height: 2, rgba: [10, 20, 30, 255])
        try fixture.write(image: expected, relativePath: testCase.expected!)
        try fixture.write(image: expected, relativePath: testCase.current)

        let summary = try ManifestRunner.run(
            manifest: manifest,
            configuration: fixture.configuration(bootstrapRolling: false)
        )

        XCTAssertFalse(summary.hasFailures)
        XCTAssertEqual(summary.cases.map(\.status), [.passed])
        let caseRoot = fixture.outputRoot.appendingPathComponent("settings-light", isDirectory: true)
        XCTAssertTrue(FileManager.default.fileExists(atPath: caseRoot.appendingPathComponent("expected.png").path))
        XCTAssertTrue(FileManager.default.fileExists(atPath: caseRoot.appendingPathComponent("actual.png").path))
        XCTAssertTrue(FileManager.default.fileExists(atPath: caseRoot.appendingPathComponent("diff.png").path))
        XCTAssertTrue(FileManager.default.fileExists(atPath: caseRoot.appendingPathComponent("report.json").path))
    }

    func testRollingBaselineUsesOnlyRollingRoot() throws {
        let fixture = try Fixture()
        let testCase = fixture.rollingCase(id: "dynamic")
        let manifest = try fixture.manifest(cases: [testCase])
        try fixture.writeProfile(id: manifest.profile, to: fixture.currentProfileURL)
        try fixture.writeProfile(id: manifest.profile, to: fixture.rollingProfileURL)

        let current = try TestImageFactory.solid(width: 1, height: 1, rgba: [40, 50, 60, 255])
        try fixture.write(image: current, relativePath: testCase.current)
        try current.writePNG(to: fixture.rollingRoot.appendingPathComponent("dynamic.png"))

        let summary = try ManifestRunner.run(
            manifest: manifest,
            configuration: fixture.configuration(bootstrapRolling: false)
        )

        XCTAssertFalse(summary.hasFailures)
        XCTAssertEqual(summary.cases.first?.status, .passed)
        XCTAssertEqual(summary.cases.first?.baselineReference, "run:12345")
    }

    func testMissingRollingBaselineIsExplicitBootstrapWhenEnabled() throws {
        let fixture = try Fixture()
        let testCase = fixture.rollingCase(id: "dynamic")
        let manifest = try fixture.manifest(cases: [testCase])
        try fixture.writeProfile(id: manifest.profile, to: fixture.currentProfileURL)
        let current = try TestImageFactory.solid(width: 1, height: 1, rgba: [40, 50, 60, 255])
        try fixture.write(image: current, relativePath: testCase.current)

        let summary = try ManifestRunner.run(
            manifest: manifest,
            configuration: fixture.configuration(
                bootstrapRolling: true,
                includeRollingRoot: false
            )
        )

        XCTAssertFalse(summary.hasFailures)
        XCTAssertEqual(summary.cases.first?.status, .bootstrap)
        XCTAssertNotEqual(summary.cases.first?.status, .passed)
    }

    func testMissingRollingBaselineFailsWhenBootstrapDisabled() throws {
        let fixture = try Fixture()
        let manifest = try fixture.manifest(cases: [fixture.rollingCase(id: "dynamic")])
        try fixture.writeProfile(id: manifest.profile, to: fixture.currentProfileURL)

        XCTAssertThrowsError(
            try ManifestRunner.run(
                manifest: manifest,
                configuration: fixture.configuration(
                    bootstrapRolling: false,
                    includeRollingRoot: false
                )
            )
        ) { error in
            guard case ManifestRunnerError.missingRollingBaseline = error else {
                return XCTFail("Unexpected error: \(error)")
            }
        }
    }

    func testRollingProfileMismatchFailsBeforePixelComparison() throws {
        let fixture = try Fixture()
        let testCase = fixture.rollingCase(id: "dynamic")
        let manifest = try fixture.manifest(cases: [testCase])
        try fixture.writeProfile(id: manifest.profile, to: fixture.currentProfileURL)
        try fixture.writeProfile(id: "old-profile", to: fixture.rollingProfileURL)

        XCTAssertThrowsError(
            try ManifestRunner.run(
                manifest: manifest,
                configuration: fixture.configuration(bootstrapRolling: false)
            )
        ) { error in
            guard case ManifestRunnerError.rollingProfileMismatch(
                expected: "macos-26-arm64-xcode-26.6",
                actual: "old-profile"
            ) = error else {
                return XCTFail("Unexpected error: \(error)")
            }
        }
    }
}

private final class Fixture {
    let root: URL
    let outputRoot: URL
    let rollingRoot: URL
    let currentProfileURL: URL
    let rollingProfileURL: URL

    init() throws {
        root = FileManager.default.temporaryDirectory
            .appendingPathComponent(UUID().uuidString, isDirectory: true)
        outputRoot = root.appendingPathComponent("artifacts/visual/report", isDirectory: true)
        rollingRoot = root.appendingPathComponent("rolling", isDirectory: true)
        currentProfileURL = root.appendingPathComponent("artifacts/visual/current/profile.json")
        rollingProfileURL = rollingRoot.appendingPathComponent("profile.json")
        try FileManager.default.createDirectory(at: rollingRoot, withIntermediateDirectories: true)
    }

    deinit {
        try? FileManager.default.removeItem(at: root)
    }

    func manifest(cases: [VisualCase]) throws -> VisualManifest {
        try VisualManifest(
            schemaVersion: 1,
            profile: "macos-26-arm64-xcode-26.6",
            cases: cases
        )
    }

    func gitCase(id: String) -> VisualCase {
        VisualCase(
            id: id,
            baseline: .git,
            current: "artifacts/visual/current/\(id).png",
            expected: "Tests/VisualBaselines/macos-26-arm64-xcode-26.6/\(id).png",
            maxChangedPixelRatio: 0,
            maxChannelDelta: 0
        )
    }

    func rollingCase(id: String) -> VisualCase {
        VisualCase(
            id: id,
            baseline: .rollingMain,
            current: "artifacts/visual/current/\(id).png",
            expected: nil,
            maxChangedPixelRatio: 0,
            maxChannelDelta: 0
        )
    }

    func configuration(
        bootstrapRolling: Bool,
        includeRollingRoot: Bool = true
    ) -> ManifestRunConfiguration {
        ManifestRunConfiguration(
            repoRoot: root,
            currentProfileURL: currentProfileURL,
            rollingRoot: includeRollingRoot ? rollingRoot : nil,
            rollingProfileURL: includeRollingRoot ? rollingProfileURL : nil,
            outputRoot: outputRoot,
            currentSHA: "abcdef",
            baselineRunID: includeRollingRoot ? "12345" : nil,
            bootstrapRolling: bootstrapRolling
        )
    }

    func write(image: PixelImage, relativePath: String) throws {
        try image.writePNG(to: root.appendingPathComponent(relativePath))
    }

    func writeProfile(id: String, to url: URL) throws {
        let metadata = ProfileMetadata(
            schemaVersion: 1,
            profile: id,
            runnerOS: "macOS",
            runnerArch: "ARM64",
            xcodePath: "/Applications/Xcode_26.6.app/Contents/Developer",
            xcodeVersion: "Xcode 26.6",
            locale: "en_US.UTF-8",
            language: "en",
            timezone: "UTC",
            currentSHA: "abcdef"
        )
        try FileManager.default.createDirectory(at: url.deletingLastPathComponent(), withIntermediateDirectories: true)
        try JSONEncoder().encode(metadata).write(to: url, options: .atomic)
    }
}
