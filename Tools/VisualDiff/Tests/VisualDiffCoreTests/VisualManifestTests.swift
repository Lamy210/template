import Foundation
@testable import VisualDiffCore
import XCTest

final class VisualManifestTests: XCTestCase {
    func testDecodesValidGitAndRollingCases() throws {
        let manifest = try VisualManifest.decode(Data(validManifest.utf8))

        XCTAssertEqual(manifest.schemaVersion, 1)
        XCTAssertEqual(manifest.profile, "macos-26-arm64-xcode-26.6")
        XCTAssertEqual(manifest.cases.count, 2)
        XCTAssertEqual(manifest.cases[0].baseline, .git)
        XCTAssertEqual(manifest.cases[1].baseline, .rollingMain)
    }

    func testRejectsUnsupportedSchemaVersion() {
        assertManifestFails(validManifest.replacingOccurrences(of: "\"schemaVersion\": 1", with: "\"schemaVersion\": 2"))
    }

    func testRejectsAbsoluteCurrentPath() {
        assertManifestFails(validManifest.replacingOccurrences(
            of: "artifacts/visual/current/settings-light.png",
            with: "/tmp/settings-light.png"
        ))
    }

    func testRejectsCurrentPathTraversal() {
        assertManifestFails(validManifest.replacingOccurrences(
            of: "artifacts/visual/current/settings-light.png",
            with: "artifacts/visual/current/../secret.png"
        ))
    }

    func testRejectsCurrentPathOutsideCaptureRoot() {
        assertManifestFails(validManifest.replacingOccurrences(
            of: "artifacts/visual/current/settings-light.png",
            with: "tmp/settings-light.png"
        ))
    }

    func testRejectsGitExpectedPathOutsideBaselineRoot() {
        assertManifestFails(validManifest.replacingOccurrences(
            of: "Tests/VisualBaselines/macos-26-arm64-xcode-26.6/settings-light.png",
            with: "Tests/Other/settings-light.png"
        ))
    }

    func testRejectsGitCaseWithoutExpectedPath() {
        let json = """
        {
          "schemaVersion": 1,
          "profile": "macos-26-arm64-xcode-26.6",
          "cases": [{
            "id": "settings-light",
            "baseline": "git",
            "current": "artifacts/visual/current/settings-light.png",
            "maxChangedPixelRatio": 0.0,
            "maxChannelDelta": 0
          }]
        }
        """
        assertManifestFails(json)
    }

    func testRejectsDuplicateCaseIds() {
        let duplicate = validManifest.replacingOccurrences(
            of: "\"id\": \"large-dynamic-screen\"",
            with: "\"id\": \"settings-light\""
        )
        assertManifestFails(duplicate)
    }

    func testRejectsEmptyCaseId() {
        assertManifestFails(validManifest.replacingOccurrences(
            of: "\"id\": \"settings-light\"",
            with: "\"id\": \"\""
        ))
    }

    func testRejectsChangedPixelRatioOutsideZeroToOne() {
        assertManifestFails(validManifest.replacingOccurrences(
            of: "\"maxChangedPixelRatio\": 0.0",
            with: "\"maxChangedPixelRatio\": 1.1"
        ))
    }

    func testRejectsChannelDeltaOutsideByteRange() {
        assertManifestFails(validManifest.replacingOccurrences(
            of: "\"maxChannelDelta\": 8",
            with: "\"maxChannelDelta\": 256"
        ))
    }

    func testRejectsExpectedPathOnRollingCase() {
        let invalid = validManifest.replacingOccurrences(
            of: "\"current\": \"artifacts/visual/current/large-dynamic-screen.png\",\n      \"maxChangedPixelRatio\"",
            with: "\"current\": \"artifacts/visual/current/large-dynamic-screen.png\",\n      \"expected\": \"Tests/VisualBaselines/macos-26-arm64-xcode-26.6/rolling.png\",\n      \"maxChangedPixelRatio\""
        )
        assertManifestFails(invalid)
    }

    private func assertManifestFails(
        _ json: String,
        file: StaticString = #filePath,
        line: UInt = #line
    ) {
        XCTAssertThrowsError(try VisualManifest.decode(Data(json.utf8)), file: file, line: line)
    }

    private var validManifest: String {
        """
        {
          "schemaVersion": 1,
          "profile": "macos-26-arm64-xcode-26.6",
          "cases": [
            {
              "id": "settings-light",
              "baseline": "git",
              "current": "artifacts/visual/current/settings-light.png",
              "expected": "Tests/VisualBaselines/macos-26-arm64-xcode-26.6/settings-light.png",
              "maxChangedPixelRatio": 0.0,
              "maxChannelDelta": 0
            },
            {
              "id": "large-dynamic-screen",
              "baseline": "rolling-main",
              "current": "artifacts/visual/current/large-dynamic-screen.png",
              "maxChangedPixelRatio": 0.001,
              "maxChannelDelta": 8
            }
          ]
        }
        """
    }
}
