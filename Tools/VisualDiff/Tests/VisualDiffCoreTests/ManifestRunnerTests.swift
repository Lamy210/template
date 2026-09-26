import Foundation
@testable import VisualDiffCore
import XCTest

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
        let metadata = try fixture.writeProfile(
            id: manifest.profile,
            to: fixture.currentProfileURL
        )

        let expected = try TestImageFactory.solid(width: 2, height: 2, rgba: [10, 20, 30, 255])
        let expectedPath = try XCTUnwrap(testCase.expected)
        try fixture.write(image: expected, relativePath: expectedPath)
        try fixture.write(image: expected, relativePath: testCase.current)

        let summary = try ManifestRunner.run(
            manifest: manifest,
            configuration: fixture.configuration(bootstrapRolling: false)
        )

        XCTAssertFalse(summary.hasFailures)
        XCTAssertEqual(summary.cases.map(\.status), [.passed])
        XCTAssertEqual(summary.cases.first?.profileFingerprint, metadata.profileFingerprint)
        let caseRoot = fixture.outputRoot.appendingPathComponent("settings-light", isDirectory: true)
        XCTAssertTrue(FileManager.default.fileExists(atPath: caseRoot.appendingPathComponent("expected.png").path))
        XCTAssertTrue(FileManager.default.fileExists(atPath: caseRoot.appendingPathComponent("actual.png").path))
        XCTAssertTrue(FileManager.default.fileExists(atPath: caseRoot.appendingPathComponent("diff.png").path))
        XCTAssertTrue(FileManager.default.fileExists(atPath: caseRoot.appendingPathComponent("report.json").path))
    }

    func testRollingBaselineAllowsObservedRuntimeDrift() throws {
        let fixture = try Fixture()
        let testCase = fixture.rollingCase(id: "dynamic")
        let manifest = try fixture.manifest(cases: [testCase])
        let currentMetadata = try fixture.writeProfile(
            id: manifest.profile,
            observedBuild: "25G83",
            to: fixture.currentProfileURL
        )
        let rollingMetadata = try fixture.writeProfile(
            id: manifest.profile,
            observedBuild: "25G84",
            to: fixture.rollingProfileURL
        )

        let current = try TestImageFactory.solid(width: 1, height: 1, rgba: [40, 50, 60, 255])
        try fixture.write(image: current, relativePath: testCase.current)
        try fixture.writeRollingBaseline(
            image: current,
            caseID: testCase.id,
            profileFingerprint: rollingMetadata.profileFingerprint
        )

        let summary = try ManifestRunner.run(
            manifest: manifest,
            configuration: fixture.configuration(bootstrapRolling: false)
        )

        XCTAssertEqual(currentMetadata.profileFingerprint, rollingMetadata.profileFingerprint)
        XCTAssertNotEqual(currentMetadata.observed, rollingMetadata.observed)
        XCTAssertFalse(summary.hasFailures)
        XCTAssertEqual(summary.cases.first?.status, .passed)
        XCTAssertEqual(summary.cases.first?.baselineReference, "run:12345")
    }

    func testRollingControlledProfileMismatchFailsBeforePixelComparison() throws {
        let fixture = try Fixture()
        let testCase = fixture.rollingCase(id: "dynamic")
        let manifest = try fixture.manifest(cases: [testCase])
        let current = try fixture.writeProfile(
            id: manifest.profile,
            controlled: fixture.controlledProfile(appearance: "light"),
            to: fixture.currentProfileURL
        )
        let rolling = try fixture.writeProfile(
            id: manifest.profile,
            controlled: fixture.controlledProfile(appearance: "dark"),
            to: fixture.rollingProfileURL
        )

        XCTAssertThrowsError(
            try ManifestRunner.run(
                manifest: manifest,
                configuration: fixture.configuration(bootstrapRolling: false)
            )
        ) { error in
            guard case ManifestRunnerError.rollingProfileFingerprintMismatch(
                expected: current.profileFingerprint,
                actual: rolling.profileFingerprint
            ) = error else {
                return XCTFail("Unexpected error: \(error)")
            }
        }
    }

    func testExactApprovalTurnsRollingMismatchIntoApprovedChange() throws {
        let fixture = try Fixture()
        let approvalPath = "Tests/VisualRegression/Approvals/dynamic.json"
        let testCase = fixture.rollingCase(id: "dynamic", approval: approvalPath)
        let manifest = try fixture.manifest(cases: [testCase])
        let currentMetadata = try fixture.writeProfile(
            id: manifest.profile,
            to: fixture.currentProfileURL
        )
        try fixture.writeProfile(id: manifest.profile, to: fixture.rollingProfileURL)

        let expected = try TestImageFactory.solid(width: 1, height: 1, rgba: [0, 0, 0, 255])
        let actual = try TestImageFactory.solid(width: 1, height: 1, rgba: [1, 0, 0, 255])
        let expectedURL = try fixture.writeRollingBaseline(
            image: expected,
            caseID: testCase.id,
            profileFingerprint: currentMetadata.profileFingerprint
        )
        let actualURL = fixture.root.appendingPathComponent(testCase.current)
        try actual.writePNG(to: actualURL)

        let approval = try VisualApproval(
            schemaVersion: 1,
            caseID: testCase.id,
            fromDigest: ImageDigest.sha256(fileAt: expectedURL),
            toDigest: ImageDigest.sha256(fileAt: actualURL),
            profileFingerprint: currentMetadata.profileFingerprint,
            reason: "Intentional redesign"
        )
        try fixture.writeApproval(approval, relativePath: approvalPath)

        let summary = try ManifestRunner.run(
            manifest: manifest,
            configuration: fixture.configuration(bootstrapRolling: false)
        )

        XCTAssertFalse(summary.hasFailures)
        XCTAssertEqual(summary.cases.first?.status, .approvedChange)
        XCTAssertEqual(summary.cases.first?.profileFingerprint, currentMetadata.profileFingerprint)
        XCTAssertGreaterThan(summary.cases.first?.changedPixelCount ?? 0, 0)
    }

    func testHumanProfileLabelCannotSubstituteForApprovalFingerprint() throws {
        let fixture = try Fixture()
        let approvalPath = "Tests/VisualRegression/Approvals/dynamic.json"
        let testCase = fixture.rollingCase(id: "dynamic", approval: approvalPath)
        let manifest = try fixture.manifest(cases: [testCase])
        let currentMetadata = try fixture.writeProfile(id: manifest.profile, to: fixture.currentProfileURL)
        try fixture.writeProfile(id: manifest.profile, to: fixture.rollingProfileURL)

        let expected = try TestImageFactory.solid(width: 1, height: 1, rgba: [0, 0, 0, 255])
        let actual = try TestImageFactory.solid(width: 1, height: 1, rgba: [1, 0, 0, 255])
        let expectedURL = try fixture.writeRollingBaseline(
            image: expected,
            caseID: testCase.id,
            profileFingerprint: currentMetadata.profileFingerprint
        )
        let actualURL = fixture.root.appendingPathComponent(testCase.current)
        try actual.writePNG(to: actualURL)

        let approval = try VisualApproval(
            schemaVersion: 1,
            caseID: testCase.id,
            fromDigest: ImageDigest.sha256(fileAt: expectedURL),
            toDigest: ImageDigest.sha256(fileAt: actualURL),
            profileFingerprint: manifest.profile,
            reason: "Incorrectly bound to label"
        )
        try fixture.writeApproval(approval, relativePath: approvalPath)

        let summary = try ManifestRunner.run(
            manifest: manifest,
            configuration: fixture.configuration(bootstrapRolling: false)
        )

        XCTAssertTrue(summary.hasFailures)
        XCTAssertEqual(summary.cases.first?.status, .failed)
    }

    func testStaleApprovalDoesNotAuthorizeDifferentCurrentImage() throws {
        let fixture = try Fixture()
        let approvalPath = "Tests/VisualRegression/Approvals/dynamic.json"
        let testCase = fixture.rollingCase(id: "dynamic", approval: approvalPath)
        let manifest = try fixture.manifest(cases: [testCase])
        let currentMetadata = try fixture.writeProfile(
            id: manifest.profile,
            to: fixture.currentProfileURL
        )
        try fixture.writeProfile(id: manifest.profile, to: fixture.rollingProfileURL)

        let expected = try TestImageFactory.solid(width: 1, height: 1, rgba: [0, 0, 0, 255])
        let actual = try TestImageFactory.solid(width: 1, height: 1, rgba: [2, 0, 0, 255])
        let expectedURL = try fixture.writeRollingBaseline(
            image: expected,
            caseID: testCase.id,
            profileFingerprint: currentMetadata.profileFingerprint
        )
        let actualURL = fixture.root.appendingPathComponent(testCase.current)
        try actual.writePNG(to: actualURL)

        let approval = try VisualApproval(
            schemaVersion: 1,
            caseID: testCase.id,
            fromDigest: ImageDigest.sha256(fileAt: expectedURL),
            toDigest: "sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
            profileFingerprint: currentMetadata.profileFingerprint,
            reason: "Approval for an older capture"
        )
        try fixture.writeApproval(approval, relativePath: approvalPath)

        let summary = try ManifestRunner.run(
            manifest: manifest,
            configuration: fixture.configuration(bootstrapRolling: false)
        )

        XCTAssertTrue(summary.hasFailures)
        XCTAssertEqual(summary.cases.first?.status, .failed)
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
        let testCase = fixture.rollingCase(id: "dynamic")
        let manifest = try fixture.manifest(cases: [testCase])
        try fixture.writeProfile(id: manifest.profile, to: fixture.currentProfileURL)
        let current = try TestImageFactory.solid(width: 1, height: 1, rgba: [40, 50, 60, 255])
        try fixture.write(image: current, relativePath: testCase.current)

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

    func testRollingProfileLabelMismatchFailsBeforePixelComparison() throws {
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

    func controlledProfile(appearance: String = "light") -> ControlledProfile {
        ControlledProfile(
            runnerFamily: "macos-26",
            architecture: "arm64",
            xcodePolicy: "26.6",
            locale: "en_US.UTF-8",
            language: "en",
            timezone: "UTC",
            appearance: appearance,
            displayScale: "2x",
            captureGeometry: "window:900x600",
            fixtureVersion: "fixture-v1",
            captureContractVersion: 1,
            comparatorSchemaVersion: 1
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

    func rollingCase(id: String, approval: String? = nil) -> VisualCase {
        VisualCase(
            id: id,
            baseline: .rollingMain,
            current: "artifacts/visual/current/\(id).png",
            expected: nil,
            maxChangedPixelRatio: 0,
            maxChannelDelta: 0,
            approval: approval
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

    @discardableResult
    func writeRollingBaseline(
        image: PixelImage,
        caseID: String,
        profileFingerprint: String
    ) throws -> URL {
        let imagesRoot = rollingRoot.appendingPathComponent("images", isDirectory: true)
        try FileManager.default.createDirectory(at: imagesRoot, withIntermediateDirectories: true)
        let imageURL = imagesRoot.appendingPathComponent("\(caseID).png", isDirectory: false)
        try image.writePNG(to: imageURL)
        let digest = try ImageDigest.sha256(fileAt: imageURL)
        let bundle = BaselineBundleManifest(
            schemaVersion: 1,
            sourceRepository: "Lamy210/template",
            workflow: "visual-regression.yml",
            sourceRunID: "12345",
            runAttempt: 1,
            sourceSHA: "0123456789abcdef0123456789abcdef01234567",
            profileFingerprint: profileFingerprint,
            previousBaselineReference: nil,
            cases: [BaselineBundleCase(
                id: caseID,
                digest: digest
            )]
        )
        let manifestURL = rollingRoot.appendingPathComponent("bundle-manifest.json", isDirectory: false)
        let data = try JSONEncoder().encode(bundle)
        try data.write(to: manifestURL, options: .atomic)
        return imageURL
    }

    func writeApproval(_ approval: VisualApproval, relativePath: String) throws {
        let url = root.appendingPathComponent(relativePath)
        try FileManager.default.createDirectory(
            at: url.deletingLastPathComponent(),
            withIntermediateDirectories: true
        )
        try JSONEncoder().encode(approval).write(to: url, options: .atomic)
    }

    @discardableResult
    func writeProfile(
        id: String,
        controlled: ControlledProfile? = nil,
        observedBuild: String = "25G83",
        to url: URL
    ) throws -> ProfileMetadata {
        let metadata = try ProfileMetadata(
            profile: id,
            controlled: controlled ?? controlledProfile(),
            observed: ObservedRuntime(
                macOSBuild: observedBuild,
                runnerImageVersion: "20260907.0351.1",
                xcodeBuild: "17G29"
            ),
            currentSHA: "abcdef"
        )
        try FileManager.default.createDirectory(
            at: url.deletingLastPathComponent(),
            withIntermediateDirectories: true
        )
        try JSONEncoder().encode(metadata).write(to: url, options: .atomic)
        return metadata
    }
}
