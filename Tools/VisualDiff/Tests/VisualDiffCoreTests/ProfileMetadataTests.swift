import Foundation
@testable import VisualDiffCore
import XCTest

final class ProfileMetadataTests: XCTestCase {
    func testControlledProfileFingerprintIsStable() throws {
        let profile = makeControlledProfile()

        XCTAssertEqual(profile.fingerprint, profile.fingerprint)
        XCTAssertTrue(profile.fingerprint.hasPrefix("sha256:"))
        XCTAssertEqual(profile.fingerprint.count, 71)
    }

    func testAnyControlledFieldChangeChangesFingerprint() {
        let baseline = makeControlledProfile()
        let changed = makeControlledProfile(appearance: "dark")

        XCTAssertNotEqual(baseline.fingerprint, changed.fingerprint)
    }

    func testObservedRuntimeDriftDoesNotChangeControlledFingerprint() throws {
        let controlled = makeControlledProfile()
        let first = try ProfileMetadata(
            profile: "canonical-macos",
            controlled: controlled,
            observed: ObservedRuntime(
                macOSBuild: "25G83",
                runnerImageVersion: "20260907.0351.1",
                xcodeBuild: "17G29"
            ),
            currentSHA: "aaa"
        )
        let second = try ProfileMetadata(
            profile: "canonical-macos",
            controlled: controlled,
            observed: ObservedRuntime(
                macOSBuild: "25G84",
                runnerImageVersion: "20260914.1000.1",
                xcodeBuild: "17G30"
            ),
            currentSHA: "bbb"
        )

        XCTAssertEqual(first.profileFingerprint, second.profileFingerprint)
        XCTAssertNotEqual(first.observed, second.observed)
    }

    func testDecodeCanonicalizesControlledProfileKeyOrder() throws {
        let fingerprint = makeControlledProfile().fingerprint
        let json = """
        {
          "schemaVersion": 2,
          "profile": "canonical-macos",
          "controlled": {
            "timezone": "UTC",
            "runnerFamily": "macos-26",
            "locale": "en_US.UTF-8",
            "language": "en",
            "xcodePolicy": "26.6",
            "architecture": "arm64",
            "appearance": "light",
            "displayScale": "2x",
            "captureGeometry": "window:900x600",
            "fixtureVersion": "fixture-v1",
            "captureContractVersion": 1,
            "comparatorSchemaVersion": 1
          },
          "observed": {
            "macOSBuild": "25G83",
            "runnerImageVersion": "20260907.0351.1",
            "xcodeBuild": "17G29"
          },
          "profileFingerprint": "\(fingerprint)",
          "currentSHA": "abcdef"
        }
        """

        let metadata = try ProfileMetadata.decode(Data(json.utf8))

        XCTAssertEqual(metadata.profileFingerprint, fingerprint)
        XCTAssertEqual(metadata.controlled.fingerprint, fingerprint)
    }

    func testRejectsStoredFingerprintThatDoesNotMatchControlledProfile() {
        let metadata = try? ProfileMetadata(
            profile: "canonical-macos",
            controlled: makeControlledProfile(),
            observed: ObservedRuntime(
                macOSBuild: "25G83",
                runnerImageVersion: "20260907.0351.1",
                xcodeBuild: "17G29"
            ),
            currentSHA: "abcdef"
        )
        XCTAssertNotNil(metadata)

        let json = """
        {
          "schemaVersion": 2,
          "profile": "canonical-macos",
          "controlled": {
            "runnerFamily": "macos-26",
            "architecture": "arm64",
            "xcodePolicy": "26.6",
            "locale": "en_US.UTF-8",
            "language": "en",
            "timezone": "UTC",
            "appearance": "light",
            "displayScale": "2x",
            "captureGeometry": "window:900x600",
            "fixtureVersion": "fixture-v1",
            "captureContractVersion": 1,
            "comparatorSchemaVersion": 1
          },
          "observed": {
            "macOSBuild": "25G83",
            "runnerImageVersion": "20260907.0351.1",
            "xcodeBuild": "17G29"
          },
          "profileFingerprint": "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
          "currentSHA": "abcdef"
        }
        """

        XCTAssertThrowsError(try ProfileMetadata.decode(Data(json.utf8)))
    }

    private func makeControlledProfile(appearance: String = "light") -> ControlledProfile {
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
}
