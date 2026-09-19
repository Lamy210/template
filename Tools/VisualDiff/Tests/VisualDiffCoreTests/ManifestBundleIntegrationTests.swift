import Foundation
@testable import VisualDiffCore
import XCTest

final class ManifestBundleIntegrationTests: XCTestCase {
    func testEstablishedRollingCaseUsesValidatedBundleImage() throws {
        let fixture = try RollingBundleFixture()
        let profile = try fixture.writeProfiles()
        let expected = try TestImageFactory.solid(width: 1, height: 1, rgba: [10, 20, 30, 255])
        let testCase = fixture.rollingCase(id: "dynamic")
        try fixture.writeCurrent(expected, testCase: testCase)
        try fixture.writeBundle(
            profileFingerprint: profile.profileFingerprint,
            images: ["dynamic": expected]
        )
        let manifest = try fixture.manifest(cases: [testCase])

        let summary = try ManifestRunner.run(
            manifest: manifest,
            configuration: fixture.configuration(bootstrapRolling: false)
        )

        XCTAssertFalse(summary.hasFailures)
        XCTAssertEqual(summary.cases.first?.status, .passed)
        XCTAssertEqual(summary.cases.first?.baselineReference, "run:12345")
    }

    func testNewRollingCaseBootstrapsAgainstEstablishedBundle() throws {
        let fixture = try RollingBundleFixture()
        let profile = try fixture.writeProfiles()
        let existing = try TestImageFactory.solid(width: 1, height: 1, rgba: [1, 2, 3, 255])
        try fixture.writeBundle(
            profileFingerprint: profile.profileFingerprint,
            images: ["existing": existing]
        )

        let newCase = fixture.rollingCase(id: "new-screen")
        let current = try TestImageFactory.solid(width: 1, height: 1, rgba: [4, 5, 6, 255])
        try fixture.writeCurrent(current, testCase: newCase)
        let manifest = try fixture.manifest(cases: [newCase])

        let summary = try ManifestRunner.run(
            manifest: manifest,
            configuration: fixture.configuration(bootstrapRolling: false)
        )

        XCTAssertFalse(summary.hasFailures)
        XCTAssertEqual(summary.cases.first?.status, .bootstrap)
    }

    func testEstablishedCaseMissingImageFailsBundleValidation() throws {
        let fixture = try RollingBundleFixture()
        let profile = try fixture.writeProfiles()
        let testCase = fixture.rollingCase(id: "dynamic")
        let current = try TestImageFactory.solid(width: 1, height: 1, rgba: [7, 8, 9, 255])
        try fixture.writeCurrent(current, testCase: testCase)
        try fixture.writeBundleManifest(
            profileFingerprint: profile.profileFingerprint,
            cases: [
                BaselineBundleCase(
                    id: "dynamic",
                    digest: ImageDigest.sha256(Data("missing-image".utf8))
                )
            ]
        )
        let manifest = try fixture.manifest(cases: [testCase])

        XCTAssertThrowsError(try ManifestRunner.run(
            manifest: manifest,
            configuration: fixture.configuration(bootstrapRolling: true)
        )) { error in
            guard case BaselineBundleError.missingImage(caseID: "dynamic") = error else {
                return XCTFail("Unexpected error: \(error)")
            }
        }
    }
}

private final class RollingBundleFixture {
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

    func controlledProfile() -> ControlledProfile {
        ControlledProfile(
            runnerFamily: "macos-26",
            architecture: "arm64",
            xcodePolicy: "26.6",
            locale: "en_US.UTF-8",
            language: "en",
            timezone: "UTC",
            appearance: "light",
            displayScale: "2x",
            captureGeometry: "window:900x600",
            fixtureVersion: "fixture-v1",
            captureContractVersion: 1,
            comparatorSchemaVersion: 1
        )
    }

    @discardableResult
    func writeProfiles() throws -> ProfileMetadata {
        let controlled = controlledProfile()
        let observed = ObservedRuntime(
            macOSBuild: "25G83",
            runnerImageVersion: "20260907.0351.1",
            xcodeBuild: "26G86"
        )
        let current = try ProfileMetadata(
            profile: "macos-26-arm64-xcode-26.6",
            controlled: controlled,
            observed: observed,
            currentSHA: "abcdef"
        )
        let rolling = try ProfileMetadata(
            profile: current.profile,
            controlled: controlled,
            observed: observed,
            currentSHA: "baseline"
        )
        try writeJSON(current, to: currentProfileURL)
        try writeJSON(rolling, to: rollingProfileURL)
        return current
    }

    func manifest(cases: [VisualCase]) throws -> VisualManifest {
        try VisualManifest(
            schemaVersion: 1,
            profile: "macos-26-arm64-xcode-26.6",
            cases: cases
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

    func configuration(bootstrapRolling: Bool) -> ManifestRunConfiguration {
        ManifestRunConfiguration(
            repoRoot: root,
            currentProfileURL: currentProfileURL,
            rollingRoot: rollingRoot,
            rollingProfileURL: rollingProfileURL,
            outputRoot: outputRoot,
            currentSHA: "abcdef",
            baselineRunID: "12345",
            bootstrapRolling: bootstrapRolling
        )
    }

    func writeCurrent(_ image: PixelImage, testCase: VisualCase) throws {
        try image.writePNG(to: root.appendingPathComponent(testCase.current))
    }

    func writeBundle(
        profileFingerprint: String,
        images: [String: PixelImage]
    ) throws {
        let imagesRoot = rollingRoot.appendingPathComponent("images", isDirectory: true)
        try FileManager.default.createDirectory(at: imagesRoot, withIntermediateDirectories: true)
        var cases: [BaselineBundleCase] = []
        for (caseID, image) in images.sorted(by: { $0.key < $1.key }) {
            let url = imagesRoot.appendingPathComponent("\(caseID).png")
            try image.writePNG(to: url)
            let digest = try ImageDigest.sha256(fileAt: url)
            cases.append(BaselineBundleCase(
                id: caseID,
                digest: digest
            ))
        }
        try writeBundleManifest(profileFingerprint: profileFingerprint, cases: cases)
    }

    func writeBundleManifest(
        profileFingerprint: String,
        cases: [BaselineBundleCase]
    ) throws {
        let imagesRoot = rollingRoot.appendingPathComponent("images", isDirectory: true)
        try FileManager.default.createDirectory(at: imagesRoot, withIntermediateDirectories: true)
        let bundle = BaselineBundleManifest(
            schemaVersion: 1,
            sourceRepository: "Lamy210/template",
            workflow: "visual-regression.yml",
            sourceRunID: "12345",
            runAttempt: 1,
            sourceSHA: "0123456789abcdef0123456789abcdef01234567",
            profileFingerprint: profileFingerprint,
            previousBaselineReference: nil,
            cases: cases
        )
        try writeJSON(bundle, to: rollingRoot.appendingPathComponent("bundle-manifest.json"))
    }

    private func writeJSON(_ value: some Encodable, to url: URL) throws {
        try FileManager.default.createDirectory(
            at: url.deletingLastPathComponent(),
            withIntermediateDirectories: true
        )
        let data = try JSONEncoder().encode(value)
        try data.write(to: url, options: .atomic)
    }
}
